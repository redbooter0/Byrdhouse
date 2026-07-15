"""Run the fixed local anime-target identity validation belt for one LoRA.

Candidates stay under ``artifacts/lora/candidates`` until this harness has
rendered and documented the four user-supplied targets.  The script copies a
candidate into ComfyUI only with an explicit ``_preview`` name; it never edits
the deployed recipe identity setting or promotes a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import byrdimage


TARGETS = (
    ("gojo", "anime_game_3.jpg", 7124),
    ("vegeta", "anime_game_4.jpg", 7125),
    ("luffy_close", "anime_game_2.jpg", 7126),
    ("luffy_full", "anime_game_1.jpg", 7127),
)


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--candidate", type=Path, required=True, help="LoRA candidate .safetensors file.")
    parser.add_argument("--label", required=True, help="Short provenance label for artifacts and cards.")
    parser.add_argument("--strength", type=float, default=0.90)
    parser.add_argument(
        "--clip-strength",
        type=float,
        help="Optional separate CLIP/text-encoder LoRA strength; defaults to --strength.",
    )
    parser.add_argument("--steps", type=int, default=18)
    parser.add_argument("--cfg", type=float, default=6.0)
    parser.add_argument("--denoise", type=float, default=0.48)
    parser.add_argument(
        "--presets",
        default="gojo,vegeta,luffy_close,luffy_full",
        help="Comma-separated normal-strength target presets (default: all four).",
    )
    parser.add_argument("--include-boundary", action="store_true", help="Also run Gojo at high influence for diagnostics.")
    parser.add_argument("--boundary-only", action="store_true", help="Run only the high-influence Gojo diagnostic.")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preview_name(candidate: Path, label: str) -> str:
    safe_label = "".join(char if char.isalnum() or char in "_-" else "_" for char in label).strip("_")
    return f"{candidate.stem}_{safe_label}_preview.safetensors"


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    candidate = args.candidate.resolve()
    if candidate.suffix.lower() != ".safetensors" or not candidate.is_file():
        raise SystemExit(f"Candidate must be an existing .safetensors file: {candidate}")
    if not 0.1 <= args.strength <= 1.5:
        raise SystemExit("--strength must be between 0.1 and 1.5")
    if args.clip_strength is not None and not 0.1 <= args.clip_strength <= 2.0:
        raise SystemExit("--clip-strength must be between 0.1 and 2.0")
    targets_dir = root / "Images" / "Targets" / "anime_games"
    lora_dir = root / "Generators" / "ComfyUI" / "models" / "loras"
    lora_dir.mkdir(parents=True, exist_ok=True)
    available_targets = {preset: (targets_dir / filename, seed) for preset, filename, seed in TARGETS}
    requested_presets = [preset.strip() for preset in args.presets.split(",") if preset.strip()]
    unknown_presets = [preset for preset in requested_presets if preset not in available_targets]
    if unknown_presets:
        raise SystemExit("Unknown target preset(s): " + ", ".join(unknown_presets))
    if not requested_presets and not args.boundary_only:
        raise SystemExit("--presets must select at least one normal target, unless --boundary-only is used.")
    target_paths = [(preset, *available_targets[preset]) for preset in requested_presets]
    required_paths = [path for _, path, _ in target_paths]
    if args.include_boundary or args.boundary_only:
        required_paths.append(available_targets["gojo"][0])
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise SystemExit("Missing validation target(s): " + ", ".join(missing))

    preview = lora_dir / preview_name(candidate, args.label)
    if not preview.exists() or sha256(preview) != sha256(candidate):
        shutil.copy2(candidate, preview)
    print(f"Preview LoRA: {preview.name}")

    engine = {
        "steps": args.steps,
        "cfg": args.cfg,
        "denoise": args.denoise,
        "sampler": "dpmpp_2m",
        "scheduler": "karras",
    }
    if args.clip_strength is not None:
        engine["identity_clip_strength"] = args.clip_strength
    results: list[dict[str, object]] = []
    if not args.boundary_only:
        for preset, target, seed in target_paths:
            job_id = f"anime_identity_{args.label}_{preset}"
            print(f"Validating {preset} with seed {seed}…")
            _, outputs = byrdimage.edit_target_identity(
                root,
                "anime_face_edit",
                target,
                project="image_lab",
                purpose=f"private local identity validation: {args.label}",
                identity_lora=preview.name,
                identity_strength=args.strength,
                target_preset=preset,
                subject_profile="me",
                seed=seed,
                engine=engine,
                job_id=job_id,
            )
            results.append(
                {"preset": preset, "target": str(target), "seed": seed, "outputs": [str(path) for path, _ in outputs]}
            )

    if args.include_boundary or args.boundary_only:
        boundary_engine = {**engine, "steps": 22, "denoise": 0.60}
        _, outputs = byrdimage.edit_target_identity(
            root,
            "anime_face_edit",
            available_targets["gojo"][0],
            project="image_lab",
            purpose=f"private local high-influence diagnostic: {args.label}",
            identity_lora=preview.name,
            identity_strength=1.25,
            target_preset="gojo",
            subject_profile="me",
            seed=7133,
            engine=boundary_engine,
            job_id=f"anime_identity_{args.label}_gojo_boundary",
        )
        results.append(
            {
                "preset": "gojo_boundary",
                "target": str(available_targets["gojo"][0]),
                "seed": 7133,
                "outputs": [str(path) for path, _ in outputs],
            }
        )

    output_dir = root / "artifacts" / "image_lab" / f"{datetime.now():%Y-%m}"
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / f"validation_{args.label}_{datetime.now():%Y%m%d_%H%M%S}.json"
    report.write_text(
        json.dumps(
            {
                "label": args.label,
                "candidate": str(candidate),
                "candidate_sha256": sha256(candidate),
                "preview_lora": str(preview),
                "engine": engine,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "results": results,
                "verdict": "pending visual review; preview only, never deployed",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Validation report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
