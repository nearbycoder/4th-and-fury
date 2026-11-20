"""The one skeleton every 4th & Fury athlete shares.

Conventions (do not change without re-exporting every mesh and animation):

* Blender units are metres, Z is up, the character FACES -Y, and its LEFT side is +X.
* The armature object is named "Armature" (Unreal drops a node with that name instead of
  turning it into an extra root bone) and sits at the world origin with no rotation or scale.
* Rest pose is a relaxed A-pose: arms 45 degrees below horizontal, feet under the hips.
* Every bone's local Y runs along the bone (Blender's rule). Rolls are set so local Z points to
  the character's FRONT wherever the bone is not itself pointing front/back, which gives one
  rule for the whole body:

      a POSITIVE rotation about local X swings the bone's tip toward the character's front.

  So spine/neck/head +X = bend forward, upperarm +X = swing the arm forward, lowerarm +X =
  flex the elbow, thigh +X = lift the knee forward, calf -X = flex the knee (heel to the back).
  Feet and toes point forward, so their local Z is UP instead: foot/ball +X = toes up.
  Local Y rotation is twist along the bone. Local Z rotation is the remaining swing; because
  the skeleton is mirrored, Z (and Y) rotations need the opposite sign on the right side to
  produce a mirrored pose, while X rotations use the same sign on both sides.

All three body builds (lean / mid / big) use exactly these joint positions; only the mesh
around them changes. That is what lets one animation set drive every athlete.

In the rest pose the palms face the thighs and the thumbs point to the front.
"""
import math

import bpy
from mathutils import Vector

ARMATURE_NAME = "Armature"
FRONT = Vector((0.0, -1.0, 0.0))
UP = Vector((0.0, 0.0, 1.0))

# name, parent, head, tail, the world direction local Z is aligned to, deforms
_CENTER = [
    ("root",     None,       (0.0, 0.0, 0.00), (0.0, 0.0, 0.15), FRONT, False),
    ("pelvis",   "root",     (0.0, 0.0, 0.98), (0.0, 0.0, 1.08), FRONT, True),
    ("spine_01", "pelvis",   (0.0, 0.0, 1.08), (0.0, 0.0, 1.20), FRONT, True),
    ("spine_02", "spine_01", (0.0, 0.0, 1.20), (0.0, 0.0, 1.34), FRONT, True),
    ("spine_03", "spine_02", (0.0, 0.0, 1.34), (0.0, 0.0, 1.52), FRONT, True),
    ("neck_01",  "spine_03", (0.0, 0.0, 1.52), (0.0, 0.0, 1.62), FRONT, True),
    ("head",     "neck_01",  (0.0, 0.0, 1.62), (0.0, 0.0, 1.84), FRONT, True),
]

# Left side; the right side is mirrored across X with "_l" -> "_r".
_LEFT = [
    ("clavicle_l", "spine_03",   (0.025, 0.00, 1.470), (0.190, 0.00, 1.490), FRONT, True),
    ("upperarm_l", "clavicle_l", (0.190, 0.00, 1.490), (0.402, 0.00, 1.278), FRONT, True),
    ("lowerarm_l", "upperarm_l", (0.402, 0.00, 1.278), (0.590, -0.03, 1.087), FRONT, True),
    ("hand_l",     "lowerarm_l", (0.590, -0.03, 1.087), (0.655, -0.04, 1.020), FRONT, True),
    ("fingers_l",  "hand_l",     (0.655, -0.04, 1.020), (0.700, -0.045, 0.975), FRONT, True),
    ("thumb_l",    "hand_l",     (0.610, -0.06, 1.060), (0.640, -0.10, 1.030), UP, True),
    ("thigh_l",    "pelvis",     (0.095, 0.00, 0.940), (0.105, -0.01, 0.520), FRONT, True),
    ("calf_l",     "thigh_l",    (0.105, -0.01, 0.520), (0.105, 0.01, 0.100), FRONT, True),
    ("foot_l",     "calf_l",     (0.105, 0.01, 0.100), (0.105, -0.13, 0.025), UP, True),
    ("ball_l",     "foot_l",     (0.105, -0.13, 0.025), (0.105, -0.21, 0.025), UP, True),
]

FINGERS = [  # name, w offset, h offset, phalanx lengths, radius, splay deg, curl degs
    ("index", 0.0332, 0.0975, (0.041, 0.024, 0.020), 0.0118, 4.0, (12.0, 22.0, 14.0)),
    ("middle", 0.0112, 0.1010, (0.045, 0.027, 0.021), 0.0121, 0.5, (14.0, 24.0, 15.0)),
    ("ring", -0.0110, 0.0985, (0.041, 0.025, 0.020), 0.0116, -3.0, (16.0, 26.0, 16.0)),
    ("pinky", -0.0322, 0.0915, (0.033, 0.019, 0.018), 0.0104, -7.5, (19.0, 29.0, 18.0)),
]


# The relaxed glove has a common knuckle fan, then two independent hinges per digit.
def _finger_joints():
    _, _, start, end, _, _ = next(bone for bone in _LEFT if bone[0] == "hand_l")
    wrist = Vector(start)
    h = (Vector(end) - wrist).normalized()
    inward = Vector((-1, 0, 0))
    p = (inward - inward.dot(h) * h).normalized()
    w = p.cross(h)
    for name, offset, height, lengths, _, splay, curls in FINGERS:
        scale = 1.10
        cur = wrist + w * offset * scale + h * height + p * 0.0015
        d = h * math.cos(math.radians(splay)) + w * math.sin(math.radians(splay))
        angle = 0
        parent = "fingers_l"
        for i, (length, curl) in enumerate(zip(lengths, curls)):
            angle += math.radians(curl)
            end = cur + (d * math.cos(angle) + p * math.sin(angle)) * length * scale
            if i:
                bone = f"{name}_{i}_l"
                yield (bone, parent, tuple(cur), tuple(end), p, True)
                parent = bone
            cur = end


_LEFT.extend(_finger_joints())

# Non-deforming socket bones on the RIGHT arm. The engine parents the football to one of them,
# so their transforms ARE the grip: the bone's head is the ball's centre and the bone's local Y
# is the ball's long axis. They may be animated like any other bone.
#   ball_hand_r  - throwing / catching grip: ball across the palm of the right hand.
#   ball_tuck_r  - carrying grip: ball lying along the inside of the right forearm.
_SOCKETS = [
    # Clearances (set by the animation build so the 0.17 m thick ball is gripped rather than
    # swallowed): ball centre 0.092 m off the hand's axis, 0.110 m off the forearm's axis.
    ("ball_hand_r", "hand_r",     (-0.556, -0.035, 0.990), (-0.556, -0.175, 0.990), UP, False),
    ("ball_tuck_r", "lowerarm_r", (-0.427, -0.017, 1.096), (-0.525, -0.033, 0.996), FRONT, False),
]


def _mirror(v):
    return (-v[0], v[1], v[2])


def bone_table():
    """Every bone as (name, parent, head, tail, z_axis_hint, deform), parents before children."""
    rows = list(_CENTER) + list(_LEFT)
    for name, parent, head, tail, hint, deform in _LEFT:
        r_parent = parent[:-2] + "_r" if parent.endswith("_l") else parent
        rows.append((name[:-2] + "_r", r_parent, _mirror(head), _mirror(tail), Vector(_mirror(hint)), deform))
    rows.extend(_SOCKETS)
    rows.append(("towel", "thigh_r", (-0.094, -0.120, 1.015), (-0.094, -0.120, 0.838), FRONT, True))
    return rows


BONE_NAMES = [row[0] for row in bone_table()]
JOINTS = {row[0]: Vector(row[2]) for row in bone_table()}      # bone head positions (rest pose)
TAILS = {row[0]: Vector(row[3]) for row in bone_table()}       # bone tail positions (rest pose)
PARENTS = {row[0]: row[1] for row in bone_table()}

# Handy landmarks of the rest pose, in metres.
HIP_HEIGHT = 0.98
STAND_HEIGHT = 1.84          # top of the skull; the helmet adds a few centimetres
UPPER_ARM_LEN = (TAILS["upperarm_l"] - JOINTS["upperarm_l"]).length
FOREARM_LEN = (TAILS["lowerarm_l"] - JOINTS["lowerarm_l"]).length
THIGH_LEN = (TAILS["thigh_l"] - JOINTS["thigh_l"]).length
CALF_LEN = (TAILS["calf_l"] - JOINTS["calf_l"]).length


def build_armature(collection=None):
    """Create the armature object named "Armature" at the origin and return it."""
    old = bpy.data.objects.get(ARMATURE_NAME)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    data = bpy.data.armatures.new(ARMATURE_NAME)
    obj = bpy.data.objects.new(ARMATURE_NAME, data)
    (collection or bpy.context.scene.collection).objects.link(obj)

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent, head, tail, hint, deform in bone_table():
        bone = data.edit_bones.new(name)
        bone.head = Vector(head)
        bone.tail = Vector(tail)
        bone.align_roll(hint)
        bone.use_deform = deform
        if parent:
            bone.parent = data.edit_bones[parent]
            bone.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for pose_bone in obj.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
    return obj


def skin_to_armature(mesh_obj, armature_obj):
    """Parent a mesh that already has vertex groups named after bones to the armature."""
    mesh_obj.parent = armature_obj
    for mod in list(mesh_obj.modifiers):
        if mod.type == "ARMATURE":
            mesh_obj.modifiers.remove(mod)
    mod = mesh_obj.modifiers.new("Armature", "ARMATURE")
    mod.object = armature_obj
    mod.use_vertex_groups = True
    return mod
