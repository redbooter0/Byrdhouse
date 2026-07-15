"""Run the fixed local portrait gate for one private Carey LoRA candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import byrdimage


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--recipe",
        default="carey_identity_gate",
        help="Fixed portrait-gate recipe ID (default: carey_identity_gate).",
    )
    parser.add_argument("--strength", type=float, default=1.0)
    parser.add_argument(
        "--clip-strength",
        type=float,
        help="Optional separate CLIP/text-encoder LoRA strength; defaults to --strength.",
    )
    parser.add_argument("--seed", type=int, default=7119)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_label(value: str) -> str:
    return "".join(char if char.isalnum() or char in "_-" else "_" for char in value).strip("_")


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    candidate = args.candidate.resolve()
    label = safe_label(args.label)
    if not label:
        raise SystemExit("--label must contain at least one safe character")
    if candidate.suffix.lower() != ".safetensors" or not candidate.is_file():
        raise SystemExit(f"Candidate must be an existing .safetensors file: {candidate}")
    if not 0.1 <= args.strength <= 1.5:
        raise SystemExit("--strength must be between 0.1 and 1.5")
    if args.clip_strength is not None and not 0.1 <= args.clip_strength <= 2.0:
        raise SystemExit("--clip-strength must be between 0.1 and 2.0")

    preview_dir = root / "Generators" / "ComfyUI" / "models" / "loras"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview = preview_dir / f"{candidate.stem}_{label}_preview.safetensors"
    if not preview.exists() or sha256(preview) != sha256(candidate):
        shutil.copy2(candidate, preview)

    _, outputs = byrdimage.generate(
        root,
        args.recipe,
        {},
        project="image_lab",
        purpose=f"private local Carey identity portrait gate: {label}",
        batch=1,
        lora=preview.name,
        lora_strength=args.strength,
        lora_clip_strength=args.clip_strength,
        seed=args.seed,
        width=512,
        height=512,
        engine={
            "steps": 24,
            "cfg": 6.0,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
        },
        job_id=f"carey_identity_gate_{label}",
    )

    output_dir = root / "artifacts" / "image_lab" / f"{datetime.now():%Y-%m}"
    report = output_dir / f"portrait_gate_{label}_{datetime.now():%Y%m%d_%H%M%S}.json"
    report.write_text(
        json.dumps(
            {
                "label": label,
                "recipe": args.recipe,
                "candidate": str(candidate),
                "candidate_sha256": sha256(candidate),
                "preview_lora": str(preview),
                "strength": args.strength,
                "clip_strength": args.clip_strength if args.clip_strength is not None else args.strength,
                "seed": args.seed,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "outputs": [str(path) for path, _ in outputs],
                "verdict": "pending visual review; private preview only",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Portrait gate report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
