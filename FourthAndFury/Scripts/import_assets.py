"""Imports everything the art and audio scripts produce into the Unreal project, and builds the
materials the game uses.

Run through the editor's Python commandlet (see build.sh):

    UnrealEditor FourthAndFury.uproject -run=pythonscript -script="Scripts/import_assets.py [groups]"

Groups (default: every group whose source files exist):
    textures characters anims stadium audio materials data test
"""
import json
import os
import shutil
import sys

import unreal

PROJECT = os.path.normpath(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
REPO = os.path.dirname(PROJECT)
ART = os.path.join(REPO, "Art", "export")
AUDIO = os.path.join(PROJECT, "AudioSource")
DATA = os.path.join(PROJECT, "Content", "Data")
ROOT = "/Game/Fury"

tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary

# The classic FBX importer is predictable and scriptable; route FBX files to it instead of Interchange.
unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX 0")


def log(msg):
    unreal.log("FURY_IMPORT " + msg)


def listing(folder, suffix):
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder) if f.lower().endswith(suffix))


# ---------------------------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------------------------

def _task(filename, dest_path, dest_name, options=None):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filename)
    task.set_editor_property("destination_path", dest_path)
    task.set_editor_property("destination_name", dest_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("replace_existing_settings", True)
    task.set_editor_property("save", True)
    if options is not None:
        task.set_editor_property("options", options)
    return task


def _run(tasks):
    if tasks:
        tools.import_asset_tasks(tasks)
    paths = []
    for task in tasks:
        paths.extend(task.get_editor_property("imported_object_paths"))
    return paths


def _fresh(dest_path, name):
    """Importing over an existing asset re-uses its old settings, so start clean."""
    full = "%s/%s" % (dest_path, name)
    if eal.does_asset_exist(full):
        eal.delete_asset(full)


def _common(data):
    # The exporter writes centimetres with no scale left on any node (see Art/blender/furylib/export.py).
    data.set_editor_property("convert_scene", True)
    data.set_editor_property("force_front_x_axis", False)
    data.set_editor_property("convert_scene_unit", False)


def import_skeletal_mesh(fbx, dest_path, name, skeleton=None):
    ui = unreal.FbxImportUI()
    ui.set_editor_property("import_mesh", True)
    ui.set_editor_property("import_as_skeletal", True)
    ui.set_editor_property("import_animations", False)
    ui.set_editor_property("import_materials", False)
    ui.set_editor_property("import_textures", False)
    ui.set_editor_property("create_physics_asset", False)
    ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    ui.set_editor_property("automated_import_should_detect_type", False)
    if skeleton is not None:
        ui.set_editor_property("skeleton", skeleton)
    data = ui.get_editor_property("skeletal_mesh_import_data")
    data.set_editor_property("import_morph_targets", False)
    data.set_editor_property("update_skeleton_reference_pose", False)
    data.set_editor_property("use_t0_as_ref_pose", False)
    data.set_editor_property("preserve_smoothing_groups", True)
    data.set_editor_property("import_meshes_in_bone_hierarchy", True)
    data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    data.set_editor_property("normal_generation_method", unreal.FBXNormalGenerationMethod.MIKK_T_SPACE)
    _common(data)
    return _run([_task(fbx, dest_path, name, ui)])


def import_animation(fbx, dest_path, name, skeleton):
    ui = unreal.FbxImportUI()
    ui.set_editor_property("import_mesh", False)
    ui.set_editor_property("import_as_skeletal", False)
    ui.set_editor_property("import_animations", True)
    ui.set_editor_property("import_materials", False)
    ui.set_editor_property("import_textures", False)
    ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
    ui.set_editor_property("automated_import_should_detect_type", False)
    ui.set_editor_property("skeleton", skeleton)
    data = ui.get_editor_property("anim_sequence_import_data")
    data.set_editor_property("animation_length", unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    data.set_editor_property("import_bone_tracks", True)
    data.set_editor_property("remove_redundant_keys", False)
    data.set_editor_property("use_default_sample_rate", False)
    data.set_editor_property("custom_sample_rate", 30)
    data.set_editor_property("import_custom_attribute", False)
    _common(data)
    return _run([_task(fbx, dest_path, name, ui)])


def import_static_mesh(fbx, dest_path, name):
    ui = unreal.FbxImportUI()
    ui.set_editor_property("import_mesh", True)
    ui.set_editor_property("import_as_skeletal", False)
    ui.set_editor_property("import_animations", False)
    ui.set_editor_property("import_materials", False)
    ui.set_editor_property("import_textures", False)
    ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    ui.set_editor_property("automated_import_should_detect_type", False)
    data = ui.get_editor_property("static_mesh_import_data")
    data.set_editor_property("combine_meshes", True)
    data.set_editor_property("auto_generate_collision", False)
    data.set_editor_property("generate_lightmap_u_vs", False)
    data.set_editor_property("remove_degenerates", True)
    data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    data.set_editor_property("normal_generation_method", unreal.FBXNormalGenerationMethod.MIKK_T_SPACE)
    data.set_editor_property("vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
    _common(data)
    return _run([_task(fbx, dest_path, name, ui)])


def find_skeleton(mesh_path):
    mesh = unreal.load_asset(mesh_path)
    return mesh.get_editor_property("skeleton") if mesh else None


# ---------------------------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------------------------

def group_test():
    src = os.path.join(ART, "test")
    dest = ROOT + "/Test"
    _fresh(dest, "SK_Blockout")
    result = import_skeletal_mesh(os.path.join(src, "SK_Blockout.fbx"), dest, "SK_Blockout")
    log("mesh -> %s" % result)
    skeleton = find_skeleton(dest + "/SK_Blockout")
    for fbx in listing(src, ".fbx"):
        if fbx.startswith("A_"):
            _fresh(dest, os.path.splitext(fbx)[0])
            result = import_animation(os.path.join(src, fbx), dest, os.path.splitext(fbx)[0], skeleton)
            log("anim %s -> %s" % (fbx, result))


def group_characters():
    src = os.path.join(ART, "characters")
    dest = ROOT + "/Characters"
    # The mid build goes first and defines the shared skeleton; the others bind to it.
    names = [os.path.splitext(f)[0] for f in listing(src, ".fbx")]
    names.sort(key=lambda n: (n != "SK_Player_Mid", n))
    shared_path = dest + "/SK_Player_Mid_Skeleton"
    skeleton = unreal.load_asset(shared_path) if eal.does_asset_exist(shared_path) else None
    for name in names:
        _fresh(dest, name)
        result = import_skeletal_mesh(os.path.join(src, name + ".fbx"), dest, name, skeleton)
        log("character %s -> %s" % (name, result))
        mesh = unreal.load_asset(f"{dest}/{name}")
        editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
        if not mesh or not editor.regenerate_lod(mesh, 3):
            raise RuntimeError(f"Unable to build athlete LODs for {name}")
        eal.save_loaded_asset(mesh)
        if skeleton is None:
            skeleton = find_skeleton("%s/%s" % (dest, name))
    # FBX import can extend an existing skeleton without marking its own package dirty.
    if not skeleton or not eal.save_loaded_asset(skeleton, only_if_is_dirty=False):
        raise RuntimeError("Unable to save the shared athlete skeleton")
    log("skeleton -> %s" % skeleton.get_path_name())


def group_anims():
    src = os.path.join(ART, "anims")
    dest = ROOT + "/Anims"
    skeleton = find_skeleton(ROOT + "/Characters/SK_Player_Mid")
    if skeleton is None:
        log("ERROR: import the characters before the animations")
        return
    # A packaged game only carries compressed animation, so every clip needs its compression
    # settings; an unattended import can leave them empty.
    defaults = (("bone_compression_settings", "/Engine/Animation/DefaultAnimBoneCompressionSettings"),
                ("curve_compression_settings", "/Engine/Animation/DefaultAnimCurveCompressionSettings"),
                ("variable_frame_stripping_settings", "/Engine/Animation/DefaultVariableFrameStrippingSettings"))
    count = 0
    patched = 0
    for fbx in listing(src, ".fbx"):
        name = os.path.splitext(fbx)[0]
        _fresh(dest, name)
        result = import_animation(os.path.join(src, fbx), dest, name, skeleton)
        count += 1 if result else 0
        if not result:
            log("ERROR: animation %s did not import" % fbx)
            continue
        anim = unreal.load_asset("%s/%s" % (dest, name))
        changed = False
        for prop, path in defaults:
            if anim and anim.get_editor_property(prop) is None:
                anim.set_editor_property(prop, unreal.load_asset(path))
                changed = True
        if changed:
            patched += 1
            eal.save_asset("%s/%s" % (dest, name), only_if_is_dirty=False)
    log("animations imported: %d (%d given default compression settings)" % (count, patched))


def group_stadium():
    src = os.path.join(ART, "stadium")
    dest = ROOT + "/Stadium"
    for fbx in listing(src, ".fbx"):
        name = os.path.splitext(fbx)[0]
        _fresh(dest, name)
        result = import_static_mesh(os.path.join(src, fbx), dest, name)
        mesh = unreal.load_asset(f"{dest}/{name}")
        if not mesh:
            raise RuntimeError(f"Missing static mesh {name}")
        # Commandlets do not instantiate the static mesh editor subsystem. Its LOD
        # methods operate on the supplied mesh and also work on the class default object.
        editor = unreal.get_default_object(unreal.StaticMeshEditorSubsystem)
        # Crowd size on screen is tiny even from the near sideline camera.
        thresholds = (0.055, 0.016) if name.startswith("SM_Crowd") else (0.55, 0.20)
        levels = [(1.0, 1.0), (0.55, thresholds[0]), (0.26, thresholds[1])]
        options = unreal.StaticMeshReductionOptions()
        options.auto_compute_lod_screen_size = False
        options.reduction_settings = [unreal.StaticMeshReductionSettings(ratio, size) for ratio, size in levels]
        editor.set_lods(mesh, options)
        if editor.get_lod_count(mesh) != len(levels):
            raise RuntimeError(f"Incomplete LOD chain for {name}")
        eal.save_loaded_asset(mesh)
        log("static %s -> %s" % (name, result))


def texture_settings(name):
    """(sRGB, compression, lod group, mip generation) by naming convention."""
    C = unreal.TextureCompressionSettings
    G = unreal.TextureGroup
    M = unreal.TextureMipGenSettings
    if name.endswith("_N"):
        return False, C.TC_NORMALMAP, G.TEXTUREGROUP_WORLD_NORMAL_MAP, M.TMGS_FROM_TEXTURE_GROUP
    if name.endswith("_M") or name in ("T_Numbers", "T_FieldLines"):
        return False, C.TC_MASKS, G.TEXTUREGROUP_WORLD, M.TMGS_FROM_TEXTURE_GROUP
    if name.startswith(("T_Icon_", "T_Title")):
        return True, C.TC_EDITOR_ICON, G.TEXTUREGROUP_UI, M.TMGS_NO_MIPMAPS
    if name.startswith("T_Logo_"):
        # Emblems are drawn in the interface and painted on helmets and turf: keep mips, keep them crisp.
        return True, C.TC_BC7, G.TEXTUREGROUP_WORLD, M.TMGS_FROM_TEXTURE_GROUP
    return True, C.TC_DEFAULT, G.TEXTUREGROUP_WORLD, M.TMGS_FROM_TEXTURE_GROUP


def group_textures():
    src = os.path.join(ART, "textures")
    dest = ROOT + "/Textures"
    tasks = []
    for png in listing(src, ".png"):
        tasks.append(_task(os.path.join(src, png), dest, os.path.splitext(png)[0]))
    _run(tasks)
    for png in listing(src, ".png"):
        name = os.path.splitext(png)[0]
        tex = unreal.load_asset("%s/%s" % (dest, name))
        if tex is None:
            log("ERROR: texture %s did not import" % name)
            continue
        srgb, compression, group, mips = texture_settings(name)
        tex.set_editor_property("srgb", srgb)
        tex.set_editor_property("compression_settings", compression)
        tex.set_editor_property("lod_group", group)
        tex.set_editor_property("mip_gen_settings", mips)
        tex.set_editor_property("never_stream", True)
        eal.save_asset("%s/%s" % (dest, name), only_if_is_dirty=False)
    log("textures imported: %d" % len(tasks))


def group_audio():
    dest = ROOT + "/Audio"
    tasks = [_task(os.path.join(AUDIO, wav), dest, os.path.splitext(wav)[0]) for wav in listing(AUDIO, ".wav")]
    _run(tasks)
    # The audio scripts say which files are seamless loops; fall back on the names if the manifest is missing.
    looping = set()
    try:
        with open(os.path.join(AUDIO, "audio_manifest.json")) as handle:
            looping = set(entry["name"] for entry in json.load(handle)["files"] if entry.get("loops"))
    except (OSError, ValueError, KeyError):
        pass
    prefixes = ("AMB_Crowd", "AMB_Chant", "AMB_Night", "MUS_Menu", "MUS_PlaySelect", "MUS_Halftime", "SFX_FuryLoop", "SFX_BallAir", "SFX_Steps")
    loops = 0
    for wav in listing(AUDIO, ".wav"):
        name = os.path.splitext(wav)[0]
        if name in looping or (not looping and name.startswith(prefixes)):
            sound = unreal.load_asset("%s/%s" % (dest, name))
            if sound:
                sound.set_editor_property("looping", True)
                eal.save_asset("%s/%s" % (dest, name), only_if_is_dirty=False)
                loops += 1
    log("sounds imported: %d (%d looping)" % (len(tasks), loops))


def group_data():
    """Plain data files the game reads at run time."""
    os.makedirs(DATA, exist_ok=True)
    for src in (os.path.join(ART, "anims", "anims.json"), os.path.join(ART, "stadium", "crowd.bin"),
                os.path.join(ART, "stadium", "stadium_meta.json"), os.path.join(AUDIO, "audio_manifest.json")):
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(DATA, os.path.basename(src)))
            log("data %s" % os.path.basename(src))


# ---------------------------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------------------------

MAT = ROOT + "/Materials"
TEX = ROOT + "/Textures"
P = unreal.MaterialProperty
S = unreal.MaterialSamplerType
F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
F2 = unreal.CustomMaterialOutputType.CMOT_FLOAT2
F3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3


def new_material(name, **props):
    full = "%s/%s" % (MAT, name)
    if eal.does_asset_exist(full):
        eal.delete_asset(full)
    mat = tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())
    for key, value in props.items():
        mat.set_editor_property(key, value)
    return mat


def finish(mat, name):
    mel.recompile_material(mat)
    eal.save_asset("%s/%s" % (MAT, name), only_if_is_dirty=False)
    log("material %s" % name)


def node(mat, cls, x, y, **props):
    expr = mel.create_material_expression(mat, cls, x, y)
    for key, value in props.items():
        expr.set_editor_property(key, value)
    return expr


def link(a, pin_out, b, pin_in):
    if not mel.connect_material_expressions(a, pin_out, b, pin_in):
        log("ERROR: could not connect %s.%s -> %s.%s" % (a.get_name(), pin_out, b.get_name(), pin_in))


def to_output(a, pin, prop):
    if not mel.connect_material_property(a, pin, prop):
        log("ERROR: could not connect %s.%s -> %s" % (a.get_name(), pin, prop))


def scalar(mat, name, default, x, y):
    return node(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=default)


def vector(mat, name, rgb, x, y):
    return node(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name,
                default_value=unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))


def constant(mat, value, x, y):
    return node(mat, unreal.MaterialExpressionConstant, x, y, r=value)


def constant3(mat, rgb, x, y):
    return node(mat, unreal.MaterialExpressionConstant3Vector, x, y, constant=unreal.LinearColor(rgb[0], rgb[1], rgb[2], 0.0))


def texture(name):
    full = "%s/%s" % (TEX, name)
    return unreal.load_asset(full) if eal.does_asset_exist(full) else None


def sample(mat, tex_name, sampler, x, y, param=None):
    cls = unreal.MaterialExpressionTextureSampleParameter2D if param else unreal.MaterialExpressionTextureSample
    expr = node(mat, cls, x, y)
    tex = texture(tex_name)
    if tex is not None:
        expr.set_editor_property("texture", tex)
    else:
        log("WARNING: texture %s is missing (import textures first)" % tex_name)
    expr.set_editor_property("sampler_type", sampler)
    if param:
        expr.set_editor_property("parameter_name", param)
    return expr


def custom(mat, code, output, inputs, x, y, description):
    expr = node(mat, unreal.MaterialExpressionCustom, x, y)
    expr.set_editor_property("code", code.strip())
    expr.set_editor_property("output_type", output)
    expr.set_editor_property("description", description)
    pins = []
    for name in inputs:
        pin = unreal.CustomInput()
        pin.set_editor_property("input_name", name)
        pins.append(pin)
    expr.set_editor_property("inputs", pins)
    return expr


def lerp(mat, x, y, const_a=None, const_b=None):
    expr = node(mat, unreal.MaterialExpressionLinearInterpolate, x, y)
    if const_a is not None:
        expr.set_editor_property("const_a", const_a)
    if const_b is not None:
        expr.set_editor_property("const_b", const_b)
    return expr


def mul(mat, x, y):
    return node(mat, unreal.MaterialExpressionMultiply, x, y)


def uv(mat, x, y, index=0, tiling=1.0):
    return node(mat, unreal.MaterialExpressionTextureCoordinate, x, y, coordinate_index=index, u_tiling=tiling, v_tiling=tiling)


def mask(mat, source, x, y, channels):
    expr = node(mat, unreal.MaterialExpressionComponentMask, x, y, r="r" in channels, g="g" in channels, b="b" in channels, a="a" in channels)
    link(source, "", expr, "")
    return expr


def make_athlete():
    """Every surface of an athlete: a colour, optional jersey number, optional helmet emblem."""
    name = "M_Athlete"
    mat = new_material(name, used_with_skeletal_mesh=True)
    color = vector(mat, "Color", (0.5, 0.5, 0.5), -1400, -300)

    # Jersey number: NumberUV (channel 1) is 0..1 inside a number panel; T_Numbers is a 10 x 10 sheet
    # with number n in column n % 10, row n / 10, row 0 at the top.
    cell = custom(mat, """
float inside = step(0.0, UV.x) * step(UV.x, 1.0) * step(0.0, UV.y) * step(UV.y, 1.0);
float n = floor(Number + 0.5);
float2 cell = float2(fmod(n, 10.0), floor(n / 10.0));
return float3((cell + saturate(UV)) * 0.1, inside);
""", F3, ["UV", "Number"], -1950, 50, "NumberCell")
    link(uv(mat, -2200, 0, index=1), "", cell, "UV")
    link(scalar(mat, "Number", 7.0, -2200, 150), "", cell, "Number")
    digits = sample(mat, "T_Numbers", S.SAMPLERTYPE_MASKS, -1500, 0)
    link(mask(mat, cell, -1700, 0, "rg"), "", digits, "UVs")
    gate = mul(mat, -1250, 200)
    link(mask(mat, cell, -1700, 120, "b"), "", gate, "A")
    link(scalar(mat, "UseNumber", 0.0, -1500, 260), "", gate, "B")
    edge_amount = mul(mat, -1050, 60)
    link(digits, "G", edge_amount, "A")
    link(gate, "", edge_amount, "B")
    fill_amount = mul(mat, -1050, 180)
    link(digits, "R", fill_amount, "A")
    link(gate, "", fill_amount, "B")
    with_edge = lerp(mat, -800, -200)
    link(color, "", with_edge, "A")
    link(vector(mat, "NumberEdge", (0.0, 0.0, 0.0), -1050, -120), "", with_edge, "B")
    link(edge_amount, "", with_edge, "Alpha")
    with_fill = lerp(mat, -600, -100)
    link(with_edge, "", with_fill, "A")
    link(vector(mat, "NumberFill", (1.0, 1.0, 1.0), -1050, 320), "", with_fill, "B")
    link(fill_amount, "", with_fill, "Alpha")

    # Helmet emblem: an RGBA picture laid over the paint.
    logo = sample(mat, "T_Logo_sasquatch", S.SAMPLERTYPE_COLOR, -800, 250, param="Logo")
    logo_amount = mul(mat, -550, 400)
    link(logo, "A", logo_amount, "A")
    link(scalar(mat, "UseLogo", 0.0, -800, 500), "", logo_amount, "B")
    with_logo = lerp(mat, -350, -50)
    link(with_fill, "", with_logo, "A")
    link(logo, "RGB", with_logo, "B")
    link(logo_amount, "", with_logo, "Alpha")
    to_output(with_logo, "", P.MP_BASE_COLOR)
    to_output(scalar(mat, "Roughness", 0.6, -350, 150), "", P.MP_ROUGHNESS)
    to_output(scalar(mat, "Metallic", 0.0, -350, 250), "", P.MP_METALLIC)

    # Cloth weave: a tiling normal map, faded in by the Fabric parameter.
    weave = sample(mat, "T_Fabric_N", S.SAMPLERTYPE_NORMAL, -900, 700)
    link(uv(mat, -1150, 700, tiling=14.0), "", weave, "UVs")
    normal = lerp(mat, -600, 800)
    link(constant3(mat, (0.0, 0.0, 1.0), -900, 950), "", normal, "A")
    link(weave, "RGB", normal, "B")
    fabric = scalar(mat, "Fabric", 0.0, -900, 1100)
    link(fabric, "", normal, "Alpha")
    to_output(normal, "", P.MP_NORMAL)

    # The padded chest and tucked waistband stay pinned. Between them the folds
    # breathe outward in response to the same damped motion that drives the towel.
    spring = node(mat, unreal.MaterialExpressionScalarParameter, -1700, 1400,
                  parameter_name="ClothSpring", use_custom_primitive_data=True, primitive_data_index=0)
    folds = custom(mat, """
float waist = smoothstep(106.0, 110.5, Rest.z) * (1.0 - smoothstep(118.0, 124.0, Rest.z));
float ridge = 0.5 + 0.5*cos(1.48*(Rest.z + 0.16*Rest.x - 1.8*sin(0.13*Rest.y)));
return Outward * (waist * ridge * step(0.95, Fabric) * Spring);
""", F3, ["Rest", "Outward", "Fabric", "Spring"], -850, 1350, "LooseJersey")
    link(node(mat, unreal.MaterialExpressionPreSkinnedPosition, -1500, 1200), "", folds, "Rest")
    link(node(mat, unreal.MaterialExpressionVertexNormalWS, -1500, 1300), "", folds, "Outward")
    link(fabric, "", folds, "Fabric")
    link(spring, "", folds, "Spring")
    to_output(folds, "", P.MP_WORLD_POSITION_OFFSET)

    # Fury: the athlete smoulders - a hot rim around the silhouette, a faint ember everywhere else,
    # so the uniform still reads underneath.
    rim = node(mat, unreal.MaterialExpressionFresnel, -900, 450, exponent=3.6, base_reflect_fraction=0.025)
    heat = mul(mat, -650, 450)
    link(rim, "", heat, "A")
    link(scalar(mat, "Glow", 0.0, -900, 700), "", heat, "B")
    glow = mul(mat, -350, 450)
    link(vector(mat, "GlowColor", (1.0, 0.35, 0.05), -650, 620), "", glow, "A")
    link(heat, "", glow, "B")
    to_output(glow, "", P.MP_EMISSIVE_COLOR)
    finish(mat, name)


def make_surface():
    """General-purpose lit surface for the stadium and props: colour, detail normal, grime."""
    name = "M_Surface"
    mat = new_material(name, used_with_instanced_static_meshes=True)
    tiled = mul(mat, -1450, 0)
    link(uv(mat, -1700, -60), "", tiled, "A")
    link(scalar(mat, "Tiling", 1.0, -1700, 80), "", tiled, "B")
    grime = sample(mat, "T_Concrete_M", S.SAMPLERTYPE_MASKS, -1200, 0)
    link(tiled, "", grime, "UVs")
    shade = lerp(mat, -900, 0, const_a=1.0)
    link(grime, "R", shade, "B")
    link(scalar(mat, "Grime", 0.0, -1200, 220), "", shade, "Alpha")
    tinted = mul(mat, -650, -150)
    link(vector(mat, "Color", (0.4, 0.4, 0.4), -900, -200), "", tinted, "A")
    link(shade, "", tinted, "B")
    to_output(tinted, "", P.MP_BASE_COLOR)
    to_output(scalar(mat, "Roughness", 0.7, -650, 50), "", P.MP_ROUGHNESS)
    to_output(scalar(mat, "Metallic", 0.0, -650, 150), "", P.MP_METALLIC)
    detail = sample(mat, "T_Concrete_N", S.SAMPLERTYPE_NORMAL, -1200, 420, param="DetailNormal")
    link(tiled, "", detail, "UVs")
    normal = lerp(mat, -900, 500)
    link(constant3(mat, (0.0, 0.0, 1.0), -1200, 680), "", normal, "A")
    link(detail, "RGB", normal, "B")
    link(scalar(mat, "Detail", 0.0, -1200, 820), "", normal, "Alpha")
    to_output(normal, "", P.MP_NORMAL)
    glow = mul(mat, -650, 300)
    link(vector(mat, "GlowColor", (1.0, 1.0, 1.0), -900, 320), "", glow, "A")
    link(scalar(mat, "Glow", 0.0, -900, 480), "", glow, "B")
    to_output(glow, "", P.MP_EMISSIVE_COLOR)
    finish(mat, name)


def make_field():
    """The turf: painted field texture, team end zones and a midfield emblem, grass detail."""
    name = "M_Field"
    mat = new_material(name)
    field_uv = uv(mat, -2600, 0)
    field = sample(mat, "T_Field", S.SAMPLERTYPE_COLOR, -1700, -500)
    link(field_uv, "", field, "UVs")

    # The field texture covers 128 m x 64 m. End zones are 9.14 m deep and 48.77 m wide.
    # Each helper returns (u, v, inside) for one painted region.
    zone_code = """
float2 m = (UV - 0.5) * float2(128.0, 64.0);          // metres from midfield; +x right, +y toward the camera
float depth = (54.86 - abs(m.x)) / 9.14;              // 0 at the end line, 1 at the goal line
float across = (m.y * Side + 24.385) / 48.77;         // reads left to right for someone standing on the field
float inside = step(0.012, depth) * step(depth, 0.972) * step(0.004, across) * step(across, 0.996) * step(0.0, m.x * Side);
return float3(across, depth, inside);
"""
    left = custom(mat, zone_code, F3, ["UV", "Side"], -2200, -200, "LeftEndZone")
    link(field_uv, "", left, "UV")
    link(constant(mat, -1.0, -2400, -120), "", left, "Side")
    right = custom(mat, zone_code, F3, ["UV", "Side"], -2200, 100, "RightEndZone")
    link(field_uv, "", right, "UV")
    link(constant(mat, 1.0, -2400, 180), "", right, "Side")
    logo_zone = custom(mat, """
float2 m = (UV - 0.5) * float2(128.0, 64.0);
float2 p = m / Size + 0.5;
float inside = step(0.0, p.x) * step(p.x, 1.0) * step(0.0, p.y) * step(p.y, 1.0);
return float3(p, inside);
""", F3, ["UV", "Size"], -2200, 400, "MidfieldLogo")
    link(field_uv, "", logo_zone, "UV")
    link(scalar(mat, "LogoSize", 13.0, -2400, 480), "", logo_zone, "Size")

    paint, pin = field, "RGB"
    x = -1200
    for zone, tex_name, param, y, is_logo in ((left, "T_EndZone_sasquatch", "EndZoneLeft", -250, False),
                                              (right, "T_EndZone_volcanoes", "EndZoneRight", 50, False),
                                              (logo_zone, "T_Logo_sasquatch", "MidLogo", 350, True)):
        tex = sample(mat, tex_name, S.SAMPLERTYPE_COLOR, -1700, y, param=param)
        link(mask(mat, zone, -1950, y, "rg"), "", tex, "UVs")
        amount = mask(mat, zone, -1950, y + 110, "b")
        if is_logo:
            visible = mul(mat, -1450, y + 110)
            link(tex, "A", visible, "A")
            link(amount, "", visible, "B")
            faded = mul(mat, x - 150, y + 150)
            link(visible, "", faded, "A")
            link(scalar(mat, "LogoOpacity", 0.85, x - 400, y + 230), "", faded, "B")
            amount = faded
        blend = lerp(mat, x, y)
        link(paint, pin, blend, "A")
        link(tex, "RGB", blend, "B")
        link(amount, "", blend, "Alpha")
        paint, pin = blend, ""
        x += 250

    # Grass: clumpy brightness variation and a blade normal map, both tiled across the turf.
    clumps = sample(mat, "T_Grass_M", S.SAMPLERTYPE_MASKS, -1400, 760)
    link(uv(mat, -1700, 700, tiling=9.0), "", clumps, "UVs")
    variation = lerp(mat, -1100, 760, const_a=0.82, const_b=1.1)
    link(clumps, "R", variation, "Alpha")
    shaded = mul(mat, -400, 300)
    link(paint, pin, shaded, "A")
    link(variation, "", shaded, "B")
    # Under floodlights the painted turf reads too neon; pull it toward a deeper, calmer green.
    toned = custom(mat, """
float grey = dot(Color, float3(0.3, 0.59, 0.11));
return lerp(float3(grey, grey, grey), Color, Saturation) * Tint;
""", F3, ["Color", "Saturation", "Tint"], -150, 300, "TurfTone")
    link(shaded, "", toned, "Color")
    link(scalar(mat, "Saturation", 0.82, -400, 480), "", toned, "Saturation")
    link(vector(mat, "Tint", (0.62, 0.66, 0.62), -400, 620), "", toned, "Tint")
    to_output(toned, "", P.MP_BASE_COLOR)
    blades = sample(mat, "T_Grass_N", S.SAMPLERTYPE_NORMAL, -1400, 1000)
    link(uv(mat, -1700, 1000, tiling=48.0), "", blades, "UVs")
    to_output(blades, "RGB", P.MP_NORMAL)
    # Paint is a touch smoother than grass.
    lines = sample(mat, "T_FieldLines", S.SAMPLERTYPE_MASKS, -1400, 1300)
    link(field_uv, "", lines, "UVs")
    rough = lerp(mat, -1100, 1300, const_a=0.93, const_b=0.72)
    link(lines, "R", rough, "Alpha")
    to_output(rough, "", P.MP_ROUGHNESS)
    to_output(constant(mat, 0.25, -400, 600), "", P.MP_SPECULAR)
    finish(mat, name)


def make_crowd():
    """Instanced spectators: shirt colours picked per instance, and a bounce that grows with the noise."""
    name = "M_Crowd"
    mat = new_material(name, used_with_instanced_static_meshes=True)
    paint = node(mat, unreal.MaterialExpressionVertexColor, -1500, -200)
    rand = node(mat, unreal.MaterialExpressionPerInstanceRandom, -1900, 0)
    section = node(mat, unreal.MaterialExpressionPerInstanceCustomData, -1900, 120, data_index=0, const_default_value=0.0)
    shirt = custom(mat, """
// Most of a section wears its team's colour; the rest wear whatever they like.
float pick = frac(Rand * 7.31);
float3 team = Section > 0.5 ? Away : Home;
float3 other = Section > 0.5 ? Home : Away;
float3 neutral = lerp(float3(0.75, 0.75, 0.78), float3(0.07, 0.08, 0.1), step(0.5, frac(Rand * 23.7)));
float3 shirt = pick < 0.62 ? team : (pick < 0.72 ? other : neutral);
// A little brightness jitter so a block of fans is not one flat colour.
return shirt * lerp(0.7, 1.1, frac(Rand * 91.7));
""", F3, ["Rand", "Section", "Home", "Away"], -1500, 150, "ShirtColor")
    link(rand, "", shirt, "Rand")
    link(section, "", shirt, "Section")
    link(vector(mat, "HomeColor", (0.8, 0.1, 0.1), -1900, 260), "", shirt, "Home")
    link(vector(mat, "AwayColor", (0.1, 0.2, 0.8), -1900, 440), "", shirt, "Away")
    skin = custom(mat, """
return lerp(float3(0.75, 0.52, 0.38), float3(0.2, 0.11, 0.06), frac(Rand * 3.77));
""", F3, ["Rand"], -1500, 420, "SkinTone")
    link(rand, "", skin, "Rand")
    body = custom(mat, """
float3 hair = lerp(float3(0.03, 0.025, 0.02), float3(0.3, 0.2, 0.1), frac(Rand * 13.1));
float3 legs = float3(0.05, 0.06, 0.09);
float sum = saturate(Paint.r + Paint.g + Paint.b);
return Shirt * Paint.r + Skin * Paint.g + hair * Paint.b + legs * (1.0 - sum);
""", F3, ["Paint", "Shirt", "Skin", "Rand"], -1100, 100, "Dress")
    link(paint, "", body, "Paint")
    link(shirt, "", body, "Shirt")
    link(skin, "", body, "Skin")
    link(rand, "", body, "Rand")
    to_output(body, "", P.MP_BASE_COLOR)
    to_output(constant(mat, 0.85, -1100, 400), "", P.MP_ROUGHNESS)

    bounce = custom(mat, """
// Each fan hops on their own beat; louder moments mean bigger, faster hops and more people on their feet.
float phase = Rand * 6.2832;
float speed = lerp(3.0, 9.0, Excitement) * lerp(0.8, 1.2, frac(Rand * 5.3));
float hop = max(0.0, sin(Time * speed + phase));
float keen = step(1.0 - Excitement * 0.9, frac(Rand * 41.3));
return float3(0.0, 0.0, Motion * hop * hop * lerp(2.0, 26.0, Excitement) * lerp(0.25, 1.0, keen));
""", F3, ["Time", "Rand", "Excitement", "Motion"], -1500, 720, "Hop")
    link(node(mat, unreal.MaterialExpressionTime, -1900, 700), "", bounce, "Time")
    link(paint, "A", bounce, "Motion")
    link(rand, "", bounce, "Rand")
    link(scalar(mat, "Excitement", 0.2, -1900, 820), "", bounce, "Excitement")
    to_output(bounce, "", P.MP_WORLD_POSITION_OFFSET)
    finish(mat, name)


def make_glow():
    """Unlit, self-lit surfaces: lamps, the video boards, the sky."""
    name = "M_Glow"
    mat = new_material(name, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, two_sided=True)
    tex = sample(mat, "T_NightSky", S.SAMPLERTYPE_COLOR, -900, -100, param="Image")
    picture = lerp(mat, -600, 0)
    link(constant3(mat, (1.0, 1.0, 1.0), -900, 300), "", picture, "A")
    link(tex, "RGB", picture, "B")
    link(scalar(mat, "UseImage", 0.0, -900, 180), "", picture, "Alpha")
    tinted = mul(mat, -400, 0)
    link(picture, "", tinted, "A")
    link(vector(mat, "Color", (1.0, 1.0, 1.0), -650, 250), "", tinted, "B")
    bright = mul(mat, -200, 0)
    link(tinted, "", bright, "A")
    link(scalar(mat, "Brightness", 1.0, -450, 400), "", bright, "B")
    to_output(bright, "", P.MP_EMISSIVE_COLOR)
    finish(mat, name)


def make_sky():
    """The night sky dome: self-lit, and flagged as sky so the sky light can capture it."""
    name = "M_Sky"
    mat = new_material(name, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, two_sided=True, is_sky=True)
    tex = sample(mat, "T_NightSky", S.SAMPLERTYPE_COLOR, -700, 0)
    bright = mul(mat, -400, 0)
    link(tex, "RGB", bright, "A")
    link(scalar(mat, "Brightness", 1.0, -700, 250), "", bright, "B")
    to_output(bright, "", P.MP_EMISSIVE_COLOR)
    finish(mat, name)


def make_ads():
    """The ad boards: eight boards in one strip; U counts boards along the wall."""
    name = "M_Ads"
    mat = new_material(name)
    cell = custom(mat, """
float which = fmod(floor(UV.x) + 8000.0, 8.0);
return float2((which + frac(UV.x)) / 8.0, UV.y);
""", F2, ["UV"], -900, 0, "AdCell")
    link(uv(mat, -1150, 0), "", cell, "UV")
    tex = sample(mat, "T_Ads", S.SAMPLERTYPE_COLOR, -650, 0)
    link(cell, "", tex, "UVs")
    to_output(tex, "RGB", P.MP_BASE_COLOR)
    lit = mul(mat, -350, 150)
    link(tex, "RGB", lit, "A")
    link(scalar(mat, "Brightness", 0.6, -650, 300), "", lit, "B")
    to_output(lit, "", P.MP_EMISSIVE_COLOR)
    to_output(constant(mat, 0.55, -350, 300), "", P.MP_ROUGHNESS)
    finish(mat, name)


def make_marker():
    """Rings on the turf under human-controlled athletes: flat, see-through, self-lit."""
    name = "M_Marker"
    mat = new_material(name, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, blend_mode=unreal.BlendMode.BLEND_TRANSLUCENT, two_sided=True)
    shape = custom(mat, """
float r = length(UV * 2.0 - 1.0);
float ring = smoothstep(Inner - 0.04, Inner, r) * (1.0 - smoothstep(0.96, 1.0, r));
float disc = (1.0 - smoothstep(Inner - 0.06, Inner - 0.02, r)) * Fill;
return saturate(ring + disc);
""", F1, ["UV", "Inner", "Fill"], -700, 0, "Ring")
    link(uv(mat, -950, 0), "", shape, "UV")
    link(scalar(mat, "Inner", 0.72, -950, 120), "", shape, "Inner")
    link(scalar(mat, "Fill", 0.18, -950, 240), "", shape, "Fill")
    bright = mul(mat, -400, -150)
    link(vector(mat, "Color", (1.0, 0.8, 0.1), -700, -200), "", bright, "A")
    link(scalar(mat, "Brightness", 2.0, -700, -330), "", bright, "B")
    to_output(bright, "", P.MP_EMISSIVE_COLOR)
    alpha = mul(mat, -400, 60)
    link(shape, "", alpha, "A")
    link(scalar(mat, "Opacity", 0.9, -700, 200), "", alpha, "B")
    to_output(alpha, "", P.MP_OPACITY)
    finish(mat, name)


def make_particle():
    """Additive soft sprites drawn as instanced quads; colour and fade come from per-instance data."""
    name = "M_Particle"
    mat = new_material(name, shading_model=unreal.MaterialShadingModel.MSM_UNLIT, blend_mode=unreal.BlendMode.BLEND_ADDITIVE,
                       two_sided=True, used_with_instanced_static_meshes=True)
    rgb = node(mat, unreal.MaterialExpressionPerInstanceCustomData3Vector, -900, -100, data_index=0,
               const_default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
    strength = node(mat, unreal.MaterialExpressionPerInstanceCustomData, -900, 120, data_index=3, const_default_value=1.0)
    soft = custom(mat, """
return pow(saturate(1.0 - length(UV * 2.0 - 1.0)), 1.8);
""", F1, ["UV"], -900, 300, "SoftDisc")
    link(uv(mat, -1150, 300), "", soft, "UV")
    lit = mul(mat, -600, 0)
    link(rgb, "", lit, "A")
    link(strength, "", lit, "B")
    shaped = mul(mat, -350, 100)
    link(lit, "", shaped, "A")
    link(soft, "", shaped, "B")
    to_output(shaped, "", P.MP_EMISSIVE_COLOR)
    finish(mat, name)


def make_contact_shadow():
    name = "M_ContactShadow"
    mat = new_material(name, shading_model=unreal.MaterialShadingModel.MSM_UNLIT,
                       blend_mode=unreal.BlendMode.BLEND_TRANSLUCENT, used_with_instanced_static_meshes=True)
    soft = custom(mat, """
float2 p = UV * 2.0 - 1.0;
float falloff = saturate(1.0 - dot(p, p));
return falloff * falloff * Gain;
""", F1, ["UV", "Gain"], -400, 160, "Ground contact")
    link(uv(mat, -750, 100), "", soft, "UV")
    gain = node(mat, unreal.MaterialExpressionPerInstanceCustomData, -750, 230, data_index=0, const_default_value=0.4)
    link(gain, "", soft, "Gain")
    to_output(soft, "", P.MP_OPACITY)
    finish(mat, name)


def group_materials():
    make_athlete()
    make_surface()
    make_field()
    make_crowd()
    make_glow()
    make_sky()
    if texture("T_Ads") is not None:
        make_ads()
    make_marker()
    make_contact_shadow()
    make_particle()


GROUPS = [
    ("textures", group_textures, lambda: listing(os.path.join(ART, "textures"), ".png")),
    ("characters", group_characters, lambda: listing(os.path.join(ART, "characters"), ".fbx")),
    ("anims", group_anims, lambda: listing(os.path.join(ART, "anims"), ".fbx")),
    ("stadium", group_stadium, lambda: listing(os.path.join(ART, "stadium"), ".fbx")),
    ("audio", group_audio, lambda: listing(AUDIO, ".wav")),
    ("materials", group_materials, lambda: listing(os.path.join(ART, "textures"), ".png")),
    ("data", group_data, lambda: True),
    ("test", group_test, lambda: False),
]


def main():
    known = [name for name, _, _ in GROUPS]
    wanted = [a for a in sys.argv[1:] if a in known]
    for name, run, available in GROUPS:
        if (wanted and name in wanted) or (not wanted and available()):
            log("=== %s ===" % name)
            run()
    # Imports create side assets (skeletons) that the import tasks do not save themselves.
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    log("DONE")


main()
