"""Build the 4th & Fury athlete in its three body builds (lean / mid / big).

    blender -b --factory-startup -P Art/blender/build_player.py
    blender -b --factory-startup -P Art/blender/build_player.py -- --builds mid --no-previews

Writes, per build:
    Art/export/characters/SK_Player_<Build>.fbx     skinned mesh + shared rig, rest pose
    Art/blend/player_<build>.blend                  the same scene (objects "Armature", "SK_Player_<Build>")
    Art/previews/characters/*_<build>.png           turnarounds, close-ups, pose tests, UV/normal checks
and Art/export/characters/player_meta.json for the engine.

Options (after "--"):
    --builds lean mid big     which builds to make (default: all three)
    --no-previews             skip the preview renders
    --scheme NAME             preview colour scheme (timber / ember / glacier)
    --only-previews           re-render previews from the saved .blend files without rebuilding

All modelling lives in Art/blender/player/. The skeleton comes from furylib/rig.py unchanged.
"""
import argparse
import json
import os
import sys
import time

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from furylib import export, render, rig          # noqa: E402
from player import assemble, build, materials, params, preview   # noqa: E402

ART = os.path.dirname(HERE)
OUT_FBX = os.path.join(ART, "export", "characters")
OUT_BLEND = os.path.join(ART, "blend")
OUT_PREVIEW = os.path.join(ART, "previews", "characters")
OUT_SCRATCH = os.path.join(ART, "_scratch", "characters")

SCHEME_FOR = {"lean": "glacier", "mid": "timber", "big": "ember"}
NUMBER_FOR = {"lean": "17", "mid": "52", "big": "74"}
TRI_BUDGET = (30000, 55000)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="build_player.py")
    ap.add_argument("--builds", nargs="+", default=["lean", "mid", "big"], choices=["lean", "mid", "big"])
    ap.add_argument("--no-previews", action="store_true")
    ap.add_argument("--only-previews", action="store_true")
    ap.add_argument("--scheme", default=None, choices=sorted(materials.SCHEMES))
    return ap.parse_args(argv)


def validate(obj, armature, stats):
    """Check the engine contract on the finished mesh; raises on a hard violation."""
    mesh = obj.data
    problems = []
    notes = {}
    deform = set(assemble.DEFORM_BONES)
    group_names = {g.index: g.name for g in obj.vertex_groups}
    worst = 0
    for v in mesh.vertices:
        ws = [(group_names[g.group], g.weight) for g in v.groups if g.weight > 0.0]
        if not ws:
            problems.append(f"vertex {v.index} has no weights"); break
        if len(ws) > assemble.MAX_INFLUENCES:
            problems.append(f"vertex {v.index} has {len(ws)} influences"); break
        if abs(sum(w for _, w in ws) - 1.0) > 1e-3:
            problems.append(f"vertex {v.index} weights sum to {sum(w for _, w in ws):.4f}"); break
        if any(name not in deform for name, _ in ws):
            problems.append(f"vertex {v.index} uses a non-deforming bone"); break
        worst = max(worst, len(ws))
    notes["max_influences"] = worst
    slots = [s.material.name for s in obj.material_slots]
    if slots != [s for s in assemble.SLOTS if s in slots]:
        problems.append(f"slot order is wrong: {slots}")
    if [l.name for l in mesh.uv_layers] != ["UVMap", "NumberUV"]:
        problems.append(f"UV layers are {[l.name for l in mesh.uv_layers]}")
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    notes["bounds_min"] = [round(float(x), 4) for x in co.min(axis=0)]
    notes["bounds_max"] = [round(float(x), 4) for x in co.max(axis=0)]
    if abs(float(co[:, 2].min())) > 0.0015:
        problems.append(f"lowest point is z = {co[:, 2].min():.4f}, feet should rest on z = 0")
    # which slots have NumberUV coordinates inside the 0..1 square
    nuv = np.empty(len(mesh.loops) * 2, dtype=np.float32)
    mesh.uv_layers["NumberUV"].data.foreach_get("uv", nuv)
    nuv = nuv.reshape(-1, 2)
    uv0 = np.empty(len(mesh.loops) * 2, dtype=np.float32)
    mesh.uv_layers["UVMap"].data.foreach_get("uv", uv0)
    uv0 = uv0.reshape(-1, 2)
    inside = {}
    logo_lo, logo_hi = [9, 9], [-9, -9]
    for poly in mesh.polygons:
        slot = slots[poly.material_index]
        rng = range(poly.loop_start, poly.loop_start + poly.loop_total)
        uv = nuv[list(rng)]
        if ((uv >= 0.0) & (uv <= 1.0)).all(axis=1).any():
            inside[slot] = inside.get(slot, 0) + 1
        if slot == "HelmetLogo":
            lo = uv0[list(rng)].min(axis=0); hi = uv0[list(rng)].max(axis=0)
            logo_lo = [min(a, float(b)) for a, b in zip(logo_lo, lo)]
            logo_hi = [max(a, float(b)) for a, b in zip(logo_hi, hi)]
    notes["numberuv_faces_in_square_by_slot"] = inside
    if set(inside) - {"Jersey"}:
        problems.append(f"NumberUV lands in the number square on slots {sorted(set(inside) - {'Jersey'})}")
    if "HelmetLogo" in slots and (min(logo_lo) < -1e-4 or max(logo_hi) > 1 + 1e-4 or max(logo_lo) > 1e-3 or min(logo_hi) < 1 - 1e-3):
        problems.append(f"HelmetLogo UVs span {logo_lo}..{logo_hi}, expected 0..1")
    if not (TRI_BUDGET[0] <= stats["triangles"] <= TRI_BUDGET[1]):
        problems.append(f"{stats['triangles']} triangles is outside the {TRI_BUDGET} budget")
    if problems:
        raise RuntimeError("contract check failed for %s:\n  %s" % (obj.name, "\n  ".join(problems)))
    return notes


def build_one(name, scheme):
    scene = render.reset_scene()
    armature = rig.build_armature()
    parts, panels, info = build.build_parts(name)
    mats = materials.make_materials(scheme)
    obj, stats = assemble.build_object(params.MESH_NAMES[name], parts, armature, mats, panels)
    notes = validate(obj, armature, stats)

    fbx = os.path.join(OUT_FBX, params.MESH_NAMES[name] + ".fbx")
    export.export_skeletal_mesh(fbx, armature, [obj])
    os.makedirs(OUT_BLEND, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0        # no .blend1 backups next to the output
    blend = os.path.join(OUT_BLEND, f"player_{name}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, check_existing=False, compress=True)

    meta = dict(
        mesh=params.MESH_NAMES[name],
        fbx=os.path.relpath(fbx, ART),
        blend=os.path.relpath(blend, ART),
        triangles=stats["triangles"],
        vertices=stats["vertices"],
        material_slots=stats["material_slots"],
        triangles_by_slot=stats["triangles_by_slot"],
        max_bone_influences=notes["max_influences"],
        bounds_min_m=notes["bounds_min"],
        bounds_max_m=notes["bounds_max"],
        uv_atlas_metres=round(stats["uv_atlas_metres"], 4),
        number_panels=info["number_panels"],
        helmet_logo=info["helmet_logo"],
    )
    return scene, armature, obj, meta


def render_previews(scene, armature, obj, name, scheme):
    os.makedirs(OUT_PREVIEW, exist_ok=True)
    os.makedirs(OUT_SCRATCH, exist_ok=True)
    cam = preview.studio(scene)
    preview.dress(obj, scheme, NUMBER_FOR[name])
    done = [preview.turnaround(obj, armature, cam, OUT_PREVIEW, OUT_SCRATCH, name)]
    done += preview.closeups(obj, armature, cam, OUT_PREVIEW, OUT_SCRATCH, name)
    done += preview.pose_sheets(obj, armature, cam, OUT_PREVIEW, OUT_SCRATCH, name)
    done.append(preview.number_check(obj, armature, cam, OUT_PREVIEW, OUT_SCRATCH, name))
    done.append(preview.logo_check(obj, armature, cam, OUT_PREVIEW, OUT_SCRATCH, name))
    done.append(preview.backface_check(obj, armature, cam, OUT_PREVIEW, OUT_SCRATCH, name))
    return done


def main():
    args = parse_args()
    t0 = time.time()
    os.makedirs(OUT_FBX, exist_ok=True)
    meta_path = os.path.join(OUT_FBX, "player_meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path) as fh:
            meta = json.load(fh)
    meta.setdefault("builds", {})
    for name in args.builds:
        scheme = args.scheme or SCHEME_FOR[name]
        t1 = time.time()
        if args.only_previews:
            bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT_BLEND, f"player_{name}.blend"))
            scene = bpy.context.scene
            armature = bpy.data.objects[rig.ARMATURE_NAME]
            obj = bpy.data.objects[params.MESH_NAMES[name]]
        else:
            scene, armature, obj, entry = build_one(name, scheme)
            meta["builds"][name] = entry
            print(f"[{name}] built {entry['triangles']} tris / {entry['vertices']} verts in {time.time() - t1:.1f}s")
        if not args.no_previews:
            done = render_previews(scene, armature, obj, name, scheme)
            print(f"[{name}] rendered {len(done)} preview sheets")
    blends = [os.path.join(OUT_BLEND, f"player_{n}.blend") for n in ("lean", "mid", "big")]
    if not args.no_previews and all(os.path.exists(b) for b in blends):
        preview.lineup(blends, [SCHEME_FOR[n] for n in ("lean", "mid", "big")], [NUMBER_FOR[n] for n in ("lean", "mid", "big")],
                       os.path.join(OUT_PREVIEW, "lineup_builds.png"), OUT_SCRATCH)
        print("[all] rendered the three-build lineup")
    if not args.only_previews:
        meta.update(
            units="metres in Blender; the FBX is exported with furylib.export.export_skeletal_mesh",
            skeleton="furylib.rig (unchanged); armature object 'Armature'; rest pose only, no animation",
            orientation="Z up, character faces -Y, left side is +X",
            uv_maps={
                "UVMap": "atlas of every part at one texel density; 1 UV unit = uv_atlas_metres metres. "
                         "HelmetLogo faces are the exception: each patch fills 0..1 (U toward the facemask, V up).",
                "NumberUV": "jersey number squares (front, back, top of each shoulder cap) map to 0..1; "
                            "faces outside a panel fall outside 0..1; faces on no panel are (-1,-1).",
            },
            slot_notes={
                "Helmet": "shell, rim, inner liner, jaw pads, front and back bumpers",
                "HelmetStripe": "3.5 cm centre stripe, part of the shell surface",
                "HelmetLogo": "two 11 x 11 cm decal patches 1.7 mm off the shell; wants an alpha-masked emblem",
                "Facemask": "cage bars and the clips that hold them",
                "Strap": "chin cup, four chin straps and their snaps",
                "Eyes": "eyes and brows",
                "JerseyTrim": "collar band, sleeve cuffs and the under-arm side panels",
                "Belt": "belt, buckle, the laces of the fly and the towel",
                "Bands": "wristbands and bicep bands",
            },
            rigid_parts="helmet, facemask, visor, chin strap, eyes: 100% head. Cleats: foot/ball only.",
            scale_note="helmet (and the head in it) is 7% larger than life-size gear, gloves 10%, cleats 6%",
            pose_note="fingers_* / thumb_*: -Z on the left, +Z on the right curls toward the palm",
        )
        with open(meta_path, "w") as fh:
            json.dump(meta, fh, indent=2)
    print("PLAYER_BUILD_OK %.1fs" % (time.time() - t0))


main()
