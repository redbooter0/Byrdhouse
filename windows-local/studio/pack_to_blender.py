"""Run with Blender --background --python this_file -- <extracted-pack-dir>.

Creates an editable timeline of image planes with subtle camera movement.
This is a still-image animatic; it does not synthesize body or facial motion.
"""
import json
import math
import sys
from pathlib import Path

import bpy


def build(pack_dir):
    pack_dir = Path(pack_dir).resolve()
    manifest = json.loads((pack_dir / 'manifest.json').read_text(encoding='utf-8'))
    entries = manifest['images']
    if not entries:
        raise ValueError('This pack contains no images.')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 832
    scene.render.resolution_y = 1216
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.view_settings.view_transform = 'Standard'
    scene.world.color = (0, 0, 0)
    scene.render.image_settings.file_format = 'PNG'
    frame = 1
    for index, entry in enumerate(entries):
        image_path = (pack_dir / entry['file']).resolve()
        if not image_path.is_relative_to(pack_dir):
            raise ValueError('Image path leaves the pack directory.')
        image = bpy.data.images.load(str(image_path), check_existing=True)
        width, height = image.size[:]
        plane_height = 10.0
        plane_width = plane_height * width / height
        center = index * 24.0
        bpy.ops.mesh.primitive_plane_add(size=2, location=(center, 0, 0))
        plane = bpy.context.object
        plane.name = entry.get('label') or f'Carey shot {index + 1}'
        plane.scale = (plane_width / 2, plane_height / 2, 1)
        material = bpy.data.materials.new(plane.name)
        material.use_nodes = True
        nodes = material.node_tree.nodes
        nodes.clear()
        texture = nodes.new('ShaderNodeTexImage')
        texture.image = image
        emission = nodes.new('ShaderNodeEmission')
        output = nodes.new('ShaderNodeOutputMaterial')
        material.node_tree.links.new(texture.outputs['Color'], emission.inputs['Color'])
        material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
        plane.data.materials.append(material)
        bpy.ops.object.camera_add(location=(center, 0, 12))
        camera = bpy.context.object
        camera.name = f'Shot {index + 1}: {plane.name}'
        camera.data.type = 'ORTHO'
        # Include the complete image without cropping its head, hands or feet.
        camera.data.ortho_scale = max(plane_height, plane_width * 1216 / 832) * 1.06
        camera.keyframe_insert(data_path='location', frame=frame)
        camera.location.x += plane_width * 0.008
        camera.location.y += plane_height * 0.005
        camera.keyframe_insert(data_path='location', frame=frame + 47)
        camera.data.keyframe_insert(data_path='ortho_scale', frame=frame)
        camera.data.ortho_scale *= 0.985
        camera.data.keyframe_insert(data_path='ortho_scale', frame=frame + 47)
        marker = scene.timeline_markers.new(plane.name, frame=frame)
        marker.camera = camera
        if index == 0:
            scene.camera = camera
        frame += 48
    scene.frame_start = 1
    scene.frame_end = frame - 1
    scene.frame_set(1)
    scene.render.filepath = str(pack_dir / 'frames' / 'carey_')
    (pack_dir / 'frames').mkdir(exist_ok=True)
    # Pack all PNGs into the .blend so moving it doesn't break its textures.
    bpy.ops.file.pack_all()
    project = pack_dir / 'Carey-animation-stills.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(project))
    project.with_suffix('.blend.json').write_text(json.dumps({
        'purpose': 'Editable Carey still-image animatic; camera motion only',
        'project': project.name, 'shots': len(entries), 'fps': 24,
        'frames': scene.frame_end, 'identity_review_required': True,
        'body_or_facial_animation': False,
        'pack_id': manifest['id'], 'source_images': entries,
    }, indent=2), encoding='utf-8')
    print(f'BYRDHOUSE_PROJECT={project}')


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if len(args) != 1:
        raise SystemExit('Pass the extracted pack directory after --')
    build(args[0])
