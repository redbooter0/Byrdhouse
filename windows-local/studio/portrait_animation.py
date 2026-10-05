"""Studio adapter for the installed upstream AdvancedLivePortrait example.

Resume collects the recorded Comfy prompt. It never submits another render.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import urllib.parse

from PIL import Image
import imageio_ffmpeg


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _json_digest(value):
    return _digest(json.dumps(value, sort_keys=True, separators=(',', ':'),
                              ensure_ascii=False, allow_nan=False).encode('utf-8'))


def _atomic_bytes(path, data):
    temporary = path.with_name(path.name + '.part')
    temporary.write_bytes(data)
    temporary.replace(path)


def _atomic_json(path, value):
    _atomic_bytes(path, json.dumps(value, indent=2, ensure_ascii=False,
                                  allow_nan=False).encode('utf-8'))


def _read_json(path, description):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object.')
        return value
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Cannot validate saved {description}; inspect the animation before retrying.') from exc


def _check_graph(graph, job_id, input_name, spec=None):
    """Check the job-specific image and output bindings without rebuilding."""
    if spec and spec.get('engine') == 'wan22':
        from wan22_workflow import check
        if not check(graph, spec, input_name):
            raise RuntimeError('Saved Wan animation workflow does not belong to this job.')
        return
    try:
        valid = (
            graph['3']['class_type'] == 'LoadImage'
            and graph['3']['inputs']['image'] == input_name
            and graph['15']['class_type'] == 'ExpressionEditor'
            and graph['15']['inputs']['src_image'] == ['3', 0]
            and graph['7']['class_type'] == 'AdvancedLivePortrait'
            and graph['7']['inputs']['motion_link'] == ['15', 1]
            and graph['10']['class_type'] == 'SaveImage'
            and graph['10']['inputs']['images'] == ['7', 0]
            and graph['10']['inputs']['filename_prefix'] == f'Carey-LivePortrait/{job_id}/frame'
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise RuntimeError('Saved animation workflow does not belong to this job.')


def _submission_matches(record, spec, source, source_hash, graph, prompt_id):
    expected = {
        'schema': 'byrdhouse.animation.submission.v2',
        'job_id': spec['id'], 'prompt_id': prompt_id,
        'source': str(source), 'source_sha256': source_hash,
        'spec_sha256': _json_digest(spec), 'workflow_sha256': _json_digest(graph),
        'state': 'submitted',
    }
    if any(record.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Saved animation submission provenance does not match this job, source, or workflow.')
    if not isinstance(record.get('upstream_workflow'), str) or not record['upstream_workflow']:
        raise RuntimeError('Saved animation submission is missing workflow provenance.')


def _is_observation_timeout(exc):
    return isinstance(exc, TimeoutError) or any(
        marker in str(exc).lower() for marker in ('timed out', 'timeout'))


def _history_graph_matches(graph, history_graph):
    """Allow only known Comfy validation/cache changes to a submitted graph.

    execution.validate_inputs coerces FLOAT widgets from int to float in place.
    IsChangedCache may add the node-level is_changed cache fingerprint. Neither
    changes node IDs, class types, links, source/output names, or motion values.
    The disk workflow and its recorded hash remain strictly validated separately.
    """
    float_inputs = {
        'KSampler': {'cfg', 'denoise'}, 'ModelSamplingSD3': {'shift'},
        'ExpressionEditor': {'rotate_pitch', 'rotate_yaw', 'rotate_roll', 'blink',
            'eyebrow', 'wink', 'pupil_x', 'pupil_y', 'aaa', 'eee', 'woo', 'smile',
            'src_ratio', 'sample_ratio', 'crop_factor'},
        'AdvancedLivePortrait': {'retargeting_eyes', 'retargeting_mouth', 'crop_factor'},
    }
    if not isinstance(history_graph, dict) or history_graph.keys() != graph.keys():
        return False
    normalized = {}
    for node_id, expected in graph.items():
        actual = history_graph[node_id]
        if not isinstance(actual, dict):
            return False
        actual = dict(actual)
        if 'is_changed' not in expected:
            actual.pop('is_changed', None)  # The sole allowed upstream cache annotation.
        if actual.keys() != expected.keys() or not isinstance(actual.get('inputs'), dict):
            return False
        actual['inputs'] = dict(actual['inputs'])
        if actual['inputs'].keys() != expected['inputs'].keys():
            return False
        for name in float_inputs.get(expected.get('class_type'), ()):
            original = expected['inputs'].get(name)
            observed = actual['inputs'].get(name)
            if (type(original) is int and type(observed) is float
                    and math.isfinite(observed) and observed == original):
                actual['inputs'][name] = original
        normalized[node_id] = actual
    try:
        return _json_digest(normalized) == _json_digest(graph)
    except (TypeError, ValueError):
        return False


def animate(config, client, spec, source, stop, submitted, resume_prompt_id=None):
    """Render once, or resume the saved prompt and collect its existing outputs.

    Legacy submissions without complete v2 provenance cannot be safely resumed.
    A submission intent is recorded before POST; ambiguous POST failures must be
    inspected instead of retried automatically.
    """
    job_id = spec['id']
    if (not isinstance(job_id, str) or len(job_id) != 32
            or any(char not in '0123456789abcdef' for char in job_id)):
        raise RuntimeError('Invalid animation job ID.')
    if resume_prompt_id is not None and (
            not isinstance(resume_prompt_id, str) or not resume_prompt_id.strip()
            or len(resume_prompt_id) > 256):
        raise RuntimeError('Invalid animation resume prompt ID.')
    source = Path(source).resolve()
    source_hash = _digest(source.read_bytes())
    if source_hash != spec['animation_source_sha256']:
        raise RuntimeError('Source changed after queueing. Review the current source before animating it.')
    root = Path(config['output_dir']).resolve().parent.parent
    wan = spec.get('engine') == 'wan22'
    if wan:
        from wan22_workflow import PREVIEWS, template_path
        expected_frames = PREVIEWS[spec['video_preset']][2]
        fps = 24
        prefix = f'Carey-Wan22/{job_id}'
    else:
        expected_frames, fps = 44, 15
        prefix = f'Carey-LivePortrait/{job_id}'
    upstream = root/'repo/external/ComfyUI-AdvancedLivePortrait'
    sample_path = template_path(config) if wan else upstream/'sample/workflows/Advanced_Animate_without_vid.json'
    output = root/'media/animation'/job_id
    workflow_path = output/'workflow.json'
    submission_path = output/'submission.json'
    input_name = f'ByrdHouse/animation/{job_id}.png'
    input_path = Path(config['comfy_dir'])/'input'/input_name

    if resume_prompt_id is not None:
        # No workflow/template discovery, source upload, metadata rewrite, or POST.
        graph = _read_json(workflow_path, 'animation workflow')
        submission = _read_json(submission_path, 'animation submission')
        _check_graph(graph, job_id, input_name, spec)
        _submission_matches(submission, spec, source, source_hash, graph, resume_prompt_id)
        if (submission.get('input_name') != input_name or not input_path.is_file()
                or submission.get('input_sha256') != _digest(input_path.read_bytes())):
            raise RuntimeError('Saved animation input changed or is missing; inspect the submitted animation.')
        prompt_id = resume_prompt_id
        sample_path = Path(submission['upstream_workflow'])
    else:
        if submission_path.exists():
            raise RuntimeError('This animation already has a submission record. Resume its prompt instead of submitting again.')
        if wan:
            from wan22_workflow import build
            graph = build(config, spec, input_name)
        else:
            sample = json.loads(sample_path.read_text(encoding='utf-8'))
            graph = {}
            for node in sample['nodes']:
                if node['type'] not in ('LoadImage', 'ExpressionEditor', 'AdvancedLivePortrait'):
                    continue
                info = client.request('/object_info/'+node['type']).get(node['type'])
                if not info:
                    raise RuntimeError('The installed LivePortrait workflow is unavailable in ComfyUI.')
                names = info['input_order']['required']
                graph[str(node['id'])] = {'class_type': node['type'],
                                        'inputs': dict(zip(names, node['widgets_values']))}
            graph['3']['inputs'] = {'image': input_name}
            graph['15']['inputs'].update(src_image=['3', 0], wink=0, blink=-8, rotate_yaw=1.5)
            graph['7']['inputs'].update(motion_link=['15', 1], command='0 = 1:10\n1 = 3:1\n0 = 3:26')
            graph['10'] = {'class_type': 'SaveImage', 'inputs': {
                'images': ['7', 0], 'filename_prefix': prefix+'/frame'}}
        _check_graph(graph, job_id, input_name, spec)
        output.mkdir(parents=True, exist_ok=True)
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_temporary = input_path.with_name(input_path.name+'.part')
        with Image.open(source) as photo:
            photo.convert('RGB').save(input_temporary, format='PNG')
        input_temporary.replace(input_path)
        _atomic_json(workflow_path, graph)
        submission = {
            'schema': 'byrdhouse.animation.submission.v2',
            'purpose': 'Resume/audit the submitted local animation without duplicating it',
            'job_id': job_id, 'prompt_id': None, 'state': 'submitting',
            'source': str(source), 'source_sha256': source_hash,
            'input_name': input_name, 'input_sha256': _digest(input_path.read_bytes()),
            'spec_sha256': _json_digest(spec), 'workflow_sha256': _json_digest(graph),
            'workflow_hash_format': 'canonical-json-sorted-keys-utf8',
            'upstream_workflow': str(sample_path),
            'upstream_workflow_sha256': _digest(sample_path.read_bytes()),
            'created': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }
        _atomic_json(submission_path, submission)
        response = client.request('/prompt', {'prompt': graph, 'client_id': 'byrdhouse-studio-animation'})
        prompt_id = response.get('prompt_id')
        if (not isinstance(prompt_id, str) or not prompt_id.strip() or len(prompt_id) > 256
                or response.get('node_errors')):
            raise RuntimeError('ComfyUI rejected the portrait-animation workflow: '+str(response)[:1500])
        submission.update(prompt_id=prompt_id, state='submitted',
                          submitted=datetime.now(timezone.utc).isoformat(timespec='seconds'))
        # Disk provenance precedes the queue callback so callback failure is resumable.
        _atomic_json(submission_path, submission)
        submitted(prompt_id)

    deadline = time.monotonic()+1200
    while time.monotonic() < deadline:
        try:
            history = client.request('/history/'+urllib.parse.quote(prompt_id, safe='')).get(prompt_id)
        except Exception as exc:
            if not _is_observation_timeout(exc):
                raise
            history = None
        if history:
            status = history.get('status', {})
            messages = status.get('messages', [])
            if status.get('status_str') == 'error' or any(
                    isinstance(message, (list, tuple)) and message
                    and message[0] in ('execution_error', 'execution_interrupted') for message in messages):
                for message in reversed(messages):
                    if (isinstance(message, (list, tuple)) and len(message) > 1
                            and message[0] == 'execution_error' and isinstance(message[1], dict)):
                        failure = message[1]
                        raise RuntimeError(f"ComfyUI {failure.get('node_type', 'node')} {failure.get('node_id', '')}: "
                                           f"{failure.get('exception_type', '')}: {failure.get('exception_message', 'Execution failed')}")
                raise RuntimeError(json.dumps(messages)[-1500:])
            if status.get('completed'):
                saved_prompt = history.get('prompt')
                if saved_prompt is not None and (
                        not isinstance(saved_prompt, (list, tuple)) or len(saved_prompt) < 3
                        or saved_prompt[1] != prompt_id
                        or not _history_graph_matches(graph, saved_prompt[2])):
                    raise RuntimeError('ComfyUI history provenance does not match the saved animation prompt.')
                break
        if stop.wait(0.8):
            raise RuntimeError('Studio stopped; inspect the submitted animation before retrying.')
    else:
        raise RuntimeError('Animation exceeded 20 minutes. Inspect ComfyUI before retrying.')
    rows = history.get('outputs', {}).get('10', {}).get('images', [])
    if len(rows) != expected_frames:
        raise RuntimeError(f'Expected {expected_frames} animation frames; received {len(rows)}.')
    normalized_rows = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError('Invalid animation output provenance.')
        filename = row.get('filename')
        raw_subfolder = row.get('subfolder', '')
        subfolder = raw_subfolder.replace('\\', '/') if isinstance(raw_subfolder, str) else ''
        if (row.get('type') != 'output' or not isinstance(filename, str) or not filename
                or '/' in filename or '\\' in filename
                or subfolder != prefix):
            raise RuntimeError('Invalid animation output provenance.')
        normalized_rows.append({'filename': filename, 'subfolder': subfolder, 'type': 'output'})
    if len({(row['subfolder'], row['filename']) for row in normalized_rows}) != expected_frames:
        raise RuntimeError('Animation history contains duplicate output frames.')
    frames = output/'frames'
    frames.mkdir(exist_ok=True)
    collection_path = output/'collection.json'
    collection = _read_json(collection_path, 'animation collection') if collection_path.exists() else {}
    identity = {'job_id': job_id, 'prompt_id': prompt_id, 'source_sha256': source_hash,
                'workflow_sha256': submission['workflow_sha256'], 'rows_sha256': _json_digest(normalized_rows)}
    if collection and any(collection.get(key) != value for key, value in identity.items()):
        raise RuntimeError('Saved animation collection belongs to different outputs or provenance.')
    collection.update(identity, schema='byrdhouse.animation.collection.v1',
                      purpose='Resume verified local frame collection and encoding without another render')
    entries = collection.setdefault('frames', {})
    if not isinstance(entries, dict) or any(not isinstance(entry, dict) for entry in entries.values()):
        raise RuntimeError('Saved animation frame collection is invalid; inspect it before retrying.')
    for index, row in enumerate(normalized_rows):
        if stop.wait(0):
            raise RuntimeError('Studio stopped; resume the submitted animation to finish collection.')
        name = f'frame_{index:04d}.png'
        frame_path = frames/name
        entry = entries.get(name, {})
        if not (frame_path.is_file() and entry.get('sha256') == _digest(frame_path.read_bytes())):
            query = urllib.parse.urlencode(row)
            data = client.request('/view?'+query, binary=True)
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise RuntimeError('Invalid animation frame format.')
            _atomic_bytes(frame_path, data)
            entries[name] = {'sha256': _digest(data)}
            _atomic_json(collection_path, collection)
    movie = Path(config['output_dir'])/f'{job_id}.mp4'
    frames_hash = _json_digest(entries)
    if not (movie.is_file() and collection.get('encoded_frames_sha256') == frames_hash
            and collection.get('movie_sha256') == _digest(movie.read_bytes())):
        if stop.wait(0):
            raise RuntimeError('Studio stopped; resume the submitted animation to finish encoding.')
        temporary = output/'encoding.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y',
            '-framerate', str(fps), '-i', str(frames/'frame_%04d.png'), '-c:v', 'libx264', '-crf', '18',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(temporary)], check=True, timeout=120)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError('Animation encoding produced no video.')
        temporary.replace(movie)
        collection.update(encoded_frames_sha256=frames_hash, movie_sha256=_digest(movie.read_bytes()))
        _atomic_json(collection_path, collection)
    poster = Path(config['output_dir'])/f'{job_id}_1.png'
    poster_data = (frames/'frame_0000.png').read_bytes()
    if not poster.is_file() or poster.read_bytes() != poster_data:
        _atomic_bytes(poster, poster_data)
    card = {'schema': 'byrdhouse.studio.animation.v1', 'job_id': job_id,
            'purpose': 'Carey illustrated scene-motion preview for likeness review' if wan else 'Carey source-portrait facial-motion preview for likeness review',
            'review_state': 'needs_review', 'identity_verified': False, 'exact_replica': False,
            'source': str(source), 'source_sha256': source_hash, 'settings': spec,
            'upstream_workflow': str(sample_path), 'workflow': graph, 'prompt_id': prompt_id,
            'upstream_workflow_sha256': submission.get('upstream_workflow_sha256'),
            'workflow_sha256': submission['workflow_sha256'], 'movie_sha256': collection['movie_sha256'],
            'frames': expected_frames, 'fps': fps, 'duration_seconds': expected_frames/fps, 'file': movie.name,
            'note': 'Wan reconstructs moving pixels; inspect every frame for identity drift. Smoke resolution is not episode quality.' if wan else 'LivePortrait reconstructs moving facial pixels; inspect likeness and motion.'}
    # Recollection of unchanged output preserves a completed human review.
    for sidecar in (poster.with_suffix('.png.json'), movie.with_suffix('.mp4.json')):
        if sidecar.exists():
            previous = _read_json(sidecar, 'animation metadata')
            if all(previous.get(key) == card[key] for key in
                   ('job_id', 'prompt_id', 'source_sha256', 'workflow_sha256', 'movie_sha256')):
                if previous.get('review_state') in ('approved', 'rejected', 'needs_review'):
                    reviewed_card = {**card, **{key: previous[key] for key in
                        ('review_state', 'reviewed') if key in previous}}
                else:
                    reviewed_card = card
            else:
                reviewed_card = card
        else:
            reviewed_card = card
        if not sidecar.exists() or _read_json(sidecar, 'animation metadata') != reviewed_card:
            _atomic_json(sidecar, reviewed_card)
    return [poster.name]
