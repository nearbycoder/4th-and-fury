"""A small polygon-soup mesh builder.

Geometry is appended face by face (each face carries its own corner positions, a material name,
optional UVs and a smooth flag); `to_object` welds coincident corners, box-projects any face that
has no explicit UVs and creates the Blender mesh.

Conventions
-----------
* Faces are wound counter-clockwise seen from the side they should be visible from.
* A transform stack (`with mb.transform(matrix):`) places primitives; a mirroring matrix flips the
  winding automatically so normals stay outward.
* Box projection: 1 UV unit = `1 / uv_scale` metres (0.25 -> 4 m).
"""
import math
from contextlib import contextmanager

import bpy
import numpy as np
from mathutils import Matrix, Vector


# --------------------------------------------------------------------------------------------
# 2D helpers
# --------------------------------------------------------------------------------------------
def polygon_area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return 0.5 * a


def triangulate(pts):
    """Ear-clip a simple 2D polygon. Returns index triples wound like the input."""
    n = len(pts)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]
    ccw = polygon_area(pts) > 0
    idx = list(range(n))
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        clipped = False
        m = len(idx)
        for k in range(m):
            i0, i1, i2 = idx[(k - 1) % m], idx[k], idx[(k + 1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            cr = cross(a, b, c)
            if (cr <= 1e-12) if ccw else (cr >= -1e-12):
                continue                                   # reflex or degenerate corner
            ear = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = pts[j]
                d0, d1, d2 = cross(a, b, p), cross(b, c, p), cross(c, a, p)
                if ccw:
                    inside = d0 >= -1e-12 and d1 >= -1e-12 and d2 >= -1e-12
                else:
                    inside = d0 <= 1e-12 and d1 <= 1e-12 and d2 <= 1e-12
                if inside:
                    ear = False
                    break
            if ear:
                tris.append((i0, i1, i2))
                del idx[k]
                clipped = True
                break
        if not clipped:                                    # numerically stuck: fan the rest
            break
    for k in range(1, len(idx) - 1):
        tris.append((idx[0], idx[k], idx[k + 1]))
    return tris


def frame_z(p0, p1, up=(0.0, 0.0, 1.0)):
    """Matrix whose origin is p0 and whose +Z runs toward p1; +Y leans toward `up`."""
    p0, p1 = Vector(p0), Vector(p1)
    z = (p1 - p0)
    length = z.length
    z = z / length if length > 1e-12 else Vector((0, 0, 1))
    y = Vector(up) - z * Vector(up).dot(z)
    if y.length < 1e-6:
        y = Vector((1.0, 0.0, 0.0)) - z * z.x
        if y.length < 1e-6:
            y = Vector((0.0, 1.0, 0.0))
    y.normalize()
    x = y.cross(z)
    m = Matrix((
        (x.x, y.x, z.x, p0.x),
        (x.y, y.y, z.y, p0.y),
        (x.z, y.z, z.z, p0.z),
        (0.0, 0.0, 0.0, 1.0),
    ))
    return m, length


def frame_axes(origin, x_axis, y_axis):
    """Right-handed frame from an origin and two (orthonormal-ish) axes; Z = X x Y."""
    x = Vector(x_axis).normalized()
    y = Vector(y_axis)
    y = (y - x * y.dot(x)).normalized()
    z = x.cross(y)
    o = Vector(origin)
    return Matrix((
        (x.x, y.x, z.x, o.x),
        (x.y, y.y, z.y, o.y),
        (x.z, y.z, z.z, o.z),
        (0.0, 0.0, 0.0, 1.0),
    ))


# --------------------------------------------------------------------------------------------
class MeshBuilder:
    def __init__(self, uv_scale=0.25):
        self.co = []          # corner positions (x, y, z)
        self.faces = []       # index tuples into co
        self.mat = []         # material name per face
        self.smooth = []      # bool per face
        self.uv = []          # per face: tuple of (u, v) per corner, or None
        self.col = []         # per face: tuple of rgba per corner, or None
        self.uv_scale = uv_scale
        self._m = None        # current transform as nested tuples (or None)
        self._mat = Matrix.Identity(4)
        self._flip = False
        self.has_col = False

    # ---- transforms ------------------------------------------------------------------------
    @contextmanager
    def transform(self, matrix):
        saved = (self._m, self._mat, self._flip)
        self._mat = self._mat @ matrix
        self._m = tuple(tuple(row) for row in self._mat)
        self._flip = self._mat.to_3x3().determinant() < 0
        try:
            yield self
        finally:
            self._m, self._mat, self._flip = saved

    def at(self, x=0.0, y=0.0, z=0.0, rz=0.0, rx=0.0, ry=0.0):
        m = Matrix.Translation((x, y, z))
        if rz:
            m = m @ Matrix.Rotation(rz, 4, "Z")
        if ry:
            m = m @ Matrix.Rotation(ry, 4, "Y")
        if rx:
            m = m @ Matrix.Rotation(rx, 4, "X")
        return self.transform(m)

    def world(self, p):
        m = self._m
        if m is None:
            return (float(p[0]), float(p[1]), float(p[2]))
        x, y, z = p
        return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
                m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
                m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])

    # ---- faces -----------------------------------------------------------------------------
    def face(self, pts, mat, uv=None, smooth=False, col=None):
        n = len(self.co)
        k = len(pts)
        w = self.world
        self.co.extend(w(p) for p in pts)
        idx = tuple(range(n, n + k))
        if self._flip:
            idx = idx[::-1]
            if uv is not None:
                uv = tuple(uv)[::-1]
            if col is not None and isinstance(col[0], (tuple, list)):
                col = tuple(col)[::-1]
        self.faces.append(idx)
        self.mat.append(mat)
        self.smooth.append(smooth)
        self.uv.append(tuple(uv) if uv is not None else None)
        if col is not None:
            self.has_col = True
            if not isinstance(col[0], (tuple, list)):
                col = (tuple(col),) * k
        self.col.append(col)

    def quad(self, a, b, c, d, mat, uv=None, smooth=False, col=None):
        self.face((a, b, c, d), mat, uv, smooth, col)

    def tri(self, a, b, c, mat, uv=None, smooth=False, col=None):
        self.face((a, b, c), mat, uv, smooth, col)

    def poly(self, pts3, mat, uv=None, smooth=False, col=None):
        """Planar polygon that may be concave: triangulated in its own plane."""
        if len(pts3) <= 4:
            self.face(pts3, mat, uv, smooth, col)
            return
        # Newell normal, then project to the dominant plane.
        nx = ny = nz = 0.0
        k = len(pts3)
        for i in range(k):
            x0, y0, z0 = pts3[i]
            x1, y1, z1 = pts3[(i + 1) % k]
            nx += (y0 - y1) * (z0 + z1)
            ny += (z0 - z1) * (x0 + x1)
            nz += (x0 - x1) * (y0 + y1)
        ax, ay, az = abs(nx), abs(ny), abs(nz)
        if az >= ax and az >= ay:
            p2 = [(p[0], p[1]) for p in pts3]
        elif ax >= ay:
            p2 = [(p[1], p[2]) for p in pts3]
        else:
            p2 = [(p[2], p[0]) for p in pts3]
        for i0, i1, i2 in triangulate(p2):
            self.face((pts3[i0], pts3[i1], pts3[i2]), mat,
                      None if uv is None else (uv[i0], uv[i1], uv[i2]), smooth, col)

    # ---- primitives ------------------------------------------------------------------------
    def box(self, lo, hi, mat, skip="", mats=None, smooth=False, uv=None):
        """Axis-aligned box in the current frame. `skip`: letters of faces to omit
        (x/X = min/max X side, y/Y, z/Z). `mats`: {letter: material} overrides."""
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        if z1 < z0:
            z0, z1 = z1, z0
        mats = mats or {}
        f = {
            "Z": ((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)),
            "z": ((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)),
            "X": ((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)),
            "x": ((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)),
            "Y": ((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)),
            "y": ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)),
        }
        for key, pts in f.items():
            if key in skip:
                continue
            self.face(pts, mats.get(key, mat), uv, smooth)

    def prism(self, outline, z0, z1, mat, caps="zZ", cap_mat=None, smooth=False):
        """Extrude a 2D outline (counter-clockwise in local XY) from z0 to z1."""
        if polygon_area(outline) < 0:
            outline = outline[::-1]
        n = len(outline)
        for i in range(n):
            (xa, ya), (xb, yb) = outline[i], outline[(i + 1) % n]
            self.face(((xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)), mat, None, smooth)
        cap_mat = cap_mat or mat
        tris = triangulate(outline) if n > 4 else None
        if "Z" in caps:
            if tris is None:
                self.face([(x, y, z1) for x, y in outline], cap_mat)
            else:
                for a, b, c in tris:
                    self.face([(outline[i][0], outline[i][1], z1) for i in (a, b, c)], cap_mat)
        if "z" in caps:
            if tris is None:
                self.face([(x, y, z0) for x, y in outline[::-1]], cap_mat)
            else:
                for a, b, c in tris:
                    self.face([(outline[i][0], outline[i][1], z0) for i in (c, b, a)], cap_mat)

    def cylinder(self, r, z0, z1, mat, segs=12, r1=None, caps="zZ", cap_mat=None, smooth=True,
                 phase=0.0):
        """Along local Z, centred on the local origin. r at z0, r1 (default r) at z1."""
        r1 = r if r1 is None else r1
        ring0, ring1 = [], []
        for k in range(segs):
            a = phase + 2.0 * math.pi * k / segs
            c, s = math.cos(a), math.sin(a)
            ring0.append((r * c, r * s, z0))
            ring1.append((r1 * c, r1 * s, z1))
        for k in range(segs):
            k2 = (k + 1) % segs
            self.face((ring0[k], ring0[k2], ring1[k2], ring1[k]), mat, None, smooth)
        cap_mat = cap_mat or mat
        if "Z" in caps and r1 > 1e-9:
            self.face(ring1, cap_mat)
        if "z" in caps and r > 1e-9:
            self.face(ring0[::-1], cap_mat)

    def cyl_between(self, p0, p1, r, mat, segs=12, r1=None, caps="zZ", cap_mat=None, smooth=True,
                    up=(0, 0, 1)):
        m, length = frame_z(p0, p1, up)
        with self.transform(m):
            self.cylinder(r, 0.0, length, mat, segs, r1, caps, cap_mat, smooth)

    def beam(self, p0, p1, w, h, mat, up=(0.0, 0.0, 1.0), caps="zZ", mats=None):
        """Rectangular section (w across, h toward `up`) between two points."""
        m, length = frame_z(p0, p1, up)
        with self.transform(m):
            self.box((-w / 2, -h / 2, 0.0), (w / 2, h / 2, length), mat,
                     skip="".join(c for c in "zZ" if c not in caps), mats=mats)

    def lathe(self, profile, mat, segs=16, smooth=True, mats=None, angles=None, uv_v=None):
        """Revolve (r, z) points about local Z. Traverse the profile counter-clockwise around
        the solid (r to the right, z up): bottom axis -> outside -> top axis."""
        if angles is None:
            angles = [2.0 * math.pi * k / segs for k in range(segs)]
        n = len(angles)
        cs = [(math.cos(a), math.sin(a)) for a in angles]
        for j in range(len(profile) - 1):
            (ra, za), (rb, zb) = profile[j], profile[j + 1]
            m = mats[j] if mats else mat
            if m is None:
                continue
            for k in range(n):
                k2 = (k + 1) % n
                (c0, s0), (c1, s1) = cs[k], cs[k2]
                a0 = (ra * c0, ra * s0, za)
                a1 = (ra * c1, ra * s1, za)
                b0 = (rb * c0, rb * s0, zb)
                b1 = (rb * c1, rb * s1, zb)
                if ra < 1e-9 and rb < 1e-9:
                    continue
                if ra < 1e-9:
                    self.face((a0, b1, b0), m, None, smooth)
                elif rb < 1e-9:
                    self.face((a0, a1, b0), m, None, smooth)
                else:
                    self.face((a0, a1, b1, b0), m, None, smooth)

    def tube(self, pts, r, mat, segs=10, caps=True, smooth=True, closed=False, cap_mat=None,
             radii=None):
        """Round tube along a polyline, with mitred joints (parallel-transported frame)."""
        P = [Vector(p) for p in pts]
        n = len(P)
        tangents = []
        for i in range(n):
            if closed:
                t = (P[(i + 1) % n] - P[i - 1])
            elif i == 0:
                t = P[1] - P[0]
            elif i == n - 1:
                t = P[-1] - P[-2]
            else:
                a = (P[i] - P[i - 1]).normalized()
                b = (P[i + 1] - P[i]).normalized()
                t = a + b
                if t.length < 1e-9:
                    t = b
            tangents.append(t.normalized())
        ref = Vector((0, 0, 1))
        if abs(tangents[0].dot(ref)) > 0.95:
            ref = Vector((1, 0, 0))
        nrm = (ref - tangents[0] * ref.dot(tangents[0])).normalized()
        rings = []
        for i in range(n):
            t = tangents[i]
            nrm = (nrm - t * nrm.dot(t))
            if nrm.length < 1e-9:
                nrm = t.orthogonal()
            nrm.normalize()
            b = t.cross(nrm)
            rr = radii[i] if radii else r
            # mitre scale so the tube keeps its radius through a bend
            if 0 < i < n - 1 and not closed:
                a = (P[i] - P[i - 1]).normalized()
                cosh = max(0.3, a.dot(t))
                scale = 1.0 / cosh
            else:
                scale = 1.0
            ring = []
            for k in range(segs):
                ang = 2.0 * math.pi * k / segs
                off = nrm * math.cos(ang) + b * math.sin(ang)
                if scale != 1.0:
                    # stretch only in the bend plane
                    a = (P[i] - P[i - 1]).normalized()
                    bend = (P[i + 1] - P[i]).normalized() - a
                    if bend.length > 1e-9:
                        bend.normalize()
                        off = off + bend * (off.dot(bend) * (scale - 1.0))
                ring.append(tuple(P[i] + off * rr))
            rings.append(ring)
        last = n if closed else n - 1
        for i in range(last):
            r0, r1 = rings[i], rings[(i + 1) % n]
            for k in range(segs):
                k2 = (k + 1) % segs
                self.face((r0[k], r0[k2], r1[k2], r1[k]), mat, None, smooth)
        if caps and not closed:
            cm = cap_mat or mat
            self.face(rings[0][::-1], cm)
            self.face(rings[-1], cm)

    def disc(self, r, mat, segs=12, z=0.0, up=True, phase=0.0):
        ring = [(r * math.cos(phase + 2 * math.pi * k / segs),
                 r * math.sin(phase + 2 * math.pi * k / segs), z) for k in range(segs)]
        self.face(ring if up else ring[::-1], mat)

    # ---- bookkeeping -----------------------------------------------------------------------
    def tri_count(self):
        return sum(len(f) - 2 for f in self.faces)

    def tri_count_by_material(self):
        out = {}
        for f, m in zip(self.faces, self.mat):
            out[m] = out.get(m, 0) + len(f) - 2
        return out

    def bounds(self):
        co = np.asarray(self.co, dtype=np.float64)
        return co.min(axis=0), co.max(axis=0)

    def triangles(self):
        """(n, 3, 3) array of triangle corner positions (fan triangulation), plus the material
        name of each triangle. Used by the validation code."""
        co = np.asarray(self.co, dtype=np.float64)
        tris, mats = [], []
        for f, m in zip(self.faces, self.mat):
            for k in range(1, len(f) - 1):
                tris.append((f[0], f[k], f[k + 1]))
                mats.append(m)
        return co[np.asarray(tris, dtype=np.int64)], mats

    # ---- Blender mesh ----------------------------------------------------------------------
    def _box_uv(self, pts):
        k = len(pts)
        nx = ny = nz = 0.0
        for i in range(k):
            x0, y0, z0 = pts[i]
            x1, y1, z1 = pts[(i + 1) % k]
            nx += (y0 - y1) * (z0 + z1)
            ny += (z0 - z1) * (x0 + x1)
            nz += (x0 - x1) * (y0 + y1)
        s = self.uv_scale
        ax, ay, az = abs(nx), abs(ny), abs(nz)
        if az >= ax and az >= ay:
            return [(p[0] * s, p[1] * s) for p in pts]
        if ax >= ay:
            sg = 1.0 if nx > 0 else -1.0
            return [(sg * p[1] * s, p[2] * s) for p in pts]
        sg = -1.0 if ny > 0 else 1.0
        return [(sg * p[0] * s, p[2] * s) for p in pts]

    def to_object(self, name, slots=None, weld=True, sharp_angle=35.0, collection=None,
                  materials=None):
        """Create the mesh object. `slots` fixes the material slot order (unused names are
        dropped unless `keep_all`); `materials` maps slot name -> bpy material."""
        co = np.asarray(self.co, dtype=np.float64).reshape(-1, 3)
        faces = self.faces
        if weld and len(co):
            key = np.round(co / 1e-4).astype(np.int64)
            _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
            inv = inv.reshape(-1)
            wco = co[first]
        else:
            inv = np.arange(len(co))
            wco = co

        used = []
        for m in self.mat:
            if m not in used:
                used.append(m)
        if slots is None:
            slots = used
        else:
            missing = [m for m in used if m not in slots]
            if missing:
                raise ValueError(f"{name}: faces use materials not in the slot list: {missing}")
            slots = [s for s in slots if s in used]
        slot_index = {s: i for i, s in enumerate(slots)}

        out_faces, out_mat, out_smooth, out_uv, out_col = [], [], [], [], []
        dropped = 0
        for fi, f in enumerate(faces):
            w = [int(inv[i]) for i in f]
            # remove consecutive duplicates created by welding
            keep = [j for j in range(len(w)) if w[j] != w[j - 1]]
            if len(keep) < 3 or len({w[j] for j in keep}) < 3:
                dropped += 1
                continue
            uv = self.uv[fi]
            if uv is None:
                uv = self._box_uv([self.co[i] for i in f])
            out_faces.append([w[j] for j in keep])
            out_mat.append(slot_index[self.mat[fi]])
            out_smooth.append(self.smooth[fi])
            out_uv.extend(uv[j] for j in keep)
            if self.has_col:
                c = self.col[fi] or ((0.0, 0.0, 0.0, 1.0),) * len(f)
                out_col.extend(c[j] for j in keep)

        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(v) for v in wco], [], out_faces)
        mesh.polygons.foreach_set("material_index", out_mat)
        mesh.polygons.foreach_set("use_smooth", out_smooth)
        uv_layer = mesh.uv_layers.new(name="UVMap")
        uv_layer.data.foreach_set("uv", np.asarray(out_uv, dtype=np.float32).ravel())
        if self.has_col:
            attr = mesh.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
            attr.data.foreach_set("color", np.asarray(out_col, dtype=np.float32).ravel())
            mesh.color_attributes.active_color = attr
            mesh.color_attributes.render_color_index = 0
        mesh.update()
        if any(out_smooth):
            mesh.set_sharp_from_angle(angle=math.radians(sharp_angle))
        mesh.validate(verbose=False)
        mesh.update()

        for s in slots:
            m = (materials or {}).get(s) or bpy.data.materials.get(s) or bpy.data.materials.new(s)
            mesh.materials.append(m)
        obj = bpy.data.objects.new(name, mesh)
        (collection or bpy.context.scene.collection).objects.link(obj)
        obj["dropped_faces"] = dropped
        return obj


def mesh_triangle_count(obj):
    return sum(p.loop_total - 2 for p in obj.data.polygons)
