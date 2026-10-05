"""Read-only, matching-view review of a proposed Carey anime frame.

The approved head sheet supplies visual references, not a biometric identity
guarantee. This tool never changes pixels or approves an image automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from identity_belt import BeltError, IdentityBelt


DEFAULT_ROOT = Path('D:/ByrdHouse/assets/characters/carey-anime')
DEFAULT_CONFIG = Path('D:/ByrdHouse/byrdhouse-local.json')
SHEET_VIEWS = ('front', 'facing-right', 'back', 'facing-left')
VIEWS = SHEET_VIEWS + ('three-quarter',)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checked(path: Path, expected: str) -> Path:
    path = path.resolve(strict=True)
    if not isinstance(expected, str) or len(expected) != 64 or _sha256(path) != expected:
        raise ValueError(f'Approved Carey reference hash differs: {path}')
    return path


def reference_binding(root: Path, view: str) -> dict:
    """Validate and return the existing approved view; no face inference."""
    if view not in VIEWS:
        raise ValueError(f'View must be one of: {", ".join(VIEWS)}')
    root = root.resolve(strict=True)
    lock = json.loads((root / 'turnaround-v1.json').read_text(encoding='utf-8'))
    manifest = json.loads((root / 'views-v2' / 'manifest-v2.json').read_text(encoding='utf-8'))
    if (lock.get('schema') != 'byrdhouse.carey-anime.turnaround.v1'
            or lock.get('wardrobe_status') != 'placeholder_not_approved'):
        raise ValueError('Carey turnaround lock or wardrobe status is unexpected.')
    head = lock['assets']['head_sheet']
    source = _checked(Path(head['path']), head['sha256'])
    if not source.is_relative_to(root):
        raise ValueError('Approved head sheet is outside the locked asset directory.')
    if (Path(manifest['source']).resolve() != source
            or manifest['source_sha256'] != head['sha256']):
        raise ValueError('Approved head-sheet and crop manifest disagree.')
    entries = manifest['views']
    if len(entries) != len(SHEET_VIEWS) or {entry['view'] for entry in entries} != set(SHEET_VIEWS):
        raise ValueError('Approved view manifest is incomplete.')
    if view == 'three-quarter':
        anchor = lock['assets']['approved_closeup_anchor']
        entry = {'path': anchor['path'], 'sha256': anchor['sha256']}
    else:
        entry = next(item for item in entries if item['view'] == view)
    reference = _checked(Path(entry['path']), entry['sha256'])
    if not reference.is_relative_to(root):
        raise ValueError('Approved view crop is outside the locked asset directory.')
    return {'path': str(reference), 'sha256': entry['sha256'],
            'source_sheet': str(source), 'source_sha256': head['sha256'],
            'source_kind': ('approved_closeup_anchor' if view == 'three-quarter'
                            else 'approved_head_sheet_crop'),
            'lock_sha256': _sha256(root / 'turnaround-v1.json'),
            'manifest_sha256': _sha256(root / 'views-v2' / 'manifest-v2.json')}


def review(target: Path, view: str, root: Path = DEFAULT_ROOT,
           config_path: Path = DEFAULT_CONFIG, belt=None) -> dict:
    """Return evidence for human review; caller may save the JSON sidecar."""
    binding = reference_binding(root, view)
    reference = Path(binding['path'])
    target = target.resolve(strict=True)
    target_hash = _sha256(target)
    report = {
        'schema': 'byrdhouse.carey-anime.matching-view-review.v1',
        'created': datetime.now().astimezone().isoformat(),
        'purpose': 'Read-only likeness continuity review for an illustrated Carey frame',
        'target': {'path': str(target), 'sha256': target_hash},
        'selected_view': view,
        'approved_reference': binding,
        'wardrobe_scope': 'excluded; existing outfits are placeholders',
        'automatic_approval': False,
        'human_review_required': True,
    }
    from identity_belt import MEASUREMENT_VERSION
    report['measurement_version'] = MEASUREMENT_VERSION
    if view == 'back':
        report['status'] = 'visual_review_only_no_face_in_approved_rear_view'
        report['review_features'] = ['afro silhouette', 'head shape', 'body proportions']
        return report
    if belt is None:
        config = json.loads(config_path.read_text(encoding='utf-8'))
        belt = IdentityBelt(config, None)
    try:
        baseline = belt.inspect(reference, illustrated=True)
        candidate = belt.inspect(target, illustrated=True)
        report['reference_face'] = baseline.public()
        report['target_face'] = candidate.public()
        report['matching_view_similarity_review_cue'] = round(belt._similarity(baseline, candidate), 6)
        report['geometry_delta'] = belt._geometry(baseline, candidate, illustrated=True)
        report['status'] = 'measured_matching_view_human_review_required'
        report['review_features'] = ['face outline', 'hairline', 'afro silhouette',
                                     'forehead', 'skin tone under lighting']
    except BeltError as exc:
        report['status'] = 'inconclusive_detection_human_review_required'
        report['inspection_error'] = str(exc)
    return report


def feature_findings(report: dict) -> list:
    """Explain existing examiner deltas without treating them as identity proof."""
    geometry = report.get('geometry_delta', {})
    comparable = geometry.get('review_scope') == 'same_view_illustrated_continuity'
    measures = (
        ('Face outline', 'face_outline_error', .05, (.82, .72), 'Match the cheek and jaw contour to the approved view.'),
        ('Forehead height', 'forehead_height_ratio', .10, (.50, .25), 'Match visible forehead height between brows and curls.'),
        ('Afro width', 'hair_width_ratio', .16, (1.28, .05), 'Match the outward curls and crown width.'),
        ('Afro height', 'hair_height_ratio', .16, (.50, -.35), 'Match crown height and outer curl shape.'),
        ('Hairline position', 'hairline_y_ratio', .10, (.50, .02), 'Match the natural irregular hair-to-skin boundary.'),
        ('Skin brightness', 'skin_median_luma', None, (.28, .55), 'Check lighting against the approved brown skin tone; reject identity lightening.'),
    )
    findings = []
    for label, key, limit, point, guidance in measures:
        value = geometry.get(key)
        measured = comparable and isinstance(value, (int, float))
        metrics = [report.get(face, {}).get('metrics', {}) for face in ('reference_face', 'target_face')]
        if key == 'face_outline_error':
            measured = measured and all(item.get('landmark_confidence', 0) >= .5 for item in metrics)
        elif key != 'skin_median_luma':
            measured = measured and all(item.get('hairline_coverage', 0) >= .25 for item in metrics)
        change = measured and (geometry.get('skin_lightening_warning', False)
                               if limit is None else value > limit)
        status = 'change' if change else 'review' if measured else 'inconclusive'
        findings.append({'feature': label, 'metric': key, 'status': status,
                         'needs_change': bool(change),
                         'difference': (f"Skin brightness shift: {geometry.get('skin_luma_shift', 0):+.3f}; lighting-sensitive."
                                        if measured and limit is None else
                                        f'Normalized difference: {value}; review cue only.' if measured else
                                        'View differs, confidence is insufficient, or this feature was not measurable.'),
                         'correction': guidance if measured else 'Confirm the visible angle and inspect this feature manually.',
                         'face_relative_point': list(point)})
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--view', choices=VIEWS, required=True)
    args = parser.parse_args()
    report = review(args.target, args.view)
    sidecar = args.target.resolve(strict=True).with_name(args.target.stem + '-anime-view-review.json')
    sidecar.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(sidecar), 'status': report['status'],
                      'matching_view_similarity_review_cue': report.get('matching_view_similarity_review_cue'),
                      'automatic_approval': False}, indent=2))


if __name__ == '__main__':
    main()
