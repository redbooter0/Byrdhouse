"""
probe-identity-lora.py — the test that has never been run.

ByrdHouse has trained ~8 Carey SD1.5 LoRAs. Every recipe that consumes one is a
TARGET EDIT (anime_face_edit, anime_face_zone_edit v1/v2/v3): a target image is
supplied, a semantic mask is cut, and the identity is warped through the
target's 478-point mesh. In that configuration the output's facial geometry is
the TARGET's before the LoRA contributes anything, so the adapter can never show
whether it learned Carey's face. Two weeks of tuning measured nothing.

This submits the one configuration that CAN answer it: plain text-to-image, no
target, no mask, no img2img — the LoRA drawing a face from scratch — across every
installed Carey LoRA and a strength sweep, at ONE fixed seed so the only variable
is the adapter.

    python scripts/probe-identity-lora.py                  # all carey LoRAs, 3 strengths
    python scripts/probe-identity-lora.py --lora carey_meina_sd15_v1
    python scripts/probe-identity-lora.py --strengths 0.6,0.8,1.0 --seed 42
    python scripts/probe-identity-lora.py --checkpoint meina --dry-run

Jobs go through the router like any other work, so every result gets a card, a
judge score and the identity gate. Then LOOK at the grid: if no cell reads as
Carey, the problem is the dataset/training and no pipeline change will fix it.
If a cell does, that LoRA + strength is the working likeness lane today.

Stdlib only.
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

DEFAULT_STRENGTHS = (0.7, 0.9, 1.1)
RECIPE = "carey_identity_probe@1"


def load_cfg(root: Path) -> dict:
    return json.loads((root / "byrdhouse.config.json").read_text(encoding="utf-8-sig"))


def post_job(cfg: dict, payload: dict) -> dict:
    router = cfg["services"]["router"].rstrip("/")
    req = urllib.request.Request(
        f"{router}/jobs", data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cfg['auth']['admin_token']}",
                 "X-Actor": "probe-identity-lora"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def find_carey_loras(root: Path) -> list:
    d = root / "Generators" / "ComfyUI" / "models" / "loras"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.safetensors") if "carey" in p.stem.lower())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lora", action="append", default=[],
                    help="LoRA to probe (repeatable). Default: every carey* LoRA installed.")
    ap.add_argument("--strengths", default=",".join(str(s) for s in DEFAULT_STRENGTHS),
                    help="comma-separated LoRA strengths (default 0.7,0.9,1.1)")
    ap.add_argument("--seed", type=int, default=42,
                    help="ONE fixed seed for every cell so the LoRA is the only variable")
    ap.add_argument("--batch", type=int, default=2, help="images per cell (default 2)")
    ap.add_argument("--checkpoint", default=None,
                    help="override the SD1.5 checkpoint (default: the recipe's)")
    ap.add_argument("--project", default="identity_probe")
    ap.add_argument("--dry-run", action="store_true", help="print the grid, submit nothing")
    args = ap.parse_args()

    root = Path(os.environ.get("BYRDHOUSE_ROOT") or Path(__file__).resolve().parents[1])
    cfg = load_cfg(root)

    loras = args.lora or find_carey_loras(root)
    if not loras:
        sys.exit(
            "No Carey LoRA found in Generators/ComfyUI/models/loras.\n"
            "Run this on BYRD-GAMING (where the models live), or pass --lora NAME.")
    strengths = [float(s) for s in args.strengths.split(",") if s.strip()]

    cells = [(lora, s) for lora in loras for s in strengths]
    print(f"Identity probe: {len(loras)} LoRA(s) x {len(strengths)} strength(s) "
          f"= {len(cells)} jobs, {args.batch} image(s) each, seed {args.seed} (fixed)")
    print("Plain text-to-image — no target, no mask. The LoRA draws the face itself.\n")
    for lora in loras:
        print(f"  {lora}")
    print()

    if args.dry_run:
        for lora, s in cells:
            print(f"  [dry-run] {lora} @ {s}")
        return

    submitted = []
    for lora, s in cells:
        payload = {
            "recipe": RECIPE,
            "slots": {},
            "project": args.project,
            "purpose": f"IDENTITY PROBE — {lora} @ strength {s} (t2i, no target)",
            "lora": lora,
            "lora_strength": s,
            "seed": args.seed,
            "batch": args.batch,
        }
        if args.checkpoint:
            payload["checkpoint"] = args.checkpoint
        job = post_job(cfg, {
            "type": "image.generate", "project": args.project,
            "required_mode": "IMAGE", "required_caps": ["comfyui"],
            "payload": payload})
        submitted.append((lora, s, job.get("id")))
        print(f"  queued {job.get('id')}  {lora} @ {s}")

    print(f"\n{len(submitted)} job(s) queued. Watch the dashboard Library "
          f"(project '{args.project}').")
    print("\nHOW TO READ THE RESULT — this is a fork, not a score:")
    print("  * At least one cell reads as Carey  -> that LoRA+strength IS your")
    print("    likeness lane today. Use it for text-to-image now; the zone lane was")
    print("    the problem, not the adapter.")
    print("  * NO cell reads as Carey            -> the adapter never learned the")
    print("    face. Stop tuning pipelines: retrain on the real-photo-dominant")
    print("    dataset (docs/IMAGE_VIDEO_STATE.md §6). No graph change can add an")
    print("    identity the weights do not contain.")
    print("  * Faces melt/duplicate at every cell -> wrong resolution or checkpoint")
    print("    family, not identity. Confirm the checkpoint is SD1.5 and 512px.")


if __name__ == "__main__":
    main()
