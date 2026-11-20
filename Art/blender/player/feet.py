"""Cleats: upper (Shoes), sole plate and studs (ShoeSole).

The upper is lofted like a bent tube: straight sections along the forefoot, then sections that
fan round the heel about a line above the instep, ending at the padded ankle collar.
"""
import math
import numpy as np

from . import meshkit as mk
from . import sdf, skin
from .body import adaptive, rep, leg_fields, lip_onto, X, Y, Z, FRONT, TAU
from .params import J

XC = float(J["foot_l"][0])            # 0.105: the foot's centre line
SOLE_TOP, SOLE_BOT = 0.0235, 0.0110
CUT_Z = 0.0210
TOE_CAP_Y = -0.168
PIVOT = np.array([XC, -0.072, 0.150])
OVERSIZE = 1.06


def spring(y):
    """Toe spring: how far the front of the shoe curls up off the ground."""
    return 0.016 * sdf.smoothstep(-0.150, -0.232, y) ** 2


def upper_field(b):
    g = OVERSIZE
    cx = XC

    def f(p):
        fore = sdf.superellipsoid(p, (cx + 0.003, -0.132, 0.0450), (0.0510 * g, 0.094, 0.0285), (2.6, 2.4, 2.5))
        mid = sdf.ellipsoid(p, (cx, -0.040, 0.066), (0.0435 * g, 0.092, 0.046))
        heel = sdf.ellipsoid(p, (cx, 0.046, 0.058), (0.0375 * g, 0.043, 0.048))
        collar = sdf.cone(p, (cx, 0.013, 0.065), (cx, 0.010, 0.175), 0.0475, 0.0455)
        d = sdf.smin(fore, mid, 0.022)
        d = sdf.smin(d, heel, 0.022)
        d = sdf.smin(d, collar, 0.020)
        toe = sdf.superellipsoid(p, (cx + 0.003, -0.190, 0.0415), (0.0445 * g, 0.036, 0.0255), (2.6, 2.3, 2.5))
        d = sdf.smin(d, toe - 0.0012, 0.006)
        # heel counter: a stiff cup round the back of the heel
        cup = sdf.smax(heel - 0.0030, np.maximum(-(p[:, 1] - 0.030), p[:, 2] - 0.088), 0.004)
        d = sdf.smin(d, cup, 0.002)
        return sdf.smax(d, CUT_Z - p[:, 2], 0.004)
    return f


def build_shoe(b):
    """Left cleat. Mirror for the right."""
    f = upper_field(b)
    up = mk.Part("shoe_l", "Shoes")
    T1 = 0.2
    y_p = float(PIVOT[1])
    z_ax = 0.046
    rho0, rho1, a_end = PIVOT[2] - z_ax, 0.088, math.radians(80.0)
    y_a0 = -0.186
    probe = np.radians(np.arange(-90.0, 270.0, 30.0))

    def frame_a(ys):
        O = np.stack([np.full_like(ys, XC), ys, np.full_like(ys, z_ax)], axis=1)
        return O, rep(X, len(ys)), rep(Z, len(ys))

    def frame_b(al):
        rho = rho0 + (rho1 - rho0) * (al / a_end)
        rad = np.stack([np.zeros_like(al), np.sin(al), -np.cos(al)], axis=1)
        O = PIVOT[None, :] + rad * rho[:, None]
        return O, rep(X, len(al)), -rad

    def rings_a(ys):
        O, U, V = frame_a(ys)
        return mk.sample_rings(f, O, U, V, probe, T1)[0]

    def rings_b(al):
        O, U, V = frame_b(al)
        return mk.sample_rings(f, O, U, V, probe, T1)[0]
    ys = adaptive(rings_a, y_a0, y_p, 0.022, 0.008, 0.0010, must=[TOE_CAP_Y])
    al = adaptive(rings_b, 0.0, a_end, math.radians(14.0), math.radians(5.0), 0.0010)[1:]
    cap_phi = np.radians([76.0, 56.0, 36.0, 17.0])
    Oa, Ua, Va = frame_a(ys)
    Ob, Ub, Vb = frame_b(al)
    nc = len(cap_phi)
    O = np.vstack([rep(Oa[0], nc), Oa, Ob])
    U = np.vstack([rep(X, nc), Ua, Ub])
    V = np.vstack([rep(Z, nc), Va, Vb])
    W = np.vstack([rep(FRONT, nc + len(ys)), np.cross(Ub, Vb)])
    phi = np.concatenate([cap_phi, np.zeros(len(ys) + len(al))])
    anchors = np.radians([-90.0, 0.0, 90.0, 180.0])
    counts = [6, 6, 6, 6]
    thetas = mk.even_thetas(f, O, U, V, anchors, counts, T1, W=W, phi=phi)
    P, _ = mk.sample_rings(f, O, U, V, thetas, T1, W=W, phi=phi)
    # toe cap: everything ahead of the cap line stands 1.6 mm proud, with a crisp step
    i_cap = nc + int(np.argmin(np.abs(ys - TOE_CAP_Y)))
    nrm = sdf.gradient(f, P[:i_cap + 1].reshape(-1, 3)).reshape(P[:i_cap + 1].shape)
    P = np.concatenate([P[:i_cap + 1] + nrm * 0.0016, P[i_cap:]], axis=0)
    O = np.concatenate([O[:i_cap + 1], O[i_cap:]], axis=0)
    U = np.concatenate([U[:i_cap + 1], U[i_cap:]], axis=0)
    V = np.concatenate([V[:i_cap + 1], V[i_cap:]], axis=0)
    # padded collar: roll the top edge inward and down
    radial = P[-1] - O[-1][None, :]
    radial /= np.linalg.norm(radial, axis=1)[:, None]
    up_dir = np.cross(U[-1], V[-1])
    up_dir = up_dir if up_dir[2] > 0 else -up_dir
    lip1 = P[-1] - radial * 0.0055 + up_dir[None, :] * 0.0040
    lip2 = lip_onto(leg_fields(b)[1], O[-1], P[-1], lo=0.008) - up_dir[None, :] * 0.0060
    grid = np.concatenate([P, lip1[None], lip2[None]], axis=0)
    idx = up.add_grid(grid, closed=True, chart="upper")
    from .body import mark_ring_sharp
    mark_ring_sharp(up, idx[i_cap]); mark_ring_sharp(up, idx[i_cap + 1])
    tip_t = sdf.march(f, Oa[0][None, :], FRONT[None, :], 0.0, T1)[0]
    U_, V_ = mk.grid_uv(grid, True)
    up.add_fan(list(idx[0]), np.stack([U_[0], V_[0]], axis=1), Oa[0] + FRONT * tip_t, float(V_[0, 0]) - 0.008,
               chart="upper", flip=mk.grid_faces_outward(grid, True))
    # drop what sits inside the sole plate
    keep = [not (up.v[list(face)][:, 2] < CUT_Z + 0.0012).all() for face in up.faces]
    for name in ("faces", "fuv", "fmat", "fchart", "ftag"):
        setattr(up, name, [v for v, k in zip(getattr(up, name), keep) if k])

    # ---- laces: five bars over the instep
    lace = mk.Part("laces_l", "Shoes")
    for k, y in enumerate(np.linspace(-0.112, -0.040, 5)):
        xs = np.linspace(-0.019, 0.019, 7) * (1.0 - 0.25 * k / 4.0)
        o = np.stack([XC + xs, np.full_like(xs, y), np.full_like(xs, 0.04)], axis=1)
        t = sdf.march(f, o, rep(Z, len(xs)), 0.0, 0.15)
        pts = o + Z[None, :] * (t[:, None] + 0.0016)
        pts[0, 2] -= 0.0030; pts[-1, 2] -= 0.0030
        mk.sweep_tube(lace, pts, 0.0030, sides=6, up_hint=(0, -1, 0), caps=True, chart=("lace", k))
    up.merge(lace)

    # ---- sole plate
    sole = mk.Part("sole_l", "ShoeSole")
    sole.smooth_angle = 42.0
    n_out = 44
    oc = np.array([[XC, -0.068, CUT_Z + 0.0045]])
    th = mk.even_thetas(f, oc, X[None, :], Y[None, :], np.radians([-90.0, 90.0]), [n_out // 2, n_out // 2], 0.3)
    ring, _ = mk.sample_rings(f, oc, X[None, :], Y[None, :], th, 0.3)
    ring = ring[0]
    tang = np.roll(ring, -1, axis=0) - np.roll(ring, 1, axis=0)
    nrm = np.stack([tang[:, 1], -tang[:, 0], np.zeros(n_out)], axis=1)
    nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    if (nrm * (ring - oc)).sum() < 0:
        nrm = -nrm

    def loop(off, z):
        q = ring + nrm * off
        q[:, 2] = z
        return q
    rings = np.stack([loop(-0.012, SOLE_TOP), loop(0.0040, SOLE_TOP), loop(0.0050, SOLE_TOP - 0.0018),
                      loop(0.0046, SOLE_BOT + 0.0024), loop(0.0018, SOLE_BOT)], axis=0)
    idx_s = sole.add_grid(rings, closed=True, chart="sole_side")
    c = ring.mean(axis=0); c[2] = SOLE_BOT
    cuv = [(q[0], q[1]) for q in rings[-1]]
    ci = sole.add_verts(c[None, :])
    for j in range(n_out):
        j1 = (j + 1) % n_out
        tri = [idx_s[-1, j], idx_s[-1, j1], ci]
        tuv = [cuv[j], cuv[j1], (c[0], c[1])]
        a, bb, cc = sole.v[tri[0]], sole.v[tri[1]], sole.v[tri[2]]
        if np.cross(bb - a, cc - a)[2] > 0:
            tri.reverse(); tuv.reverse()
        sole.add_face(tri, tuv, "ShoeSole", "sole_bottom")
    # ---- studs
    studs = [(-0.020, 0.052), (0.021, 0.050), (-0.031, -0.104), (0.035, -0.110), (-0.027, -0.166), (0.031, -0.160), (0.003, -0.200)]
    ang = TAU * np.arange(8) / 8
    for k, (dx, y) in enumerate(studs):
        cxy = np.array([XC + dx, y])
        top = np.stack([cxy[0] + 0.0082 * np.cos(ang), cxy[1] + 0.0082 * np.sin(ang), np.full(8, SOLE_BOT + 0.001)], axis=1)
        bot = np.stack([cxy[0] + 0.0056 * np.cos(ang), cxy[1] + 0.0056 * np.sin(ang), np.zeros(8)], axis=1)
        idx_k = sole.add_grid(np.stack([top, bot], axis=0), closed=True, chart=("stud", k))
        sole.add_cap(list(idx_k[-1]), chart=("stud_tip", k), flip=True)
    for part in (up, sole):
        part.v[:, 2] += spring(part.v[:, 1])
        part.set_weights(lambda q: skin.foot(q, "l"))
    return [up, sole]
