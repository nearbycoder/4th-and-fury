"""Torso with shoulder pads, shoulder caps and sleeves, arms, pants and socks.

Each piece is an implicit form (see sdf.py) sampled into a loft of clean rings, so edge loops sit
where joints bend and where one material ends and the next begins.
"""
import math
import numpy as np

from . import meshkit as mk
from . import sdf, skin
from .params import J, TAIL, CORE_COLS, PANEL_CAP

X = np.array([1.0, 0.0, 0.0])
Y = np.array([0.0, 1.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])
FRONT = -Y
MIRROR = np.array([-1.0, 1.0, 1.0])
TAU = 2.0 * math.pi


def rep(v, n):
    return np.repeat(np.asarray(v, float)[None, :], n, axis=0)


def limb_frame(a_from, a_to):
    """(side, front, along): `side` is up/out for an arm and outward for a leg."""
    a = sdf.unit(np.asarray(a_to, float) - np.asarray(a_from, float))
    f = sdf.unit(FRONT - (FRONT @ a) * a)
    s = np.cross(f, a)
    return s, f, a


def declutter(ts, must, gap):
    """Drop stations closer than `gap` to a neighbour, never dropping the `must` ones."""
    must = sorted(must)
    out = []
    for t in sorted(ts):
        if any(abs(t - m) < 1e-9 for m in must):
            while out and t - out[-1] < gap and not any(abs(out[-1] - m) < 1e-9 for m in must):
                out.pop()
            out.append(t)
        elif not out or t - out[-1] >= gap:
            out.append(t)
    # second pass from the right so nothing crowds a `must` station from below
    res = []
    for t in reversed(out):
        if any(abs(t - m) < 1e-9 for m in must) or not res or res[-1] - t >= gap:
            res.append(t)
    return np.array(sorted(res))


def adaptive(fn, lo, hi, max_step, min_step, tol, must=()):
    """Stations in [lo, hi], refined where the profile fn(t) -> (n, K, 3) bends."""
    ts = set(np.linspace(lo, hi, int(math.ceil((hi - lo) / max_step)) + 1).tolist())
    ts |= {float(m) for m in must if lo <= m <= hi}
    for _ in range(8):
        ta = np.array(sorted(ts))
        mids = 0.5 * (ta[1:] + ta[:-1])
        P = fn(ta)
        Pm = fn(mids)
        dev = np.linalg.norm(Pm - 0.5 * (P[1:] + P[:-1]), axis=2).max(axis=1)
        add = (dev > tol) & ((ta[1:] - ta[:-1]) > 2.0 * min_step)
        if not add.any():
            break
        ts |= set(mids[add].tolist())
    return declutter(sorted(ts), [m for m in must if lo <= m <= hi] + [lo, hi], min_step * 0.75)


rbox2 = mk.rbox2


def lip_onto(under, O, P, inside=0.003, lo=0.006, hi=0.035):
    """Turn a garment edge inward until it sinks `inside` metres into the form beneath it.

    under: field of the layer below. O: ring origin(s) on the limb axis. P (S, 3): the edge ring.
    Returns the lip ring. Depth is clamped to [lo, hi] so the lip never folds back on itself.
    """
    O = np.broadcast_to(np.asarray(O, float), P.shape)
    D = P - O
    L = np.linalg.norm(D, axis=1)
    D = D / L[:, None]
    t = sdf.march(under, O, D, 0.0, L, mode="last", steps=48)
    t = np.where(np.isnan(t), L - hi, t)
    depth = np.clip(L - t + inside, lo, hi)
    return P - D * depth[:, None]


def mark_ring_sharp(part, idx_row):
    n = len(idx_row)
    for j in range(n):
        a, b = int(idx_row[j]), int(idx_row[(j + 1) % n])
        part.sharp.add((a, b) if a < b else (b, a))


class Chain:
    """Polyline through joints; gives ring origins and smoothly turning ring frames."""

    def __init__(self, pts, blend=0.03):
        self.pts = [np.asarray(p, float) for p in pts]
        self.seg = [self.pts[i + 1] - self.pts[i] for i in range(len(self.pts) - 1)]
        self.len = [float(np.linalg.norm(s)) for s in self.seg]
        self.dir = [s / l for s, l in zip(self.seg, self.len)]
        self.cum = np.concatenate([[0.0], np.cumsum(self.len)])
        self.blend = blend

    def at(self, d):
        d = np.atleast_1d(np.asarray(d, float))
        O = np.zeros((len(d), 3)); T = np.zeros((len(d), 3))
        last = len(self.seg) - 1
        for k, dk in enumerate(d):
            i = int(np.clip(np.searchsorted(self.cum, dk, side="right") - 1, 0, last))
            O[k] = self.pts[i] + self.dir[i] * (dk - self.cum[i])
            t = self.dir[i].copy()
            if i > 0 and dk - self.cum[i] < self.blend:
                w = 0.5 * (1.0 - (dk - self.cum[i]) / self.blend)
                t = sdf.unit(t * (1.0 - w) + self.dir[i - 1] * w)
            if i < last and self.cum[i + 1] - dk < self.blend:
                w = 0.5 * (1.0 - (self.cum[i + 1] - dk) / self.blend)
                t = sdf.unit(t * (1.0 - w) + self.dir[i + 1] * w)
            T[k] = t
        F = FRONT[None, :] - (T @ FRONT)[:, None] * T
        F /= np.linalg.norm(F, axis=1)[:, None]
        S = np.cross(F, T)
        return O, S, F, T


# =================================================================================== torso
SIDE_PANEL_TOP = 1.405
PLATE_STEP = 0.021           # how far the chest / back plate stands proud of the taut jersey below it


def core_field(b):
    tab = sdf.Table(CORE_COLS, b.core)
    R = np.stack([X, FRONT, Z], axis=1)

    def f(p):
        return sdf.section_tube(p, (0.0, 0.0, 0.0), R, tab)
    return f


def jersey_field(b):
    core = core_field(b)
    sh, cp, bp = b.shelf, b.chest_plate, b.back_plate
    cx = 0.5 * (sh["rim"] + sh["inner"]); rx = 0.5 * (sh["rim"] - sh["inner"])
    cz = sh["top"] - 0.5 * sh["thick"]
    chest_c = (0.0, cp["front"] + cp["depth"], 0.5 * (cp["top"] + cp["bottom"]))
    chest_r = (cp["half_w"], cp["depth"], 0.5 * (cp["top"] - cp["bottom"]))
    back_c = (0.0, bp["back"] - bp["depth"], 0.5 * (bp["top"] + bp["bottom"]))
    back_r = (bp["half_w"], bp["depth"], 0.5 * (bp["top"] - bp["bottom"]))

    # the jersey is stretched from the lower edge of each plate down to the belt, so under the
    # plates it stands off the stomach and back instead of clinging to them
    R = np.stack([X, FRONT, Z], axis=1)
    rows = [list(r) for r in b.core]
    for r in rows:
        z = r[0]
        k = sdf.smoothstep(1.075, cp["bottom"] + 0.02, z) * (1.0 - sdf.smoothstep(cp["bottom"] + 0.05, cp["bottom"] + 0.16, z))
        r[2] = r[2] + float(k) * max(0.0, (-cp["front"] - PLATE_STEP) - r[2])
        kb = sdf.smoothstep(1.075, bp["bottom"] + 0.02, z) * (1.0 - sdf.smoothstep(bp["bottom"] + 0.05, bp["bottom"] + 0.16, z))
        r[3] = r[3] + float(kb) * max(0.0, (bp["back"] - PLATE_STEP) - r[3])
    drape_tab = sdf.Table(CORE_COLS, rows)

    def f(p):
        body = sdf.smax(sdf.section_tube(p, (0.0, 0.0, 0.0), R, drape_tab), p[:, 2] - 1.535, 0.02)
        # Bunched fabric above the belt, feathered out before the rigid chest plate.
        z = p[:, 2]
        hem = sdf.smoothstep(1.06, 1.105, z) * (1.0 - sdf.smoothstep(1.18, 1.24, z))
        diagonal = z + 0.16 * p[:, 0] + 0.018 * np.sin(13 * p[:, 1])
        body -= hem * (0.0025 + 0.0045 * np.cos(148 * diagonal))
        q = p * np.array([1.0, 1.0, 1.0])
        q[:, 0] = np.abs(q[:, 0])
        # the shelf drops a little toward its outer rim instead of lying dead flat
        q[:, 2] = q[:, 2] + sh.get("slope", 0.0) * np.maximum(q[:, 0] - sh["inner"], 0.0)
        slab = sdf.superellipsoid(q, (cx, sh["cy"], cz), (rx, sh["depth"], 0.5 * sh["thick"]), (3.4, 2.8, 3.2))
        chest = sdf.superellipsoid(p, chest_c, chest_r, (3.2, 2.4, 3.4))
        back = sdf.superellipsoid(p, back_c, back_r, (3.2, 2.4, 3.4))
        pads = sdf.smin(sdf.smin(chest, back, 0.02), slab, 0.03)
        return sdf.smin(body, pads, b.pad_blend)
    return f


def build_trunk(b, under=None):
    """Jersey over the pads. `under` is the field of the neck / chest skin, used to carry the
    collar's inner wall down until it meets the body so nothing can be seen through the gap."""
    f = jersey_field(b)
    part = mk.Part("trunk", "Jersey")
    # columns: front centre, the two edges of each under-arm side panel, back centre
    half_panel = 12.0
    anchors = np.radians([-90.0, -half_panel, half_panel, 90.0, 180.0 - half_panel, 180.0 + half_panel])
    counts = [14, 4, 14, 14, 4, 14]
    panel_cols = list(range(14, 18)) + list(range(46, 50))
    probe = np.radians(np.arange(-90.0, 270.0, 30.0))
    z_lo, z_f = 1.034, 1.455
    T1 = 0.7

    def horiz(zs):
        O = np.stack([np.zeros_like(zs), np.zeros_like(zs), zs], axis=1)
        P, _ = mk.sample_rings(f, O, rep(X, len(zs)), rep(Y, len(zs)), probe, T1)
        return P
    zs = adaptive(horiz, z_lo, z_f, 0.030, 0.008, 0.0012)

    # the collar: where the pad surface meets an ellipse round the neck
    col = b.collar
    dense = np.linspace(-math.pi, math.pi, 181)[:-1]
    sy = np.sin(dense)
    ex = col["a"] * np.cos(dense)
    ey = col["cy"] + np.where(sy < 0.0, col["bf"], col["bb"]) * sy
    t = sdf.march(f, np.stack([ex, ey, np.full_like(ex, 1.30)], axis=1), rep(Z, len(ex)), 0.0, 0.45, steps=160)
    phi_d = np.arctan2(1.30 + t - z_f, np.hypot(ex, ey))
    ang = np.arctan2(ey, ex)
    order = np.argsort(ang)
    ang_s, phi_s = ang[order], phi_d[order]

    def phi_end(th):
        return np.interp(th, ang_s, phi_s, period=TAU)

    def fan(ss):
        n = len(ss)
        P, _ = mk.sample_rings(f, rep([0.0, 0.0, z_f], n), rep(X, n), rep(Y, n), probe, T1,
                               W=rep(Z, n), phi=lambda th: ss[:, None] * phi_end(th))
        return P
    dense_s = np.linspace(0.0, 1.0, 101)
    Pd = fan(dense_s)
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(Pd, axis=0), axis=2).mean(axis=1))])
    band_w = 0.024
    s_band = float(np.interp(arc[-1] - band_w, arc, dense_s))
    ss = adaptive(fan, 0.0, 1.0, 0.10, 0.02, 0.0012, must=[s_band])[1:]
    i_band_fan = int(np.argmin(np.abs(ss - s_band)))

    nh, nf = len(zs), len(ss)
    O = np.vstack([np.stack([np.zeros(nh), np.zeros(nh), zs], axis=1), rep([0.0, 0.0, z_f], nf)])
    s_all = np.concatenate([np.zeros(nh), ss])
    R = nh + nf
    U, V, W = rep(X, R), rep(Y, R), rep(Z, R)
    phi = lambda th: s_all[:, None] * phi_end(th)
    thetas = mk.even_thetas(f, O, U, V, anchors, counts, T1, W=W, phi=phi)
    P, _ = mk.sample_rings(f, O, U, V, thetas, T1, W=W, phi=phi)

    # collar band: raised 2.5 mm from the ring at s_band to the neck opening, then a lip going in
    ib = nh + i_band_fan
    n_band = sdf.gradient(f, P[ib:].reshape(-1, 3)).reshape(P[ib:].shape)
    raised = P[ib:] + n_band * 0.0025
    C = raised[-1]
    centre = np.array([0.0, col["cy"], 0.0])
    d_in = centre[None, :] - C * np.array([1.0, 1.0, 0.0])
    d_in /= np.linalg.norm(d_in, axis=1)[:, None]
    lip1 = C + d_in * 0.004 - Z * 0.005
    down = d_in * 0.40 - Z
    down /= np.linalg.norm(down, axis=1)[:, None]
    lip2 = C + down * 0.030
    if under is not None:
        far = C + down * 0.16
        t = sdf.march(under, far, -down, 0.0, 0.16, mode="last", steps=64)
        reach = np.where(np.isnan(t), 0.030, np.clip(0.16 - t + 0.005, 0.012, 0.11))
        lip2 = C + down * reach[:, None]
    rings = np.concatenate([P[:ib + 1], raised, lip1[None], lip2[None]], axis=0)
    n_r = len(rings)
    face_mats = [[None] * sum(counts) for _ in range(n_r - 1)]
    face_tags = [["torso"] * sum(counts) for _ in range(n_r - 1)]
    for i in range(ib, n_r - 2):
        face_mats[i] = ["JerseyTrim"] * sum(counts)
        face_tags[i] = [None] * sum(counts)
    face_tags[n_r - 2] = [None] * sum(counts)          # inner wall of the neck hole: plain jersey
    # side panels run from the belt up into the armpit
    for i in range(nh - 1):
        if zs[i + 1] <= SIDE_PANEL_TOP:
            for j in panel_cols:
                face_mats[i][j] = "JerseyTrim"
                face_tags[i][j] = None
    idx = part.add_grid(rings, closed=True, chart="trunk", face_mats=face_mats, face_tags=face_tags)
    mark_ring_sharp(part, idx[ib]); mark_ring_sharp(part, idx[ib + 1])
    part.set_weights(skin.torso)
    info = dict(collar_ring=C, collar_z_front=float(C[:, 2].min()), collar_z_back=float(C[np.argmax(C[:, 1]), 2]))
    return part, info


# ======================================================================= shoulder cap + sleeve
SLEEVE_GAP = 0.0055          # cloth stand-off from the arm


def sleeve_field(b):
    S0, E = J["upperarm_l"], J["lowerarm_l"]
    n, fr, a = limb_frame(S0, E)
    R = np.stack([n, fr, a], axis=1)
    cap, sl = b.cap, b.sleeve
    arm_f, _ = arm_field(b)

    def f(p):
        q = sdf.local(p, S0, R)
        c = sdf.superellipsoid(q, (cap["off"], 0.0, cap["centre_s"]),
                               (cap["r_out"], cap["r_fb"], cap["half_len"]), (2.3, 2.4, 2.3))
        c = sdf.smax(c, -(q[:, 0] - cap["cut"]), 0.014)
        tube = sdf.smax(arm_f(p) - SLEEVE_GAP, q[:, 2] - (sl["end"] + 0.05), 0.01)
        ball = sdf.sphere(p, S0, sl["r0"] + 0.003)
        return sdf.smin(sdf.smin(tube, ball, 0.012), c, 0.012)
    return f, (n, fr, a)


def build_sleeve(b):
    """Left shoulder cap and sleeve; mirror for the right."""
    f, (n, fr, a) = sleeve_field(b)
    S0 = J["upperarm_l"]
    cap, sl = b.cap, b.sleeve
    part = mk.Part("sleeve_l", "Jersey")
    anchors = np.radians([0.0, 90.0, 180.0, 270.0])
    counts = [8, 7, 7, 8]
    S = sum(counts)
    probe = np.radians(np.arange(0.0, 360.0, 30.0))
    T1 = 0.22

    def rings(ss):
        O = S0[None, :] + ss[:, None] * a[None, :]
        P, _ = mk.sample_rings(f, O, rep(n, len(ss)), rep(fr, len(ss)), probe, T1)
        return P
    end = sl["end"]
    trim_w = 0.022
    ss = adaptive(rings, 0.0, end, 0.022, 0.004, 0.0010, must=[end - trim_w])
    cap_phi = np.radians([-72.0, -52.0, -33.0, -15.0])
    nc, ns = len(cap_phi), len(ss)
    O = np.vstack([rep(S0, nc), S0[None, :] + ss[:, None] * a[None, :]])
    phi = np.concatenate([cap_phi, np.zeros(ns)])
    R = nc + ns
    U, V, W = rep(n, R), rep(fr, R), rep(a, R)
    thetas = mk.even_thetas(f, O, U, V, anchors, counts, T1, W=W, phi=phi)
    P, _ = mk.sample_rings(f, O, U, V, thetas, T1, W=W, phi=phi)

    i_trim = nc + int(np.argmin(np.abs(ss - (end - trim_w))))
    radial = P[i_trim:] - O[i_trim:, None, :]
    radial /= np.linalg.norm(radial, axis=2)[:, :, None]
    raised = P[i_trim:] + radial * 0.002
    edge = raised[-1]
    lip = lip_onto(arm_field(b)[0], O[-1], edge) + a[None, :] * 0.001
    grid = np.concatenate([P[:i_trim + 1], raised, lip[None]], axis=0)
    n_r = len(grid)
    face_mats = [[None] * S for _ in range(n_r - 1)]
    face_tags = [[None] * S for _ in range(n_r - 1)]
    for i in range(i_trim, n_r - 1):
        face_mats[i] = ["JerseyTrim"] * S
    # faces on top of the cap carry the shoulder number
    s_ring = np.concatenate([np.full(nc, -1.0), ss[:i_trim - nc + 1]])
    cap_end = cap["centre_s"] + cap["half_len"]
    for i in range(len(s_ring) - 1):
        if s_ring[i] < -0.5 or s_ring[i + 1] > cap_end + 0.004:
            continue
        for j in range(S):
            th = 0.5 * (thetas[i, j] + thetas[i, (j + 1) % S] + (TAU if j == S - 1 else 0.0))
            th = (th + math.pi) % TAU - math.pi
            if abs(th) < math.radians(62.0):
                face_tags[i][j] = "cap_l"
    idx = part.add_grid(grid, closed=True, chart="sleeve", face_mats=face_mats, face_tags=face_tags)
    mark_ring_sharp(part, idx[i_trim]); mark_ring_sharp(part, idx[i_trim + 1])
    # close the hidden inner end
    pole_t = sdf.march(f, S0[None, :], -a[None, :], 0.0, T1)[0]
    U_, V_ = mk.grid_uv(grid, True)
    ring_uv = np.stack([U_[0], V_[0]], axis=1)
    part.add_fan(list(idx[0]), ring_uv, S0 - a * pole_t, float(V_[0, 0]) - 0.02, chart="sleeve", flip=True)
    def shoulder_weights(p):
        distance = (p - S0) @ a
        collar = 0.45 * (1.0 - sdf.smoothstep(-0.045, 0.085, distance))
        return {"clavicle_l": collar, "upperarm_l": 1.0 - collar}
    part.set_weights(shoulder_weights)

    # number panel on top of the cap: digits' tops toward the neck, read from the player's side
    mid_s = cap_end - 0.5 * PANEL_CAP["h"] - 0.004
    top = sdf.march(f, (S0 + a * mid_s)[None, :], n[None, :], 0.0, T1)[0]
    panel = dict(origin=S0 + a * mid_s + n * top, eu=-fr.copy(), ev=-a.copy(), w=PANEL_CAP["w"], h=PANEL_CAP["h"])
    return part, panel


# ===================================================================================== arm
UPPER_ROWS = [  # s, ws, df, db, ef, eb   (ws: half-width along the elbow hinge axis)
    (-0.03, 0.058, 0.058, 0.058, 2.0, 2.0),
    (0.06, 0.058, 0.059, 0.058, 2.0, 2.0),
    (0.12, 0.055, 0.060, 0.058, 2.0, 2.0),
    (0.17, 0.052, 0.061, 0.055, 2.0, 2.0),
    (0.22, 0.047, 0.054, 0.048, 2.0, 2.0),
    (0.265, 0.0435, 0.043, 0.0445, 2.0, 2.1),
    (0.30, 0.0465, 0.039, 0.047, 2.0, 2.2),      # elbow: wide across the hinge, flat in the crease
    (0.34, 0.046, 0.042, 0.045, 2.0, 2.1),
]
LOWER_ROWS = [  # d from the elbow
    (-0.04, 0.0445, 0.040, 0.046, 2.0, 2.2),
    (0.00, 0.0465, 0.040, 0.047, 2.0, 2.2),
    (0.04, 0.0495, 0.052, 0.0475, 2.0, 2.1),     # the forearm swells below the elbow ...
    (0.08, 0.0480, 0.052, 0.0455, 2.0, 2.0),
    (0.125, 0.0425, 0.046, 0.0405, 2.0, 2.0),
    (0.17, 0.0360, 0.040, 0.0365, 2.1, 2.1),
    (0.22, 0.0290, 0.035, 0.0330, 2.3, 2.3),     # ... and flattens into the wrist
    (0.27, 0.0250, 0.033, 0.0310, 2.4, 2.4),
    (0.30, 0.0250, 0.033, 0.0310, 2.4, 2.4),
]
ARM_COLS = ("t", "ws", "df", "db", "ef", "eb")


def arm_field(b):
    S0, E, Wr = J["upperarm_l"], J["lowerarm_l"], J["hand_l"]
    n1, f1, a1 = limb_frame(S0, E)
    n2, f2, a2 = limb_frame(E, Wr)
    R1 = np.stack([n1, f1, a1], axis=1)
    R2 = np.stack([n2, f2, a2], axis=1)
    up = sdf.Table(ARM_COLS, UPPER_ROWS)
    lo = sdf.Table(ARM_COLS, LOWER_ROWS)
    g = b.arm
    L1 = float(np.linalg.norm(E - S0))

    def g_low(t):                      # wrists do not bulk up the way biceps do
        return 1.0 + (g - 1.0) * (1.0 - 0.6 * sdf.smoothstep(0.03, 0.26, t))

    def f(p):
        u = sdf.section_tube(p, S0, R1, up, girth=g, lo=-0.03, hi=L1 + 0.03, cap=0.02)
        l = sdf.section_tube(p, E, R2, lo, girth=g_low, lo=-0.035, hi=0.30, cap=0.02)
        d = sdf.smin(u, l, 0.012)
        # muscle and bone landmarks, so the arm reads as an arm and not a tube
        bic = sdf.ellipsoid(p, S0 + a1 * 0.170 + f1 * 0.029 * g, np.array([0.036, 0.036, 0.074]) * [g, g, 1.0], R1)
        tri = sdf.ellipsoid(p, S0 + a1 * 0.125 - f1 * 0.025 * g + n1 * 0.012 * g, np.array([0.034, 0.032, 0.076]) * [g, g, 1.0], R1)
        brach = sdf.ellipsoid(p, E + a2 * 0.050 + f2 * 0.021 * g + n2 * 0.004 * g,
                              np.array([0.030, 0.031, 0.074]) * [g, g, 1.0], R2)
        ext = sdf.ellipsoid(p, E + a2 * 0.062 - f2 * 0.008 * g + n2 * 0.019 * g,
                            np.array([0.028, 0.030, 0.066]) * [g, g, 1.0], R2)
        flex = sdf.ellipsoid(p, E + a2 * 0.070 + f2 * 0.004 * g - n2 * 0.019 * g,
                             np.array([0.028, 0.032, 0.070]) * [g, g, 1.0], R2)
        elbow = sdf.ellipsoid(p, E - f2 * 0.037 * g - a2 * 0.004, np.array([0.0165, 0.0150, 0.0215]) * g, R2)
        for blob, k in ((bic, 0.014), (tri, 0.014), (brach, 0.014), (ext, 0.014), (flex, 0.014), (elbow, 0.009)):
            d = sdf.smin(d, blob, k)
        return d
    return f, L1


def build_arm(b):
    """Left bare arm from inside the sleeve to inside the glove cuff, with a wristband."""
    f, L1 = arm_field(b)
    chain = Chain([J["upperarm_l"], J["lowerarm_l"], J["hand_l"]], blend=0.035)
    part = mk.Part("arm_l", "Skin")
    anchors = np.radians([0.0, 90.0, 180.0, 270.0])
    counts = [6, 6, 6, 6]
    S = sum(counts)
    probe = np.radians(np.arange(0.0, 360.0, 45.0))
    T1 = 0.16
    d0 = b.sleeve["end"] - 0.045
    band0, band1 = L1 + 0.176, L1 + 0.228
    bare = L1 - b.sleeve["end"]                       # bare upper arm between the cuff and the elbow
    bic0 = b.sleeve["end"] + float(np.clip(0.4 * bare - 0.008, 0.012, 0.034))
    bic1 = bic0 + 0.016
    d1 = L1 + 0.262

    def rings(ds):
        O, Sd, F, _ = chain.at(ds)
        P, _ = mk.sample_rings(f, O, Sd, F, probe, T1)
        return P
    must = [L1 + x for x in (-0.055, -0.038, -0.024, -0.012, 0.0, 0.012, 0.024, 0.038, 0.055)] + [band0, band1, bic0, bic1]
    ds = adaptive(rings, d0, d1, 0.030, 0.009, 0.0010, must=must)
    O, Sd, F, _ = chain.at(ds)
    thetas = mk.even_thetas(f, O, Sd, F, anchors, counts, T1)
    P, _ = mk.sample_rings(f, O, Sd, F, thetas, T1)
    radial = P - O[:, None, :]
    radial /= np.linalg.norm(radial, axis=2)[:, :, None]
    # raised bands: a thin one round the biceps and a wide sweatband above the glove
    rows, mats, sharp = [], [], []
    bands = [(bic0, bic1, 0.0026), (band0, band1, 0.0032)]
    for i in range(len(ds)):
        lift = 0.0
        for a0, a1, h in bands:
            if a0 - 1e-9 <= ds[i] <= a1 + 1e-9:
                lift = h
        starts = [h for a0, a1, h in bands if abs(ds[i] - a0) < 1e-9]
        ends = [h for a0, a1, h in bands if abs(ds[i] - a1) < 1e-9]
        if starts:                       # step up: plain ring, then the lifted ring
            rows.append(P[i]); mats.append("Bands"); sharp.append(len(rows) - 1)
            rows.append(P[i] + radial[i] * starts[0]); mats.append("Bands"); sharp.append(len(rows) - 1)
        elif ends:                       # step down: lifted ring, then the plain ring
            rows.append(P[i] + radial[i] * ends[0]); mats.append("Bands"); sharp.append(len(rows) - 1)
            rows.append(P[i]); mats.append(None); sharp.append(len(rows) - 1)
        else:
            rows.append(P[i] + radial[i] * lift); mats.append("Bands" if lift > 0.0 else None)
    grid = np.stack(rows, axis=0)
    n_r = len(grid)
    face_mats = [[mats[i]] * S for i in range(n_r - 1)]
    idx = part.add_grid(grid, closed=True, chart="arm", face_mats=face_mats)
    for r in sharp:
        mark_ring_sharp(part, idx[r])
    part.set_weights(lambda p: skin.arm(p, "l"))
    return part


# =================================================================================== pants
THIGH_COLS = ("t", "wo", "wi", "df", "db", "ef", "eb", "cf")
THIGH_ROWS = [
    (-0.10, 0.078, 0.080, 0.084, 0.088, 2.2, 2.2, 0.000),
    (0.00, 0.083, 0.090, 0.094, 0.098, 2.2, 2.2, 0.004),
    (0.06, 0.085, 0.092, 0.098, 0.097, 2.2, 2.2, 0.008),
    (0.15, 0.084, 0.086, 0.098, 0.090, 2.2, 2.2, 0.010),
    (0.25, 0.077, 0.076, 0.089, 0.080, 2.2, 2.2, 0.009),
    (0.33, 0.068, 0.067, 0.077, 0.069, 2.2, 2.2, 0.006),
    (0.39, 0.061, 0.060, 0.066, 0.061, 2.2, 2.2, 0.004),
    (0.42, 0.058, 0.058, 0.063, 0.058, 2.3, 2.2, 0.003),
    (0.50, 0.056, 0.056, 0.058, 0.060, 2.2, 2.2, 0.000),
]
CALF_COLS = ("t", "ws", "df", "db", "ef", "eb")
CALF_ROWS = [
    (-0.08, 0.055, 0.056, 0.056, 2.1, 2.1),
    (0.00, 0.054, 0.054, 0.056, 2.1, 2.1),
    (0.06, 0.058, 0.051, 0.064, 2.1, 2.0),
    (0.13, 0.060, 0.048, 0.071, 2.2, 2.0),
    (0.20, 0.054, 0.045, 0.063, 2.2, 2.0),
    (0.28, 0.044, 0.040, 0.049, 2.1, 2.0),
    (0.35, 0.037, 0.037, 0.040, 2.0, 2.0),
    (0.40, 0.035, 0.037, 0.040, 2.0, 2.0),
    (0.46, 0.036, 0.040, 0.042, 2.0, 2.0),
]
STRIPE_HALF = 0.019
STRIPE_SHIFT = -0.004        # stripe centre, metres toward the back of the leg's axis


def leg_fields(b):
    """(thigh, calf) fields of the LEFT leg plus the frames they live in."""
    H, K, A = J["thigh_l"], J["calf_l"], J["foot_l"]
    st, ft, at = limb_frame(H, K)
    sc, fc, ac = limb_frame(K, A)
    Rt = np.stack([st, ft, at], axis=1)
    Rc = np.stack([sc, fc, ac], axis=1)
    thigh_tab = sdf.Table(THIGH_COLS, THIGH_ROWS)
    calf_tab = sdf.Table(CALF_COLS, CALF_ROWS)
    gt, gc = b.thigh, b.calf

    def g_thigh(t):                    # knees stay closer to bone size
        return 1.0 + (gt - 1.0) * (1.0 - 0.45 * sdf.smoothstep(0.24, 0.42, t))

    def g_calf(t):
        return 1.0 + (gc - 1.0) * (1.0 - 0.6 * sdf.smoothstep(0.22, 0.38, t))

    def inner_limit(t):
        return H[0] + at[0] * t - 0.005

    def thigh(p):
        return sdf.section_tube(p, H, Rt, thigh_tab, girth=g_thigh, inner_limit=inner_limit, lo=-0.11, hi=0.52, cap=0.02)

    def calf(p):
        return sdf.section_tube(p, K, Rc, calf_tab, girth=g_calf, lo=-0.09, hi=0.47, cap=0.02)
    return thigh, calf, (H, K, A, Rt, Rc)


def pants_field(b):
    core = core_field(b)
    thigh, calf, (H, K, A, Rt, Rc) = leg_fields(b)
    gl = b.glute
    thick = b.pad_thick

    def leg(p):
        t = thigh(p)
        c = calf(p) - 0.005
        base = sdf.smin(t, c, 0.02)
        q = sdf.local(p, H, Rt)
        front = -(q[:, 1] - 0.025)
        # thigh pad: a rounded plate standing off the front of the thigh
        reg = np.maximum(rbox2(q[:, 0] - 0.004, q[:, 2] - 0.205, 0.062 * b.thigh, 0.100, 0.035), front)
        pad = sdf.smax(t - thick, reg, 0.012)
        # knee pad
        reg = np.maximum(rbox2(q[:, 0], q[:, 2] - 0.418, 0.047 * (0.5 + 0.5 * b.thigh), 0.056, 0.030), front)
        kpad = sdf.smax(base - thick, reg, 0.012)
        return sdf.smin(sdf.smin(base, pad, 0.008), kpad, 0.008)

    def f(p):
        legs = np.minimum(leg(p), leg(p * MIRROR))
        q = p.copy(); q[:, 0] = np.abs(q[:, 0])
        hips = sdf.smin(core(p) - 0.004, sdf.ellipsoid(q, gl["c"], gl["r"]), 0.035)
        hips = sdf.smax(hips, b.crotch_z - p[:, 2], 0.035)
        return sdf.smin(hips, legs, 0.035)
    return f


def build_pants(b):
    f = pants_field(b)
    part = mk.Part("pants", "Pants")
    H, K, A = J["thigh_l"], J["calf_l"], J["foot_l"]
    N_FRONT, N_STRIPE, N_BACK, N_INNER = 11, 2, 11, 8
    N_HALF = N_FRONT + N_STRIPE + N_BACK                # 24
    NP = 2 * N_HALF                                     # pelvis ring: 48
    NL = N_HALF + N_INNER                               # leg ring: 32
    T1 = 0.45
    z_top, z_belt = 1.078, 1.046
    z_c = b.crotch_z + 0.030

    # ---- pelvis rings (top -> crotch level)
    def stripe_edges(O, U, V, lat_of):
        """Angles on each ring where the surface is STRIPE_HALF either side of the stripe line."""
        th = np.radians(np.linspace(-65.0, 65.0, 131))
        P, _ = mk.sample_rings(f, O, U, V, th, T1, mode=lat_of[1])
        lat = lat_of[0](P)
        lo = np.array([np.interp(-STRIPE_HALF, lat[r], th) for r in range(len(O))])
        hi = np.array([np.interp(STRIPE_HALF, lat[r], th) for r in range(len(O))])
        return lo, hi

    probe = np.radians(np.arange(-90.0, 270.0, 30.0))

    def horiz(zs):
        O = np.stack([np.zeros_like(zs), np.zeros_like(zs), zs], axis=1)
        P, _ = mk.sample_rings(f, O, rep(X, len(zs)), rep(Y, len(zs)), probe, T1)
        return P
    zs_body = adaptive(horiz, z_c, z_belt - 0.0006, 0.030, 0.010, 0.0012)[::-1]
    zs = np.concatenate([[z_top - 0.004, z_top, z_belt], zs_body])
    offs = np.concatenate([[-0.009, 0.003, 0.003], np.zeros(len(zs_body))])
    n_p = len(zs)
    O = np.stack([np.zeros(n_p), np.zeros(n_p), zs], axis=1)
    U, V = rep(X, n_p), rep(Y, n_p)
    lo, hi = stripe_edges(O, U, V, (lambda P: P[:, :, 1] - STRIPE_SHIFT, "last"))
    anchors = np.stack([np.full(n_p, -0.5 * math.pi), lo, hi, np.full(n_p, 0.5 * math.pi),
                        math.pi - hi, math.pi - lo], axis=1)
    counts = [N_FRONT, N_STRIPE, N_BACK, N_BACK, N_STRIPE, N_FRONT]
    thetas = mk.even_thetas(f, O, U, V, anchors, counts, T1)
    Pp, _ = mk.sample_rings(f, O, U, V, thetas, T1)
    dirs = mk.ring_dirs(U, V, thetas)
    Pp = Pp + dirs * offs[:, None, None]
    face_mats = [[None] * NP for _ in range(n_p - 1)]
    for i in range(n_p - 1):
        if i < 3:
            face_mats[i] = ["Belt"] * NP
        else:
            for j in list(range(N_FRONT, N_FRONT + N_STRIPE)) + list(range(NP - N_FRONT - N_STRIPE, NP - N_FRONT)):
                face_mats[i][j] = "PantsStripe"
    idx_p = part.add_grid(Pp, closed=True, chart="pelvis", face_mats=face_mats)
    for r in (1, 2, 3):
        mark_ring_sharp(part, idx_p[r])

    # ---- the crotch line: from the front-centre vertex, under, to the back-centre vertex
    beta = np.linspace(0.0, math.pi, 121)
    Oc = rep([0.0, 0.0, z_c], len(beta))
    Dc = np.stack([np.zeros_like(beta), -np.cos(beta), -np.sin(beta)], axis=1)
    tb = sdf.march(f, Oc, Dc, 0.0, 0.3, mode="first")
    line = Oc + Dc * tb[:, None]
    seg = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))])
    want = seg[-1] * np.arange(1, N_INNER) / N_INNER
    bridge = np.stack([np.interp(want, seg, line[:, k]) for k in range(3)], axis=1)   # front -> back
    idx_b = part.add_verts(bridge) + np.arange(N_INNER - 1)

    # ---- left leg rings
    chain = Chain([H, K, A], blend=0.04)
    Lt = float(np.linalg.norm(K - H))
    d_first = (H[2] - (b.crotch_z - 0.020)) / abs(chain.dir[0][2])
    d_hem = Lt + (K[2] - 0.462) / abs(chain.dir[1][2])
    def leg_frames(ds):
        # the first rings under the crotch tilt up toward the hip so they follow the split ring
        Ol, Sd, F, T = chain.at(ds)
        tilt = math.radians(6.0) * (1.0 - sdf.smoothstep(0.0, 0.055, np.asarray(ds) - d_first))
        Ul = np.cos(tilt)[:, None] * Sd - np.sin(tilt)[:, None] * T
        return Ol, Ul, -F

    def leg_rings(ds):
        Ol, Ul, Vl = leg_frames(ds)
        P, _ = mk.sample_rings(f, Ol, Ul, Vl, np.radians(np.arange(-150.0, 180.0, 30.0)), 0.25, mode="first")
        return P
    must = [d_first + 0.024] + [Lt + x for x in (-0.066, -0.044, -0.024, -0.006, 0.012, 0.030, 0.048)]
    ds = adaptive(leg_rings, d_first, d_hem, 0.036, 0.010, 0.0012, must=must)
    Ol, Ul, Vl = leg_frames(ds)
    n_l = len(ds)
    lo, hi = stripe_edges(Ol, Ul, Vl, (lambda P: np.einsum("rsk,rk->rs", P - Ol[:, None, :], Vl) - STRIPE_SHIFT, "first"))
    a_in = math.radians(135.0)
    anchors = np.stack([np.full(n_l, -a_in), lo, hi, np.full(n_l, a_in)], axis=1)
    counts = [N_FRONT, N_STRIPE, N_BACK, N_INNER]
    thetas = mk.even_thetas(f, Ol, Ul, Vl, anchors, counts, 0.25, mode="first")
    Pl, _ = mk.sample_rings(f, Ol, Ul, Vl, thetas, 0.25, mode="first")
    Pl[:, :, 0] = np.maximum(Pl[:, :, 0], 0.0025)
    # hem: a short lip turning in under the pants so the edge has thickness
    lip = lip_onto(leg_fields(b)[1], Ol[-1], Pl[-1], inside=0.009, hi=0.045) + Z * 0.0015
    Pl = np.concatenate([Pl, lip[None]], axis=0)
    n_l += 1

    split = idx_p[-1]
    ring0_l = np.concatenate([split[:N_HALF + 1], idx_b[::-1]])
    ring0_r = np.concatenate([split[(NP - np.arange(N_HALF + 1)) % NP], idx_b[::-1]])
    P0_l = part.v[ring0_l]
    P0_r = part.v[ring0_r]
    for side, ring0, P0, sign in (("l", ring0_l, P0_l, 1.0), ("r", ring0_r, P0_r, -1.0)):
        Pleg = np.concatenate([P0[None], Pl * np.array([sign, 1.0, 1.0])], axis=0)
        idx = np.full((n_l + 1, NL), -1, dtype=int)
        idx[0] = ring0
        fm = [[None] * NL for _ in range(n_l)]
        for i in range(n_l - 1):
            for j in range(N_FRONT, N_FRONT + N_STRIPE):
                fm[i][j] = "PantsStripe"
        part.add_grid(Pleg, closed=True, chart="leg_" + side, face_mats=fm, idx=idx)
    part.set_weights(lambda p: skin.lower_body(p, b.crotch_z))
    return part


# ==================================================================================== sock
def build_sock(b):
    """Left sock: from under the pants hem down into the shoe."""
    thigh, calf, (H, K, A, Rt, Rc) = leg_fields(b)
    part = mk.Part("sock_l", "Socks")
    chain = Chain([K, A, A + sdf.unit(A - K) * 0.08])
    anchors = np.radians([0.0, 90.0, 180.0, 270.0])
    counts = [5, 5, 5, 5]
    probe = np.radians(np.arange(0.0, 360.0, 45.0))

    def rings(ds):
        O, Sd, F, _ = chain.at(ds)
        P, _ = mk.sample_rings(calf, O, Sd, F, probe, 0.15)
        return P
    ds = adaptive(rings, -0.030, 0.435, 0.040, 0.012, 0.0012)
    O, Sd, F, _ = chain.at(ds)
    thetas = mk.even_thetas(calf, O, Sd, F, anchors, counts, 0.15)
    P, _ = mk.sample_rings(calf, O, Sd, F, thetas, 0.15)
    part.add_grid(P, closed=True, chart="sock")
    part.set_weights(lambda p: skin.leg(p, "l"))
    return part
