#!/usr/bin/env python3
"""
verify_identity.py — the measurement the ByrdHouse belt was missing.

Answers the ONLY question that matters for face swap:
    "Does this output actually carry Carey's identity, or is it just the
     target with recolored skin?"

Contract (what the belt calls):
    score = identity_score(output_image, reference_photos, bbox=None,
                           source_target=None)
    -> dict: { identity_score, backend, face_detected, target_similarity,
               method_guess }

Backends, tried in order (configurable):
    1. arcface  (InsightFace buffalo_l) — best when a face is DETECTED on the crop.
                 Anime faces often aren't detected by real-face detectors, so:
    2. clip     (open_clip or transformers CLIP) — image-image similarity that
                 works across the photo<->anime domain gap.

This file is dependency-light and guarded: if no ML backend is installed it still
runs and returns backend="none" with a clear message, so it can be smoke-tested
anywhere. Run `python verify_identity.py --selftest` to verify the cosine math
with no external models.

Wired into byrdjudge.judge_card(): identity cards get scores.identity_score +
method_guess recorded on the sidecar and via the router review. On a machine with
no ML backend the judge records the result as unmeasured rather than inventing a
number — the belt's honesty rule.
"""

from __future__ import annotations
import argparse
import glob
import json
import os
import sys
from typing import Optional, Sequence

# ---------------------------------------------------------------------------
# math helpers (no external deps)
# ---------------------------------------------------------------------------
def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return num / (na * nb)


def _expand_refs(reference) -> list[str]:
    """Accept a file, a dir, a glob, or an explicit list of paths.

    The list form matters: scoring identity against a whole reference FOLDER
    silently includes synthetic/generated portraits, and an adapter that has
    drifted toward its own generated look would then score as a success. Callers
    that know which files are camera ground truth pass them explicitly."""
    if isinstance(reference, (list, tuple, set)):
        return sorted(str(r) for r in reference if os.path.isfile(str(r)))
    if os.path.isdir(reference):
        out: list[str] = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            out.extend(glob.glob(os.path.join(reference, ext)))
        return sorted(out)
    if any(ch in reference for ch in "*?[") and not os.path.exists(reference):
        return sorted(glob.glob(reference))
    return [reference]


# ---------------------------------------------------------------------------
# backend: ArcFace via InsightFace (optional import)
# ---------------------------------------------------------------------------
def _arcface_embeddings(paths: Sequence[str]):
    try:
        import numpy as np
        from insightface.app import FaceAnalysis
    except Exception:
        return None  # backend unavailable

    app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider",
                                                     "CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))

    embs = []
    for p in paths:
        try:
            import cv2
            img = cv2.imread(p)
            if img is None:
                embs.append(None)
                continue
            faces = app.get(img)
            if not faces:
                embs.append(None)  # no face detected (common on anime)
                continue
            faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
                       reverse=True)
            embs.append(np.asarray(faces[0].normed_embedding, dtype="float32").tolist())
        except Exception:
            embs.append(None)
    return embs


# ---------------------------------------------------------------------------
# backend: CLIP image-image (optional import) — crosses the anime domain gap
# ---------------------------------------------------------------------------
def _clip_embeddings(paths: Sequence[str], bbox: Optional[tuple] = None):
    try:
        import torch
        from PIL import Image
        import open_clip
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k")
        model.eval()
    except Exception:
        return None

    embs = []
    with torch.no_grad():
        for i, p in enumerate(paths):
            try:
                img = Image.open(p).convert("RGB")
                # crop the output image to the known face zone if provided (index 0 = output)
                if bbox is not None and i == 0:
                    x, y, w, h = bbox
                    img = img.crop((x, y, x + w, y + h))
                t = preprocess(img).unsqueeze(0)
                f = model.encode_image(t)
                f = f / f.norm(dim=-1, keepdim=True)
                embs.append(f.squeeze(0).tolist())
            except Exception:
                embs.append(None)
    return embs


# ---------------------------------------------------------------------------
# optional: behavioral recolor guard (SSIM of output vs original target)
# ---------------------------------------------------------------------------
def _target_ssim(output_image: str, source_target: str) -> Optional[float]:
    try:
        import cv2
        from skimage.metrics import structural_similarity as ssim
        a = cv2.imread(output_image, cv2.IMREAD_GRAYSCALE)
        b = cv2.imread(source_target, cv2.IMREAD_GRAYSCALE)
        if a is None or b is None:
            return None
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
        return float(ssim(a, b))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def identity_score(output_image: str,
                   reference: str,
                   bbox: Optional[tuple] = None,
                   source_target: Optional[str] = None,
                   backend_priority: Sequence[str] = ("arcface", "clip")) -> dict:
    refs = _expand_refs(reference)
    if not refs:
        return {"identity_score": 0.0, "backend": "none", "face_detected": False,
                "error": f"no reference images found at {reference!r}"}

    paths = [output_image] + refs
    result = {"identity_score": 0.0, "backend": "none", "face_detected": False,
              "target_similarity": None, "method_guess": "unknown"}

    for backend in backend_priority:
        embs = _arcface_embeddings(paths) if backend == "arcface" else \
               _clip_embeddings(paths, bbox) if backend == "clip" else None
        if embs is None:
            continue  # backend not installed
        out_emb, ref_embs = embs[0], [e for e in embs[1:] if e is not None]
        if out_emb is None:
            # face not detected on the output (typical for anime under arcface) -> next backend
            result["face_detected"] = False
            continue
        if not ref_embs:
            continue
        best = max(_cosine(out_emb, r) for r in ref_embs)
        result.update({"identity_score": round(float(best), 4),
                       "backend": backend,
                       "face_detected": True})
        break

    # behavioral recolor guard
    if source_target:
        s = _target_ssim(output_image, source_target)
        result["target_similarity"] = None if s is None else round(s, 4)
        if s is not None and s > 0.92 and result["identity_score"] < 0.20:
            result["method_guess"] = "recolor_only"   # near-identical to target + no identity
        elif result["identity_score"] >= 0.20:
            result["method_guess"] = "ipadapter_like"

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _selftest() -> int:
    # prove the cosine path with hand-made vectors, no models needed
    same = _cosine([1, 2, 3], [2, 4, 6])            # colinear -> 1.0
    orth = _cosine([1, 0, 0], [0, 1, 0])            # orthogonal -> 0.0
    part = _cosine([1, 1, 0], [1, 0, 0])            # 45 deg -> ~0.707
    ok = abs(same - 1.0) < 1e-6 and abs(orth) < 1e-6 and abs(part - 0.7071) < 1e-3
    print(json.dumps({"selftest": "pass" if ok else "FAIL",
                      "colinear": round(same, 4),
                      "orthogonal": round(orth, 4),
                      "forty_five_deg": round(part, 4)}, indent=2))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ByrdHouse identity-similarity gate")
    ap.add_argument("--output", help="generated image to judge")
    ap.add_argument("--reference", help="reference photo, dir, or glob")
    ap.add_argument("--bbox", help="face zone on the output as x,y,w,h (optional)")
    ap.add_argument("--source-target", help="original target image, for the recolor guard")
    ap.add_argument("--selftest", action="store_true", help="verify cosine math, no models")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if not args.output or not args.reference:
        ap.error("--output and --reference are required (or use --selftest)")

    bbox = tuple(int(v) for v in args.bbox.split(",")) if args.bbox else None
    res = identity_score(args.output, args.reference, bbox=bbox,
                         source_target=args.source_target)
    print(json.dumps(res, indent=2))
    # exit 2 signals "no backend installed" so callers can distinguish from a low score
    return 2 if res["backend"] == "none" else 0


if __name__ == "__main__":
    raise SystemExit(main())
