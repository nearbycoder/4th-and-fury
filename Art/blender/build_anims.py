"""Build the 4th & Fury athlete animation set.

    blender -b --factory-startup -P Art/blender/build_anims.py -- [options]

Writes, for every clip (in the order of anim/library.py):

    Art/export/anims/A_<Name>.fbx      the clip on the bare shared rig, 30 fps, frames 0..N
    Art/export/anims/anims.json        the manifest (updated after every clip)
    Art/previews/anims/<Name>.png      contact sheet: three-quarter view (top) and side view (bottom)
    Art/previews/anims/_overview.png   one key frame of every clip

Options (after the "--"):

    --only A,B,...   build just these clips (the manifest and overview keep the others)
    --no-render      skip the contact sheets
    --no-export      write no FBX / manifest; contact sheets go to Art/_scratch/anims/draft
    --big 0,6,12     also render these frames large into Art/_scratch/anims/big
    --pose A,B       render named static poses of anim/poses.py from four sides into
                     Art/_scratch/anims/pose and exit ("all" for every pose)
    --mesh M         preview body: auto (default: Art/blend/player_mid.blend if present, else the
                     mannequin), dummy, blockout, player
    --list           print the clip list and exit
    --selftest       check the control rig's conventions and exit

Everything is generated from code: anim/library.py holds the clips, anim/controls.py the control
rig they are written against. Per clip the script prints a few measurements (ground contact,
foot sliding, reach, loop closure) next to what the contact sheets show.
"""
import argparse
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from furylib import export, render, rig as furyrig  # noqa: E402
from anim import bake, library, preview, selftest  # noqa: E402
from anim.clip import report  # noqa: E402
from anim.controls import Rig  # noqa: E402
from anim.skel import Skel  # noqa: E402

ART = os.path.dirname(HERE)
EXPORT_DIR = os.path.join(ART, "export", "anims")
PREVIEW_DIR = os.path.join(ART, "previews", "anims")
SCRATCH_DIR = os.path.join(ART, "_scratch", "anims")
PLAYER_BLEND = os.path.join(ART, "blend", "player_mid.blend")
MANIFEST = os.path.join(EXPORT_DIR, "anims.json")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="build_anims.py")
    ap.add_argument("--only", default="")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--big", default="")
    ap.add_argument("--pose", default="")
    ap.add_argument("--zoom", default="", help="with --pose: bone:metres, e.g. hand_r:0.6")
    ap.add_argument("--mesh", default="auto", choices=("auto", "dummy", "blockout", "player"))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    return ap.parse_args(argv)


def main():
    args = parse_args()
    scene = render.reset_scene()
    armature = furyrig.build_armature()
    rig = Rig(Skel(armature))

    if args.selftest:
        ok = selftest.run(armature, rig)
        sys.exit(0 if ok else 1)

    if args.pose:
        from anim import poses as pose_lib
        stage = preview.Stage(scene, armature, mesh=args.mesh, player_blend=PLAYER_BLEND, scratch=SCRATCH_DIR)
        names = list(pose_lib.POSES) if args.pose == "all" else [n.strip() for n in args.pose.split(",")]
        for name in names:
            controls, ball = pose_lib.POSES[name]()
            pose = rig.solve(controls)
            matrix = None
            if ball in ("hand", "tuck"):
                matrix = preview.socket_matrix(pose, ball)
            elif ball is not None:
                matrix = ball
            zoom = None
            if args.zoom:
                bone, _, size = args.zoom.partition(":")
                zoom = (bone, float(size or 0.6))
            out = stage.pose_sheet(name, pose, matrix, os.path.join(SCRATCH_DIR, "pose", name + ".png"), zoom=zoom)
            low = rig.lowest(pose)
            print(f"[pose] {name}: lowest {low[0] * 100:+.1f} cm ({low[1]}), lift {pose.lift * 100:+.1f} cm, "
                  f"warn {pose.warn} -> {out}")
        return

    clips = library.build_all(rig)
    order = [c.name for c in clips]
    if args.list:
        for c in clips:
            print(f"{c.name:14s} {c.frames:3d} f  loop={c.loop!s:5s} ball={c.ball:4s} events={c.events}")
        return
    only = [n.strip() for n in args.only.split(",") if n.strip()]
    unknown = [n for n in only if n not in order]
    if unknown:
        raise SystemExit(f"unknown clip(s): {', '.join(unknown)}")
    selected = [c for c in clips if not only or c.name in only]
    big_frames = [int(f) for f in args.big.split(",") if f.strip()]

    do_render = not args.no_render
    stage = None
    if do_render or big_frames:
        stage = preview.Stage(scene, armature, mesh=args.mesh, player_blend=PLAYER_BLEND, scratch=SCRATCH_DIR)
        print(f"[preview] body: {stage.mesh_name}")
    sheet_dir = PREVIEW_DIR if not args.no_export else os.path.join(SCRATCH_DIR, "draft")
    tile_dir = os.path.join(SCRATCH_DIR, "overview")
    os.makedirs(sheet_dir, exist_ok=True)
    os.makedirs(tile_dir, exist_ok=True)

    entries = bake.load_manifest(MANIFEST)
    entries = {k: v for k, v in entries.items() if k in order}
    problems_all = {}
    t_start = time.time()
    for clip in selected:
        t0 = time.time()
        poses = clip.sample(rig)
        lines, problems = report(clip, rig, poses)
        action = bake.make_action(armature, "A_" + clip.name, poses)
        print(f"\n=== {clip.name}  ({clip.frames} f{', loop' if clip.loop else ''}, ball {clip.ball}, events {clip.events})")
        for line in lines:
            print("    " + line)
        for p in problems:
            print("    !! " + p)
        if problems:
            problems_all[clip.name] = problems
        if not args.no_export:
            export.export_action(os.path.join(EXPORT_DIR, f"A_{clip.name}.fbx"), armature, action, 0, clip.frames)
            entries[clip.name] = clip.manifest()
            bake.write_manifest(MANIFEST, entries, order)
        if stage is not None:
            if do_render:
                stage.clip_sheet(clip, poses, action, os.path.join(sheet_dir, clip.name + ".png"))
                stage.overview_tile(clip, poses, action, os.path.join(tile_dir, clip.name + ".png"))
            if big_frames:
                stage.big(clip, poses, action, [f for f in big_frames if 0 <= f <= clip.frames],
                          os.path.join(SCRATCH_DIR, "big"))
        print(f"    done in {time.time() - t0:.1f} s")
        bpy.data.actions.remove(action)

    if do_render:
        preview.overview_sheet(tile_dir, order, os.path.join(sheet_dir, "_overview.png"))
    print(f"\nBUILT {len(selected)} clip(s) in {time.time() - t_start:.1f} s"
          + ("" if not args.no_export else "  (draft: nothing exported)"))
    if problems_all:
        print("CLIPS WITH WARNINGS:")
        for name, problems in problems_all.items():
            for p in problems:
                print(f"  {name}: {p}")
    print("ANIMS_OK")


main()
