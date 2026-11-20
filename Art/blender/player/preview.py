"""Preview renders used to judge the athlete by eye: turnarounds, close-ups, deformation tests and
the UV / normal checks. Nothing here is exported; it only writes PNGs."""
import math
import os

import bpy
import numpy as np

from furylib import render
from . import materials, poses
from .assemble import SLOTS

TILE_PAD = 6


# ============================================================================ test images
_T = 0.27     # stroke thickness as a fraction of the digit width (block numerals)
_SEGS = {  # 7-segment layout: name -> (x0, y0, x1, y1) in a 1 x 2 digit box, y up
    "a": (0.0, 2.0 - _T, 1.0, 2.0), "g": (0.0, 1.0 - _T / 2, 1.0, 1.0 + _T / 2), "d": (0.0, 0.0, 1.0, _T),
    "f": (0.0, 1.0 - _T / 2, _T, 2.0), "b": (1.0 - _T, 1.0 - _T / 2, 1.0, 2.0),
    "e": (0.0, 0.0, _T, 1.0 + _T / 2), "c": (1.0 - _T, 0.0, 1.0, 1.0 + _T / 2),
}
_DIGITS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
           "6": "afgecd", "7": "abc", "8": "abcdefg", "9": "abfgcd"}


def _canvas(size):
    yy, xx = np.mgrid[0:size, 0:size]
    u = (xx + 0.5) / size
    v = 1.0 - (yy + 0.5) / size          # v up, row 0 is the top of the image
    return u, v, np.zeros((size, size, 4), dtype=np.float32)


def number_image(text="88", size=512, color=(1.0, 1.0, 1.0), outline=(0.05, 0.05, 0.06), test=False):
    """Two block digits filling the square. With test=True an italic slant, a frame and a
    corner flag make any mirroring or rotation obvious."""
    u, v, img = _canvas(size)
    shear = 0.16 if test else 0.0
    us = u - (v - 0.5) * shear
    dw, dh, gap = 0.36, 0.76, 0.08
    x0 = 0.5 - dw - gap / 2
    fill = np.zeros(u.shape, dtype=bool)
    for k, ch in enumerate(text[:2]):
        ox = x0 + k * (dw + gap)
        oy = 0.5 - dh / 2
        for seg in _DIGITS[ch]:
            a0, b0, a1, b1 = _SEGS[seg]
            fill |= ((us >= ox + a0 * dw) & (us <= ox + a1 * dw) & (v >= oy + b0 * dh / 2) & (v <= oy + b1 * dh / 2))
    # outline = fill dilated by a few pixels
    r = max(2, size // 90)
    grown = fill.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                grown |= np.roll(np.roll(fill, dy, axis=0), dx, axis=1)
    img[grown] = (*outline, 1.0)
    img[fill] = (*color, 1.0)
    if test:
        frame = (u < 0.02) | (u > 0.98) | (v < 0.02) | (v > 0.98)
        img[frame] = (0.9, 0.1, 0.7, 1.0)
        flag = (u < 0.22) & (v > 0.78) & ((u - 0.0) + (1.0 - v) < 0.22)
        img[flag] = (0.1, 0.8, 0.9, 1.0)
    return img


def logo_test_image(size=512):
    """Arrow pointing toward +U (the facemask) with a flag in the top-left corner."""
    u, v, img = _canvas(size)
    img[:] = (0.96, 0.96, 0.92, 1.0)
    frame = (u < 0.03) | (u > 0.97) | (v < 0.03) | (v > 0.97)
    img[frame] = (0.9, 0.1, 0.7, 1.0)
    shaft = (u > 0.15) & (u < 0.62) & (np.abs(v - 0.45) < 0.07)
    head = (u >= 0.62) & (u < 0.88) & (np.abs(v - 0.45) < (0.88 - u) * 0.85)
    img[shaft | head] = (0.08, 0.08, 0.10, 1.0)
    stem = (u > 0.20) & (u < 0.27) & (v > 0.60) & (v < 0.90)         # an "F": not symmetric any way
    bar1 = (u > 0.20) & (u < 0.42) & (v > 0.83) & (v < 0.90)
    bar2 = (u > 0.20) & (u < 0.36) & (v > 0.70) & (v < 0.76)
    img[stem | bar1 | bar2] = (0.85, 0.15, 0.1, 1.0)
    flag = (u < 0.2) & (v > 0.8) & (u + (1.0 - v) < 0.2)
    img[flag] = (0.1, 0.8, 0.9, 1.0)
    return img


def emblem_image(size=512, color=(1.0, 1.0, 1.0), outline=(0.05, 0.05, 0.06)):
    """An original emblem for the previews: a comet - a star with three speed bars - heading +U."""
    u, v, img = _canvas(size)
    cx, cy = 0.63, 0.5
    dx, dy = u - cx, v - cy
    ang = np.arctan2(dy, dx)
    rad = np.hypot(dx, dy)
    k = (ang % (2 * math.pi / 5)) / (2 * math.pi / 5)
    tri = np.abs(k - 0.5) * 2.0                      # 1 at a point, 0 in a notch
    star_r = 0.135 + (0.31 - 0.135) * tri ** 1.35
    star = rad <= star_r
    bars = np.zeros(u.shape, dtype=bool)
    for yo, x0, half in ((0.0, 0.05, 0.036), (0.17, 0.14, 0.030), (-0.17, 0.14, 0.030)):
        bars |= (u > x0) & (u < 0.50) & (np.abs(v - (cy + yo)) < half)
    fill = star | bars
    r = max(2, size // 70)
    grown = fill.copy()
    for oy in range(-r, r + 1):
        for ox in range(-r, r + 1):
            if ox * ox + oy * oy <= r * r:
                grown |= np.roll(np.roll(fill, oy, axis=0), ox, axis=1)
    img[grown] = (*outline, 1.0)
    img[fill] = (*color, 1.0)
    return img


def to_bpy_image(name, arr, path=None):
    h, w = arr.shape[:2]
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(arr[::-1].ravel())
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    img.pack()
    return img


# ============================================================================== materials
def _bsdf(mat):
    return mat.node_tree.nodes["Principled BSDF"]


def clear_overlays(mat):
    tree = mat.node_tree
    for node in list(tree.nodes):
        if node.name.startswith("ovl_"):
            tree.nodes.remove(node)


def add_number(mat, image):
    """Draw `image` over a slot's base colour through NumberUV, only inside the 0..1 square."""
    clear_overlays(mat)
    tree = mat.node_tree
    bsdf = _bsdf(mat)
    uv = tree.nodes.new("ShaderNodeUVMap"); uv.name = "ovl_uv"; uv.uv_map = "NumberUV"
    tex = tree.nodes.new("ShaderNodeTexImage"); tex.name = "ovl_tex"
    tex.image = image; tex.extension = "CLIP"
    mix = tree.nodes.new("ShaderNodeMix"); mix.name = "ovl_mix"; mix.data_type = "RGBA"
    base = tuple(bsdf.inputs["Base Color"].default_value)
    mix.inputs["A"].default_value = base
    tree.links.new(uv.outputs["UV"], tex.inputs["Vector"])
    tree.links.new(tex.outputs["Alpha"], mix.inputs["Factor"])
    tree.links.new(tex.outputs["Color"], mix.inputs["B"])
    tree.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])


def add_logo(mat, image, cutout=True):
    """Show `image` on the logo patches through the first UV map; alpha cuts the patch away."""
    clear_overlays(mat)
    tree = mat.node_tree
    bsdf = _bsdf(mat)
    uv = tree.nodes.new("ShaderNodeUVMap"); uv.name = "ovl_uv"; uv.uv_map = "UVMap"
    tex = tree.nodes.new("ShaderNodeTexImage"); tex.name = "ovl_tex"
    tex.image = image; tex.extension = "CLIP"
    tree.links.new(uv.outputs["UV"], tex.inputs["Vector"])
    tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if cutout:
        gt = tree.nodes.new("ShaderNodeMath"); gt.name = "ovl_gt"; gt.operation = "GREATER_THAN"
        gt.inputs[1].default_value = 0.5
        tree.links.new(tex.outputs["Alpha"], gt.inputs[0])
        tree.links.new(gt.outputs[0], bsdf.inputs["Alpha"])
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"


def dress(obj, scheme, number="88"):
    """Team colours plus a jersey number and helmet emblem on one athlete, for the beauty renders."""
    materials.recolor(scheme, obj)
    table = materials.SCHEMES[scheme]
    trim = materials.hex_rgb(table["JerseyTrim"][0])
    logo = materials.hex_rgb(table["HelmetLogo"][0])
    num = to_bpy_image(f"preview_number_{obj.name}", number_image(number, color=trim, outline=tuple(c * 0.25 for c in trim)))
    emb = to_bpy_image(f"preview_emblem_{obj.name}", emblem_image(color=logo))
    for slot in obj.material_slots:
        which = materials.slot_of(slot.material)
        if which == "Jersey":
            clear_overlays(slot.material)
            _bsdf(slot.material).inputs["Base Color"].default_value = (*materials.hex_rgb(table["Jersey"][0]), 1.0)
            add_number(slot.material, num)
        elif which == "HelmetLogo":
            add_logo(slot.material, emb)


def backface_material():
    mat = bpy.data.materials.new("check_backface")
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    geo = tree.nodes.new("ShaderNodeNewGeometry")
    front = tree.nodes.new("ShaderNodeBsdfDiffuse")
    front.inputs["Color"].default_value = (0.62, 0.66, 0.70, 1.0)
    back = tree.nodes.new("ShaderNodeEmission")
    back.inputs["Color"].default_value = (1.0, 0.0, 0.0, 1.0)
    back.inputs["Strength"].default_value = 3.0
    mix = tree.nodes.new("ShaderNodeMixShader")
    tree.links.new(geo.outputs["Backfacing"], mix.inputs["Fac"])
    tree.links.new(front.outputs["BSDF"], mix.inputs[1])
    tree.links.new(back.outputs["Emission"], mix.inputs[2])
    tree.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    mat.use_backface_culling = False
    return mat


def swap_materials(obj, fn):
    """Temporarily replace every slot's material with fn(slot_name). Returns the originals."""
    old = [slot.material for slot in obj.material_slots]
    for slot in obj.material_slots:
        slot.material = fn(slot.material.name)
    return old


def restore_materials(obj, old):
    for slot, mat in zip(obj.material_slots, old):
        slot.material = mat


# ================================================================================= scene
def studio(scene, ground=True):
    for obj in list(bpy.data.objects):
        if obj.name.startswith(("Key", "Fill", "Rim", "PreviewGround", "PreviewCam", "Kick")):
            bpy.data.objects.remove(obj, do_unlink=True)
    render.studio(scene, ground=ground, world_strength=0.55)
    # a low kicker from the front so the face inside the helmet and the pants' pads read
    data = bpy.data.lights.new("Kick", "AREA")
    data.energy = 90
    data.size = 3.0
    kick = bpy.data.objects.new("Kick", data)
    scene.collection.objects.link(kick)
    kick.location = (0.5, -4.0, 0.9)
    from mathutils import Vector
    kick.rotation_euler = (Vector((0, 0, 1.2)) - Vector(kick.location)).to_track_quat("-Z", "Y").to_euler()
    scene.view_settings.view_transform = "Standard"      # team colours should read true
    scene.view_settings.exposure = -0.45
    return render.camera(scene)


def posed_bounds(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    co = np.empty(len(ev.data.vertices) * 3, dtype=np.float32)
    ev.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return co.min(axis=0), co.max(axis=0)


def shot(cam, path, target, distance, az, el, size=(700, 700), lens=70.0, samples=48):
    render.orbit(cam, target=tuple(target), distance=distance, azimuth_deg=az, elevation_deg=el, lens=lens)
    return render.still(path, size[0], size[1], samples=samples)


def sheet(paths, out, columns):
    render.contact_sheet(paths, out, columns=columns, pad=TILE_PAD)
    for p in paths:
        if os.path.exists(p):
            os.remove(p)
    return out


def fit_distance(height, lens=70.0, sensor=36.0, margin=1.12):
    return (height * margin) * lens / sensor


# ================================================================================ renders
def turnaround(obj, arm, cam, out_dir, tmp_dir, build, samples=64):
    poses.reset_pose(arm)
    bpy.context.view_layer.update()
    lo, hi = posed_bounds(obj)
    target = (0.0, 0.0, 0.5 * (lo[2] + hi[2]))
    dist = fit_distance(hi[2] - lo[2], margin=1.10)
    tiles = []
    for name, az in (("front", 0), ("threeq", 35), ("side", 90), ("back", 180)):
        tiles.append(shot(cam, os.path.join(tmp_dir, f"t_{build}_{name}.png"), target, dist, az, 5, (691, 691), samples=samples))
    return sheet(tiles, os.path.join(out_dir, f"turnaround_{build}.png"), 2)


def pose_sheets(obj, arm, cam, out_dir, tmp_dir, build, samples=56):
    names = ["sprint", "three_point", "arms_up", "throw", "deep_knee", "lying"]
    outs = []
    for tag, az, el in (("a", 38, 10), ("b", -118, 12)):
        tiles = []
        for name in names:
            poses.apply_pose(arm, poses.POSES[name])
            bpy.context.view_layer.update()
            lo, hi = posed_bounds(obj)
            c = 0.5 * (lo + hi)
            size = float(np.linalg.norm(hi - lo))
            e = 38 if name == "lying" else el
            tiles.append(shot(cam, os.path.join(tmp_dir, f"p_{build}_{name}_{tag}.png"), c, size * 1.55, az, e, (458, 458), samples=samples))
        outs.append(sheet(tiles, os.path.join(out_dir, f"poses_{build}_{tag}.png"), 3))
    poses.reset_pose(arm)
    bpy.context.view_layer.update()
    return outs


def closeups(obj, arm, cam, out_dir, tmp_dir, build, samples=64):
    poses.reset_pose(arm)
    bpy.context.view_layer.update()
    outs = []
    tiles = []
    for name, az, el in (("front", 0, 2), ("threeq", 40, 8), ("side", 90, 4), ("back", 205, 12)):
        tiles.append(shot(cam, os.path.join(tmp_dir, f"c_{build}_helmet_{name}.png"), (0, 0.0, 1.725), 1.02, az, el, (342, 380), samples=samples))
    outs.append(sheet(tiles, os.path.join(out_dir, f"closeup_helmet_{build}.png"), 4))
    # face with the visor hidden
    visor = next(s.material for s in obj.material_slots if materials.slot_of(s.material) == "Visor")
    alpha = visor.node_tree.nodes["Principled BSDF"].inputs["Alpha"]
    keep = alpha.default_value
    alpha.default_value = 0.0
    tiles = []
    for name, az, el in (("front", 0, 0), ("threeq", 32, 4), ("low", 18, -22)):
        tiles.append(shot(cam, os.path.join(tmp_dir, f"c_{build}_face_{name}.png"), (0, -0.03, 1.70), 0.74, az, el, (458, 458), samples=samples))
    alpha.default_value = keep
    outs.append(sheet(tiles, os.path.join(out_dir, f"closeup_face_{build}.png"), 3))
    # hands
    tiles = []
    hand = np.array([0.665, -0.045, 1.01])
    for name, az, el in (("back", 100, 12), ("thumb", 10, 10), ("palm", -78, 6)):
        tiles.append(shot(cam, os.path.join(tmp_dir, f"c_{build}_hand_{name}.png"), hand, 0.80, az, el, (458, 458), samples=samples))
    poses.apply_pose(arm, poses.POSES["fist"])
    bpy.context.view_layer.update()
    knuckle = arm.pose.bones["fingers_l"].head
    tiles.append(shot(cam, os.path.join(tmp_dir, f"c_{build}_closed_hand.png"),
                      knuckle, 0.76, 75, 16, (458, 458), samples=samples))
    outs.append(sheet(tiles, os.path.join(out_dir, f"closeup_hands_{build}.png"), 4))
    poses.reset_pose(arm)
    bpy.context.view_layer.update()
    # cleats, including the studs from below
    ground = bpy.data.objects.get("PreviewGround")
    tiles = []
    foot = np.array([0.0, -0.06, 0.07])
    for name, az, el in (("front", 28, 14), ("side", 90, 6)):
        tiles.append(shot(cam, os.path.join(tmp_dir, f"c_{build}_cleat_{name}.png"), foot, 1.25, az, el, (458, 458), samples=samples))
    if ground is not None:
        ground.hide_render = True
    tiles.append(shot(cam, os.path.join(tmp_dir, f"c_{build}_cleat_under.png"), foot, 1.25, 35, -48, (458, 458), samples=samples))
    if ground is not None:
        ground.hide_render = False
    outs.append(sheet(tiles, os.path.join(out_dir, f"closeup_cleats_{build}.png"), 3))
    return outs


def number_check(obj, arm, cam, out_dir, tmp_dir, build, samples=32):
    """Every slot gets one grey material that shows the "88" test card wherever NumberUV is in
    0..1, so a stray face or a mirrored panel would be obvious."""
    poses.reset_pose(arm)
    bpy.context.view_layer.update()
    card = to_bpy_image("check_number", number_image("88", color=(0.02, 0.02, 0.02), outline=(1.0, 0.85, 0.1), test=True),
                        os.path.join(tmp_dir, "test_number_88.png"))
    grey = materials.principled("check_grey", (0.30, 0.31, 0.33), 0.8)
    add_number(grey, card)
    old = swap_materials(obj, lambda name: grey)
    tiles = []
    views = (("front", (0, 0, 1.37), 1.55, 0, 0), ("back", (0, 0, 1.37), 1.55, 180, 0),
             ("left", (0.1, 0, 1.45), 1.45, 90, 38), ("right", (-0.1, 0, 1.45), 1.45, -90, 38))
    for name, target, dist, az, el in views:
        tiles.append(shot(cam, os.path.join(tmp_dir, f"n_{build}_{name}.png"), target, dist, az, el, (342, 342), samples=samples))
    restore_materials(obj, old)
    return sheet(tiles, os.path.join(out_dir, f"check_numberuv_{build}.png"), 4)


def logo_check(obj, arm, cam, out_dir, tmp_dir, build, samples=32):
    poses.reset_pose(arm)
    bpy.context.view_layer.update()
    card = to_bpy_image("check_logo", logo_test_image(), os.path.join(tmp_dir, "test_logo.png"))
    mat = materials.principled("check_logo_mat", (1, 1, 1), 0.5)
    add_logo(mat, card, cutout=False)
    slot_mats = {slot.material.name: slot.material for slot in obj.material_slots}
    old = swap_materials(obj, lambda name: mat if name.split(".")[0] == "HelmetLogo" else slot_mats[name])
    tiles = []
    for name, az in (("left", 90), ("left_q", 55), ("right_q", -55), ("right", -90)):
        tiles.append(shot(cam, os.path.join(tmp_dir, f"l_{build}_{name}.png"), (0, 0.01, 1.74), 0.95, az, 6, (342, 342), samples=samples))
    restore_materials(obj, old)
    return sheet(tiles, os.path.join(out_dir, f"check_helmetlogo_{build}.png"), 4)


def backface_check(obj, arm, cam, out_dir, tmp_dir, build, samples=32):
    """Front faces render grey, back faces glow red. Any red means an inverted or exposed
    inside face. Rendered in the rest pose and in a deep crouch."""
    mat = backface_material()
    old = swap_materials(obj, lambda name: mat)
    ground = bpy.data.objects.get("PreviewGround")
    if ground is not None:
        ground.hide_render = True
    tiles = []
    for pose_name in (None, "three_point"):
        if pose_name:
            poses.apply_pose(arm, poses.POSES[pose_name])
        else:
            poses.reset_pose(arm)
        bpy.context.view_layer.update()
        lo, hi = posed_bounds(obj)
        c = 0.5 * (lo + hi)
        size = float(np.linalg.norm(hi - lo))
        for name, az, el in (("f", 30, 12), ("b", 205, 20), ("u", 140, -40)):
            tiles.append(shot(cam, os.path.join(tmp_dir, f"b_{build}_{pose_name}_{name}.png"), c, size * 1.5, az, el, (458, 458), samples=samples))
    if ground is not None:
        ground.hide_render = False
    restore_materials(obj, old)
    poses.reset_pose(arm)
    bpy.context.view_layer.update()
    return sheet(tiles, os.path.join(out_dir, f"check_backfaces_{build}.png"), 3)


def lineup(blend_paths, schemes, numbers, out_path, tmp_dir, samples=64):
    """The three builds side by side in three team schemes, standing relaxed."""
    scene = render.reset_scene()
    spacing = 1.02
    athletes = []
    for i, (path, scheme, number) in enumerate(zip(blend_paths, schemes, numbers)):
        with bpy.data.libraries.load(path) as (src, dst):
            dst.objects = list(src.objects)
        arm = mesh = None
        for o in dst.objects:
            scene.collection.objects.link(o)
            if o.type == "ARMATURE":
                arm = o
            elif o.type == "MESH":
                mesh = o
        arm.location.x = (i - 1) * spacing
        dress(mesh, scheme, number)
        poses.apply_pose(arm, poses.POSES["arms_down"])
        athletes.append((arm, mesh))
    cam = studio(scene)
    bpy.context.view_layer.update()
    path = shot(cam, out_path, (0.0, 0.0, 0.97), 9.3, 14, 5, (1400, 900), lens=85.0, samples=samples)
    return path
