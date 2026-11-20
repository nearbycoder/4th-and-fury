"""Pose samples -> Blender action (one key per frame per bone), and the manifest file."""
import json
import os

import bpy


def make_action(armature, name, poses):
    """Create action `name` holding poses[f] at frame f for every bone. Returns the action."""
    old = bpy.data.actions.get(name)
    if old is not None:
        bpy.data.actions.remove(old)
    action = bpy.data.actions.new(name)
    slot = action.slots.new(id_type="OBJECT", name=armature.name)
    layer = action.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    bag = strip.channelbag(slot, ensure=True)
    count = len(poses)
    frames = [float(f) for f in range(count)]

    def curve(path, index, group, values):
        fc = bag.fcurves.new(path, index=index, group_name=group)
        fc.keyframe_points.add(count)
        co = [0.0] * (2 * count)
        co[0::2] = frames
        co[1::2] = values
        fc.keyframe_points.foreach_set("co", co)
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        fc.update()

    for bone in poses[0].skel.names:
        quats, prev = [], None
        for pose in poses:
            q = pose.q[bone].copy()
            if prev is not None and prev.dot(q) < 0.0:
                q.negate()                      # keep the sign continuous from frame to frame
            quats.append(q)
            prev = q
        for i in range(4):
            curve(f'pose.bones["{bone}"].rotation_quaternion', i, bone, [q[i] for q in quats])
        for i in range(3):
            curve(f'pose.bones["{bone}"].location', i, bone, [pose.loc[bone][i] for pose in poses])
    action.use_fake_user = True
    return action


def assign(armature, action):
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    if hasattr(armature.animation_data, "action_slot") and len(action.slots):
        armature.animation_data.action_slot = action.slots[0]


def load_manifest(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            data = json.load(fh)
        return {entry["name"]: entry for entry in data.get("clips", [])}
    except (ValueError, KeyError, TypeError):
        return {}


def write_manifest(path, entries, order, fps=30):
    """entries: {name: manifest entry}; written in `order`, skipping names without an entry."""
    clips = [entries[name] for name in order if name in entries]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    space = ("Positions and directions are in metres relative to the root, in the rig's axes: -Y is the way the "
             "character faces, +X its left, +Z up. `direction` is the way the root travels at `speed`. "
             "`ball_frames` are the first and last frame the ball rides in the socket named by `ball`.")
    lines = ["{", f'  "fps": {fps},', f'  "space": {json.dumps(space)},', '  "clips": [']
    for i, entry in enumerate(clips):
        lines.append("    " + json.dumps(entry) + ("," if i < len(clips) - 1 else ""))
    lines += ["  ]", "}"]
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
