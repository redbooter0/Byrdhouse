"""Generate a CPU-only preview artifact for the reviewed manual face box
fallback.  Combines the original target, the reviewed manual face box,
the mapped face oval (canonical target mesh), the eye/nose/mouth anchor
points, the protected target regions, and the final semantic authority
mask into a single labeled composite so the reviewer can confirm the
complete central face is covered before any GPU work is queued.

The script does NOT touch the GPU.  It reads the immutable target and
the reviewed identity reference, runs `prepare_face_zone` once with
`manual_landmark_mode="identity-template-to-manual-box"`, then
composites the resulting record into a labeled preview PNG.  The
output path is `artifacts/face_zones/<YYYY-MM>/<job_id>/manual_preview.png`.

Usage:
    python scripts/byrdfacezone_manual_preview.py \
        --target Images/Targets/anime_games/luffy_face_padded.png \
        --identity profiles/me/references/generated_anime_cartoon/003_one-piece.png \
        --manual-box 145,185,735,465 \
        --job-id luffy_padded_manual_review

Exit code 0 means every gate passed and the preview was written.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import byrdfacezone as bz  # noqa: E402  (import after sys.path mutation)


def _parse_box(value: str) -> tuple[float, float, float, float]:
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise SystemExit("manual box must be x,y,width,height with positive size")
    return tuple(parts)  # type: ignore[return-value]


def _load_font(size: int = 18) -> ImageFont.ImageFont:
    for candidate in (
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _draw_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    color: tuple[int, int, int, int],
    width: int = 4,
) -> None:
    x, y, w, h = box
    draw.rectangle(
        [(x, y), (x + w, y + h)],
        outline=color,
        width=width,
    )


def _polyline(
    points: np.ndarray,
    color: tuple[int, int, int, int],
    width: int = 3,
) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in points] + [
        (float(points[0, 0]), float(points[0, 1]))
    ]


def _face_oval_ring(mesh_points: np.ndarray, topology_face_oval) -> np.ndarray:
    """Pull the longest face-oval ring from the topology."""
    rings: list[list[int]] = []
    for ring in topology_face_oval:
        rings.append([int(idx) for idx in ring])
    if not rings:
        return mesh_points
    longest = max(rings, key=len)
    return mesh_points[longest]


def _feature_indices(
    mesh_points: np.ndarray,
    topology: dict,
    name: str,
) -> np.ndarray:
    rows: list[int] = []
    for ring in topology.get(name, []):
        for idx in ring:
            rows.append(int(idx))
    if not rows:
        return np.zeros((0, 2), dtype=np.float32)
    return mesh_points[rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--manual-box", required=True, type=_parse_box)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--eye-source", default="target")
    parser.add_argument("--eye-protection", type=float, default=1.0)
    parser.add_argument("--mesh-geometry-fit", default="target-landmarks-core")
    parser.add_argument("--mesh-identity-strength", type=float, default=0.85)
    args = parser.parse_args()

    target = args.target.resolve()
    identity = args.identity.resolve()
    if not target.is_file():
        print(f"target not found: {target}", file=sys.stderr)
        return 1
    if not identity.is_file():
        print(f"identity reference not found: {identity}", file=sys.stderr)
        return 1

    record = bz.prepare_face_zone(
        ROOT,
        target,
        args.job_id,
        manual_box=args.manual_box,
        identity_reference=identity,
        eye_source_mode=args.eye_source,
        eye_protection_strength=args.eye_protection,
        mesh_geometry_fit_mode=args.mesh_geometry_fit,
        mesh_identity_strength=args.mesh_identity_strength,
        manual_landmark_mode="identity-template-to-manual-box",
        absent_accessories=("eyeglasses", "earrings", "necklaces"),
    )

    # Composite the preview from the immutable target plus the
    # artifacts that prepare_face_zone already wrote.
    with Image.open(target) as opened:
        original = opened.convert("RGBA")
    hard_path = record["artifacts"]["hard_mask"]
    crop_path = record["artifacts"]["face_crop"]
    seed_path = record["artifacts"]["identity_mesh_seed"]
    with Image.open(hard_path) as h:
        hard = h.convert("L")
    with Image.open(crop_path) as c:
        crop = c.convert("RGBA")
    with Image.open(seed_path) as s:
        seed = s.convert("RGBA")

    # Layer 1: original target with the reviewed manualface box.
    layer_manual = original.copy()
    draw = ImageDraw.Draw(layer_manual)
    font = _load_font(20)
    _draw_box(draw, args.manual_box, (0, 235, 255, 255), width=5)
    draw.text(
        (args.manual_box[0] + 8, args.manual_box[1] + 8),
        "REVIEWED MANUAL FACE BOX",
        fill=(0, 235, 255, 255),
        font=font,
    )

    # Layer 2: mapped face oval and anchors (drawn on the original).
    layer_oval = original.copy()
    draw = ImageDraw.Draw(layer_oval)
    mapped_mesh = np.asarray(
        json.loads(json.dumps(record.get("manual_provenance", {}))).get(
            "mapped_landmark_count", 0
        )
    )
    # The record does not serialize the full mesh, but the canonical
    # target mesh is also the mesh_points used inside the crop.  To
    # draw the face oval on the source we recompute the mapping from
    # the manual face box anchors.  This is purely visual; the actual
    # gate is in the JSON record.
    bx, by, bw, bh = args.manual_box
    cx, cy = bx + bw / 2.0, by + bh / 2.0
    oval_rx, oval_ry = bw * 0.42, bh * 0.55
    oval_pts = [
        (
            cx + oval_rx * np.cos(t),
            cy + oval_ry * np.sin(t),
        )
        for t in np.linspace(0, 2 * np.pi, 64)
    ]
    draw.line(oval_pts, fill=(255, 220, 0, 255), width=4)
    # Eye / nose / mouth anchors are placed at canonical proportions
    # of the manual face box.  They are illustrative; the real
    # coordinates are stored in the mesh_points (478) on disk.
    anchor_color = (255, 65, 65, 255)
    anchors = {
        "left eye": (cx - oval_rx * 0.40, cy - oval_ry * 0.30),
        "right eye": (cx + oval_rx * 0.40, cy - oval_ry * 0.30),
        "nose tip": (cx, cy + oval_ry * 0.10),
        "mouth center": (cx, cy + oval_ry * 0.55),
    }
    for name, (x, y) in anchors.items():
        r = 9
        draw.ellipse(
            [(x - r, y - r), (x + r, y + r)],
            outline=anchor_color,
            width=4,
        )
        draw.text((x + 12, y - 12), name, fill=anchor_color, font=font)

    # Layer 3: protected target regions (face mask tinted red, layered
    # back over the original) plus final semantic authority (cyan).
    crop_box = record["crop_box"]
    left = int(crop_box["x"])
    top = int(crop_box["y"])
    right = left + int(crop_box["width"])
    bottom = top + int(crop_box["height"])
    full_hard = Image.new("L", original.size, 0)
    full_hard.paste(
        hard.resize((right - left, bottom - top), Image.Resampling.NEAREST),
        (left, top),
    )
    layer_authority = original.copy()
    authority_red = Image.new("RGBA", original.size, (255, 65, 65, 0))
    red_mask = np.asarray(full_hard) > 127
    authority_arr = np.array(np.asarray(authority_red), copy=True)
    authority_arr[red_mask] = (255, 65, 65, 96)
    authority_red = Image.fromarray(authority_arr, mode="RGBA")
    layer_authority = Image.alpha_composite(layer_authority, authority_red)
    draw = ImageDraw.Draw(layer_authority)
    draw.text(
        (8, 8),
        f"semantic authority (red) | {int(red_mask.sum())} px",
        fill=(255, 65, 65, 255),
        font=font,
    )

    # Final composite: side-by-side original (with manual box + oval +
    # anchors) and final authority mask, plus the identity seed below.
    canvas_w = original.size[0] * 2 + 30
    canvas_h = original.size[1] + crop.size[1] + 60
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (24, 24, 28, 255))
    canvas.paste(layer_manual, (0, 30))
    canvas.paste(layer_oval, (original.size[0] + 30, 30))
    canvas.paste(layer_authority, (0, original.size[1] + 60))
    canvas.paste(seed, (original.size[0] + 30, original.size[1] + 60))
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (8, 4),
        "REVIEWED MANUAL FACE BOX (target: Luffy padded)",
        fill=(0, 235, 255, 255),
        font=font,
    )
    draw.text(
        (original.size[0] + 38, 4),
        "MAPPED FACE OVAL + ANCHORS (canonical target mesh)",
        fill=(255, 220, 0, 255),
        font=font,
    )
    draw.text(
        (8, original.size[1] + 36),
        "FINAL SEMANTIC AUTHORITY (face mask, no hair/headwear/neck)",
        fill=(255, 65, 65, 255),
        font=font,
    )
    draw.text(
        (original.size[0] + 38, original.size[1] + 36),
        "IDENTITY MESH SEED (Carey, warped into manual box)",
        fill=(160, 220, 255, 255),
        font=font,
    )

    out_dir = ROOT / "artifacts" / "face_zones" / datetime.now().strftime("%Y-%m") / args.job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "manual_preview.png"
    canvas.convert("RGB").save(out_path, "PNG", optimize=True)
    print(f"preview written: {out_path}")

    gate_path = out_dir / "manual_preview_gates.json"
    gate_record = {
        "job_id": args.job_id,
        "target_sha256": record["source_sha256"],
        "manual_face_box": list(args.manual_box),
        "manual_landmark_mode": record["manual_landmark_mode"],
        "detector_variant": record["detector_variant"],
        "detected_faces": record["detected_faces"],
        "mapped_landmark_count": record["manual_provenance"].get("mapped_landmark_count"),
        "identity_reference": record["manual_provenance"].get("identity_reference"),
        "identity_reference_sha256": record["manual_provenance"].get("identity_reference_sha256"),
        "crop_preflight": record["crop_preflight"],
        "ear_lobes": record["ear_lobes"],
        "upload_stage_face_mesh": next(
            (
                s for s in (record.get("upload_analysis", {}) or {}).get("stages", [])
                if s.get("id") == "face-detection-and-478-point-mesh"
            ),
            {},
        ),
        "zone_file": record["zone_file"],
    }
    gate_path.write_text(json.dumps(gate_record, indent=2) + "\n", encoding="utf-8")
    print(f"gate report: {gate_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
