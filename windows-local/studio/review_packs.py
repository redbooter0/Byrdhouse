"""Create local QA contact sheets and export completed Studio packs."""
import argparse
import io
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args()
    config = json.loads((ROOT / 'byrdhouse-local.json').read_text(encoding='utf-8-sig'))
    base = f"http://{config['studio_host']}:{config['studio_port']}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def fetch(route, binary=False):
        with opener.open(base + route, timeout=30) as response:
            data = response.read()
        return data if binary else json.loads(data)
    out = ROOT / 'media' / 'packs'
    out.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 17)
    small = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 13)
    index = []
    for pack in fetch('/api/packs')['packs']:
        jobs = pack['jobs']
        completed = [job for job in jobs if job['images'] and job['state'] != 'rejected']
        if not completed:
            continue
        recipe = jobs[0]['recipe']
        name = f"{recipe}_{pack['id'][:6]}"
        cards = [('ORIGINAL CAREY PHOTO', Image.open(io.BytesIO(fetch('/references/' + completed[0]['reference'], True))).convert('RGB'), 'Reference')]
        for job in completed:
            image = Image.open(io.BytesIO(fetch(job['images'][0], True))).convert('RGB')
            cards.append((job['variant'], image, f"{job['id'][:8]} / {job['state']}"))
        cols, cell_w, cell_h = 3, 310, 440
        rows = (len(cards) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * cell_w, rows * cell_h + 52), '#111718')
        draw = ImageDraw.Draw(sheet)
        draw.text((12, 12), f"Carey / {pack['title']} / {len(completed)} of {len(jobs)} candidates", font=font, fill='#ccf17b')
        for number, (label, picture, note) in enumerate(cards):
            x, y = (number % cols) * cell_w, 52 + (number // cols) * cell_h
            scaled = ImageOps.contain(picture, (cell_w - 16, cell_h - 65))
            sheet.paste(scaled, (x + (cell_w - scaled.width) // 2, y + 30 + (cell_h - 65 - scaled.height) // 2))
            draw.text((x + 8, y + 4), label, font=font, fill='white')
            draw.text((x + 8, y + cell_h - 26), note, font=small, fill='#a3aaa6')
        path = out / (name + '_contact.png')
        sheet.save(path)
        path.with_suffix('.png.json').write_text(json.dumps({
            'purpose': 'Visual QA comparison of actual Carey reference and generated still candidates',
            'pack_id': pack['id'], 'identity_verified': False,
            'jobs': [job['id'] for job in completed],
        }, indent=2), encoding='utf-8')
        ready = not any(job['state'] in ('queued', 'running') for job in jobs)
        row = {'id': pack['id'], 'recipe': recipe, 'title': pack['title'], 'completed': len(completed),
               'total': len(jobs), 'ready': ready, 'contact_sheet': str(path),
               'failed': [job['id'] for job in jobs if job['state'] == 'failed']}
        if args.export and ready:
            target = out / (name + '.zip')
            target.write_bytes(fetch('/api/packs/' + pack['id'] + '/download', True))
            row['zip'] = str(target)
        index.append(row)
        print(json.dumps(row), flush=True)
    (out / 'index.json').write_text(json.dumps({'purpose': 'Local Carey candidate pack index', 'packs': index}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
