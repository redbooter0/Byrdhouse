"""Current-PC and historical model lookup for the existing CPU alignment tool."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from byrdfacezone import _model_path, _parsenet_path, _selfie_segmenter_path, MODEL_NAME, _run_parsenet


class FaceZoneModelPathTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.config=self.root/'byrdhouse-local.json'

    def test_historical_root_keeps_existing_model_layout(self):
        self.assertEqual(_model_path(self.root),self.root/'Generators/ComfyUI/models/detection'/MODEL_NAME)

    def test_current_absolute_comfy_directory_resolves_all_existing_loaders(self):
        comfy=self.root/'current-comfy'
        self.config.write_text(json.dumps({'comfy_dir':str(comfy)}),encoding='utf-8-sig')
        self.assertEqual(_model_path(self.root),comfy/'models/detection'/MODEL_NAME)
        self.assertEqual(_parsenet_path(self.root).parent,comfy/'models/facedetection')
        self.assertEqual(_selfie_segmenter_path(self.root).parent,comfy/'models/segmentation')

    def test_current_relative_comfy_directory_resolves_against_named_root(self):
        self.config.write_text(json.dumps({'comfy_dir':'runtime/comfy'}))
        self.assertEqual(_model_path(self.root),self.root/'runtime/comfy/models/detection'/MODEL_NAME)

    def test_invalid_current_config_does_not_fall_back_to_unrelated_models(self):
        for content in ('{', '{}', '{"comfy_dir":null}'):
            self.config.write_text(content)
            with self.assertRaises(ValueError): _model_path(self.root)

    def test_parsenet_reuses_code_from_same_configured_comfy_as_weights(self):
        comfy=self.root/'current-comfy'
        self.config.write_text(json.dumps({'comfy_dir':str(comfy)}))
        import torch
        model=Mock(return_value=[torch.zeros((1,19,2,2))])
        with patch('byrdfacezone._verify_model'), patch('byrdfacezone._load_parsenet_model',return_value=model) as load:
            labels, metadata=_run_parsenet(self.root,Image.new('RGB',(2,2)))
        self.assertEqual(load.call_args.args,(str(comfy/'models/facedetection/parsing_parsenet.pth'),str(comfy/'custom_nodes/ComfyUI-ReActor')))
        self.assertEqual(labels.shape,(2,2))
        self.assertEqual(metadata['deployment_scope'],'private-local-evaluation-only')


if __name__=='__main__': unittest.main()
