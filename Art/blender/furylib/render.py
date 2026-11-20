"""Preview rendering: a neutral studio, quick stills, and contact sheets.

Previews exist so the art can be judged by eye before it goes anywhere near Unreal.
"""
import math
import os
import bpy
import numpy as np
from mathutils import Vector


def reset_scene():
    """Empty file with sane defaults (metres, 30 fps)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.fps = 30
    scene.render.fps_base = 1.0
    return scene


def studio(scene=None, ground=True, world_strength=0.35):
    """Three-point lighting, a soft grey world and an optional ground plane."""
    scene = scene or bpy.context.scene
    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.16, 0.17, 0.19, 1.0)
        bg.inputs[1].default_value = world_strength
    scene.world = world

    def area(name, loc, energy, size, color=(1, 1, 1)):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = loc
        direction = Vector((0, 0, 1.0)) - Vector(loc)
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        return obj

    area("Key", (2.5, -3.5, 3.6), 420, 2.5, (1.0, 0.97, 0.92))
    area("Fill", (-3.5, -2.0, 2.0), 140, 3.5, (0.85, 0.92, 1.0))
    area("Rim", (-1.5, 3.5, 3.2), 380, 2.0, (0.9, 0.95, 1.0))

    if ground:
        bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
        plane = bpy.context.object
        plane.name = "PreviewGround"
        mat = bpy.data.materials.new("PreviewGround")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.10, 0.11, 0.12, 1)
            bsdf.inputs["Roughness"].default_value = 0.9
        plane.data.materials.append(mat)

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    return scene


def camera(scene=None, name="PreviewCam"):
    scene = scene or bpy.context.scene
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        scene.collection.objects.link(cam)
    scene.camera = cam
    return cam


def aim(cam, eye, target, lens=50.0):
    cam.location = Vector(eye)
    cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens


def orbit(cam, target=(0, 0, 1.0), distance=4.2, azimuth_deg=30.0, elevation_deg=8.0, lens=50.0):
    """Azimuth 0 looks at the character's front (camera on -Y); positive turns toward its left (+X)."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    t = Vector(target)
    eye = t + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * distance
    aim(cam, eye, t, lens)


def still(path, width=960, height=960, scene=None, samples=32):
    scene = scene or bpy.context.scene
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = samples
    bpy.ops.render.render(write_still=True)
    return path


def _load(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1]          # top row first


def contact_sheet(paths, out_path, columns=4, pad=6, background=(0.05, 0.05, 0.06, 1.0)):
    """Tile already-rendered PNGs (all the same size) into one image."""
    tiles = [_load(p) for p in paths]
    h, w = tiles[0].shape[:2]
    rows = (len(tiles) + columns - 1) // columns
    sheet = np.empty((rows * h + (rows + 1) * pad, columns * w + (columns + 1) * pad, 4), dtype=np.float32)
    sheet[:] = background
    for i, tile in enumerate(tiles):
        r, c = divmod(i, columns)
        y, x = pad + r * (h + pad), pad + c * (w + pad)
        sheet[y:y + h, x:x + w] = tile
    out = bpy.data.images.new("ContactSheet", sheet.shape[1], sheet.shape[0], alpha=True)
    out.pixels.foreach_set(sheet[::-1].ravel())
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.filepath_raw = out_path
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    return out_path
