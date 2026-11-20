"""Preview materials, one per engine slot. The engine replaces all of these by slot name."""
import bpy

from .assemble import SLOTS


def hex_rgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c)   # sRGB -> linear


# slot -> (colour, roughness, metallic). A believable two-colour team look.
SCHEMES = {
    "timber": {   # forest green / cream
        "Helmet": ("#1F6B3A", 0.22, 0.0), "HelmetStripe": ("#EFE6CC", 0.30, 0.0), "HelmetLogo": ("#F7F1DC", 0.35, 0.0),
        "Facemask": ("#D9D2BC", 0.35, 0.6), "Visor": ("#101418", 0.06, 0.0), "Strap": ("#DADAD4", 0.55, 0.0),
        "Skin": ("#8A5A3C", 0.55, 0.0), "Eyes": ("#120C0A", 0.42, 0.0),
        "Jersey": ("#1F6B3A", 0.72, 0.0), "JerseyTrim": ("#EFE6CC", 0.70, 0.0),
        "Pants": ("#EFE6CC", 0.68, 0.0), "PantsStripe": ("#1F6B3A", 0.68, 0.0), "Belt": ("#2A2118", 0.50, 0.0),
        "Socks": ("#1F6B3A", 0.80, 0.0), "Shoes": ("#DCDCD6", 0.45, 0.0), "ShoeSole": ("#6B4423", 0.50, 0.0),
        "Gloves": ("#6B4423", 0.55, 0.0), "Bands": ("#DEDED8", 0.75, 0.0),
    },
    "ember": {    # crimson / charcoal
        "Helmet": ("#26262B", 0.20, 0.0), "HelmetStripe": ("#B01228", 0.30, 0.0), "HelmetLogo": ("#FF8A1F", 0.35, 0.0),
        "Facemask": ("#B01228", 0.35, 0.3), "Visor": ("#0A0C10", 0.05, 0.0), "Strap": ("#F2F2EE", 0.55, 0.0),
        "Skin": ("#C68E6A", 0.55, 0.0), "Eyes": ("#140E0C", 0.42, 0.0),
        "Jersey": ("#B01228", 0.72, 0.0), "JerseyTrim": ("#26262B", 0.70, 0.0),
        "Pants": ("#26262B", 0.68, 0.0), "PantsStripe": ("#B01228", 0.68, 0.0), "Belt": ("#E8E8E4", 0.50, 0.0),
        "Socks": ("#26262B", 0.80, 0.0), "Shoes": ("#17171A", 0.40, 0.0), "ShoeSole": ("#FF8A1F", 0.50, 0.0),
        "Gloves": ("#F2F2EE", 0.55, 0.0), "Bands": ("#FF8A1F", 0.75, 0.0),
    },
    "glacier": {  # navy / ice blue, white helmet
        "Helmet": ("#F4F8FB", 0.20, 0.0), "HelmetStripe": ("#0F3470", 0.30, 0.0), "HelmetLogo": ("#8FE3FF", 0.35, 0.0),
        "Facemask": ("#0F3470", 0.35, 0.3), "Visor": ("#0B1626", 0.05, 0.0), "Strap": ("#F2F2EE", 0.55, 0.0),
        "Skin": ("#5E3A26", 0.55, 0.0), "Eyes": ("#0E0A08", 0.42, 0.0),
        "Jersey": ("#0F3470", 0.72, 0.0), "JerseyTrim": ("#8FE3FF", 0.70, 0.0),
        "Pants": ("#F4F8FB", 0.68, 0.0), "PantsStripe": ("#0F3470", 0.68, 0.0), "Belt": ("#0F3470", 0.50, 0.0),
        "Socks": ("#0F3470", 0.80, 0.0), "Shoes": ("#F4F8FB", 0.40, 0.0), "ShoeSole": ("#8FE3FF", 0.50, 0.0),
        "Gloves": ("#8FE3FF", 0.55, 0.0), "Bands": ("#F4F8FB", 0.75, 0.0),
    },
}


def principled(name, color, rough=0.6, metal=0.0, alpha=1.0):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF")
    if bsdf is None:
        tree.nodes.clear()
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Alpha"].default_value = alpha
    return mat


def make_materials(scheme="timber"):
    """slot name -> material named exactly after the slot."""
    table = SCHEMES[scheme]
    out = {}
    for slot in SLOTS:
        color, rough, metal = table[slot]
        mat = principled(slot, hex_rgb(color), rough, metal)
        if slot == "Visor":
            bsdf = mat.node_tree.nodes["Principled BSDF"]
            bsdf.inputs["Alpha"].default_value = 0.84
            mat.surface_render_method = "BLENDED"
            mat.use_transparency_overlap = False
            mat.use_backface_culling = True
        out[slot] = mat
    return out


def slot_of(mat):
    """Engine slot a material stands for (copies appended from other files get a .001 suffix)."""
    return mat.name.split(".")[0]


def recolor(scheme, obj=None):
    """Repaint the preview materials (all of them, or just the ones on `obj`)."""
    table = SCHEMES[scheme]
    mats = [s.material for s in obj.material_slots] if obj is not None else [bpy.data.materials.get(s) for s in SLOTS]
    for mat in mats:
        if mat is None or slot_of(mat) not in table:
            continue
        color, rough, metal = table[slot_of(mat)]
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*hex_rgb(color), 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
