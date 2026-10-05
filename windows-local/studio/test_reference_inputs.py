"""Snapshot provenance, normalization, and immutability tests without a GPU."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageOps

from reference_inputs import ReferenceInputError, reverify_reference, stage_reference


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ReferenceInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.photos = self.root/'photos'
        self.references = self.root/'references'
        self.photos.mkdir()
        self.references.mkdir()
        self.original = self.photos/'original.png'
        self.crop = self.references/'crop.png'
        Image.new('RGB', (18, 24), (70, 45, 20)).save(self.original)
        Image.new('RGB', (8, 6), (80, 50, 25)).save(self.crop)
        self.row = {
            'id': 'portrait', 'file': 'crop.png', 'source': str(self.original),
            'source_sha256': sha(self.original.read_bytes()), 'generated': False,
            'comfy_image': 'ByrdHouse/carey/mutable-alias.png',
        }
        self.config = {'photo_dir': str(self.photos), 'reference_dir': str(self.references),
                       'comfy_dir': str(self.root/'comfy')}
        self.job_id = 'a'*32

    def stage(self, use_original=False, **kwargs):
        return stage_reference(self.config, kwargs.get('row', self.row),
                               kwargs.get('job_id', self.job_id), use_original)

    def test_crop_hash_is_independent_of_original_manifest_hash(self):
        snapshot = self.stage()
        self.assertEqual(snapshot['source_kind'], 'reference_file')
        self.assertEqual(snapshot['source'], str(self.crop.resolve()))
        self.assertEqual(snapshot['source_sha256'], sha(self.crop.read_bytes()))
        self.assertNotEqual(snapshot['source_sha256'], self.row['source_sha256'])
        self.assertEqual(snapshot['manifest_original_source_sha256'], self.row['source_sha256'])
        self.assertEqual((snapshot['width'], snapshot['height']), (8, 6))
        self.assertEqual(snapshot['comfy_image'], f'ByrdHouse/references/{self.job_id}/reference.png')
        self.assertNotEqual(snapshot['comfy_image'], self.row['comfy_image'])
        self.assertTrue(snapshot['purpose'])
        self.assertEqual(reverify_reference(self.config, snapshot, self.job_id), snapshot)

    def test_original_mode_stages_full_original_and_checks_its_hash(self):
        snapshot = self.stage(use_original=True)
        self.assertEqual(snapshot['source_kind'], 'original_photo')
        self.assertEqual(snapshot['source_sha256'], self.row['source_sha256'])
        self.assertEqual(snapshot['source'], str(self.original.resolve()))
        self.assertEqual((snapshot['width'], snapshot['height']), (18, 24))
        with Image.open(self.original) as photo:
            expected_pixels = ImageOps.exif_transpose(photo).convert('RGB').tobytes()
        self.assertEqual(snapshot['rgb_pixel_sha256'], sha(expected_pixels))
        self.assertEqual(snapshot['staged_png_sha256'], sha(Path(snapshot['staged_path']).read_bytes()))

    def test_original_mode_refuses_missing_or_stale_manifest_hash(self):
        for row in ({**self.row, 'source_sha256': '0'*64},
                    {key: value for key, value in self.row.items() if key != 'source_sha256'}):
            with self.subTest(row=row):
                with self.assertRaises(ReferenceInputError):
                    self.stage(use_original=True, row=row)
        self.assertFalse((self.root/'comfy/input/ByrdHouse/references'/self.job_id).exists())

    def test_original_mode_refuses_generated_reference(self):
        with self.assertRaisesRegex(ReferenceInputError, 'original photograph'):
            self.stage(use_original=True, row={**self.row, 'generated': True})

    def test_orientation_normalization_preserves_dimensions_and_rgb_pixels(self):
        photo = Image.new('RGB', (2, 3))
        photo.putdata([(10, 20, 30), (40, 50, 60), (70, 80, 90),
                       (100, 110, 120), (130, 140, 150), (160, 170, 180)])
        exif = photo.getexif()
        exif[274] = 6
        photo.save(self.crop, exif=exif)
        with Image.open(self.crop) as saved:
            expected = ImageOps.exif_transpose(saved).convert('RGB')
        snapshot = self.stage()
        self.assertEqual((snapshot['width'], snapshot['height']), (3, 2))
        with Image.open(snapshot['staged_path']) as staged:
            self.assertEqual(staged.mode, 'RGB')
            self.assertEqual(staged.tobytes(), expected.tobytes())
            self.assertNotIn(274, staged.getexif())
        self.assertEqual(snapshot['rgb_pixel_sha256'], sha(expected.tobytes()))

    def test_reuse_never_changes_snapshot_when_reference_or_comfy_alias_changes(self):
        snapshot = self.stage()
        staged = Path(snapshot['staged_path'])
        before = (staged.read_bytes(), staged.stat().st_mtime_ns,
                  Path(snapshot['metadata_path']).read_bytes())
        Image.new('RGB', (10, 12), (255, 0, 0)).save(self.crop)
        alias = self.root/'comfy/input'/self.row['comfy_image']
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.write_bytes(b'mutable alias changed')
        self.row['comfy_image'] = '../different-alias.png'
        self.assertEqual(self.stage(), snapshot)
        self.assertEqual((staged.read_bytes(), staged.stat().st_mtime_ns,
                          Path(snapshot['metadata_path']).read_bytes()), before)

    def test_existing_original_snapshot_survives_mutation_of_original_alias(self):
        snapshot = self.stage(use_original=True)
        before = Path(snapshot['staged_path']).read_bytes()
        Image.new('RGB', (20, 20), (255, 255, 255)).save(self.original)
        self.assertNotEqual(sha(self.original.read_bytes()), snapshot['source_sha256'])
        self.assertEqual(self.stage(use_original=True), snapshot)
        self.assertEqual(Path(snapshot['staged_path']).read_bytes(), before)

    def test_reverify_does_not_consult_removed_source_or_manifest(self):
        snapshot = self.stage(use_original=True)
        self.original.unlink()
        self.row.clear()
        self.assertEqual(reverify_reference(self.config, snapshot), snapshot)

    def test_conflicting_binding_cannot_overwrite_an_existing_job(self):
        snapshot = self.stage()
        before = Path(snapshot['staged_path']).read_bytes()
        Image.new('RGB', (8, 8), (0, 0, 255)).save(self.references/'another.png')
        rows = [{**self.row, 'file': 'another.png'}, {**self.row, 'id': 'another-id'},
                {**self.row, 'source_sha256': '0'*64}]
        for row in rows:
            with self.subTest(row=row):
                with self.assertRaisesRegex(ReferenceInputError, 'different reference snapshot'):
                    self.stage(row=row)
        with self.assertRaisesRegex(ReferenceInputError, 'different reference snapshot'):
            self.stage(use_original=True)
        self.assertEqual(Path(snapshot['staged_path']).read_bytes(), before)

    def test_reverify_rejects_png_and_metadata_tampering(self):
        snapshot = self.stage()
        staged = Path(snapshot['staged_path'])
        original_png = staged.read_bytes()
        staged.write_bytes(original_png+b'changed')
        with self.assertRaisesRegex(ReferenceInputError, 'PNG changed'):
            reverify_reference(self.config, snapshot)
        staged.write_bytes(original_png)
        metadata = Path(snapshot['metadata_path'])
        saved = json.loads(metadata.read_text())
        metadata.write_text(json.dumps({**saved, 'width': 999}))
        with self.assertRaisesRegex(ReferenceInputError, 'metadata changed'):
            reverify_reference(self.config, snapshot)

    def test_reverify_rejects_wrong_paths_job_and_pixel_provenance(self):
        snapshot = self.stage()
        with self.assertRaisesRegex(ReferenceInputError, 'another job'):
            reverify_reference(self.config, snapshot, 'b'*32)
        for key, value in [('staged_path', str(self.root/'outside.png')),
                           ('metadata_path', str(self.root/'outside.json')),
                           ('comfy_image', '../outside.png'), ('rgb_pixel_sha256', '0'*64),
                           ('source', str(self.root/'outside-source.png'))]:
            with self.subTest(key=key):
                altered = {**snapshot, key: value}
                if key == 'rgb_pixel_sha256':
                    # A coordinated changed card still cannot invent the PNG's decoded pixels.
                    Path(snapshot['metadata_path']).write_text(json.dumps(altered))
                with self.assertRaises(ReferenceInputError):
                    reverify_reference(self.config, altered)

    def test_input_directory_override_is_used(self):
        self.config['comfy_input_dir'] = str(self.root/'configured-input')
        snapshot = self.stage()
        self.assertTrue(Path(snapshot['staged_path']).is_relative_to(self.root/'configured-input'))
        self.assertFalse((self.root/'comfy/input').exists())

    def test_source_paths_cannot_escape_allowed_roots(self):
        outside = self.root/'outside.png'
        Image.new('RGB', (4, 4)).save(outside)
        for use_original, row in [
                (False, {**self.row, 'file': '../outside.png'}),
                (False, {**self.row, 'file': str(outside)}),
                (True, {**self.row, 'source': '../outside.png'}),
                (True, {**self.row, 'source': str(outside)})]:
            with self.subTest(original=use_original, row=row):
                with self.assertRaisesRegex(ReferenceInputError, 'outside'):
                    self.stage(use_original=use_original, row=row)

    def test_job_and_mode_validation_precedes_any_snapshot_creation(self):
        for job_id in ('../outside', 'A'*32, 'g'*32, 123, None):
            with self.subTest(job_id=job_id):
                with self.assertRaises(ReferenceInputError):
                    self.stage(job_id=job_id)
        with self.assertRaises(ReferenceInputError):
            self.stage(use_original='yes')
        self.assertFalse((self.root/'comfy/input').exists())

    def test_simultaneous_create_once_publishes_one_complete_bundle(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.stage(), range(8)))
        self.assertTrue(all(snapshot == results[0] for snapshot in results))
        directory = Path(results[0]['staged_path']).parent
        self.assertEqual({path.name for path in directory.iterdir()},
                         {'reference.png', 'reference.png.json'})
        self.assertEqual(list(directory.parent.glob(f'.{self.job_id}-*')), [])
        self.assertEqual(reverify_reference(self.config, results[0]), results[0])

    def test_failed_prepublication_write_leaves_no_partial_job_or_staging_directory(self):
        original_write = Path.write_text
        def failed_write(path, *args, **kwargs):
            if path.name == 'reference.png.json':
                raise OSError('Interrupted metadata write')
            return original_write(path, *args, **kwargs)
        with patch.object(Path, 'write_text', failed_write):
            with self.assertRaisesRegex(OSError, 'Interrupted metadata write'):
                self.stage()
        namespace = self.root/'comfy/input/ByrdHouse/references'
        self.assertFalse((namespace/self.job_id).exists())
        self.assertEqual(list(namespace.glob(f'.{self.job_id}-*')), [])

    def test_dimensions_and_ids_are_typed_provenance(self):
        snapshot = self.stage()
        for key, value in [('width', True), ('height', 0), ('reference_id', None),
                           ('manifest_original_source_sha256', 'invalid')]:
            with self.subTest(key=key):
                altered = {**snapshot, key: value}
                Path(snapshot['metadata_path']).write_text(json.dumps(altered))
                with self.assertRaises(ReferenceInputError):
                    reverify_reference(self.config, altered)


if __name__ == '__main__':
    unittest.main()
