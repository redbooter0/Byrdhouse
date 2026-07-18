#!/usr/bin/env python3
"""Fast CPU-only tests for the audited target head-mold cache."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_head_mold_library as molds  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def save_mask(path: Path, painter) -> None:
    image = Image.new("L", (64, 64), 0)
    painter(ImageDraw.Draw(image))
    image.save(path)


def create_fixture(root: Path, index: int) -> tuple[Path, Path]:
    target = root / f"target_{index}.png"
    Image.new("RGB", (96, 80), (20 + index, 40, 60)).save(target)
    zone_dir = root / f"zone_{index}"
    zone_dir.mkdir()

    save_mask(
        zone_dir / "head.png",
        lambda draw: (
            draw.ellipse((10, 4, 54, 55), fill=255),
            draw.rectangle((22, 43, 42, 63), fill=255),
        ),
    )
    save_mask(
        zone_dir / "skin.png",
        lambda draw: (
            draw.ellipse((13, 8, 51, 53), fill=255),
            draw.rectangle((24, 43, 40, 61), fill=255),
        ),
    )
    save_mask(
        zone_dir / "lineart.png",
        lambda draw: (
            draw.line((22, 27, 28, 26), fill=255, width=2),
            draw.line((36, 26, 42, 27), fill=255, width=2),
            draw.line((28, 40, 37, 40), fill=255, width=2),
        ),
    )
    save_mask(
        zone_dir / "hair.png",
        lambda draw: draw.polygon(
            ((10, 4), (54, 4), (49, 19), (39, 13), (31, 21), (23, 13), (15, 20)),
            fill=255,
        ),
    )
    save_mask(
        zone_dir / "hairline.png",
        lambda draw: draw.line(
            ((15, 20), (23, 13), (31, 21), (39, 13), (49, 19)),
            fill=255,
            width=2,
        ),
    )
    save_mask(
        zone_dir / "neck.png",
        lambda draw: draw.rectangle((24, 45, 40, 61), fill=255),
    )
    save_mask(
        zone_dir / "protected_color.png",
        lambda draw: draw.ellipse((29, 32, 35, 36), outline=255, width=1),
    )
    save_mask(
        zone_dir / "identity_core.png",
        lambda draw: draw.ellipse((18, 20, 46, 48), fill=255),
    )

    checkpoints = {
        "neck_left": {"x": 24, "y": 60},
        "left_outer": {"x": 10, "y": 30},
        "top": {"x": 32, "y": 4},
        "right_outer": {"x": 54, "y": 30},
        "neck_right": {"x": 40, "y": 60},
    }
    zone = {
        "version": 1,
        "source": str(target),
        "source_sha256": sha256_file(target),
        "processor": "cpu-test-landmarker",
        "manual_zone": False,
        "zone_kind": molds.EXPECTED_ZONE_KIND,
        "canvas_size": 64,
        "crop_box": {"x": 8, "y": 4, "width": 64, "height": 64},
        "crop_preflight": {"passed": True},
        "semantic_parser": {
            "name": "test-parser",
            "license": "test-only",
            "deployment_scope": "test-only",
            "head_contour": {
                "body_part_traversal": {
                    "passed": True,
                    "closed": True,
                    "order": [
                        "neck-left",
                        "left-outer-head-and-ear",
                        "top-of-head",
                        "right-outer-head-and-ear",
                        "neck-right",
                        "neck-anchor-close",
                    ],
                    "checkpoints": checkpoints,
                }
            },
        },
        "upload_analysis": {
            "all_passed": True,
            "acceptance_contract": {
                "target_feature_lock": {
                    "eyes": {"bbox": {"x": 20, "y": 24, "width": 24, "height": 6}},
                    "mouth": {"bbox": {"x": 27, "y": 38, "width": 11, "height": 5}},
                }
            },
            "pixel_feature_inventory": {
                "geometry_expression_pose": {
                    "yaw_asymmetry": 0.05,
                    "mouth_open_ratio": 0.01,
                }
            },
        },
        "artifacts": {
            "head_envelope": str(zone_dir / "head.png"),
            "hard_mask": str(zone_dir / "skin.png"),
            "protected_seed_features": str(zone_dir / "lineart.png"),
            "hair_headwear_exclusion": str(zone_dir / "hair.png"),
            "hair_boundary": str(zone_dir / "hairline.png"),
            "neck_anchor": str(zone_dir / "neck.png"),
            "protected_color_features": str(zone_dir / "protected_color.png"),
            "identity_mesh_warp_mask": str(zone_dir / "identity_core.png"),
        },
    }
    zone_manifest = zone_dir / "face_zone.json"
    zone_manifest.write_text(json.dumps(zone), encoding="utf-8")
    return target, zone_manifest


class HeadMoldLibraryTests(unittest.TestCase):
    def test_seven_targets_build_336_bounded_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "library"
            entries = []
            for index in range(7):
                target, zone = create_fixture(root, index)
                entries.append(
                    {"target": str(target), "zone_manifest": str(zone)}
                )
            mapping = root / "map.json"
            mapping.write_text(json.dumps({"targets": entries}), encoding="utf-8")

            result = molds.build_map(mapping, library)
            self.assertEqual(result["targets"], 7)
            self.assertEqual(result["mold_count"], 7)
            self.assertEqual(result["total_parameterized_variants"], 336)

            index = json.loads((library / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["mold_count"], 7)
            self.assertEqual(index["total_parameterized_variants"], 336)

            first_dir = library / index["molds"][0]["target_sha256"]
            manifest = json.loads(
                (first_dir / "mold.json").read_text(encoding="utf-8")
            )
            self.assertFalse(manifest["contains_rgb_target_artwork"])
            self.assertEqual(manifest["variant_count"], 48)
            self.assertFalse(any(path.suffix.lower() in {".jpg", ".jpeg"} for path in first_dir.rglob("*")))

            skin = Image.open(first_dir / "skin.png").convert("L")
            protected = Image.open(first_dir / "protected.png").convert("L")
            for record in manifest["variants"]:
                variant = Image.open(first_dir / record["path"]).convert("L")
                self.assertEqual(
                    molds.mask_pixels(ImageChops.subtract(variant, skin)), 0
                )
                self.assertEqual(
                    molds.mask_intersection_pixels(variant, protected), 0
                )

            verification = molds.verify_mold(first_dir)
            self.assertEqual(verification["variant_count"], 48)

    def test_missing_authoritative_mask_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target, zone_manifest = create_fixture(root, 0)
            zone = json.loads(zone_manifest.read_text(encoding="utf-8"))
            Path(zone["artifacts"]["hair_boundary"]).unlink()
            with self.assertRaisesRegex(molds.MoldError, "hair_boundary"):
                molds.build_mold(target, zone_manifest, root / "library")

    def test_sha_mismatch_never_reuses_masks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target, zone_manifest = create_fixture(root, 0)
            Image.new("RGB", (96, 80), (250, 10, 10)).save(target)
            with self.assertRaisesRegex(molds.MoldError, "SHA-256"):
                molds.build_mold(target, zone_manifest, root / "library")


if __name__ == "__main__":
    unittest.main()
