#!/usr/bin/env python3
"""
verify_identity.py - ByrdHouse identity similarity gate.

This measures whether an output actually carries Carey's identity or merely
resembles the target after recoloring/stylization.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from typing import Optional, Sequence


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return num / (na * nb)


def _expand_refs(reference: str) -> list[str]:
    if os.path.isdir(reference):
        out: list[str] = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            out.extend(glob.glob(os.path.join(reference, ext)))
        return sorted(out)
    if any(ch in reference for ch in "*?[") and not os.path.exists(reference):
        return sorted(glob.glob(reference))
    return [reference]


def _arcface_embeddings(paths: Sequence[str]):
    try:
        import numpy as np
        from insightface.app import FaceAnalysis
    except Exception:
        return None

    app = FaceAnalysis(
        name="buffalo_l",
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    app.prepare(ctx_id=0, det_size=(640, 640))

    embs = []
    for path in paths:
        try:
            import cv2

            img = cv2.imread(path)
            if img is None:
                embs.append(None)
                continue
            faces = app.get(img)
            if not faces:
                embs.append(None)
                continue
            faces.sort(
                key=lambda face: (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1]),
                reverse=True,
            )
            embs.append(np.asarray(faces[0].normed_embedding, dtype="float32").tolist())
        except Exception:
            embs.append(None)
    return embs


def _clip_embeddings(paths: Sequence[str], bbox: Optional[tuple] = None):
    try:
        import torch
        from PIL import Image
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        model.eval()
    except Exception:
        return None

    embs = []
    with torch.no_grad():
        for index, path in enumerate(paths):
            try:
                img = Image.open(path).convert("RGB")
                if bbox is not None and index == 0:
                    x, y, w, h = bbox
                    img = img.crop((x, y, x + w, y + h))
                tensor = preprocess(img).unsqueeze(0)
                feat = model.encode_image(tensor)
                feat = feat / feat.norm(dim=-1, keepdim=True)
                embs.append(feat.squeeze(0).tolist())
            except Exception:
                embs.append(None)
    return embs


def _target_ssim(output_image: str, source_target: str) -> Optional[float]:
    try:
        import cv2
        from skimage.metrics import structural_similarity as ssim

        img_a = cv2.imread(output_image, cv2.IMREAD_GRAYSCALE)
        img_b = cv2.imread(source_target, cv2.IMREAD_GRAYSCALE)
        if img_a is None or img_b is None:
            return None
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))
        return float(ssim(img_a, img_b))
    except Exception:
        return None


def identity_score(
    output_image: str,
    reference: str,
    bbox: Optional[tuple] = None,
    source_target: Optional[str] = None,
    backend_priority: Sequence[str] = ("arcface", "clip"),
) -> dict:
    refs = _expand_refs(reference)
    if not refs:
        return {
            "identity_score": 0.0,
            "backend": "none",
            "face_detected": False,
            "error": f"no reference images found at {reference!r}",
        }

    paths = [output_image] + refs
    result = {
        "identity_score": 0.0,
        "backend": "none",
        "face_detected": False,
        "target_similarity": None,
        "method_guess": "unknown",
    }

    for backend in backend_priority:
        if backend == "arcface":
            embs = _arcface_embeddings(paths)
        elif backend == "clip":
            embs = _clip_embeddings(paths, bbox)
        else:
            embs = None
        if embs is None:
            continue
        out_emb, ref_embs = embs[0], [emb for emb in embs[1:] if emb is not None]
        if out_emb is None:
            result["face_detected"] = False
            continue
        if not ref_embs:
            continue
        best = max(_cosine(out_emb, ref) for ref in ref_embs)
        result.update(
            {
                "identity_score": round(float(best), 4),
                "backend": backend,
                "face_detected": True,
            }
        )
        break

    if source_target:
        similarity = _target_ssim(output_image, source_target)
        result["target_similarity"] = None if similarity is None else round(similarity, 4)
        if similarity is not None and similarity > 0.92 and result["identity_score"] < 0.20:
            result["method_guess"] = "recolor_only"
        elif result["identity_score"] >= 0.20:
            result["method_guess"] = "ipadapter_like"

    return result


def _selftest() -> int:
    same = _cosine([1, 2, 3], [2, 4, 6])
    orth = _cosine([1, 0, 0], [0, 1, 0])
    part = _cosine([1, 1, 0], [1, 0, 0])
    ok = abs(same - 1.0) < 1e-6 and abs(orth) < 1e-6 and abs(part - 0.7071) < 1e-3
    print(
        json.dumps(
            {
                "selftest": "pass" if ok else "FAIL",
                "colinear": round(same, 4),
                "orthogonal": round(orth, 4),
                "forty_five_deg": round(part, 4),
            },
            indent=2,
        )
    )
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ByrdHouse identity similarity gate")
    ap.add_argument("--output", help="generated image to judge")
    ap.add_argument("--reference", help="reference photo, dir, or glob")
    ap.add_argument("--bbox", help="face zone on the output as x,y,w,h")
    ap.add_argument("--source-target", help="original target image, for recolor guard")
    ap.add_argument("--selftest", action="store_true", help="verify cosine math, no models")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if not args.output or not args.reference:
        ap.error("--output and --reference are required (or use --selftest)")

    bbox = tuple(int(v) for v in args.bbox.split(",")) if args.bbox else None
    result = identity_score(
        args.output,
        args.reference,
        bbox=bbox,
        source_target=args.source_target,
    )
    print(json.dumps(result, indent=2))
    return 2 if result["backend"] == "none" else 0


if __name__ == "__main__":
    raise SystemExit(main())
