"""Frozen inputs, private preview, protection failure and existing resume journal."""
import io
import json
from pathlib import Path
import shutil
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from mesh_cleanup import freeze, build, finish, sha, MeshCleanupError
from server import Studio


class MeshCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config={'output_dir':str(self.root/'media/images'),'photo_dir':str(self.root/'photos'),
                     'comfy_dir':str(self.root/'comfy'),'comfy_url':'http://127.0.0.1:8188'}
        self.zone_dir=self.root/'artifacts/face_zones/2026-10/test'; self.zone_dir.mkdir(parents=True)
        self.source=self.root/'upload.png'; Image.new('RGB',(24,32),(110,65,40)).save(self.source)
        self.ref=self.root/'approved.png'; self.ref.write_bytes(self.source.read_bytes())
        self.reference={'path':str(self.ref),'sha256':sha(self.ref),'selected_view':'three-quarter'}
        artifacts={}
        for name in ['original','face_crop','identity_mesh_seed','hard_mask','soft_mask','graded_mask','hair_headwear_exclusion']:
            path=self.zone_dir/(name+'.png')
            if name=='original': path.write_bytes(self.source.read_bytes())
            elif name=='hair_headwear_exclusion': Image.new('L',(16,16),0).save(path)
            elif name.endswith('mask'):
                im=Image.new('L',(16,16),0); im.paste(255,(4,4,12,12)); im.save(path)
            else: Image.new('RGB',(16,16),(110,65,40)).save(path)
            artifacts[name]=str(path)
        self.zone=self.zone_dir/'face_zone.json'
        self.zone.write_text(json.dumps({'source':str(self.source),'source_sha256':sha(self.source),
            'manual_zone':False,'generated_parent':None,'upload_analysis':{'all_passed':True},
            'crop_preflight':{'passed':True},'identity_mesh':{'reference':str(self.ref),
                'reference_sha256':sha(self.ref),'eye_source_mode':'identity'},
            'artifacts':artifacts,'canvas_size':16,'crop_box':{'x':4,'y':8,'width':16,'height':16}}))
        scripts=self.root/'repo/scripts'; scripts.mkdir(parents=True)
        (scripts/'byrdfacezone.py').write_text('# bound CPU helper')
        (scripts/'facezone_composite.py').write_text('# bound material helper')
        workflow=self.root/'repo/workflows'; workflow.mkdir()
        shutil.copy2(Path(__file__).resolve().parents[2]/'workflows/sd15_face_mesh_seed_refine_api.json',workflow)
        self.binding=freeze(self.config,self.zone,self.reference)
        self.spec={'id':'c'*32,'operation':'mesh_cleanup','mesh_binding':self.binding,
            'checkpoint':'installed-anime.safetensors','full_prompt':'Black Carey portrait','negative':'blur',
            'seed':7124,'denoise':.18,'aspect':'portrait','engine':'sdxl','purpose':'Private Carey cleanup trial'}
        self.canon=patch('anime_view_review.reference_binding',return_value={k:v for k,v in self.reference.items() if k!='selected_view'})
        self.canon.start(); self.addCleanup(self.canon.stop)

    def test_saved_graph_preserves_encoded_identity_seed_and_masks_only_noise(self):
        graph=build(self.config,self.spec)
        self.assertEqual(graph['6']['class_type'],'VAEEncode')
        self.assertEqual(graph['11']['class_type'],'SetLatentNoiseMask')
        self.assertEqual(graph['7']['inputs']['latent_image'],['11',0])
        self.assertEqual(graph['1']['inputs']['ckpt_name'],'installed-anime.safetensors')
        self.assertEqual(graph['7']['inputs']['denoise'],.18)
        self.assertFalse(any(n['class_type']=='VAEEncodeForInpaint' for n in graph.values()))

    def test_changed_source_mask_or_helper_refuses_before_any_gpu_submission(self):
        client=Mock()
        studio=Studio(self.config,self.root,client,start_worker=False); self.addCleanup(studio.close)
        for key in ['source','graded_mask','helper_code']:
            path=Path(self.binding['files'][key]['path']); before=path.read_bytes()
            path.write_bytes(before+b'changed')
            with self.assertRaises(MeshCleanupError): studio.generate(self.spec)
            path.write_bytes(before)
        client.request.assert_not_called()

    def test_changed_canon_lock_refuses_even_when_reference_image_is_unchanged(self):
        with patch('anime_view_review.reference_binding',return_value={'path':str(self.ref),'sha256':sha(self.ref),'lock_sha256':'different'}):
            with self.assertRaises(MeshCleanupError): build(self.config,self.spec)

    def test_preparation_refuses_manual_wrong_view_or_failed_gate(self):
        before=json.loads(self.zone.read_text())
        for update in [{'manual_zone':True},{'upload_analysis':{'all_passed':False}},
                       {'identity_mesh':{**before['identity_mesh'],'reference_sha256':'0'*64}}]:
            self.zone.write_text(json.dumps({**before,**update}))
            with self.assertRaises(MeshCleanupError): freeze(self.config,self.zone,self.reference)

    def fake_helper(self,corrupt=False):
        def composite(zone_path,crop,out):
            image=Image.open(self.source).convert('RGB')
            image.paste((125,70,45),(8,12,16,20))
            if corrupt: image.putpixel((0,0),(255,0,0))
            image.save(out,'PNG')
        from facezone_composite import restore_protected_material
        return SimpleNamespace(__file__=self.binding['files']['helper_code']['path'],
                               composite_generated=composite,restore_protected_material=restore_protected_material)

    def test_composite_refuses_any_change_outside_frozen_edit_mask(self):
        target=self.root/'raw.png'; Image.new('RGB',(16,16),(100,60,35)).save(target)
        with patch('mesh_cleanup.importlib.import_module',return_value=self.fake_helper(corrupt=True)):
            with self.assertRaises(MeshCleanupError): finish(self.config,self.spec,target)
        with Image.open(target) as image: self.assertEqual(image.size,(16,16))

    def test_existing_submission_journal_recovers_same_crop_without_another_prompt(self):
        buffer=io.BytesIO(); Image.new('RGB',(16,16),(100,60,35)).save(buffer,'PNG')
        client=Mock()
        def request(route,body=None,binary=False):
            if route=='/prompt': return {'prompt_id':'same-mesh-prompt','node_errors':{}}
            if route.startswith('/history/'): return {'same-mesh-prompt':{'status':{'completed':True},'outputs':{'9':{'images':[{'filename':'crop.png','subfolder':'','type':'output'}]}}}}
            if route.startswith('/view?'): return buffer.getvalue()
            raise AssertionError(route)
        client.request.side_effect=request
        studio=Studio(self.config,self.root,client,start_worker=False); self.addCleanup(studio.close)
        studio.enqueue([self.spec])
        with patch('mesh_cleanup.importlib.import_module',return_value=self.fake_helper()):
            self.assertTrue(studio.run_next())
            self.assertEqual(studio.job(self.spec['id'])['state'],'needs_review')
            outputs=[studio.image_path(self.spec['id'],0).name]
            before=sha(studio.output_dir/outputs[0])
            self.assertEqual(studio.saved_prompt_id(self.spec),'same-mesh-prompt')
            recovered=studio.generate(self.spec,resume_prompt_id='same-mesh-prompt')
        self.assertEqual(outputs,recovered)
        self.assertEqual(sha(studio.output_dir/outputs[0]),before)
        self.assertEqual(sum(call.args[0]=='/prompt' for call in client.request.call_args_list),1)
        card=studio.metadata(self.spec['id'])
        self.assertEqual((card['width'],card['height']),(24,32))
        self.assertEqual(card['mesh_composite']['outside_mask_changed_pixels'],0)
        self.assertFalse(card['identity_verified']); self.assertTrue(card['private_evaluation_only'])
        self.assertEqual(card['review_state'],'needs_review')


if __name__=='__main__': unittest.main()
