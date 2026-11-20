"""Helmet: shell with real rim thickness, ear holes, bumpers, centre stripe, logo patches,
facemask cage, visor and chin strap. Everything here is rigid on the `head` bone.

The shell is one smooth implicit form. Its outer skin is sampled as rings round the ear-to-ear
axis, which gives (a) columns of constant X, so the centre stripe has dead-straight edges, and
(b) concentric rings round each ear hole. The face opening and lower rim are then cut out along a
smooth curve (meshkit.trim_grid) and the surface is given thickness.
"""
import math
import numpy as np

from . import meshkit as mk
from . import sdf
from .params import HEAD_SCALE
from .sdf import smoothstep

X = np.array([1.0, 0.0, 0.0])
Y = np.array([0.0, 1.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])
FRONT = -Y
TAU = 2.0 * math.pi

C = np.array([0.0, 0.010, 1.742])            # shell centre
A0, BF0, BB0, CT = 0.132, 0.150, 0.160, 0.150  # half-width, front / back half-length, crown height
NE, ME = 2.25, 2.3                           # plan squareness, dome profile
THICK = 0.007
EAR = np.array([0.0, 0.012, -0.028])         # ear-hole centre relative to C (x unused)
CP = C + EAR                                 # origin of the ear-to-ear axis
STRIPE_HALF = 0.0175 / HEAD_SCALE          # the whole helmet is scaled up afterwards

RIDGE_H, RIDGE_W0, RIDGE_W1 = 0.0034, 0.025, 0.041   # crown ridge height, flat half-width, foot half-width

Z_BROW = 0.028                               # top edge of the face opening (local z)
W_OPEN, H_OPEN, R_OPEN, TAPER = 0.086, 0.30, 0.036, 0.14
RIM_Y = [-0.17, -0.10, -0.04, 0.02, 0.07, 0.12, 0.17]
RIM_Z = [-0.124, -0.129, -0.133, -0.133, -0.127, -0.112, -0.098]

LOGO_C = (0.006, 0.046)                      # logo patch centre (local y, z)
LOGO_HALF = 0.055 / HEAD_SCALE


def shell_field(p):
    q = p - C
    x = np.abs(q[:, 0]); y = q[:, 1]; z = q[:, 2]
    zn = np.clip(-z / 0.14, 0.0, 1.8)
    a = A0 * (1.0 - 0.20 * zn ** 2)
    b = np.where(y < 0.0, BF0 * (1.0 - 0.06 * zn ** 2), BB0 * (1.0 - 0.15 * zn ** 2))
    h = (x / a) ** NE + (np.abs(y) / b) ** NE
    kz = np.clip(z / CT, 0.0, None)
    k = (h ** (ME / NE) + kz ** ME) ** (1.0 / ME)
    # a low, flat-topped ridge runs over the crown from the brow to the back bumper
    ridge = RIDGE_H * smoothstep(RIDGE_W1, RIDGE_W0, x) * smoothstep(-0.035, 0.045, z)
    return (k - 1.0) * 0.13 - ridge


def keep(p):
    """> 0 where the shell exists: above the lower rim and outside the face opening."""
    q = p - C
    g_bottom = q[:, 2] - sdf.pchip(q[:, 1], RIM_Y, RIM_Z)
    x_eff = np.abs(q[:, 0]) + TAPER * (Z_BROW - q[:, 2])
    d_open = mk.rbox2(x_eff, q[:, 2] - (Z_BROW - H_OPEN), W_OPEN, H_OPEN, R_OPEN)
    g_face = np.maximum(d_open, q[:, 1] + 0.03)
    return sdf.smin(g_bottom, g_face, 0.030)


def on_shell(y, z, side=1.0, lift=0.0):
    """World point on the shell's outer surface at world (y, z) on the given side (+1 = left)."""
    y = np.atleast_1d(np.asarray(y, float)); z = np.atleast_1d(np.asarray(z, float))
    O = np.stack([np.full_like(y, 0.012 * side), y, z], axis=1)
    D = np.repeat((X * side)[None, :], len(y), axis=0)
    t = sdf.march(shell_field, O, D, 0.0, 0.22)
    P = O + D * t[:, None]
    if lift:
        P = P + sdf.gradient(shell_field, P) * lift
    return P


def front_on_shell(x, z, lift=0.0, back=False):
    """World point on the shell's front (or back) surface at world (x, z)."""
    x = np.atleast_1d(np.asarray(x, float)); z = np.atleast_1d(np.asarray(z, float))
    O = np.stack([x, np.full_like(x, C[1]), z], axis=1)
    D = np.repeat((Y if back else FRONT)[None, :], len(x), axis=0)
    t = sdf.march(shell_field, O, D, 0.0, 0.25)
    P = O + D * t[:, None]
    N = sdf.gradient(shell_field, P)
    return P + N * lift, N


# ------------------------------------------------------------------------------ the shell
_XS = [0.0, STRIPE_HALF, 0.027, 0.041, 0.058, 0.076, 0.093, 0.105]
_FAN = [0.24, 0.45, 0.63, 0.79, 0.91, 1.0]
_XF = _XS[-1]


def _stations():
    xs, ss = [], []
    for s in reversed(_FAN):
        xs.append(_XF); ss.append(s)
    for x in reversed(_XS):
        xs.append(x); ss.append(0.0)
    for x in _XS[1:]:
        xs.append(-x); ss.append(0.0)
    for s in _FAN:
        xs.append(-_XF); ss.append(-s)
    return np.array(xs), np.array(ss)


def _hole_radius(phi):
    return 1.0 / np.sqrt((np.cos(phi) / 0.0125) ** 2 + (np.sin(phi) / 0.0165) ** 2)


def _eta_end():
    phi = np.linspace(0.0, TAU, 181)[:-1]
    r = _hole_radius(phi)
    rad = np.cos(phi)[:, None] * FRONT + np.sin(phi)[:, None] * Z
    O = CP + _XF * X + rad * r[:, None]
    t = sdf.march(shell_field, O, np.repeat(X[None, :], len(phi), axis=0), 0.0, 0.1)
    eta = np.arctan2(t, r)
    return lambda ph: np.interp(ph, phi, eta, period=TAU)


def shell_surface():
    xs, ss = _stations()
    idx = np.arange(len(xs), dtype=float)
    eta_end = _eta_end()

    def S(u, phi):
        u = np.asarray(u, float); phi = np.asarray(phi, float)
        x = np.interp(u, idx, xs)
        s = np.interp(u, idx, ss)
        O = CP[None, :] + x[:, None] * X[None, :]
        rad = np.cos(phi)[:, None] * FRONT + np.sin(phi)[:, None] * Z
        eta = s * eta_end(phi)
        D = np.cos(eta)[:, None] * rad + np.sin(eta)[:, None] * X[None, :]
        t = sdf.march(shell_field, O, D, 0.0, 0.3, steps=48, iters=18)
        return O + D * t[:, None]
    return S, idx


def build_shell():
    part = mk.Part("helmet_shell", "Helmet")
    S, us = shell_surface()
    vs = np.radians(np.linspace(90.0, 450.0, 73))
    uv, faces = mk.trim_grid(lambda u, v: keep(S(u, v)), us, vs, periodic_v=True)
    P = S(uv[:, 0], uv[:, 1])
    N = sdf.gradient(shell_field, P)
    # trim_grid winds u -> v; make it outward
    f0 = faces[0]
    n0 = np.cross(P[f0[1]] - P[f0[0]], P[f0[2]] - P[f0[0]])
    if n0 @ N[f0[0]] < 0.0:
        faces = [list(reversed(f)) for f in faces]
    q = P - C
    # two chart families: a band over the top (unrolled round the ear axis) and the two sides
    rel = P - CP
    phi = np.arctan2(rel[:, 2], -rel[:, 1])
    phi = np.where(phi < -0.5 * math.pi, phi + TAU, phi)
    band_uv = np.stack([phi * 0.150, P[:, 0]], axis=1)
    side_uv = np.stack([P[:, 1], P[:, 2]], axis=1)
    o = part.add_verts(P)
    inner = part.add_verts(P - N * THICK)
    for f in faces:
        xs_ = np.abs(q[f, 0])
        stripe = bool((xs_ <= STRIPE_HALF + 1e-6).all())
        cx = float(P[f, 0].mean())
        if abs(cx) < 0.078:
            uvs = [band_uv[i] for i in f]; chart = "band"
        else:
            uvs = [side_uv[i] for i in f]; chart = "side_l" if cx > 0 else "side_r"
        part.add_face([o + i for i in f], uvs, "HelmetStripe" if stripe else "Helmet", ("shell", chart))
        part.add_face([inner + i for i in reversed(f)], [uvs[k] for k in range(len(f) - 1, -1, -1)], "Helmet", ("liner", chart))
    # rim walls round every opening (face, bottom, ear holes)
    for li, loop in enumerate(mk.boundary_loops(faces)):
        L = len(loop)
        pts = P[loop]
        tang = np.array([sdf.unit(pts[(k + 1) % L] - pts[(k - 1) % L]) for k in range(L)])
        outward = np.cross(tang, N[loop])
        outward /= np.maximum(np.linalg.norm(outward, axis=1), 1e-12)[:, None]
        mid = pts - N[loop] * (0.5 * THICK) + outward * (0.30 * THICK)
        m = part.add_verts(mid)
        seg = np.linalg.norm(pts - np.roll(pts, -1, axis=0), axis=1)
        s = np.concatenate([[0.0], np.cumsum(seg)])
        h = 0.6 * THICK
        for k in range(L):
            k1 = (k + 1) % L
            a, b = loop[k], loop[k1]
            part.add_face([o + b, o + a, m + k, m + k1], [(s[k + 1], 0.0), (s[k], 0.0), (s[k], h), (s[k + 1], h)],
                          "Helmet", ("rim", li))
            part.add_face([m + k1, m + k, inner + a, inner + b], [(s[k + 1], h), (s[k], h), (s[k], 2 * h), (s[k + 1], 2 * h)],
                          "Helmet", ("rim", li))
            part.sharp.add(tuple(sorted((o + a, o + b))))
            part.sharp.add(tuple(sorted((inner + a, inner + b))))
    part.set_rigid("head")
    return part


def build_bumpers():
    part = mk.Part("helmet_bumpers", "Helmet")
    part.smooth_angle = 50.0
    zb = C[2] + Z_BROW
    mk.raised_patch(part, "front", 0.0, zb + 0.0145, 0.064, 0.0125, 0.008,
                  lambda x, z: front_on_shell(x, z), 0.0055, "Helmet", n=(26, 8))
    zr = C[2] + RIM_Z[-1]
    mk.raised_patch(part, "back", 0.0, zr + 0.021, 0.056, 0.0135, 0.009,
                  lambda x, z: front_on_shell(x, z, back=True), 0.0055, "Helmet", n=(22, 8))
    part.set_rigid("head")
    return part


def build_logos():
    """Two decal patches, 11 x 11 cm, 1.6 mm off the shell. UVs fill 0..1 with U toward the
    facemask and V up on BOTH sides."""
    part = mk.Part("helmet_logos", "HelmetLogo")
    part.uv_absolute = True
    n = 11
    ys = np.linspace(-LOGO_HALF, LOGO_HALF, n)
    zs = np.linspace(-LOGO_HALF, LOGO_HALF, n)
    YY, ZZ = np.meshgrid(ys, zs, indexing="ij")
    for side in (1.0, -1.0):
        P = on_shell(C[1] + LOGO_C[0] + YY.ravel(), C[2] + LOGO_C[1] + ZZ.ravel(), side=side, lift=0.0016)
        base = part.add_verts(P)
        U = (LOGO_HALF - YY.ravel()) / (2 * LOGO_HALF)
        V = (ZZ.ravel() + LOGO_HALF) / (2 * LOGO_HALF)
        for i in range(n - 1):
            for j in range(n - 1):
                quad = [i * n + j, (i + 1) * n + j, (i + 1) * n + j + 1, i * n + j + 1]
                # (i -> +y back, j -> +z up): y x z = +x, so this winding faces +X
                if side < 0:
                    quad.reverse()
                part.add_face([base + k for k in quad], [(U[k], V[k]) for k in quad], "HelmetLogo", ("logo", side))
    part.set_rigid("head")
    centre = on_shell(C[1] + LOGO_C[0], C[2] + LOGO_C[1], side=1.0)[0]
    return part, dict(centre_left=centre.tolist(), size=2 * LOGO_HALF)


# ----------------------------------------------------------------------------- facemask
YC = -0.066
BAR_R = 0.0038
_MASK_Z = [1.600, 1.618, 1.655, 1.700, 1.742, 1.772, 1.790]
_MASK_B = [0.096, 0.100, 0.107, 0.106, 0.097, 0.086, 0.078]
MASK_A = 0.108


def mask_pt(t, z):
    """Cage surface: an ellipse in plan that bulges out in front of the mouth."""
    t = np.asarray(t, float); z = np.asarray(z, float)
    B = sdf.pchip(z, _MASK_Z, _MASK_B)
    return np.stack([MASK_A * np.sin(t), YC - B * np.cos(t), z + 0.0 * t], axis=-1)


def bar_pts(t, z):
    """Cage point; toward the sides the bar bends in to lie on the shell's jaw flap."""
    t = np.atleast_1d(np.asarray(t, float)); z = np.atleast_1d(np.asarray(z, float))
    if len(z) == 1 and len(t) > 1:
        z = np.repeat(z, len(t))
    if len(t) == 1 and len(z) > 1:
        t = np.repeat(t, len(z))
    P = mask_pt(t, z)
    w = sdf.smoothstep(math.radians(50.0), math.radians(76.0), np.abs(t))
    side = np.where(t >= 0.0, 1.0, -1.0)
    Ps = P.copy()
    for sgn in (1.0, -1.0):
        m = (side == sgn) & (w > 0.0)
        if m.any():
            Ps[m] = on_shell(P[m, 1], P[m, 2], side=sgn, lift=BAR_R * 0.72)
    bad = np.isnan(Ps).any(axis=1)
    Ps[bad] = P[bad]
    return P * (1.0 - w)[:, None] + Ps * w[:, None]


MASK_STYLES = {
    # horizontal bar heights (the lowest is the chin bar), centre / side vertical angles (deg),
    # and how high the centre verticals climb (1.787 = all the way to the brow bar)
    "lean": dict(bars=(1.700, 1.657), verticals=(13.0,), v_top=1.700),
    "mid": dict(bars=(1.700, 1.657), verticals=(13.0, 44.0), v_top=1.700),
    "big": dict(bars=(1.703, 1.674, 1.645), verticals=(13.0, 44.0), v_top=1.787),
}
CHIN_BAR_Z = 1.616


def build_facemask(style="mid"):
    """Cage of round bars. Skill players get an open cage, linemen a denser one whose centre
    bars run up over the eyes."""
    cfg = MASK_STYLES[style]
    part = mk.Part("facemask", "Facemask")
    part.smooth_angle = 55.0
    d = np.radians
    bars = {}
    # outer frame: up the jaw flap, over the temple, across the brow bumper, and down again
    ft = np.array([78, 78, 78, 77, 73, 62, 46, 26, 0], float)
    fz = np.array([1.628, 1.662, 1.700, 1.736, 1.760, 1.776, 1.783, 1.786, 1.787])
    t_all = np.concatenate([d(ft), -d(ft[::-1][1:])])
    z_all = np.concatenate([fz, fz[::-1][1:]])
    bars["frame"] = mk.catmull(bar_pts(t_all, z_all), per_seg=6)
    span = np.linspace(-d(78), d(78), 41)
    for k, z in enumerate(cfg["bars"]):
        bars[f"h{k}"] = bar_pts(span, np.full_like(span, z))
    # chin bar sweeps up at its ends to meet the bottom of the frame
    tc = np.linspace(-d(78), d(78), 45)
    zc = CHIN_BAR_Z + 0.012 * sdf.smoothstep(d(52), d(78), np.abs(tc))
    bars["chin"] = bar_pts(tc, zc)
    for k, ang in enumerate(cfg["verticals"]):
        top = cfg["v_top"] if k == 0 else cfg["bars"][0]
        for sgn in (1.0, -1.0):
            zz = np.linspace(top, CHIN_BAR_Z, max(9, int((top - CHIN_BAR_Z) / 0.010)))
            bars[f"v{k}{'l' if sgn > 0 else 'r'}"] = bar_pts(np.full_like(zz, d(ang * sgn)), zz)
    for name, pts in bars.items():
        pts = mk.resample_polyline(pts, spacing=0.011)
        mk.sweep_tube(part, pts, BAR_R, sides=8, up_hint=(0, 0, 1), caps=True, chart=name)
    # clips that hold the cage to the shell
    clips = [bar_pts(d(s * 20.0), 1.7865)[0] for s in (1, -1)]
    clips += [bar_pts(d(s * 78.0), z)[0] for s in (1, -1) for z in (1.705, 1.640)]
    for k, c in enumerate(clips):
        n = sdf.gradient(shell_field, c[None, :])[0]
        tang = sdf.unit(np.cross(n, Z)) if abs(n[2]) < 0.9 else X
        if k < 2:
            tang = Z
        _clip(part, c - n * 0.001, n, tang, k)
    part.set_rigid("head")
    return part


def _clip(part, c, n, along, k, half=(0.0075, 0.0105, 0.0062)):
    """Small rounded block wrapped over a bar: `along` runs across the bar."""
    side = sdf.unit(np.cross(n, along))
    along = np.cross(side, n)
    hs, ha, hn = half
    corners = np.array([[sx * hs, sy * ha, sz * hn] for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)])
    P = c[None, :] + corners[:, 0:1] * side[None, :] + corners[:, 1:2] * along[None, :] + corners[:, 2:3] * n[None, :]
    b = part.add_verts(P)
    quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    for qi, qd in enumerate(quads):
        pts = P[list(qd)]
        if np.cross(pts[1] - pts[0], pts[2] - pts[0]) @ (pts.mean(axis=0) - c) < 0.0:
            qd = tuple(reversed(qd))
            pts = P[list(qd)]
        e1 = sdf.unit(pts[1] - pts[0]); nn = sdf.unit(np.cross(pts[1] - pts[0], pts[2] - pts[0])); e2 = np.cross(nn, e1)
        uv = [((p - pts[0]) @ e1, (p - pts[0]) @ e2) for p in pts]
        part.add_face([b + i for i in qd], uv, "Facemask", ("clip", k, qi))


# -------------------------------------------------------------------------------- visor
def build_visor():
    part = mk.Part("visor", "Visor")
    z0, z1 = 1.699, 1.777
    hw = 0.094
    us = np.linspace(-hw - 0.004, hw + 0.004, 31)
    vs = np.linspace(z0 - 0.004, z1 + 0.004, 12)
    zc, hz = 0.5 * (z0 + z1), 0.5 * (z1 - z0)

    def g(u, v):
        return -mk.rbox2(u, v - zc, hw, hz, 0.016)
    uv, faces = mk.trim_grid(g, us, vs)
    P, N = front_on_shell(uv[:, 0], uv[:, 1])
    P = P - N * 0.0105
    f0 = faces[0]
    if np.cross(P[f0[1]] - P[f0[0]], P[f0[2]] - P[f0[0]]) @ N[f0[0]] < 0.0:
        faces = [list(reversed(f)) for f in faces]
    mk.shell_from_surface(part, P, N, faces, 0.0022, mat="Visor", chart="visor", uvs=uv, rim_round=0.4, sharp_rim=True)
    part.set_rigid("head")
    return part


# --------------------------------------------------------------------------- chin strap
def build_strap():
    part = mk.Part("chin_strap", "Strap")
    part.smooth_angle = 48.0
    cup_c = np.array([0.0, -0.0935, 1.6165])
    # chin cup: a shallow rounded shell over the point of the chin
    cup_r = (0.037, 0.0165, 0.0245)
    f = lambda p: sdf.superellipsoid(p, cup_c, cup_r, (2.6, 2.2, 2.4))
    n_r, n_s = 9, 20
    rings = []
    phis = np.radians(np.linspace(-78.0, 78.0, n_r))
    th = np.linspace(0.0, TAU, n_s, endpoint=False)
    O = np.repeat(cup_c[None, :], n_r, axis=0)
    Pc, _ = mk.sample_rings(f, O, np.repeat(X[None, :], n_r, 0), np.repeat(Z[None, :], n_r, 0), th, 0.08,
                            W=np.repeat(FRONT[None, :], n_r, 0), phi=phis)
    idx = part.add_grid(Pc, closed=True, chart="cup")
    U_, V_ = mk.grid_uv(Pc, True)
    for end, flip in ((0, True), (-1, False)):
        tip = cup_c + FRONT * cup_r[1] * (-1.0 if end == 0 else 1.0)
        part.add_fan(list(idx[end]), np.stack([U_[end], V_[end]], axis=1), tip,
                     float(V_[end, 0]) + (-0.008 if end == 0 else 0.008), chart="cup", flip=flip)
    # four straps: from the cup, round the jaw flap, to a snap on the shell
    snaps = []
    for side in (1.0, -1.0):
        for name, (sy, sz), (my, mz) in (("hi", (-0.046, 1.676), (-0.092, 1.652)), ("lo", (-0.018, 1.634), (-0.086, 1.628))):
            snap = on_shell(sy, sz, side=side, lift=0.0026)[0]
            mid = on_shell(np.array([my, 0.5 * (my + sy)]), np.array([mz, 0.5 * (mz + sz)]), side=side, lift=0.0026)
            start = cup_c + np.array([side * 0.030, 0.006, 0.006 if name == "hi" else -0.006])
            lead = start + np.array([side * 0.030, -0.004, 0.012 if name == "hi" else 0.002])
            pts = mk.catmull(np.vstack([start, lead, mid, snap]), per_seg=7)
            pts = mk.resample_polyline(pts, spacing=0.012)
            nrm = sdf.gradient(shell_field, pts)
            _ribbon(part, pts, nrm, 0.0085, 0.0013, ("strap", name, side))
            snaps.append((snap, sdf.gradient(shell_field, snap[None, :])[0]))
    for k, (c, n) in enumerate(snaps):
        _button(part, c + n * 0.0008, n, 0.0072, 0.0030, ("snap", k))
    part.set_rigid("head")
    return part


def _ribbon(part, pts, normals, half_w, half_t, chart):
    """Flat strap along a polyline, its face turned to `normals`."""
    n = len(pts)
    T = np.zeros_like(pts)
    T[1:-1] = pts[2:] - pts[:-2]; T[0] = pts[1] - pts[0]; T[-1] = pts[-1] - pts[-2]
    T /= np.linalg.norm(T, axis=1)[:, None]
    Wd = np.cross(T, normals)
    Wd /= np.maximum(np.linalg.norm(Wd, axis=1), 1e-9)[:, None]
    Nn = np.cross(Wd, T)
    prof = [(-1, 1), (1, 1), (1, -1), (-1, -1)]
    P = np.stack([pts + Wd * (a * half_w) + Nn * (b * half_t) for a, b in prof], axis=1)
    idx = part.add_grid(P, closed=True, chart=chart)
    part.add_cap(list(idx[0]), chart=(chart, "c0"), flip=not _cap_faces_out(P[0], -T[0]))
    part.add_cap(list(idx[-1]), chart=(chart, "c1"), flip=not _cap_faces_out(P[-1], T[-1]))


def _cap_faces_out(ring, direction):
    c = ring.mean(axis=0)
    n = np.zeros(3)
    for j in range(len(ring)):
        n += np.cross(ring[j] - c, ring[(j + 1) % len(ring)] - c)
    return n @ direction > 0.0


def _button(part, c, n, r, h, chart, sides=10):
    a = sdf.unit(np.cross(n, Z) if abs(n[2]) < 0.9 else np.cross(n, X))
    b = np.cross(n, a)
    ang = np.linspace(0.0, TAU, sides, endpoint=False)
    ring = lambda rad, off: c[None, :] + n[None, :] * off + rad * (np.cos(ang)[:, None] * a + np.sin(ang)[:, None] * b)
    P = np.stack([ring(r, -0.001), ring(r, h * 0.6), ring(r * 0.72, h)], axis=0)
    idx = part.add_grid(P, closed=True, chart=chart)
    part.add_cap(list(idx[-1]), chart=(chart, "top"), flip=not _cap_faces_out(P[-1], n))


def build_jaw_pads():
    """Cheek pads inside the jaw flaps: they close the gap between the shell and the face."""
    part = mk.Part("helmet_pads", "Helmet")
    n_r, n_s = 8, 12
    phis = np.radians(np.linspace(-70.0, 70.0, n_r))
    th = np.linspace(0.0, TAU, n_s, endpoint=False)
    for side in (1.0, -1.0):
        c = np.array([side * 0.0895, -0.062, 1.670])
        f = lambda p, c=c: sdf.superellipsoid(p, c, (0.0200, 0.037, 0.041), (2.4, 2.6, 2.6))
        O = np.repeat(c[None, :], n_r, axis=0)
        P, _ = mk.sample_rings(f, O, np.repeat(X[None, :], n_r, 0), np.repeat(Z[None, :], n_r, 0), th, 0.08,
                               W=np.repeat(FRONT[None, :], n_r, 0), phi=phis)
        idx = part.add_grid(P, closed=True, chart=("pad", side))
        U_, V_ = mk.grid_uv(P, True)
        out = mk.grid_faces_outward(P, True)
        for end, sgn in ((0, -1.0), (-1, 1.0)):
            tip = c + FRONT * 0.037 * sgn
            part.add_fan(list(idx[end]), np.stack([U_[end], V_[end]], axis=1), tip, float(V_[end, 0]) + 0.008 * sgn,
                         chart=("pad", side), flip=(out if end == 0 else not out))
    part.set_rigid("head")
    return part


def build_helmet(style="mid"):
    """All rigid head gear. Returns (parts, info for the meta file)."""
    logos, logo_info = build_logos()
    parts = [build_shell(), build_bumpers(), build_jaw_pads(), logos, build_facemask(style), build_visor(), build_strap()]
    return parts, logo_info
