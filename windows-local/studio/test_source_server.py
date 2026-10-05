"""Source-preservation server gates and frozen references; no GPU requests."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from PIL import Image

from reference_inputs import reverify_reference
from server import Studio, ValidationError, build_graph, handler_class
from source_masks import inspect_masks
from source_preserve import work_dir


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FakeComfy:
    """Model discovery and a completed ordinary-still mock, never real rendering."""
    def __init__(self):
        self.calls = []
        self.graph = None
        self.on_post = None
        self.model_choices = {
            'checkpoints': ['base.safetensors', 'RealVisXL_V5.0_Lightning_fp16.safetensors'],
            'loras': ['lightning.safetensors', 'ip-adapter-faceid-plusv2_sdxl_lora.safetensors'],
            'ipadapter': ['faceid.bin'], 'clip_vision': ['vision.safetensors'],
            'nodes': ['IPAdapterFaceID', 'IPAdapterUnifiedLoaderFaceID',
                      'FaceParse(FaceParsing)', 'FaceParsingModelLoaderNew',
                      'FaceParsingProcessorLoader(FaceParsing)',
                      'FaceParsingResultsParser(FaceParsing)',
                      'ImageCompositeMasked', 'VAEEncodeForInpaint',
                      'LoadBackgroundRemovalModel', 'RemoveBackground'],
        }
        output = io.BytesIO()
        Image.new('RGB', (16, 16), (70, 45, 25)).save(output, format='PNG')
        self.png = output.getvalue()

    def models(self):
        return copy.deepcopy(self.model_choices)

    def request(self, endpoint, payload=None, binary=False):
        self.calls.append((endpoint, payload, binary))
        if endpoint == '/prompt':
            self.graph = copy.deepcopy(payload['prompt'])
            if self.on_post:
                self.on_post(self.graph)
            return {'prompt_id': 'ordinary-frozen-reference-prompt'}
        if endpoint.startswith('/history/'):
            return {'ordinary-frozen-reference-prompt': {
                'status': {'completed': True, 'status_str': 'success'},
                'prompt': [0, 'ordinary-frozen-reference-prompt', self.graph, {}, ['9']],
                'outputs': {'9': {'images': [{
                    'filename': 'still.png', 'subfolder': '', 'type': 'output'}]}}}}
        if endpoint.startswith('/view?'):
            return self.png
        raise AssertionError('Unexpected mocked Comfy request: '+endpoint)

    def posts(self):
        return [call for call in self.calls if call[0] == '/prompt']


class SourceServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.photos = self.root/'photos'
        self.references = self.root/'references'
        self.photos.mkdir()
        self.references.mkdir()
        self.original = self.photos/'original.png'
        self.reference_file = self.references/'portrait-crop.png'
        Image.new('RGB', (16, 16), (90, 55, 25)).save(self.original)
        Image.new('RGB', (8, 8), (100, 60, 30)).save(self.reference_file)
        self.row = {'id': 'portrait', 'label': 'Original portrait', 'file': self.reference_file.name,
                    'source': str(self.original), 'source_sha256': sha(self.original),
                    'comfy_image': 'ByrdHouse/carey/mutable.png', 'generated': False}
        self.config = {
            'comfy_url': 'http://127.0.0.1:8188', 'comfy_dir': str(self.root/'comfy'),
            'comfy_input_dir': str(self.root/'configured-input'),
            'output_dir': str(self.root/'media/images'), 'photo_dir': str(self.photos),
            'reference_dir': str(self.references), 'checkpoint': 'base.safetensors',
            'fast_checkpoint': 'RealVisXL_V5.0_Lightning_fp16.safetensors',
            'lightning_lora': 'lightning.safetensors', 'identity_lora': '',
            'identity_lora_strength': 0.0, 'identity_mode': 'reference',
            'default_reference': 'portrait', 'default_mode': 'fast',
            'ipadapter_model': 'faceid.bin', 'clip_vision_model': 'vision.safetensors',
        }
        self.client = FakeComfy()
        self.studio = Studio(self.config, self.root, self.client, start_worker=False)
        self.studio.references = {'portrait': copy.deepcopy(self.row)}
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.studio.close)

    def mask_job(self, region='background'):
        return self.studio.create_source_mask({'reference': 'portrait', 'region': region})

    def approved_mask(self, region='background', state='approved'):
        """Materialize real binary PNGs and metadata in the expected parent bundle."""
        job = self.mask_job(region)
        directory = work_dir(self.config, job['id'])
        directory.mkdir(parents=True)
        protect = Image.new('L', (16, 16), 0)
        protect.paste(255, (2, 2, 8, 8))
        edit = Image.new('L', (16, 16), 0)
        edit.paste(255, (9, 9, 16, 16))
        protect.save(directory/'protect.png')
        core = Image.new('L', (16, 16), 0)
        core.paste(255, (3, 3, 7, 7))
        core.save(directory/'core.png')
        edit.save(directory/'edit.png')
        Image.new('RGB', (16, 16), (50, 100, 150)).save(directory/'labels.png')
        matte = Image.new('L', (16, 16), 0)
        matte.paste(255, (1, 1, 12, 12))
        matte.save(directory/'matte.png')
        report = inspect_masks(job['reference_snapshot']['staged_path'],
            directory/'protect.png', directory/'edit.png', labels_path=directory/'labels.png',
            region=region, expected_source_sha256=job['reference_snapshot']['staged_png_sha256'])
        report['mask_hashes'] = {name: sha(directory/(name+'.png'))
                                for name in ('protect', 'core', 'edit', 'labels', 'matte')}
        poster = self.studio.output_dir/(job['id']+'_1.png')
        Image.new('RGB', (16, 16), (60, 90, 70)).save(poster)
        card = {'schema': 'byrdhouse.studio.image.v1', 'job_id': job['id'],
                'purpose': 'Review mocked semantic coverage before a scene edit',
                'identity_verified': False, 'exact_replica': False, 'review_state': 'needs_review',
                'settings': job, 'inspection': report,
                'file': poster.name}
        poster.with_suffix('.png.json').write_text(json.dumps(card), encoding='utf-8')
        with self.studio.db() as db:
            db.execute('UPDATE jobs SET state=?,outputs=? WHERE id=?',
                       ('needs_review', json.dumps([poster.name]), job['id']))
        if state in ('approved', 'rejected'):
            self.studio.review(job['id'], state)
        return self.studio.job(job['id']), directory

    def queued_edit(self, mask):
        return self.studio.create_source_edit({
            'mask_job_id': mask['id'], 'prompt': 'a quiet bookstore background', 'seed': 123})

    def test_source_mask_freezes_verified_original_and_queues_before_rendering(self):
        earlier = self.studio.create_job({'prompt': 'earlier ordinary still'})
        job = self.mask_job()
        self.assertEqual(job['state'], 'queued')
        self.assertEqual(job['operation'], 'source_mask')
        self.assertEqual(job['region'], 'background')
        snapshot = job['reference_snapshot']
        self.assertEqual(snapshot['source_kind'], 'original_photo')
        self.assertEqual(snapshot['source_sha256'], self.row['source_sha256'])
        self.assertEqual(snapshot['source'], str(self.original.resolve()))
        self.assertEqual((snapshot['width'], snapshot['height']), (16, 16))
        self.assertNotEqual(snapshot['source_sha256'], sha(self.reference_file))
        self.assertTrue(Path(snapshot['staged_path']).is_relative_to(Path(self.config['comfy_input_dir'])))
        self.assertEqual(self.studio.job(earlier['id'])['state'], 'queued')
        self.assertEqual(self.client.calls, [])
        with self.studio.db() as db:
            order = [row[0] for row in db.execute('SELECT id FROM jobs ORDER BY rowid')]
        self.assertEqual(order, [earlier['id'], job['id']])

    def test_source_mask_refuses_stale_original_hash_without_queueing(self):
        self.studio.references['portrait']['source_sha256'] = '0'*64
        with self.assertRaisesRegex(ValidationError, 'manifest hash is stale'):
            self.mask_job()
        self.assertEqual(self.studio.jobs(), [])
        self.assertFalse(self.client.posts())

    def test_source_mask_refuses_generated_reference_without_queueing(self):
        self.studio.references['portrait']['generated'] = True
        with self.assertRaisesRegex(ValidationError, 'original photo or the locked Carey Anime Canon Anchor'):
            self.mask_job()
        self.assertEqual(self.studio.jobs(), [])
        self.assertFalse(self.client.posts())

    def test_source_mask_refuses_nondivisible_native_dimensions_without_resizing(self):
        Image.new('RGB', (15, 16), (80, 50, 25)).save(self.original)
        self.studio.references['portrait']['source_sha256'] = sha(self.original)
        with self.assertRaisesRegex(ValidationError, 'divisible by 8'):
            self.mask_job()
        self.assertEqual(self.studio.jobs(), [])
        self.assertFalse(self.client.posts())
        # Staging must preserve the original size even for a refused preset.
        staged = list(Path(self.config['comfy_input_dir']).glob('ByrdHouse/references/*/reference.png'))
        self.assertEqual(len(staged), 1)
        with Image.open(staged[0]) as photo:
            self.assertEqual(photo.size, (15, 16))

    def test_source_mask_requires_installed_parser_nodes(self):
        self.client.model_choices['nodes'].remove('FaceParse(FaceParsing)')
        with self.assertRaisesRegex(ValidationError, 'unavailable'):
            self.mask_job()
        self.assertEqual(self.studio.jobs(), [])
        self.assertFalse(self.client.posts())

    def test_scene_edit_requires_reviewed_mask_including_correct_parent_operation(self):
        pending, _ = self.approved_mask(state='needs_review')
        for state in ('needs_review', 'rejected'):
            with self.subTest(state=state):
                with self.studio.db() as db:
                    db.execute('UPDATE jobs SET state=? WHERE id=?', (state, pending['id']))
                with self.assertRaisesRegex(ValidationError, 'accept the protection mask'):
                    self.queued_edit(pending)
        ordinary = self.studio.create_job({'prompt': 'ordinary still'})
        with self.studio.db() as db:
            db.execute("UPDATE jobs SET state='approved' WHERE id=?", (ordinary['id'],))
        with self.assertRaisesRegex(ValidationError, 'accept the protection mask'):
            self.queued_edit(ordinary)
        self.assertFalse(any(job.get('operation') == 'source_preserve' for job in self.studio.jobs()))
        self.assertFalse(self.client.posts())

    def test_approved_mask_queues_frozen_edit_with_real_masks_and_no_post(self):
        parent, directory = self.approved_mask(region='clothing')
        edit = self.queued_edit(parent)
        self.assertEqual(edit['state'], 'queued')
        self.assertEqual(edit['operation'], 'source_preserve')
        self.assertEqual(edit['region'], 'clothing')
        self.assertEqual(edit['mask_job_id'], parent['id'])
        self.assertEqual(edit['reference_snapshot'], parent['reference_snapshot'])
        self.assertEqual(Path(edit['edit_mask_path']).read_bytes(), (directory/'edit.png').read_bytes())
        self.assertEqual(edit['mask_hashes']['edit'], sha(edit['edit_mask_path']))
        self.assertEqual(edit['checkpoint'], self.config['fast_checkpoint'])
        self.assertEqual(edit['steps'], 5)
        self.assertEqual(edit['mask_reviewed'], self.studio.metadata(parent['id'])['reviewed'])
        self.assertFalse(self.client.posts())

    def test_mask_mutation_fails_before_edit_enters_queue(self):
        parent, directory = self.approved_mask()
        before = len(self.studio.jobs())
        (directory/'edit.png').write_bytes((directory/'edit.png').read_bytes()+b'changed')
        with self.assertRaisesRegex(ValidationError, 'semantic mask changed'):
            self.queued_edit(parent)
        self.assertEqual(len(self.studio.jobs()), before)
        self.assertFalse(self.client.posts())

    def test_approved_db_state_requires_matching_reviewed_mask_sidecar(self):
        parent, _ = self.approved_mask()
        sidecar = self.studio.image_path(parent['id'], 0).with_suffix('.png.json')
        card = json.loads(sidecar.read_text())
        bad_cards = [{**card, 'review_state': 'needs_review'},
                     {key: value for key, value in card.items() if key != 'reviewed'},
                     {**card, 'reviewed': ''}]
        for bad_card in bad_cards:
            with self.subTest(card=bad_card):
                sidecar.write_text(json.dumps(bad_card))
                with self.assertRaises(ValidationError):
                    self.queued_edit(parent)
        self.assertEqual(len(self.studio.jobs()), 1)
        self.assertFalse(self.client.posts())

    def test_snapshot_mutation_fails_before_edit_enters_queue(self):
        parent, _ = self.approved_mask()
        staged = Path(parent['reference_snapshot']['staged_path'])
        staged.write_bytes(staged.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValidationError, 'PNG changed'):
            self.queued_edit(parent)
        self.assertEqual(len(self.studio.jobs()), 1)
        self.assertFalse(self.client.posts())

    def test_rejected_mask_after_edit_queueing_fails_worker_before_post(self):
        parent, _ = self.approved_mask()
        edit = self.queued_edit(parent)
        self.studio.review(parent['id'], 'rejected')
        self.assertTrue(self.studio.run_next())
        result = self.studio.job(edit['id'])
        self.assertEqual(result['state'], 'failed')
        self.assertIn('rejected after queueing', result['error'])
        self.assertIsNone(result['prompt_id'])
        self.assertFalse(self.client.posts())

    def test_an_approved_mask_review_sheet_cannot_be_animated(self):
        mask, _ = self.approved_mask()
        before = len(self.studio.jobs())
        with self.assertRaisesRegex(ValidationError, 'Keep the still'):
            self.studio.create_animation({'source_job_id': mask['id']})
        self.assertEqual(len(self.studio.jobs()), before)
        self.assertFalse(self.client.posts())

    def test_snapshot_helper_and_http_source_remain_bound_after_alias_change(self):
        job = self.mask_job()
        snapshot = job['reference_snapshot']
        expected = Path(snapshot['staged_path']).read_bytes()
        Image.new('RGB', (16, 16), (255, 255, 255)).save(self.original)
        Image.new('RGB', (8, 8), (0, 0, 0)).save(self.reference_file)
        self.studio.references['portrait']['file'] = 'removed-alias.png'
        self.studio.references['portrait']['comfy_image'] = 'different-mutable-alias.png'
        self.assertEqual(reverify_reference(self.config, snapshot), snapshot)
        self.assertEqual(self.studio.snapshot_path(job['id']).read_bytes(), expected)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_class(self.studio))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/api/jobs/{job["id"]}/source'
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get('Content-Type'), 'image/png')
                self.assertEqual(response.read(), expected)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)
        self.assertFalse(self.client.posts())

    def test_ordinary_make_spec_stages_independent_per_job_reference_inputs(self):
        first = self.studio.make_spec({'prompt': 'first ordinary still'})
        second = self.studio.make_spec({'prompt': 'second ordinary still'})
        self.assertNotEqual(first['id'], second['id'])
        self.assertNotEqual(first['reference_image'], second['reference_image'])
        for spec in (first, second):
            snapshot = spec['reference_snapshot']
            self.assertEqual(snapshot['source_kind'], 'reference_file')
            self.assertEqual(snapshot['source_sha256'], sha(self.reference_file))
            self.assertEqual(spec['reference_input_sha256'], snapshot['staged_png_sha256'])
            self.assertEqual(spec['reference_image'], snapshot['comfy_image'])
            self.assertEqual(build_graph(self.config, spec)['10']['inputs']['image'], snapshot['comfy_image'])
        self.assertFalse(self.client.posts())
        self.assertEqual(self.studio.jobs(), [])

    def test_ordinary_runtime_uses_frozen_input_after_mutable_alias_changes(self):
        job = self.studio.create_job({'prompt': 'ordinary frozen input'})
        snapshot = job['reference_snapshot']
        expected_png = Path(snapshot['staged_path']).read_bytes()
        Image.new('RGB', (8, 8), (255, 0, 0)).save(self.reference_file)
        self.studio.references['portrait']['file'] = 'another-file.png'
        self.studio.references['portrait']['comfy_image'] = 'another-alias.png'
        def submitted(graph):
            self.assertEqual(self.studio.job(job['id'])['state'], 'running')
            self.assertEqual(graph['10']['inputs']['image'], snapshot['comfy_image'])
            self.assertEqual(Path(snapshot['staged_path']).read_bytes(), expected_png)
        self.client.on_post = submitted
        self.assertTrue(self.studio.run_next())
        final = self.studio.job(job['id'])
        self.assertEqual(final['state'], 'needs_review')
        self.assertEqual(len(self.client.posts()), 1)
        self.assertEqual(self.studio.metadata(job['id'])['settings']['reference_snapshot'], snapshot)

    def test_ordinary_tampered_staged_input_fails_before_post(self):
        job = self.studio.create_job({'prompt': 'must retain frozen input'})
        staged = Path(job['reference_snapshot']['staged_path'])
        staged.write_bytes(staged.read_bytes()+b'changed')
        self.assertTrue(self.studio.run_next())
        final = self.studio.job(job['id'])
        self.assertEqual(final['state'], 'failed')
        self.assertIn('PNG changed', final['error'])
        self.assertIsNone(final['prompt_id'])
        self.assertFalse(self.client.posts())
        self.assertFalse((self.studio.submission_dir/(job['id']+'.json')).exists())

    def test_queued_source_mask_tampered_input_fails_before_post(self):
        job = self.mask_job()
        staged = Path(job['reference_snapshot']['staged_path'])
        staged.write_bytes(staged.read_bytes()+b'changed')
        self.assertTrue(self.studio.run_next())
        final = self.studio.job(job['id'])
        self.assertEqual(final['state'], 'failed')
        self.assertIn('PNG changed', final['error'])
        self.assertFalse(self.client.posts())


if __name__ == '__main__':
    unittest.main()
