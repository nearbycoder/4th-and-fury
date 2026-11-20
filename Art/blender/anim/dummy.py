"""Preview stand-ins: a chunky athlete mannequin, the football proxy and a checkered ground.

The mannequin is skinned rigidly (each part to one bone) and colour coded so a pose reads at
thumbnail size: LEFT limbs blue, RIGHT limbs orange, red facemask on the FRONT of a white helmet,
dark number plate on the front of the chest. Its volumes approximate a padded mid-size athlete,
which is what the ground-contact spheres in controls.py assume.
"""
import bmesh
import bpy
from mathutils import Vector

from furylib import rig as furyrig

COLORS = {
    "jersey": (0.74, 0.76, 0.80),
    "pants": (0.42, 0.44, 0.50),
    "left": (0.16, 0.40, 0.95),
    "left_dark": (0.08, 0.20, 0.55),
    "right": (1.00, 0.48, 0.10),
    "right_dark": (0.62, 0.26, 0.04),
    "helmet": (0.95, 0.95, 0.95),
    "mask": (0.90, 0.08, 0.06),
    "plate": (0.12, 0.13, 0.16),
    "skin": (0.80, 0.62, 0.50),
}


def material(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    tree = getattr(mat, "node_tree", None)
    if tree is not None:
        bsdf = tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*color, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.65
    return mat


class _Builder:
    def __init__(self):
        self.bm = bmesh.new()
        self.groups = []            # (bone, [vert indices])
        self.mats = []
        self.mat_index = {}
        self.rest = {}              # bone -> rest matrix (armature space)
        self.length = {}

    def mat(self, key):
        if key not in self.mat_index:
            self.mat_index[key] = len(self.mats)
            self.mats.append(material("Dummy_" + key, COLORS[key]))
        return self.mat_index[key]

    def hull(self, corners, bone, color):
        """A box from 8 corners ordered (bottom ring of 4, top ring of 4)."""
        verts = [self.bm.verts.new(c) for c in corners]
        faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        index = self.mat(color)
        for f in faces:
            face = self.bm.faces.new([verts[i] for i in f])
            face.material_index = index
        self.groups.append((bone, verts))

    def box(self, center, size, bone, color):
        c, h = Vector(center), Vector(size) * 0.5
        ring = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        corners = [c + Vector((sx * h.x, sy * h.y, -h.z)) for sx, sy in ring]
        corners += [c + Vector((sx * h.x, sy * h.y, h.z)) for sx, sy in ring]
        self.hull(corners, bone, color)

    def limb(self, bone, start, end, color, t0=0.0, t1=1.0):
        """Tapered box along a bone. start/end = (size along local X, size along local Z)."""
        rest = self.rest[bone]
        x, y, z = (rest.col[i].to_3d() for i in range(3))
        head = rest.translation
        length = self.length[bone]
        a, b = head + y * (length * t0), head + y * (length * t1)
        ring = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        corners = [a + x * (sx * start[0] * 0.5) + z * (sz * start[1] * 0.5) for sx, sz in ring]
        corners += [b + x * (sx * end[0] * 0.5) + z * (sz * end[1] * 0.5) for sx, sz in ring]
        self.hull(corners, bone, color)

    def sphere(self, center, radius, bone, color, scale=(1.0, 1.0, 1.0)):
        made = bmesh.ops.create_uvsphere(self.bm, u_segments=16, v_segments=10, radius=radius)
        verts = made["verts"]
        index = self.mat(color)
        for v in verts:
            v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])) + Vector(center)
        for f in {f for v in verts for f in v.link_faces}:
            f.material_index = index
        self.groups.append((bone, verts))


def build_dummy(armature, name="SK_AnimDummy"):
    """Create the mannequin, skin it to `armature` and return the mesh object."""
    b = _Builder()
    for bone in armature.data.bones:
        b.rest[bone.name] = bone.matrix_local.copy()
        b.length[bone.name] = bone.length

    # torso
    b.box((0.0, 0.005, 0.975), (0.33, 0.21, 0.21), "pelvis", "pants")
    b.box((0.0, 0.0, 1.14), (0.30, 0.20, 0.13), "spine_01", "jersey")
    b.box((0.0, 0.0, 1.27), (0.33, 0.22, 0.15), "spine_02", "jersey")
    b.box((0.0, 0.0, 1.42), (0.38, 0.25, 0.20), "spine_03", "jersey")
    b.box((0.0, -0.128, 1.40), (0.17, 0.012, 0.15), "spine_03", "plate")
    b.box((0.0, 0.0, 1.57), (0.11, 0.11, 0.12), "neck_01", "skin")
    b.sphere((0.0, -0.01, 1.735), 0.125, "head", "helmet")
    b.box((0.0, -0.125, 1.70), (0.14, 0.07, 0.09), "head", "mask")

    for suf, col, dark in (("_l", "left", "left_dark"), ("_r", "right", "right_dark")):
        s = 1.0 if suf == "_l" else -1.0
        b.box((0.155 * s, 0.0, 1.497), (0.19, 0.23, 0.10), "clavicle" + suf, "jersey")
        b.limb("upperarm" + suf, (0.105, 0.105), (0.085, 0.085), col)
        b.limb("lowerarm" + suf, (0.085, 0.085), (0.062, 0.066), col)
        b.limb("hand" + suf, (0.034, 0.080), (0.030, 0.084), dark)
        b.limb("fingers" + suf, (0.028, 0.080), (0.016, 0.066), dark)
        b.limb("thumb" + suf, (0.024, 0.024), (0.018, 0.018), dark)
        b.limb("thigh" + suf, (0.165, 0.165), (0.115, 0.115), col)
        b.limb("calf" + suf, (0.115, 0.115), (0.075, 0.080), col)
        x0, x1 = 0.105 * s - 0.046, 0.105 * s + 0.046
        # foot: heel to ball, sole on the ground
        b.hull([Vector((x0, 0.075, 0.0)), Vector((x1, 0.075, 0.0)), Vector((x1, -0.13, 0.0)), Vector((x0, -0.13, 0.0)),
                Vector((x0, 0.065, 0.105)), Vector((x1, 0.065, 0.105)), Vector((x1, -0.13, 0.055)), Vector((x0, -0.13, 0.055))],
               "foot" + suf, dark)
        b.hull([Vector((x0, -0.13, 0.0)), Vector((x1, -0.13, 0.0)), Vector((x1, -0.215, 0.0)), Vector((x0, -0.215, 0.0)),
                Vector((x0, -0.13, 0.055)), Vector((x1, -0.13, 0.055)), Vector((x1, -0.215, 0.032)), Vector((x0, -0.215, 0.032))],
               "ball" + suf, dark)

    bm = b.bm
    bm.verts.index_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    index_groups = [(bone, [v.index for v in verts]) for bone, verts in b.groups]
    bm.to_mesh(mesh)
    bm.free()
    for mat in b.mats:
        mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for bone, indices in index_groups:
        group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
        group.add(indices, 1.0, "REPLACE")
    furyrig.skin_to_armature(obj, armature)
    return obj


def build_ball(name="PreviewBall"):
    """Football proxy: prolate spheroid 0.28 m long (local Y), 0.17 m thick, with stripes and laces."""
    bm = bmesh.new()
    made = bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=14, radius=1.0)
    for v in made["verts"]:
        # the UV sphere's poles are on Z: turn them onto Y, then squash
        v.co = Vector((v.co.x * 0.085, v.co.z * 0.14, v.co.y * 0.085))
    leather = material("Ball_leather", (0.45, 0.20, 0.08))
    white = material("Ball_white", (0.95, 0.95, 0.90))
    for f in bm.faces:
        y = abs(f.calc_center_median().y)
        f.material_index = 1 if 0.078 < y < 0.100 else 0
    # laces on local +Z
    ring = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    verts = [bm.verts.new((sx * 0.012, sy * 0.05, 0.080)) for sx, sy in ring]
    verts += [bm.verts.new((sx * 0.012, sy * 0.05, 0.092)) for sx, sy in ring]
    for f in [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]:
        bm.faces.new([verts[i] for i in f]).material_index = 1
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(leather)
    mesh.materials.append(white)
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build_ground(name="PreviewField", half=12.0, cell=0.5):
    """Checkered ground at z = 0 with a marker at the root (origin) pointing to the front (-Y)."""
    bm = bmesh.new()
    a = material("Field_a", (0.165, 0.30, 0.19))
    c = material("Field_b", (0.19, 0.335, 0.215))
    mark = material("Field_mark", (0.95, 0.95, 0.30))
    n = int(round(half / cell))
    for i in range(-n, n):
        for j in range(-n, n):
            x0, y0 = i * cell, j * cell
            face = bm.faces.new([bm.verts.new((x0, y0, 0.0)), bm.verts.new((x0 + cell, y0, 0.0)),
                                 bm.verts.new((x0 + cell, y0 + cell, 0.0)), bm.verts.new((x0, y0 + cell, 0.0))])
            face.material_index = (i + j) % 2
    z = 0.002
    for pts in ([(-0.16, -0.012), (0.16, -0.012), (0.16, 0.012), (-0.16, 0.012)],
                [(-0.012, -0.30), (0.012, -0.30), (0.012, 0.16), (-0.012, 0.16)],
                [(-0.05, -0.30), (0.0, -0.38), (0.05, -0.30), (0.0, -0.31)]):
        bm.faces.new([bm.verts.new((x, y, z)) for x, y in pts]).material_index = 2
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for m in (a, c, mark):
        mesh.materials.append(m)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj
