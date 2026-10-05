"""Wan provenance, shared queue and no-duplicate recovery; no real GPU."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from portrait_animation import animate
from server import Studio, ValidationError
from test_portrait_resume import FakeComfy, Stop
from wan22_workflow import build, MODEL, ENCODER, VAE, NODES


class WanAnimationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.images = self.root/'media/images'
        self.images.mkdir(parents=True)
        self.source = self.root/'source.png'
        Image.new('RGB', (24, 32), (100, 60, 30)).save(self.source)
        self.template = self.root/'external/workflows/comfy-wan22-5b/image_to_video_wan22_5B.json'
        self.template.parent.mkdir(parents=True)
        self.template.write_bytes((Path(__file__).parent.parent/'workflows/upstream/comfy-wan22-5b.json').read_bytes())
        self.job_id = 'b'*32
        self.config = {'output_dir': str(self.images), 'comfy_dir': str(self.root/'comfy'),
                       'comfy_url': 'http://127.0.0.1:8188', 'checkpoint': 'base.safetensors',
                       'lightning_lora': 'lightning.safetensors', 'photo_dir': str(self.root/'photos')}
        self.spec = {'id': self.job_id, 'operation': 'scene_animation', 'engine': 'wan22',
                     'seed': 10, 'video_preset': 'portrait_smoke', 'prompt': 'Carey blinks',
                     'negative': 'different person', 'reference': 'carey',
                     'animation_source_sha256': hashlib.sha256(self.source.read_bytes()).hexdigest()}
        self.output = self.root/'media/animation'/self.job_id
        self.client = FakeComfy(self.job_id)
        self.client.rows = [{'filename': f'frame_{i:05d}_.png', 'type': 'output',
                             'subfolder': 'Carey-Wan22/'+self.job_id} for i in range(33)]
        self.callback = Mock()
        self.encoder = patch('portrait_animation.subprocess.run', side_effect=self.encode).start()
        patch('portrait_animation.imageio_ffmpeg.get_ffmpeg_exe', return_value='mock-ffmpeg').start()
        self.addCleanup(patch.stopall)

    def encode(self, args, **kwargs):
        self.assertEqual(args[args.index('-framerate')+1], '24')
        self.assertEqual(len(list((self.output/'frames').glob('*.png'))), 33)
        Path(args[-1]).write_bytes(b'movie')

    def run_video(self, resume=False, stop=None):
        return animate(self.config, self.client, self.spec, self.source, stop or Stop(), self.callback,
                       resume_prompt_id=self.client.prompt_id if resume else None)

    def test_resume_uses_same_submission_after_template_removed(self):
        self.client.observations = [{}]
        with self.assertRaisesRegex(RuntimeError, 'Studio stopped'):
            self.run_video(stop=Stop(True))
        self.template.unlink()
        self.client.calls.clear()
        self.assertEqual(self.run_video(resume=True), [self.job_id+'_1.png'])
        self.assertFalse(self.client.requests('/prompt'))
        self.assertFalse(self.client.requests('/object_info'))
        card = json.loads((self.images/(self.job_id+'.mp4.json')).read_text())
        self.assertEqual((card['frames'], card['fps']), (33, 24))
        self.assertFalse(card['identity_verified'])
        self.assertEqual(card['review_state'], 'needs_review')

    def test_changed_source_fails_before_submission(self):
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'Source changed'):
            self.run_video()
        self.assertFalse(self.client.requests('/prompt'))

    def test_execution_error_keeps_the_actionable_exception(self):
        self.client.observations = [{self.client.prompt_id: {'status': {
            'completed': False, 'status_str': 'error', 'messages': [['execution_error', {
                'node_type': 'KSampler', 'node_id': '3', 'exception_type': 'RuntimeError',
                'exception_message': 'HostBuffer.read_file_slice failed',
                'current_inputs': 'large tensor dump '*1000}]]}}}]
        with self.assertRaisesRegex(RuntimeError, 'KSampler 3: RuntimeError: HostBuffer.read_file_slice failed'):
            self.run_video()
        self.encoder.assert_not_called()

    def test_template_tampering_and_duplicate_frames_fail(self):
        original = self.template.read_bytes()
        self.template.write_bytes(original+b' ')
        with self.assertRaisesRegex(RuntimeError, 'upstream Wan workflow changed'):
            build(self.config, self.spec, 'Carey.png')
        self.template.write_bytes(original)
        self.client.rows[1] = self.client.rows[0]
        with self.assertRaisesRegex(RuntimeError, 'duplicate output frames'):
            self.run_video()
        self.encoder.assert_not_called()

    def test_queue_rejects_unreviewed_sources_and_unbounded_previews(self):
        self.client.models = lambda: {'checkpoints': ['base.safetensors'], 'loras': [],
            'diffusion_models': [MODEL], 'text_encoders': [ENCODER], 'vaes': [VAE], 'nodes': list(NODES)}
        studio = Studio(self.config, self.root, self.client, start_worker=False)
        self.addCleanup(studio.close)
        studio.reference_dir.mkdir(parents=True, exist_ok=True)
        (studio.reference_dir/'source.png').write_bytes(self.source.read_bytes())
        studio.references = {'carey': {'id': 'carey', 'file': 'source.png', 'generated': True}}
        with self.assertRaises(ValidationError):
            studio.create_scene_animation({'reference': 'carey'})
        self.config['animation_allowed_illustrated_references'] = ['carey']
        for payload in [{'video_preset': 'unlimited'}, {'seed': True}, {'prompt': ''},
                        {'source_job_id': 'a'*32}, {'frames': 1000}]:
            with self.assertRaises(ValidationError):
                studio.create_scene_animation({'reference': 'carey', **payload})
        job = studio.create_scene_animation({'reference': 'carey', 'seed': 1})
        self.assertEqual((job['state'], job['operation']), ('queued', 'scene_animation'))
        self.assertEqual(job['animation_source_sha256'], self.spec['animation_source_sha256'])
        self.assertFalse(self.client.requests('/prompt'))
