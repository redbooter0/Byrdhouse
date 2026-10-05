"""Compare upstream ReActor restorers on an identical local target and reference."""
import argparse
import copy
import json
import time
from pathlib import Path
from identity_belt import IdentityBelt
from server import ComfyClient, load_config

parser = argparse.ArgumentParser()
parser.add_argument('--target', type=Path, required=True)
args = parser.parse_args()
config = load_config(Path(r'D:\ByrdHouse\byrdhouse-local.json'))
belt = IdentityBelt(config, ComfyClient(config['comfy_url']))
reference = Path(config['reference_dir']) / 'portrait.jpeg'
run = 'restore-compare-' + str(time.time_ns())
target_name, reference_name = belt._input_copy(run, args.target, reference)
template, _ = belt._graph(target_name, reference_name, run)
graph = {key: template[key] for key in ['target', 'reference']}
outputs = {}
for label, model, visibility in [('gpen06', 'GPEN-BFR-512.onnx', 0.6),
                                  ('gpen10', 'GPEN-BFR-512.onnx', 1.0),
                                  ('gfpgan10', 'GFPGANv1.4.pth', 1.0)]:
    swap, mask, save = 'swap_'+label, 'mask_'+label, 'save_'+label
    graph[swap] = copy.deepcopy(template['swap1'])
    graph[swap]['inputs'].update(face_restore_model=model, face_restore_visibility=visibility)
    graph[mask] = copy.deepcopy(template['mask1'])
    graph[mask]['inputs']['swapped_image'] = [swap, 0]
    graph[save] = {'class_type': 'SaveImage', 'inputs': {
        'images': [mask, 0], 'filename_prefix': f'ByrdHouse/evaluations/{run}/{label}'}}
    outputs[label] = save
graph_path = belt.output_dir / f'{run}.workflow.json'
graph_path.write_text(json.dumps(graph, indent=2), encoding='utf-8')
start = time.monotonic()
print(json.dumps({'state': 'submitted', 'workflow': str(graph_path)}), flush=True)
images = belt._run_graph(graph, outputs)
seconds = round(time.monotonic()-start, 2)
ref = belt.inspect(reference)
for label, pixels in images.items():
    file = belt.output_dir / f'{run}-{label}.png'
    file.write_bytes(pixels)
    face = belt.inspect(file)
    row = {'purpose': 'Private comparison of restored Carey candidates',
           'review_state': 'needs_review', 'file': str(file), 'source': str(args.target),
           'workflow': str(graph_path), 'generation_seconds_all_variants': seconds,
           'reference': ref.public(), 'face': face.public(),
           'similarity': round(belt._similarity(ref, face), 6),
           'geometry_delta': belt._geometry(ref, face)}
    file.with_suffix('.png.json').write_text(json.dumps(row, indent=2), encoding='utf-8')
    print(json.dumps({key: row[key] for key in ['file', 'similarity', 'geometry_delta', 'generation_seconds_all_variants']}), flush=True)
