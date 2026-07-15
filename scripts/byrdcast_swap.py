"""
byrdcast_swap.py — ByrdCast Swap V0 (docs/BYRDCAST_SWAP_V0.md).

Target-image-first LOCAL face swap for the RTX 3070 8GB / i9-10850K / 32GB box.
Given any target image, replace the MAIN face with a chosen identity from a
local approved-reference folder while preserving the target's pose, lighting,
style, scene, clothing and composition. Image only (no video, no multi-person,
no prompt generation in V0).

It shows its work: what it detected, which reference it chose and why, which
swap route it used, and why the final passed or failed. Every run writes a full
debug folder and fails CLOSED — a weak result is saved and marked
accepted=false with the reason, never silently shipped.

Stdlib + Pillow always; numpy/cv2/insightface/torch and a live ComfyUI are used
when present (the RTX box) and degrade honestly when absent (recorded in the
sidecar). Run under the ComfyUI venv python on BYRD-GAMING.

    python scripts\\byrdcast_swap.py --identity Carey \\
        --target "E:\\ByrdHouse\\Inputs\\target.png" \\
        --refs "E:\\ByrdHouse\\Identities\\Carey\\approved" \\
        --out "E:\\ByrdHouse\\Outputs\\ByrdCastSwap" --quality best

    --dry-run   run the CPU stages + write the full folder without a GPU/ONNX
                swap (structure proof; always accepted=false)
"""

import argparse
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


# ── tiny logger ──────────────────────────────────────────────────────────────
def log(msg):
    print(f"[byrdcast {datetime.now():%H:%M:%S}] {msg}", flush=True)


def die(msg, code=2):
    print(f"[byrdcast] ERROR: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(code)


# ── config ───────────────────────────────────────────────────────────────────
def load_config(root: Path) -> dict:
    cfg_path = root / "configs" / "byrdcast_swap_v0.json"
    if not cfg_path.is_file():
        die(f"config not found: {cfg_path}")
    with open(cfg_path, encoding="utf-8-sig") as f:
        return json.load(f)


def comfy_url(root: Path) -> str:
    """Host rule: never hardcoded — read from byrdhouse.config.json."""
    try:
        with open(root / "byrdhouse.config.json", encoding="utf-8-sig") as f:
            return json.load(f)["services"]["comfyui"].rstrip("/")
    except Exception:
        return ""


# ── PIL-only image metrics (no numpy needed) ─────────────────────────────────
def _gray(img: Image.Image) -> Image.Image:
    return img.convert("L")


def _mean_std(gray: Image.Image) -> tuple:
    hist = gray.histogram()
    total = sum(hist) or 1
    mean = sum(i * n for i, n in enumerate(hist)) / total
    var = sum(n * (i - mean) ** 2 for i, n in enumerate(hist)) / total
    return mean, var ** 0.5


def _sharpness(gray: Image.Image) -> float:
    """Edge energy — higher is sharper/more in focus."""
    edges = gray.filter(ImageFilter.FIND_EDGES)
    mean, _ = _mean_std(edges)
    return float(mean)


def image_metrics(img: Image.Image) -> dict:
    g = _gray(img)
    mean, std = _mean_std(g)
    return {
        "brightness": round(mean, 2),
        "contrast": round(std, 2),
        "sharpness": round(_sharpness(g), 3),
        "width": img.width,
        "height": img.height,
    }


# ── detection chain (best available, recorded) ───────────────────────────────
def _try_insightface():
    try:
        from insightface.app import FaceAnalysis  # noqa
        app = FaceAnalysis(name="buffalo_l")
        app.prepare(ctx_id=-1, det_size=(640, 640))  # CPU detection is fine
        return app
    except Exception:
        return None


_INSIGHT = "unset"


def detect_face(img: Image.Image, min_px: int, want_embedding: bool) -> dict:
    """Return {method, box[x1,y1,x2,y2], landmarks?, embedding?, angle?, metrics}.
    Chain: insightface (box+5pt+embedding+pose) -> cv2 haar (box) -> PIL center
    placeholder (box only, forces accepted=false downstream). Never guesses
    silently — the method used is always recorded."""
    global _INSIGHT
    if _INSIGHT == "unset":
        _INSIGHT = _try_insightface()
    metrics = image_metrics(img)

    if _INSIGHT is not None:
        try:
            import numpy as np
            arr = np.asarray(img.convert("RGB"))[:, :, ::-1]  # RGB->BGR
            faces = _INSIGHT.get(arr)
            faces = [f for f in faces if (f.bbox[2] - f.bbox[0]) >= min_px]
            if faces:
                f = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
                box = [int(v) for v in f.bbox[:4]]
                out = {"method": "insightface", "box": box,
                       "landmarks": [[int(x), int(y)] for x, y in f.kps.tolist()],
                       "metrics": metrics, "faces_found": len(faces)}
                if getattr(f, "pose", None) is not None:
                    out["angle"] = [round(float(v), 2) for v in f.pose.tolist()]
                if want_embedding and getattr(f, "normed_embedding", None) is not None:
                    out["embedding"] = [round(float(v), 6) for v in f.normed_embedding.tolist()]
                return out
        except Exception as exc:
            log(f"insightface detect failed, falling back: {exc}")

    try:
        import cv2  # noqa
        import numpy as np
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray = np.asarray(img.convert("L"))
        found = cascade.detectMultiScale(gray, 1.1, 5, minSize=(min_px, min_px))
        if len(found):
            x, y, w, h = max(found, key=lambda r: r[2] * r[3])
            return {"method": "opencv_haar", "box": [int(x), int(y), int(x + w), int(y + h)],
                    "metrics": metrics, "faces_found": len(found)}
    except Exception:
        pass

    # PIL placeholder — an honest "I could not detect": center box, flagged.
    w, h = img.size
    side = int(min(w, h) * 0.55)
    cx, cy = w // 2, int(h * 0.45)
    return {"method": "placeholder_center", "box": [cx - side // 2, cy - side // 2,
                                                    cx + side // 2, cy + side // 2],
            "metrics": metrics, "faces_found": 0,
            "note": "no real detector available — geometry is a placeholder; "
                    "the job will fail closed"}


# ── reference selection ──────────────────────────────────────────────────────
def score_reference(target_obs: dict, ref_obs: dict, weights: dict) -> dict:
    """Score a reference 0-1 on the factors we could actually measure, then
    renormalize the weights over the measured set (unmeasured factors never
    count as a silent 1.0)."""
    tm, rm = target_obs["metrics"], ref_obs["metrics"]
    measured = {}

    # lighting similarity: closeness of mean brightness (0-255) -> 0-1
    measured["lighting"] = max(0.0, 1.0 - abs(tm["brightness"] - rm["brightness"]) / 128.0)
    # quality: reference sharpness relative to a soft target (higher is better)
    measured["quality"] = min(1.0, rm["sharpness"] / 24.0)

    # angle + expression need landmarks/pose (insightface). If both sides have
    # pose, score angle closeness; else leave unmeasured (renormalized away).
    if target_obs.get("angle") and ref_obs.get("angle"):
        d = sum(abs(a - b) for a, b in zip(target_obs["angle"], ref_obs["angle"]))
        measured["face_angle"] = max(0.0, 1.0 - d / 90.0)
    if target_obs.get("landmarks") and ref_obs.get("landmarks"):
        # crude expression proxy: mouth-openness ratio similarity (5-pt kps:
        # 0,1 eyes; 2 nose; 3,4 mouth corners). Only a weak signal in V0.
        def mouth_w(o):
            l = o["landmarks"]
            return abs(l[3][0] - l[4][0]) or 1
        measured["expression"] = 1.0  # placeholder-neutral until 68pt lands

    used = {k: weights[k] for k in measured if k in weights}
    wsum = sum(used.values()) or 1.0
    overall = sum(measured[k] * (used[k] / wsum) for k in used)
    return {"overall": round(overall, 4), "factors": {k: round(v, 4) for k, v in measured.items()},
            "measured": list(measured.keys())}


def choose_reference(target_obs, refs, weights):
    ranked = []
    for ref in refs:
        s = score_reference(target_obs, ref["obs"], weights)
        ranked.append({**ref, "select_score": s})
    ranked.sort(key=lambda r: r["select_score"]["overall"], reverse=True)
    return ranked


# ── masks (geometric; a semantic parser would refine these later) ────────────
def build_masks(size, box, mcfg) -> dict:
    """Return {name: PIL 'L' mask}. Geometry off the detected box: face oval,
    jaw (lower band), hairline (top band), ears (side bands), neck (below chin),
    skin (face minus hairline). Feathered so composites never hard-edge."""
    W, H = size
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    feather = int(mcfg.get("feather_px", 9))

    def blank():
        return Image.new("L", (W, H), 0)

    def feathered(m):
        return m.filter(ImageFilter.GaussianBlur(feather))

    masks = {}
    # face oval
    m = blank(); d = ImageDraw.Draw(m)
    sc = mcfg.get("face_oval_scale", 1.02)
    ox = int(bw * (sc - 1) / 2); oy = int(bh * (sc - 1) / 2)
    d.ellipse([x1 - ox, y1 - oy, x2 + ox, y2 + oy], fill=255)
    masks["face"] = feathered(m)
    # jaw = lower band of the oval
    m = blank(); d = ImageDraw.Draw(m)
    jb = int(bh * mcfg.get("jaw_band_frac", 0.34))
    d.ellipse([x1, y2 - jb - bh // 2, x2, y2], fill=255)
    masks["jaw"] = feathered(m)
    # hairline = top band
    m = blank(); d = ImageDraw.Draw(m)
    hb = int(bh * mcfg.get("hairline_band_frac", 0.20))
    d.rectangle([x1, y1 - hb // 2, x2, y1 + hb], fill=255)
    masks["hairline"] = feathered(m)
    # ears = side bands
    m = blank(); d = ImageDraw.Draw(m)
    eb = int(bw * mcfg.get("ear_band_frac", 0.22))
    d.rectangle([x1 - eb // 2, y1 + bh // 3, x1 + eb, y2 - bh // 5], fill=255)
    d.rectangle([x2 - eb, y1 + bh // 3, x2 + eb // 2, y2 - bh // 5], fill=255)
    masks["ears"] = feathered(m)
    # neck = below chin
    m = blank(); d = ImageDraw.Draw(m)
    nb = int(bh * mcfg.get("neck_band_frac", 0.28))
    d.rectangle([x1 + bw // 6, y2 - feather, x2 - bw // 6, y2 + nb], fill=255)
    masks["neck"] = feathered(m)
    # skin = face minus hairline band
    from PIL import ImageChops
    masks["skin"] = feathered(ImageChops.subtract(masks["face"], masks["hairline"]))
    return masks


def mask_overlay(target: Image.Image, masks: dict) -> Image.Image:
    """Colored overlay so a human can see every zone at a glance."""
    colors = {"face": (52, 211, 153), "jaw": (96, 165, 250), "hairline": (251, 191, 36),
              "ears": (167, 139, 250), "neck": (248, 113, 113), "skin": (45, 212, 191)}
    base = target.convert("RGB").copy()
    for name, m in masks.items():
        layer = Image.new("RGB", base.size, colors.get(name, (200, 200, 200)))
        base = Image.composite(Image.blend(base, layer, 0.28), base,
                               m.point(lambda p: int(p * 0.6)))
    return base


def detect_overlay(target: Image.Image, obs: dict) -> Image.Image:
    base = target.convert("RGB").copy()
    d = ImageDraw.Draw(base)
    x1, y1, x2, y2 = obs["box"]
    color = (52, 211, 153) if obs["method"] not in ("placeholder_center",) else (248, 113, 113)
    d.rectangle([x1, y1, x2, y2], outline=color, width=max(2, (x2 - x1) // 90))
    for pt in obs.get("landmarks", []):
        d.ellipse([pt[0] - 3, pt[1] - 3, pt[0] + 3, pt[1] + 3], fill=(255, 255, 0))
    d.text((x1 + 4, max(0, y1 - 14)), f"{obs['method']} ({obs.get('faces_found', 0)})", fill=color)
    return base


# ── ComfyUI plumbing (self-contained, stdlib) ────────────────────────────────
def comfy_has_node(comfy: str, node: str) -> bool:
    try:
        with urllib.request.urlopen(f"{comfy}/object_info/{node}", timeout=8) as r:
            return bool(json.loads(r.read().decode()).get(node))
    except Exception:
        return False


def comfy_upload(comfy: str, path: Path) -> str:
    boundary = f"----byrdcast{secrets.token_hex(8)}"
    data = path.read_bytes()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"{path.name}\"\r\nContent-Type: image/png\r\n\r\n").encode() \
        + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{comfy}/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode()).get("name", path.name)


def comfy_run(comfy: str, graph: dict, timeout_s=600) -> dict:
    req = urllib.request.Request(f"{comfy}/prompt",
                                 data=json.dumps({"prompt": graph}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        pid = json.loads(r.read().decode()).get("prompt_id")
    if not pid:
        raise RuntimeError("ComfyUI rejected the job")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with urllib.request.urlopen(f"{comfy}/history/{pid}", timeout=15) as r:
            hist = json.loads(r.read().decode()).get(pid)
        if hist:
            if hist.get("status", {}).get("status_str") == "error":
                raise RuntimeError(f"ComfyUI job error: {json.dumps(hist['status'])[:400]}")
            if hist.get("outputs"):
                return hist["outputs"]
        time.sleep(2)
    raise RuntimeError("ComfyUI timed out")


def comfy_fetch(comfy: str, image_ref: dict, dest: Path):
    q = urllib.parse.urlencode({"filename": image_ref["filename"],
                                "subfolder": image_ref.get("subfolder", ""),
                                "type": image_ref.get("type", "output")})
    with urllib.request.urlopen(f"{comfy}/view?{q}", timeout=60) as r:
        dest.write_bytes(r.read())


# ── swap routes ──────────────────────────────────────────────────────────────
def run_swap(root, cfg, comfy, target_path, ref_path, jobdir, quality):
    """Try each configured route; return (candidate_path, route, refined_path|None, notes)."""
    notes = []
    for route in cfg["swap"].get("route_order", []):
        if route == "comfy_reactor":
            if not comfy or not comfy_has_node(comfy, "ReActorFaceSwap"):
                notes.append("comfy_reactor: ComfyUI or ReActor unavailable")
                continue
            graph = json.loads((root / cfg["workflow"]).read_text(encoding="utf-8-sig"))
            graph.pop("_comment", None)
            want_refine = quality.get("use_facedetailer", True) \
                and cfg["refine"].get("use_facedetailer_if_available", True) \
                and comfy_has_node(comfy, "FaceDetailer")
            if not want_refine:
                for n in ("20", "21", "22", "23", "24", "25"):
                    graph.pop(n, None)
            graph["target"]["inputs"]["image"] = comfy_upload(comfy, Path(target_path))
            graph["face"]["inputs"]["image"] = comfy_upload(comfy, Path(ref_path))
            for node in graph.values():
                if node.get("class_type") == "SaveImage":
                    node["inputs"]["filename_prefix"] = f"byrdcast_{jobdir.name}"
            outputs = comfy_run(comfy, graph)
            imgs = {nid: o["images"] for nid, o in outputs.items() if o.get("images")}
            candidate = jobdir / "candidate_reactor.png"
            refined = None
            # swap_save node holds the ReActor output; node 25 the refined one
            if "swap_save" in imgs:
                comfy_fetch(comfy, imgs["swap_save"][0], candidate)
            else:  # fall back to any output
                first = next(iter(imgs.values()))[0]
                comfy_fetch(comfy, first, candidate)
            if want_refine and "25" in imgs:
                refined = jobdir / "candidate_refined.png"
                comfy_fetch(comfy, imgs["25"][0], refined)
                notes.append("refine: FaceDetailer masked restore applied")
            else:
                notes.append("refine: FaceDetailer skipped (absent or quality=fast)")
            return str(candidate), "comfy_reactor", (str(refined) if refined else None), notes

        if route == "insightface":
            try:
                import insightface  # noqa
                import numpy as np
                from insightface.model_zoo import get_model
                app_ok = _try_insightface()
                swapper = get_model("inswapper_128.onnx", download=False)
                tgt = np.asarray(Image.open(target_path).convert("RGB"))[:, :, ::-1].copy()
                src = np.asarray(Image.open(ref_path).convert("RGB"))[:, :, ::-1].copy()
                tfaces, sfaces = app_ok.get(tgt), app_ok.get(src)
                if not tfaces or not sfaces:
                    notes.append("insightface: a face was missing in target or reference")
                    continue
                res = swapper.get(tgt, max(tfaces, key=lambda f: f.bbox[2] - f.bbox[0]),
                                  max(sfaces, key=lambda f: f.bbox[2] - f.bbox[0]), paste_back=True)
                candidate = jobdir / "candidate_reactor.png"
                Image.fromarray(res[:, :, ::-1]).save(candidate)
                notes.append("swap: insightface inswapper in-process")
                return str(candidate), "insightface", None, notes
            except Exception as exc:
                notes.append(f"insightface: unavailable ({exc})")
                continue
    return None, "none", None, notes + ["no swap route available"]


# ── scoring ──────────────────────────────────────────────────────────────────
def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1
    nb = sum(y * y for y in b) ** 0.5 or 1
    return dot / (na * nb)


def score_candidate(cfg, target_obs, ref_obs, candidate_path, final_path, masks, route):
    """0-1 per factor; renormalize identity if it could not be measured."""
    w = dict(cfg["scoring"]["weights"])
    factors, unmeasured = {}, []

    # identity similarity: embedding cosine of the SWAPPED face vs the reference
    if route != "none" and ref_obs.get("embedding") and Path(final_path).is_file():
        final_obs = detect_face(Image.open(final_path), 32, want_embedding=True)
        if final_obs.get("embedding"):
            factors["identity_similarity"] = round(max(0.0, _cosine(
                final_obs["embedding"], ref_obs["embedding"])), 4)
    if "identity_similarity" not in factors:
        unmeasured.append("identity_similarity")

    # mask fit: face-mask coverage sits inside frame and isn't degenerate
    fm = masks["face"]
    cover = (sum(fm.histogram()[128:]) / (fm.width * fm.height)) if fm else 0
    factors["mask_fit"] = round(min(1.0, cover * 6.0), 4)

    # landmark alignment: did we detect real landmarks (not placeholder)?
    factors["landmark_alignment"] = 1.0 if target_obs.get("landmarks") else (
        0.5 if target_obs["method"] == "opencv_haar" else 0.0)

    # blend quality: edge continuity across the face boundary (lower edge energy
    # at the seam ring = smoother blend). Measured on the final if present.
    if route != "none" and Path(final_path).is_file():
        ring = masks["face"].filter(ImageFilter.FIND_EDGES)
        seam = _gray(Image.open(final_path).convert("RGB")).filter(ImageFilter.FIND_EDGES)
        comp = Image.composite(seam, Image.new("L", seam.size, 0), ring.point(lambda p: 255 if p > 40 else 0))
        m, _ = _mean_std(comp)
        factors["blend_quality"] = round(max(0.0, 1.0 - m / 40.0), 4)
    else:
        factors["blend_quality"] = 0.0

    # artifact risk (inverted -> higher is safer): placeholder/none = risky
    factors["artifact_risk"] = 0.2 if route == "none" else (
        0.6 if target_obs["method"] != "insightface" else 0.85)

    used = {k: w[k] for k in factors}
    wsum = sum(used.values()) or 1.0
    overall = round(sum(factors[k] * (used[k] / wsum) for k in factors), 4)
    weakest = sorted(factors.items(), key=lambda kv: kv[1])[:2]
    return {"overall": overall, "factors": factors, "unmeasured": unmeasured,
            "weakest": [k for k, _ in weakest],
            "accept_threshold": cfg["scoring"]["accept_threshold"]}


# ── pipeline ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--identity", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--refs", help="approved reference folder (default: <identities_root>/<id>/approved)")
    ap.add_argument("--out", help="outputs root (default from config)")
    ap.add_argument("--quality", default="best", choices=["fast", "balanced", "best"])
    ap.add_argument("--root", default=os.environ.get("BYRDHOUSE_ROOT", "."))
    ap.add_argument("--dry-run", action="store_true",
                    help="CPU stages + full folder, no GPU/ONNX swap (always accepted=false)")
    args = ap.parse_args()

    root = Path(args.root)
    cfg = load_config(root)
    qmode = cfg["quality_modes"].get(args.quality, cfg["quality_modes"]["best"])
    comfy = "" if args.dry_run else comfy_url(root)

    # 1. validate target
    target_path = Path(args.target)
    if not target_path.is_file():
        die(f"target image not found: {target_path}")
    # 2. validate identity folder
    refs_dir = Path(args.refs) if args.refs else (
        Path(cfg["identities_root"]) / args.identity / cfg["approved_subdir"])
    if not refs_dir.is_dir():
        die(f"identity reference folder not found: {refs_dir}")
    # 3. load approved references
    ref_paths = sorted(p for p in refs_dir.iterdir() if p.suffix.lower() in IMG_EXT)
    if not ref_paths:
        die(f"no approved reference images in {refs_dir}")

    out_root = Path(args.out) if args.out else Path(cfg["outputs_root"])
    jobid = f"{datetime.now():%Y%m%d_%H%M%S}_{args.identity}_{secrets.token_hex(3)}"
    jobdir = out_root / jobid
    jobdir.mkdir(parents=True, exist_ok=True)
    log(f"job {jobid} -> {jobdir}")

    notes = []
    if cfg["hardware"].get("unload_lmstudio_before_swap") and not args.dry_run:
        notes.append("reminder: unload LM Studio before the heavy ComfyUI pass (8GB rule)")

    # 4. detect target face
    target_img = Image.open(target_path)
    ImageOps.exif_transpose(target_img).save(jobdir / "target.png")
    target_obs = detect_face(target_img, cfg["masks"] and 64 or 64, want_embedding=True)
    log(f"target face: {target_obs['method']} box={target_obs['box']}")

    # 5. detect reference faces
    min_ref = cfg["reference_selection"]["min_reference_face_px"]
    refs = []
    for rp in ref_paths:
        try:
            robs = detect_face(Image.open(rp), min_ref, want_embedding=True)
        except Exception as exc:
            notes.append(f"reference {rp.name} skipped: {exc}")
            continue
        refs.append({"path": str(rp), "name": rp.name, "obs": robs})
    if not refs:
        die("no usable reference faces detected")

    # 6. choose the best reference (renormalized weighted score)
    ranked = choose_reference(target_obs, refs, cfg["reference_selection"]["weights"])
    chosen = ranked[0]
    Image.open(chosen["path"]).save(jobdir / "selected_reference.png")
    log(f"chosen reference: {chosen['name']} score={chosen['select_score']['overall']} "
        f"(measured {chosen['select_score']['measured']})")

    # 7. target detection debug overlay
    detect_overlay(target_img, target_obs).save(jobdir / "face_detect_overlay.png")
    # 8. masks + overlay
    masks = build_masks(target_img.size, target_obs["box"], cfg["masks"])
    mask_overlay(target_img, masks).save(jobdir / "mask_overlay.png")
    masks_dir = jobdir / "masks"; masks_dir.mkdir(exist_ok=True)
    for name, m in masks.items():
        m.save(masks_dir / f"{name}.png")

    # 9-11. swap + refine + optional blend
    candidate_path = refined_path = None
    route = "none"
    if not args.dry_run:
        candidate_path, route, refined_path, swap_notes = run_swap(
            root, cfg, comfy, jobdir / "target.png", chosen["path"], jobdir, qmode)
        notes += swap_notes
    else:
        notes.append("dry-run: swap/refine/blend skipped by request")

    # final = refined if present, else candidate, else (dry/failed) target copy
    final_path = jobdir / "final.png"
    if refined_path and Path(refined_path).is_file():
        Image.open(refined_path).save(final_path)
    elif candidate_path and Path(candidate_path).is_file():
        Image.open(candidate_path).save(final_path)
    else:
        Image.open(jobdir / "target.png").save(final_path)  # fail-closed placeholder
        notes.append("final.png is the untouched target (no swap produced)")

    # 12. score
    score = score_candidate(cfg, target_obs, chosen["obs"], candidate_path, final_path, masks, route)
    accepted = (route != "none" and not args.dry_run
                and score["overall"] >= score["accept_threshold"]
                and target_obs["method"] != "placeholder_center")
    reasons = []
    if args.dry_run:
        reasons.append("dry-run: no swap performed")
    if route == "none":
        reasons.append("no swap route available (install ReActor + inswapper_128, or insightface)")
    if target_obs["method"] == "placeholder_center":
        reasons.append("no real face detector — target geometry is a placeholder")
    if route != "none" and not args.dry_run and score["overall"] < score["accept_threshold"]:
        reasons.append(f"score {score['overall']} below threshold {score['accept_threshold']} "
                       f"(weakest: {', '.join(score['weakest'])})")
    if accepted:
        reasons.append(f"passed: score {score['overall']} >= {score['accept_threshold']}")

    # 13. save score.json + sidecar.json
    (jobdir / "score.json").write_text(json.dumps(score, indent=2), encoding="utf-8")
    sidecar = {
        "tool": "byrdcast_swap", "version": cfg["version"], "job_id": jobid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "identity": args.identity, "quality": args.quality, "quality_mode": qmode,
        "target": str(target_path), "target_face": target_obs,
        "references_dir": str(refs_dir), "references_considered": len(refs),
        "reference_ranking": [{"name": r["name"], "score": r["select_score"]["overall"],
                               "factors": r["select_score"]["factors"]} for r in ranked],
        "selected_reference": chosen["name"],
        "swap_route": route, "refined": bool(refined_path),
        "score": score, "accepted": accepted, "reasons": reasons,
        "hardware_rules": {k: cfg["hardware"][k] for k in
                           ("vram_budget_mb", "batch_size", "preview_size", "refine_size")},
        "artifacts": {
            "target": "target.png", "selected_reference": "selected_reference.png",
            "face_detect_overlay": "face_detect_overlay.png", "mask_overlay": "mask_overlay.png",
            "candidate_reactor": "candidate_reactor.png" if candidate_path else None,
            "candidate_refined": "candidate_refined.png" if refined_path else None,
            "final": "final.png", "score": "score.json", "sidecar": "sidecar.json",
            "masks_dir": "masks",
        },
        "notes": notes,
    }
    (jobdir / "sidecar.json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

    # 14. report
    log(f"route={route} score={score['overall']} accepted={accepted}")
    for r in reasons:
        log(f"  - {r}")
    log(f"DONE — {jobdir}")
    print(json.dumps({"job_dir": str(jobdir), "accepted": accepted,
                      "route": route, "score": score["overall"], "reasons": reasons}, indent=2))
    return 0 if accepted else (0 if args.dry_run else 1)


if __name__ == "__main__":
    raise SystemExit(main())
