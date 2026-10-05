"""Thin bridge from the existing CPU mesh bundle to its saved Comfy cleanup graph.

No new detector, parser, warp or queue: use byrdfacezone and Studio's journal.
All candidates stay private, unapproved previews.
"""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image


class MeshCleanupError(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root(config):
    return Path(config['output_dir']).resolve().parent.parent


def freeze(config, zone_file, reference_binding):
    home=root(config)
    zone_file=Path(zone_file).resolve(strict=True)
    allowed=(home/'artifacts/face_zones').resolve()
    if not zone_file.is_relative_to(allowed) or zone_file.name!='face_zone.json':
        raise MeshCleanupError('Choose an existing audited CPU face-zone bundle.')
    zone=json.loads(zone_file.read_text(encoding='utf-8'))
    mesh=zone.get('identity_mesh',{})
    if (zone.get('manual_zone') or zone.get('generated_parent') is not None
            or not zone.get('upload_analysis',{}).get('all_passed')
            or not zone.get('crop_preflight',{}).get('passed')
            or mesh.get('eye_source_mode')!='identity'):
        raise MeshCleanupError('CPU preparation/identity-eye gates must pass before cleanup.')
    if (Path(mesh.get('reference','')).resolve()!=Path(reference_binding['path']).resolve()
            or mesh.get('reference_sha256')!=reference_binding['sha256']):
        raise MeshCleanupError('The mesh seed does not use the selected approved Carey view.')
    paths={'zone':zone_file,'source':Path(zone['source']).resolve(),
           'reference':Path(reference_binding['path']).resolve()}
    if sha(paths['source'])!=zone['source_sha256']:
        raise MeshCleanupError('Original upload changed after CPU preparation.')
    for name,value in zone['artifacts'].items():
        path=Path(value).resolve(strict=True)
        if not path.is_relative_to(zone_file.parent):
            raise MeshCleanupError('CPU artifact escaped its saved bundle.')
        paths[name]=path
    for key in ('original','identity_mesh_seed','soft_mask','graded_mask','hair_headwear_exclusion'):
        if key not in paths: raise MeshCleanupError('CPU bundle lacks '+key)
    scripts=home/'repo/scripts'
    paths['helper_code']=scripts/'byrdfacezone.py'
    paths['composite_code']=scripts/'facezone_composite.py'
    paths['template']=home/'repo/workflows/sd15_face_mesh_seed_refine_api.json'
    paths['adapter_code']=Path(__file__).resolve()
    return {'zone_file':str(zone_file),'files':{key:{'path':str(path),'sha256':sha(path)} for key,path in paths.items()},
            'reference_binding':copy.deepcopy(reference_binding),'private_evaluation_only':True}


def verify(config, binding):
    if not Path(binding['zone_file']).resolve().is_relative_to(root(config)/'artifacts/face_zones'):
        raise MeshCleanupError('CPU bundle is outside this deployment.')
    for row in binding['files'].values():
        if sha(row['path'])!=row['sha256']:
            raise MeshCleanupError('Mesh input, mask or code changed after queueing: '+Path(row['path']).name)
    # Recheck the actual canon lock, not just the cached reference path/hash.
    from anime_view_review import reference_binding
    current=reference_binding(root(config)/'assets/characters/carey-anime',binding['reference_binding']['selected_view'])
    expected={k:v for k,v in binding['reference_binding'].items() if k!='selected_view'}
    if current!=expected: raise MeshCleanupError('Approved Carey view lock changed after queueing.')
    return json.loads(Path(binding['zone_file']).read_text(encoding='utf-8'))


def stage(config, spec):
    verify(config,spec['mesh_binding'])
    directory=(Path(config['comfy_dir'])/'input/ByrdHouse/mesh'/spec['id']).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    result={}
    for key,name in [('identity_mesh_seed','seed.png'),('graded_mask','mask.png')]:
        row=spec['mesh_binding']['files'][key]
        path=directory/name
        if not path.exists(): path.write_bytes(Path(row['path']).read_bytes())
        if sha(path)!=row['sha256']: raise MeshCleanupError('Staged mesh input changed: '+name)
        result[key]='ByrdHouse/mesh/'+spec['id']+'/'+name
    return result


def build(config,spec):
    inputs=stage(config,spec)
    original=json.loads(Path(spec['mesh_binding']['files']['template']['path']).read_text())
    # Remap the saved graph to Studio's existing checkpoint/sampler/save IDs.
    mapping={'1':'2','2':'3','3':'10','4':'1','5':'4','6':'5','7':'6','8':'11','9':'7','10':'8','11':'9'}
    def remap(value):
        if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and value[0] in mapping and type(value[1]) is int:
            return [mapping[value[0]],value[1]]
        if isinstance(value,dict): return {key:remap(item) for key,item in value.items()}
        if isinstance(value,list): return [remap(item) for item in value]
        return value
    graph={mapping[key]:remap(value) for key,value in original.items() if key in mapping}
    graph['1']['inputs']['ckpt_name']=spec['checkpoint']
    graph['2']['inputs']['image']=inputs['identity_mesh_seed']
    graph['3']['inputs']['image']=inputs['graded_mask']
    graph['4']['inputs']['text']=spec['full_prompt']
    graph['5']['inputs']['text']=spec['negative']
    graph['7']['inputs'].update(seed=spec['seed'],steps=20,cfg=4.0,denoise=spec['denoise'])
    graph['9']['inputs']['filename_prefix']='ByrdHouse/mesh-cleanup-'+spec['id']
    return graph


def finish(config,spec,target):
    zone=verify(config,spec['mesh_binding'])
    directory=root(config)/'media/mesh-edits'/spec['id']
    directory.mkdir(parents=True,exist_ok=True)
    raw=directory/'generated-crop.png'
    raw.write_bytes(Path(target).read_bytes())
    with Image.open(raw) as image:
        if image.size!=(zone['canvas_size'],zone['canvas_size']):
            raise MeshCleanupError('Cleanup returned an unexpected crop size.')
    scripts=root(config)/'repo/scripts'
    if str(scripts) not in sys.path: sys.path.insert(0,str(scripts))
    helper=importlib.import_module('byrdfacezone')
    if Path(helper.__file__).resolve()!=Path(spec['mesh_binding']['files']['helper_code']['path']).resolve():
        raise MeshCleanupError('CPU compositor import differs from bound code.')
    output=directory/'composited.png'
    helper.composite_generated(Path(spec['mesh_binding']['zone_file']),raw,output)
    # Reassert protected hair exactly using the existing material-restoration helper.
    original=Image.open(zone['artifacts']['original']).convert('RGB')
    final=Image.open(output).convert('RGB')
    box=zone['crop_box']; side=box['width']; x,y=box['x'],box['y']
    hair=Image.open(zone['artifacts']['hair_headwear_exclusion']).convert('L').resize((side,side),Image.Resampling.NEAREST)
    material=Image.new('L',original.size,0); material.paste(hair,(x,y))
    final=helper.restore_protected_material(final,original,material)
    soft=Image.open(zone['artifacts']['soft_mask']).convert('L').resize((side,side),Image.Resampling.BILINEAR)
    full_mask=Image.new('L',original.size,0); full_mask.paste(soft,(x,y))
    changed=np.any(np.asarray(final)!=np.asarray(original),axis=2)
    outside=int(np.count_nonzero(changed & (np.asarray(full_mask)==0)))
    hair_changes=int(np.count_nonzero(changed & (np.asarray(material)==255)))
    if outside or hair_changes: raise MeshCleanupError('Protected source pixels changed during cleanup composite.')
    final.save(output,'PNG')
    verify(config,spec['mesh_binding'])
    Path(target).write_bytes(output.read_bytes())
    report={'purpose':'Audited cleanup of existing Carey mesh seed, using saved mask/template; private unapproved preview',
            'raw_crop':str(raw),'raw_crop_sha256':sha(raw),'final_sha256':sha(target),
            'outside_mask_changed_pixels':outside,'protected_hair_changed_pixels':hair_changes,
            'changed_pixels':int(changed.sum()),'width':original.width,'height':original.height,
            'identity_verified':False,'exact_replica':False,'review_state':'needs_review'}
    (directory/'composite-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
