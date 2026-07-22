import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import byrdfacezone
import byrdswap


class ImageLaneRegressionTests(unittest.TestCase):
    def test_finish_source_preserves_at_recipe_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "candidate.png"
            Image.new("RGB", (8, 8), "black").save(image)
            card = {
                "job_id": "job.test",
                "target": str(image),
                "recipe": "anime_face_zone_edit@1",
                "seed": 7125,
                "target_preset": "vegeta",
                "engine": {},
            }
            Path(str(image) + ".json").write_text(json.dumps(card), encoding="utf-8")
            self.assertEqual(byrdswap.finish_source(image)["recipe"], "anime_face_zone_edit@1")

    def test_composite_never_expands_immutable_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            original = work / "original.png"
            generated = work / "generated.png"
            face_crop = work / "face_crop.png"
            hard = work / "hard.png"
            soft = work / "soft.png"
            output = work / "output.png"
            zone_file = work / "face_zone.json"

            Image.new("RGB", (100, 60), (20, 30, 40)).save(original)
            Image.new("RGB", (64, 64), (130, 70, 55)).save(generated)
            Image.new("RGB", (64, 64), (20, 30, 40)).save(face_crop)
            mask = Image.new("L", (64, 64), 0)
            ImageDraw.Draw(mask).ellipse((8, 6, 56, 58), fill=255)
            mask.save(hard)
            mask.save(soft)
            zone_file.write_text(
                json.dumps(
                    {
                        "crop_box": {"x": 20, "y": 0, "width": 64, "height": 64},
                        "identity_mesh": None,
                        "artifacts": {
                            "original": str(original),
                            "face_crop": str(face_crop),
                            "hard_mask": str(hard),
                            "soft_mask": str(soft),
                        },
                    }
                ),
                encoding="utf-8",
            )

            byrdfacezone.composite_generated(zone_file, generated, output)
            with Image.open(output) as rendered:
                self.assertEqual(rendered.size, (100, 60))
            verification = json.loads(Path(str(output) + ".verify.json").read_text())
            self.assertTrue(verification["outside_mask"]["passed"])

    def test_manual_recovery_does_not_infer_unreviewed_ears(self):
        source = (SCRIPTS / "byrdfacezone.py").read_text(encoding="utf-8")
        self.assertIn(
            "ear_boxes = [] if manual_box is not None else _ear_boxes",
            source,
        )

    def test_likeness_parser_targets_final_json_block(self):
        source = (SCRIPTS / "byrdimage.py").read_text(encoding="utf-8")
        self.assertIn('likeness_output.rfind("\\n{")', source)
        self.assertIn('card["status"] = "needs_review"', source)


if __name__ == "__main__":
    unittest.main()