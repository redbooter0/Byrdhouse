"""Add face-centered training crops to an already staged Carey identity set.

The source files remain untouched. Each selected real photo (and, for the
studio-core diagnostic, every clean studio identity view) gets a tight and
medium face crop so the compact SD 1.5 LoRA sees facial geometry at useful
pixel density rather than mostly background, outfit, and phone framing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True)
class CropRecord:
    source: str
    crop: str
    method: str
    box: list[int]
    variant: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="ByrdHouse root (default: inferred from this script).",
    )
    parser.add_argument(
        "--dataset-mode",
        choices=("identity", "anime-mix", "studio-core", "expanded-hybrid"),
        default="identity",
        help="Select the staged set whose eligible identity buckets receive crops.",
    )
    parser.add_argument("--replace", action="store_true", help="Replace prior generated face crops.")
    return parser.parse_args()


def clip_square(center_x: float, center_y: float, side: float, width: int, height: int) -> tuple[int, int, int, int]:
    side = int(round(min(side, width, height)))
    left = int(round(center_x - side / 2))
    top = int(round(center_y - side / 2))
    left = max(0, min(width - side, left))
    top = max(0, min(height - side, top))
    return left, top, left + side, top + side


def largest_face_box(image: Image.Image, cascade: cv2.CascadeClassifier) -> tuple[int, int, int, int] | None:
    rgb = image.convert("RGB")
    array = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)
    boxes = cascade.detectMultiScale(array, scaleFactor=1.08, minNeighbors=4, minSize=(60, 60))
    if len(boxes) == 0:
        return None
    width, height = image.size
    plausible = [tuple(int(value) for value in box) for box in boxes if box[2] * box[3] >= width * height * 0.02]
    if not plausible:
        return None
    return max(plausible, key=lambda box: box[2] * box[3])


def fallback_box(image: Image.Image) -> tuple[int, int, int, int]:
    """Conservative upper-center crop for a clear selfie Haar does not find."""
    width, height = image.size
    side = min(width * 0.92, height * 0.62)
    left, top, right, bottom = clip_square(width / 2, height * 0.43, side, width, height)
    return left, top, right - left, bottom - top


def write_crop(image: Image.Image, box: tuple[int, int, int, int], multiplier: float, destination: Path) -> list[int]:
    x, y, width, height = box
    center_x = x + width / 2
    # Shift a little upward so hairline and brow remain in the training crop.
    center_y = y + height * 0.46
    crop_box = clip_square(center_x, center_y, max(width, height) * multiplier, *image.size)
    image.crop(crop_box).resize((512, 512), Image.Resampling.LANCZOS).save(destination, "PNG", optimize=True)
    return list(crop_box)


def crop_buckets(mode_root: Path, mode: str) -> list[tuple[Path, str]]:
    if mode == "identity":
        buckets = [(mode_root / "10_careybh", "real")]
    else:
        real_buckets = sorted(path for path in mode_root.glob("*_careybh_real") if path.is_dir())
        if len(real_buckets) != 1:
            raise SystemExit(
                "Expected exactly one weighted real-photo bucket in "
                f"{mode_root}; found {len(real_buckets)}."
            )
        buckets = [(real_buckets[0], "real")]
        if mode == "studio-core":
            studio_buckets = sorted(path for path in mode_root.glob("*_careybh_studio") if path.is_dir())
            if len(studio_buckets) != 1:
                raise SystemExit(
                    "Expected exactly one weighted studio-identity bucket in "
                    f"{mode_root}; found {len(studio_buckets)}."
                )
            buckets.append((studio_buckets[0], "studio"))
    return buckets


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    mode_root = root / "profiles" / "me" / "lora_dataset" / args.dataset_mode
    buckets = crop_buckets(mode_root, args.dataset_mode)
    for dataset, category in buckets:
        if not dataset.is_dir():
            raise SystemExit(f"Identity staging directory does not exist: {dataset}")
        originals = sorted(
            path for path in dataset.glob(f"{category}_*.*") if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        if not originals:
            raise SystemExit(f"No staged {category} identity images found in {dataset}")
        existing = list(dataset.glob("face_*.png")) + list(dataset.glob("face_*.txt"))
        manifest_path = dataset / "face_crop_manifest.json"
        if existing and not args.replace:
            raise SystemExit("Face crops already exist. Use --replace to rebuild them.")
        if args.replace:
            for path in existing + ([manifest_path] if manifest_path.exists() else []):
                path.unlink()

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        raise SystemExit("OpenCV's bundled Haar cascade is unavailable.")
    total = 0
    for dataset, category in buckets:
        originals = sorted(
            path for path in dataset.glob(f"{category}_*.*") if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        records: list[CropRecord] = []
        for source in originals:
            caption_path = source.with_suffix(".txt")
            if not caption_path.is_file():
                raise SystemExit(f"Missing source caption: {caption_path}")
            source_caption = caption_path.read_text(encoding="utf-8-sig").strip()
            caption = f"{source_caption}, close face crop, natural facial features"
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
            detected = largest_face_box(image, cascade)
            method = "haar" if detected else "upper_center_fallback"
            face_box = detected or fallback_box(image)
            for variant, multiplier in (("tight", 1.55), ("medium", 2.15)):
                output = dataset / f"face_{variant}_{source.stem}.png"
                crop_box = write_crop(image, face_box, multiplier, output)
                output.with_suffix(".txt").write_text(caption + "\n", encoding="utf-8")
                records.append(
                    CropRecord(
                        source=str(source), crop=str(output), method=method, box=crop_box, variant=variant
                    )
                )
                print(f"{method:21} {variant:6} {source.name} -> {output.name}")
        (dataset / "face_crop_manifest.json").write_text(
            json.dumps({"version": 1, "caption": caption, "items": [asdict(record) for record in records]}, indent=2) + "\n",
            encoding="utf-8",
        )
        total += len(records)
        print(f"Created {len(records)} face crops in {dataset}")
    print(f"Created {total} face crops across {len(buckets)} bucket(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
