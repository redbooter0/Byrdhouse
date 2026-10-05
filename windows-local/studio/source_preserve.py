"""Thin adapter for installed CPU parsing and ComfyUI core masked editing.

Generation/compositing happens in ComfyUI. Pillow/numpy inspect saved pixels and
draw a mask review sheet; they never reconstruct Carey's face.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from reference_inputs import reverify_reference
from source_masks import build_mask_graph, inspect_masks, inspect_matte, _read_rgb, _read_mask


class SourceError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    part = path.with_suffix(path.suffix + '.part')
    part.write_text(json.dumps(value, indent=2), encoding='utf-8')
    part.replace(path)


def work_dir(config, job_id):
    if len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
        raise SourceError('Invalid source-preservation job ID.')
    return Path(config['output_dir']).resolve().parent / 'source-preserved' / job_id


def checked_masks(config, spec):
    """Read frozen masks only from the recorded, approved parent bundle."""
    parent = work_dir(config, spec['mask_job_id'])
    names = ('protect', 'edit', 'labels') + (('core', 'matte') if 'matte' in spec.get('mask_hashes', {}) else ())
    if 'character' in spec.get('mask_hashes', {}):
        names += ('character',)
    paths = {name: parent / (name + '.png') for name in names}
    for name, path in paths.items():
        if file_hash(path) != spec['mask_hashes'][name]:
            raise SourceError('Reviewed semantic mask changed; inspect it before editing.')
    source = reverify_reference(config, spec['reference_snapshot'])
    report = inspect_masks(source['staged_path'], paths['protect'], paths['edit'],
                           labels_path=paths['labels'], region=spec['region'],
                           expected_source_sha256=source['staged_png_sha256'])
    if 'matte' in paths:
        report['matte'] = inspect_matte(source['staged_path'], paths['matte'],
                                        expected_source_sha256=source['staged_png_sha256'])
        core, _ = _read_mask(paths['core'], (source['height'], source['width']))
        protect, _ = _read_mask(paths['protect'], (source['height'], source['width']))
        if not np.any(core) or np.any(core & ~protect):
            raise SourceError('Semantic core must be nonempty and contained by the reviewed protection mask.')
        report['core'] = {'path': str(paths['core'].resolve()), 'selected_pixels': int(core.sum()),
                          'selected_fraction': float(core.mean()), 'contained_by_protect': True}
        if 'character' in paths:
            report['character'] = inspect_matte(source['staged_path'], paths['character'],
                                                 expected_source_sha256=source['staged_png_sha256'])
            character, _ = _read_rgb(paths['character'])
            if np.any(core & (character[:, :, 0] < 128)):
                raise SourceError('Tight illustrated character mask omitted protected face or hair core pixels.')
    return paths, report


def build_edit_graph(config, spec):
    """Build a source edit or an independent anime background composite."""
    source = spec['reference_snapshot']['comfy_image']
    graph = {
        'source': {'class_type': 'LoadImage', 'inputs': {'image': source}},
        'checkpoint': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': spec['checkpoint']}},
        'positive': {'class_type': 'CLIPTextEncode', 'inputs': {'text': spec['full_prompt'], 'clip': ['checkpoint', 1]}},
        'negative': {'class_type': 'CLIPTextEncode', 'inputs': {'text': spec['negative'], 'clip': ['checkpoint', 1]}},
        'sampler': {'class_type': 'KSampler', 'inputs': {
            'model': ['checkpoint', 0], 'positive': ['positive', 0], 'negative': ['negative', 0],
            'latent_image': ['encode', 0], 'seed': spec['seed'], 'steps': spec['steps'],
            'cfg': spec['cfg'], 'sampler_name': spec['sampler'], 'scheduler': spec['scheduler'], 'denoise': 1.0}},
        'decode': {'class_type': 'VAEDecode', 'inputs': {'samples': ['sampler', 0], 'vae': ['checkpoint', 2]}},
        'final': {'class_type': 'SaveImage', 'inputs': {
            'images': ['composite', 0], 'filename_prefix': 'ByrdHouse/source-preserved-' + spec['id']}},
    }
    if spec.get('anime_anchor_scene') and spec.get('character_mask_image'):
        snapshot = spec['reference_snapshot']
        width, height = snapshot['width'], snapshot['height']
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise SourceError('Anime scene source has invalid dimensions.')
        graph.update({
            'character': {'class_type': 'LoadImageMask', 'inputs': {
                'image': spec['character_mask_image'], 'channel': 'red'}},
            'core': {'class_type': 'LoadImageMask', 'inputs': {
                'image': spec['core_mask_image'], 'channel': 'red'}},
            # An independently painted background cannot carry the anchor's
            # off-white canvas into pixels outside the reviewed character.
            'empty_latent': {'class_type': 'EmptyLatentImage', 'inputs': {
                'width': width, 'height': height, 'batch_size': 1}},
            'composite': {'class_type': 'ImageCompositeMasked', 'inputs': {
                'destination': ['decode', 0], 'source': ['source', 0],
                'mask': ['character', 0], 'x': 0, 'y': 0, 'resize_source': False}},
            'core_composite': {'class_type': 'ImageCompositeMasked', 'inputs': {
                'destination': ['composite', 0], 'source': ['source', 0],
                'mask': ['core', 0], 'x': 0, 'y': 0, 'resize_source': False}},
        })
        graph['sampler']['inputs']['latent_image'] = ['empty_latent', 0]
        graph['final']['inputs']['images'] = ['core_composite', 0]
    elif spec.get('matte_mask_image'):
        graph.update({
            'matte': {'class_type': 'LoadImageMask', 'inputs': {'image': spec['matte_mask_image'], 'channel': 'red'}},
            'core': {'class_type': 'LoadImageMask', 'inputs': {'image': spec['core_mask_image'], 'channel': 'red'}},
            # Regenerate fully behind the edge rather than mixing old white
            # bathroom pixels into the new scene. A stylized source uses a
            # larger shrink because its off-white anti-aliased outline is
            # visibly louder against a saturated illustrated background.
            'matte_binary': {'class_type': 'ThresholdMask', 'inputs': {'mask': ['matte', 0], 'value': 0.5}},
            'background': {'class_type': 'InvertMask', 'inputs': {'mask': ['matte_binary', 0]}},
            'matte_edge_shrink': {'class_type': 'GrowMask', 'inputs': {
                'mask': ['matte', 0], 'expand': int(spec.get('matte_edge_shrink_pixels', -2)), 'tapered_corners': True}},
            'encode': {'class_type': 'VAEEncodeForInpaint', 'inputs': {
                'pixels': ['source', 0], 'vae': ['checkpoint', 2], 'mask': ['background', 0], 'grow_mask_by': 0}},
            'composite': {'class_type': 'ImageCompositeMasked', 'inputs': {
                'destination': ['decode', 0], 'source': ['source', 0], 'mask': ['matte_edge_shrink', 0],
                'x': 0, 'y': 0, 'resize_source': False}},
            'core_composite': {'class_type': 'ImageCompositeMasked', 'inputs': {
                'destination': ['composite', 0], 'source': ['source', 0], 'mask': ['core', 0],
                'x': 0, 'y': 0, 'resize_source': False}},
        })
        graph['final']['inputs']['images'] = ['core_composite', 0]
    else:
        graph.update({
            'mask': {'class_type': 'LoadImageMask', 'inputs': {'image': spec['edit_mask_image'], 'channel': 'red'}},
            'encode': {'class_type': 'VAEEncodeForInpaint', 'inputs': {
                'pixels': ['source', 0], 'vae': ['checkpoint', 2], 'mask': ['mask', 0], 'grow_mask_by': 0}},
            'composite': {'class_type': 'ImageCompositeMasked', 'inputs': {
                'destination': ['source', 0], 'source': ['decode', 0], 'mask': ['mask', 0],
                'x': 0, 'y': 0, 'resize_source': False}},
        })
    return graph, {'final': 'final'}


def verify_pixels(source, output, protect, edit, matte=None, core=None, *, edge_source='BiRefNet'):
    """Compare actual saved uint8 RGB pixels, not an embedding or preview."""
    original, source_card = _read_rgb(source)
    rendered, output_card = _read_rgb(output)
    if original.shape != rendered.shape or output_card['format'] != 'PNG':
        raise SourceError('Saved output must be a PNG at the original dimensions.')
    protected, _ = _read_mask(protect, original.shape[:2])
    editable, _ = _read_mask(edit, original.shape[:2])
    if np.any(protected & editable):
        raise SourceError('Edit mask overlaps protected pixels.')
    changed = np.any(original != rendered, axis=2)
    difference = np.abs(original.astype(np.int16) - rendered.astype(np.int16))
    if matte is not None:
        alpha, alpha_card = _read_rgb(matte)
        if alpha.shape != original.shape or alpha_card['format'] != 'PNG' or not np.all(alpha == alpha[:, :, :1]):
            raise SourceError('Saved alpha matte must be a grayscale PNG at original dimensions.')
        alpha = alpha[:, :, 0]
        edge = (alpha > 0) & (alpha < 255)
        if core is None:
            raise SourceError('Alpha source-preservation output requires a frozen semantic core mask.')
        core_mask, _ = _read_mask(core, original.shape[:2])
        if not np.any(core_mask) or np.any(core_mask & ~protected):
            raise SourceError('Frozen semantic core is empty or falls outside the protection mask.')
        core_changed = int(np.count_nonzero(changed & core_mask))
        report = {
            'schema': 'byrdhouse.source-preservation.alpha-pixels.v1',
            'width': source_card['width'], 'height': source_card['height'],
            'source': source_card, 'output': output_card,
            'semantic_protected_pixels': int(protected.sum()), 'semantic_core_pixels': int(core_mask.sum()),
            'alpha_edge_pixels': int(edge.sum()), 'editable_pixels': int(editable.sum()),
            'semantic_core_changed_pixels': core_changed,
            'semantic_core_max_channel_difference': int(difference[core_mask].max()),
            'background_changed_pixels': int(np.count_nonzero(changed & (alpha == 0))),
            'edge_changed_pixels': int(np.count_nonzero(changed & edge)),
            'core_source_pixels_sha256': hashlib.sha256(original[core_mask].tobytes()).hexdigest(),
            'core_output_pixels_sha256': hashlib.sha256(rendered[core_mask].tobytes()).hexdigest(),
            'passed': core_changed == 0,
            'claim_scope': ('Identical saved RGB pixels inside the frozen semantic face-and-hair core. '
                            + edge_source + ' handles the soft outer edge; no claim of exact new poses, generated likeness, or animation.')}
        if not report['passed']:
            raise SourceError(f"Saved image changed {core_changed} semantic protected-core pixels.")
        if not report['background_changed_pixels']:
            raise SourceError('The requested background did not change; no useful edit was produced.')
        return report
    protected_changed = int(np.count_nonzero(changed & protected))
    outside_changed = int(np.count_nonzero(changed & ~editable))
    report = {
        'schema': 'byrdhouse.source-preservation.pixels.v1',
        'width': source_card['width'], 'height': source_card['height'],
        'source': source_card, 'output': output_card,
        'protected_pixels': int(protected.sum()), 'editable_pixels': int(editable.sum()),
        'protected_changed_pixels': protected_changed,
        'protected_max_channel_difference': int(difference[protected].max()),
        'outside_edit_changed_pixels': outside_changed,
        'edited_changed_pixels': int(np.count_nonzero(changed & editable)),
        'protected_source_pixels_sha256': hashlib.sha256(original[protected].tobytes()).hexdigest(),
        'protected_output_pixels_sha256': hashlib.sha256(rendered[protected].tobytes()).hexdigest(),
        'passed': protected_changed == 0 and outside_changed == 0,
        'claim_scope': 'Identical saved RGB pixels within the frozen protection mask at the original pose. Semantic coverage still requires visual review; no claim of exact new poses or animation.'}
    if not report['passed']:
        raise SourceError(f'Saved image changed {protected_changed} protected pixels and {outside_changed} pixels outside the edit mask.')
    if not report['edited_changed_pixels']:
        raise SourceError('The requested region did not change; no useful edit was produced.')
    return report


def render_mask_review(source, protect, edit, target, character=None):
    """Inspection sheet only; full-resolution original/masks remain separate."""
    rgb, _ = _read_rgb(source)
    p, _ = _read_mask(protect, rgb.shape[:2])
    e, _ = _read_mask(edit, rgb.shape[:2])
    highlighted = rgb.copy()
    if character is not None:
        character_rgb, _ = _read_rgb(character)
        if character_rgb.shape != rgb.shape or not np.all(character_rgb == character_rgb[:, :, :1]):
            raise SourceError('Illustrated character mask does not match the source canvas.')
        p = character_rgb[:, :, 0] >= 128
    highlighted[p] = np.rint(rgb[p] * .58 + np.array([36, 210, 130]) * .42).astype(np.uint8)
    highlighted[e] = np.rint(rgb[e] * .58 + np.array([70, 140, 255]) * .42).astype(np.uint8)
    size = (480, round(rgb.shape[0] * 480 / rgb.shape[1]))
    sheet = Image.new('RGB', (size[0] * 2, size[1] + 112), '#121b24')
    sheet.paste(Image.fromarray(rgb).resize(size), (0, 54))
    sheet.paste(Image.fromarray(highlighted).resize(size), (size[0], 54))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 19)
    except OSError:
        font = ImageFont.load_default()
    draw.text((16, 14), 'Approved Carey anime anchor' if character is not None else 'Original Carey photo', fill='white', font=font)
    draw.text((496, 14), 'Green = keep / blue = edit', fill='white', font=font)
    draw.text((16, size[1] + 65), 'Inspect curls, hairline, face, beard, neck and shirt. Estimated mask; review required.', fill='white', font=font)
    sheet.save(target, format='PNG')


def _history_graph_matches(expected, actual):
    if not isinstance(actual, dict):
        return False
    cleaned = {key: {k: v for k, v in node.items() if k != 'is_changed'}
               for key, node in actual.items() if isinstance(node, dict)}
    return digest(expected) == digest(cleaned)


def _execute(config, client, spec, graph, save_nodes, input_files, stop, submitted, resume_prompt_id):
    """One durable intent, one submission; resume collects that same prompt."""
    if stop.is_set():
        raise SourceError('Studio stopped before source-preservation execution.')
    directory = work_dir(config, spec['id']); directory.mkdir(parents=True, exist_ok=True)
    journal = directory / 'submission.json'
    fingerprint = {'schema': 'byrdhouse.source-preservation.submission.v1', 'job_id': spec['id'],
                   'settings_sha256': digest(spec), 'workflow': graph, 'workflow_sha256': digest(graph),
                   'save_nodes': save_nodes, 'input_files': input_files}
    for path, expected_hash in input_files.items():
        if file_hash(path) != expected_hash:
            raise SourceError('Frozen source or mask input changed before execution.')
    saved = json.loads(journal.read_text(encoding='utf-8')) if journal.is_file() else None
    if saved and any(saved.get(k) != value for k, value in fingerprint.items()):
        raise SourceError('Saved source-preservation submission differs; refusing altered work.')
    prompt_id = resume_prompt_id or (saved.get('prompt_id') if saved else None)
    if resume_prompt_id and (not saved or saved.get('prompt_id') != resume_prompt_id):
        raise SourceError('Source-preservation resume has no matching submission journal.')
    if prompt_id is None:
        if saved:
            raise SourceError('Interrupted submission has no recorded ID. Inspect ComfyUI; no automatic resubmission.')
        saved = {**fingerprint, 'prompt_id': None}
        write_json(journal, saved)
        if stop.is_set():
            raise SourceError('Studio stopped before ComfyUI submission. Inspect the saved intent before retrying.')
        response = client.request('/prompt', {'prompt': graph, 'client_id': 'byrdhouse-source-preservation'})
        prompt_id = response.get('prompt_id')
        if not isinstance(prompt_id, str) or not prompt_id or response.get('node_errors'):
            raise SourceError('ComfyUI rejected the source-preservation workflow: ' + json.dumps(response)[:1200])
        saved['prompt_id'] = prompt_id
        write_json(journal, saved)
    submitted(prompt_id)
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        if stop.is_set():
            raise SourceError('Studio stopped while awaiting ComfyUI. Resume the existing prompt.')
        record = client.request('/history/' + urllib.parse.quote(prompt_id, safe='')).get(prompt_id)
        if record:
            status = record.get('status', {})
            errors = [m[1] for m in status.get('messages', []) if isinstance(m, list) and len(m) == 2
                      and m[0] in ('execution_error', 'execution_interrupted')]
            if errors or status.get('status_str') == 'error':
                detail = errors[0].get('exception_message') if errors and isinstance(errors[0], dict) else 'ComfyUI source-preservation failed.'
                raise SourceError(str(detail))
            if status.get('completed'):
                actual = record.get('prompt', [])
                if not (isinstance(actual, list) and len(actual) > 2 and actual[1] == prompt_id
                        and _history_graph_matches(graph, actual[2])):
                    raise SourceError('Completed source-preservation history has a different workflow.')
                paths = {}
                for name, node_id in save_nodes.items():
                    images = record.get('outputs', {}).get(node_id, {}).get('images', [])
                    if len(images) != 1 or images[0].get('type') != 'output':
                        raise SourceError('ComfyUI must save exactly one PNG for each expected output.')
                    item = images[0]
                    prefix = graph[node_id]['inputs']['filename_prefix']
                    if (Path(item.get('filename', '')).name != item.get('filename') or
                            item.get('subfolder') != str(Path(prefix).parent).replace('\\', '/') or
                            not item['filename'].startswith(Path(prefix).name + '_') or not item['filename'].endswith('.png')):
                        raise SourceError('Completed output does not belong to the saved job prefix.')
                    query = urllib.parse.urlencode({k: item.get(k, '') for k in ('filename', 'subfolder', 'type')})
                    data = client.request('/view?' + query, binary=True)
                    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                        raise SourceError('ComfyUI did not return a PNG.')
                    target = directory / (name + '.png')
                    if target.exists() and target.read_bytes() != data:
                        raise SourceError('Saved output differs from the existing collected artifact.')
                    if not target.exists():
                        part = target.with_suffix('.png.part'); part.write_bytes(data); part.replace(target)
                    paths[name] = target
                for path, expected_hash in input_files.items():
                    if file_hash(path) != expected_hash:
                        raise SourceError('Frozen input changed during rendering.')
                return paths, prompt_id
        if stop.wait(.8):
            raise SourceError('Studio stopped while awaiting ComfyUI. Resume the existing prompt.')
    raise SourceError('Generation exceeded 20 minutes. Inspect ComfyUI before retrying.')


def run(config, client, spec, stop, submitted, resume_prompt_id=None):
    snapshot = reverify_reference(config, spec['reference_snapshot'])
    source = Path(snapshot['staged_path'])
    input_files = {str(source): snapshot['staged_png_sha256']}
    if spec['operation'] == 'source_mask':
        graph, nodes = build_mask_graph(snapshot['comfy_image'], spec['id'], spec['region'],
                                        illustrated=bool(spec.get('anime_anchor_scene')))
    else:
        masks, _ = checked_masks(config, spec)
        edit_input = Path(spec['edit_mask_path'])
        input_root = Path(config.get('comfy_input_dir', Path(config.get('comfy_dir', '')) / 'input')).resolve()
        expected_input = (input_root / 'ByrdHouse' / 'source-edits' / spec['id'] / 'edit.png').resolve()
        if (not expected_input.is_relative_to(input_root) or edit_input != expected_input
                or spec['edit_mask_image'] != expected_input.relative_to(input_root).as_posix()):
            raise SourceError('Edit mask path does not belong to this job input bundle.')
        if file_hash(edit_input) != spec['mask_hashes']['edit']:
            raise SourceError('Staged edit mask changed before rendering.')
        input_files.update({str(path): spec['mask_hashes'][name] for name, path in masks.items()})
        input_files[str(edit_input)] = spec['mask_hashes']['edit']
        if spec.get('matte_mask_path'):
            matte_input = Path(spec['matte_mask_path'])
            expected_matte = (input_root / 'ByrdHouse' / 'source-edits' / spec['id'] / 'matte.png').resolve()
            if matte_input != expected_matte or spec.get('matte_mask_image') != expected_matte.relative_to(input_root).as_posix():
                raise SourceError('Alpha matte path does not belong to this job input bundle.')
            if file_hash(matte_input) != spec['mask_hashes'].get('matte'):
                raise SourceError('Staged alpha matte changed before rendering.')
            input_files[str(matte_input)] = spec['mask_hashes']['matte']
            core_input = Path(spec['core_mask_path'])
            expected_core = (input_root / 'ByrdHouse' / 'source-edits' / spec['id'] / 'core.png').resolve()
            if core_input != expected_core or spec.get('core_mask_image') != expected_core.relative_to(input_root).as_posix():
                raise SourceError('Semantic core path does not belong to this job input bundle.')
            if file_hash(core_input) != spec['mask_hashes'].get('core'):
                raise SourceError('Staged semantic core changed before rendering.')
            input_files[str(core_input)] = spec['mask_hashes']['core']
        if spec.get('character_mask_path'):
            character_input = Path(spec['character_mask_path'])
            expected_character = (input_root / 'ByrdHouse' / 'source-edits' / spec['id'] / 'character.png').resolve()
            if character_input != expected_character or spec.get('character_mask_image') != expected_character.relative_to(input_root).as_posix():
                raise SourceError('Tight character mask path does not belong to this job input bundle.')
            if file_hash(character_input) != spec['mask_hashes'].get('character'):
                raise SourceError('Staged tight character mask changed before rendering.')
            input_files[str(character_input)] = spec['mask_hashes']['character']
        graph, nodes = build_edit_graph(config, spec)
    paths, prompt_id = _execute(config, client, spec, graph, nodes, input_files, stop, submitted, resume_prompt_id)
    directory = work_dir(config, spec['id'])
    filename = spec['id'] + '_1.png'
    final = Path(config['output_dir']) / filename
    if spec['operation'] == 'source_mask':
        report = inspect_masks(source, paths['protect'], paths['edit'], labels_path=paths['labels'],
                               region=spec['region'], expected_source_sha256=snapshot['staged_png_sha256'])
        report['matte'] = inspect_matte(source, paths['matte'],
                                        expected_source_sha256=snapshot['staged_png_sha256'])
        core, _ = _read_mask(paths['core'], (snapshot['height'], snapshot['width']))
        protect, _ = _read_mask(paths['protect'], (snapshot['height'], snapshot['width']))
        if not np.any(core) or np.any(core & ~protect):
            raise SourceError('Semantic core must be nonempty and contained by the reviewed protection mask.')
        report['core'] = {'path': str(paths['core'].resolve()), 'selected_pixels': int(core.sum()),
                          'selected_fraction': float(core.mean()), 'contained_by_protect': True}
        report['mask_hashes'] = {name: file_hash(paths[name]) for name in paths}
        if 'character' in paths:
            report['character'] = inspect_matte(source, paths['character'],
                                                 expected_source_sha256=snapshot['staged_png_sha256'])
            character_rgb, _ = _read_rgb(paths['character'])
            if np.any(core & (character_rgb[:, :, 0] < 128)):
                raise SourceError('Tight illustrated character mask omitted protected face or hair core pixels.')
        render_mask_review(source, paths['protect'], paths['edit'], final,
                           character=paths.get('character'))
        purpose = 'Review semantic coverage before source-preserved scene editing'
    else:
        edge_name = 'Reviewed semantic character mask' if spec.get('character_mask_path') else 'BiRefNet'
        report = verify_pixels(source, paths['final'], masks['protect'], masks['edit'],
                               masks.get('character') if spec.get('character_mask_path') else masks.get('matte'),
                               masks.get('core'), edge_source=edge_name)
        part = final.with_suffix('.png.part'); part.write_bytes(paths['final'].read_bytes()); part.replace(final)
        purpose = ('Private illustrated scene-edit candidate preserving the locked Carey Anime Canon opaque core pixels at the source pose'
                   if spec.get('anime_anchor_scene') else
                   'Private scene-edit candidate preserving reviewed original Carey opaque core pixels at the source pose')
    write_json(directory / 'inspection.json', report)
    card = {'schema': 'byrdhouse.studio.image.v1', 'job_id': spec['id'], 'purpose': purpose,
            'identity_verified': False, 'exact_replica': False, 'review_state': 'needs_review',
            'prompt_id': prompt_id, 'settings': spec, 'workflow': graph,
            'file': filename, 'source': 'local ComfyUI', 'inspection': report,
            'width': snapshot['width'], 'height': snapshot['height']}
    with Image.open(final) as saved_image:
        card['width'], card['height'] = saved_image.size
    write_json(final.with_suffix('.png.json'), card)
    return [filename]
