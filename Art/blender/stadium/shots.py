"""Preview renders: the stadium at night (empty and with a crowd), prop close-ups, and a
back-face audit. Everything created here lives in PV_* collections and is never exported.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from . import crowd as crowdlib
from . import preview as pv
from . import spec as S

W, H = 1400, 788


# ---- collections ---------------------------------------------------------------------------------
def coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def move_to(obj, collection):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    collection.objects.link(obj)


def show_only(scene, names):
    """Include exactly the named top-level collections in the view layer."""
    for lc in scene.view_layers[0].layer_collection.children:
        lc.exclude = lc.name not in names


def bbox(obj):
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


# ---- compositor glow -------------------------------------------------------------------------------
def set_glow(scene, on, strength=0.55, size=0.45, threshold=1.6):
    """Bloom on lamps and screens for the night shots (off for studio and audit renders)."""
    try:
        if not on:
            scene.compositing_node_group = None
            return
        ng = bpy.data.node_groups.get("PV_Glow")
        if ng is None:
            ng = bpy.data.node_groups.new("PV_Glow", "CompositorNodeTree")
            ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            rl = ng.nodes.new("CompositorNodeRLayers")
            gl = ng.nodes.new("CompositorNodeGlare")
            gl.name = "Glare"
            out = ng.nodes.new("NodeGroupOutput")
            ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
            ng.links.new(gl.outputs["Image"], out.inputs["Image"])
        gl = ng.nodes["Glare"]
        try:
            gl.inputs["Type"].default_value = "Bloom"
        except Exception:
            pass
        for key, val in (("Threshold", threshold), ("Strength", strength), ("Size", size)):
            if key in gl.inputs:
                gl.inputs[key].default_value = val
        scene.compositing_node_group = ng
    except Exception as exc:
        print("glow unavailable:", exc)


# ---- the stage: turf, floodlights, props placed on the field -----------------------------------------
def suggested_dressing():
    """Where the props go on the field (Blender metres / radians about +Z). Also written to the
    metadata as a suggestion for the engine."""
    gx, fx, fy = S.GOAL_X, S.FIELD_HX, S.FIELD_HY
    out = dict(
        SM_Goalpost=[dict(pos=[fx, 0, 0], yaw=0.0), dict(pos=[-fx, 0, 0], yaw=math.pi)],
        SM_Pylon=[dict(pos=[sx * x, sy * fy, 0], yaw=0.0) for x in (gx, fx) for sx in (-1, 1) for sy in (-1, 1)],
        SM_Bench=[dict(pos=[x, sy * 30.2, 0], yaw=0.0 if sy > 0 else math.pi)
                  for sy in (1, -1) for x in (-13.5, -4.5, 4.5, 13.5)],
        SM_Cooler=[dict(pos=[sx * 17.2, sy * 30.4, 0], yaw=0.0 if sy > 0 else math.pi)
                   for sy in (1, -1) for sx in (-1, 1)],
        SM_ChainPole=[dict(pos=[-4.572, fy + 1.9, 0], yaw=0.0), dict(pos=[4.572, fy + 1.9, 0], yaw=0.0)],
        SM_DownBox=[dict(pos=[-4.572, fy + 2.5, 0], yaw=0.0)],
        SM_Camera=[dict(pos=[-34.0, 31.0, 0], yaw=0.0), dict(pos=[34.0, 31.0, 0], yaw=0.0),
                   dict(pos=[0.0, -31.0, 0], yaw=math.pi), dict(pos=[60.5, -8.0, 0], yaw=-0.5 * math.pi)],
        SM_KickTee=[dict(pos=[-13.716, 0, 0], yaw=0.0)],
    )
    return out


def build_stage(scene, lights, prop_objs):
    stage = coll("PV_Stage")
    ground = pv.field_ground(collection=stage)
    floods = pv.flood_lights(lights, collection=stage)
    # faint moonlight so roofs and the outside of the building read in the aerial shots
    moon = bpy.data.lights.new("PV_Moon", "SUN")
    moon.energy = 0.42
    moon.color = (0.55, 0.66, 1.0)
    moon.angle = math.radians(3.0)
    mo = bpy.data.objects.new("PV_Moon", moon)
    mo.rotation_euler = (math.radians(38), math.radians(-18), math.radians(25))
    stage.objects.link(mo)
    for name, places in suggested_dressing().items():
        src = prop_objs.get(name)
        if src is None:
            continue
        for p in places:
            o = bpy.data.objects.new("PV_" + name, src.data)
            o.location = p["pos"]
            o.rotation_euler = (0, 0, p["yaw"])
            stage.objects.link(o)
    ball = prop_objs.get("SM_Football")
    if ball is not None:                       # teed up for the kickoff
        o = bpy.data.objects.new("PV_Ball", ball.data)
        o.location = (-13.716 + 0.012, 0, 0.165)
        o.rotation_euler = (0, math.radians(-80), 0)
        stage.objects.link(o)
    return stage


STADIUM_VIEWS = {
    # name: (eye, target, horizontal FOV)
    "broadcast_center": (S.CAMERA, (0.0, S.FIELD_HY, 0.0), 84.0),
    "broadcast_left": ((-22.0, -52.0, 26.0), (-50.0, 6.0, 0.0), 84.0),
    "broadcast_right": ((22.0, -52.0, 26.0), (50.0, 6.0, 0.0), 84.0),
    "broadcast_tight": (S.CAMERA, (0.0, 4.0, 0.0), 62.0),
    "overview": ((95.0, -150.0, 185.0), (0.0, 4.0, 6.0), 46.0),
    "overview_back": ((-150.0, 165.0, 105.0), (0.0, 5.0, 14.0), 44.0),
    "exterior": ((-190.0, 150.0, 34.0), (-20.0, 50.0, 22.0), 50.0),
    "plan": ((0.0, -0.5, 300.0), (0.0, 0.0, 0.0), 54.0),
    "field_north": ((0.0, -9.0, 1.8), (0.0, 40.0, 15.5), 84.0),
    "field_south": ((0.0, 14.0, 1.8), (0.0, -50.0, 11.0), 84.0),
    "endzone_west": ((14.0, -3.0, 2.2), (-80.0, 6.0, 15.0), 76.0),
    "endzone_east": ((-14.0, -3.0, 2.2), (80.0, 6.0, 15.0), 76.0),
    "corner_ne": ((28.0, -12.0, 3.0), (80.0, 46.0, 17.0), 72.0),
    "tunnel_out": None,          # filled in by set_tunnel_views()
    "tunnel_mouth": None,
    "upper_deck": ((44.0, 30.0, 23.0), (62.0, 72.0, 27.0), 70.0),
    "sideline_props": ((-9.0, 18.5, 2.0), (6.0, 34.0, 1.6), 62.0),
    "goal_east": ((30.0, -13.0, 2.6), (58.0, 2.0, 5.5), 60.0),
    "crowd_closeup": ((14.0, 30.5, 4.2), (20.5, 41.0, 4.4), 62.0),
    "crowd_rows": ((2.2, 32.4, 3.3), (13.5, 38.2, 3.5), 52.0),
    "crowd_upper": ((54.0, 36.0, 26.5), (63.0, 62.0, 25.0), 64.0),
}


def set_tunnel_views(tunnel):
    """Aim the two tunnel shots from the metadata (mouth point and the direction players run)."""
    m = Vector(tunnel["mouth"])
    d = Vector(tunnel["dir"]).normalized()
    side = Vector((-d.y, d.x, 0.0))
    up = Vector((0.0, 0.0, 1.0))
    STADIUM_VIEWS["tunnel_out"] = (tuple(m - d * 24.0 + up * 1.75), tuple(m + d * 34.0 + up * 1.9), 70.0)
    STADIUM_VIEWS["tunnel_mouth"] = (tuple(m + d * 20.8 + side * 5.0 + up * 2.0), tuple(m - d * 12.2 + up * 3.6), 62.0)


def render_stadium(scene, names, out_dir, suffix="", samples=96, exposure=0.15, with_crowd=False):
    show_only(scene, {"Stadium", "PV_Stage"} | ({"PV_Crowd"} if with_crowd else set()))
    pv.night_world(scene)
    pv.setup_render(scene, "CYCLES", samples=samples, exposure=exposure)
    set_glow(scene, True)
    cam = pv.camera(scene)
    done = []
    for name in names:
        eye, tgt, fov = STADIUM_VIEWS[name]
        pv.aim(cam, eye, tgt, fov_deg=fov)
        path = os.path.join(out_dir, name + suffix + ".png")
        pv.render(scene, path, W, H)
        done.append(path)
    return done


# ---- props in a studio ---------------------------------------------------------------------------------
def studio_world(scene):
    world = bpy.data.worlds.get("PV_Studio") or bpy.data.worlds.new("PV_Studio")
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.20, 0.21, 0.23, 1.0)
    bg.inputs["Strength"].default_value = 0.55
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = world


def _studio(scene, lo, hi):
    """Floor and three area lights sized to the subject's bounding box."""
    studio = coll("PV_Studio")
    for o in list(studio.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    centre = (lo + hi) * 0.5
    size = max((hi - lo).length, 1e-3)
    k = size / 2.0
    mesh = bpy.data.meshes.new("PV_Floor")
    e = 60.0 * k
    mesh.from_pydata([(-e, -e, 0), (e, -e, 0), (e, e, 0), (-e, e, 0)], [], [(0, 1, 2, 3)])
    mesh.materials.append(pv.principled("PV_Floor", (0.16, 0.17, 0.19), 0.75))
    floor = bpy.data.objects.new("PV_Floor", mesh)
    floor.location = (centre.x, centre.y, lo.z - 0.0005 * k)
    studio.objects.link(floor)
    for name, off, power, sz, colr in (("Key", (2.6, -3.4, 3.4), 520, 2.4, (1.0, 0.96, 0.9)),
                                       ("Fill", (-3.6, -2.2, 1.8), 170, 3.6, (0.85, 0.92, 1.0)),
                                       ("Rim", (-1.4, 3.6, 3.0), 420, 2.0, (0.9, 0.95, 1.0))):
        data = bpy.data.lights.new("PV_" + name, "AREA")
        data.energy = power * k * k
        data.size = sz * k
        data.color = colr
        o = bpy.data.objects.new("PV_" + name, data)
        o.location = centre + Vector(off) * k
        o.rotation_euler = (centre - o.location).to_track_quat("-Z", "Y").to_euler()
        studio.objects.link(o)
    return centre, size


def render_prop(scene, objs, path, az=32.0, el=14.0, fov=30.0, fill=1.25, res=(1000, 750), samples=96,
                target_shift=(0.0, 0.0, 0.0), exposure=-1.25):
    """Studio shot of one or more objects (which must be in the PV_Subject collection)."""
    los, his = zip(*(bbox(o) for o in objs))
    lo = Vector((min(v.x for v in los), min(v.y for v in los), min(v.z for v in los)))
    hi = Vector((max(v.x for v in his), max(v.y for v in his), max(v.z for v in his)))
    centre, size = _studio(scene, lo, hi)
    show_only(scene, {"PV_Subject", "PV_Studio"})
    studio_world(scene)
    pv.setup_render(scene, "CYCLES", samples=samples, exposure=exposure, view="Standard")
    set_glow(scene, False)
    cam = pv.camera(scene)
    tgt = centre + Vector(target_shift) * size
    dist = fill * (size / 2) / math.tan(math.radians(fov) / 2)
    a, e = math.radians(az), math.radians(el)
    eye = tgt + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    pv.aim(cam, eye, tgt, fov_deg=fov)
    cam.data.clip_start = max(0.001, dist * 0.01)
    pv.render(scene, path, res[0], res[1])
    cam.data.clip_start = 0.05
    return path


def subject(objs):
    """Put linked copies of the given objects in PV_Subject (emptying it first)."""
    sub = coll("PV_Subject")
    for o in list(sub.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    out = []
    for item in objs:
        src, loc, rot = (item + ((0, 0, 0), (0, 0, 0)))[:3] if isinstance(item, tuple) else (item, (0, 0, 0), (0, 0, 0))
        o = bpy.data.objects.new("PV_S_" + src.name, src.data)
        o.location = loc
        o.rotation_euler = rot
        o.color = src.color
        sub.objects.link(o)
        out.append(o)
    bpy.context.view_layer.update()
    return out


# ---- back-face audit -----------------------------------------------------------------------------------
def backface_material():
    mat, nt, out = pv._fresh("PV_Backface")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    front = nt.nodes.new("ShaderNodeEmission")
    front.inputs["Color"].default_value = (0.0, 1.0, 0.0, 1.0)
    back = nt.nodes.new("ShaderNodeEmission")
    back.inputs["Color"].default_value = (1.0, 0.0, 0.0, 1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geo.outputs["Backfacing"], mix.inputs["Fac"])
    nt.links.new(front.outputs["Emission"], mix.inputs[1])
    nt.links.new(back.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


AUDIT_VIEWS = ["broadcast_center", "broadcast_left", "broadcast_right", "field_north", "field_south",
               "endzone_west", "endzone_east", "corner_ne", "tunnel_out", "tunnel_mouth", "upper_deck",
               "overview", "overview_back", "plan"]
AUDIT_EXTRA = {
    "seat_upper_n": ((-35.0, 66.0, 30.5), (20.0, -10.0, 0.0), 95.0),
    "seat_upper_e": ((98.0, 10.0, 30.0), (-20.0, -5.0, 0.0), 95.0),
    "seat_south": ((20.0, -72.0, 24.5), (-10.0, 20.0, 5.0), 95.0),
    "seat_lower_s": ((-30.0, -50.0, 11.5), (30.0, 30.0, 10.0), 100.0),
    "walkway_n": ((30.0, 56.5, 14.2), (-30.0, 58.5, 13.6), 95.0),
    "deck_s": ((-50.0, -59.5, 17.2), (40.0, -60.5, 16.0), 95.0),
    "sw_corner": ((-40.0, -20.0, 2.0), (-95.0, -70.0, 22.0), 80.0),
    "se_corner": ((40.0, -20.0, 2.0), (95.0, -70.0, 22.0), 80.0),
    "low_sideline": ((-45.0, 30.0, 0.6), (40.0, 33.0, 6.0), 95.0),
    "under_roof": ((60.0, 68.0, 36.0), (-40.0, 40.0, 34.0), 95.0),
}


def backface_audit(scene, out_dir):
    """Render with front faces green and back faces red; report the red fraction per view. Any
    red that a game camera could see would be a hole once the engine culls back faces."""
    show_only(scene, {"Stadium"})
    vl = scene.view_layers[0]
    vl.material_override = backface_material()
    set_glow(scene, False)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 4
    scene.cycles.use_denoising = False
    saved = (scene.view_settings.view_transform, scene.view_settings.look, scene.view_settings.exposure)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    world = bpy.data.worlds.get("PV_Black") or bpy.data.worlds.new("PV_Black")
    nt = world.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputWorld")
    b = nt.nodes.new("ShaderNodeBackground")
    b.inputs["Color"].default_value = (0, 0, 0, 1)
    nt.links.new(b.outputs["Background"], o.inputs["Surface"])
    scene.world = world
    cam = pv.camera(scene)
    views = {k: STADIUM_VIEWS[k] for k in AUDIT_VIEWS}
    views.update(AUDIT_EXTRA)
    report = {}
    tiles = []
    tw, th = 466, 262
    for name, (eye, tgt, fov) in views.items():
        pv.aim(cam, eye, tgt, fov_deg=fov)
        path = os.path.join(out_dir, "audit_" + name + ".png")
        pv.render(scene, path, tw * 2, th * 2)
        img = bpy.data.images.load(path, check_existing=False)
        px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        px = px.reshape(th * 2, tw * 2, 4)
        red = (px[..., 0] > 0.35) & (px[..., 1] < 0.6)
        report[name] = float(red.mean())
        # half-size tile with every suspicious pixel blown up so it cannot be missed
        small = px.reshape(th, 2, tw, 2, 4).mean(axis=(1, 3))
        mask = red.reshape(th, 2, tw, 2).any(axis=(1, 3))
        grown = mask.copy()
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                grown |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
        small[..., :3] *= 0.45
        small[grown, :3] = (1.0, 0.0, 0.0)
        small[..., 3] = 1.0
        tile = bpy.data.images.new("PV_AuditTile", tw, th, alpha=False)
        tile.pixels.foreach_set(small.astype(np.float32).ravel())
        tpath = os.path.join(out_dir, "tile_" + name + ".png")
        tile.filepath_raw = tpath
        tile.file_format = "PNG"
        tile.save()
        bpy.data.images.remove(tile)
        tiles.append(tpath)
    from furylib import render as frender
    for i in range(0, len(tiles), 12):
        frender.contact_sheet(tiles[i:i + 12], os.path.join(out_dir, "sheet_%d.png" % (i // 12)), columns=3, pad=2)
    vl.material_override = None
    scene.view_settings.view_transform, scene.view_settings.look, scene.view_settings.exposure = saved
    return report
