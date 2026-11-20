"""Gloved hands: palm with cuff and strap, four separate fingers and a thumb.

The knuckles share a curl control. Each finger has separately weighted middle and tip joints.
"""
import math
import numpy as np

from furylib.rig import FINGERS
from . import meshkit as mk
from . import sdf, skin
from .body import adaptive, rep, Chain, arm_field, mark_ring_sharp, lip_onto, X, Y, Z, FRONT, TAU
from .params import J, TAIL

OVERSIZE = 1.10


def hand_frame():
    """(w toward the thumb, p out of the palm, h along the hand) for the LEFT hand."""
    Wr = J["hand_l"]
    h = sdf.unit(TAIL["hand_l"] - Wr)
    p = -X - (-X @ h) * h
    p = sdf.unit(p)
    w = np.cross(p, h)
    return Wr, w, p, h


def glove_field(b):
    Wr, w, p, h = hand_frame()
    R = np.stack([w, p, h], axis=1)
    g = OVERSIZE * b.glove
    arm_f, L1 = arm_field(b)
    E = J["lowerarm_l"]
    a2 = sdf.unit(Wr - E)
    L2 = float(np.linalg.norm(Wr - E))

    knuckle_w = [x[1] for x in FINGERS]

    def f(p_):
        q = sdf.local(p_, Wr, R)
        palm = sdf.superellipsoid(q, (0.003 * g, 0.0, 0.047), (0.0485 * g, 0.0175 * g, 0.058), (3.2, 2.3, 3.6))
        thenar = sdf.ellipsoid(q, (0.031 * g, 0.011 * g, 0.036), (0.023 * g, 0.017 * g, 0.035))
        hypo = sdf.ellipsoid(q, (-0.032 * g, 0.009 * g, 0.044), (0.015 * g, 0.013 * g, 0.039))
        d = sdf.smin(palm, thenar, 0.012)
        d = sdf.smin(d, hypo, 0.010)
        # padded panel on the back of the hand and a ridge over the knuckles
        pad = sdf.superellipsoid(q, (0.001 * g, -0.0150 * g, 0.052), (0.034 * g, 0.0075 * g, 0.031), (3.6, 2.0, 3.6))
        d = sdf.smin(d, pad, 0.0035)
        for wo in knuckle_w:
            kn = sdf.ellipsoid(q, (wo * g, -0.0135 * g, 0.0965), (0.0098 * g, 0.0070 * g, 0.0105))
            d = sdf.smin(d, kn, 0.004)
        along = (p_ - E) @ a2
        cuff = sdf.smax(arm_f(p_) - 0.0050, np.maximum((L2 - 0.062) - along, along - (L2 + 0.02)), 0.006)
        return sdf.smin(d, cuff, 0.014)
    return f, g


def _digit(part, axis_pts, r0, r1, chart, w_dir, sides=8, joints=None):
    """Round-tipped tube along a smooth axis; slightly wider than it is thick."""
    pts = mk.resample_polyline(mk.catmull(axis_pts, per_seg=6), spacing=0.0072)
    n = len(pts)
    radii = np.linspace(r0, r1, n)
    if joints is not None:
        seg = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        for jd in joints:
            radii = radii * (1.0 + 0.075 * sdf.bump(seg, jd, 0.011))
    T, N, B = mk.transport_frames(pts, w_dir)
    tip_r = radii[-1]
    extra = [(math.sin(math.radians(a)) * tip_r, math.cos(math.radians(a)) * tip_r) for a in (32.0, 58.0, 78.0)]
    centres = list(pts) + [pts[-1] + T[-1] * off for off, _ in extra]
    rads = list(radii) + [rr for _, rr in extra]
    Nn = list(N) + [N[-1]] * 3
    Bn = list(B) + [B[-1]] * 3
    ang = TAU * np.arange(sides) / sides
    P = np.stack([c[None, :] + rr * (1.07 * np.cos(ang)[:, None] * nn[None, :] + 0.95 * np.sin(ang)[:, None] * bb[None, :])
                  for c, rr, nn, bb in zip(centres, rads, Nn, Bn)], axis=0)
    idx = part.add_grid(P, closed=True, chart=chart)
    U_, V_ = mk.grid_uv(P, True)
    part.add_fan(list(idx[-1]), np.stack([U_[-1], V_[-1]], axis=1), pts[-1] + T[-1] * tip_r,
                 float(V_[-1, 0]) + 0.004, chart=chart, flip=not mk.grid_faces_outward(P, True))
    return idx


def build_hand(b):
    """Left glove. Mirror for the right."""
    f, g = glove_field(b)
    Wr, w, p, h = hand_frame()
    E = J["lowerarm_l"]
    L2 = float(np.linalg.norm(Wr - E))
    part = mk.Part("glove_l", "Gloves")

    # ---- palm + cuff: rings along the forearm/hand axis
    chain = Chain([E, Wr, Wr + h * 0.2], blend=0.02)
    d0, d1 = L2 - 0.060, L2 + 0.090
    strap0, strap1 = L2 - 0.047, L2 - 0.027
    probe = np.radians(np.arange(0.0, 360.0, 30.0))
    T1 = 0.12

    def frames(ds):
        O, Sd, F, T = chain.at(ds)
        return O, Sd, F, T

    def rings(ds):
        O, Sd, F, _ = frames(ds)
        P, _ = mk.sample_rings(f, O, Sd, F, probe, T1)
        return P
    ds = adaptive(rings, d0, d1, 0.014, 0.005, 0.0008, must=[strap0, strap1])
    O, Sd, F, T = frames(ds)
    cap_phi = np.radians([24.0, 46.0, 66.0, 82.0])
    n_s, n_c = len(ds), len(cap_phi)
    O_all = np.vstack([O, rep(O[-1], n_c)])
    U_all = np.vstack([Sd, rep(Sd[-1], n_c)])
    V_all = np.vstack([F, rep(F[-1], n_c)])
    W_all = np.vstack([T, rep(T[-1], n_c)])
    phi = np.concatenate([np.zeros(n_s), cap_phi])
    anchors = np.radians([0.0, 90.0, 180.0, 270.0])
    counts = [5, 5, 5, 5]
    S = sum(counts)
    thetas = mk.even_thetas(f, O_all, U_all, V_all, anchors, counts, T1, W=W_all, phi=phi)
    P, _ = mk.sample_rings(f, O_all, U_all, V_all, thetas, T1, W=W_all, phi=phi)
    i0 = int(np.argmin(np.abs(ds - strap0))); i1 = int(np.argmin(np.abs(ds - strap1)))
    radial = P - O_all[:, None, :]
    radial /= np.linalg.norm(radial, axis=2)[:, :, None]
    lip = lip_onto(arm_field(b)[0], O_all[0], P[0])
    grid = np.concatenate([lip[None], P[:i0 + 1], P[i0:i1 + 1] + radial[i0:i1 + 1] * 0.0034, P[i1:]], axis=0)
    idx = part.add_grid(grid, closed=True, chart="palm")
    for r in (i0 + 1, i0 + 2, i1 + 2, i1 + 3):
        mark_ring_sharp(part, idx[r])
    tip_t = sdf.march(f, O[-1][None, :], T[-1][None, :], 0.0, T1)[0]
    U_, V_ = mk.grid_uv(grid, True)
    part.add_fan(list(idx[-1]), np.stack([U_[-1], V_[-1]], axis=1), O[-1] + T[-1] * tip_t, float(V_[-1, 0]) + 0.006,
                 chart="palm", flip=not mk.grid_faces_outward(grid, True))

    digits_by_name = {}
    n_palm = len(part.v)
    # ---- fingers
    for name, wo, ho, lens, r, splay, curls in FINGERS:
        base = Wr + w * (wo * g) + h * ho + p * 0.0015
        s = math.radians(splay)
        d = math.cos(s) * h + math.sin(s) * w
        side = np.cross(p, d)                 # this finger's own "toward the thumb" axis
        pts = [base - d * 0.016, base - d * 0.004]
        cur = base.copy()
        ang = 0.0
        for L, c in zip(lens, curls):
            ang += math.radians(c)
            dd = math.cos(ang) * d + math.sin(ang) * p
            cur = cur + dd * (L * g)
            pts.append(cur.copy())
        rr = r * g
        j1 = 0.012 + lens[0] * g
        start = len(part.v)
        _digit(part, np.array(pts), rr * 1.04, rr * 0.90, ("finger", name), side, joints=(j1, j1 + lens[1] * g))

        digits_by_name[name] = (slice(start, len(part.v)), pts[2], pts[3], pts[4])

    n_fingers = len(part.v)
    # ---- thumb
    T0 = J["thumb_l"]
    dt = sdf.unit(TAIL["thumb_l"] - T0)
    bend = sdf.unit(dt + 0.22 * h - 0.10 * w + 0.16 * p)
    pts = [T0 - dt * 0.022, T0 - dt * 0.004, T0 + dt * (0.038 * g), T0 + dt * (0.038 * g) + bend * (0.031 * g)]
    _digit(part, np.array(pts), 0.0145 * g, 0.0122 * g, ("thumb",), np.cross(p, dt), joints=(0.018 + 0.038 * g,))

    # ---- skin: wrist blend on the cuff, then each digit hinges at its own root
    V = part.v
    wa = skin.arm(V, "l")
    lower, hand = wa["lowerarm_l"] + wa["upperarm_l"], wa["hand_l"]
    d_f = (V - J["fingers_l"]) @ h
    along_t = (V - T0) @ dt
    kind = np.zeros(len(V), dtype=int)
    kind[n_palm:n_fingers] = 1
    kind[n_fingers:] = 2
    # the palm stays whole; each finger hinges inside it, so a fist shows knuckles, not stretch
    w_f = np.where(kind == 1, sdf.smoothstep(-0.011, 0.007, d_f), 0.0)
    w_t = np.where(kind == 2, sdf.smoothstep(-0.010, 0.008, along_t), 0.0)
    digits = kind > 0
    lower = np.where(digits, 0.0, lower)
    hand = np.where(digits, 1.0, hand)
    part.w = {"lowerarm_l": lower, "hand_l": hand * (1.0 - w_f - w_t), "fingers_l": hand * w_f, "thumb_l": hand * w_t}
    # Ease the glove into the knuckles, then distribute curl across the two tip joints.
    palm_bend = np.where(kind == 0, 0.32 * sdf.smoothstep(-0.035, 0.012, d_f), 0.0)
    transfer = palm_bend * part.w["hand_l"]
    part.w["hand_l"] -= transfer
    part.w["fingers_l"] += transfer
    for name, (rows, pip, dip, tip) in digits_by_name.items():
        shaft = sdf.unit(tip - pip)
        for joint, point in enumerate((pip, dip), 1):
            child = f"{name}_{joint}_l"
            parent = "fingers_l" if joint == 1 else f"{name}_1_l"
            weights = np.zeros(len(V))
            weights[rows] = part.w[parent][rows] * sdf.smoothstep(-0.007, 0.007, (V[rows] - point) @ shaft)
            part.w[parent] -= weights
            part.w[child] = weights
    return part
