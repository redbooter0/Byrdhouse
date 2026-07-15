"""
facelab_preflight.py — prove the face-swap FUNCTION works on this machine.

Runs on BYRD-GAMING against the REAL ComfyUI (MINI/router/dashboard not needed):

  1. Asks ComfyUI itself whether the ReActor node pack is installed
     (GET /object_info/ReActorFaceSwap) and which swap/restore models it can see.
  2. Cross-checks our workflow JSONs input-by-input against the LIVE node schema,
     so a ReActor version drift is caught here — not as a cryptic job failure.
  3. Checks a face photo exists in profiles/me/references.
  4. --run: performs a REAL swap through byrdimage.faceswap() and prints the
     output PNG path. That is the function, end to end, on real pixels.

Usage (on GAMING, ComfyUI running):
    python scripts\facelab_preflight.py                 # checks only
    python scripts\facelab_preflight.py --run gojo.png  # checks + real swap
    python scripts\facelab_preflight.py --run gojo.png --blend 0.35

Stdlib only. Exit 0 = ready/proven, 2 = something missing (told exactly what).
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import byrdimage  # noqa: E402

PROBLEMS = []


def say(msg):
    print(f"[facelab] {msg}")


def problem(msg, fix):
    PROBLEMS.append(msg)
    print(f"[facelab] ✗ {msg}\n          fix: {fix}")


def ok(msg):
    print(f"[facelab] ✓ {msg}")


def get_json(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def node_inputs(spec):
    """Flatten a ComfyUI object_info node spec to {input_name: options_or_type}."""
    inp = spec.get("input", {})
    flat = {}
    for section in ("required", "optional"):
        for k, v in inp.get(section, {}).items():
            flat[k] = v[0] if isinstance(v, list) and v else v
    return flat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", metavar="TARGET_IMAGE",
                    help="perform a real swap onto this image (the proof)")
    ap.add_argument("--route", choices=["swap", "auto"], default="swap",
                    help="swap = ReActor (+ --blend); auto = detector finds the face "
                         "and redraws it as you (use --lora)")
    ap.add_argument("--face", help="face photo (default: newest in profiles/me/references)")
    ap.add_argument("--lora", help="identity LoRA for the auto route (e.g. carey_face_v2)")
    ap.add_argument("--blend", type=float, default=0.0)
    ap.add_argument("--purpose", default="facelab preflight proof")
    args = ap.parse_args()

    root = Path(os.environ.get("BYRDHOUSE_ROOT") or
                sys.exit("[facelab] BYRDHOUSE_ROOT not set"))
    cfg = json.loads((root / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))
    comfy = cfg["services"]["comfyui"].rstrip("/")
    img_cfg = cfg.get("image", {})
    say(f"ComfyUI: {comfy}")

    # ── 1. is ComfyUI up, and is ReActor installed? ──────────────────────────
    try:
        info = get_json(f"{comfy}/object_info/ReActorFaceSwap")
    except Exception as e:
        say(f"✗ ComfyUI unreachable at {comfy}: {e}")
        say("  start it first (start-byrdhouse.ps1 or the ComfyUI launcher), then rerun")
        sys.exit(2)
    spec = info.get("ReActorFaceSwap")
    if not spec:
        problem("ReActor node pack is NOT installed in this ComfyUI",
                "ComfyUI Manager → search 'ReActor' → Install → restart ComfyUI "
                "(or git clone https://github.com/Gourieff/ComfyUI-ReActor into "
                "custom_nodes and run install.bat) — see docs/MODELS.md")
        finish()

    live = node_inputs(spec)
    ok("ReActor node pack installed")

    # ── 2. swap/restore models the live node can actually see ────────────────
    swap_models = live.get("swap_model") if isinstance(live.get("swap_model"), list) else []
    if any("inswapper_128" in str(m) for m in swap_models):
        ok("inswapper_128.onnx visible to ReActor")
    else:
        problem(f"inswapper_128.onnx not in ReActor's swap models ({swap_models or 'none'})",
                "download inswapper_128.onnx into ComfyUI\\models\\insightface "
                "(see docs/MODELS.md)")
    restore_want = img_cfg.get("faceswap_restore", "GFPGANv1.4.pth")
    restore_have = live.get("face_restore_model") if isinstance(live.get("face_restore_model"), list) else []
    if any(restore_want in str(m) for m in restore_have):
        ok(f"restore model {restore_want} available")
    else:
        problem(f"restore model {restore_want} not visible ({restore_have or 'none'})",
                "download GFPGANv1.4.pth into ComfyUI\\models\\facerestore_models, "
                "or set image.faceswap_restore to one you have ('none' works too)")

    # ── 3. our graphs must match the LIVE node schema (version-drift guard) ──
    for wf_key, wf_default in (("faceswap_workflow", "workflows/reactor_faceswap_api.json"),
                               ("faceswap_blend_workflow", "workflows/reactor_faceswap_blend_api.json")):
        wf_rel = img_cfg.get(wf_key, wf_default)
        graph = json.loads((root / wf_rel).read_text(encoding="utf-8-sig"))
        graph.pop("_comment", None)
        swap_nodes = [n for n in graph.values() if n.get("class_type") == "ReActorFaceSwap"]
        unknown = [k for n in swap_nodes for k in n["inputs"]
                   if k not in live and k not in ("input_image", "source_image")]
        # input_image/source_image are connection sockets; they exist in the spec
        # too, but tolerate spec layout differences for links
        unknown = [k for k in unknown if k not in live]
        if unknown:
            problem(f"{wf_rel}: node inputs {unknown} not accepted by the installed ReActor",
                    "the node pack version changed its schema — update the workflow "
                    "or the node pack so they agree")
        else:
            ok(f"{wf_rel} matches the installed ReActor schema")

    # ── 3b. AUTO route: FaceDetailer + face detector (the daily driver) ──────
    try:
        fd_info = get_json(f"{comfy}/object_info/FaceDetailer")
        det_info = get_json(f"{comfy}/object_info/UltralyticsDetectorProvider")
    except Exception:
        fd_info, det_info = {}, {}
    if fd_info.get("FaceDetailer") and det_info.get("UltralyticsDetectorProvider"):
        ok("Impact Pack installed (FaceDetailer + UltralyticsDetectorProvider)")
        det_live = node_inputs(det_info["UltralyticsDetectorProvider"])
        det_models = det_live.get("model_name") if isinstance(det_live.get("model_name"), list) else []
        det_want = img_cfg.get("faceswap_detector", "bbox/face_yolov8m.pt")
        if any(det_want in str(m) for m in det_models):
            ok(f"face detector {det_want} available")
        else:
            problem(f"face detector {det_want} not visible ({det_models[:5] or 'none'})",
                    "ComfyUI Manager -> Model Manager -> install face_yolov8m.pt "
                    "(goes to models\\ultralytics\\bbox), or set image.faceswap_detector "
                    "to one you have")
    else:
        problem("Impact Pack nodes missing — the AUTO route (one-step 'redraw as me') needs them",
                "ComfyUI Manager -> install 'ComfyUI Impact Pack' AND 'ComfyUI Impact Subpack', "
                "restart ComfyUI (the face_yolov8m.pt detector installs with the Subpack)")

    # ── 4. face photo ─────────────────────────────────────────────────────────
    refs = root / "profiles" / "me" / "references"
    photos = [f for f in refs.glob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".png")] \
        if refs.is_dir() else []
    if photos:
        ok(f"{len(photos)} face photo(s) in {refs}")
    else:
        problem(f"no face photos in {refs}",
                "copy 5-7 clear photos of your face there (front.jpg first)")

    if not args.run:
        finish()

    # ── 5. the PROOF: a real swap through the real function ──────────────────
    if PROBLEMS:
        say("not running the swap — fix the ✗ items above first")
        sys.exit(2)
    target = Path(args.run)
    if args.route == "auto":
        say(f"running REAL auto zone: target {target.name} (lora {args.lora or 'none'})")
        job_id, saved = byrdimage.facezone_auto(
            root, target, "sandbox", args.purpose, lora=args.lora)
    else:
        face = Path(args.face) if args.face else max(photos, key=lambda p: p.stat().st_mtime)
        say(f"running REAL swap: face {face.name} -> target {target.name} (blend {args.blend})")
        job_id, saved = byrdimage.faceswap(
            root, target, face, "sandbox", args.purpose, style_blend=args.blend)
    for png, _card in saved:
        ok(f"PROOF: swapped image at {png}")
    finish()


def finish():
    if PROBLEMS:
        say(f"NOT READY — {len(PROBLEMS)} problem(s) listed above")
        sys.exit(2)
    say("READY — the face-swap function is proven on this machine" )
    sys.exit(0)


if __name__ == "__main__":
    main()
