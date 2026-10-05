"""Adapt the pinned official ComfyUI Wan 2.2 5B I2V example.

The model and sampling links come from the upstream graph. Only the source,
prompts, bounded preview dimensions, tiled decode and audited frame sink change.
"""
import hashlib
import json
from pathlib import Path

TEMPLATE_SHA256 = '2b1784c9d6ecf03462651d6e8ded7b5cc5e18047e9eb5e2a885fb6c89c5ac515'
MODEL = 'wan2.2_ti2v_5B_fp16.safetensors'
ENCODER = 'umt5_xxl_fp8_e4m3fn_scaled.safetensors'
VAE = 'wan2.2_vae.safetensors'
NODES = {'UNETLoader', 'CLIPLoader', 'VAELoader', 'CLIPTextEncode',
         'ModelSamplingSD3', 'Wan22ImageToVideoLatent', 'KSampler',
         'LoadImage', 'VAEDecodeTiled', 'SaveImage'}
PREVIEWS = {'portrait_smoke': (384, 576, 33),
            'portrait_detail': (576, 832, 49)}


def template_path(config):
    return Path(config['output_dir']).resolve().parent.parent / 'external/workflows/comfy-wan22-5b/image_to_video_wan22_5B.json'


def ready(config, models):
    return (MODEL in models.get('diffusion_models', [])
            and ENCODER in models.get('text_encoders', [])
            and VAE in models.get('vaes', [])
            and NODES.issubset(models.get('nodes', []))
            and template_path(config).is_file())


def build(config, spec, input_name):
    raw = template_path(config).read_bytes()
    if hashlib.sha256(raw).hexdigest() != TEMPLATE_SHA256:
        raise RuntimeError('The pinned upstream Wan workflow changed; review its provenance before rendering.')
    sample = json.loads(raw)
    fields = {
        'UNETLoader': ['unet_name', 'weight_dtype'],
        'CLIPLoader': ['clip_name', 'type', 'device'],
        'VAELoader': ['vae_name'], 'CLIPTextEncode': ['text'],
        'ModelSamplingSD3': ['shift'],
        'Wan22ImageToVideoLatent': ['width', 'height', 'length', 'batch_size'],
        'KSampler': ['seed', '_seed_control', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise'],
        'LoadImage': ['image'], 'VAEDecode': [],
    }
    links = {row[0]: row for row in sample['links']}
    graph = {}
    for node in sample['nodes']:
        if node['type'] not in fields:
            continue
        inputs = dict(zip(fields[node['type']], node['widgets_values']))
        inputs.pop('_seed_control', None)
        for socket in node.get('inputs', []):
            if socket.get('link') is not None:
                link = links[socket['link']]
                inputs[socket['name']] = [str(link[1]), link[2]]
        graph[str(node['id'])] = {'class_type': node['type'], 'inputs': inputs}
    graph['57']['inputs']['image'] = input_name
    graph['6']['inputs']['text'] = spec['prompt']
    graph['7']['inputs']['text'] = spec['negative']
    width, height, length = PREVIEWS[spec['video_preset']]
    graph['55']['inputs'].update(width=width, height=height, length=length, batch_size=1)
    graph['3']['inputs']['seed'] = int(spec['seed'])
    # Retain upstream 30-step UniPC/simple, CFG 5 and shift 8.
    graph['8']['class_type'] = 'VAEDecodeTiled'
    graph['8']['inputs'].update(tile_size=256, overlap=64, temporal_size=16, temporal_overlap=4)
    graph['10'] = {'class_type': 'SaveImage', 'inputs': {
        'images': ['8', 0], 'filename_prefix': f"Carey-Wan22/{spec['id']}/frame"}}
    return graph


def check(graph, spec, input_name):
    """Bind critical sources, models and output sinks during resume."""
    try:
        width, height, length = PREVIEWS[spec['video_preset']]
        return (
            graph['57']['class_type'] == 'LoadImage'
            and graph['57']['inputs']['image'] == input_name
            and graph['55']['class_type'] == 'Wan22ImageToVideoLatent'
            and graph['55']['inputs']['start_image'] == ['57', 0]
            and all(graph['55']['inputs'][k] == v for k, v in
                    [('width', width), ('height', height), ('length', length)])
            and graph['37']['inputs']['unet_name'] == MODEL
            and graph['38']['inputs']['clip_name'] == ENCODER
            and graph['39']['inputs']['vae_name'] == VAE
            and graph['8']['class_type'] == 'VAEDecodeTiled'
            and graph['10']['class_type'] == 'SaveImage'
            and graph['10']['inputs'] == {'images': ['8', 0],
                'filename_prefix': f"Carey-Wan22/{spec['id']}/frame"})
    except (KeyError, TypeError):
        return False
