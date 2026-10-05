"""Complete-frame provenance, no GPU submission, and resumable CPU review."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image
from anime_continuity import sha, work_dir
from anime_view_review import SHEET_VIEWS
from identity_belt import BeltError
from portrait_animation import _json_digest
from server import Studio, ValidationError


class FakeBelt:
    def __init__(self):
        self.targets = []
        self.stop_after = None
        self.stop = None

    def inspect(self, path, illustrated):
        if 'frame_' in Path(path).name:
            self.targets.append(Path(path).name)
            if self.stop_after == len(self.targets): self.stop.set()
        class Face:
            def public(self):
                return {'file': str(path), 'bbox': [4, 4, 30, 45],
                        'metrics': {'landmark_confidence': .9, 'hairline_coverage': .8}}
        return Face()

    def _similarity(self, *_): return .9

    def _geometry(self, reference, candidate, **kwargs):
        if candidate.public()['file'].endswith('frame_0001.png'):
            return {'review_scope': 'different_view_requires_visual_review'}
        return {'review_scope': 'same_view_illustrated_continuity', 'face_outline_error': .01,
                'hair_width_ratio': .20, 'forehead_height_ratio': .02,
                'hairline_y_ratio': .03, 'hair_height_ratio': .02,
                'skin_median_luma': 0, 'skin_luma_shift': 0}


class ContinuityQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.images = self.root / 'media/images'; self.images.mkdir(parents=True)
        self.config = {'output_dir': str(self.images), 'photo_dir': str(self.root/'photos'),
                       'comfy_dir': str(self.root/'comfy'), 'comfy_url': 'http://127.0.0.1:8188'}
        self.client = Mock()
        self.client.request.side_effect = AssertionError('CPU review must never request a Comfy render')
        self.studio = Studio(self.config, self.root, self.client, start_worker=False)
        self.addCleanup(self.studio.close)
        assets = self.root/'assets/characters/carey-anime'; views = assets/'views-v2'; views.mkdir(parents=True)
        sheet = assets/'sheet.png'; Image.new('RGB',(48,64),(95,60,35)).save(sheet)
        entries = []
        for view in SHEET_VIEWS:
            path = views/(view+'.png'); path.write_bytes(sheet.read_bytes())
            entries.append({'view': view, 'path': str(path), 'sha256': sha(path)})
        (assets/'turnaround-v1.json').write_text(json.dumps({
            'schema': 'byrdhouse.carey-anime.turnaround.v1', 'wardrobe_status': 'placeholder_not_approved',
            'assets': {'head_sheet': {'path': str(sheet), 'sha256': sha(sheet)},
                       'approved_closeup_anchor': {'path': str(sheet), 'sha256': sha(sheet)}}}))
        (views/'manifest-v2.json').write_text(json.dumps({'source': str(sheet),
                'source_sha256': sha(sheet), 'views': entries}))
        self.parent_id = 'c'*32
        self.directory = self.root/'media/animation'/self.parent_id
        frames = self.directory/'frames'; frames.mkdir(parents=True)
        self.frames = []
        for i in range(3):
            path = frames/f'frame_{i:04d}.png'; path.write_bytes(sheet.read_bytes()); self.frames.append(path)
        movie = self.images/(self.parent_id+'.mp4'); movie.write_bytes(b'tested movie bytes')
        self.collection = {'schema': 'byrdhouse.animation.collection.v1', 'job_id': self.parent_id,
            'prompt_id': 'saved-prompt', 'source_sha256': sha(sheet), 'workflow_sha256': 'a'*64,
            'movie_sha256': sha(movie), 'frames': {p.name:{'sha256':sha(p)} for p in self.frames}}
        self.collection['encoded_frames_sha256'] = _json_digest(self.collection['frames'])
        (self.directory/'collection.json').write_text(json.dumps(self.collection))
        poster = self.images/(self.parent_id+'_1.png'); poster.write_bytes(sheet.read_bytes())
        poster.with_suffix('.png.json').write_text(json.dumps({**self.collection, 'frames': 3,
            'review_state':'needs_review', 'identity_verified':False}))
        self.parent_spec = {'id':self.parent_id, 'operation':'scene_animation', 'seed':7,
            'reference':'carey-anime-anchor', 'identity_mode':'reference', 'prompt':'Carey blinks'}
        with self.studio.db() as db:
            db.execute('INSERT INTO jobs(id,state,created,spec,outputs) VALUES(?,?,?,?,?)',
                (self.parent_id,'needs_review','2026-10-04',json.dumps(self.parent_spec),json.dumps([poster.name])))
        self.belt = FakeBelt(); self.studio.identity_belt = self.belt

    def queue(self, **kwargs):
        return self.studio.create_anime_review({'source_job_id':self.parent_id,'view':'three-quarter',**kwargs})

    def test_all_frames_checked_source_unchanged_and_diagnostics_cannot_animate(self):
        original = [sha(p) for p in self.frames]
        job = self.queue(); self.studio.run_next()
        result = self.studio.job(job['id']); summary = result['review_summary']
        self.assertEqual(result['state'],'needs_review')
        self.assertEqual(summary['frames_examined'],3)
        self.assertEqual(summary['feature_counts']['Afro width'],{'change':2,'review':0,'inconclusive':1})
        self.assertFalse(summary['automatic_approval'])
        self.assertEqual(self.studio.job(self.parent_id)['state'],'needs_review')
        self.assertEqual([sha(p) for p in self.frames],original)
        self.assertFalse(self.studio.metadata(job['id'])['identity_verified'])
        self.studio.review(job['id'],'approved')
        with self.assertRaises(ValidationError):
            self.studio.animation_source({'parent_job_id':job['id']})
        self.client.request.assert_not_called()

    def test_changed_frame_fails_before_cpu_inference(self):
        job = self.queue(); self.frames[0].write_bytes(b'changed')
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'failed')
        self.assertEqual(self.belt.targets,[])
        self.client.request.assert_not_called()

    def test_changed_matching_reference_fails_before_cpu_inference(self):
        job=self.queue()
        reference=Path(job['approved_view_binding']['path']); reference.write_bytes(b'changed reference')
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'failed')
        self.assertEqual(self.belt.targets,[])

    def test_rear_view_has_no_face_claim_or_cpu_detection(self):
        job=self.queue(view='back'); self.studio.run_next()
        result=self.studio.job(job['id'])
        self.assertEqual(result['state'],'needs_review')
        self.assertEqual(self.belt.targets,[])
        summary=result['review_summary']
        self.assertEqual(summary['feature_counts']['Face outline']['inconclusive'],3)
        report=self.studio.anime_review_report(job['id'])
        self.assertTrue(all(not row['geometry_delta'] for row in report['frames']))
        self.assertFalse(summary['identity_verified'])

    def test_missing_frame_or_changed_movie_refuses_queue(self):
        self.frames[2].unlink()
        with self.assertRaises(ValidationError): self.queue()
        self.frames[2].write_bytes(self.frames[0].read_bytes())
        (self.images/(self.parent_id+'.mp4')).write_bytes(b'changed movie')
        with self.assertRaisesRegex(ValidationError,'video no longer matches'): self.queue()

    def test_invalid_view_photo_or_report_refused(self):
        for payload in ({'view':'guess'}, {'image_index':True}, {'image_index':1}, {'path':'outside'}):
            with self.assertRaises(ValidationError): self.queue(**payload)
        with self.studio.db() as db:
            spec = {**self.parent_spec,'reference':'neutral','preset':'photo'}
            db.execute('UPDATE jobs SET spec=? WHERE id=?',(json.dumps(spec),self.parent_id))
        with self.assertRaises(ValidationError): self.queue()

    def test_live_queue_restart_resumes_verified_frame_reports_without_gpu(self):
        self.belt.stop_after = 1; self.belt.stop = self.studio.stop
        job = self.queue(); self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'queued')
        self.assertEqual(self.belt.targets,['frame_0000.png'])
        # Simulate abrupt termination while the CPU job is claimed/running.
        with self.studio.db() as db:
            db.execute("UPDATE jobs SET state='running', started=? WHERE id=?",
                       ((datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat(),job['id']))
        self.studio.close()
        self.studio = Studio(self.config,self.root,self.client,start_worker=False)
        self.addCleanup(self.studio.close)
        self.studio.identity_belt = self.belt
        self.belt.stop_after = None
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'needs_review')
        self.assertGreaterEqual(self.studio.job(job['id'])['seconds'],30)
        self.assertEqual(self.belt.targets,['frame_0000.png','frame_0001.png','frame_0002.png'])
        report = self.studio.anime_review_report(job['id'])
        self.assertEqual(len(report['frames']),3)
        self.client.request.assert_not_called()

    def test_changed_cached_report_rejected_on_resume(self):
        self.belt.stop_after=1; self.belt.stop=self.studio.stop
        job=self.queue(); self.studio.run_next(); self.studio.stop.clear()
        cached=work_dir(self.config,job['id'])/'frame_0000.json'; cached.write_text('{}')
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'failed')
        self.assertIn('Saved frame review changed',self.studio.job(job['id'])['error'])


    def test_model_change_after_queueing_refuses_old_measurements_without_gpu(self):
        job=self.queue()
        weights=Path(self.config['comfy_dir'])/'models/face_parsing/model.safetensors'
        weights.parent.mkdir(parents=True)
        weights.write_bytes(b'different examiner model')
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'failed')
        self.assertIn('Examiner code or model weights changed',self.studio.job(job['id'])['error'])
        self.assertEqual(self.belt.targets,[])

    def test_old_partial_review_cannot_resume_under_new_examiner(self):
        self.belt.stop_after=1; self.belt.stop=self.studio.stop
        job=self.queue(); self.studio.run_next(); self.studio.stop.clear()
        with self.studio.db() as db:
            spec=json.loads(db.execute('SELECT spec FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])
            spec['measurement_binding']['measurement_version']='legacy-v1'
            db.execute('UPDATE jobs SET spec=? WHERE id=?',(json.dumps(spec),job['id']))
        self.belt.stop_after=None
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'failed')
        self.assertIn('Examiner code or model weights changed',self.studio.job(job['id'])['error'])
        self.assertEqual(self.belt.targets,['frame_0000.png'])


if __name__ == '__main__': unittest.main()
