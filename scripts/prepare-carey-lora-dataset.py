"""Stage a small, reproducible Carey identity-LoRA dataset from local refs.

This script never modifies the source reference folders.  It copies only
approved files into a git-ignored staging folder and adds conservative captions
with the stable trigger phrase ``careybh person``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from PIL import Image, UnidentifiedImageError
except ImportError as exc:  # Run with the ComfyUI Python, which includes Pillow.
    raise SystemExit("Pillow is required. Run this with the ComfyUI .venv Python.") from exc


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
CORE_REAL_NAMES = (
    "me_photo_01.jpg",
    "me_photo_02.jpg",
    "me_photo_03.jpg",
    "me_photo_04.jpg",
    "me_photo_05.jpg",
    "me_photo_07.jpg",
    "me_photo_09.jpg",
    # 2026-07-14 refresh: user-supplied real photos add cleaner smiles,
    # three-quarter views, and genuinely different lighting/hair states.
    # These are real-photo anchors, never generated style material.
    "me_photo_11.jpg",
    "me_photo_12.jpg",
    "me_photo_13.jpg",
    "me_photo_14.jpg",
    "me_photo_15.jpg",
    "me_photo_19.jpg",
)
# These variations remain out of the default identity set: 06 has a cap and
# hard shadow; 08 is washed/redundant; 17 has reflective glasses across the
# eyes.  Keep them available only for a deliberately reviewed follow-up.
OPTIONAL_REAL_NAMES = (
    "me_photo_06.jpg",
    "me_photo_08.jpg",
    "me_photo_17.jpg",
)
# 10 has a tiny face; 16 is motion-soft; 18 is soft with a distracting hand;
# and 20 is soft with low, cluttered framing.  They are archived as references
# but deliberately excluded from both the core and optional training sets.
ANIME_SEED_IDS = (
    "001",
    "002",
    "003",
    "011",
    "012",
    "013",
    "016",
    "017",
    "020",
    "021",
    "022",
    "023",
    "027",
    "031",
    "032",
    "033",
    "036",
    "037",
)

# Full-corpus audit of generated IDs 001-100.  These frames keep Carey's face
# readable while spanning materially different 2D shape languages.  They are
# style support only: authentic camera photos remain the identity ground truth.
ANIMATION_SUPPORT_IDS = (
    "002",
    "011",
    "012",
    "021",
    "022",
    "027",
    "030",
    "041",
    "050",
    "051",
    "061",
    "062",
    "067",
    "070",
    "072",
    "076",
    "081",
    "086",
    "091",
    "097",
)

# Synthetic-photoreal frames are never identity truth.  Keep this list tiny
# and its repeat weight at one so camera photos and verified face crops
# dominate.  Late-batch picks are added only after the 101-200 audit.
SYNTHETIC_REAL_SUPPORT_IDS = (
    "101",
    "108",
    "111",
    "121",
)

STUDIO_IDENTITY_GLOB = "ai_identity_*.png"
# Describe the attributes that change from photo to photo so the rare trigger
# is pushed toward the stable identity geometry instead of memorizing hair,
# expression, lighting, or a recurring selfie background.
REAL_CAPTION_DETAILS = {
    "me_photo_01.jpg": "three-quarter view, neutral expression, natural afro, warm indoor light",
    "me_photo_02.jpg": "three-quarter view, smiling, short natural afro, warm indoor light",
    "me_photo_03.jpg": "front view, neutral expression, short braids, overhead retail light",
    "me_photo_04.jpg": "front view, smiling with teeth, full natural afro, indoor overhead light",
    "me_photo_05.jpg": "front view, smiling with teeth, black durag, daylight",
    "me_photo_07.jpg": "front view, neutral expression, full natural afro, strong daylight, low camera angle",
    "me_photo_09.jpg": "front view, neutral expression, braids, warm indoor light, mirror selfie",
    "me_photo_11.jpg": "front view, neutral expression, natural afro, soft daylight, car interior",
    "me_photo_12.jpg": "three-quarter view, neutral expression, braids, warm indoor light",
    "me_photo_13.jpg": "front view, neutral expression, full natural afro, black headband, daylight",
    "me_photo_14.jpg": "front view, neutral expression, short natural hair, daylight",
    "me_photo_15.jpg": "front view, smiling with teeth, natural afro, clean indoor light",
    "me_photo_19.jpg": "three-quarter view, neutral expression, full natural afro, soft indoor light, earbuds",
}
# The repeat folder names are consumed directly by sd-scripts.  Real images
# remain the ground truth; studio render angles and personally approved anime
# portraits only add controlled coverage for the target anime workflow.
ANIME_MIX_BUCKETS = {
    "real": "5_careybh_real",
    "studio": "3_careybh_studio",
    "anime": "2_careybh_anime",
}
STUDIO_CORE_BUCKETS = {
    "real": "5_careybh_real",
    "studio": "6_careybh_studio",
}
EXPANDED_HYBRID_BUCKETS = {
    "real": "5_careybh_real",
    "synthetic": "1_careybh_synthetic_support",
    "anime": "2_careybh_animation_support",
}


@dataclass(frozen=True)
class StagedImage:
    source: str
    destination: str
    category: str
    width: int
    height: int
    sha256: str
    caption: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="ByrdHouse root (default: inferred from this script).",
    )
    parser.add_argument(
        "--mode",
        choices=("identity", "anime-mix", "studio-core", "expanded-hybrid"),
        default="identity",
        help=(
            "identity uses real photos only; studio-core adds studio-angle support; "
            "anime-mix is the legacy starter mix; expanded-hybrid uses the audited "
            "001-200 support subset while keeping camera photos dominant."
        ),
    )
    parser.add_argument(
        "--max-anime",
        type=int,
        default=24,
        help="Maximum approved anime references for anime-mix (default: 24).",
    )
    parser.add_argument(
        "--include-optional-real",
        action="store_true",
        help="Also use reviewed cap/shadow, washed, or glasses variations (not recommended by default).",
    )
    parser.add_argument(
        "--include-unreviewed-anime",
        action="store_true",
        help="Include extra anime files after the reviewed starter set (not recommended for v1).",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the generated staging directory for this mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the selected files without copying anything.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dimensions(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise SystemExit(f"Unreadable image: {path} ({exc})") from exc


def real_sources(reference_root: Path, include_optional: bool) -> list[Path]:
    names = list(CORE_REAL_NAMES)
    if include_optional:
        names.extend(OPTIONAL_REAL_NAMES)
    missing = [name for name in names if not (reference_root / name).is_file()]
    if missing:
        raise SystemExit("Missing selected real reference(s): " + ", ".join(missing))
    return [reference_root / name for name in names]


def studio_sources(reference_root: Path) -> list[Path]:
    sources = sorted(path for path in reference_root.glob(STUDIO_IDENTITY_GLOB) if path.is_file())
    if not sources:
        raise SystemExit(
            "The anime-mix experiment requires the generated studio identity views "
            f"matching {STUDIO_IDENTITY_GLOB} in {reference_root}."
        )
    return sources


def anime_sources(anime_root: Path, maximum: int, include_unreviewed: bool) -> list[Path]:
    if maximum < 1:
        raise SystemExit("--max-anime must be at least 1.")
    manifest_path = anime_root / "manifest.json"
    manifest_items: list[tuple[str, Path]] = []
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Unreadable anime reference manifest: {manifest_path} ({exc})") from exc
        for item in manifest.get("items", []):
            if item.get("group") != "anime" or item.get("status") != "generated":
                continue
            filename = item.get("filename")
            item_id = str(item.get("id", ""))
            path = anime_root / filename if filename else None
            if path and path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                manifest_items.append((item_id, path))
    if not manifest_items:
        # A safe fallback for a new user-owned library before its manifest has
        # been generated. IDs 001-039 are the existing anime lane; do not
        # accidentally blend in the separate cartoon lanes.
        for path in sorted(anime_root.iterdir()):
            prefix = path.name.split("_", 1)[0]
            if (
                path.is_file()
                and path.suffix.lower() in IMAGE_SUFFIXES
                and prefix.isdigit()
                and 1 <= int(prefix) <= 39
            ):
                manifest_items.append((prefix.zfill(3), path))
    by_id = {item_id: path for item_id, path in manifest_items}
    chosen = [by_id[item_id] for item_id in ANIME_SEED_IDS if item_id in by_id]
    if include_unreviewed:
        chosen_names = {path.name for path in chosen}
        chosen.extend(
            path
            for _, path in manifest_items
            if path.name not in chosen_names
        )
    return chosen[:maximum]


def selected_manifest_sources(directory: Path, selected_ids: tuple[str, ...], label: str) -> list[Path]:
    """Resolve an explicit, audited ID list without trusting manifest status."""
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Missing {label} manifest: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Unreadable {label} manifest: {manifest_path} ({exc})") from exc
    by_id: dict[str, Path] = {}
    for item in manifest.get("items", []):
        item_id = str(item.get("id", "")).zfill(3)
        filename = item.get("filename")
        path = directory / filename if filename else None
        if path and path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            by_id[item_id] = path
    missing = [item_id for item_id in selected_ids if item_id not in by_id]
    if missing:
        raise SystemExit(f"Missing audited {label} image(s): {', '.join(missing)}")
    return [by_id[item_id] for item_id in selected_ids]


def manifest_item(source: Path) -> dict[str, object]:
    manifest_path = source.parent / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    for item in manifest.get("items", []):
        if item.get("filename") == source.name:
            return item
    return {}


def caption_for(source: Path, category: str) -> str:
    if category == "real":
        caption = "careybh person, adult Black man, portrait photograph"
        details = REAL_CAPTION_DETAILS.get(source.name)
        return f"{caption}, {details}" if details else caption
    item = manifest_item(source)
    view = str(item.get("view", "")).strip()
    hairstyle = str(item.get("hairstyle", "")).strip()
    details = ", ".join(part for part in (view, hairstyle) if part)
    if category == "synthetic":
        caption = "careybh person, adult Black man, synthetic photoreal support portrait"
    elif category == "anime":
        tone = str(item.get("tone_reference", "")).strip()
        caption = "careybh person, adult Black man, animation illustration"
        if tone:
            caption += f", broad {tone} visual tone"
    else:
        caption = "careybh person, adult Black man, studio identity portrait"
    return f"{caption}, {details}" if details else caption


def relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def stage_images(sources: list[tuple[Path, str, Path]]) -> list[StagedImage]:
    staged: list[StagedImage] = []
    counters: dict[tuple[str, Path], int] = {}
    for source, category, destination in sources:
        key = (category, destination)
        counters[key] = counters.get(key, 0) + 1
        width, height = dimensions(source)
        file_name = f"{category}_{counters[key]:03d}_{source.name}"
        copied = destination / file_name
        caption = caption_for(source, category)
        shutil.copy2(source, copied)
        copied.with_suffix(".txt").write_text(caption + "\n", encoding="utf-8")
        staged.append(
            StagedImage(
                source=str(source),
                destination=str(copied),
                category=category,
                width=width,
                height=height,
                sha256=sha256(source),
                caption=caption,
            )
        )
    return staged


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    references = root / "profiles" / "me" / "references"
    anime_root = references / "generated_anime_cartoon"
    mode_root = root / "profiles" / "me" / "lora_dataset" / args.mode
    if args.mode == "identity":
        destinations = {"real": mode_root / "10_careybh"}
    elif args.mode == "studio-core":
        destinations = {category: mode_root / bucket for category, bucket in STUDIO_CORE_BUCKETS.items()}
    elif args.mode == "expanded-hybrid":
        destinations = {category: mode_root / bucket for category, bucket in EXPANDED_HYBRID_BUCKETS.items()}
    else:
        destinations = {category: mode_root / bucket for category, bucket in ANIME_MIX_BUCKETS.items()}
    allowed_root = root / "profiles" / "me" / "lora_dataset"

    if not references.is_dir():
        raise SystemExit(f"Reference directory does not exist: {references}")
    if not relative_to(mode_root, allowed_root) or any(
        not relative_to(destination, allowed_root) for destination in destinations.values()
    ):
        raise SystemExit(f"Refusing to stage outside {allowed_root}")

    sources: list[tuple[Path, str, Path]] = [
        (path, "real", destinations["real"])
        for path in real_sources(references, args.include_optional_real)
    ]
    if args.mode in ("studio-core", "anime-mix"):
        sources.extend((path, "studio", destinations["studio"]) for path in studio_sources(references))
    if args.mode == "anime-mix":
        if not anime_root.is_dir():
            raise SystemExit(f"Anime reference directory does not exist: {anime_root}")
        sources.extend(
            (path, "anime", destinations["anime"])
            for path in anime_sources(
                anime_root, args.max_anime, args.include_unreviewed_anime
            )
        )
    if args.mode == "expanded-hybrid":
        synthetic_root = references / "generated_real_photos"
        if not synthetic_root.is_dir() or not anime_root.is_dir():
            raise SystemExit("Expanded-hybrid requires both completed generated support directories.")
        sources.extend(
            (path, "synthetic", destinations["synthetic"])
            for path in selected_manifest_sources(
                synthetic_root, SYNTHETIC_REAL_SUPPORT_IDS, "synthetic-photoreal"
            )
        )
        sources.extend(
            (path, "anime", destinations["anime"])
            for path in selected_manifest_sources(
                anime_root, ANIMATION_SUPPORT_IDS, "animation"
            )
        )

    print(f"Mode: {args.mode}")
    kinds = ("real", "studio", "synthetic", "anime")
    selection_summary = ", ".join(
        f"{sum(kind == category for _, kind, _ in sources)} {category}" for category in kinds if any(kind == category for _, kind, _ in sources)
    )
    print(f"Selected: {len(sources)} ({selection_summary})")
    for path, category, _ in sources:
        width, height = dimensions(path)
        print(f"  {category:5} {width:4}x{height:<4} {path.name}")

    if args.dry_run:
        return 0
    if mode_root.exists():
        if not args.replace:
            raise SystemExit(
                f"Staging directory exists: {mode_root}. Use --replace to rebuild it."
            )
        shutil.rmtree(mode_root)
    for destination in destinations.values():
        destination.mkdir(parents=True, exist_ok=False)
    staged = stage_images(sources)
    manifest = {
        "version": 3,
        "mode": args.mode,
        "trigger": "careybh person",
        "source_root": str(references),
        "buckets": {category: str(path) for category, path in destinations.items()},
        "strategy": (
            "camera-ground-truth-with-low-weight-generated-support"
            if args.mode == "expanded-hybrid"
            else "legacy"
        ),
        "items": [asdict(item) for item in staged],
    }
    (mode_root / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Staged {len(staged)} image/caption pairs at {mode_root}")
    if args.mode == "identity" and len(staged) < 12:
        print(
            "NOTE: this is a technical starter set, not enough for a final LoRA. "
            "Add 6-12 more clear real photos before final training."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
