"""
compose_thumbnail.py — pass 2 of the thumbnail pipeline (Blueprint v3.1 §3).

Diffusion models are bad at text, so ByrdHouse never diffuses a title:
pass 1 (byrdimage) generates the ART, this module lays REAL TEXT on top —
3-5 huge words, 900-weight font, stroke + drop shadow, palette-locked,
kept out of the subject's face zone. Output: 1280x720 YouTube-ready PNG.

Requires Pillow (the kit's only pip dependency, per the blueprint):
    python -m pip install pillow

CLI:
    python compose_thumbnail.py --image art.png --title "BEST BUILDS TIER LIST" \
        --zone upper-left --out final.png
Library:
    compose(image_path, title, out_path, zone="upper-left", palette="gold-red")
"""

import argparse
import sys
from pathlib import Path

CANVAS = (1280, 720)

# Palette-locked title colors (fill, stroke) — matches the recipe palettes.
PALETTES = {
    "gold-red":      ((255, 214, 64), (120, 12, 12)),
    "black-gold":    ((255, 214, 64), (10, 10, 10)),
    "electric-blue": ((120, 216, 255), (8, 24, 64)),
    "crimson-slate": ((255, 90, 74), (24, 28, 36)),
    "default":       ((255, 255, 255), (0, 0, 0)),
}

# Windows-first font hunt; falls back to PIL's bundled DejaVu, then bitmap.
FONT_CANDIDATES = [
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/seguibl.ttf",   # Segoe UI Black
    "DejaVuSans-Bold.ttf",
]


def _font(size: int):
    from PIL import ImageFont
    for cand in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def compose(image_path, title, out_path, zone="upper-left", palette="default",
            max_words=5):
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        sys.exit("[compose] Pillow missing — run: python -m pip install pillow")

    words = str(title).upper().split()
    if len(words) > max_words:
        print(f"[compose] WARNING: title has {len(words)} words; thumbnail grammar "
              f"wants <= {max_words}. Keeping the first {max_words}.")
        words = words[:max_words]

    art = Image.open(image_path).convert("RGB")
    # cover-fit the art onto the 1280x720 canvas
    scale = max(CANVAS[0] / art.width, CANVAS[1] / art.height)
    art = art.resize((round(art.width * scale), round(art.height * scale)))
    canvas = Image.new("RGB", CANVAS)
    canvas.paste(art, ((CANVAS[0] - art.width) // 2, (CANVAS[1] - art.height) // 2))

    fill, stroke = PALETTES.get(palette, PALETTES["default"])

    # Split into 1-3 lines of 1-2 words so every word stays huge.
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 2:
            lines.append(" ".join(cur)); cur = []
    if cur:
        lines.append(" ".join(cur))

    # Size the font so the widest line fills ~55% of the canvas width.
    target_w = CANVAS[0] * 0.55
    size = 160
    font = _font(size)
    probe = ImageDraw.Draw(canvas)
    widest = max(lines, key=lambda ln: probe.textlength(ln, font=font))
    while size > 40 and probe.textlength(widest, font=font) > target_w:
        size -= 8
        font = _font(size)

    line_h = int(size * 1.12)
    block_h = line_h * len(lines)
    margin = 42
    # Safe zones (v3.1): text never covers the subject — corners/bands only.
    zones = {
        "upper-left":  (margin, margin),
        "top":         (margin, margin),
        "bottom":      (margin, CANVAS[1] - block_h - margin),
        "center-seam": (margin, (CANVAS[1] - block_h) // 2),
    }
    x, y = zones.get(zone, zones["upper-left"])

    # Drop shadow layer (blurred), then stroked text on top.
    shadow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for i, ln in enumerate(lines):
        sd.text((x + 6, y + 6 + i * line_h), ln, font=font, fill=(0, 0, 0, 220))
    canvas.paste(Image.new("RGB", CANVAS, (0, 0, 0)),
                 mask=shadow.filter(ImageFilter.GaussianBlur(6)).split()[3])

    draw = ImageDraw.Draw(canvas)
    for i, ln in enumerate(lines):
        draw.text((x, y + i * line_h), ln, font=font, fill=fill,
                  stroke_width=max(3, size // 18), stroke_fill=stroke)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG")
    print(f"[compose] {out_path}  ({len(lines)} line(s), font {size}px, palette {palette})")
    return str(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--zone", default="upper-left",
                    choices=["upper-left", "top", "bottom", "center-seam"])
    ap.add_argument("--palette", default="default", choices=list(PALETTES))
    args = ap.parse_args()
    compose(args.image, args.title, args.out, zone=args.zone, palette=args.palette)


if __name__ == "__main__":
    main()
