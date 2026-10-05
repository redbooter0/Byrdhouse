"""Recover already-rendered outputs after a Studio/ComfyUI HTTP timeout.

Run only with Studio stopped and both queues idle. Never resubmit a prompt.
"""
import json
from pathlib import Path

from server import ComfyClient, Studio, load_config, utcnow

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = load_config(ROOT / 'byrdhouse-local.json')
    client = ComfyClient(config['comfy_url'])
    queue = client.request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):
        raise RuntimeError('Wait for ComfyUI to finish before recovery.')
    import sqlite3
    with sqlite3.connect(ROOT / 'studio' / 'jobs.sqlite3') as db:
        if db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('running','queued')").fetchone()[0]:
            raise RuntimeError('Wait for the Studio queue to finish before recovery.')
    history = client.request('/history')
    records = {}
    for prompt_id, record in history.items():
        prompt = record.get('prompt', [])
        if len(prompt) < 3 or not isinstance(prompt[2], dict):
            continue
        prefix = prompt[2].get('9', {}).get('inputs', {}).get('filename_prefix', '')
        if prefix.startswith('ByrdHouse/') and record.get('status', {}).get('completed'):
            records[prefix.split('/')[-1]] = (prompt_id, record)
    studio = Studio(config, ROOT / 'studio', client, start_worker=False)
    recovered = []
    for job in studio.jobs():
        if job['state'] != 'failed' or 'timed out' not in (job['error'] or '') or job['id'] not in records:
            continue
        prompt_id, record = records[job['id']]
        if record.get('status', {}).get('status_str') == 'error':
            continue
        # Reuse the exact stored job specification and existing backend record.
        with studio.db() as db:
            spec = json.loads(db.execute('SELECT spec FROM jobs WHERE id=?', (job['id'],)).fetchone()[0])
        outputs = studio.generate(spec, resume_prompt_id=prompt_id)
        stamps = {kind: payload.get('timestamp') for kind, payload in record.get('status', {}).get('messages', []) if isinstance(payload, dict)}
        start, end = stamps.get('execution_start'), stamps.get('execution_success')
        seconds = round((end - start) / 1000, 2) if start is not None and end is not None else None
        for output in outputs:
            path = studio.output_dir / output
            card_path = path.with_suffix('.png.json')
            card = json.loads(card_path.read_text(encoding='utf-8'))
            card.update(recovered_after_http_timeout=True, execution_seconds=seconds)
            card_path.write_text(json.dumps(card, indent=2), encoding='utf-8')
        with studio.db() as db:
            db.execute("UPDATE jobs SET state='needs_review',finished=?,outputs=?,error=NULL,seconds=? WHERE id=?",
                       (utcnow(), json.dumps(outputs), seconds, job['id']))
        recovered.append({'id': job['id'], 'prompt_id': prompt_id, 'variant': job.get('variant'), 'seconds': seconds})
        print(json.dumps(recovered[-1]), flush=True)
    report = ROOT / 'media' / 'packs' / 'timeout-recovery.json'
    report.write_text(json.dumps({'purpose': 'Recovery audit; no prompt was submitted again', 'recovered': recovered}, indent=2), encoding='utf-8')
    studio.close()


if __name__ == '__main__':
    main()
