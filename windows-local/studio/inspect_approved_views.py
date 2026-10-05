"""Measure Carey's locked multi-view sheet without approving any generated frame.

Run with the bundled ByrdHouse Python and its venv site-packages on PYTHONPATH.
This is a read-only examiner; only the JSON report is written.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from identity_belt import BeltError, IdentityBelt


ROOT = Path('D:/ByrdHouse/assets/characters/carey-anime')
LOCK = ROOT / 'turnaround-v1.json'
VIEWS = ROOT / 'views-v2' / 'manifest-v2.json'
CONFIG = Path('D:/ByrdHouse/byrdhouse-local.json')
REPORT = ROOT / 'views-v2' / 'inspection-v1.json'


def checked(path: Path, expected_hash: str) -> Path:
    path = path.resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError(f'Approved reference changed: {path}')
    return path


def main() -> None:
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    manifest = json.loads(VIEWS.read_text(encoding='utf-8'))
    checked(Path(manifest['source']), manifest['source_sha256'])
    anchor = lock['assets']['approved_closeup_anchor']
    anchor_path = checked(Path(anchor['path']), anchor['sha256'])
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    belt = IdentityBelt(config, None)
    anchor_record = belt.inspect(anchor_path, illustrated=True)
    results = []
    for item in manifest['views']:
        view_path = checked(Path(item['path']), item['sha256'])
        result = {'view': item['view'], 'path': str(view_path),
                  'sha256': item['sha256'], 'box': item['box'],
                  'automatic_approval': False}
        if item['view'] == 'back':
            result['status'] = 'no face in rear view; visual hair/body review only'
        else:
            try:
                record = belt.inspect(view_path, illustrated=True)
                result['status'] = 'measured; human view match still required'
                result['face'] = record.public()
                result['similarity_to_front_anchor_review_cue'] = round(
                    belt._similarity(anchor_record, record), 6)
                result['geometry_vs_front_anchor'] = belt._geometry(
                    anchor_record, record, illustrated=True)
            except BeltError as exc:
                result['status'] = 'inconclusive; visual review required'
                result['error'] = str(exc)
        results.append(result)
    report = {'schema': 'byrdhouse.carey-anime.approved-view-inspection.v1',
              'created': datetime.now().astimezone().isoformat(),
              'visual_likeness_approval': 'Carey approved the model sheets in chat',
              'automatic_frame_approval': False,
              'anchor_sha256': anchor['sha256'],
              'sheet_sha256': manifest['source_sha256'],
              'results': results}
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(REPORT), 'results': [
        {'view': r['view'], 'status': r['status'],
         'similarity': r.get('similarity_to_front_anchor_review_cue'),
         'review_scope': r.get('geometry_vs_front_anchor', {}).get('review_scope')}
        for r in results]}, indent=2))


if __name__ == '__main__':
    main()
