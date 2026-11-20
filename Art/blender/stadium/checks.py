"""Automated validation of the stadium mesh, the seat list and the UV conventions.

Every check returns a dict that goes into the build report; `ok` says whether it passed.
"""
import math

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import spec as S


# ---- triangle / box intersection -----------------------------------------------------------------
def _clip(poly, axis, value, keep_greater):
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ina = (a[axis] > value) if keep_greater else (a[axis] < value)
        inb = (b[axis] > value) if keep_greater else (b[axis] < value)
        if ina:
            out.append(a)
        if ina != inb:
            t = (value - a[axis]) / (b[axis] - a[axis])
            out.append(tuple(a[k] + (b[k] - a[k]) * t for k in range(3)))
    return out


def _area(poly):
    total = Vector((0.0, 0.0, 0.0))
    p0 = Vector(poly[0])
    for i in range(1, len(poly) - 1):
        total += (Vector(poly[i]) - p0).cross(Vector(poly[i + 1]) - p0)
    return 0.5 * total.length


def tris_in_box(tris, lo, hi, eps=1e-5):
    """Indices of triangles with a positive-area part strictly inside the box."""
    lo = np.asarray(lo, dtype=np.float64)
    hi = np.asarray(hi, dtype=np.float64)
    tmin = tris.min(axis=1)
    tmax = tris.max(axis=1)
    cand = np.nonzero(np.all(tmax > lo + eps, axis=1) & np.all(tmin < hi - eps, axis=1))[0]
    hits = []
    for i in cand:
        poly = [tuple(p) for p in tris[i]]
        for axis in range(3):
            poly = _clip(poly, axis, lo[axis] + eps, True)
            if len(poly) < 3:
                break
            poly = _clip(poly, axis, hi[axis] - eps, False)
            if len(poly) < 3:
                break
        if len(poly) >= 3 and _area(poly) > 1e-9:
            hits.append(int(i))
    return hits


def camera_clear(mb):
    """Nothing may enter |x| < 75, -62 < y < -30, z > 17."""
    tris, mats = mb.triangles()
    hits = tris_in_box(tris, (-S.CLEAR_X, S.CLEAR_Y0, S.CLEAR_Z), (S.CLEAR_X, S.CLEAR_Y1, 1e4))
    worst = {}
    for i in hits:
        worst[mats[i]] = worst.get(mats[i], 0) + 1
    # how close does the geometry come?
    near = tris[(np.abs(tris[:, :, 0]).min(axis=1) < S.CLEAR_X)
                & (tris[:, :, 1].max(axis=1) > S.CLEAR_Y0) & (tris[:, :, 1].min(axis=1) < S.CLEAR_Y1)]
    v = near.reshape(-1, 3)
    v = v[(np.abs(v[:, 0]) < S.CLEAR_X) & (v[:, 1] > S.CLEAR_Y0) & (v[:, 1] < S.CLEAR_Y1)]
    return dict(ok=not hits, triangles_inside=len(hits), by_material=worst,
                highest_vertex_under_it=float(v[:, 2].max()) if len(v) else None)


def turf_clear(mb):
    """Nothing of ours above z = 0 inside the engine's turf rectangle."""
    tris, mats = mb.triangles()
    hits = tris_in_box(tris, (-S.TURF_HX, -S.TURF_HY, 0.002), (S.TURF_HX, S.TURF_HY, 1e4))
    worst = {}
    for i in hits:
        worst[mats[i]] = worst.get(mats[i], 0) + 1
    return dict(ok=not hits, triangles_inside=len(hits), by_material=worst)


# ---- seats -------------------------------------------------------------------------------------------
def seats_on_steps(obj, seats, slot_names):
    """Drop a ray on every seat: it must land on a SeatA/SeatB face of the mesh, at the seat's own
    height, and the face's block must match the seat's section value."""
    mesh = obj.data
    verts = [v.co.copy() for v in mesh.vertices]
    polys = [tuple(p.vertices) for p in mesh.polygons]
    mat_of = [slot_names[p.material_index] for p in mesh.polygons]
    bvh = BVHTree.FromPolygons(verts, polys, all_triangles=False)
    down = Vector((0.0, 0.0, -1.0))
    bad_height = bad_surface = bad_section = 0
    worst = 0.0
    for (x, y, z, yaw, section) in seats:
        loc, nrm, idx, dist = bvh.ray_cast(Vector((x, y, z + 0.6)), down, 5.0)
        if loc is None:
            bad_height += 1
            continue
        err = abs(dist - 0.6)
        worst = max(worst, err)
        if err > 0.004:
            bad_height += 1
            continue
        m = mat_of[idx]
        if m not in ("SeatA", "SeatB"):
            bad_surface += 1
        elif (m == "SeatB") != (section > 0.5):
            bad_section += 1
    return dict(ok=(bad_height + bad_surface + bad_section) == 0, not_on_a_step=bad_height,
                not_on_seating=bad_surface, wrong_section=bad_section, worst_height_error=worst)


def seats_general(seats):
    arr = np.asarray(seats, dtype=np.float64).reshape(-1, 5)
    x, y, z, yaw, sec = arr.T
    # camera volume, allowing 2.3 m for a standing fan with arms up
    inside = (np.abs(x) < S.CLEAR_X) & (y > S.CLEAR_Y0) & (y < S.CLEAR_Y1) & (z + 2.3 > S.CLEAR_Z)
    # facing: the figure faces -Y at yaw 0; it must look toward the field
    fx, fy = np.sin(yaw), -np.cos(yaw)
    cx = np.clip(x, -S.FIELD_HX, S.FIELD_HX)
    cy = np.clip(y, -S.FIELD_HY, S.FIELD_HY)
    dx, dy = cx - x, cy - y
    dn = np.hypot(dx, dy)
    facing = (fx * dx + fy * dy) / np.maximum(dn, 1e-9)
    # spacing: nearest neighbour on the same level
    order = np.lexsort((y, x))
    cell = {}
    for i in range(len(arr)):
        key = (int(math.floor(x[i])), int(math.floor(y[i])))
        cell.setdefault(key, []).append(i)
    nearest = np.full(len(arr), 9.0)
    for (kx, ky), idx in cell.items():
        cand = []
        for ax in (-1, 0, 1):
            for ay in (-1, 0, 1):
                cand += cell.get((kx + ax, ky + ay), [])
        c = np.asarray(cand)
        for i in idx:
            same = c[(np.abs(z[c] - z[i]) < 0.05) & (c != i)]
            if len(same):
                d = np.hypot(x[same] - x[i], y[same] - y[i]).min()
                nearest[i] = d
    has = nearest < 8.9
    return dict(
        ok=bool(not inside.any() and facing.min() > 0.5 and nearest[has].min() > 0.5),
        count=int(len(arr)),
        in_camera_volume=int(inside.sum()),
        min_facing_cosine=float(facing.min()),
        pitch_min=float(nearest[has].min()),
        pitch_median=float(np.median(nearest[has])),
        pitch_p99=float(np.percentile(nearest[has], 99)),
        section_a=int((sec < 0.5).sum()),
        section_b=int((sec > 0.5).sum()),
        z_min=float(z.min()), z_max=float(z.max()),
    )


# ---- UV conventions ------------------------------------------------------------------------------------
def uv_conventions(mb):
    """Screen / ScreenSmall fill 0..1 upright and unmirrored as seen from in front; AdBoard runs
    left to right at one unit per board with V 0..1 bottom to top."""
    out = {}
    for slot in ("Screen", "ScreenSmall", "AdBoard"):
        umin = vmin = 1e9
        umax = vmax = -1e9
        flipped = mirrored = n = 0
        scale = []
        for f, m, uv in zip(mb.faces, mb.mat, mb.uv):
            if m != slot or uv is None:
                continue
            n += 1
            p = [Vector(mb.co[i]) for i in f]
            nrm = (p[1] - p[0]).cross(p[2] - p[0]).normalized()
            right = Vector((0, 0, 1)).cross(nrm)        # viewer's right when looking at the face
            if right.length < 1e-6:
                continue
            right.normalize()
            # gradients of u along `right` and v along up, from the first three corners
            e1, e2 = p[1] - p[0], p[2] - p[0]
            du1, dv1 = uv[1][0] - uv[0][0], uv[1][1] - uv[0][1]
            du2, dv2 = uv[2][0] - uv[0][0], uv[2][1] - uv[0][1]
            a11, a12 = e1.dot(right), e1.z
            a21, a22 = e2.dot(right), e2.z
            det = a11 * a22 - a12 * a21
            if abs(det) < 1e-12:
                continue
            du_dr = (du1 * a22 - du2 * a12) / det
            dv_dz = (dv2 * a11 - dv1 * a21) / det
            if du_dr <= 0:
                mirrored += 1
            if dv_dz <= 0:
                flipped += 1
            scale.append(1.0 / du_dr if du_dr > 0 else 0.0)
            for (u, v) in uv:
                umin, umax = min(umin, u), max(umax, u)
                vmin, vmax = min(vmin, v), max(vmax, v)
        res = dict(faces=n, u=[umin, umax], v=[vmin, vmax], mirrored=mirrored, upside_down=flipped)
        if slot == "AdBoard" and scale:
            res["metres_per_u"] = [float(min(scale)), float(max(scale))]
            res["ok"] = (mirrored == 0 and flipped == 0 and vmin > -1e-6 and vmax < 1 + 1e-6
                         and 5.7 < min(scale) and max(scale) < 6.3)
        else:
            res["ok"] = (mirrored == 0 and flipped == 0 and umin > -1e-6 and umax < 1 + 1e-6
                         and vmin > -1e-6 and vmax < 1 + 1e-6)
        out[slot] = res
    return out


# ---- back faces a camera could see ----------------------------------------------------------------------
def visible_backfaces(obj, slot_names, eyes, min_area=0.0005, limit=40):
    """For each eye point, list polygons that face away from it yet are the first thing rays from
    the eye hit (so a back-face-culling engine would show a hole there).

    Five points are tried on each back-facing polygon and at least two must be reached: a single
    hit is nearly always a ray slipping along a shared edge, and is only counted as a suspect.
    """
    mesh = obj.data
    verts = [v.co.copy() for v in mesh.vertices]
    polys = [tuple(p.vertices) for p in mesh.polygons]
    bvh = BVHTree.FromPolygons(verts, polys, all_triangles=False)
    centers = [p.center.copy() for p in mesh.polygons]
    normals = [p.normal.copy() for p in mesh.polygons]
    areas = [p.area for p in mesh.polygons]
    mats = [slot_names[p.material_index] for p in mesh.polygons]
    out = {}
    for name, eye in eyes.items():
        eye = Vector(eye)
        found = []
        total = 0.0
        suspects = 0
        for i, c in enumerate(centers):
            if areas[i] < min_area:
                continue
            to_eye = eye - c
            dist = to_eye.length
            if dist < 1e-6 or normals[i].dot(to_eye) >= -2e-3 * dist:
                continue                                   # front-facing, or too edge-on to judge
            vs = polys[i]
            n = len(vs)
            pts = [c] + [c * 0.45 + verts[vs[(k * n) // 4]] * 0.55 for k in range(4)]
            seen = 0
            for p in pts:
                d = p - eye
                length = d.length
                loc, nrm, idx, hd = bvh.ray_cast(eye, d / length, length + 0.5)
                if idx == i or (loc is not None and abs(hd - length) < 2e-3 and idx is not None
                                and normals[idx].dot(normals[i]) > 0.99):
                    seen += 1
            if seen >= 2:
                total += areas[i]
                found.append((areas[i], mats[i], [round(v, 2) for v in c]))
            elif seen == 1:
                suspects += 1
        found.sort(reverse=True)
        out[name] = dict(count=len(found), area=round(total, 4), single_ray_suspects=suspects,
                         worst=[dict(area=round(a, 4), slot=m, at=c) for a, m, c in found[:limit]])
    return out
