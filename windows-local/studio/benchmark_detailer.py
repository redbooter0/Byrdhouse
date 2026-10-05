"""Private evaluation of upstream Impact FaceDetailer after the existing ReActor pass.

Reuses the saved Studio graph and the installed upstream FaceDetailer example.
No model training or custom image synthesis; outputs always need review.
"""
import argparse
import copy
import json
import shutil
import time
from pathlib import Path

from identity_belt import IdentityBelt
from server import ComfyClient, load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path(r'D:\ByrdHouse\byrdhouse-local.json'))
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--label', default='upstream-detailer')
    args = parser.parse_args()
    config = load_config(args.config)
    client = ComfyClient(config['comfy_url'])
    belt = IdentityBelt(config, client)
    card = json.loads(args.card.read_text(encoding='utf-8'))
    graph = copy.deepcopy(card['workflow'])
    for key in ['6', '7', '8', '9']:
        graph.pop(key, None)
    run = belt._safe_name(args.label) + '-' + str(time.time_ns())
    source, reference = belt._input_copy(run, args.target,
        Path(config['reference_dir']) / 'portrait.jpeg')
    graph['10']['inputs']['image'] = reference
    graph['target'] = {'class_type': 'LoadImage', 'inputs': {'image': source}}
    graph['detector'] = {'class_type': 'UltralyticsDetectorProvider',
                         'inputs': {'model_name': 'bbox/face_yolov8m.pt'}}
    graph['sam'] = {'class_type': 'SAMLoader',
                    'inputs': {'model_name': 'sam_vit_b_01ec64.pth', 'device_mode': 'AUTO'}}
    outputs = {}
    for index, denoise in enumerate((0.20, 0.35)):
        key = 'detail' + str(index)
        graph[key] = {'class_type': 'FaceDetailer', 'inputs': {
            'image': ['target', 0], 'model': ['14', 0], 'clip': ['1', 1], 'vae': ['1', 2],
            'positive': ['4', 0], 'negative': ['5', 0],
            'guide_size': 512, 'guide_size_for': True, 'max_size': 1024,
            'seed': 20261002, 'steps': 5, 'cfg': 1.5,
            'sampler_name': 'dpmpp_sde', 'scheduler': 'karras', 'denoise': denoise,
            'feather': 15, 'noise_mask': True, 'force_inpaint': True,
            'bbox_threshold': 0.5, 'bbox_dilation': 10, 'bbox_crop_factor': 2.0,
            'sam_detection_hint': 'center-1', 'sam_dilation': 0, 'sam_threshold': 0.93,
            'sam_bbox_expansion': 0, 'sam_mask_hint_threshold': 0.7,
            'sam_mask_hint_use_negative': 'False', 'drop_size': 10,
            'bbox_detector': ['detector', 0], 'sam_model_opt': ['sam', 0],
            'wildcard': '', 'cycle': 1, 'noise_mask_feather': 20}}
        output = 'save' + str(index)
        label = f'denoise-{denoise:.2f}'
        graph[output] = {'class_type': 'SaveImage', 'inputs': {
            'images': [key, 0], 'filename_prefix': f'ByrdHouse/evaluations/{run}/{label}'}}
        outputs[label] = output
    graph_file = belt.output_dir / f'{run}.workflow.json'
    graph_file.write_text(json.dumps(graph, indent=2), encoding='utf-8')
    start = time.monotonic()
    print(json.dumps({'state': 'submitted', 'workflow': str(graph_file)}), flush=True)
    result = belt._run_graph(graph, outputs)
    generation_seconds = round(time.monotonic() - start, 2)
    reference_face = belt.inspect(Path(config['reference_dir']) / 'portrait.jpeg')
    rows = []
    for label, pixels in result.items():
        path = belt.output_dir / f'{run}-{label}.png'
        path.write_bytes(pixels)
        face = belt.inspect(path)
        row = {'file': str(path), 'similarity': round(belt._similarity(reference_face, face), 6),
               'geometry_delta': belt._geometry(reference_face, face)}
        path.with_suffix('.png.json').write_text(json.dumps({
            'purpose': 'Evaluate upstream FaceDetailer after ReActor; not approved',
            'review_state': 'needs_review', 'source': str(args.target),
            'reference': reference_face.public(), 'face': face.public(),
            'workflow_file': str(graph_file), 'generation_seconds_both_variants': generation_seconds,
            'upstream': 'https://github.com/ltdrdata/ComfyUI-Impact-Pack/blob/Main/example_workflows/1-FaceDetailer.json',
            **row}, indent=2), encoding='utf-8')
        rows.append(row)
        print(json.dumps(row), flush=True)
    print(json.dumps({'generation_seconds_both_variants': generation_seconds, 'results': rows}), flush=True)


if __name__ == '__main__':
    main()
