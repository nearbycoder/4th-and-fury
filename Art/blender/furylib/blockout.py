"""A box-man skinned to the shared rig: a stand-in body for previewing animation.

It carries two asymmetric markers so a mirrored or mis-rotated result is obvious: a red nose on
the FRONT of the head and a yellow block on the LEFT shoulder.
"""
import bpy

from . import rig


def _material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.6
    return mat


def _weight_all(obj, bone):
    group = obj.vertex_groups.new(name=bone)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")


def _box(name, center, size, bone, mat, parts):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    _weight_all(obj, bone)
    parts.append(obj)


def _bone_box(bone, thickness, mat, parts):
    head, tail = rig.JOINTS[bone], rig.TAILS[bone]
    axis = tail - head
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(head + tail) * 0.5)
    obj = bpy.context.object
    obj.name = "seg_" + bone
    obj.scale = (thickness, axis.length, thickness)
    obj.rotation_euler = axis.to_track_quat("Y", "Z").to_euler()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    obj.data.materials.append(mat)
    _weight_all(obj, bone)
    parts.append(obj)


def build_blockout(armature, name="SK_Blockout"):
    """Create the box-man, skin it to `armature`, and return the mesh object."""
    grey = _material("Body", (0.42, 0.45, 0.50))
    dark = _material("Limb", (0.20, 0.22, 0.26))
    red = _material("Nose", (0.9, 0.08, 0.05))
    yellow = _material("LeftMark", (0.95, 0.8, 0.05))
    parts = []
    deforming = {row[0] for row in rig.bone_table() if row[5]}
    for bone in rig.BONE_NAMES:
        if bone not in deforming:
            continue
        core = bone.startswith(("pelvis", "spine"))
        thick = 0.22 if core else 0.17 if bone == "head" else 0.08
        _bone_box(bone, thick, grey if core or bone == "head" else dark, parts)
    _box("nose", (0.0, -0.11, 1.74), (0.05, 0.08, 0.05), "head", red, parts)
    _box("left_mark", (0.19, 0.0, 1.58), (0.09, 0.09, 0.09), "spine_03", yellow, parts)

    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    body = bpy.context.object
    body.name = name
    rig.skin_to_armature(body, armature)
    return body
