"""Build a labeled visual QA sheet from references or a staged dataset.

The script is read-only with respect to sources.  It is deliberately small so
the identity-LoRA review can be repeated locally before any synthetic reference
is admitted to a training experiment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--group", default="anime", help="Manifest group to inspect.")
    parser.add_argument("--start", type=int, default=1, help="First numeric manifest ID.")
    parser.add_argument("--end", type=int, default=39, help="Last numeric manifest ID.")
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--tile-width", type=int, default=240)
    parser.add_argument(
        "--directory",
        type=Path,
        help="Inspect image files in this directory instead of the generated-reference manifest.",
    )
    parser.add_argument("--pattern", default="*.png", help="Glob used with --directory (default: *.png).")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_items(root: Path, group: str, start: int, end: int) -> list[dict[str, object]]:
    reference_root = root / "profiles" / "me" / "references" / "generated_anime_cartoon"
    manifest_path = reference_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    selected: list[dict[str, object]] = []
    for item in manifest.get("items", []):
        if item.get("group") != group or item.get("status") != "generated":
            continue
        try:
            item_id = int(str(item.get("id")))
        except ValueError:
            continue
        path = reference_root / str(item.get("filename", ""))
        if start <= item_id <= end and path.is_file():
            selected.append({"id": item_id, "name": path.stem, "path": path})
    return sorted(selected, key=lambda item: int(item["id"]))


def load_directory_items(directory: Path, pattern: str) -> list[dict[str, object]]:
    supported = {".jpg", ".jpeg", ".png", ".webp"}
    paths = sorted(
        path
        for path in directory.glob(pattern)
        if path.is_file() and path.suffix.lower() in supported
    )
    return [
        {"id": index, "name": path.stem, "path": path}
        for index, path in enumerate(paths, start=1)
    ]


def build_sheet(items: list[dict[str, object]], columns: int, tile_width: int) -> Image.Image:
    if not items:
        raise SystemExit("No matching generated manifest images were found.")
    if columns < 1 or tile_width < 80:
        raise SystemExit("--columns must be positive and --tile-width must be at least 80.")
    label_height = 38
    tile_height = int(tile_width * 1.28)
    padding = 8
    rows = (len(items) + columns - 1) // columns
    canvas = Image.new(
        "RGB",
        (columns * (tile_width + padding) + padding, rows * (tile_height + label_height + padding) + padding),
        "#16181f",
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, item in enumerate(items):
        x = padding + (index % columns) * (tile_width + padding)
        y = padding + (index // columns) * (tile_height + label_height + padding)
        with Image.open(item["path"]) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        preview = ImageOps.fit(image, (tile_width, tile_height), method=Image.Resampling.LANCZOS)
        canvas.paste(preview, (x, y))
        label = f"{int(item['id']):03d} {str(item['name'])[:25]}"
        draw.text((x + 4, y + tile_height + 8), label, fill="white", font=font)
    return canvas


def main() -> int:
    args = parse_args()
    if args.directory:
        directory = args.directory.resolve()
        if not directory.is_dir():
            raise SystemExit(f"Directory does not exist: {directory}")
        items = load_directory_items(directory, args.pattern)
    else:
        items = load_items(args.root.resolve(), args.group, args.start, args.end)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    build_sheet(items, args.columns, args.tile_width).save(output, "PNG", optimize=True)
    print(f"Wrote {len(items)} previews to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
