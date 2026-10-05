"""Encode the actually rendered Blender frames into a local review MP4."""
import argparse
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pack_dir', type=Path)
    args = parser.parse_args()
    root = args.pack_dir.resolve()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    expected = len(manifest['images']) * 48
    frames = sorted((root / 'preview_frames').glob('carey_*.png'))
    if len(frames) != expected:
        raise RuntimeError(f'Expected {expected} rendered frames, found {len(frames)}')
    output = root / 'Carey-camera-motion-preview.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y',
                    '-framerate', '24', '-i', str(root / 'preview_frames' / 'carey_%04d.png'),
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart', str(output)], check=True)
    output.with_suffix('.mp4.json').write_text(json.dumps({
        'purpose': 'Blender-rendered Carey still-image animatic preview; editable camera movement',
        'source_project': 'Carey-animation-stills.blend', 'pack_id': manifest['id'],
        'fps': 24, 'frames': expected, 'seconds': expected / 24,
        'width': 416, 'height': 608, 'source_images': manifest['images'],
        'identity_review_required': True, 'facial_or_body_animation': False,
    }, indent=2), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
