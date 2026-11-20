"""Pipeline smoke test: a box-man on the shared rig plus three probe animations.

    blender -b --factory-startup -P Art/blender/test_blockout.py

Writes Art/export/test/*.fbx and Art/previews/test/blockout.png. The box-man carries two
asymmetric markers so a mirrored or mis-rotated import is obvious in Unreal: a red nose on the
FRONT of the head and a yellow block on the LEFT shoulder.
"""
import math
import os
import sys

import bpy
from mathutils import Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from furylib import blockout, export, render, rig  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "export", "test")
PREVIEW = os.path.join(ROOT, "previews", "test")


def key_x(arm, action_name, frames, bones):
    """bones: {bone: degrees about local X at the last frame}. Returns the action."""
    action = bpy.data.actions.new(action_name)
    arm.animation_data_create()
    arm.animation_data.action = action
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion()
        pb.location = (0, 0, 0)
    for frame, t in ((0, 0.0), (frames, 1.0)):
        for pb in arm.pose.bones:
            deg = bones.get(pb.name, 0.0) * t
            pb.rotation_quaternion = Quaternion(Vector((1, 0, 0)), math.radians(deg))
            pb.keyframe_insert("rotation_quaternion", frame=frame)
            pb.keyframe_insert("location", frame=frame)
    return action


def main():
    scene = render.reset_scene()
    arm = rig.build_armature()

    body = blockout.build_blockout(arm)

    export.export_skeletal_mesh(os.path.join(OUT, "SK_Blockout.fbx"), arm, [body])

    probes = {
        "A_Test_ArmsFwd": {"upperarm_l": 90, "upperarm_r": 90},
        "A_Test_Bow": {"spine_01": 25, "spine_02": 25, "spine_03": 25, "head": 20},
        "A_Test_KneeL": {"thigh_l": 80, "calf_l": -90},
    }
    actions = {name: key_x(arm, name, 30, bones) for name, bones in probes.items()}
    for name, action in actions.items():
        export.export_action(os.path.join(OUT, name + ".fbx"), arm, action, 0, 30)

    # Preview: the left-knee probe at its last frame, seen from the front-left.
    arm.animation_data.action = actions["A_Test_KneeL"]
    scene.frame_set(30)
    render.studio(scene)
    cam = render.camera(scene)
    render.orbit(cam, target=(0, 0, 1.0), distance=4.5, azimuth_deg=35, elevation_deg=10)
    render.still(os.path.join(PREVIEW, "blockout.png"), 720, 720)
    print("BLOCKOUT_OK")


main()
