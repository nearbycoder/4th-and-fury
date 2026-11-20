"""Test poses for judging deformation. Angles are degrees about each bone's LOCAL axes, following
the rule in furylib/rig.py: +X swings a bone's tip toward the character's front (calf: -X flexes
the knee), Y twists, Z is the remaining swing and needs the opposite sign on the right side.
For an arm, +Z on the left / -Z on the right lifts it away from the body.
For the fingers and thumb, -Z on the left / +Z on the right curls them toward the palm.
"""
import math
from furylib.rig import FINGERS
from mathutils import Euler, Quaternion, Vector


def apply_pose(armature, pose):
    """pose: {bone: (rx, ry, rz)} plus optional {"__loc__": {bone: (x, y, z)}} in bone space."""
    locs = pose.get("__loc__", {})
    for pb in armature.pose.bones:
        rot = pose.get(pb.name)
        parts = pb.name.split("_")
        if len(parts) == 3 and parts[0] in {digit[0] for digit in FINGERS}:
            grip = abs(pose.get("fingers_" + parts[2], (0, 0, 0))[2]) / 58.0
            rot = ((52 if parts[1] == "1" else 30) * min(1, grip), 0, 0)
        pb.rotation_mode = "QUATERNION"
        if rot is None:
            pb.rotation_quaternion = Quaternion()
        else:
            pb.rotation_quaternion = Euler([math.radians(a) for a in rot], "XYZ").to_quaternion()
        pb.location = Vector(locs.get(pb.name, (0.0, 0.0, 0.0)))


def reset_pose(armature):
    apply_pose(armature, {})


POSES = {
    "sprint": {
        "pelvis": (10, 0, 0), "spine_01": (4, -4, 0), "spine_02": (4, -4, 0), "spine_03": (4, -5, 0),
        "neck_01": (-6, 0, 0), "head": (-10, 0, 0),
        "thigh_l": (72, 0, 0), "calf_l": (-98, 0, 0), "foot_l": (8, 0, 0),
        "thigh_r": (-28, 0, 0), "calf_r": (-28, 0, 0), "foot_r": (-32, 0, 0), "ball_r": (28, 0, 0),
        "upperarm_l": (-48, 0, -32), "lowerarm_l": (88, 0, 0),
        "upperarm_r": (52, 0, 30), "lowerarm_r": (96, 0, 0),
        "fingers_l": (0, 0, -30), "fingers_r": (0, 0, 30),
        "__loc__": {"pelvis": (0.0, -0.03, 0.0)},
    },
    "three_point": {
        "pelvis": (62, 0, 0), "spine_01": (4, 0, 0), "spine_02": (3, 0, 0), "spine_03": (2, 0, 0),
        "neck_01": (-26, 0, 0), "head": (-34, 0, 0),
        "thigh_l": (118, 0, 6), "calf_l": (-108, 0, 0), "foot_l": (50, 0, 0),
        "thigh_r": (112, 0, -6), "calf_r": (-100, 0, 0), "foot_r": (48, 0, 0),
        "upperarm_r": (64, 0, 40), "lowerarm_r": (6, 0, 0), "hand_r": (0, 0, 0), "fingers_r": (0, 0, 25),
        "upperarm_l": (40, 0, -30), "lowerarm_l": (86, 0, 0),
        "__loc__": {"pelvis": (0.0, -0.335, -0.10)},
    },
    "arms_up": {
        "clavicle_l": (0, 0, 22), "clavicle_r": (0, 0, -22),
        "upperarm_l": (0, 0, 108), "upperarm_r": (0, 0, -108),
        "lowerarm_l": (6, 0, 0), "lowerarm_r": (6, 0, 0),
        "head": (-8, 0, 0),
    },
    "throw": {
        "pelvis": (0, -14, 0), "spine_01": (-3, -10, 0), "spine_02": (-3, -12, 0), "spine_03": (-2, -14, 0),
        "neck_01": (0, 14, 0), "head": (0, 24, 0),
        "clavicle_r": (0, 0, -14),
        "upperarm_r": (-38, 60, -52), "lowerarm_r": (102, 0, 0), "hand_r": (-20, 0, 0),
        "upperarm_l": (62, 0, 12), "lowerarm_l": (28, 0, 0),
        "thigh_l": (30, 0, 6), "calf_l": (-24, 0, 0),
        "thigh_r": (-18, 0, -6), "calf_r": (-22, 0, 0), "foot_r": (-22, 0, 0), "ball_r": (20, 0, 0),
        "__loc__": {"pelvis": (0.0, -0.035, 0.0)},
    },
    "deep_knee": {
        "pelvis": (26, 0, 0), "spine_01": (6, 0, 0), "spine_02": (6, 0, 0), "spine_03": (4, 0, 0),
        "neck_01": (-14, 0, 0), "head": (-18, 0, 0),
        "thigh_l": (118, 0, 10), "calf_l": (-142, 0, 0), "foot_l": (36, 0, 0),
        "thigh_r": (118, 0, -10), "calf_r": (-142, 0, 0), "foot_r": (36, 0, 0),
        "upperarm_l": (58, 0, -20), "lowerarm_l": (50, 0, 0),
        "upperarm_r": (58, 0, 20), "lowerarm_r": (50, 0, 0),
        "__loc__": {"pelvis": (0.0, -0.50, -0.03)},
    },
    "lying": {
        "root": (-90, 0, 0),
        "spine_02": (-4, 0, 0), "head": (10, 0, 12),
        "thigh_l": (38, 0, 12), "calf_l": (-72, 0, 0), "foot_l": (-20, 0, 0),
        "thigh_r": (4, 0, -14), "calf_r": (-8, 0, 0), "foot_r": (-30, 0, 0),
        "upperarm_l": (0, 0, 40), "lowerarm_l": (40, 0, 0),
        "upperarm_r": (10, 0, 14), "lowerarm_r": (70, 0, 0),
        "__loc__": {"root": (0.0, 0.0, 0.0)},
    },
    "arms_down": {
        "upperarm_l": (6, 0, -34), "upperarm_r": (6, 0, 34),
        "lowerarm_l": (14, 0, 0), "lowerarm_r": (14, 0, 0),
    },
    "fist": {      # fingers and thumbs closed, wrists turned, head turned and tipped
        "fingers_l": (0, 0, -58), "fingers_r": (0, 0, 58),
        "thumb_l": (0, 0, -35), "thumb_r": (0, 0, 35),
        "hand_l": (0, 60, 0), "hand_r": (-35, 0, 0),
        "lowerarm_l": (70, 0, 0), "lowerarm_r": (70, 0, 0),
        "upperarm_l": (30, 0, -20), "upperarm_r": (30, 0, 20),
        "neck_01": (-8, 24, 0), "head": (-14, 34, 8),
    },
    "tpose": {
        "upperarm_l": (0, 0, 45), "upperarm_r": (0, 0, -45),
    },
}
