"""Matching-view review must preserve approved provenance and require humans."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from anime_view_review import review, SHEET_VIEWS


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MatchingViewReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        view_dir = self.root / 'views-v2'
        view_dir.mkdir()
        sheet = self.root / 'sheet.png'
        sheet.write_bytes(b'approved sheet')
        self.target = self.root / 'new-frame.png'
        self.target.write_bytes(b'candidate frame')
        self.entries = []
        for view in SHEET_VIEWS:
            path = view_dir / (view + '.png')
            path.write_bytes(('approved ' + view).encode())
            self.entries.append({'view': view, 'path': str(path), 'sha256': digest(path)})
        (self.root / 'turnaround-v1.json').write_text(json.dumps({
            'schema': 'byrdhouse.carey-anime.turnaround.v1',
            'wardrobe_status': 'placeholder_not_approved',
            'assets': {'head_sheet': {'path': str(sheet), 'sha256': digest(sheet)},
                       'approved_closeup_anchor': {
                           'path': str(self.target), 'sha256': digest(self.target)}}}))
        (view_dir / 'manifest-v2.json').write_text(json.dumps({
            'source': str(sheet), 'source_sha256': digest(sheet),
            'views': self.entries}))

    def tearDown(self):
        self.temp.cleanup()

    def test_profile_compares_with_approved_profile_and_never_approves(self):
        calls = []

        class Face:
            def __init__(self, path): self.path = path
            def public(self): return {'file': str(self.path)}

        class Belt:
            def inspect(self, path, *, illustrated):
                calls.append(Path(path))
                assert illustrated
                return Face(path)
            def _similarity(self, reference, candidate): return 0.93
            def _geometry(self, reference, candidate, *, illustrated):
                return {'review_scope': 'same_view_illustrated_continuity'}

        report = review(self.target, 'facing-right', self.root, belt=Belt())
        self.assertEqual(calls, [Path(self.entries[1]['path']), self.target])
        self.assertEqual(report['matching_view_similarity_review_cue'], 0.93)
        self.assertFalse(report['automatic_approval'])
        self.assertTrue(report['human_review_required'])
        self.assertEqual(report['wardrobe_scope'], 'excluded; existing outfits are placeholders')

    def test_back_has_no_face_score(self):
        report = review(self.target, 'back', self.root, belt=object())
        self.assertNotIn('matching_view_similarity_review_cue', report)
        self.assertEqual(report['status'], 'visual_review_only_no_face_in_approved_rear_view')

    def test_three_quarter_uses_approved_closeup_anchor(self):
        class Face:
            def public(self): return {}
        class Belt:
            def inspect(self, path, *, illustrated):
                self_test.assertEqual(path, self_test.target)
                return Face()
            def _similarity(self, reference, candidate): return 1.0
            def _geometry(self, reference, candidate, *, illustrated): return {}
        self_test = self
        report = review(self.target, 'three-quarter', self.root, belt=Belt())
        self.assertEqual(report['approved_reference']['source_kind'], 'approved_closeup_anchor')
        self.assertFalse(report['automatic_approval'])

    def test_changed_approved_crop_fails_closed(self):
        Path(self.entries[3]['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            review(self.target, 'facing-left', self.root, belt=object())

    def test_changed_approved_sheet_fails_closed(self):
        (self.root / 'sheet.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            review(self.target, 'front', self.root, belt=object())


if __name__ == '__main__':
    unittest.main()
