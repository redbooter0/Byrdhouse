"""Generate a private multi-view Carey anime bootstrap set on local ComfyUI."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import byrdimage


VARIANTS = (
    ("front_neutral", "front view, direct eye contact", "neutral relaxed expression", "natural afro", 7201),
    ("front_smile", "front view, direct eye contact", "warm closed-mouth smile", "natural afro", 7202),
    ("front_teeth", "front view, direct eye contact", "smiling with teeth", "full natural afro", 7203),
    ("left_threequarter", "left three-quarter view", "neutral relaxed expression", "natural afro", 7204),
    ("right_threequarter", "right three-quarter view", "neutral relaxed expression", "natural afro", 7205),
    ("left_profile", "clean left profile view", "neutral expression", "short natural afro", 7206),
    ("right_profile", "clean right profile view", "neutral expression", "short natural afro", 7207),
    ("stern", "front view", "focused stern expression", "natural afro", 7208),
    ("braids_neutral", "front view", "neutral relaxed expression", "short braids", 7209),
    ("braids_threequarter", "right three-quarter view", "subtle smile", "short braids", 7210),
    ("low_angle", "slight low camera angle", "neutral expression", "full natural afro", 7211),
    ("high_angle", "slight high camera angle", "soft closed-mouth smile", "natural afro", 7212),
)


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--label", default="teacher_v1")
    parser.add_argument("--model-strength", type=float, default=0.60)
    parser.add_argument("--clip-strength", type=float, default=1.30)
    parser.add_argument("--max-variants", type=int, default=len(VARIANTS))
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
    if candidate.suffix.lower() != ".safetensors" or not candidate.is_file():
        raise SystemExit(f"Candidate must be an existing .safetensors file: {candidate}")
    if not label:
        raise SystemExit("--label must contain at least one safe character")
    if not 0.1 <= args.model_strength <= 1.5:
        raise SystemExit("--model-strength must be between 0.1 and 1.5")
    if not 0.1 <= args.clip_strength <= 2.0:
        raise SystemExit("--clip-strength must be between 0.1 and 2.0")
    if not 1 <= args.max_variants <= len(VARIANTS):
        raise SystemExit(f"--max-variants must be between 1 and {len(VARIANTS)}")

    preview_dir = root / "Generators" / "ComfyUI" / "models" / "loras"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview = preview_dir / f"{candidate.stem}_{label}_teacher_preview.safetensors"
    if not preview.exists() or sha256(preview) != sha256(candidate):
        shutil.copy2(candidate, preview)

    style = "1990s shonen anime screencap, hand-drawn 2D animation, bold black outlines, flat cel shading"
    results: list[dict[str, object]] = []
    for name, pose, expression, hairstyle, seed in VARIANTS[: args.max_variants]:
        _, outputs = byrdimage.generate(
            root,
            "carey_anime_bootstrap",
            {
                "pose": pose,
                "expression": expression,
                "hairstyle": hairstyle,
                "style": style,
            },
            project="image_lab",
            purpose=f"private local Carey anime identity bootstrap: {label}/{name}",
            batch=1,
            lora=preview.name,
            lora_strength=args.model_strength,
            lora_clip_strength=args.clip_strength,
            seed=seed,
            width=512,
            height=512,
            engine={
                "steps": 28,
                "cfg": 6.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
            },
            job_id=f"carey_bootstrap_{label}_{name}",
        )
        results.append(
            {
                "name": name,
                "pose": pose,
                "expression": expression,
                "hairstyle": hairstyle,
                "seed": seed,
                "outputs": [str(path) for path, _ in outputs],
            }
        )

    output_dir = root / "artifacts" / "image_lab" / f"{datetime.now():%Y-%m}"
    report = output_dir / f"carey_bootstrap_{label}_{datetime.now():%Y%m%d_%H%M%S}.json"
    report.write_text(
        json.dumps(
            {
                "label": label,
                "teacher_candidate": str(candidate),
                "teacher_sha256": sha256(candidate),
                "model_strength": args.model_strength,
                "clip_strength": args.clip_strength,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "results": results,
                "verdict": "pending visual review; do not stage automatically",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Bootstrap report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
