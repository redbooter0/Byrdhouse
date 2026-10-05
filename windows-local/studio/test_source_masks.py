"""Source-mask graph contracts and collected-output checks, without model/GPU imports."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from source_masks import (CORE_SHRINK_PIXELS, GUARD_PIXELS, LABEL_ID_TO_NAME, PARSER_FLAG_TO_LABEL_ID,
                          MaskError, build_mask_graph, inspect_masks)


class GraphTests(unittest.TestCase):
    def test_installed_schema_and_link_types(self):
        # Required input/output types independently captured from the installed
        # /object_info endpoint on 2026-10-03. No live requests in these tests.
        schemas = {
            "LoadImage": ({"image": "STRING"}, ["IMAGE", "MASK"]),
            "LoadBackgroundRemovalModel": ({"bg_removal_name": "STRING"}, ["BACKGROUND_REMOVAL"]),
            "RemoveBackground": ({"bg_removal_model": "BACKGROUND_REMOVAL", "image": "IMAGE"}, ["MASK"]),
            "FaceParsingModelLoaderNew": ({"device": "STRING"}, ["FACE_PARSING_MODEL"]),
            "FaceParsingProcessorLoader(FaceParsing)": ({}, ["FACE_PARSING_PROCESSOR"]),
            "FaceParse(FaceParsing)": ({"model": "FACE_PARSING_MODEL", "processor": "FACE_PARSING_PROCESSOR",
                                        "image": "IMAGE"}, ["IMAGE", "FACE_PARSING_RESULT"]),
            "FaceParsingResultsParser(FaceParsing)": ({"result": "FACE_PARSING_RESULT", **{
                name: "BOOLEAN" for name in ("background", "skin", "nose", "eye_g", "r_eye", "l_eye",
                    "r_brow", "l_brow", "r_ear", "l_ear", "mouth", "u_lip", "l_lip", "hair", "hat",
                    "ear_r", "neck_l", "neck", "cloth")}}, ["MASK"]),
            "GrowMask": ({"mask": "MASK", "expand": "INT", "tapered_corners": "BOOLEAN"}, ["MASK"]),
            "ThresholdMask": ({"mask": "MASK", "value": "FLOAT"}, ["MASK"]),
            "InvertMask": ({"mask": "MASK"}, ["MASK"]),
            "MaskComposite": ({"destination": "MASK", "source": "MASK", "x": "INT", "y": "INT",
                               "operation": "STRING"}, ["MASK"]),
            "MaskToImage": ({"mask": "MASK"}, ["IMAGE"]),
            "SaveImage": ({"images": "IMAGE", "filename_prefix": "STRING"}, ["IMAGE"]),
        }
        graph, saves = build_mask_graph("snapshot.png", "stable-job")
        for node in graph.values():
            types, _ = schemas[node["class_type"]]
            self.assertEqual(set(node["inputs"]), set(types))
            for field, value in node["inputs"].items():
                if isinstance(value, list):
                    self.assertEqual(len(value), 2)
                    _, outputs = schemas[graph[value[0]]["class_type"]]
                    self.assertEqual(outputs[value[1]], types[field])
        self.assertEqual(saves, {"protect": "protect", "core": "core", "edit": "edit", "labels": "labels", "matte": "matte_save"})
        json.dumps(graph)

    def test_explicit_protection_and_region_never_inherit_clothing_default(self):
        for region, enabled in (("background", {"background"}), ("clothing", {"cloth"})):
            graph, _ = build_mask_graph("snapshot.png", "stable-job", region)
            self.assertEqual(graph["parser_model"]["inputs"], {"device": "cpu"})
            protection = graph["protect_regions"]["inputs"]
            requested = graph["region"]["inputs"]
            self.assertEqual(protection["result"], ["parse", 1])
            self.assertEqual({key for key, value in protection.items() if value is True},
                             set(PARSER_FLAG_TO_LABEL_ID) - {"background", "cloth"})
            self.assertEqual({key for key, value in requested.items() if value is True}, enabled)
            self.assertTrue(protection["skin"])
            self.assertTrue(protection["hair"])
            self.assertFalse(protection["cloth"])

    def test_edit_excludes_grown_protection_and_saves_no_resize(self):
        graph, _ = build_mask_graph("snapshot.png", "stable-job")
        self.assertEqual(graph["protect_grow"]["inputs"]["expand"], GUARD_PIXELS)
        self.assertEqual(graph["core_shrink"]["inputs"]["expand"], -CORE_SHRINK_PIXELS)
        self.assertGreater(CORE_SHRINK_PIXELS, 0)
        self.assertGreater(GUARD_PIXELS, 0)
        self.assertLessEqual(GUARD_PIXELS, 8)
        self.assertEqual(graph["edit_exclusion"]["inputs"]["mask"], ["protect_binary", 0])
        self.assertEqual(graph["edit_region"]["inputs"], {
            "destination": ["region", 0], "source": ["edit_exclusion", 0],
            "x": 0, "y": 0, "operation": "multiply"})
        self.assertEqual(graph["protect_image"]["inputs"]["mask"], ["protect_binary", 0])
        self.assertEqual(graph["core_image"]["inputs"]["mask"], ["core_binary", 0])
        self.assertEqual(graph["matte_model"]["inputs"], {"bg_removal_name": "birefnet.safetensors"})
        self.assertEqual(graph["matte"]["inputs"], {"bg_removal_model": ["matte_model", 0], "image": ["source", 0]})
        self.assertEqual(graph["matte_save"]["inputs"]["images"], ["matte_image", 0])
        self.assertEqual(graph["labels"]["inputs"]["images"], ["parse", 0])
        self.assertFalse(any("Scale" in node["class_type"] or "Resize" in node["class_type"]
                             for node in graph.values()))

    def test_outputs_are_bound_to_safe_job_id(self):
        graph, _ = build_mask_graph("jobs\\source.png", "job_123")
        self.assertEqual(graph["source"]["inputs"]["image"], "jobs/source.png")
        for name in ("protect", "core", "edit", "labels"):
            self.assertEqual(graph[name]["inputs"]["filename_prefix"],
                             f"ByrdHouse/source-masks-job_123-{name}")
        self.assertEqual(graph["matte_save"]["inputs"]["filename_prefix"],
                         "ByrdHouse/source-masks-job_123-matte")
        for job in ("", "../escape", "job/other", "job%date%", "a" * 65, None):
            with self.subTest(job=job), self.assertRaises(MaskError):
                build_mask_graph("source.png", job)

    def test_illustrated_character_mask_uses_existing_parser_and_tight_blur(self):
        graph, saves = build_mask_graph('anchor.png', 'anime-job', illustrated=True)
        self.assertEqual(saves['character'], 'character_save')
        selected = graph['character_regions']['inputs']
        self.assertFalse(selected['background'])
        self.assertTrue(selected['hair'])
        self.assertTrue(selected['hat'])
        self.assertTrue(selected['cloth'])
        self.assertEqual(graph['character_shrink']['inputs']['expand'], -4)
        self.assertEqual(graph['character_blur']['class_type'], 'ImpactGaussianBlurMask')
        self.assertEqual(graph['character_blur']['inputs']['kernel_size'], 3)

    def test_unsafe_inputs_and_unknown_regions_fail_before_submission(self):
        for name in ("", "../escape.png", "x/../../escape.png", "C:\\source.png", "/tmp/source.png",
                     "\\\\server\\source.png", "source\n.png", " source.png", None):
            with self.subTest(name=name), self.assertRaises(MaskError):
                build_mask_graph(name, "job")
        for region in ("face", ["background"], None):
            with self.subTest(region=region), self.assertRaises(MaskError):
                build_mask_graph("source.png", "job", region)


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        self.protect = self.root / "protect.png"
        self.edit = self.root / "edit.png"
        self.labels = self.root / "labels.png"
        Image.new("RGB", (12, 10), (76, 50, 35)).save(self.source)
        self.p = np.zeros((10, 12), dtype=np.uint8)
        self.p[2:6, 3:8] = 255
        self.e = np.zeros_like(self.p)
        self.e[:, :2] = 255
        self.save_masks()
        Image.new("RGB", (12, 10), (25, 140, 160)).save(self.labels)

    def save_masks(self):
        Image.fromarray(self.p).save(self.protect)
        Image.fromarray(self.e).save(self.edit)

    def inspect(self, **kwargs):
        return inspect_masks(self.source, self.protect, self.edit, **kwargs)

    def test_valid_outputs_have_counts_hashes_and_review_limit(self):
        expected = hashlib.sha256(self.source.read_bytes()).hexdigest()
        report = self.inspect(labels_path=self.labels, expected_source_sha256=expected)
        self.assertEqual(report["canvas"], {"width": 12, "height": 10})
        self.assertEqual(report["protect"]["selected_pixels"], 20)
        self.assertEqual(report["edit"]["selected_pixels"], 20)
        self.assertEqual(report["source_sha256"], expected)
        self.assertEqual(report["protect_sha256"], hashlib.sha256(self.protect.read_bytes()).hexdigest())
        self.assertEqual(report["overlap_pixels"], 0)
        self.assertTrue(all(report["validation"].values()))
        self.assertTrue(report["review_required"])
        self.assertFalse(report["coverage_verified"])
        self.assertFalse(report["exact_replica"])
        self.assertIsNone(report["per_class_counts"])
        self.assertIn("thin curls", report["coverage_limit"])
        self.assertEqual(report["label_id_to_name"]["4"], "l_eye")
        self.assertEqual(report["parser_flag_to_label_id"]["r_eye"], 4)
        self.assertEqual(LABEL_ID_TO_NAME[13], "hair")
        json.dumps(report)

    def test_clothing_region_has_correct_mapping(self):
        report = self.inspect(region="clothing")
        self.assertEqual(report["edit_label_ids"], [18])
        self.assertEqual(report["protection_label_ids"], list(range(1, 18)))

    def test_dimension_mismatch_is_rejected_without_resizing(self):
        Image.new("L", (13, 10), 255).save(self.edit)
        with self.assertRaisesRegex(MaskError, "dimensions differ"):
            self.inspect()

    def test_nonbinary_and_colored_masks_are_rejected(self):
        self.e[0, 0] = 128
        self.save_masks()
        with self.assertRaisesRegex(MaskError, "not binary"):
            self.inspect()
        Image.new("RGB", (12, 10), (255, 0, 0)).save(self.edit)
        with self.assertRaisesRegex(MaskError, "grayscale"):
            self.inspect()

    def test_overlap_rejected_even_when_only_one_pixel(self):
        self.e[2, 3] = 255
        self.save_masks()
        with self.assertRaisesRegex(MaskError, "overlaps protection at 1 pixels"):
            self.inspect()

    def test_empty_masks_are_rejected(self):
        for mask_path in (self.protect, self.edit):
            self.save_masks()
            Image.new("L", (12, 10), 0).save(mask_path)
            with self.subTest(mask=mask_path.name), self.assertRaisesRegex(MaskError, "empty"):
                self.inspect()

    def test_changed_source_is_rejected(self):
        expected = hashlib.sha256(self.source.read_bytes()).hexdigest()
        Image.new("RGB", (12, 10), (80, 51, 34)).save(self.source)
        with self.assertRaisesRegex(MaskError, "source changed"):
            self.inspect(expected_source_sha256=expected)

    def test_preview_dimensions_and_transparency_are_rejected(self):
        Image.new("RGB", (11, 10), (25, 140, 160)).save(self.labels)
        with self.assertRaisesRegex(MaskError, "Labels preview/source dimensions differ"):
            self.inspect(labels_path=self.labels)
        Image.new("RGBA", (12, 10), (255, 255, 255, 0)).save(self.edit)
        with self.assertRaisesRegex(MaskError, "opaque"):
            self.inspect()

    def test_lossy_masks_are_rejected(self):
        lossy = self.root / "edit.jpg"
        Image.fromarray(self.e).save(lossy)
        with self.assertRaisesRegex(MaskError, "lossless PNG"):
            inspect_masks(self.source, self.protect, lossy)

    def test_palette_transparency_is_not_silently_flattened(self):
        image = Image.fromarray(self.e).convert("P")
        image.save(self.edit, transparency=0)
        with self.assertRaisesRegex(MaskError, "opaque"):
            self.inspect()

    def test_exif_orientation_is_applied_for_native_canvas_inspection(self):
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (10, 12), (76, 50, 35)).save(self.source, exif=exif)
        report = self.inspect()
        self.assertEqual(report["canvas"], {"width": 12, "height": 10})
        self.assertEqual(report["source"]["file_width"], 10)
        self.assertEqual(report["source"]["exif_orientation"], 6)


if __name__ == "__main__":
    unittest.main()
