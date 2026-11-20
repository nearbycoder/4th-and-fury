"""Blender -> glTF exporter for the 4th & Fury web port.

    blender -b --factory-startup --python web/tools/export_gltf.py -- [--only characters,anims,stadium,props]
                                                                      [--out web/public/assets]

Sources (read-only):
    Art/blend/player_{lean,mid,big}.blend      skinned athletes (metres, Z up, facing -Y)
    Art/export/anims/A_<Clip>.fbx + anims.json  the clips Unreal plays (centimetres, baked every frame)
    Art/export/stadium/SM_<Name>.fbx            bowl and props (centimetres)

Writes:
    characters/{lean,mid,big}.glb   skinned mesh, one material per slot, UVMap -> TEXCOORD_0, NumberUV -> TEXCOORD_1
    characters/anims.glb            the shared armature (no mesh) with every clip as a named animation
    characters/anims.json           anims.json plus derived timing / root-motion facts
    stadium/stadium.glb             the bowl, materials coloured as FuryStadium.cpp dresses them, ad texture embedded
    stadium/<prop>.glb              football, goalpost, pylon, kicktee, bench, cooler, chainpole, downbox, camera,
                                    crowdA, crowdB, crowdC

Every glTF is written by Blender's exporter with its default +Y-up conversion:
    glTF (x, y, z) = Blender (x, z, -y) = Unreal (X, Z, Y) / 100

Animation clips are not imported straight from FBX onto the export rig. The FBX importer rebuilds bone
rest poses from the first animated frame (an armature-only FBX has no bind pose), so each clip is
retargeted in world space onto the exact armature stored in player_mid.blend, which is the one the
three character GLBs are skinned to. The script checks the result against the FBX joint positions.
"""
import argparse
import json
import math
import os
import sys
import time

import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ART = os.path.join(REPO, "Art")
BLEND = os.path.join(ART, "blend")
ANIMS = os.path.join(ART, "export", "anims")
STADIUM = os.path.join(ART, "export", "stadium")
TEXTURES = os.path.join(ART, "export", "textures")
SCRATCH = os.environ.get("FURY_SCRATCH", "/private/tmp/fury_web")

FBX_IMPORT = dict(
    axis_forward="-Z", axis_up="Y", primary_bone_axis="Y", secondary_bone_axis="X",
    automatic_bone_orientation=False, ignore_leaf_bones=False, use_custom_props=False,
    use_image_search=False, anim_offset=0.0, colors_type="LINEAR",
)

GLTF_COMMON = dict(
    export_format="GLB", export_yup=True, export_apply=False, export_texcoords=True, export_normals=True,
    export_tangents=False, export_cameras=False, export_lights=False, export_extras=False,
    export_attributes=False, use_selection=False, export_morph=False, export_def_bones=False,
    export_leaf_bone=False, export_optimize_disable_viewport=True, export_loglevel=-1,
)

# --------------------------------------------------------------------------------------------- materials
# Character slots: (colour, roughness, metallic) as FuryAthlete::SetLook sets them. Colours are LINEAR.
# Slots the game tints per kit get a neutral grey placeholder here; the renderer sets them per team.
GREY = (0.5, 0.5, 0.5)
ATHLETE = {
    "Helmet": (GREY, 0.16, 0.0), "HelmetStripe": (GREY, 0.2, 0.0), "HelmetLogo": (GREY, 0.16, 0.0),
    "Facemask": ((0.7, 0.7, 0.72), 0.3, 0.85), "Visor": ((0.01, 0.012, 0.016), 0.06, 0.9),
    "Strap": ((0.85, 0.85, 0.85), 0.6, 0.0), "Skin": ((0.45, 0.28, 0.18), 0.55, 0.0),
    "Eyes": ((0.015, 0.012, 0.01), 0.4, 0.0), "Jersey": (GREY, 0.72, 0.0), "JerseyTrim": (GREY, 0.7, 0.0),
    "Pants": (GREY, 0.62, 0.0), "PantsStripe": (GREY, 0.62, 0.0), "Belt": ((0.03, 0.03, 0.03), 0.5, 0.0),
    "Socks": (GREY, 0.8, 0.0), "Shoes": ((0.015, 0.015, 0.018), 0.35, 0.0), "ShoeSole": ((0.75, 0.75, 0.75), 0.6, 0.0),
    "Gloves": (GREY, 0.55, 0.0), "Bands": (GREY, 0.75, 0.0),
}

ORANGE = (1.0, 0.32, 0.02)
# Stadium / prop slots as AFuryStadium::ApplySlotMaterials dresses them (linear colour, roughness, metallic,
# extra). SeatA / SeatB / WallPad / GoalPad are re-tinted per home team by AFuryStadium::Dress.
STADIUM_SLOTS = {
    "Concrete": ((0.36, 0.36, 0.37), 0.86, 0.0, {}),
    "ConcreteDark": ((0.045, 0.045, 0.05), 0.9, 0.0, {}),
    "SeatA": ((0.2, 0.02, 0.03), 0.6, 0.0, {}),
    "SeatB": ((0.03, 0.04, 0.08), 0.6, 0.0, {}),
    "Steel": ((0.3, 0.32, 0.35), 0.42, 0.9, {}),
    "Glass": ((0.012, 0.02, 0.035), 0.08, 0.7, {}),
    "WallPad": ((0.02, 0.05, 0.14), 0.55, 0.0, {}),
    "LampHousing": ((0.04, 0.04, 0.045), 0.5, 0.7, {}),
    "Apron": ((0.05, 0.075, 0.055), 0.92, 0.0, {}),
    "Roof": ((0.07, 0.075, 0.085), 0.5, 0.6, {}),
    "GoalYellow": ((0.95, 0.72, 0.03), 0.35, 0.2, {}),
    "GoalPad": ((0.3, 0.02, 0.02), 0.6, 0.0, {}),
    "Leather": ((0.25, 0.095, 0.04), 0.5, 0.0, {}),
    "Laces": ((0.9, 0.9, 0.88), 0.6, 0.0, {}),
    "BallStripe": ((0.9, 0.9, 0.88), 0.6, 0.0, {}),
    "Tee": (ORANGE, 0.45, 0.0, {}),
    "CoolerBody": (ORANGE, 0.45, 0.0, {}),
    "MarkerOrange": (ORANGE, 0.45, 0.0, {}),
    "Pylon": (ORANGE, 0.5, 0.0, {"emit": ORANGE, "strength": 0.6}),
    "BenchSeat": ((0.07, 0.075, 0.09), 0.6, 0.0, {}),
    "DownFace": ((0.0, 0.0, 0.0), 0.5, 0.0, {"emit": (0.02, 0.02, 0.02), "strength": 1.0, "two_sided": True}),
    "CameraBody": ((0.03, 0.03, 0.035), 0.4, 0.3, {}),
    "AdBoard": ((1.0, 1.0, 1.0), 0.55, 0.0, {"image": "ads", "emit_image": 0.6, "uv_scale": (0.125, 1.0)}),
    # M_Glow (unlit, two-sided): white * 45 for the lamp faces.
    "Lamp": ((0.0, 0.0, 0.0), 1.0, 0.0, {"emit": (1.0, 0.97, 0.9), "strength": 45.0, "two_sided": True}),
    # Video boards: the HUD's 1280x720 render target at brightness 2.2; this is its clear colour.
    "Screen": ((0.0, 0.0, 0.0), 1.0, 0.0, {"emit": (0.01, 0.012, 0.02), "strength": 1.0, "two_sided": True}),
    "ScreenSmall": ((0.0, 0.0, 0.0), 1.0, 0.0, {"emit": (0.01, 0.012, 0.02), "strength": 1.0, "two_sided": True}),
    # Crowd figures: the vertex colour is a mask (R shirt, G skin, B hair, black = trousers); see README.
    "Crowd": ((1.0, 1.0, 1.0), 0.85, 0.0, {}),
}

PROPS = {
    "SM_Football": "football", "SM_Goalpost": "goalpost", "SM_Pylon": "pylon", "SM_KickTee": "kicktee",
    "SM_Bench": "bench", "SM_Cooler": "cooler", "SM_ChainPole": "chainpole", "SM_DownBox": "downbox",
    "SM_Camera": "camera", "SM_CrowdA": "crowdA", "SM_CrowdB": "crowdB", "SM_CrowdC": "crowdC",
}


def log(*args):
    print("[export_gltf]", *args, flush=True)


def make_material(name, color, rough, metal, emit=None, strength=1.0, image=None, emit_image=0.0, two_sided=False,
                  uv_scale=None):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit is not None:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.extension = "REPEAT"
        if uv_scale is not None:
            mapping = nt.nodes.new("ShaderNodeMapping")
            mapping.vector_type = "POINT"
            mapping.inputs["Scale"].default_value = (uv_scale[0], uv_scale[1], 1.0)
            coords = nt.nodes.new("ShaderNodeUVMap")
            nt.links.new(coords.outputs["UV"], mapping.inputs["Vector"])
            nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if emit_image > 0.0:
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = emit_image
    mat.use_backface_culling = not two_sided
    mat.diffuse_color = (*color, 1.0)
    return mat


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def gltf_export(path, **overrides):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    opts = dict(GLTF_COMMON)
    opts.update(overrides)
    bpy.ops.export_scene.gltf(filepath=path, **opts)
    log("wrote", os.path.relpath(path, REPO), "%.1f KB" % (os.path.getsize(path) / 1024))


# --------------------------------------------------------------------------------------------- characters
def export_characters(out):
    meta = json.load(open(os.path.join(ART, "export", "characters", "player_meta.json")))
    rests = {}
    for build in ("lean", "mid", "big"):
        bpy.ops.wm.open_mainfile(filepath=os.path.join(BLEND, "player_%s.blend" % build))
        arm = bpy.data.objects["Armature"]
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        for obj in list(bpy.data.objects):
            if obj is not arm and obj not in meshes:
                bpy.data.objects.remove(obj, do_unlink=True)
        slots = meta["builds"][build]["material_slots"]
        for mesh in meshes:
            names = [s.material.name if s.material else None for s in mesh.material_slots]
            assert names == slots, (build, names)
            uvs = [uv.name for uv in mesh.data.uv_layers]
            assert uvs[:2] == ["UVMap", "NumberUV"], uvs
            # TEXCOORD order follows the uv_layers order; keep UVMap active for rendering.
            mesh.data.uv_layers.active_index = 0
            for attr in list(mesh.data.color_attributes):
                mesh.data.color_attributes.remove(attr)
        for name in slots:
            color, rough, metal = ATHLETE[name]
            make_material(name, color, rough, metal)
        for img in list(bpy.data.images):
            bpy.data.images.remove(img)
        rests[build] = {b.name: [list(r) for r in b.matrix_local] for b in arm.data.bones}
        arm.data.pose_position = "REST"
        gltf_export(os.path.join(out, "characters", "%s.glb" % build), export_animations=False, export_skins=True,
                    export_influence_nb=4, export_vertex_color="NONE", export_image_format="NONE",
                    export_materials="EXPORT", export_rest_position_armature=True)
    # All three must share one skeleton so one set of clips drives them all.
    worst = 0.0
    for build in ("lean", "big"):
        for bone, m in rests[build].items():
            ref = rests["mid"][bone]
            worst = max(worst, max(abs(a - b) for ra, rb in zip(m, ref) for a, b in zip(ra, rb)))
    log("skeleton rest difference lean/big vs mid: %.2e" % worst)
    assert worst < 1e-4, "builds do not share one rest skeleton"


# --------------------------------------------------------------------------------------------- animations
def _norm(matrix):
    loc, rot, _scale = matrix.decompose()
    return Matrix.LocRotScale(loc, rot, Vector((1.0, 1.0, 1.0)))


def _retarget_clip(scene, target, clip, report):
    name, frames = clip["name"], int(clip["frames"])
    path = os.path.join(ANIMS, "A_%s.fbx" % name)
    before_obj, before_act = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.fbx(filepath=path, use_anim=True, **FBX_IMPORT)
    new_objs = [o for o in bpy.data.objects if o not in before_obj]
    src = next(o for o in new_objs if o.type == "ARMATURE")
    src_action = src.animation_data.action
    f0, f1 = (int(round(v)) for v in src_action.frame_range)
    if f1 - f0 != frames:
        raise RuntimeError("%s: FBX covers frames %d..%d, manifest says %d" % (name, f0, f1, frames))

    bones = list(target.data.bones)          # parents before children
    missing = [b.name for b in bones if b.name not in src.pose.bones]
    if missing:
        raise RuntimeError("%s: FBX lacks bones %s" % (name, missing))

    # Pose of every bone, world space, metres, unit scale.
    posed = []
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        mw = src.matrix_world
        posed.append({b.name: _norm(mw @ src.pose.bones[b.name].matrix) for b in bones})

    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    target.animation_data.action = action
    rest_local = {}
    for b in bones:
        rest_local[b.name] = (b.parent.matrix_local.inverted() @ b.matrix_local) if b.parent else b.matrix_local.copy()
    prev_q = {}
    for i, pose in enumerate(posed):
        for b in bones:
            pb = target.pose.bones[b.name]
            local = (pose[b.parent.name].inverted() @ pose[b.name]) if b.parent else pose[b.name]
            basis = rest_local[b.name].inverted() @ local
            loc, rot, _ = basis.decompose()
            last = prev_q.get(b.name)
            if last is not None and last.dot(rot) < 0.0:
                rot.negate()
            prev_q[b.name] = rot.copy()
            pb.rotation_mode = "QUATERNION"
            pb.location = loc
            pb.rotation_quaternion = rot
            pb.scale = (1.0, 1.0, 1.0)
            pb.keyframe_insert("location", frame=i)
            pb.keyframe_insert("rotation_quaternion", frame=i)
    action.use_frame_range = True
    action.frame_start, action.frame_end = 0, frames

    # Check: evaluate the retargeted rig and compare every joint with the FBX, every frame.
    worst = 0.0
    root_path, pelvis_path = [], []
    for i in range(frames + 1):
        scene.frame_set(f0 + i)          # FBX rig at its frame
        src_heads = {b.name: (src.matrix_world @ src.pose.bones[b.name].head) for b in bones}
        scene.frame_set(i)               # target rig at the same clip time
        if f0 != 0:
            # both rigs are evaluated on one scene clock; only valid when the FBX starts on frame 0
            raise RuntimeError("unexpected FBX frame offset %d" % f0)
        for b in bones:
            worst = max(worst, (target.pose.bones[b.name].head - src_heads[b.name]).length)
        root_path.append(target.pose.bones["root"].head.copy())
        pelvis_path.append(target.pose.bones["pelvis"].head.copy())

    target.animation_data.action = None
    for obj in new_objs:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Armature):
                bpy.data.armatures.remove(data)
            elif isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
    for act in [a for a in bpy.data.actions if a not in before_act and a is not action]:
        bpy.data.actions.remove(act)

    root_travel = max((p - root_path[0]).length for p in root_path)
    pel_xy = [Vector((p.x, p.y)) for p in pelvis_path]
    pel_net = (pel_xy[-1] - pel_xy[0]).length
    pel_span = max((p - q).length for p in pel_xy for q in pel_xy)
    report[name] = dict(max_joint_error_m=round(worst, 6), root_max_offset_m=round(root_travel, 6),
                        pelvis_net_xy_m=round(pel_net, 4), pelvis_span_xy_m=round(pel_span, 4),
                        pelvis_start=[round(v, 4) for v in pelvis_path[0]],
                        pelvis_end=[round(v, 4) for v in pelvis_path[-1]])
    log("clip %-14s %3d f  joint err %.2e m  root %.3f m  pelvis net %.3f m" % (name, frames, worst, root_travel, pel_net))
    return worst


def export_anims(out):
    manifest = json.load(open(os.path.join(ANIMS, "anims.json")))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(BLEND, "player_mid.blend"))
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = int(manifest["fps"]), 1.0
    target = bpy.data.objects["Armature"]
    for obj in list(bpy.data.objects):
        if obj is not target:
            bpy.data.objects.remove(obj, do_unlink=True)
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)
    target.data.pose_position = "POSE"
    if target.animation_data is None:
        target.animation_data_create()
    for pb in target.pose.bones:
        for c in list(pb.constraints):
            pb.constraints.remove(c)
    report = {}
    t0 = time.time()
    worst = 0.0
    for clip in manifest["clips"]:
        worst = max(worst, _retarget_clip(scene, target, clip, report))
    log("retargeted %d clips in %.0f s, worst joint error %.2e m" % (len(manifest["clips"]), time.time() - t0, worst))
    assert worst < 2e-3, "retarget mismatch"
    # Rest pose on export; every action becomes one glTF animation named after it.
    for pb in target.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.scale = (1, 1, 1)
    scene.frame_set(0)
    gltf_export(os.path.join(out, "characters", "anims.glb"), export_animations=True, export_animation_mode="ACTIONS",
                export_force_sampling=True, export_frame_step=1, export_optimize_animation_size=True,
                export_optimize_animation_keep_anim_armature=True, export_anim_slide_to_zero=False,
                export_reset_pose_bones=True, export_skins=False, export_materials="NONE",
                export_image_format="NONE", export_rest_position_armature=True, export_vertex_color="NONE")
    os.makedirs(SCRATCH, exist_ok=True)
    with open(os.path.join(SCRATCH, "anim_report.json"), "w") as handle:
        json.dump(report, handle, indent=1)

    # Runtime manifest: the game's anims.json plus derived numbers.
    clips = []
    for clip in manifest["clips"]:
        entry = dict(clip)
        frames = int(clip["frames"])
        entry["duration_s"] = round(frames / manifest["fps"], 6)
        entry["keys"] = frames + 1
        r = report[clip["name"]]
        entry["root_motion"] = r["root_max_offset_m"] > 1e-4
        entry["pelvis_net_xy_m"] = r["pelvis_net_xy_m"]
        if "events" in clip:
            entry["event_times_s"] = {k: round(v / manifest["fps"], 6) for k, v in clip["events"].items()}
        clips.append(entry)
    runtime = dict(
        fps=manifest["fps"],
        source="Art/export/anims/anims.json (+ derived fields from web/tools/export_gltf.py)",
        space_blender=manifest["space"],
        space_gltf=("Positions in the original notes are Blender rig axes: -Y forward, +X the athlete's left, +Z up. "
                    "In glTF/three.js that is +Z forward, +X the athlete's left, +Y up: (x, y, z)_gltf = (x, z, -y)_blender. "
                    "A `direction` [dx, dy] becomes (dx, 0, -dy) in the athlete's local glTF frame."),
        timing=("Every clip has frames+1 keys (0..frames) at 30 fps; duration = frames/30 s. For loops the last key "
                "equals the first, so LoopRepeat over the full duration is seamless (the game wraps at frames/30)."),
        sockets=dict(hand="ball_hand_r", tuck="ball_tuck_r", head="head"),
        clips=clips,
    )
    with open(os.path.join(out, "characters", "anims.json"), "w") as handle:
        json.dump(runtime, handle, indent=1)
    log("wrote characters/anims.json")


# --------------------------------------------------------------------------------------------- stadium + props
def _import_static(fbx):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx, use_anim=False, **FBX_IMPORT)
    objs = [o for o in bpy.data.objects if o not in before]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    # FBX is centimetres with a 0.01 object scale: bake it so the glTF is in metres with identity nodes.
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return objs


def _dress(objs, images):
    for obj in objs:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            if slot.material is None:
                continue
            raw = slot.material.name.split(".")[0]
            spec = STADIUM_SLOTS.get(raw)
            if spec is None:
                log("WARNING: no recipe for slot", raw)
                continue
            color, rough, metal, extra = spec
            img = images.get(extra.get("image")) if extra.get("image") else None
            mat = make_material(raw + "__new", color, rough, metal, emit=extra.get("emit"),
                                strength=extra.get("strength", 1.0), image=img,
                                emit_image=extra.get("emit_image", 0.0), two_sided=extra.get("two_sided", False),
                                uv_scale=extra.get("uv_scale"))
            slot.material = mat
    for mat in list(bpy.data.materials):
        if not mat.name.endswith("__new") and mat.users == 0:
            bpy.data.materials.remove(mat)
    for mat in list(bpy.data.materials):
        if mat.name.endswith("__new"):
            target = mat.name[: -len("__new")]
            old = bpy.data.materials.get(target)
            if old is not None:
                old.name = target + "__old"
            mat.name = target
    for mat in list(bpy.data.materials):
        if mat.name.endswith("__old") and mat.users == 0:
            bpy.data.materials.remove(mat)


def _check_ad_uvs(obj):
    """M_Ads picks the board in the shader: U' = (fmod(floor(U), 8) + frac(U)) / 8, U = 1 per board.
    For U >= 0 that equals frac(U / 8), so the AdBoard material samples T_Ads through a texture transform
    of scale (1/8, 1) with REPEAT wrapping (KHR_texture_transform). TEXCOORD_0 itself stays as authored
    (1 unit per board, 0..63), so a custom shader can still apply the M_Ads formula to the raw UVs."""
    names = [s.material.name if s.material else "" for s in obj.material_slots]
    if "AdBoard" not in names:
        return 0
    slot = names.index("AdBoard")
    uv = obj.data.uv_layers[0].data
    us = [uv[li].uv[0] for p in obj.data.polygons if p.material_index == slot for li in p.loop_indices]
    assert min(us) > -1e-3, "negative ad U would need the +8000 offset of M_Ads"
    log("ad board UVs: %d loops, U %.2f..%.2f (1 per board)" % (len(us), min(us), max(us)))
    return len(us)


def export_stadium(out, which):
    os.makedirs(SCRATCH, exist_ok=True)
    ads_path = os.path.join(SCRATCH, "ads_gltf.jpg")
    if "stadium" in which:
        clear_scene()
        if not os.path.exists(ads_path):
            raise SystemExit("run web/tools/convert_textures.py first (needs %s)" % ads_path)
        images = {"ads": bpy.data.images.load(ads_path)}
        objs = _import_static(os.path.join(STADIUM, "SM_Stadium.fbx"))
        for o in objs:
            if o.type == "MESH":
                o.name = "Stadium"
                o.data.name = "Stadium"
                for attr in list(o.data.color_attributes):
                    o.data.color_attributes.remove(attr)
                _check_ad_uvs(o)
        _dress(objs, images)
        gltf_export(os.path.join(out, "stadium", "stadium.glb"), export_animations=False, export_skins=False,
                    export_vertex_color="NONE", export_image_format="JPEG", export_jpeg_quality=85,
                    export_materials="EXPORT")
    if "props" in which:
        for src, dst in PROPS.items():
            clear_scene()
            objs = _import_static(os.path.join(STADIUM, src + ".fbx"))
            crowd = src.startswith("SM_Crowd")
            for o in objs:
                if o.type == "MESH":
                    o.name = dst
                    o.data.name = dst
                    if not crowd:
                        for attr in list(o.data.color_attributes):
                            o.data.color_attributes.remove(attr)
                    elif o.data.color_attributes:
                        o.data.color_attributes.active_color_index = 0
            _dress(objs, {})
            gltf_export(os.path.join(out, "stadium", dst + ".glb"), export_animations=False, export_skins=False,
                        export_vertex_color="ACTIVE" if crowd else "NONE", export_all_vertex_colors=False,
                        export_active_vertex_color_when_no_material=crowd,
                        export_image_format="NONE", export_materials="EXPORT")


# --------------------------------------------------------------------------------------------- main
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="export_gltf.py")
    ap.add_argument("--out", default=os.path.join(REPO, "web", "public", "assets"))
    ap.add_argument("--only", default="characters,anims,stadium,props")
    args = ap.parse_args(argv)
    which = [w.strip() for w in args.only.split(",") if w.strip()]
    out = os.path.abspath(args.out)
    if "characters" in which:
        export_characters(out)
    if "anims" in which:
        export_anims(out)
    if "stadium" in which or "props" in which:
        export_stadium(out, which)
    log("done")


main()
