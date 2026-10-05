"""Render a small review video from the loaded, editable Blender pack project."""
from pathlib import Path
import bpy

scene = bpy.context.scene
root = Path(bpy.data.filepath).parent
scene.render.resolution_percentage = 50
if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'taa_render_samples'):
    scene.eevee.taa_render_samples = 8
preview = root / 'preview_frames'
preview.mkdir(exist_ok=True)
scene.render.filepath = str(preview / 'carey_')
scene.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True)
