"""Queue adapter for the existing matching-view examiner and report renderer.

No model downloads, pixel correction, Comfy submission or automatic approval.
"""
import hashlib
import json
from pathlib import Path
import shutil

from anime_view_review import reference_binding, review, feature_findings
from portrait_animation import _atomic_json, _json_digest
from identity_belt import measurement_binding


class ReviewInterrupted(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def asset_root(config):
    return Path(config['output_dir']).resolve().parent.parent / 'assets/characters/carey-anime'


def work_dir(config, job_id):
    if (not isinstance(job_id, str) or len(job_id) != 32
            or any(c not in '0123456789abcdef' for c in job_id)):
        raise ValueError('Invalid continuity review ID.')
    return Path(config['output_dir']).resolve().parent / 'anime-reviews' / job_id


def illustrated(job, reference_id):
    return (job.get('identity_mode') in ('anime_anchor', 'anime_source_preserve')
            or job.get('preset') == 'anime'
            or job.get('operation') in ('portrait_animation', 'scene_animation')
            and job.get('reference') == reference_id)


def freeze_inputs(studio, parent, image_index):
    """Use the animation collector's complete hash journal, not a frame glob."""
    if parent.get('operation') not in ('portrait_animation', 'scene_animation'):
        target = studio.image_path(parent['id'], image_index)
        return [{'path': str(target), 'sha256': sha(target), 'index': image_index}], []
    if image_index != 0:
        raise ValueError('Video review examines every frame; choose image index zero.')
    card = studio.metadata(parent['id'])
    directory = studio.output_dir.parent / 'animation' / parent['id']
    collection_path = directory / 'collection.json'
    collection = json.loads(collection_path.read_text(encoding='utf-8'))
    count = card.get('frames')
    if type(count) is not int or not 1 <= count <= 240:
        raise ValueError('Video frame count is missing or outside the bounded review range.')
    if (collection.get('schema') != 'byrdhouse.animation.collection.v1'
            or any(collection.get(key) != card.get(key) for key in
                   ('job_id', 'prompt_id', 'source_sha256', 'workflow_sha256', 'movie_sha256'))):
        raise ValueError('Video metadata and frame collection provenance disagree.')
    names = [f'frame_{i:04d}.png' for i in range(count)]
    entries = collection.get('frames', {})
    if set(entries) != set(names):
        raise ValueError('The complete collected frame set is required for video review.')
    if collection.get('encoded_frames_sha256') != _json_digest(entries):
        raise ValueError('The frame collection no longer matches the encoded video.')
    frames = []
    for i, name in enumerate(names):
        path = (directory / 'frames' / name).resolve()
        if not path.is_relative_to((directory / 'frames').resolve()) or sha(path) != entries[name].get('sha256'):
            raise ValueError('A collected animation frame changed or escaped its directory.')
        frames.append({'path': str(path), 'sha256': entries[name]['sha256'], 'index': i})
    movie = studio.video_path(parent['id'])
    if sha(movie) != card.get('movie_sha256'):
        raise ValueError('The video no longer matches its collected frames.')
    return frames, [{'path': str(movie), 'sha256': sha(movie)},
                    {'path': str(collection_path), 'sha256': sha(collection_path)}]


def run(config, spec, belt, stop):
    examiner = measurement_binding(config)
    if spec.get('measurement_binding') != examiner:
        raise ValueError('Examiner code or model weights changed after queueing; create a new likeness check.')
    directory = work_dir(config, spec['id'])
    directory.mkdir(parents=True, exist_ok=True)
    root = asset_root(config)
    binding = reference_binding(root, spec['selected_view'])
    if binding != spec['approved_view_binding']:
        raise ValueError('The approved matching view changed after this review was queued.')
    output_dir = Path(config['output_dir']).resolve()
    frame_root = (output_dir.parent / 'animation' / spec['source_job_id'] / 'frames').resolve()
    allowed_files = {str((output_dir / (spec['source_job_id'] + '.mp4')).resolve()),
                     str((frame_root.parent / 'collection.json').resolve())}
    frames = spec['review_frames']
    if not isinstance(frames, list) or not 1 <= len(frames) <= 240:
        raise ValueError('Invalid complete review frame list.')
    for row in frames:
        path = Path(row['path']).resolve()
        if not (path.parent == output_dir or path.parent == frame_root) or sha(path) != row['sha256']:
            raise ValueError('Review image changed or is outside the local source job.')
    for row in spec['review_files']:
        if str(Path(row['path']).resolve()) not in allowed_files or sha(row['path']) != row['sha256']:
            raise ValueError('The reviewed video or collection changed after queueing.')
    intent = {'schema': 'byrdhouse.anime-continuity.intent.v1', 'settings_sha256': _json_digest(spec)}
    intent_path = directory / 'intent.json'
    if intent_path.exists() and json.loads(intent_path.read_text(encoding='utf-8')) != intent:
        raise ValueError('Saved continuity review settings changed; refusing stale evidence.')
    _atomic_json(intent_path, intent)
    checkpoint_path = directory / 'checkpoint.json'
    checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8')) if checkpoint_path.exists() else {
        'intent_sha256': _json_digest(intent), 'reports': {}}
    if checkpoint.get('intent_sha256') != _json_digest(intent) or not isinstance(checkpoint.get('reports'), dict):
        raise ValueError('Saved review checkpoint belongs to different settings.')
    rows = []
    for frame in frames:
        if stop.is_set():
            raise ReviewInterrupted('CPU review interrupted; verified frame reports will resume without rendering.')
        path = Path(frame['path'])
        if reference_binding(root, spec['selected_view']) != binding or sha(path) != frame['sha256']:
            raise ValueError('Approved view or frame changed while reviewing.')
        report_path = directory / f"frame_{frame['index']:04d}.json"
        saved_hash = checkpoint['reports'].get(str(frame['index']))
        if saved_hash and (not report_path.is_file() or sha(report_path) != saved_hash):
            raise ValueError('Saved frame review changed; refusing stale evidence.')
        cached = json.loads(report_path.read_text(encoding='utf-8')) if saved_hash else None
        if cached:
            valid = (cached.get('schema') == 'byrdhouse.carey-anime.matching-view-review.v1'
                     and cached.get('target') == {'path': str(path), 'sha256': frame['sha256']}
                     and cached.get('approved_reference') == binding
                     and cached.get('selected_view') == spec['selected_view']
                     and cached.get('measurement_version') == examiner['measurement_version']
                     and cached.get('automatic_approval') is False)
            if not valid:
                raise ValueError('Saved frame review provenance changed; refusing stale evidence.')
            report = cached
        else:
            report = review(path, spec['selected_view'], root, belt=belt)
            if report['target']['sha256'] != frame['sha256'] or report['approved_reference'] != binding or sha(path) != frame['sha256']:
                raise ValueError('Frame or approved view changed during examination.')
            report['visual_review'] = {'findings': feature_findings(report)}
            _atomic_json(report_path, report)
            checkpoint['reports'][str(frame['index'])] = sha(report_path)
            _atomic_json(checkpoint_path, checkpoint)
        findings = report['visual_review']['findings']
        rows.append({'index': frame['index'], 'target_sha256': frame['sha256'],
                     'status': report['status'], 'geometry_delta': report.get('geometry_delta', {}),
                     'findings': findings, 'report_sha256': sha(report_path)})
        _atomic_json(directory / 'progress.json', {'completed': len(rows), 'total': len(frames)})
    counts = {feature: {'change': 0, 'review': 0, 'inconclusive': 0}
              for feature in (item['feature'] for item in rows[0]['findings'])}
    for row in rows:
        for finding in row['findings']:
            counts[finding['feature']][finding['status']] += 1
    summary = {'frames_examined': len(rows), 'total_frames': len(frames),
               'measurement_version': examiner['measurement_version'],
               'selected_view': spec['selected_view'], 'feature_counts': counts,
               'automatic_approval': False, 'identity_verified': False,
               'note': 'All saved frames were examined against one selected view. Detector and angle gaps remain inconclusive; eyes, beard, teeth and mouth require visual review.'}
    full = {'schema': 'byrdhouse.anime-continuity.review.v1',
            'measurement_binding': examiner,
            'purpose': 'Read-only complete-frame continuity evidence; never an identity approval',
            'source_job_id': spec['source_job_id'], 'approved_view_binding': binding,
            'settings_sha256': intent['settings_sha256'], 'summary': summary, 'frames': rows}
    full_path = directory / 'review.json'
    for frame in frames:
        if sha(frame['path']) != frame['sha256']:
            raise ValueError('A reviewed frame changed before the report was published.')
    if reference_binding(root, spec['selected_view']) != binding or any(
            sha(row['path']) != row['sha256'] for row in spec['review_files']):
        raise ValueError('The approved view or video changed before the report was published.')
    if measurement_binding(config) != examiner:
        raise ValueError('Examiner code or model weights changed during review; refusing mixed measurements.')
    _atomic_json(full_path, full)
    worst = max(rows, key=lambda row: (sum(f['status'] == 'change' for f in row['findings']),
                                      sum(f['status'] == 'inconclusive' for f in row['findings'])))
    report_path = directory / f"frame_{worst['index']:04d}.json"
    report = json.loads(report_path.read_text(encoding='utf-8'))
    filename = spec['id'] + '_1.png'
    target = output_dir / filename
    if 'target_face' in report and 'reference_face' in report:
        from render_belt_report import render
        visual = {'identity_mode': 'anime_anchor', 'reference': report['reference_face'],
                  'target': report['target_face'], 'selected': {'face': report['target_face']},
                  'visual_review': report['visual_review']}
        visual_path = directory / 'visual.json'
        _atomic_json(visual_path, visual)
        shutil.copyfile(render(visual_path), target)
    else:
        from PIL import Image, ImageDraw
        sheet = Image.new('RGB', (960, 620), '#141a25')
        with Image.open(next(frame['path'] for frame in frames if frame['index'] == worst['index'])) as source:
            source = source.convert('RGB'); source.thumbnail((800, 500))
            sheet.paste(source, ((960-source.width)//2, 70))
        ImageDraw.Draw(sheet).text((18, 18), 'INCONCLUSIVE: no comparable face measurement. Inspect the selected view manually.', fill='white')
        sheet.save(target)
    # Source bytes are not edited. The separate diagnostic image cannot be an animation source.
    card = {'schema': 'byrdhouse.studio.anime-continuity.v1', 'job_id': spec['id'],
            'purpose': full['purpose'], 'file': filename, 'review_state': 'needs_review',
            'identity_verified': False, 'exact_replica': False, 'source_job_id': spec['source_job_id'],
            'settings': spec, 'review_summary': summary, 'review_report_sha256': sha(full_path),
            'diagnostic_frame': worst['index'], 'generated_pixels': False}
    _atomic_json(target.with_suffix('.png.json'), card)
    return [filename]
