"""Run the upstream no-driving-video example with an original Carey portrait."""
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import time

import imageio_ffmpeg
from server import ComfyClient, BackendError

ROOT = Path(__file__).resolve().parent.parent
config = json.loads((ROOT/'byrdhouse-local.json').read_text())
client = ComfyClient(config['comfy_url'])
upstream = ROOT/'repo/external/ComfyUI-AdvancedLivePortrait'
workflow = upstream/'sample/workflows/Advanced_Animate_without_vid.json'
sample = json.loads(workflow.read_text())
job_id = secrets.token_hex(16)
output = ROOT/'media/animation'/job_id
output.mkdir(parents=True)
source = ROOT/'training/carey/references/portrait.jpeg'
source_copy = Path(config['comfy_dir'])/'input/ByrdHouse/carey/liveportrait-original.jpeg'
source_copy.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source, source_copy)
graph = {}
for node in sample['nodes']:
    if node['type'] not in ('LoadImage', 'ExpressionEditor', 'AdvancedLivePortrait'):
        continue
    info = client.request('/object_info/'+node['type'])[node['type']]
    names = info['input_order']['required']
    graph[str(node['id'])] = {'class_type':node['type'],
                            'inputs':dict(zip(names,node['widgets_values']))}
graph['3']['inputs'] = {'image':'ByrdHouse/carey/liveportrait-original.jpeg'}
graph['15']['inputs'].update(src_image=['3',0],wink=0,blink=-8,rotate_yaw=1.5)
graph['7']['inputs'].update(motion_link=['15',1],command='0 = 1:10\n1 = 3:1\n0 = 3:26')
graph['10'] = {'class_type':'SaveImage','inputs':{
    'images':['7',0], 'filename_prefix':f'Carey-LivePortrait/{job_id}/frame'}}
(output/'workflow.json').write_text(json.dumps(graph,indent=2))
card = {'schema':'byrdhouse.animation.preview.v1','job_id':job_id,
        'purpose':'Original Carey photo animated with restrained blink/head movement for identity review',
        'state':'queued','source':str(source),
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'upstream_workflow':str(workflow),'upstream_commit':'3bba732915e22f18af0d221b9c5c282990181f1b',
        'identity_verified':False,'exact_replica':False,'review_required':True,
        'note':'LivePortrait reconstructs moving face pixels; this is not an exact-pixel identity guarantee.',
        'fps':15,'frames_expected':44}
card_path=output/'job.json'
def save(): card_path.write_text(json.dumps(card,indent=2))
save()
started=time.monotonic()
try:
    queued=client.request('/prompt',{'prompt':graph,'client_id':'byrdhouse-liveportrait'})
    card.update(state='running',prompt_id=queued['prompt_id']); save()
    print(json.dumps({'job':str(card_path),'prompt_id':card['prompt_id']}),flush=True)
    while True:
        try: history=client.request('/history/'+card['prompt_id']).get(card['prompt_id'])
        except BackendError: time.sleep(2); continue
        if history and history.get('status',{}).get('status_str')=='error':
            raise RuntimeError(json.dumps(history['status']['messages'])[-3000:])
        if history and history.get('status',{}).get('completed'): break
        time.sleep(2)
    rows=history['outputs']['10']['images']
    if len(rows)!=44: raise RuntimeError(f'Expected 44 frames; got {len(rows)}')
    frames=output/'frames'; frames.mkdir()
    for i,row in enumerate(rows):
        path=ROOT/'media/comfy'/row['subfolder']/row['filename']
        shutil.copy2(path,frames/f'frame_{i:04d}.png')
    movie=output/'Carey-original-photo-motion.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error',
        '-framerate','15','-i',str(frames/'frame_%04d.png'),'-c:v','libx264',
        '-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(movie)],check=True)
    card.update(state='needs_review',frames=len(rows),seconds=len(rows)/15,
                elapsed_seconds=round(time.monotonic()-started,2),output=str(movie))
    save(); movie.with_suffix('.mp4.json').write_text(json.dumps(card,indent=2))
    print(json.dumps(card,indent=2),flush=True)
except Exception as exc:
    card.update(state='failed',error=str(exc)); save(); raise
