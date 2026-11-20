"""Preview-only scene dressing: stand-in materials, test textures, a turf plane with field
markings, night lighting driven by the light-bank metadata, cameras and render helpers.

Nothing in here is exported. The engine assigns its own materials by slot name.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from . import spec as S

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.dirname(os.path.dirname(HERE))
TEX_DIR = os.path.join(ART, "_scratch", "stadium", "tex")

TEAM_A = (0.60, 0.035, 0.07)      # stand-in team colours for SeatA / SeatB
TEAM_B = (0.05, 0.13, 0.40)


# ------------------------------------------------------------------------------------------------
# materials
# ------------------------------------------------------------------------------------------------
def _fresh(name):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    return mat, nt, out


def principled(name, color, rough=0.7, metal=0.0, emit=None, emit_strength=0.0, spec=0.5):
    mat, nt, out = _fresh(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = spec
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = emit_strength
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*color, 1.0)
    return mat


def emissive_image(name, image, strength=4.0, u_scale=1.0, base=0.02):
    mat, nt, out = _fresh(name)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.extension = "REPEAT"
    if u_scale != 1.0:
        uv = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (u_scale, 1.0, 1.0)
        nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (base, base, base, 1.0)
    b.inputs["Roughness"].default_value = 0.35
    nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = strength
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return mat


def vertex_color_material(name, attr="Col"):
    mat, nt, out = _fresh(name)
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_name = attr
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Roughness"].default_value = 0.8
    nt.links.new(a.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return mat


def leather_material(name, color):
    """Pebbled leather for the ball close-up."""
    mat, nt, out = _fresh(name)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = 0.55
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 520.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.0006
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return mat


# ---- test textures (drawn with Blender's own font) ---------------------------------------------
def _draw_image(name, w, h, painter):
    """painter(text, rect) callbacks draw into a float RGBA numpy canvas (row 0 = bottom)."""
    import blf
    import imbuf
    os.makedirs(TEX_DIR, exist_ok=True)
    canvas = np.zeros((h, w, 4), dtype=np.float32)
    canvas[..., 3] = 1.0
    texts = []

    def rect(x0, y0, x1, y1, color):
        x0, x1 = sorted((int(x0), int(x1)))
        y0, y1 = sorted((int(y0), int(y1)))
        canvas[max(0, y0):min(h, y1), max(0, x0):min(w, x1), :3] = color

    def text(s, x, y, size, color=(1, 1, 1), center=False):
        texts.append((s, x, y, size, color, center))

    painter(rect, text, canvas)
    base = os.path.join(TEX_DIR, name + "_bg.png")
    img = bpy.data.images.new(name + "_bg", w, h, alpha=False)
    img.pixels.foreach_set(canvas.ravel())
    img.filepath_raw = base
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    ib = imbuf.load(base)
    with blf.bind_imbuf(0, ib, display_name="sRGB"):
        for (s, x, y, size, color, center) in texts:
            blf.size(0, size)
            if center:
                tw, th = blf.dimensions(0, s)
                x = x - tw / 2
            blf.position(0, x, y, 0)
            blf.color(0, color[0], color[1], color[2], 1.0)
            blf.draw_buffer(0, s)
    path = os.path.join(TEX_DIR, name + ".png")
    imbuf.write(ib, filepath=path)
    out = bpy.data.images.load(path, check_existing=False)
    out.name = name
    out.pack()
    return out


def test_images():
    """Screen, score-board and ad-strip textures with readable text (proves UV orientation)."""
    def screen(rect, text, canvas):
        h, w = canvas.shape[:2]
        yy = np.linspace(0, 1, h)[:, None]
        xx = np.linspace(0, 1, w)[None, :]
        canvas[..., 0] = 0.02 + 0.10 * yy
        canvas[..., 1] = 0.05 + 0.12 * xx * (1 - yy)
        canvas[..., 2] = 0.16 + 0.30 * (1 - yy)
        rect(0, 0, w, 10, (1.0, 0.75, 0.1))
        rect(0, h - 10, w, h, (1.0, 0.75, 0.1))
        rect(0, 0, 10, h, (1.0, 0.75, 0.1))
        rect(w - 10, 0, w, h, (1.0, 0.75, 0.1))
        rect(60, 150, w - 60, 156, (1.0, 0.3, 0.1))
        text("4TH & FURY", w / 2, 330, 150, (1.0, 0.82, 0.15), True)
        text("TOUCHDOWN!", w / 2, 190, 110, (1, 1, 1), True)
        text("HOME 21", 60, 60, 64, (1.0, 0.35, 0.3))
        text("AWAY 17", w - 330, 60, 64, (0.45, 0.7, 1.0))
        text("top left", 26, h - 52, 30, (0.7, 0.9, 1.0))
        text("top right", w - 150, h - 52, 30, (0.7, 0.9, 1.0))

    def small(rect, text, canvas):
        h, w = canvas.shape[:2]
        canvas[..., :3] = (0.02, 0.03, 0.05)
        rect(0, 0, w, 6, (1.0, 0.75, 0.1))
        rect(0, h - 6, w, h, (1.0, 0.75, 0.1))
        rect(330, 20, 336, h - 20, (0.5, 0.5, 0.5))
        rect(688, 20, 694, h - 20, (0.5, 0.5, 0.5))
        text("HOME", 40, 150, 70, (1.0, 0.35, 0.3))
        text("21", 110, 40, 110, (1, 1, 1))
        text("Q3  08:42", 512, 150, 62, (1.0, 0.82, 0.15), True)
        text("2ND & 7", 512, 50, 80, (1, 1, 1), True)
        text("AWAY", 740, 150, 70, (0.45, 0.7, 1.0))
        text("17", 820, 40, 110, (1, 1, 1))

    ads = [("FURY COLA", (0.75, 0.05, 0.05), (1, 1, 1)),
           ("IRONJAW BBQ", (0.95, 0.75, 0.1), (0.1, 0.05, 0.02)),
           ("ZAPP! ENERGY", (0.05, 0.45, 0.2), (1, 1, 0.3)),
           ("TURBOHAWK TIRES", (0.08, 0.1, 0.14), (1.0, 0.5, 0.1)),
           ("4TH & FURY", (0.1, 0.2, 0.7), (1, 1, 1)),
           ("GRIDIRON GRUB", (0.9, 0.9, 0.88), (0.7, 0.1, 0.1)),
           ("KRAKEN KICKS", (0.35, 0.1, 0.5), (0.6, 1.0, 0.9)),
           ("NIGHT OWL RADIO", (0.02, 0.02, 0.03), (0.3, 0.8, 1.0))]

    def adstrip(rect, text, canvas):
        h, w = canvas.shape[:2]
        bw = w // len(ads)
        for i, (label, bg, fg) in enumerate(ads):
            rect(i * bw, 0, (i + 1) * bw, h, bg)
            rect(i * bw, 0, i * bw + 3, h, (0, 0, 0))
            rect((i + 1) * bw - 3, 0, (i + 1) * bw, h, (0, 0, 0))
            text(label, i * bw + bw / 2, 26, 46 if len(label) < 13 else 38, fg, True)

    return dict(
        Screen=_draw_image("pv_screen", 1024, 576, screen),
        ScreenSmall=_draw_image("pv_small", 1024, 256, small),
        AdBoard=_draw_image("pv_ads", 4096, 80, adstrip),
        ads=len(ads),
    )


# Flat colour per slot. The objects are exported wearing these plain materials, so the FBX files
# carry nothing but the slot names and a diffuse colour (no texture references); the preview
# shaders below are swapped in afterwards.
BASE_COLORS = {
    "Concrete": (0.50, 0.50, 0.51), "ConcreteDark": (0.055, 0.058, 0.068), "SeatA": TEAM_A, "SeatB": TEAM_B,
    "Steel": (0.30, 0.32, 0.36), "Glass": (0.035, 0.07, 0.10), "WallPad": (0.03, 0.07, 0.24),
    "AdBoard": (0.6, 0.6, 0.6), "Screen": (0.05, 0.08, 0.2), "ScreenSmall": (0.05, 0.05, 0.06),
    "Lamp": (1.0, 1.0, 1.0), "LampHousing": (0.025, 0.027, 0.03), "Apron": (0.30, 0.105, 0.075),
    "Roof": (0.74, 0.76, 0.80),
    "GoalYellow": (0.95, 0.72, 0.03), "GoalPad": (0.03, 0.07, 0.24), "Leather": (0.33, 0.115, 0.045),
    "Laces": (0.92, 0.91, 0.87), "BallStripe": (0.93, 0.92, 0.88), "Tee": (0.95, 0.33, 0.04),
    "Pylon": (1.0, 0.36, 0.03), "BenchSeat": (0.72, 0.74, 0.76), "CoolerBody": (0.95, 0.42, 0.04),
    "MarkerOrange": (1.0, 0.33, 0.02), "DownFace": (0.9, 0.9, 0.88), "CameraBody": (0.06, 0.065, 0.075),
    "Crowd": (0.5, 0.5, 0.5),
}


def plain_materials():
    """One texture-less material per slot name, for building and exporting."""
    return {name: principled(name, color) for name, color in BASE_COLORS.items()}


def stadium_materials():
    imgs = test_images()
    mats = {
        "Concrete": principled("Concrete", (0.50, 0.50, 0.51), 0.85),
        "ConcreteDark": principled("ConcreteDark", (0.055, 0.058, 0.068), 0.9),
        "SeatA": principled("SeatA", TEAM_A, 0.6),
        "SeatB": principled("SeatB", TEAM_B, 0.6),
        "Steel": principled("Steel", (0.30, 0.32, 0.36), 0.42, 0.75),
        "Glass": principled("Glass", (0.035, 0.07, 0.10), 0.06, 0.0, spec=1.0),
        "WallPad": principled("WallPad", (0.03, 0.07, 0.24), 0.55),
        "AdBoard": emissive_image("AdBoard", imgs["AdBoard"], 2.2, 1.0 / imgs["ads"]),
        "Screen": emissive_image("Screen", imgs["Screen"], 5.0),
        "ScreenSmall": emissive_image("ScreenSmall", imgs["ScreenSmall"], 4.0),
        "Lamp": principled("Lamp", (1, 1, 1), 0.3, emit=(1.0, 0.97, 0.9), emit_strength=38.0),
        "LampHousing": principled("LampHousing", (0.025, 0.027, 0.03), 0.5, 0.3),
        "Apron": principled("Apron", (0.30, 0.105, 0.075), 0.9),
        "Roof": principled("Roof", (0.74, 0.76, 0.80), 0.7),
    }
    return mats


def prop_materials():
    return {
        "GoalYellow": principled("GoalYellow", (0.95, 0.72, 0.03), 0.35),
        "GoalPad": principled("GoalPad", (0.03, 0.07, 0.24), 0.6),
        "Leather": leather_material("Leather", (0.33, 0.115, 0.045)),
        "Laces": principled("Laces", (0.92, 0.91, 0.87), 0.6),
        "BallStripe": principled("BallStripe", (0.93, 0.92, 0.88), 0.55),
        "Tee": principled("Tee", (0.95, 0.33, 0.04), 0.6),
        "Pylon": principled("Pylon", (1.0, 0.36, 0.03), 0.55),
        "BenchSeat": principled("BenchSeat", (0.72, 0.74, 0.76), 0.35, 0.6),
        "CoolerBody": principled("CoolerBody", (0.95, 0.42, 0.04), 0.4),
        "MarkerOrange": principled("MarkerOrange", (1.0, 0.33, 0.02), 0.5),
        "DownFace": principled("DownFace", (0.9, 0.9, 0.88), 0.5),
        "CameraBody": principled("CameraBody", (0.06, 0.065, 0.075), 0.45, 0.2),
        "Crowd": vertex_color_material("Crowd"),
    }


# ------------------------------------------------------------------------------------------------
# preview turf with markings (never exported)
# ------------------------------------------------------------------------------------------------
def field_ground(collection=None):
    from .meshkit import MeshBuilder
    mb = MeshBuilder()
    tx, ty = S.TURF_HX, S.TURF_HY
    fx, fy, gx = S.FIELD_HX, S.FIELD_HY, S.GOAL_X
    z = 0.0
    # mown stripes every 5 yards
    yd = 0.9144
    mb.quad((-tx, -ty, z), (tx, -ty, z), (tx, ty, z), (-tx, ty, z), "PV_Turf")
    k = 0
    x = -gx
    while x < gx - 1e-6:
        if k % 2 == 0:
            mb.quad((x, -fy, z + 0.004), (x + 5 * yd, -fy, z + 0.004), (x + 5 * yd, fy, z + 0.004),
                    (x, fy, z + 0.004), "PV_TurfLight")
        x += 5 * yd
        k += 1
    mb.quad((-fx, -fy, z + 0.006), (-gx, -fy, z + 0.006), (-gx, fy, z + 0.006), (-fx, fy, z + 0.006), "PV_EndA")
    mb.quad((gx, -fy, z + 0.006), (fx, -fy, z + 0.006), (fx, fy, z + 0.006), (gx, fy, z + 0.006), "PV_EndB")
    zl = z + 0.012

    def line(x0, y0, x1, y1):
        mb.quad((x0, y0, zl), (x1, y0, zl), (x1, y1, zl), (x0, y1, zl), "PV_Line")

    w = 0.10
    b = 1.8                                           # the white border
    line(-fx - b, -fy - b, fx + b, -fy)
    line(-fx - b, fy, fx + b, fy + b)
    line(-fx - b, -fy, -fx, fy)
    line(fx, -fy, fx + b, fy)
    for sgn in (-1, 1):
        line(sgn * gx - 0.1, -fy, sgn * gx + 0.1, fy)
    for i in range(1, 20):
        x = -gx + i * 5 * yd
        line(x - w / 2, -fy, x + w / 2, fy)
    hash_y = 6.1                                     # hash marks either side of centre
    for i in range(1, 100):
        if i % 5 == 0:
            continue
        x = -gx + i * yd
        for y in (-fy + 0.1, -hash_y - 0.3, hash_y - 0.3, fy - 0.7):
            line(x - 0.05, y, x + 0.05, y + 0.6)
    # midfield mark
    for a in range(48):
        a0, a1 = 2 * math.pi * a / 48, 2 * math.pi * (a + 1) / 48
        r0, r1 = 5.2, 5.8
        mb.quad((r0 * math.cos(a0), r0 * math.sin(a0), zl), (r1 * math.cos(a0), r1 * math.sin(a0), zl),
                (r1 * math.cos(a1), r1 * math.sin(a1), zl), (r0 * math.cos(a1), r0 * math.sin(a1), zl), "PV_Line")
    mats = {
        "PV_Turf": principled("PV_Turf", (0.035, 0.20, 0.045), 0.95),
        "PV_TurfLight": principled("PV_TurfLight", (0.05, 0.26, 0.06), 0.95),
        "PV_EndA": principled("PV_EndA", tuple(c * 0.8 for c in TEAM_A), 0.95),
        "PV_EndB": principled("PV_EndB", tuple(c * 0.8 for c in TEAM_B), 0.95),
        "PV_Line": principled("PV_Line", (0.9, 0.9, 0.9), 0.9),
    }
    return mb.to_object("PV_Ground", materials=mats, collection=collection)


# ------------------------------------------------------------------------------------------------
# lighting, cameras, rendering
# ------------------------------------------------------------------------------------------------
def night_world(scene, strength=1.0):
    world = bpy.data.worlds.get("PV_Night") or bpy.data.worlds.new("PV_Night")
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.035, 0.045, 0.085, 1.0)       # glow at the horizon
    ramp.color_ramp.elements[1].position = 0.45
    ramp.color_ramp.elements[1].color = (0.004, 0.006, 0.016, 1.0)       # dark overhead
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = world
    return world


def flood_lights(lights, power=95000.0, collection=None):
    """One wide spot per light bank, placed and aimed from the metadata."""
    objs = []
    for i, l in enumerate(lights):
        data = bpy.data.lights.new(f"PV_Flood{i}", "SPOT")
        data.energy = power
        data.spot_size = math.radians(118)
        data.spot_blend = 0.55
        data.shadow_soft_size = 3.0
        data.color = (1.0, 0.97, 0.92)
        obj = bpy.data.objects.new(f"PV_Flood{i}", data)
        (collection or bpy.context.scene.collection).objects.link(obj)
        pos, aim = Vector(l["pos"]), Vector(l["aim"])
        fwd = (aim - pos).normalized()
        obj.location = pos + fwd * 1.2            # just in front of the lamp faces
        obj.rotation_euler = fwd.to_track_quat("-Z", "Y").to_euler()
        objs.append(obj)
    return objs


def camera(scene, name="PV_Cam"):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        scene.collection.objects.link(cam)
    cam.data.clip_start = 0.05
    cam.data.clip_end = 2000.0
    scene.camera = cam
    return cam


def aim(cam, eye, target, lens=None, fov_deg=None):
    cam.location = Vector(eye)
    cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = 36.0
    if fov_deg is not None:
        cam.data.lens = 18.0 / math.tan(math.radians(fov_deg) / 2)
    elif lens is not None:
        cam.data.lens = lens


def setup_render(scene, engine="CYCLES", samples=64, exposure=0.0, look="Medium High Contrast", view="AgX"):
    scene.render.engine = engine
    if engine == "CYCLES":
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "METAL"
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            scene.cycles.device = "GPU"
        except Exception as exc:                       # CPU fallback
            print("cycles GPU unavailable:", exc)
        scene.cycles.samples = samples
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.02
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 5
        scene.cycles.diffuse_bounces = 3
        scene.cycles.glossy_bounces = 3
        scene.cycles.transmission_bounces = 4
        scene.cycles.sample_clamp_indirect = 8.0
    else:
        scene.eevee.taa_render_samples = samples
        scene.eevee.use_shadows = True
        scene.eevee.use_raytracing = True
    scene.view_settings.view_transform = view
    try:
        scene.view_settings.look = look if view == "AgX" else "None"
    except Exception:
        pass
    scene.view_settings.exposure = exposure
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"


def render(scene, path, width=1400, height=788):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path
