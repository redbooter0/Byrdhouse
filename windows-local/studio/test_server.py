"""Exercise queue failure recovery and request/path boundaries without a GPU."""
import hashlib, io, json, tempfile, unittest, zipfile, threading
from pathlib import Path
from types import SimpleNamespace
from server import Studio, BackendError, ValidationError, build_graph, local_url
from identity_belt import BeltError
from PIL import Image

class FakeComfy:
    def models(self):
        return {'checkpoints':['base.safetensors'],'loras':['lightning.safetensors','carey.safetensors']}
    def request(self,*args,**kwargs):
        raise RuntimeError('Intentional backend failure')

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.config={'comfy_url':'http://127.0.0.1:8188','checkpoint':'base.safetensors',
            'lightning_lora':'lightning.safetensors','output_dir':str(self.root/'images'),
            'photo_dir':str(self.root/'photos')}
        self.config['comfy_input_dir'] = str(self.root/'comfy-input')
        self.studio=Studio(self.config,self.root,FakeComfy(),start_worker=False)
    def tearDown(self):
        self.studio.close(); self.tmp.cleanup()
    def test_failed_job_does_not_block_next(self):
        first=self.studio.create_job({'prompt':'first'})
        second=self.studio.create_job({'prompt':'second'})
        self.assertTrue(self.studio.run_next())
        self.assertEqual(self.studio.job(first['id'])['state'],'failed')
        self.assertEqual(self.studio.job(second['id'])['state'],'queued')
        self.assertTrue(self.studio.run_next())
        self.assertFalse(self.studio.run_next())
    def test_rejects_uninstalled_lora_and_invalid_values(self):
        for payload in [{'prompt':'a','lora':'../private'}, {'prompt':'a','seed':True},
                        {'prompt':'a','strength':float('nan')}, {'prompt':'a','mode':'unknown'}]:
            with self.assertRaises(ValidationError): self.studio.create_job(payload)
    def test_private_path_cannot_be_read(self):
        with self.assertRaises(FileNotFoundError): self.studio.image_path('../secret',0)

    def belt_sources(self):
        self.studio.reference_dir.mkdir(parents=True, exist_ok=True)
        (self.studio.reference_dir/'portrait.png').write_bytes(b'original Carey')
        self.studio.references={'portrait':{'file':'portrait.png','generated':False}}
        target=self.studio.output_dir/'local-target.png'; target.write_bytes(b'target')
        return target

    def test_correction_is_recorded_before_render_and_uses_the_shared_worker(self):
        target=self.belt_sources()
        earlier=self.studio.create_job({'prompt':'earlier render'})
        calls=[]
        studio=self.studio
        class Belt:
            def run(self,target,reference,label,**options):
                job_id=options['run_id']; calls.append(job_id)
                self_outer.assertEqual(studio.job(job_id)['state'],'running')
                options['submitted']('correction-prompt')
                path=studio.output_dir/f'belt-{job_id}.png'; path.write_bytes(b'corrected')
                return {'file':path.name,'report':path.name+'.json','analysis':path.name+'-analysis.png',
                        'selected':{'name':'restored','similarity':0.89},'accepted':False,'elapsed_seconds':1}
        self_outer=self
        self.studio.identity_belt=Belt()
        correction=self.studio.run_identity_belt({'target':target.name,'reference':'portrait'})
        self.assertEqual(correction['state'],'queued')
        self.assertEqual(calls,[])
        self.studio.run_next()
        self.assertEqual(self.studio.job(earlier['id'])['state'],'failed')
        self.assertEqual(calls,[])
        self.studio.run_next()
        result=self.studio.job(correction['id'])
        self.assertEqual(result['state'],'needs_review')
        self.assertEqual(result['prompt_id'],'correction-prompt')
        self.assertEqual(calls,[correction['id']])
        self.assertEqual(len(self.studio.jobs()),2)
        self.assertEqual(target.read_bytes(),b'target')
        self.assertFalse(self.studio.metadata(correction['id'])['identity_verified'])

    def test_queued_correction_rejects_changed_source_before_rendering(self):
        target=self.belt_sources()
        job=self.studio.run_identity_belt({'target':target.name,'reference':'portrait'})
        target.write_bytes(b'changed target')
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'failed')
        self.assertIn('source changed',self.studio.job(job['id'])['error'])
        self.assertIsNone(self.studio.identity_belt)

    def test_anime_anchor_face_detection_gap_records_inconclusive_review(self):
        self.studio.reference_dir.mkdir(parents=True, exist_ok=True)
        anchor = self.studio.reference_dir / 'anchor.png'
        anchor.write_bytes(b'approved anchor')
        target = self.studio.output_dir / 'anime-render.png'
        target.write_bytes(b'illustrated render')
        target.with_suffix('.png.json').write_text('{}', encoding='utf-8')
        self.studio.references = {'carey-anime-anchor': {'file': 'anchor.png', 'generated': True}}
        self.studio.config['anime_reference_id'] = 'carey-anime-anchor'

        class ReferenceFace:
            def public(self):
                return {'file': str(anchor), 'bbox': [0, 0, 1, 1], 'metrics': {}}

        class Belt:
            def inspect(self, path, *, illustrated=False):
                self_test.assertTrue(illustrated)
                if Path(path).name == 'anchor.png':
                    return ReferenceFace()
                raise BeltError('No face detected in anime-render.png')

        self_test = self
        self.studio.identity_belt = Belt()
        result = self.studio.analyze_generated_identity(
            {'identity_mode': 'anime_anchor'}, ['anime-render.png'])
        self.assertFalse(result['automatic_gates_passed'])
        self.assertIsNone(result['similarity'])
        report = json.loads((self.studio.output_dir / 'anime-render-identity-analysis.json').read_text())
        self.assertIn('could not locate a usable face', report['visual_review']['findings'][0]['difference'])

    def test_anime_canon_profile_rejects_changed_anchor_or_feature_targets(self):
        reference = self.root / 'approved-anime.png'
        reference.write_bytes(b'locked illustrated Carey')
        digest = hashlib.sha256(reference.read_bytes()).hexdigest()
        self.studio.references = {'carey-anime-anchor': {'source_sha256': digest}}
        keys = ('hairline_y_ratio', 'forehead_height_ratio', 'hair_width_ratio',
                'hair_height_ratio', 'face_aspect_ratio')
        metrics = {key: 0.4 for key in keys}
        path = self.root / 'canon-profile.json'
        profile = {'schema': 'byrdhouse.carey-anime-canon-profile.v1',
                   'status': 'measured_from_approved_anchor',
                   'reference_id': 'carey-anime-anchor', 'anchor_sha256': digest,
                   'metrics': metrics}
        path.write_text(json.dumps(profile), encoding='utf-8')
        self.studio.config['anime_canon_profile'] = str(path)
        result = self.studio.verify_anime_canon_profile(
            'carey-anime-anchor', reference, SimpleNamespace(metrics=metrics))
        self.assertEqual(result['status'], 'verified')
        reference.write_bytes(b'changed')
        with self.assertRaisesRegex(BeltError, 'hashes differ'):
            self.studio.verify_anime_canon_profile(
                'carey-anime-anchor', reference, SimpleNamespace(metrics=metrics))
        reference.write_bytes(b'locked illustrated Carey')
        changed = dict(metrics, hair_width_ratio=1.4)
        with self.assertRaisesRegex(BeltError, 'hair_width_ratio'):
            self.studio.verify_anime_canon_profile(
                'carey-anime-anchor', reference, SimpleNamespace(metrics=changed))
        from identity_belt import MEASUREMENT_VERSION, measurement_binding
        self.studio.config.setdefault('comfy_dir', str(self.root/'comfy'))
        current=dict(metrics, measurement_version=MEASUREMENT_VERSION)
        with self.assertRaisesRegex(BeltError, 'different examiner version'):
            self.studio.verify_anime_canon_profile(
                'carey-anime-anchor', reference, SimpleNamespace(metrics=current))
        profile['measurement_version']=MEASUREMENT_VERSION
        profile['measurement_binding']=measurement_binding(self.studio.config)
        path.write_text(json.dumps(profile), encoding='utf-8')
        self.assertEqual(self.studio.verify_anime_canon_profile(
            'carey-anime-anchor', reference, SimpleNamespace(metrics=current))['status'],'verified')
        profile['measurement_binding']['measurement_version']='wrong'
        path.write_text(json.dumps(profile), encoding='utf-8')
        with self.assertRaisesRegex(BeltError, 'model weights changed'):
            self.studio.verify_anime_canon_profile(
                'carey-anime-anchor', reference, SimpleNamespace(metrics=current))

    def test_anime_canon_anchor_can_enter_reviewed_scene_mask_route(self):
        self.studio.reference_dir.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (64, 64), '#6d4a35').save(self.studio.reference_dir / 'anchor.png')
        self.studio.references = {'carey-anime-anchor': {
            'id': 'carey-anime-anchor', 'file': 'anchor.png', 'generated': True}}
        self.studio.config['anime_reference_id'] = 'carey-anime-anchor'
        self.studio.state = lambda: {'source_mask_ready': True}
        job = self.studio.create_source_mask({'reference': 'carey-anime-anchor', 'region': 'background'})
        self.assertEqual(job['identity_mode'], 'anime_source_preserve')
        self.assertTrue(job['anime_anchor_scene'])
        self.assertEqual(job['reference_snapshot']['source_kind'], 'reference_file')

    def test_only_one_worker_can_execute_even_if_run_next_is_called_concurrently(self):
        first=self.studio.create_job({'prompt':'first'})
        second=self.studio.create_job({'prompt':'second'})
        entered=threading.Event(); release=threading.Event(); calls=[]
        def generate(spec):
            calls.append(spec['id']); entered.set()
            if not release.wait(3): raise AssertionError('test worker never released')
            return []
        self.studio.generate=generate
        thread=threading.Thread(target=self.studio.run_next); thread.start()
        try:
            self.assertTrue(entered.wait(3))
            self.assertFalse(self.studio.run_next())
            self.assertEqual(self.studio.job(second['id'])['state'],'queued')
        finally:
            release.set(); thread.join(3)
        self.assertEqual(calls,[first['id']])

    def test_restart_collects_existing_still_without_submitting_another_prompt(self):
        job=self.studio.create_job({'prompt':'resume this render'})
        class Pending(FakeComfy):
            def request(self,endpoint,payload=None,binary=False):
                if endpoint=='/prompt': return {'prompt_id':'saved-prompt'}
                raise BackendError('Cannot reach local ComfyUI: disconnected')
        self.studio.client=Pending()
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'recovering')
        calls=[]
        class Completed(FakeComfy):
            def request(self,endpoint,payload=None,binary=False):
                calls.append(endpoint)
                if endpoint.startswith('/history/'):
                    return {'saved-prompt':{'status':{'completed':True},'outputs':{'9':{'images':[{'filename':'preview.png','type':'output'}]}}}}
                if endpoint.startswith('/view?'): return b'\x89PNG\r\n\x1a\nrestored'
                raise AssertionError('unexpected submission: '+endpoint)
        self.studio.close()
        # Changing the installed default must not change a submitted workflow.
        self.config['checkpoint']='different-default.safetensors'
        self.studio=Studio(self.config,self.root,Completed(),start_worker=False)
        self.assertEqual(self.studio.job(job['id'])['state'],'recovering')
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'needs_review')
        self.assertEqual(self.studio.metadata(job['id'])['checkpoint'],'base.safetensors')
        self.assertNotIn('/prompt',calls)

    def test_completion_between_history_and_queue_reads_is_reconciled(self):
        calls=[]
        def request(endpoint,*args,**kwargs):
            calls.append(endpoint)
            if endpoint=='/queue': return {'queue_pending':[],'queue_running':[]}
            if calls.count(endpoint)==1: return {}
            return {'prompt':{'status':{'completed':True}}}
        self.studio.client.request=request
        self.studio.reconcile_prompt('prompt')
        self.assertEqual(calls,['/history/prompt','/queue','/history/prompt'])

    def test_callback_failure_recovers_durable_id_without_submitting_again(self):
        target=self.belt_sources()
        job=self.studio.run_identity_belt({'target':target.name,'reference':'portrait'})
        def interrupted(spec):
            path=self.studio.output_dir/f"belt-{spec['id']}.submission.json"
            path.write_text(json.dumps({'prompt_id':'durable-prompt'}))
            raise RuntimeError('Callback failed after durable journal write')
        self.studio.generate=interrupted
        self.assertFalse(self.studio.run_next())
        recovered=self.studio.job(job['id'])
        self.assertEqual(recovered['state'],'recovering')
        self.assertEqual(recovered['prompt_id'],'durable-prompt')

    def test_recovery_button_queues_saved_prompt_without_new_settings_or_submission(self):
        job=self.studio.create_job({'prompt':'recover existing output'})
        with self.studio.db() as db:
            db.execute("UPDATE jobs SET state='failed',prompt_id='saved-render',error='collection failed' WHERE id=?",(job['id'],))
        recovered=self.studio.recover_job(job['id'])
        self.assertEqual(recovered['state'],'recovering')
        self.assertEqual(recovered['prompt_id'],'saved-render')
        self.assertEqual(recovered['prompt'],'recover existing output')
        self.assertIsNone(recovered['error'])
        with self.assertRaises(ValidationError): self.studio.recover_job(job['id'])

    def test_unknown_or_unsubmitted_job_cannot_be_recovered(self):
        job=self.studio.create_job({'prompt':'no backend submission'})
        with self.studio.db() as db:
            db.execute("UPDATE jobs SET state='failed' WHERE id=?",(job['id'],))
        for job_id in (job['id'],'b'*32,'../private'):
            with self.assertRaises(ValidationError): self.studio.recover_job(job_id)

    def test_recovery_observation_failure_keeps_job_and_stops_later_submission(self):
        job=self.studio.create_job({'prompt':'recover'})
        later=self.studio.create_job({'prompt':'wait behind recovery'})
        with self.studio.db() as db:
            db.execute("UPDATE jobs SET state='running',prompt_id='saved-prompt' WHERE id=?",(job['id'],))
        class Offline(FakeComfy):
            def request(self,*args,**kwargs): raise BackendError('Cannot reach local ComfyUI: timed out')
        self.studio.close()
        self.studio=Studio(self.config,self.root,Offline(),start_worker=False)
        self.assertFalse(self.studio.run_next())
        self.assertEqual(self.studio.job(job['id'])['state'],'recovering')
        self.assertEqual(self.studio.job(later['id'])['state'],'queued')
        self.assertEqual(self.studio.job(job['id'])['prompt_id'],'saved-prompt')

    def test_restart_without_submission_id_refuses_automatic_retry(self):
        job=self.studio.create_job({'prompt':'ambiguous interruption'})
        with self.studio.db() as db:
            db.execute("UPDATE jobs SET state='running' WHERE id=?",(job['id'],))
        self.studio.close()
        self.studio=Studio(self.config,self.root,FakeComfy(),start_worker=False)
        self.assertEqual(self.studio.job(job['id'])['state'],'failed')
        self.assertIn('no automatic resubmission',self.studio.job(job['id'])['error'])
        self.assertFalse(self.studio.run_next())

    def test_restart_adopts_durable_belt_prompt_after_callback_crash(self):
        target=self.belt_sources()
        job=self.studio.run_identity_belt({'target':target.name,'reference':'portrait'})
        journal=self.studio.output_dir/f"belt-{job['id']}.submission.json"
        journal.write_text(json.dumps({'prompt_id':'durable-correction-id'}))
        with self.studio.db() as db:
            db.execute("UPDATE jobs SET state='running' WHERE id=?",(job['id'],))
        self.studio.close()
        self.studio=Studio(self.config,self.root,FakeComfy(),start_worker=False)
        recovered=self.studio.job(job['id'])
        self.assertEqual(recovered['state'],'recovering')
        self.assertEqual(recovered['prompt_id'],'durable-correction-id')

    def test_missing_backend_submission_is_not_resubmitted(self):
        job=self.studio.create_job({'prompt':'lost backend record'})
        with self.studio.db() as db:
            db.execute("UPDATE jobs SET state='running',prompt_id='missing-id' WHERE id=?",(job['id'],))
        calls=[]
        class Empty(FakeComfy):
            def request(self,endpoint,*args,**kwargs):
                calls.append(endpoint)
                if endpoint.startswith('/history/'): return {}
                if endpoint=='/queue': return {'queue_pending':[],'queue_running':[]}
                raise AssertionError(endpoint)
        self.studio.close()
        self.studio=Studio(self.config,self.root,Empty(),start_worker=False)
        self.studio.run_next()
        self.assertEqual(self.studio.job(job['id'])['state'],'failed')
        self.assertNotIn('/prompt',calls)

    def test_animation_requires_approved_still_and_keeps_reference(self):
        parent=self.studio.create_job({'prompt':'review this face'})
        path=self.studio.output_dir/(parent['id']+'_1.png'); path.write_bytes(b'photo')
        with self.studio.db() as db:
            spec=json.loads(db.execute('SELECT spec FROM jobs WHERE id=?',(parent['id'],)).fetchone()[0])
            spec['reference']='portrait'
            db.execute('UPDATE jobs SET state=?,outputs=?,spec=? WHERE id=?',
                       ('needs_review',json.dumps([path.name]),json.dumps(spec),parent['id']))
        with self.assertRaisesRegex(ValidationError,'Keep the still'):
            self.studio.create_animation({'source_job_id':parent['id']})
        with self.studio.db() as db: db.execute("UPDATE jobs SET state='approved' WHERE id=?",(parent['id'],))
        motion=self.studio.create_animation({'source_job_id':parent['id']})
        self.assertEqual(motion['parent_job_id'],parent['id'])
        self.assertEqual(motion['reference'],'portrait')
        self.assertEqual(motion['state'],'queued')
        self.assertEqual(motion['operation'],'portrait_animation')
        with self.studio.db() as db: db.execute("UPDATE jobs SET state='rejected' WHERE id=?",(parent['id'],))
        with self.assertRaises(ValidationError): self.studio.animation_source(motion)

    def test_original_photo_animation_records_exact_source_hash(self):
        import hashlib
        self.studio.reference_dir.mkdir(parents=True,exist_ok=True)
        (self.studio.reference_dir/'portrait.png').write_bytes(b'original-photo')
        self.studio.references={'portrait':{'file':'portrait.png','generated':False}}
        job=self.studio.create_animation({'reference':'portrait'})
        self.assertEqual(job['animation_source_sha256'],hashlib.sha256(b'original-photo').hexdigest())
        self.assertIsNone(job['video_url'])
        self.studio.references['portrait']['generated']=True
        with self.assertRaises(ValidationError): self.studio.create_animation({'reference':'portrait'})

    def test_approved_illustrated_canon_anchor_can_be_animated(self):
        self.studio.reference_dir.mkdir(parents=True, exist_ok=True)
        anchor = self.studio.reference_dir/'anime.png'; anchor.write_bytes(b'illustrated-canon')
        self.studio.references = {'anime': {'id': 'anime', 'file': 'anime.png', 'generated': True}}
        self.studio.config['animation_allowed_illustrated_references'] = ['anime']
        job = self.studio.create_animation({'reference': 'anime'})
        self.assertEqual(job['reference'], 'anime')
        self.assertEqual(job['animation_source_sha256'], hashlib.sha256(b'illustrated-canon').hexdigest())

    def test_animation_rejects_paths_and_does_not_expose_still_as_video(self):
        for payload in ({'source_job_id':'../private'},{'reference':[]},{'file':'C:/private.png'}):
            with self.assertRaises(ValidationError): self.studio.create_animation(payload)
        with self.assertRaises(FileNotFoundError): self.studio.video_path('../private')

    def test_motion_review_updates_both_sidecars_without_verifying_identity(self):
        job_id='a'*32
        spec={'id':job_id,'seed':0,'operation':'portrait_animation','prompt':'motion'}
        poster=self.studio.output_dir/(job_id+'_1.png'); poster.write_bytes(b'poster')
        movie=self.studio.output_dir/(job_id+'.mp4'); movie.write_bytes(b'video')
        card={'purpose':'motion preview','review_state':'needs_review','identity_verified':False}
        poster.with_suffix('.png.json').write_text(json.dumps(card))
        movie.with_suffix('.mp4.json').write_text(json.dumps(card))
        with self.studio.db() as db:
            db.execute('INSERT INTO jobs(id,state,created,spec,outputs) VALUES(?,?,?,?,?)',
                       (job_id,'needs_review','now',json.dumps(spec),json.dumps([poster.name])))
        self.studio.review(job_id,'approved')
        for sidecar in (poster.with_suffix('.png.json'),movie.with_suffix('.mp4.json')):
            reviewed=json.loads(sidecar.read_text())
            self.assertEqual(reviewed['review_state'],'approved')
            self.assertFalse(reviewed['identity_verified'])

    def test_corrected_still_has_own_review_record_and_preserves_parent(self):
        parent = self.studio.create_job({'prompt': 'gallery portrait', 'seed': 12})
        original = self.studio.output_dir / (parent['id'] + '_1.png')
        original.write_bytes(b'original')
        with self.studio.db() as db:
            db.execute('UPDATE jobs SET state=?,outputs=? WHERE id=?',
                       ('needs_review', json.dumps([original.name]), parent['id']))
        corrected = self.studio.output_dir / 'belt-test.png'
        corrected.write_bytes(b'corrected')
        result = {'file': corrected.name, 'report': 'belt-test.png.json',
                  'analysis': 'belt-test.png-analysis.png',
                  'selected': {'name': 'restored', 'similarity': 0.89},
                  'accepted': False, 'elapsed_seconds': 12.0}
        new_id = self.studio.register_belt_candidate(original, 'portrait', result)
        job = self.studio.job(new_id)
        self.assertEqual(job['state'], 'needs_review')
        self.assertEqual(job['parent_job_id'], parent['id'])
        self.assertEqual(job['operation'], 'identity_belt')
        self.assertEqual(job['belt_analysis'], result['analysis'])
        self.assertEqual(self.studio.image_path(new_id, 0).read_bytes(), b'corrected')
        self.assertEqual(original.read_bytes(), b'original')
        card = json.loads(self.studio.image_path(new_id, 0).with_suffix('.png.json').read_text())
        self.assertFalse(card['identity_verified'])
        self.assertFalse(card['measurement_checks_passed'])
    def test_fast_acceleration_and_identity_chain(self):
        job=self.studio.create_job({'prompt':'byrdcarey man','lora':'carey.safetensors','mode':'fast'})
        graph=build_graph(self.config,job)
        self.assertEqual(graph['3']['inputs']['model'],['2',0])
        self.assertEqual(graph['7']['inputs']['steps'],4)
        self.assertEqual(graph['7']['inputs']['scheduler'],'sgm_uniform')
    def test_no_remote_backend_or_credentials(self):
        for url in ['https://example.com','http://127.0.0.1@evil.test','http://localhost/path']:
            with self.assertRaises(ValidationError): local_url(url)
    def test_carey_defaults_add_trigger_and_choose_installed_identity(self):
        self.studio.config.update(identity_lora='carey.safetensors', identity_trigger='byrdcarey man')
        job=self.studio.create_job({'prompt':'on a rooftop','lora':''})
        self.assertEqual(job['lora'],'carey.safetensors')
        self.assertTrue(job['full_prompt'].startswith('photo of byrdcarey man, Black man'))
        self.assertEqual(job['mode'],'quality')
    def test_reference_mode_refuses_missing_models(self):
        with self.assertRaises(ValidationError):
            self.studio.create_job({'prompt':'portrait','identity_mode':'reference'})

    def test_faceid_uses_upstream_paired_loader(self):
        spec = self.studio.make_spec({'prompt': 'portrait', 'mode': 'quality'})
        spec.update(identity_mode='reference', reference_image='Carey/portrait.jpeg', reference_strength=0.72)
        graph = build_graph(self.config, spec)
        self.assertEqual(graph['11']['class_type'], 'IPAdapterUnifiedLoaderFaceID')
        self.assertEqual(graph['11']['inputs']['preset'], 'FACEID PLUS V2')
        self.assertGreater(graph['11']['inputs']['lora_strength'], 0)
        self.assertEqual(graph['14']['inputs']['model'], ['11', 0])
        self.assertEqual(graph['14']['inputs']['ipadapter'], ['11', 1])

    def test_baked_lightning_checkpoint_does_not_get_another_lightning_lora(self):
        spec = self.studio.make_spec({'prompt': 'portrait', 'mode': 'fast'})
        graph = build_graph({**self.config, 'fast_checkpoint': 'RealVisXL_V5.0_Lightning_fp16.safetensors'}, spec)
        self.assertEqual(graph['1']['inputs']['ckpt_name'], 'RealVisXL_V5.0_Lightning_fp16.safetensors')
        self.assertNotIn('3', graph)
        self.assertEqual(graph['7']['inputs']['steps'], 5)
        self.assertEqual(graph['7']['inputs']['sampler_name'], 'dpmpp_sde')
        self.assertEqual(graph['7']['inputs']['scheduler'], 'karras')
        self.assertEqual(graph['7']['inputs']['cfg'], 1.5)

    def test_pulid_uses_the_frozen_three_photo_board_and_real_pose_control(self):
        spec = {'id': 'pulid-test', 'engine': 'sdxl', 'identity_mode': 'pulid',
                'lora': '', 'strength': 0.0, 'mode': 'fast', 'aspect': 'portrait',
                'preset': 'photo', 'seed': 42, 'full_prompt': 'Carey in a studio',
                'pulid_reference_images': ['ByrdHouse/references/a/reference.png',
                                           'ByrdHouse/references/b/reference.png',
                                           'ByrdHouse/references/c/reference.png'],
                'pulid_pose_image': 'ByrdHouse/references/d/reference.png'}
        config = {**self.config, 'fast_checkpoint': 'RealVisXL_V5.0_Lightning_fp16.safetensors',
                  'pulid_steps': 8, 'pulid_cfg': 2.0}
        graph = build_graph(config, spec)
        self.assertEqual(graph['17']['class_type'], 'ImageBatch')
        self.assertEqual(graph['21']['class_type'], 'ApplyPulidAdvanced')
        self.assertEqual(graph['24']['class_type'], 'SDPoseKeypointExtractor')
        self.assertEqual(graph['27']['inputs']['type'], 'openpose')
        self.assertEqual(graph['7']['inputs']['positive'], ['28', 0])
        self.assertEqual(graph['7']['inputs']['steps'], 8)
        self.assertEqual(graph['7']['inputs']['cfg'], 2.0)

    def test_anime_anchor_uses_existing_ipadapter_and_pose_control_pattern(self):
        spec = {'id': 'anime-test', 'engine': 'sdxl', 'identity_mode': 'anime_anchor',
                'lora': '', 'strength': 0.0, 'mode': 'quality', 'aspect': 'portrait',
                'preset': 'anime', 'seed': 42, 'full_prompt': 'anime Carey in Brambleton',
                'reference_image': 'ByrdHouse/references/anime/reference.png',
                'anime_pose_image': 'ByrdHouse/references/pose/reference.png'}
        config = {**self.config, 'anime_checkpoint': 'animagine-xl-4.0-opt.safetensors',
                  'anime_steps': 30, 'anime_cfg': 4.0, 'anime_face_detailer': True,
                  'anime_img2img_denoise': 0.38}
        graph = build_graph(config, spec)
        self.assertEqual(graph['1']['inputs']['ckpt_name'], 'animagine-xl-4.0-opt.safetensors')
        self.assertEqual(graph['11']['class_type'], 'IPAdapterUnifiedLoader')
        self.assertEqual(graph['11']['inputs']['preset'], 'PLUS FACE (portraits)')
        self.assertEqual(graph['12']['inputs']['weight_type'], 'style transfer precise')
        self.assertEqual(graph['18']['inputs']['type'], 'openpose')
        self.assertEqual(graph['20']['class_type'], 'VAEEncode')
        self.assertEqual(graph['7']['inputs']['latent_image'], ['20', 0])
        self.assertEqual(graph['7']['inputs']['denoise'], 0.38)
        self.assertEqual(graph['30']['class_type'], 'UltralyticsDetectorProvider')
        self.assertEqual(graph['31']['class_type'], 'SAMLoader')
        self.assertEqual(graph['33']['class_type'], 'FaceDetailerPipe')
        self.assertEqual(graph['33']['inputs']['denoise'], 0.22)
        self.assertEqual(graph['32']['inputs']['Select to add Wildcard'], 'Select the Wildcard to add to the text')
        self.assertEqual(graph['9']['inputs']['images'], ['33', 0])
        self.assertEqual(graph['7']['inputs']['positive'], ['19', 0])
        self.assertEqual(graph['7']['inputs']['steps'], 30)

    def test_civitai_anime_lab_starts_new_latent_from_cropped_approved_face(self):
        spec = {'id': 'anime-civitai-lab', 'engine': 'sdxl', 'identity_mode': 'anime_anchor',
                'anime_scene_mode': 'civitai_new_scene_lab', 'lora': '', 'strength': 0.0,
                'mode': 'quality', 'aspect': 'square', 'preset': 'anime', 'seed': 42,
                'full_prompt': 'Carey in a new Brambleton scene',
                'reference_image': 'ByrdHouse/references/anime/reference.png',
                'anime_pose_image': 'ByrdHouse/references/pose/reference.png'}
        graph = build_graph({**self.config, 'anime_checkpoint': 'animagine-xl-4.0-opt.safetensors'}, spec)
        self.assertEqual(graph['21']['class_type'], 'ImageCrop')
        self.assertEqual(graph['21']['inputs']['image'], ['10', 0])
        self.assertEqual(graph['12']['inputs']['image'], ['21', 0])
        self.assertEqual(graph['7']['inputs']['latent_image'], ['6', 0])
        self.assertEqual(graph['7']['inputs']['denoise'], 1.0)
        self.assertEqual(graph['18']['inputs']['type'], 'openpose')
        self.assertNotIn('20', graph)

    def test_anime_scene_mode_requires_anime_identity(self):
        with self.assertRaisesRegex(ValidationError, 'requires the approved anime'):
            self.studio.make_spec({'prompt': 'Carey', 'anime_scene_mode': 'civitai_new_scene_lab'})

    def test_photo_edit_preserves_reference_latent_and_skips_ipadapter(self):
        spec = {'id': 'photo-edit-test', 'engine': 'sdxl', 'identity_mode': 'photo_edit',
                'lora': '', 'strength': 0.0, 'mode': 'quality', 'aspect': 'square',
                'preset': 'photo', 'seed': 42, 'denoise': 0.45,
                'reference_image': 'ByrdHouse/carey/smile.png',
                'full_prompt': 'Edit Carey, keep his exact face.'}
        graph = build_graph(self.config, spec)
        self.assertEqual(graph['11']['class_type'], 'ImageScale')
        self.assertEqual(graph['12']['class_type'], 'VAEEncode')
        self.assertEqual(graph['7']['inputs']['latent_image'], ['12', 0])
        self.assertEqual(graph['7']['inputs']['denoise'], 0.45)
        self.assertFalse(any(node['class_type'].startswith('IPAdapter') for node in graph.values()))

    def test_photo_edit_mode_forces_quality_and_drops_lora(self):
        from PIL import Image
        self.studio.reference_dir.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (16, 16), '#754f37').save(self.studio.reference_dir/'smile.png')
        self.studio.references = {'smile': {'id': 'smile', 'file': 'smile.png',
                                            'label': 'Carey', 'comfy_image': 'ByrdHouse/carey/smile.png',
                                            'source_sha256': '0'*64}}
        spec = self.studio.make_spec({'prompt': 'black t-shirt portrait', 'identity_mode': 'photo_edit',
                                      'reference': 'smile', 'lora': 'carey.safetensors', 'mode': 'fast'})
        self.assertEqual(spec['mode'], 'quality')
        self.assertEqual(spec['lora'], '')
        self.assertEqual(spec['denoise'], 0.45)
        self.assertEqual(spec['reference'], 'smile')
    def test_carey_reference_requirement_cannot_be_bypassed(self):
        self.studio.config['require_carey_reference']=True
        with self.assertRaisesRegex(ValidationError,'requires your photo'):
            self.studio.create_job({'prompt':'portrait','identity_mode':'lora'})
    def test_flux_refuses_incomplete_install_instead_of_falling_back(self):
        with self.assertRaisesRegex(ValidationError,'FLUX'):
            self.studio.create_job({'prompt':'portrait','engine':'flux'})
        self.assertEqual(self.studio.jobs(),[])
    def test_flux_uses_real_photo_and_excludes_incompatible_sdxl_loras(self):
        from PIL import Image
        self.studio.reference_dir.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (16, 16), '#754f37').save(self.studio.reference_dir/'smile.png')
        self.studio.config.update(flux_model='flux.safetensors',flux_text_encoder='qwen.safetensors',flux_vae='vae.safetensors')
        self.studio.references={'smile':{'id':'smile','file':'smile.png','label':'Carey','comfy_image':'ByrdHouse/carey/smile.png','source_sha256':'0'*64}}
        self.studio.cached_models={**FakeComfy().models(),'connected':True,'error':None,
            'diffusion_models':['flux.safetensors'],'text_encoders':['qwen.safetensors'],'vaes':['vae.safetensors'],
            'nodes':['ReferenceLatent','Flux2Scheduler','EmptyFlux2LatentImage','BasicGuider','SamplerCustomAdvanced']}
        import time
        self.studio.models_checked=time.monotonic()
        job=self.studio.create_job({'prompt':'navy blazer','engine':'flux','reference':'smile','lora':'carey.safetensors'})
        graph=build_graph(self.studio.config,job)
        self.assertEqual(job['lora'],'')
        self.assertEqual(graph['10']['inputs']['image'],job['reference_snapshot']['comfy_image'])
        self.assertIn(job['id'],graph['10']['inputs']['image'])
        self.assertEqual(graph['12']['inputs']['latent'],['11',0])
        self.assertEqual(graph['16']['inputs']['steps'],4)
        self.assertIn('SAME man',graph['4']['inputs']['text'])
        self.assertIn('Black man',graph['4']['inputs']['text'])
        self.assertFalse(any(node['class_type']=='LoraLoader' for node in graph.values()))
    def test_history_timeout_does_not_duplicate_submission_or_lose_image(self):
        spec=self.studio.make_spec({'prompt':'Carey portrait'})
        calls=[]
        timeouts=[True]
        def request(endpoint,payload=None,binary=False):
            calls.append(endpoint)
            if endpoint=='/prompt': return {'prompt_id':'already-submitted'}
            if endpoint.startswith('/history/'):
                if timeouts:
                    timeouts.pop(); raise BackendError('Cannot reach local ComfyUI: timed out')
                return {'already-submitted':{'status':{'completed':True},'outputs':{'9':{'images':[{'filename':'preview.png','type':'output'}]}}}}
            if endpoint.startswith('/view?'): return b'\x89PNG\r\n\x1a\nlocal-test'
            raise AssertionError(endpoint)
        self.studio.client.request=request
        outputs=self.studio.generate(spec)
        self.assertEqual(calls.count('/prompt'),1)
        self.assertTrue((self.root/'images'/outputs[0]).is_file())
        calls.clear()
        self.studio.generate(spec,resume_prompt_id='already-submitted')
        self.assertNotIn('/prompt',calls)
    def test_pack_seed_variations_and_atomic_queue_limit(self):
        pack=self.studio.create_pack({'recipe':'angles','seed':1234,'versions':2})
        jobs=self.studio.pack(pack['id'])['jobs']
        self.assertEqual(len(jobs),12)
        self.assertEqual([int(job['seed']) for job in jobs],list(range(1234,1246)))
        # A whole pack is refused if capacity would be exceeded; no partial insert.
        with self.studio.db() as db:
            db.executemany('INSERT INTO jobs(id,state,created,spec) VALUES(?,?,?,?)',
                [('extra'+str(n),'queued','now','{}') for n in range(50)])
        with self.assertRaises(ValidationError): self.studio.create_pack({'recipe':'angles'})
        with self.studio.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],62)
    def test_export_omits_rejected_candidates_and_keeps_metadata(self):
        pack=self.studio.create_pack({'recipe':'angles'})
        for index,job in enumerate(self.studio.pack(pack['id'])['jobs']):
            path=self.root/'images'/(job['id']+'.png')
            path.write_bytes(b'png-test')
            path.with_suffix('.png.json').write_text(json.dumps({'purpose':'animation still','seed':job['seed']}))
            with self.studio.db() as db:
                db.execute('UPDATE jobs SET state=?,outputs=? WHERE id=?',
                    ('rejected' if index==0 else 'needs_review',json.dumps([path.name]),job['id']))
        with zipfile.ZipFile(io.BytesIO(self.studio.export_pack(pack['id']))) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            self.assertEqual(len(manifest['images']),5)
            self.assertTrue(all(row['review_state']=='needs_review' for row in manifest['images']))
            self.assertTrue(all(row['file']+'.json' in archive.namelist() for row in manifest['images']))

if __name__=='__main__': unittest.main()
