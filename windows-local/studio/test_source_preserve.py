"""Saved-pixel and durable source-edit contracts, with PNG fixtures and mock ComfyUI."""
import copy
import hashlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np
from PIL import Image

from reference_inputs import stage_reference
from source_masks import MaskError
from source_preserve import (SourceError, _execute, build_edit_graph, file_hash,
                             run, verify_pixels, work_dir)


def png_bytes(array):
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format='PNG')
    return buffer.getvalue()


class FakeComfy:
    def __init__(self, graph, payloads):
        self.graph = copy.deepcopy(graph)
        self.payloads = payloads
        self.calls = []
        self.prompt_id = 'source-prompt-original'
        self.graph_override = None
        self.item_override = None
        self.status = {'completed': True}
        self.empty_history = False
        self.on_request = None
        self.history_exception = None
        self.response = None
        self.history_prompt_id = None

    def request(self, endpoint, payload=None, binary=False):
        self.calls.append((endpoint, payload, binary))
        if self.on_request:
            self.on_request(endpoint, payload)
        if endpoint == '/prompt':
            self.graph = copy.deepcopy(payload['prompt'])
            return self.response if self.response is not None else {'prompt_id': self.prompt_id}
        if endpoint.startswith('/history/'):
            if self.history_exception:
                raise self.history_exception
            if self.empty_history:
                return {}
            outputs = {}
            for node_id, node in self.graph.items():
                if node['class_type'] != 'SaveImage':
                    continue
                prefix = Path(node['inputs']['filename_prefix'])
                item = {'filename': prefix.name + '_00001_.png',
                        'subfolder': str(prefix.parent).replace('\\', '/'), 'type': 'output'}
                if self.item_override:
                    item.update(self.item_override)
                outputs[node_id] = {'images': [item]}
            return {self.prompt_id: {
                'status': copy.deepcopy(self.status), 'outputs': outputs,
                'prompt': [0, self.history_prompt_id or self.prompt_id,
                           copy.deepcopy(self.graph_override if self.graph_override is not None else self.graph),
                           {}, list(outputs)],
            }}
        if endpoint.startswith('/view?'):
            # The test caller supplies distinct mask/result bytes by output ID.
            for node_id, node in self.graph.items():
                if node['class_type'] == 'SaveImage' and Path(node['inputs']['filename_prefix']).name in endpoint:
                    return self.payloads[node_id]
            raise AssertionError('Unexpected output URL: ' + endpoint)
        raise AssertionError(endpoint)

    def submissions(self):
        return sum(endpoint == '/prompt' for endpoint, _, _ in self.calls)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {'output_dir': str(self.root / 'output'),
                       'comfy_dir': str(self.root / 'comfy'),
                       'photo_dir': str(self.root / 'photos'),
                       'reference_dir': str(self.root / 'references')}
        for name in ('output', 'photos', 'references'):
            (self.root / name).mkdir()
        yy, xx = np.indices((16, 16))
        self.original = np.stack((90 + xx, 50 + yy, 30 + xx + yy), axis=-1).astype(np.uint8)
        self.original_path = self.root / 'photos' / 'original.png'
        self.original_path.write_bytes(png_bytes(self.original))
        self.mask_id, self.job_id = 'b' * 32, 'a' * 32
        self.snapshot = stage_reference(self.config, {
            'id': 'carey-original', 'source': 'original.png',
            'source_sha256': file_hash(self.original_path)}, self.mask_id, use_original=True)
        self.source = Path(self.snapshot['staged_path'])
        parent = work_dir(self.config, self.mask_id)
        parent.mkdir(parents=True)
        self.protect, self.edit, self.labels = (parent / (name + '.png')
                                                for name in ('protect', 'edit', 'labels'))
        self.p = np.zeros((16, 16), dtype=np.uint8)
        self.p[5:9, 5:9] = 255
        self.e = np.zeros((16, 16), dtype=np.uint8)
        self.e[:, :4] = 255
        self.protect.write_bytes(png_bytes(self.p))
        self.edit.write_bytes(png_bytes(self.e))
        self.labels.write_bytes(png_bytes(np.full((16, 16, 3), (30, 140, 80), dtype=np.uint8)))
        self.result = self.original.copy()
        self.result[self.e == 255] = (20, 100, 180)
        self.output = self.root / 'rendered.png'
        self.output.write_bytes(png_bytes(self.result))
        self.edit_input = self.root / 'comfy' / 'input' / 'ByrdHouse' / 'source-edits' / self.job_id / 'edit.png'
        self.edit_input.parent.mkdir(parents=True)
        self.edit_input.write_bytes(self.edit.read_bytes())
        self.spec = {'id': self.job_id, 'operation': 'source_preserve',
                     'reference_snapshot': self.snapshot, 'mask_job_id': self.mask_id,
                     'region': 'background', 'mask_hashes': {
                         name: file_hash(path) for name, path in
                         (('protect', self.protect), ('edit', self.edit), ('labels', self.labels))},
                     'edit_mask_path': str(self.edit_input),
                     'edit_mask_image': self.edit_input.relative_to(self.root / 'comfy' / 'input').as_posix(),
                     'checkpoint': 'installed-test.safetensors', 'seed': 123, 'steps': 5,
                     'cfg': 1.5, 'sampler': 'dpmpp_sde', 'scheduler': 'karras',
                     'full_prompt': 'A quiet studio background', 'negative': 'extra person'}
        self.graph, self.saves = build_edit_graph(self.config, self.spec)
        self.inputs = {str(self.source): file_hash(self.source), str(self.edit_input): file_hash(self.edit_input),
                       str(self.protect): file_hash(self.protect), str(self.edit): file_hash(self.edit)}
        self.client = FakeComfy(self.graph, {'final': self.output.read_bytes()})
        self.stop = threading.Event()
        self.callback = Mock()

    @property
    def journal(self):
        return work_dir(self.config, self.job_id) / 'submission.json'

    def execute(self, **kwargs):
        return _execute(self.config, self.client, kwargs.pop('spec', self.spec),
                        kwargs.pop('graph', self.graph), self.saves,
                        kwargs.pop('input_files', self.inputs), kwargs.pop('stop', self.stop),
                        kwargs.pop('submitted', self.callback), kwargs.pop('resume_prompt_id', None))


class PixelTests(Fixture):
    def test_anime_scene_can_use_a_tighter_matte_edge_shrink(self):
        spec = {**self.spec, 'matte_mask_image': 'ByrdHouse/matte.png',
                'core_mask_image': 'ByrdHouse/core.png', 'matte_edge_shrink_pixels': -8}
        graph, _ = build_edit_graph(self.config, spec)
        self.assertEqual(graph['matte_edge_shrink']['inputs']['expand'], -8)

    def test_anime_scene_paints_independent_background_behind_reviewed_character(self):
        spec = {**self.spec, 'anime_anchor_scene': True,
                'matte_mask_image': 'ByrdHouse/matte.png',
                'core_mask_image': 'ByrdHouse/core.png',
                'character_mask_image': 'ByrdHouse/character.png'}
        graph, _ = build_edit_graph(self.config, spec)
        self.assertEqual(graph['composite']['inputs']['mask'], ['character', 0])
        self.assertEqual(graph['empty_latent']['inputs'], {
            'width': 16, 'height': 16, 'batch_size': 1})
        self.assertEqual(graph['sampler']['inputs']['latent_image'], ['empty_latent', 0])
        self.assertEqual(graph['final']['inputs']['images'], ['core_composite', 0])
        self.assertNotIn('matte_edge_shrink', graph)
        self.assertNotIn('encode', graph)
        self.assertNotIn('background', graph)

    def test_alpha_matte_keeps_opaque_protected_core_exact_and_permits_soft_edge_blending(self):
        matte = np.zeros((16, 16), dtype=np.uint8)
        matte[4:10, 4:10] = 255
        matte[4, 3:10] = 128
        matte_path = self.root / 'matte.png'
        matte_path.write_bytes(png_bytes(matte))
        alpha_result = self.original.copy()
        alpha_result[matte == 0] = (20, 100, 180)
        alpha_result[4, 3:10] = (55, 75, 100)
        self.output.write_bytes(png_bytes(alpha_result))
        core = self.root / 'core.png'
        core.write_bytes(png_bytes(self.p))
        report = verify_pixels(self.source, self.output, self.protect, self.edit, matte_path, core)
        self.assertTrue(report['passed'])
        self.assertEqual(report['semantic_core_changed_pixels'], 0)
        self.assertGreater(report['background_changed_pixels'], 0)
        self.assertGreater(report['edge_changed_pixels'], 0)
        self.assertIn('BiRefNet handles the soft outer edge', report['claim_scope'])

    def test_alpha_matte_rejects_one_changed_opaque_protected_core_pixel(self):
        matte = np.zeros((16, 16), dtype=np.uint8)
        matte[4:10, 4:10] = 255
        matte_path = self.root / 'matte.png'
        matte_path.write_bytes(png_bytes(matte))
        self.result[5, 5, 0] += 1
        self.result[matte == 0] = (20, 100, 180)
        self.output.write_bytes(png_bytes(self.result))
        core = self.root / 'core.png'
        core.write_bytes(png_bytes(self.p))
        with self.assertRaisesRegex(SourceError, '1 semantic protected-core pixels'):
            verify_pixels(self.source, self.output, self.protect, self.edit, matte_path, core)

    def test_saved_png_keeps_protected_and_outside_edit_pixels_exact(self):
        report = verify_pixels(self.source, self.output, self.protect, self.edit)
        self.assertTrue(report['passed'])
        self.assertEqual(report['protected_changed_pixels'], 0)
        self.assertEqual(report['protected_max_channel_difference'], 0)
        self.assertEqual(report['outside_edit_changed_pixels'], 0)
        self.assertEqual(report['edited_changed_pixels'], 64)
        expected = hashlib.sha256(self.original[self.p == 255].tobytes()).hexdigest()
        self.assertEqual(report['protected_source_pixels_sha256'], expected)
        self.assertEqual(report['protected_output_pixels_sha256'], expected)
        self.assertIn('Semantic coverage still requires visual review', report['claim_scope'])

    def test_one_changed_protected_channel_is_rejected(self):
        self.result[5, 5, 0] += 1
        self.output.write_bytes(png_bytes(self.result))
        with self.assertRaisesRegex(SourceError, 'changed 1 protected pixels'):
            verify_pixels(self.source, self.output, self.protect, self.edit)

    def test_one_changed_outside_edit_pixel_is_rejected(self):
        self.result[1, 12, 2] += 1
        self.output.write_bytes(png_bytes(self.result))
        with self.assertRaisesRegex(SourceError, '0 protected pixels and 1 pixels outside'):
            verify_pixels(self.source, self.output, self.protect, self.edit)

    def test_unchanged_copy_is_not_a_useful_edit(self):
        self.output.write_bytes(self.source.read_bytes())
        with self.assertRaisesRegex(SourceError, 'requested region did not change'):
            verify_pixels(self.source, self.output, self.protect, self.edit)

    def test_output_dimensions_and_lossy_format_fail(self):
        Image.new('RGB', (15, 16)).save(self.output)
        with self.assertRaisesRegex(SourceError, 'original dimensions'):
            verify_pixels(self.source, self.output, self.protect, self.edit)
        jpeg = self.root / 'rendered.jpg'
        Image.fromarray(self.result).save(jpeg)
        with self.assertRaisesRegex(SourceError, 'must be a PNG'):
            verify_pixels(self.source, jpeg, self.protect, self.edit)

    def test_nonbinary_mismatched_and_overlapping_masks_fail(self):
        self.e[0, 0] = 127
        self.edit.write_bytes(png_bytes(self.e))
        with self.assertRaisesRegex(MaskError, 'not binary'):
            verify_pixels(self.source, self.output, self.protect, self.edit)
        Image.new('L', (16, 15), 255).save(self.edit)
        with self.assertRaisesRegex(MaskError, 'dimensions differ'):
            verify_pixels(self.source, self.output, self.protect, self.edit)
        self.e[0, 0] = 255
        self.e[5, 5] = 255
        self.edit.write_bytes(png_bytes(self.e))
        with self.assertRaisesRegex(SourceError, 'overlaps protected'):
            verify_pixels(self.source, self.output, self.protect, self.edit)


class SubmissionTests(Fixture):
    def test_intent_exists_before_post_and_id_before_callback_and_history(self):
        observed = []
        def check_request(endpoint, payload):
            card = json.loads(self.journal.read_text())
            self.assertEqual(card['input_files'], self.inputs)
            self.assertEqual(card['workflow'], self.graph)
            if endpoint == '/prompt':
                self.assertIsNone(card['prompt_id'])
                self.assertEqual(payload['prompt'], card['workflow'])
            elif endpoint.startswith('/history/'):
                self.assertEqual(card['prompt_id'], self.client.prompt_id)
                self.assertEqual(observed, [self.client.prompt_id])
        def submitted(prompt_id):
            self.assertEqual(json.loads(self.journal.read_text())['prompt_id'], prompt_id)
            observed.append(prompt_id)
        self.client.on_request = check_request
        paths, prompt_id = self.execute(submitted=submitted)
        self.assertEqual(prompt_id, self.client.prompt_id)
        self.assertEqual(paths['final'].read_bytes(), self.output.read_bytes())
        self.assertEqual(self.client.submissions(), 1)

    def test_resume_collects_same_prompt_without_second_post(self):
        first_paths, prompt_id = self.execute()
        self.client.calls.clear()
        paths, resumed_id = self.execute(resume_prompt_id=prompt_id)
        self.assertEqual((paths, resumed_id), (first_paths, prompt_id))
        self.assertEqual(self.client.submissions(), 0)
        self.assertTrue(self.client.calls[0][0].startswith('/history/'))

    def test_callback_crash_keeps_id_and_auto_adopts_it(self):
        with self.assertRaisesRegex(RuntimeError, 'SQLite callback failure'):
            self.execute(submitted=Mock(side_effect=RuntimeError('SQLite callback failure')))
        self.assertEqual(json.loads(self.journal.read_text())['prompt_id'], self.client.prompt_id)
        self.client.calls.clear()
        self.execute()
        self.assertEqual(self.client.submissions(), 0)

    def test_submission_response_loss_does_not_blindly_post_again(self):
        def lose_response(endpoint, payload):
            if endpoint == '/prompt':
                raise TimeoutError('Submission response lost')
        self.client.on_request = lose_response
        with self.assertRaises(TimeoutError):
            self.execute()
        self.client.on_request = None
        self.client.calls.clear()
        with self.assertRaisesRegex(SourceError, 'no recorded ID'):
            self.execute()
        self.assertEqual(self.client.calls, [])

    def test_mutated_source_or_mask_fails_without_new_backend_request(self):
        self.execute()
        for path in (self.source, self.edit_input):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(b'changed frozen input')
                self.client.calls.clear()
                with self.assertRaisesRegex(SourceError, 'input changed'):
                    self.execute(resume_prompt_id=self.client.prompt_id)
                self.assertEqual(self.client.calls, [])
                path.write_bytes(original)

    def test_mutated_settings_graph_or_journal_fails_without_resubmission(self):
        self.execute()
        changed_spec = copy.deepcopy(self.spec); changed_spec['seed'] += 1
        changed_graph = copy.deepcopy(self.graph); changed_graph['positive']['inputs']['text'] = 'Altered work'
        for kwargs in ({'spec': changed_spec}, {'graph': changed_graph}):
            self.client.calls.clear()
            with self.subTest(kwargs=next(iter(kwargs))), self.assertRaisesRegex(SourceError, 'refusing altered work'):
                self.execute(**kwargs)
            self.assertEqual(self.client.calls, [])
        journal = json.loads(self.journal.read_text())
        journal['workflow_sha256'] = '0' * 64
        self.journal.write_text(json.dumps(journal))
        self.client.calls.clear()
        with self.assertRaisesRegex(SourceError, 'refusing altered work'):
            self.execute()
        self.assertEqual(self.client.calls, [])

    def test_mismatched_resume_id_or_history_graph_fails(self):
        self.execute()
        self.client.calls.clear()
        with self.assertRaisesRegex(SourceError, 'matching submission journal'):
            self.execute(resume_prompt_id='other-prompt')
        self.assertEqual(self.client.calls, [])
        self.client.graph_override = copy.deepcopy(self.graph)
        self.client.graph_override['positive']['inputs']['text'] = 'Wrong history workflow'
        with self.assertRaisesRegex(SourceError, 'different workflow'):
            self.execute(resume_prompt_id=self.client.prompt_id)
        self.assertFalse(any(endpoint.startswith('/view?') for endpoint, _, _ in self.client.calls))

    def test_mismatched_history_prompt_id_is_rejected(self):
        self.client.history_prompt_id = 'another-prompt'
        with self.assertRaisesRegex(SourceError, 'history|workflow|prompt'):
            self.execute()
        self.assertFalse(any(endpoint.startswith('/view?') for endpoint, _, _ in self.client.calls))

    def test_foreign_prefix_path_or_temporary_output_is_rejected(self):
        self.execute()
        for override in ({'filename': 'source-preserved-foreign_00001_.png'},
                         {'filename': '../escaped.png'}, {'subfolder': 'other-job'}, {'type': 'temp'}):
            self.client.calls.clear()
            self.client.item_override = override
            with self.subTest(override=override), self.assertRaises(SourceError):
                self.execute(resume_prompt_id=self.client.prompt_id)
            self.assertEqual(self.client.submissions(), 0)
            self.assertFalse(any(endpoint.startswith('/view?') for endpoint, _, _ in self.client.calls))

    def test_history_is_changed_annotations_are_accepted(self):
        self.client.graph_override = copy.deepcopy(self.graph)
        for node in self.client.graph_override.values():
            node['is_changed'] = 'backend cache annotation'
        self.execute()

    def test_source_changed_during_render_is_detected_before_return(self):
        def mutate(endpoint, payload):
            if endpoint.startswith('/history/'):
                self.source.write_bytes(b'replaced during render')
        self.client.on_request = mutate
        with self.assertRaisesRegex(SourceError, 'changed during rendering'):
            self.execute()
        self.assertEqual(self.client.submissions(), 1)

    def test_changed_collected_output_is_not_overwritten_on_resume(self):
        paths, _ = self.execute()
        original = paths['final'].read_bytes()
        changed = self.result.copy(); changed[0, 0, 0] += 1
        self.client.payloads['final'] = png_bytes(changed)
        with self.assertRaisesRegex(SourceError, 'existing collected artifact'):
            self.execute(resume_prompt_id=self.client.prompt_id)
        self.assertEqual(paths['final'].read_bytes(), original)

    def test_pending_stop_retains_prompt_and_resume_does_not_resubmit(self):
        self.client.empty_history = True
        stop = Mock(); stop.wait.return_value = True; stop.is_set.return_value = False
        with self.assertRaisesRegex(SourceError, 'Studio stopped.*Resume the existing prompt'):
            self.execute(stop=stop)
        self.assertEqual(json.loads(self.journal.read_text())['prompt_id'], self.client.prompt_id)
        self.client.empty_history = False
        self.client.calls.clear()
        self.execute(resume_prompt_id=self.client.prompt_id)
        self.assertEqual(self.client.submissions(), 0)

    def test_already_stopped_studio_never_submits_new_work(self):
        self.stop.set()
        with self.assertRaisesRegex(SourceError, 'Studio stopped'):
            self.execute()
        self.assertEqual(self.client.submissions(), 0)
        self.assertFalse(self.journal.exists())

    def test_terminal_backend_failure_is_not_reported_as_stop(self):
        self.client.status = {'completed': True, 'status_str': 'error', 'messages': [
            ['execution_error', {'exception_message': 'HIP kernel failure'}]]}
        with self.assertRaisesRegex(SourceError, '^HIP kernel failure$'):
            self.execute()
        self.assertEqual(self.client.submissions(), 1)
        self.assertFalse(any(endpoint.startswith('/view?') for endpoint, _, _ in self.client.calls))

    def test_observation_timeout_keeps_prompt_for_external_recovery(self):
        self.client.history_exception = TimeoutError('history observation timed out')
        with self.assertRaises(TimeoutError):
            self.execute()
        self.assertEqual(json.loads(self.journal.read_text())['prompt_id'], self.client.prompt_id)
        self.client.history_exception = None
        self.client.calls.clear()
        self.execute(resume_prompt_id=self.client.prompt_id)
        self.assertEqual(self.client.submissions(), 0)

    def test_full_adapter_promotes_only_verified_png_and_keeps_review_claims(self):
        result = run(self.config, self.client, self.spec, self.stop, self.callback)
        self.assertEqual(result, [self.job_id + '_1.png'])
        published = Path(self.config['output_dir']) / result[0]
        self.assertEqual(published.read_bytes(), self.output.read_bytes())
        card = json.loads(published.with_suffix('.png.json').read_text())
        self.assertTrue(card['inspection']['passed'])
        self.assertFalse(card['exact_replica'])
        self.assertFalse(card['identity_verified'])
        self.assertEqual(card['review_state'], 'needs_review')
        self.assertEqual(card['prompt_id'], self.client.prompt_id)

    def test_failed_pixel_gate_does_not_publish_gallery_artifact(self):
        changed = self.result.copy(); changed[5, 5, 0] += 1
        self.client.payloads['final'] = png_bytes(changed)
        with self.assertRaisesRegex(SourceError, 'protected pixels'):
            run(self.config, self.client, self.spec, self.stop, self.callback)
        published = Path(self.config['output_dir']) / (self.job_id + '_1.png')
        self.assertFalse(published.exists())
        self.assertFalse(published.with_suffix('.png.json').exists())

    def test_full_adapter_rejects_changed_mask_alias_before_submission(self):
        self.spec['edit_mask_image'] = 'mutable-mask.png'
        with self.assertRaises(SourceError):
            run(self.config, self.client, self.spec, self.stop, self.callback)
        self.assertEqual(self.client.calls, [])


if __name__ == '__main__':
    unittest.main()
