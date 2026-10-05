"""Render existing belt measurements for visual checking; no inference or edits to originals."""
import argparse
import json
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageOps, ImageFont


def render(report_path):
    report_path = Path(report_path)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    findings = report.get('visual_review', {}).get('findings', [])
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 18)
    panels = []
    anime = report.get('identity_mode') == 'anime_anchor'
    for label, face in [(('Approved anime canon' if anime else 'Original Carey'), report['reference']),
                        ('Generated target', report['target']),
                        (('Review candidate' if anime else 'Corrected candidate'), report['selected']['face'])]:
        picture = Image.open(face['file']).convert('RGB')
        draw = ImageDraw.Draw(picture)
        left, top, right, bottom = face['bbox']
        width, height = right - left, bottom - top
        metrics = face['metrics']
        stroke = max(2, round(picture.width / 250))
        points = metrics.get('face_outline_signature', [])
        jaw = [(left + points[i] * width, top + points[i + 1] * height)
               for i in range(0, len(points), 2)]
        if jaw:
            draw.line(jaw, fill='#28ddf2', width=stroke)
        hairline = [tuple(point) for point in metrics.get('hairline_points', [])]
        if hairline:
            # Dots preserve gaps where the semantic parser did not find a boundary.
            for x, y in hairline:
                draw.ellipse((x-stroke, y-stroke, x+stroke, y+stroke), fill='#ffc857')
        if label in ('Review candidate', 'Corrected candidate'):
            marker_font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', max(18, round(picture.width / 30)))
            for index, finding in enumerate(findings, 1):
                fx, fy = finding['face_relative_point']
                x, y = left + fx * width, top + fy * height
                radius = max(14, round(picture.width / 38))
                x = max(radius + 2, min(picture.width - radius - 2, x))
                y = max(radius + 2, min(picture.height - radius - 2, y))
                fill = '#b63142' if finding.get('needs_change') else '#456579'
                draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=fill,outline='white',width=2)
                draw.text((x,y),str(index),font=marker_font,anchor='mm',fill='white')
        panel = Image.new('RGB', (420, 640), '#141a25')
        thumb = ImageOps.contain(picture, (420, 560))
        panel.paste(thumb, ((420-thumb.width)//2, 40 + (560-thumb.height)//2))
        text = ImageDraw.Draw(panel)
        text.text((12, 12), label, fill='white')
        text.text((12, 604), 'Gold: estimated hair edge | Cyan: jaw outline', fill='white')
        panels.append(panel)
    sheet = Image.new('RGB', (1260, 640 + (100 + 80*len(findings) if findings else 0)), '#141a25')
    for index, panel in enumerate(panels):
        sheet.paste(panel, (420*index, 0))
    if findings:
        draw = ImageDraw.Draw(sheet)
        draw.text((20,655),('CANON CONTINUITY REVIEW REQUIRED' if anime else
                          'NOT AN EXACT REPLICA - changes required before animation approval'),font=font,fill='#ffc857')
        draw.text((20,683),'Visual review of this pair. Pose and lighting differ; these are not calibrated biometric measurements.',font=font,fill='white')
        for index, finding in enumerate(findings, 1):
            y = 720 + (index-1)*80
            marker = 'CHANGE' if finding.get('needs_change') else 'REVIEW'
            color = '#ff8f7c' if finding.get('needs_change') else 'white'
            draw.text((20,y),f"{index}. [{marker}] {finding['feature']}: {finding['difference']}",font=font,fill=color)
            for line_index, line in enumerate(textwrap.wrap('Correction: ' + finding['correction'],width=124)):
                draw.text((42,y+25+line_index*23),line,font=font,fill='#b8d9ed')
    destination = report_path.with_name(report_path.stem + '-analysis.png')
    sheet.save(destination)
    destination.with_suffix('.png.json').write_text(json.dumps({
        'purpose': 'Visual verification of hairline and jaw measurements; not likeness approval',
        'source_report': str(report_path), 'generated_pixels': False,
        'visual_review': report.get('visual_review'),
    }, indent=2), encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    print(render(parser.parse_args().report))
