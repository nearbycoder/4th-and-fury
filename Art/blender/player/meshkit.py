"""Mesh assembly helpers (pure numpy, no bpy).

A `Part` is a bag of vertices and faces that knows, per face, its material slot, its UV chart and
its per-corner chart coordinates (in metres), and per vertex its skin weights. Parts are built
from structured grids (lofts, sweeps, trimmed patches) so topology, UVs and weights all come
straight from the construction. `assemble.py` turns a list of parts into one Blender mesh.
"""
import math
import numpy as np

from . import sdf


class Part:
    def __init__(self, name, mat):
        self.name = name
        self.mat = mat
        self.v = np.zeros((0, 3))
        self.faces = []          # tuples of vertex indices (3 or 4, outward winding)
        self.fuv = []            # tuples of (u, v) per corner, metres in chart space
        self.fmat = []           # material slot name per face
        self.fchart = []         # chart key per face (any hashable)
        self.ftag = []           # NumberUV tag per face or None
        self.w = {}              # bone name -> (N,) weight array
        self.smooth_angle = None  # None = smooth everywhere, else edges sharper than this split
        self.sharp = set()       # explicit hard edges as sorted vertex-index pairs
        self.uv_absolute = False  # True: fuv is already final 0..1 UVs (not packed into the atlas)
        self.rigid = None        # bone name if the whole part follows one bone

    # ------------------------------------------------------------------ construction
    def add_verts(self, pts):
        pts = np.asarray(pts, float).reshape(-1, 3)
        start = len(self.v)
        self.v = np.vstack([self.v, pts])
        return start

    def add_face(self, idx, uv, mat=None, chart=0, tag=None):
        self.faces.append(tuple(int(i) for i in idx))
        self.fuv.append(tuple((float(a), float(b)) for a, b in uv))
        self.fmat.append(mat or self.mat)
        self.fchart.append(chart)
        self.ftag.append(tag)

    def add_grid(self, P, closed=True, mat=None, chart=0, tag=None, uv=None, flip=None,
                 ring_mats=None, col_mats=None, face_mats=None, face_tags=None, idx=None):
        """Quads over a (rings, segments, 3) grid. `closed` wraps the segment direction.

        Winding is chosen so normals point away from the grid's own axis unless `flip` is given.
        ring_mats[i] / col_mats[j] / face_mats[i][j] override the material of the quads that
        START at ring i / column j. `idx` (rings, segments) may name vertices that already
        exist (entries < 0 are created from P), which is how two lofts share a ring.
        Returns the (rings, segments) vertex index array.
        """
        P = np.asarray(P, float)
        R, S = P.shape[:2]
        if idx is None:
            base = self.add_verts(P.reshape(-1, 3))
            idx = base + np.arange(R * S).reshape(R, S)
        else:
            idx = np.asarray(idx)
            fresh = idx < 0
            if fresh.any():
                base = self.add_verts(P[fresh])
                idx = idx.copy()
                idx[fresh] = base + np.arange(int(fresh.sum()))
        if uv is None:
            U, V = grid_uv(P, closed)
        else:
            U, V = uv
        if flip is None:
            flip = not grid_faces_outward(P, closed)
        cols = S if closed else S - 1
        for i in range(R - 1):
            for j in range(cols):
                j1 = (j + 1) % S
                quad = [idx[i, j], idx[i, j1], idx[i + 1, j1], idx[i + 1, j]]
                quv = [(U[i, j], V[i, j]), (U[i, j + 1], V[i, j + 1]),
                       (U[i + 1, j + 1], V[i + 1, j + 1]), (U[i + 1, j], V[i + 1, j])]
                if flip:
                    quad.reverse(); quv.reverse()
                m = mat
                if ring_mats is not None and ring_mats[i] is not None:
                    m = ring_mats[i]
                if col_mats is not None and col_mats[j] is not None:
                    m = col_mats[j]
                if face_mats is not None and face_mats[i][j] is not None:
                    m = face_mats[i][j]
                t = tag
                if face_tags is not None and face_tags[i][j] is not None:
                    t = face_tags[i][j]
                self.add_face(quad, quv, m, chart, t)
        return idx

    def add_fan(self, ring_idx, ring_uv, apex, apex_v, mat=None, chart=0, tag=None, flip=False):
        """Close a ring of existing vertices with triangles to a new apex vertex.

        ring_uv: (S+1, 2) chart coordinates of the ring (wrapped). apex_v: chart v of the apex.
        """
        a = self.add_verts(np.asarray(apex, float).reshape(1, 3))
        S = len(ring_idx)
        for j in range(S):
            j1 = (j + 1) % S
            tri = [ring_idx[j], ring_idx[j1], a]
            um = 0.5 * (ring_uv[j][0] + ring_uv[j + 1][0])
            tuv = [tuple(ring_uv[j]), tuple(ring_uv[j + 1]), (um, apex_v)]
            if flip:
                tri.reverse(); tuv.reverse()
            self.add_face(tri, tuv, mat, chart, tag)
        return a

    def add_cap(self, ring_idx, mat=None, chart=0, flip=False, tag=None):
        """Flat-ish cap over a ring: triangle fan to the centroid, planar UVs."""
        pts = self.v[list(ring_idx)]
        c = pts.mean(axis=0)
        n = np.zeros(3)
        for j in range(len(pts)):
            n += np.cross(pts[j] - c, pts[(j + 1) % len(pts)] - c)
        n = sdf.unit(n)
        e1 = sdf.unit(pts[0] - c)
        e2 = np.cross(n, e1)
        a = self.add_verts(c.reshape(1, 3))
        S = len(ring_idx)
        for j in range(S):
            j1 = (j + 1) % S
            tri = [ring_idx[j], ring_idx[j1], a]
            tuv = [((pts[j] - c) @ e1, (pts[j] - c) @ e2), ((pts[j1] - c) @ e1, (pts[j1] - c) @ e2), (0.0, 0.0)]
            if flip:
                tri.reverse(); tuv.reverse()
            self.add_face(tri, tuv, mat, chart, tag)
        return a

    # ------------------------------------------------------------------- operations
    def set_rigid(self, bone):
        self.rigid = bone
        self.w = {bone: np.ones(len(self.v))}
        return self

    def set_weights(self, fn):
        """fn(points) -> {bone: weights}."""
        self.rigid = None
        self.w = {b: np.asarray(a, float) for b, a in fn(self.v).items()}
        return self

    def transformed(self, M=None, t=None):
        if M is not None:
            self.v = self.v @ np.asarray(M, float).T
        if t is not None:
            self.v = self.v + np.asarray(t, float)
        return self

    def mirrored(self, name=None):
        """Copy reflected across X = 0, with _l/_r bones and tags swapped."""
        out = Part(name or swap_side(self.name), self.mat)
        out.v = self.v * np.array([-1.0, 1.0, 1.0])
        out.faces = [tuple(reversed(f)) for f in self.faces]
        out.fuv = [tuple((-u, v) for u, v in reversed(uv)) for uv in self.fuv]
        out.fmat = list(self.fmat)
        out.fchart = list(self.fchart)
        out.ftag = [swap_side(t) if isinstance(t, str) else t for t in self.ftag]
        out.w = {swap_side(b): a.copy() for b, a in self.w.items()}
        out.smooth_angle = self.smooth_angle
        out.sharp = set(self.sharp)
        out.uv_absolute = self.uv_absolute
        out.rigid = swap_side(self.rigid) if self.rigid else None
        return out

    def merge(self, other):
        """Append another part's geometry (keeps this part's name and smoothing rule)."""
        off = len(self.v)
        n_self, n_other = len(self.v), len(other.v)
        self.v = np.vstack([self.v, other.v])
        self.faces += [tuple(i + off for i in f) for f in other.faces]
        self.fuv += other.fuv
        self.fmat += other.fmat
        self.fchart += [(other.name, c) for c in other.fchart]
        self.ftag += other.ftag
        bones = set(self.w) | set(other.w)
        merged = {}
        for b in bones:
            a0 = self.w.get(b, np.zeros(n_self))
            a1 = other.w.get(b, np.zeros(n_other))
            merged[b] = np.concatenate([a0, a1])
        self.w = merged
        self.sharp |= {(a + off, b + off) for a, b in other.sharp}
        self.rigid = None
        return self

    def tri_count(self):
        return sum(len(f) - 2 for f in self.faces)

    def face_normals(self):
        out = np.zeros((len(self.faces), 3))
        for k, f in enumerate(self.faces):
            p = self.v[list(f)]
            n = np.zeros(3)
            for j in range(len(f)):
                n += np.cross(p[j], p[(j + 1) % len(f)])
            out[k] = n
        ln = np.linalg.norm(out, axis=1)
        return out / np.maximum(ln, 1e-20)[:, None]

    def face_centers(self):
        return np.array([self.v[list(f)].mean(axis=0) for f in self.faces])


def swap_side(name):
    if name is None:
        return None
    if name.endswith("_l"):
        return name[:-2] + "_r"
    if name.endswith("_r"):
        return name[:-2] + "_l"
    return name


# ----------------------------------------------------------------------------------- grids
def grid_uv(P, closed=True):
    """Chart coordinates for a lofted grid: u = arc length round the ring (centred on the ring),
    v = running distance between rings. Returns U, V of shape (R, S+1) if closed else (R, S)."""
    P = np.asarray(P, float)
    R, S = P.shape[:2]
    if closed:
        ring = np.concatenate([P, P[:, :1]], axis=1)
    else:
        ring = P
    seg = np.linalg.norm(np.diff(ring, axis=1), axis=2)
    U = np.concatenate([np.zeros((R, 1)), np.cumsum(seg, axis=1)], axis=1)
    U = U - 0.5 * U[:, -1:]
    step = np.linalg.norm(np.diff(P, axis=0), axis=2).mean(axis=1) if R > 1 else np.zeros(0)
    v = np.concatenate([[0.0], np.cumsum(step)])
    V = np.repeat(v[:, None], U.shape[1], axis=1)
    return U, V


def grid_faces_outward(P, closed=True):
    """True if quads (i,j),(i,j+1),(i+1,j+1),(i+1,j) face away from the grid's ring centres."""
    P = np.asarray(P, float)
    R, S = P.shape[:2]
    centre = P.mean(axis=1)
    total = 0.0
    cols = S if closed else S - 1
    for i in range(R - 1):
        a = P[i, :cols]
        b = P[i, (np.arange(cols) + 1) % S]
        c = P[i + 1, :cols]
        n = np.cross(b - a, c - a)
        mid = (a + b + c) / 3.0 - 0.5 * (centre[i] + centre[i + 1])
        total += float(np.einsum("ij,ij->", n, mid))
    return total >= 0.0


# --------------------------------------------------------------------------- ring sampling
def ring_dirs(U, V, thetas, W=None, phi=None):
    """Ray directions for rings. U, V (R,3) span each ring's plane; thetas (S,) or (R,S).
    Optional W (R,3) and elevation phi (R,) tilt the rays out of the plane (for end caps)."""
    U = np.asarray(U, float); V = np.asarray(V, float)
    R = U.shape[0]
    thetas = np.asarray(thetas, float)
    if thetas.ndim == 1:
        thetas = np.repeat(thetas[None, :], R, axis=0)
    c = np.cos(thetas)[:, :, None]; s = np.sin(thetas)[:, :, None]
    D = c * U[:, None, :] + s * V[:, None, :]
    if W is not None and phi is not None:
        phi = phi(thetas) if callable(phi) else np.asarray(phi, float)
        if phi.ndim == 1:
            phi = np.repeat(phi[:, None], D.shape[1], axis=1)
        D = np.cos(phi)[:, :, None] * D + np.sin(phi)[:, :, None] * np.asarray(W, float)[:, None, :]
    return D


def sample_rings(field, O, U, V, thetas, t1, W=None, phi=None, t0=0.0, mode="last", steps=72):
    """March rays out from each ring origin; returns points (R,S,3) and distances (R,S)."""
    O = np.asarray(O, float)
    D = ring_dirs(U, V, thetas, W, phi)
    R, S = D.shape[:2]
    Of = np.repeat(O[:, None, :], S, axis=1).reshape(-1, 3)
    t = sdf.march(field, Of, D.reshape(-1, 3), t0, t1, steps=steps, mode=mode)
    if np.isnan(t).any():
        bad = np.argwhere(np.isnan(t.reshape(R, S)))
        raise RuntimeError(f"sample_rings: {len(bad)} rays start outside the solid, e.g. ring/seg {bad[:6].tolist()}")
    P = Of + D.reshape(-1, 3) * t[:, None]
    return P.reshape(R, S, 3), t.reshape(R, S)


def even_thetas(field, O, U, V, anchors, counts, t1, W=None, phi=None, dense=6, mode="last", t0=0.0,
                weight=None):
    """Angles that put vertices evenly (by arc length) between anchor angles on every ring.

    anchors: (A,) or (R, A) increasing angles; the ring closes at anchors[0] + 2 pi.
    counts:  A segment counts, one per anchor interval.
    weight:  optional fn(points (N,3)) -> density (N,), >1 packs vertices closer together.
    Returns thetas (R, sum(counts)).
    """
    O = np.asarray(O, float)
    R = O.shape[0]
    anchors = np.asarray(anchors, float)
    if anchors.ndim == 1:
        anchors = np.repeat(anchors[None, :], R, axis=0)
    A = anchors.shape[1]
    ends = np.concatenate([anchors[:, 1:], anchors[:, :1] + 2.0 * math.pi], axis=1)
    out = []
    for a in range(A):
        n = counts[a]
        K = dense * n + 1
        frac = np.linspace(0.0, 1.0, K)
        th = anchors[:, a:a + 1] + (ends[:, a:a + 1] - anchors[:, a:a + 1]) * frac[None, :]
        P, _ = sample_rings(field, O, U, V, th, t1, W, phi, t0=t0, mode=mode)
        seg = np.linalg.norm(np.diff(P, axis=1), axis=2)
        if weight is not None:
            mid = 0.5 * (P[:, 1:] + P[:, :-1])
            seg = seg * weight(mid.reshape(-1, 3)).reshape(seg.shape)
        cum = np.concatenate([np.zeros((R, 1)), np.cumsum(seg, axis=1)], axis=1)
        picks = np.empty((R, n))
        for r in range(R):
            target = cum[r, -1] * np.arange(n) / n
            picks[r] = np.interp(target, cum[r], th[r])
        out.append(picks)
    return np.concatenate(out, axis=1)


def smooth_rows(a, passes=2, closed=False):
    """Light smoothing along axis 0 (ring index) so columns do not zig-zag."""
    a = np.asarray(a, float).copy()
    for _ in range(passes):
        b = a.copy()
        b[1:-1] = 0.25 * a[:-2] + 0.5 * a[1:-1] + 0.25 * a[2:]
        a = b
    return a


# ---------------------------------------------------------------------------------- curves
def resample_polyline(pts, spacing=None, count=None, closed=False):
    pts = np.asarray(pts, float)
    if closed:
        pts = np.vstack([pts, pts[:1]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if count is None:
        count = max(2, int(round(total / spacing)) + 1)
    if closed:
        target = total * np.arange(count) / count
    else:
        target = np.linspace(0.0, total, count)
    out = np.stack([np.interp(target, cum, pts[:, k]) for k in range(3)], axis=1)
    return out


def catmull(points, per_seg=8, closed=False):
    """Smooth curve through control points (centripetal-ish uniform Catmull-Rom)."""
    P = np.asarray(points, float)
    n = len(P)
    out = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = P[(i - 1) % n] if closed or i > 0 else 2 * P[0] - P[1]
        p1 = P[i]
        p2 = P[(i + 1) % n]
        p3 = P[(i + 2) % n] if closed or i + 2 < n else 2 * P[-1] - P[-2]
        for s in range(per_seg):
            t = s / per_seg
            t2 = t * t; t3 = t2 * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1])
    return np.array(out)


def transport_frames(pts, up_hint, closed=False):
    """Tangent / normal / binormal along a polyline, twist-free, starting near `up_hint`."""
    pts = np.asarray(pts, float)
    n = len(pts)
    T = np.zeros_like(pts)
    for i in range(n):
        a = pts[(i - 1) % n] if (closed or i > 0) else pts[i]
        b = pts[(i + 1) % n] if (closed or i < n - 1) else pts[i]
        T[i] = sdf.unit(b - a)
    N = np.zeros_like(pts)
    up = np.asarray(up_hint, float)
    n0 = up - (up @ T[0]) * T[0]
    if np.linalg.norm(n0) < 1e-6:
        n0 = np.cross(T[0], [1.0, 0.0, 0.0])
        if np.linalg.norm(n0) < 1e-6:
            n0 = np.cross(T[0], [0.0, 1.0, 0.0])
    N[0] = sdf.unit(n0)
    for i in range(1, n):
        v = N[i - 1] - (N[i - 1] @ T[i]) * T[i]
        N[i] = sdf.unit(v)
    B = np.cross(T, N)
    return T, N, B


def sweep_tube(part, pts, radius, sides=8, up_hint=(0, 0, 1), closed=False, caps=True, mat=None,
               chart=0, ry=None, phase=0.0, radii=None):
    """Sweep a round (or elliptical: `radius` along the frame normal, `ry` along the binormal)
    section along a polyline. Returns the (len(pts), sides) vertex index grid."""
    pts = np.asarray(pts, float)
    T, N, B = transport_frames(pts, up_hint, closed)
    n = len(pts)
    ang = phase + 2.0 * math.pi * np.arange(sides) / sides
    rx = np.full(n, radius, float) if radii is None else np.asarray(radii, float)
    rb = rx if ry is None else np.full(n, ry, float) * (rx / radius)
    P = (pts[:, None, :] + (np.cos(ang)[None, :, None] * N[:, None, :]) * rx[:, None, None]
         + (np.sin(ang)[None, :, None] * B[:, None, :]) * rb[:, None, None])
    if closed:
        P = np.concatenate([P, P[:1]], axis=0)
    # rings are counter-clockwise about T, quads built along T -> outward
    idx = part.add_grid(P, closed=True, mat=mat, chart=chart, flip=False)
    if closed:
        # weld is not needed visually; the duplicate end ring coincides with the first ring
        return idx
    if caps:
        part.add_cap(list(idx[0]), mat=mat, chart=(chart, "cap0"), flip=True)
        part.add_cap(list(idx[-1]), mat=mat, chart=(chart, "cap1"), flip=False)
    return idx


# ----------------------------------------------------------------------- trimmed surfaces
def trim_grid(g_fn, us, vs, periodic_v=False, snap=0.30):
    """Tessellate the part of a parameter rectangle where g(u, v) > 0.

    Grid nodes near the trim curve are slid onto it and crossed grid edges are split exactly on
    it, so the cut is a clean smooth polyline whatever the grid direction. With `periodic_v` the
    last column is the same line as the first (vs must span exactly one period).
    Returns (uv (N, 2), faces as lists of indices wound u -> v).
    """
    us = np.asarray(us, float); vs = np.asarray(vs, float)
    nu, nv = len(us), len(vs)
    UU, VV = np.meshgrid(us, vs, indexing="ij")
    uv = np.stack([UU, VV], axis=2).reshape(-1, 2).copy()
    du = np.gradient(us); dv = np.gradient(vs)
    cell = np.stack([np.repeat(du[:, None], nv, 1), np.repeat(dv[None, :], nu, 0)], axis=2).reshape(-1, 2)
    ii, jj = np.divmod(np.arange(nu * nv), nv)
    e = 1e-4 * np.array([max(us[-1] - us[0], 1e-9), max(vs[-1] - vs[0], 1e-9)])

    def g(a):
        return np.asarray(g_fn(a[:, 0], a[:, 1]), float)

    def grad(a):
        gu = (g(a + [e[0], 0.0]) - g(a - [e[0], 0.0])) / (2.0 * e[0])
        gv = (g(a + [0.0, e[1]]) - g(a - [0.0, e[1]])) / (2.0 * e[1])
        return np.stack([gu, gv], axis=1)

    moved = np.zeros(nu * nv, dtype=bool)
    for _ in range(4):
        gv_ = g(uv)
        gr = grad(uv)
        gg = np.einsum("ij,ij->i", gr, gr)
        step = -gr * (gv_ / np.maximum(gg, 1e-30))[:, None]
        step[(ii == 0) | (ii == nu - 1), 0] = 0.0
        step[(jj == 0) | (jj == nv - 1), 1] = 0.0
        total = uv + step - np.stack([UU, VV], axis=2).reshape(-1, 2)
        near = (np.abs(total[:, 0]) < snap * cell[:, 0]) & (np.abs(total[:, 1]) < snap * cell[:, 1])
        uv[near] += step[near]
        moved |= near
    gv_ = g(uv)
    gr = grad(uv)
    dist = np.abs(gv_) / np.maximum(np.linalg.norm(gr * cell, axis=1), 1e-30)
    on = moved & (dist < 2e-3)
    state = np.where(on, 0, np.where(gv_ > 0, 1, -1))

    def node(i, j):
        if periodic_v and j == nv - 1:
            j = 0
        return i * nv + j

    # every grid edge that changes sign gets one new vertex, found for all edges at once
    pairs = []
    for i in range(nu):
        for j in range(nv - 1):
            a, b = node(i, j), node(i, j + 1)
            if state[a] * state[b] < 0:
                pairs.append((i * nv + j, i * nv + j + 1, a, b))
    for i in range(nu - 1):
        for j in range(nv - (1 if periodic_v else 0)):
            a, b = node(i, j), node(i + 1, j)
            if state[a] * state[b] < 0:
                pairs.append((i * nv + j, (i + 1) * nv + j, a, b))
    cut_index = {}
    cut_uv = np.zeros((0, 2))
    if pairs:
        pa = uv[[p[0] for p in pairs]]; pb = uv[[p[1] for p in pairs]]
        ga = g(pa)
        lo = np.zeros(len(pairs)); hi = np.ones(len(pairs))
        for _ in range(34):
            mid = 0.5 * (lo + hi)
            gm = g(pa + (pb - pa) * mid[:, None])
            same = (gm > 0) == (ga > 0)
            lo = np.where(same, mid, lo); hi = np.where(same, hi, mid)
        t = 0.5 * (lo + hi)
        cut_uv = pa + (pb - pa) * t[:, None]
        for k, p in enumerate(pairs):
            key = (p[2], p[3]) if p[2] < p[3] else (p[3], p[2])
            cut_index[key] = nu * nv + k

    def cut(a, b):
        return cut_index[(a, b) if a < b else (b, a)]

    faces = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            corners = [node(i, j), node(i + 1, j), node(i + 1, j + 1), node(i, j + 1)]
            st = [state[c] for c in corners]
            if all(s >= 0 for s in st) and any(s > 0 for s in st):
                faces.append(corners)
                continue
            if all(s <= 0 for s in st):
                continue
            poly = []
            for k in range(4):
                a, b = corners[k], corners[(k + 1) % 4]
                sa, sb = st[k], st[(k + 1) % 4]
                if sa >= 0:
                    poly.append(a)
                if sa * sb < 0:
                    poly.append(cut(a, b))
            clean = []
            for p in poly:
                if not clean or clean[-1] != p:
                    clean.append(p)
            if len(clean) > 1 and clean[0] == clean[-1]:
                clean.pop()
            if len(clean) < 3:
                continue
            while len(clean) > 4:
                faces.append(clean[:4])
                clean = [clean[0]] + clean[3:]
            faces.append(clean)
    all_uv = np.vstack([uv, cut_uv])
    used = sorted({i for f in faces for i in f})
    remap = {old: new for new, old in enumerate(used)}
    return all_uv[used], [[remap[i] for i in f] for f in faces]


def boundary_loops(faces):
    """Ordered boundary loops of a face list, each oriented with the surface on its left
    (the same direction the faces wind)."""
    nxt = {}
    edges = {}
    for f in faces:
        n = len(f)
        for k in range(n):
            a, b = f[k], f[(k + 1) % n]
            edges[(a, b)] = edges.get((a, b), 0) + 1
    for (a, b) in edges:
        if (b, a) not in edges:
            nxt.setdefault(a, []).append(b)
    loops = []
    visited = set()
    for start in list(nxt):
        for first in nxt[start]:
            if (start, first) in visited:
                continue
            loop = [start]
            cur, nx = start, first
            visited.add((cur, nx))
            while nx != start:
                loop.append(nx)
                cand = [c for c in nxt.get(nx, []) if (nx, c) not in visited]
                if not cand:
                    break
                cur, nx = nx, cand[0]
                visited.add((cur, nx))
            loops.append(loop)
    return loops


def shell_from_surface(part, P, N, faces, thickness, mat=None, inner_mat=None, rim_mat=None, chart=0,
                       uvs=None, rim_round=0.5, face_mats=None, sharp_rim=True, inner=True, tag=None):
    """Give an open surface real thickness.

    P (n,3) points, N (n,3) outward unit normals, faces (outward winding). Adds the outer skin,
    an inner skin `thickness` below it (unless inner=False) and a two-step rounded wall round
    every open edge. `uvs` (n,2): chart coordinates of the outer skin (planar fallback if None).
    Returns (outer start index, inner start index, boundary loops).
    """
    P = np.asarray(P, float); N = np.asarray(N, float)
    if uvs is None:
        uvs = P[:, [0, 2]]
    uvs = np.asarray(uvs, float)
    o = part.add_verts(P)
    inner_i = part.add_verts(P - N * thickness)
    for k, f in enumerate(faces):
        m = face_mats[k] if face_mats is not None else mat
        part.add_face([o + i for i in f], [uvs[i] for i in f], m, (chart, "out"), tag)
        if inner:
            part.add_face([inner_i + i for i in reversed(f)], [uvs[i] for i in reversed(f)], inner_mat or mat, (chart, "in"))
    loops = boundary_loops(faces)
    for li, loop in enumerate(loops):
        L = len(loop)
        pts = P[loop]
        tang = np.array([sdf.unit(pts[(k + 1) % L] - pts[(k - 1) % L]) for k in range(L)])
        outward = np.cross(tang, N[loop])
        outward /= np.maximum(np.linalg.norm(outward, axis=1), 1e-12)[:, None]
        mid = pts - N[loop] * (0.5 * thickness) + outward * (rim_round * 0.5 * thickness)
        m_idx = part.add_verts(mid)
        seg = np.linalg.norm(pts - np.roll(pts, -1, axis=0), axis=1)
        s = np.concatenate([[0.0], np.cumsum(seg)])
        h = 0.6 * thickness
        for k in range(L):
            k1 = (k + 1) % L
            a, b = loop[k], loop[k1]
            u0, u1 = s[k], s[k + 1]
            # the kept surface lies to the left of a->b, so the wall winds b, a, down
            part.add_face([o + b, o + a, m_idx + k, m_idx + k1], [(u1, 0.0), (u0, 0.0), (u0, h), (u1, h)],
                          rim_mat or mat, (chart, "rim", li))
            part.add_face([m_idx + k1, m_idx + k, inner_i + a, inner_i + b], [(u1, h), (u0, h), (u0, 2 * h), (u1, 2 * h)],
                          rim_mat or mat, (chart, "rim", li))
            if sharp_rim:
                part.sharp.add(tuple(sorted((o + a, o + b))))
                if inner:
                    part.sharp.add(tuple(sorted((inner_i + a, inner_i + b))))
    return o, inner_i, loops


def rbox2(x, y, hx, hy, r):
    """Signed distance to a rounded rectangle centred on the origin (2D)."""
    dx = np.abs(x) - (hx - r)
    dy = np.abs(y) - (hy - r)
    return np.hypot(np.maximum(dx, 0.0), np.maximum(dy, 0.0)) + np.minimum(np.maximum(dx, dy), 0.0) - r


def raised_patch(part, name, uc, vc, hu, hv, r, project, lift, mat, n=(20, 8), sink=0.0012, rim_round=0.9,
                 sharp_rim=False):
    """A pad standing `lift` proud of a surface, with a rounded-rectangle outline.

    project(u, v) -> (points on the surface, outward unit normals) for parameters (u, v) in the
    projection plane; (uc, vc) is the centre and (hu, hv) the half-size of the outline there.
    """
    us = np.linspace(uc - hu - 0.004, uc + hu + 0.004, n[0])
    vs = np.linspace(vc - hv - 0.004, vc + hv + 0.004, n[1])
    uv, faces = trim_grid(lambda u, v: -rbox2(u - uc, v - vc, hu, hv, r), us, vs)
    P, N = project(uv[:, 0], uv[:, 1])
    Pl = P + N * lift
    f0 = faces[0]
    if np.cross(Pl[f0[1]] - Pl[f0[0]], Pl[f0[2]] - Pl[f0[0]]) @ N[f0[0]] < 0.0:
        faces = [list(reversed(f)) for f in faces]
    shell_from_surface(part, Pl, N, faces, lift + sink, mat=mat, chart=name, uvs=uv, rim_round=rim_round,
                       inner=False, sharp_rim=sharp_rim)
    return Pl, N
