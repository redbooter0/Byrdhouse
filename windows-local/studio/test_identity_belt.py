import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import torch

from identity_belt import FaceRecord, IdentityBelt


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.belt = IdentityBelt({'comfy_dir': self.tmp.name, 'output_dir': self.tmp.name}, None)

    def parse(self, image, box, eyes, *, illustrated=False):
        # Feed exact semantic labels through the real coordinate calculations.
        def processor(images, return_tensors):
            labels = torch.tensor(np.array(images)[:, :, 0].astype(np.int64))
            logits = torch.nn.functional.one_hot(labels, 19).permute(2, 0, 1)[None].float()
            return {'logits': logits}
        self.belt._face_parser = (lambda logits: SimpleNamespace(logits=logits), processor)
        return self.belt._parsing_metrics(image, box, eyes, cv2, illustrated=illustrated)

    def test_hair_skin_boundary_is_translation_invariant(self):
        image = np.zeros((250, 240, 3), np.uint8)
        image[15:60, 65:175] = 13
        image[60:170, 65:175] = 1
        box = np.array([80, 50, 160, 170], dtype=float)
        eyes = np.array([[100, 95], [140, 95]], dtype=float)
        a = self.parse(image, box, eyes)
        padded = cv2.copyMakeBorder(image, 160, 0, 80, 0, cv2.BORDER_CONSTANT)
        b = self.parse(padded, box + [80, 160, 80, 160], eyes + [80, 160])
        self.assertAlmostEqual(a['hairline_y_ratio'], 10 / 120, places=5)
        self.assertAlmostEqual(a['forehead_height_ratio'], 35 / 120, places=5)
        for key in ['hairline_y_ratio', 'forehead_height_ratio', 'hair_width_ratio']:
            self.assertAlmostEqual(a[key], b[key], places=5)
        self.assertEqual(a['hairline_points'][0][1], 60)
        self.assertEqual(b['hairline_points'][0][1], 220)

    def test_illustrated_afro_classed_as_hat_still_measures_as_hair_silhouette(self):
        # The upstream photo-trained parser often places a drawn afro in its
        # ``hat`` label.  The belt must report that truth and still measure the
        # visible hairline rather than silently calling the feature absent.
        image = np.zeros((250, 240, 3), np.uint8)
        image[15:60, 65:175] = 14
        image[60:170, 65:175] = 1
        metrics = self.parse(image, [80, 50, 160, 170], [[100, 95], [140, 95]], illustrated=True)
        self.assertEqual(metrics['hair_silhouette_mode'], 'hair_plus_hat_for_illustrated_review')
        self.assertEqual(metrics['hair_area_ratio'], 0.0)
        self.assertGreater(metrics['headwear_area_ratio'], 0.0)
        self.assertGreater(metrics['hair_silhouette_area_ratio'], 0.0)
        self.assertAlmostEqual(metrics['hairline_y_ratio'], 10 / 120, places=5)

    def test_real_hat_is_not_counted_as_hair(self):
        image = np.zeros((250, 240, 3), np.uint8)
        image[15:60, 65:175] = 14
        image[60:170, 65:175] = 1
        metrics = self.parse(image, [80, 50, 160, 170], [[100, 95], [140, 95]])
        self.assertEqual(metrics['hair_silhouette_mode'], 'literal_hair_only')
        self.assertEqual(metrics['hair_silhouette_area_ratio'], 0.0)
        self.assertIsNone(metrics['hairline_y_ratio'])

    def test_detached_eyebrow_mislabeled_as_hair_cannot_lower_hairline(self):
        image = np.zeros((250, 240, 3), np.uint8)
        image[15:60, 65:175] = 13
        image[60:170, 65:175] = 1
        image[80:88, 95:145] = 13
        metrics = self.parse(image, [80,50,160,170], [[100,95],[140,95]])
        self.assertEqual(metrics['hairline_y_pixels'], 60)
        self.assertTrue(all(y==60 for x,y in metrics['hairline_points']))
        self.assertEqual(metrics['hair_pixels_excluded'], 400)
        self.assertEqual(metrics['hair_components_excluded'], 1)
        self.assertGreater(metrics['raw_hair_silhouette_area_ratio'], metrics['hair_silhouette_area_ratio'])

    def test_connected_curved_hairline_retains_its_real_boundary(self):
        image = np.zeros((250,240,3), np.uint8)
        image[15:60,65:175] = 13
        image[60:170,65:175] = 1
        image[60:72,95:112] = 13
        metrics=self.parse(image,[80,50,160,170],[[100,95],[140,95]])
        self.assertIn(72, [y for x,y in metrics['hairline_points']])
        self.assertEqual(metrics['hair_pixels_excluded'],0)

    def test_brow_only_and_missing_eyes_do_not_invent_forehead_boundary(self):
        image = np.ones((250,240,3),np.uint8)
        image[80:88,95:145]=13
        metrics=self.parse(image,[80,50,160,170],[[100,95],[140,95]])
        self.assertIsNone(metrics['hairline_y_pixels'])
        self.assertEqual(metrics['hairline_coverage'],0)
        image[15:60,65:175]=13
        without_eyes=self.parse(image,[80,50,160,170],[])
        self.assertIsNone(without_eyes['forehead_height_ratio'])

    def test_unrelated_hair_component_outside_detected_forehead_is_excluded(self):
        image = np.zeros((250,240,3),np.uint8)
        image[15:60,65:175]=13
        image[60:170,65:175]=1
        image[:200,180:]=13
        metrics=self.parse(image,[80,50,160,170],[[100,95],[140,95]])
        self.assertEqual(metrics['hair_bounds_pixels'],[65,15,175,60])
        self.assertEqual(metrics['hairline_y_pixels'],60)

    def test_illustrated_same_view_thresholds_reject_hair_and_forehead_drift(self):
        base = {'face_aspect_ratio': 0.74, 'eye_distance_ratio': 0.52,
                'hairline_coverage': 1.0, 'forehead_height_ratio': 0.44,
                'hairline_y_ratio': -0.15, 'hair_width_ratio': 1.80,
                'hair_height_ratio': 1.28, 'landmark_confidence': 0.77,
                'face_outline_signature': [0.0, 0.0, 1.0, 1.0]}
        drifted = dict(base, forehead_height_ratio=0.59, hairline_y_ratio=0.09,
                       hair_width_ratio=2.11, hair_height_ratio=1.53,
                       face_outline_signature=[0.1, 0.0, 1.1, 1.0])
        a = FaceRecord(Path('canon'), 832, 1216, (0, 0, 1, 1), np.ones(2), base)
        b = FaceRecord(Path('candidate'), 832, 1216, (0, 0, 1, 1), np.ones(2), drifted)
        delta = self.belt._geometry(a, b, illustrated=True)
        self.assertEqual(delta['review_scope'], 'same_view_illustrated_continuity')
        self.assertFalse(delta['forehead_within_gate'])
        self.assertFalse(delta['hair_within_gate'])
        self.assertFalse(delta['outline_within_gate'])

    def test_missing_hair_and_outline_fail_review_checks(self):
        metrics = self.parse(np.ones((200, 200, 3), np.uint8), [60, 50, 140, 170], [[80, 90], [120, 90]])
        self.assertIsNone(metrics['hairline_y_ratio'])
        self.assertIsNone(metrics['forehead_height_ratio'])
        metrics['forehead_ratio'] = 0.4
        record = FaceRecord(Path('test'), 200, 200, (60, 50, 140, 170), np.ones(2), metrics)
        result = self.belt._geometry(record, record)
        self.assertFalse(result['forehead_within_gate'])
        self.assertFalse(result['hair_within_gate'])
        self.assertFalse(result['outline_within_gate'])

    def test_padded_detection_maps_keypoints_back_before_parsing(self):
        path = Path(self.tmp.name) / 'source.png'
        cv2.imwrite(str(path), np.zeros((100, 100, 3), np.uint8))
        points = np.array([[20, 30], [60, 30], [40, 45], [30, 60], [50, 60]], dtype=float)
        face = SimpleNamespace(bbox=np.array([10, 10, 80, 85]) + 64,
                               kps=points + 64, normed_embedding=np.ones(2), det_score=0.9)
        self.belt._examiner = (SimpleNamespace(get=Mock(side_effect=[[], [face]])), cv2, None)
        self.belt._landmark_metrics = Mock(return_value={})
        self.belt._parsing_metrics = Mock(return_value={})
        self.belt.inspect(path)
        np.testing.assert_array_equal(self.belt._parsing_metrics.call_args.args[2], points)

    def test_inspection_cache_reuses_exact_anchor_and_reexamines_changed_file(self):
        path = Path(self.tmp.name) / 'anchor.png'
        cv2.imwrite(str(path), np.zeros((100, 100, 3), np.uint8))
        face = SimpleNamespace(bbox=np.array([10, 10, 80, 85]),
                               kps=np.array([[20, 30], [60, 30], [40, 45],
                                             [30, 60], [50, 60]], dtype=float),
                               normed_embedding=np.ones(2), det_score=0.9)
        examiner = SimpleNamespace(get=Mock(return_value=[face]))
        self.belt._examiner = (examiner, cv2, None)
        self.belt._landmark_metrics = Mock(return_value={})
        self.belt._parsing_metrics = Mock(return_value={})
        first = self.belt.inspect(path, illustrated=True)
        self.assertIs(first, self.belt.inspect(path, illustrated=True))
        self.assertEqual(examiner.get.call_count, 1)
        self.belt.inspect(path, illustrated=False)
        self.assertEqual(examiner.get.call_count, 2)
        cv2.imwrite(str(path), np.full((100, 100, 3), 128, np.uint8))
        self.belt.inspect(path, illustrated=True)
        self.assertEqual(examiner.get.call_count, 3)


if __name__ == '__main__':
    unittest.main()
