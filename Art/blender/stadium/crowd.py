"""Low-poly spectators (SM_CrowdA/B/C), the seat file crowd.bin, and preview instancing.

Figures face -Y with their origin on the tread. A seated figure has its own chair.
Both soles and the chair base share the same ground plane on every tier.

Vertex colour attribute `Col` is a mask: red = shirt, green = skin, blue = hair/hat,
black = trousers and shoes.
"""
import math
import struct

import bpy
import numpy as np
from mathutils import Vector

from .meshkit import MeshBuilder

SHIRT = (1.0, 0.0, 0.0, 1.0)
SKIN = (0.0, 1.0, 0.0, 1.0)
HAIR = (0.0, 0.0, 1.0, 1.0)
DARK = (0.0, 0.0, 0.0, 1.0)


def limb(mb, pts, sizes, cols, ref=(0.0, 1.0, 0.0), tans=None, cap0=None, cap1=None):
    """Four-sided tapering limb through `pts`. sizes[i] = (a, b) half extents of ring i: with the
    default ref and a vertical limb, a is the half width (X) and b the half depth (Y), and the
    four sides are [front (-Y), one side, back, other side]. cols[i] colours segment i: one
    colour, or four (one per side)."""
    n = len(pts)
    rings = []
    for i in range(n):
        p = Vector(pts[i])
        if tans and tans[i] is not None:
            t = Vector(tans[i])
        elif i == 0:
            t = Vector(pts[1]) - p
        elif i == n - 1:
            t = p - Vector(pts[i - 1])
        else:
            t = (Vector(pts[i + 1]) - p).normalized() + (p - Vector(pts[i - 1])).normalized()
        t.normalize()
        u = t.cross(Vector(ref))
        u.normalize()
        w = t.cross(u)
        a, b = sizes[i]
        rings.append([tuple(p + u * a + w * b), tuple(p - u * a + w * b),
                      tuple(p - u * a - w * b), tuple(p + u * a - w * b)])
    for i in range(n - 1):
        c = cols[i]
        for k in range(4):
            k2 = (k + 1) % 4
            ck = c[k] if isinstance(c[0], (tuple, list)) else c
            mb.face((rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]), "Crowd", None, True, col=ck)
    if cap0:
        mb.face(rings[0][::-1], "Crowd", None, True, col=cap0)
    if cap1:
        mb.face(rings[-1], "Crowd", None, True, col=cap1)


def _head(mb, x, y, z):
    """Neck and head with a hair cap; (x, y, z) is the base of the neck."""
    limb(mb, [(x, y, z - 0.02), (x, y - 0.005, z + 0.07)], [(0.05, 0.05), (0.048, 0.05)], [SKIN])
    hy = y - 0.012
    limb(mb,
         [(x, hy, z + 0.06), (x, hy, z + 0.165), (x, hy, z + 0.25), (x, hy, z + 0.31)],
         [(0.066, 0.078), (0.086, 0.098), (0.084, 0.096), (0.062, 0.072)],
         [(SKIN, SKIN, HAIR, SKIN), (SKIN, HAIR, HAIR, HAIR), HAIR], cap1=HAIR)


def _torso(mb, pts, lean_sizes=None):
    sizes = lean_sizes or [(0.172, 0.105), (0.155, 0.095), (0.20, 0.115), (0.185, 0.088)]
    limb(mb, pts, sizes, [SHIRT, SHIRT, SHIRT], cap0=DARK, cap1=SHIRT,
         tans=[(0, 0, 1)] * 4)


def _arm(mb, sx, shoulder, elbow, hand, ref=(0.0, 1.0, 0.0)):
    def m(p):
        return (sx * p[0], p[1], p[2])
    limb(mb, [m(shoulder), m(elbow), m(hand)], [(0.052, 0.056), (0.042, 0.046), (0.036, 0.042)],
         [SHIRT, SKIN], ref=ref, cap0=SHIRT, cap1=SKIN)


def figure_standing(arms_up=False):
    mb = MeshBuilder(uv_scale=1.0)
    for sx in (-1, 1):
        x = sx * 0.092
        limb(mb, [(x, 0.0, 0.90), (x, 0.005, 0.085), (x, -0.045, 0.0)],
             [(0.085, 0.09), (0.052, 0.058), (0.055, 0.115)], [DARK, DARK],
             tans=[(0, 0, -1)] * 3, cap1=DARK)
    _torso(mb, [(0, 0.0, 0.86), (0, 0.0, 1.07), (0, -0.01, 1.32), (0, -0.01, 1.435)])
    _head(mb, 0.0, -0.01, 1.435)
    for sx in (-1, 1):
        if arms_up:
            _arm(mb, sx, (0.222, -0.01, 1.385), (0.345, -0.03, 1.60), (0.385, -0.06, 1.90))
        else:
            _arm(mb, sx, (0.228, -0.01, 1.385), (0.262, -0.02, 1.11), (0.25, -0.085, 0.84))
    return mb


def figure_seated():
    mb = MeshBuilder(uv_scale=1.0)
    # The seat pan and both soles sit over one tread at any deck pitch.
    with mb.at(y=0.33, z=0.44):
        seated_body(mb)
    mb.box((-0.185, 0.09, 0.39), (0.185, 0.44, 0.45), "Crowd")
    mb.box((-0.065, 0.22, 0.0), (0.065, 0.33, 0.39), "Crowd")
    return mb


def seated_body(mb):
    for sx in (-1, 1):
        x = sx * 0.098
        limb(mb,
             [(x, 0.03, 0.088), (sx * 0.108, -0.43, 0.092), (sx * 0.108, -0.415, -0.35), (sx * 0.108, -0.46, -0.44)],
             [(0.078, 0.082), (0.068, 0.066), (0.052, 0.05), (0.115, 0.055)],
             [DARK, DARK, DARK], ref=(1.0, 0.0, 0.0),
             tans=[(0, -1, 0), (0, -0.7, -0.7), (0, 0, -1), (0, 0, -1)], cap1=DARK)
    _torso(mb, [(0, 0.03, 0.02), (0, 0.015, 0.22), (0, -0.02, 0.46), (0, -0.03, 0.575)])
    _head(mb, 0.0, -0.04, 0.575)
    for sx in (-1, 1):
        _arm(mb, sx, (0.226, -0.03, 0.525), (0.25, -0.10, 0.27), (0.155, -0.34, 0.185), ref=(1.0, 0.0, 0.0))


FIGURES = {
    "SM_CrowdA": figure_seated,
    "SM_CrowdB": lambda: figure_standing(False),
    "SM_CrowdC": lambda: figure_standing(True),
}


# ---- crowd.bin ---------------------------------------------------------------------------------
def write_bin(path, seats):
    """int32 count, then count x (x, y, z, yaw, section) float32, little-endian."""
    arr = np.asarray(seats, dtype="<f4").reshape(-1, 5)
    with open(path, "wb") as f:
        f.write(struct.pack("<i", len(arr)))
        f.write(arr.tobytes())
    return len(arr)


def read_bin(path):
    with open(path, "rb") as f:
        (n,) = struct.unpack("<i", f.read(4))
        arr = np.frombuffer(f.read(n * 20), dtype="<f4").reshape(n, 5)
    return arr


# ---- preview instancing ------------------------------------------------------------------------
def crowd_material(name="PV_Crowd"):
    """Shirt = object colour, skin and hair vary per object; all selected by the Col mask."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.85
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Col"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    info = nt.nodes.new("ShaderNodeObjectInfo")
    skin = nt.nodes.new("ShaderNodeValToRGB")
    skin.color_ramp.elements[0].color = (0.16, 0.075, 0.04, 1)
    skin.color_ramp.elements[1].color = (0.80, 0.52, 0.38, 1)
    hair = nt.nodes.new("ShaderNodeValToRGB")
    hair.color_ramp.elements[0].color = (0.012, 0.01, 0.008, 1)
    hair.color_ramp.elements[1].color = (0.42, 0.26, 0.10, 1)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 7.31
    frac = nt.nodes.new("ShaderNodeMath")
    frac.operation = "FRACT"
    nt.links.new(attr.outputs["Color"], sep.inputs["Color"])
    nt.links.new(info.outputs["Random"], skin.inputs["Fac"])
    nt.links.new(info.outputs["Random"], mul.inputs[0])
    nt.links.new(mul.outputs[0], frac.inputs[0])
    nt.links.new(frac.outputs[0], hair.inputs["Fac"])

    def mix(fac, a, b):
        node = nt.nodes.new("ShaderNodeMix")
        node.data_type = "RGBA"
        nt.links.new(fac, node.inputs["Factor"])
        if isinstance(a, tuple):
            node.inputs["A"].default_value = a
        else:
            nt.links.new(a, node.inputs["A"])
        nt.links.new(b, node.inputs["B"])
        return node.outputs["Result"]

    c = mix(sep.outputs["Red"], (0.03, 0.035, 0.05, 1.0), info.outputs["Color"])
    c = mix(sep.outputs["Green"], c, skin.outputs["Color"])
    c = mix(sep.outputs["Blue"], c, hair.outputs["Color"])
    nt.links.new(c, bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


CASUAL = [(0.85, 0.85, 0.82), (0.55, 0.56, 0.58), (0.06, 0.06, 0.07), (0.75, 0.62, 0.2),
          (0.2, 0.42, 0.2), (0.7, 0.45, 0.25), (0.35, 0.2, 0.45), (0.9, 0.75, 0.75)]


def instance_crowd(seats, meshes, team_a, team_b, fill=0.93, seed=7, collection=None, where=None,
                   mix=(0.5, 0.32, 0.18)):
    """Link one object per occupied seat (shared mesh data, so it renders as instances).

    seats   (n, 5) array as stored in crowd.bin
    meshes  [seated, standing, arms-up] mesh datablocks
    where   optional predicate(x, y, z) limiting which seats are filled
    """
    rng = np.random.default_rng(seed)
    coll = collection or bpy.data.collections.new("PV_Crowd")
    if coll.name not in bpy.context.scene.collection.children:
        try:
            bpy.context.scene.collection.children.link(coll)
        except RuntimeError:
            pass
    n = len(seats)
    occupied = rng.random(n) < fill
    kind = rng.choice(3, size=n, p=list(mix))
    fan = rng.random(n) < 0.62
    casual = rng.integers(0, len(CASUAL), size=n)
    jitter = rng.normal(0.0, 0.06, size=(n, 3))
    yawj = rng.normal(0.0, 0.10, size=n)
    count = 0
    for i in range(n):
        if not occupied[i]:
            continue
        x, y, z, yaw, section = (float(v) for v in seats[i])
        if where is not None and not where(x, y, z):
            continue
        obj = bpy.data.objects.new("PV_Fan", meshes[int(kind[i])])
        obj.location = (x, y, z)
        obj.rotation_euler = (0.0, 0.0, yaw + float(yawj[i]))
        s = 1.0 + float(jitter[i, 0]) * 0.6
        obj.scale = (s, s, s)
        base = (team_a if section < 0.5 else team_b) if fan[i] else CASUAL[int(casual[i])]
        col = [min(1.0, max(0.0, base[k] * (1.0 + float(jitter[i, k])))) for k in range(3)]
        obj.color = (col[0], col[1], col[2], 1.0)
        coll.objects.link(obj)
        count += 1
    return coll, count
