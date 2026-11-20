"""FBX export that imports cleanly into Unreal Engine 5.9.

Every exporter in the project goes through these three functions so the conventions stay in one
place. Unreal reads the files with FourthAndFury/Scripts/import_assets.py.

* Skeletal meshes: the armature (named "Armature") plus its skinned meshes in one file.
* Animations: the armature alone, one action per file, sampled on every frame at 30 fps.
* Static meshes: one or more mesh objects per file; each object's origin becomes its pivot.

Scenes are authored in metres, but the files are written in CENTIMETRES with the factor baked
into the data itself (vertex positions, bone positions, animated bone offsets) and no scale left
on any object. That matters: Unreal builds a skeleton from the FBX bind pose, which its unit
conversion never touches, so a metre-unit file yields a skeleton one hundredth of the right size.
The baking is done on temporary copies; the scene you call from is left exactly as it was.
"""
import os

import bpy
from mathutils import Matrix

FPS = 30
CM = 100.0   # Blender metres -> Unreal centimetres
_SOURCE_SUFFIX = "__src"


def set_scene_fps(scene=None):
    scene = scene or bpy.context.scene
    scene.render.fps = FPS
    scene.render.fps_base = 1.0


def _object_mode():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _select_only(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def _fbx_settings():
    return dict(
        use_selection=True,
        # Data is already in centimetres: write it through unscaled and label the file "cm".
        global_scale=0.01,
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_NONE",
        axis_forward="-Z",
        axis_up="Y",
        use_mesh_modifiers=True,
        mesh_smooth_type="FACE",
        use_tspace=False,
        colors_type="LINEAR",
        add_leaf_bones=False,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        use_armature_deform_only=False,
        use_custom_props=False,
        path_mode="AUTO",
        embed_textures=False,
        batch_mode="OFF",
    )


def _baked_mesh_copy(obj, name, matrix):
    """A new object whose mesh is `obj` with every modifier applied, transformed by `matrix`."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.transform(matrix)
    mesh.update()
    copy = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(copy)
    for group in obj.vertex_groups:          # same order, so the copied weights keep their meaning
        copy.vertex_groups.new(name=group.name)
    return copy


def _scaled_armature_copy(armature):
    """A copy of the armature, named "Armature", with every bone position multiplied by CM."""
    source_name = armature.name
    armature.name = source_name + _SOURCE_SUFFIX
    copy = armature.copy()
    copy.data = armature.data.copy()
    copy.name = "Armature"
    copy.data.name = "Armature"
    copy.animation_data_clear()
    copy.matrix_world = Matrix.Identity(4)
    bpy.context.scene.collection.objects.link(copy)
    for pose_bone in copy.pose.bones:
        for constraint in list(pose_bone.constraints):
            pose_bone.constraints.remove(constraint)
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.matrix_basis = Matrix.Identity(4)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = copy
    copy.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for bone in copy.data.edit_bones:
        bone.use_connect = False
    for bone in copy.data.edit_bones:
        roll = bone.roll
        bone.head = bone.head * CM
        bone.tail = bone.tail * CM
        bone.roll = roll
    bpy.ops.object.mode_set(mode="OBJECT")
    return copy, source_name


def _discard(objects):
    for obj in objects:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Armature):
                bpy.data.armatures.remove(data)


def export_skeletal_mesh(path, armature, meshes):
    """Armature + skinned meshes in the rest pose (no animation)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _object_mode()
    previous_pose = armature.data.pose_position
    armature.data.pose_position = "REST"       # so applying modifiers bakes the undeformed shape
    bpy.context.view_layer.update()
    temporary = []
    mesh_names = [(m, m.name) for m in meshes]
    rig, source_name = None, armature.name
    try:
        for mesh, name in mesh_names:
            mesh.name = name + _SOURCE_SUFFIX
            copy = _baked_mesh_copy(mesh, name, Matrix.Scale(CM, 4) @ mesh.matrix_world)
            temporary.append(copy)
        rig, source_name = _scaled_armature_copy(armature)
        rig.data.pose_position = "REST"
        for copy in temporary:
            copy.parent = rig
            modifier = copy.modifiers.new("Armature", "ARMATURE")
            modifier.object = rig
        _select_only([rig] + temporary)
        bpy.ops.export_scene.fbx(filepath=path, object_types={"ARMATURE", "MESH"}, bake_anim=False, **_fbx_settings())
    finally:
        _object_mode()
        _discard(temporary + ([rig] if rig else []))
        armature.name = source_name
        for mesh, name in mesh_names:
            mesh.name = name
        armature.data.pose_position = previous_pose


def _basis(pose_bone):
    """The bone's pose relative to its rest pose and parent, constraints included."""
    rest = pose_bone.bone.matrix_local
    if pose_bone.parent:
        rest_local = pose_bone.parent.bone.matrix_local.inverted() @ rest
        pose_local = pose_bone.parent.matrix.inverted() @ pose_bone.matrix
        return rest_local.inverted() @ pose_local
    return rest.inverted() @ pose_bone.matrix


def export_action(path, armature, action, frame_start=None, frame_end=None):
    """One action on the bare armature, sampled on every frame of [frame_start, frame_end]."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene = bpy.context.scene
    set_scene_fps(scene)
    _object_mode()
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    # Blender 4.4+ binds animation through action slots; pick the first one.
    if hasattr(armature.animation_data, "action_slot") and len(getattr(action, "slots", [])):
        armature.animation_data.action_slot = action.slots[0]
    start = int(action.frame_range[0]) if frame_start is None else int(frame_start)
    end = int(action.frame_range[1]) if frame_end is None else int(frame_end)
    armature.data.pose_position = "POSE"

    rig, source_name = _scaled_armature_copy(armature)
    baked = bpy.data.actions.new(action.name + "__cm")
    try:
        rig.animation_data_create()
        rig.animation_data.action = baked
        previous = {}
        for frame in range(start, end + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            for source in armature.pose.bones:
                target = rig.pose.bones[source.name]
                location, rotation, _scale = _basis(source).decompose()
                last = previous.get(source.name)
                if last is not None and last.dot(rotation) < 0.0:
                    rotation.negate()            # stay on one side of the quaternion sphere
                previous[source.name] = rotation.copy()
                target.location = location * CM
                target.rotation_quaternion = rotation
                target.keyframe_insert("location", frame=frame)
                target.keyframe_insert("rotation_quaternion", frame=frame)
        if hasattr(rig.animation_data, "action_slot") and len(getattr(baked, "slots", [])):
            rig.animation_data.action_slot = baked.slots[0]
        scene.frame_start, scene.frame_end = start, end
        scene.frame_set(start)
        _select_only([rig])
        bpy.ops.export_scene.fbx(
            filepath=path,
            object_types={"ARMATURE"},
            bake_anim=True,
            bake_anim_use_all_bones=True,
            bake_anim_use_nla_strips=False,
            bake_anim_use_all_actions=False,
            bake_anim_force_startend_keying=True,
            bake_anim_step=1.0,
            bake_anim_simplify_factor=0.0,
            **_fbx_settings(),
        )
    finally:
        _object_mode()
        _discard([rig])
        bpy.data.actions.remove(baked)
        armature.name = source_name
        bpy.context.view_layer.objects.active = armature


def export_static_mesh(path, objects):
    """Static geometry. Each object keeps its own origin as the pivot (rotation and scale are baked)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _object_mode()
    bpy.context.view_layer.update()
    temporary = []
    names = [(obj, obj.name) for obj in objects]
    try:
        for obj, name in names:
            obj.name = name + _SOURCE_SUFFIX
            location = obj.matrix_world.to_translation()
            linear = obj.matrix_world.to_3x3().to_4x4()        # rotation and scale, baked into the data
            copy = _baked_mesh_copy(obj, name, Matrix.Scale(CM, 4) @ linear)
            copy.location = location * CM
            temporary.append(copy)
        _select_only(temporary)
        bpy.ops.export_scene.fbx(filepath=path, object_types={"MESH"}, bake_anim=False, **_fbx_settings())
    finally:
        _object_mode()
        _discard(temporary)
        for obj, name in names:
            obj.name = name
