"""Animation recovery and collection tests; no GPU or real encoder required."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from portrait_animation import animate


class Stop:
    def __init__(self, stop=False):
        self.stopped = stop
        self.waits = []

    def wait(self, seconds):
        self.waits.append(seconds)
        return self.stopped


class FakeComfy:
    def __init__(self, job_id):
        self.job_id = job_id
        self.prompt_id = 'existing-animation-prompt'
        self.graph = None
        self.calls = []
        self.observations = []
        self.prompt_error = None
        self.view_failure_at = None
        self.view_count = 0
        self.rows = [{'filename': f'frame_{index:05d}_.png',
                      'subfolder': f'Carey-LivePortrait/{job_id}', 'type': 'output'}
                     for index in range(44)]
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), (50, 25, 10)).save(buffer, format='PNG')
        self.png = buffer.getvalue()
        self.history_graph = None
        self.input_names = {'LoadImage': ['image'], 'ExpressionEditor': ['blink'],
                            'AdvancedLivePortrait': ['command']}

    def request(self, endpoint, payload=None, binary=False):
        self.calls.append((endpoint, payload, binary))
        if endpoint.startswith('/object_info/'):
            kind = endpoint.rsplit('/', 1)[1]
            names = self.input_names[kind]
            return {kind: {'input_order': {'required': names}}}
        if endpoint == '/prompt':
            self.graph = copy.deepcopy(payload['prompt'])
            if self.prompt_error:
                raise self.prompt_error
            return {'prompt_id': self.prompt_id}
        if endpoint.startswith('/history/'):
            if self.observations:
                observation = self.observations.pop(0)
                if isinstance(observation, Exception):
                    raise observation
                return observation
            graph = self.graph if self.history_graph is None else self.history_graph
            return {self.prompt_id: {'status': {'completed': True, 'status_str': 'success'},
                    'prompt': [0, self.prompt_id, graph, {}, ['10']],
                    'outputs': {'10': {'images': self.rows}}}}
        if endpoint.startswith('/view?'):
            self.view_count += 1
            if self.view_count == self.view_failure_at:
                raise RuntimeError('Connection dropped collecting frame')
            return self.png
        raise AssertionError('Unexpected request: '+endpoint)

    def requests(self, prefix):
        return [call for call in self.calls if call[0].startswith(prefix)]


class PortraitResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.images = self.root/'media/images'
        self.images.mkdir(parents=True)
        self.source = self.root/'original.png'
        Image.new('RGB', (16, 16), (100, 60, 25)).save(self.source)
        self.job_id = 'a'*32
        self.spec = {'id': self.job_id, 'operation': 'portrait_animation',
                     'reference': 'portrait', 'prompt': 'blink preview',
                     'animation_source_sha256': hashlib.sha256(self.source.read_bytes()).hexdigest()}
        self.config = {'output_dir': str(self.images), 'comfy_dir': str(self.root/'comfy')}
        self.output = self.root/'media/animation'/self.job_id
        self.template = (self.root/'repo/external/ComfyUI-AdvancedLivePortrait'
                         '/sample/workflows/Advanced_Animate_without_vid.json')
        self.template.parent.mkdir(parents=True)
        self.template.write_text(json.dumps({'nodes': [
            {'id': 3, 'type': 'LoadImage', 'widgets_values': ['old.png']},
            {'id': 15, 'type': 'ExpressionEditor', 'widgets_values': [0]},
            {'id': 7, 'type': 'AdvancedLivePortrait', 'widgets_values': ['old command']},
        ]}))
        self.client = FakeComfy(self.job_id)
        self.submitted = Mock()
        self.encoder = patch('portrait_animation.subprocess.run', side_effect=self.encode).start()
        patch('portrait_animation.imageio_ffmpeg.get_ffmpeg_exe', return_value='mock-ffmpeg').start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.tmp.cleanup)

    def encode(self, args, **kwargs):
        self.assertEqual(args[args.index('-framerate')+1], '15')
        self.assertEqual(len(list((self.output/'frames').glob('frame_*.png'))), 44)
        Path(args[-1]).write_bytes(b'encoded movie')

    def run_animation(self, resume=False, stop=None):
        return animate(self.config, self.client, self.spec, self.source,
                       stop or Stop(), self.submitted,
                       resume_prompt_id=self.client.prompt_id if resume else None)

    def interrupt_after_submit(self):
        self.client.observations = [{}]
        with self.assertRaisesRegex(RuntimeError, 'Studio stopped'):
            self.run_animation(stop=Stop(True))
        self.assertEqual(len(self.client.requests('/prompt')), 1)

    def test_resume_collects_same_prompt_without_post_template_or_callback(self):
        self.interrupt_after_submit()
        workflow_before = (self.output/'workflow.json').read_bytes()
        submission_before = (self.output/'submission.json').read_bytes()
        self.template.unlink()
        self.client.calls.clear()
        self.submitted.reset_mock()
        self.client.observations = [TimeoutError(), RuntimeError('backend timed out'), {}]
        stop = Stop()
        self.assertEqual(self.run_animation(resume=True, stop=stop), [self.job_id+'_1.png'])
        self.assertFalse(self.client.requests('/prompt'))
        self.assertFalse(self.client.requests('/object_info'))
        self.submitted.assert_not_called()
        self.assertEqual((self.output/'workflow.json').read_bytes(), workflow_before)
        self.assertEqual((self.output/'submission.json').read_bytes(), submission_before)
        self.assertEqual(len(self.client.requests('/history/')), 4)
        self.assertTrue(all(call[0].endswith(self.client.prompt_id)
                            for call in self.client.requests('/history/')))
        self.assertEqual([seconds for seconds in stop.waits if seconds], [0.8]*3)
        self.assertEqual(self.client.view_count, 44)
        self.encoder.assert_called_once()

    def test_submission_is_durable_before_callback_and_callback_failure_resumes(self):
        def callback(prompt_id):
            saved = json.loads((self.output/'submission.json').read_text())
            self.assertEqual(saved['prompt_id'], prompt_id)
            self.assertEqual(saved['state'], 'submitted')
            self.assertEqual(len(saved['workflow_sha256']), 64)
            raise RuntimeError('SQLite callback interrupted')
        self.submitted.side_effect = callback
        with self.assertRaisesRegex(RuntimeError, 'SQLite callback interrupted'):
            self.run_animation()
        self.submitted.reset_mock(side_effect=True)
        self.run_animation(resume=True)
        self.assertEqual(len(self.client.requests('/prompt')), 1)
        self.submitted.assert_not_called()

    def test_ambiguous_post_is_recorded_and_not_retried(self):
        self.client.prompt_error = TimeoutError('POST timed out after possible acceptance')
        with self.assertRaises(TimeoutError):
            self.run_animation()
        saved = json.loads((self.output/'submission.json').read_text())
        self.assertEqual(saved['state'], 'submitting')
        self.assertIsNone(saved['prompt_id'])
        with self.assertRaisesRegex(RuntimeError, 'already has a submission record'):
            self.run_animation()
        self.assertEqual(len(self.client.requests('/prompt')), 1)

    def test_resume_rejects_tampered_submission_without_backend_requests(self):
        self.interrupt_after_submit()
        path = self.output/'submission.json'
        original = json.loads(path.read_text())
        for key, value in [('job_id', 'b'*32), ('prompt_id', 'wrong'),
                           ('source_sha256', '0'*64), ('spec_sha256', '0'*64),
                           ('workflow_sha256', '0'*64), ('input_sha256', '0'*64),
                           ('schema', 'legacy'), ('state', 'submitting')]:
            with self.subTest(key=key):
                path.write_text(json.dumps({**original, key: value}))
                self.client.calls.clear()
                with self.assertRaises(RuntimeError):
                    self.run_animation(resume=True)
                self.assertEqual(self.client.calls, [])
        path.write_text(json.dumps(original))

    def test_resume_rejects_changed_workflow_source_input_and_spec(self):
        self.interrupt_after_submit()
        workflow = self.output/'workflow.json'
        original = workflow.read_bytes()
        graph = json.loads(original)
        graph['15']['inputs']['blink'] = 99
        workflow.write_text(json.dumps(graph))
        with self.assertRaisesRegex(RuntimeError, 'provenance'):
            self.run_animation(resume=True)
        workflow.write_bytes(original)
        source_original = self.source.read_bytes()
        self.source.write_bytes(source_original+b'changed')
        with self.assertRaisesRegex(RuntimeError, 'Source changed'):
            self.run_animation(resume=True)
        self.source.write_bytes(source_original)
        self.spec['reference'] = 'different reference'
        with self.assertRaisesRegex(RuntimeError, 'provenance'):
            self.run_animation(resume=True)
        self.spec['reference'] = 'portrait'
        input_path = Path(self.config['comfy_dir'])/'input/ByrdHouse/animation'/f'{self.job_id}.png'
        input_path.write_bytes(b'changed input')
        with self.assertRaisesRegex(RuntimeError, 'input changed'):
            self.run_animation(resume=True)
        self.assertEqual(len(self.client.requests('/prompt')), 1)

    def test_history_from_another_workflow_is_not_collected(self):
        self.interrupt_after_submit()
        self.client.history_graph = {'wrong': {'class_type': 'SaveImage'}}
        with self.assertRaisesRegex(RuntimeError, 'history provenance'):
            self.run_animation(resume=True)
        self.assertEqual(self.client.view_count, 0)
        self.encoder.assert_not_called()

    def test_repeated_collection_preserves_files_and_human_review(self):
        self.run_animation()
        movie = self.images/f'{self.job_id}.mp4'
        poster = self.images/f'{self.job_id}_1.png'
        for path in (poster.with_suffix('.png.json'), movie.with_suffix('.mp4.json')):
            card = json.loads(path.read_text())
            card.update(review_state='approved', reviewed='human review date')
            path.write_text(json.dumps(card))
        watched = list((self.output/'frames').glob('*.png')) + [movie, poster,
                    self.output/'workflow.json', self.output/'submission.json',
                    poster.with_suffix('.png.json'), movie.with_suffix('.mp4.json')]
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in watched}
        self.client.calls.clear()
        self.encoder.reset_mock()
        self.run_animation(resume=True)
        self.assertFalse(self.client.requests('/view?'))
        self.assertFalse(self.client.requests('/prompt'))
        self.encoder.assert_not_called()
        for path in watched:
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before[path])
        self.assertFalse(json.loads(movie.with_suffix('.mp4.json').read_text())['identity_verified'])

    def test_partial_collection_reuses_verified_frames(self):
        self.client.view_failure_at = 6
        with self.assertRaisesRegex(RuntimeError, 'Connection dropped'):
            self.run_animation()
        self.assertEqual(len(list((self.output/'frames').glob('*.png'))), 5)
        self.client.view_failure_at = None
        self.client.calls.clear()
        self.run_animation(resume=True)
        self.assertEqual(len(self.client.requests('/view?')), 39)
        self.assertFalse(self.client.requests('/prompt'))
        self.encoder.assert_called_once()

    def test_resume_repairs_corrupted_frame_without_regenerating(self):
        self.run_animation()
        (self.output/'frames/frame_0010.png').write_bytes(b'corrupt cached frame')
        self.client.calls.clear()
        self.encoder.reset_mock()
        self.run_animation(resume=True)
        self.assertEqual(len(self.client.requests('/view?')), 1)
        self.assertEqual((self.output/'frames/frame_0010.png').read_bytes(), self.client.png)
        self.assertFalse(self.client.requests('/prompt'))
        self.encoder.assert_not_called()  # Restored bytes match the already encoded movie.

    def test_encoding_failure_keeps_existing_video_and_resume_encodes(self):
        movie = self.images/f'{self.job_id}.mp4'
        movie.write_bytes(b'previous complete video')
        self.encoder.side_effect = RuntimeError('encoder interrupted')
        with self.assertRaisesRegex(RuntimeError, 'encoder interrupted'):
            self.run_animation()
        self.assertEqual(movie.read_bytes(), b'previous complete video')
        self.encoder.side_effect = self.encode
        self.client.calls.clear()
        self.run_animation(resume=True)
        self.assertEqual(movie.read_bytes(), b'encoded movie')
        self.assertFalse(self.client.requests('/view?'))
        self.assertFalse(self.client.requests('/prompt'))

    def test_wrong_frame_count_or_output_folder_is_not_encoded(self):
        self.interrupt_after_submit()
        original = copy.deepcopy(self.client.rows)
        self.client.rows = original[:-1]
        with self.assertRaisesRegex(RuntimeError, 'Expected 44'):
            self.run_animation(resume=True)
        self.client.rows = copy.deepcopy(original)
        self.client.rows[0]['subfolder'] = 'Carey-LivePortrait/another-job'
        with self.assertRaisesRegex(RuntimeError, 'output provenance'):
            self.run_animation(resume=True)
        self.encoder.assert_not_called()
        self.assertEqual(self.client.view_count, 0)

    def test_non_timeout_history_errors_remain_errors(self):
        self.interrupt_after_submit()
        self.client.observations = [RuntimeError('connection refused')]
        with self.assertRaisesRegex(RuntimeError, 'connection refused'):
            self.run_animation(resume=True)
        self.assertEqual(len(self.client.requests('/prompt')), 1)

    def test_duplicate_frames_are_rejected_before_collection(self):
        self.interrupt_after_submit()
        self.client.rows[1] = copy.deepcopy(self.client.rows[0])
        with self.assertRaisesRegex(RuntimeError, 'duplicate output frames'):
            self.run_animation(resume=True)
        self.assertEqual(self.client.view_count, 0)
        self.encoder.assert_not_called()

    def test_stop_during_collection_keeps_frames_for_resume(self):
        self.interrupt_after_submit()
        client = self.client
        class StopDuringCollection(Stop):
            def wait(self, seconds):
                return client.view_count >= 7
        with self.assertRaisesRegex(RuntimeError, 'finish collection'):
            self.run_animation(resume=True, stop=StopDuringCollection())
        self.assertEqual(len(list((self.output/'frames').glob('*.png'))), 7)
        self.client.calls.clear()
        self.run_animation(resume=True)
        self.assertEqual(len(self.client.requests('/view?')), 37)
        self.assertFalse(self.client.requests('/prompt'))

    def test_real_history_float_coercion_and_cache_annotation_resume_without_post(self):
        # Shape and input types from live prompt 371274e1-790e-43e5-af31-3273b2c77938.
        required = {
            'LoadImage': {'image': 'old.png'},
            'ExpressionEditor': {'rotate_pitch': 0, 'rotate_yaw': 0, 'rotate_roll': 0,
                'blink': 0, 'eyebrow': 0, 'wink': 0, 'pupil_x': 0, 'pupil_y': 0,
                'aaa': 0, 'eee': 0, 'woo': 0, 'smile': 0, 'src_ratio': 1,
                'sample_ratio': 1, 'sample_parts': 'OnlyExpression', 'crop_factor': 1.7},
            'AdvancedLivePortrait': {'retargeting_eyes': 0, 'retargeting_mouth': 0,
                'crop_factor': 1.7000000000000002, 'turn_on': True,
                'tracking_src_vid': False, 'animate_without_vid': True, 'command': ''},
        }
        self.client.input_names = {kind: list(values) for kind, values in required.items()}
        self.template.write_text(json.dumps({'nodes': [
            {'id': node_id, 'type': kind, 'widgets_values': list(required[kind].values())}
            for node_id, kind in [(3, 'LoadImage'), (7, 'AdvancedLivePortrait'), (15, 'ExpressionEditor')]
        ]}))
        self.interrupt_after_submit()
        history_graph = copy.deepcopy(self.client.graph)
        for node_id in ('7', '15'):
            for name, value in history_graph[node_id]['inputs'].items():
                if type(value) is int:
                    history_graph[node_id]['inputs'][name] = float(value)
        history_graph['3']['is_changed'] = ['upstream source-file cache fingerprint']
        self.client.history_graph = history_graph
        for row in self.client.rows:
            row['subfolder'] = row['subfolder'].replace('/', '\\')
        self.client.calls.clear()
        self.run_animation(resume=True)
        self.assertFalse(self.client.requests('/prompt'))
        self.assertFalse(self.client.requests('/object_info'))
        self.assertEqual(len(self.client.requests('/view?')), 44)
        self.encoder.assert_called_once()

    def test_history_numeric_or_extra_field_changes_are_not_annotations(self):
        self.interrupt_after_submit()
        changes = [
            lambda graph: graph['15']['inputs'].update(blink=-7.0),
            lambda graph: graph['15']['inputs'].update(wink=False),
            lambda graph: graph['15']['inputs'].update(rotate_yaw='1.5'),
            lambda graph: graph['15']['inputs'].update(src_image=['3', 0.0]),
            lambda graph: graph['15'].update(unrecognized_annotation='ignored?'),
            lambda graph: graph['10']['inputs'].update(filename_prefix='other-job/frame'),
            lambda graph: graph['15']['inputs'].update(blink=float('nan')),
            lambda graph: graph['7']['inputs'].update(command='different motion'),
        ]
        for change in changes:
            with self.subTest(change=change):
                self.client.history_graph = copy.deepcopy(self.client.graph)
                change(self.client.history_graph)
                with self.assertRaisesRegex(RuntimeError, 'history provenance'):
                    self.run_animation(resume=True)
        self.assertEqual(self.client.view_count, 0)
        self.encoder.assert_not_called()


if __name__ == '__main__':
    unittest.main()
