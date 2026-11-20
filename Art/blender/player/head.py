"""Head, face and neck under the helmet (Skin), plus eyes and brows (Eyes).

A simple, clean stylized face: brow ridge, eye sockets, wedge nose, cheekbones, mouth line, a
strong jaw and chin. Below the neck the skin spreads into a low dome under the jersey collar.
"""
import math
import numpy as np

from . import meshkit as mk
from . import sdf, skin
from .body import adaptive, rep, X, Y, Z, FRONT, TAU

EYE_X, EYE_Z = 0.0325, 1.7275
MOUTH_Z = 1.6640
DOME_C = (0.0, 0.012, 1.468)


def head_field(b):
    nr, nrb = b.neck["r"], b.neck["rb"]

    def f(p):
        q = p.copy(); q[:, 0] = np.abs(q[:, 0])
        cran = sdf.ellipsoid(p, (0.0, 0.014, 1.752), (0.079, 0.097, 0.090))
        face = sdf.ellipsoid(p, (0.0, -0.022, 1.692), (0.0745, 0.076, 0.094))
        jaw = sdf.superellipsoid(p, (0.0, -0.022, 1.641), (0.0685, 0.072, 0.041), (2.8, 2.6, 2.4))
        chin = sdf.ellipsoid(p, (0.0, -0.078, 1.6185), (0.031, 0.022, 0.021))
        d = sdf.smin(cran, face, 0.020)
        d = sdf.smin(d, jaw, 0.016)
        d = sdf.smin(d, chin, 0.012)
        cheek = sdf.ellipsoid(q, (0.050, -0.062, 1.704), (0.024, 0.022, 0.0175))
        d = sdf.smin(d, cheek, 0.014)
        brow = sdf.capsule(q, (0.0, -0.0885, 1.7500), (0.047, -0.0815, 1.7525), 0.0142)
        d = sdf.smin(d, brow, 0.011)
        # eye sockets, then a soft upper lid over each eye
        socket = sdf.ellipsoid(q, (EYE_X, -0.107, EYE_Z - 0.001), (0.0245, 0.020, 0.0150))
        d = sdf.ssub(d, socket, 0.009)
        lid = sdf.capsule(q, (EYE_X - 0.0165, -0.0895, EYE_Z + 0.0120), (EYE_X + 0.0175, -0.0865, EYE_Z + 0.0108), 0.0036)
        d = sdf.smin(d, lid, 0.0035)
        # nose: bridge running down to a rounded tip, with wings
        bridge = sdf.cone(p, (0.0, -0.093, 1.7435), (0.0, -0.1165, 1.6975), 0.0090, 0.0135)
        wing = sdf.ellipsoid(q, (0.0150, -0.1040, 1.6900), (0.0105, 0.0120, 0.0090))
        nose = sdf.smin(bridge, wing, 0.006)
        d = sdf.smin(d, nose, 0.007)
        # lips and the mouth line
        up = sdf.capsule(q, (0.0, -0.0990, MOUTH_Z + 0.0063), (0.0240, -0.0920, MOUTH_Z + 0.0047), 0.0068)
        lo = sdf.capsule(q, (0.0, -0.0980, MOUTH_Z - 0.0073), (0.0200, -0.0918, MOUTH_Z - 0.0059), 0.0082)
        d = sdf.smin(d, sdf.smin(up, lo, 0.0015), 0.006)
        line = sdf.capsule(q, (0.0, -0.1065, MOUTH_Z), (0.0310, -0.0940, MOUTH_Z + 0.0014), 0.0036)
        d = sdf.ssub(d, line, 0.0018)
        # neck and the top of the chest
        neck = sdf.cone(p, (0.0, 0.014, 1.44), (0.0, 0.004, 1.67), nrb + 0.006, nr)
        # the top of the chest and shoulders: a low dome that passes under the jersey collar
        dome = sdf.ellipsoid(p, DOME_C, (nrb + 0.082, nrb + 0.050, 0.062))
        d = sdf.smin(d, sdf.smin(neck, dome, 0.03), 0.022)
        return d
    return f


def build_head(b):
    f = head_field(b)
    part = mk.Part("head", "Skin")
    z_lo, z_hi = 1.538, 1.800
    T1 = 0.25

    def axis(zs):
        y = 0.010 + (-0.014) * sdf.smoothstep(1.56, 1.64, zs)
        return np.stack([np.zeros_like(zs), y, zs], axis=1)
    probe = np.radians([-90.0, -78.0, -66.0, -52.0, -35.0, -10.0, 30.0, 90.0])

    def rings(zs):
        P, _ = mk.sample_rings(f, axis(zs), rep(X, len(zs)), rep(Y, len(zs)), probe, T1)
        return P
    must = [MOUTH_Z + k * 0.0021 for k in (-3, -2, -1, 0, 1, 2, 3)]
    must += [1.6905, 1.6975, EYE_Z - 0.009, EYE_Z - 0.004, EYE_Z + 0.002, EYE_Z + 0.0065, EYE_Z + 0.011, 1.752]
    zs = adaptive(rings, z_lo, z_hi, 0.020, 0.0027, 0.00065, must=must)
    # below the neck, rings fan out over the chest dome from a point inside it
    fan_phi = np.radians([10.0, 18.0, 27.0, 36.0, 45.0, 52.0])
    nf = len(fan_phi)
    n = nf + len(zs)
    O = np.vstack([rep([DOME_C[0], DOME_C[1], DOME_C[2] - 0.043], nf), axis(zs)])
    phi = np.concatenate([fan_phi, np.zeros(len(zs))])
    U, V, W = rep(X, n), rep(Y, n), rep(Z, n)

    def density(P):
        front = sdf.smoothstep(0.02, -0.05, P[:, 1]) * sdf.smoothstep(1.585, 1.62, P[:, 2])
        centre = sdf.smoothstep(0.06, 0.02, np.abs(P[:, 0]))
        return 1.0 + 2.0 * front + 1.6 * front * centre
    anchors = np.radians([-90.0, 90.0])
    counts = [23, 23]
    thetas = mk.even_thetas(f, O, U, V, anchors, counts, T1, W=W, phi=phi, weight=density, dense=8)
    thetas = mk.smooth_rows(thetas, passes=2)
    P, _ = mk.sample_rings(f, O, U, V, thetas, T1, W=W, phi=phi)
    S = sum(counts)
    idx = part.add_grid(P, closed=True, chart="head")
    # the loft stops above the brow: the crown is never visible under the helmet, but the back of
    # the skull is kept so nothing shows through when looking up under the helmet's back rim
    part.set_weights(skin.neck)

    eyes = mk.Part("eyes", "Eyes")
    for side in (1.0, -1.0):
        # eye: a dark almond set into the socket, outer corner a touch higher than the inner
        o = np.array([side * EYE_X, -0.04, EYE_Z - 0.0010])
        t = sdf.march(f, o[None, :], FRONT[None, :], 0.0, 0.12)[0]
        c = o + FRONT * (t - 0.0012)
        rx, ry, rz = 0.0166, 0.0078, 0.0092
        n_r, n_s = 6, 16
        phis = np.radians(np.linspace(6.0, 80.0, n_r))
        th = np.linspace(0.0, TAU, n_s, endpoint=False)
        ring = np.stack([c[None, :] + np.cos(ph) * (rx * np.cos(th)[:, None] * X + rz * np.sin(th)[:, None] * Z)
                         + np.sin(ph) * ry * FRONT[None, :] for ph in phis], axis=0)
        ring[:, :, 2] += 0.0020 * np.cos(th)[None, :] * side
        ring[:, :, 1] += 0.0030 * (np.cos(th)[None, :] * side + 1.0) * 0.5      # wrap back round the face
        idx_e = eyes.add_grid(ring, closed=True, chart=("eye", side))
        U_, V_ = mk.grid_uv(ring, True)
        eyes.add_fan(list(idx_e[-1]), np.stack([U_[-1], V_[-1]], axis=1), c + FRONT * ry, float(V_[-1, 0]) + 0.004,
                     chart=("eye", side), flip=not mk.grid_faces_outward(ring, True))
        # brow: a thick tapered ribbon lying on the brow ridge, lower at the nose for a set look
        k = np.linspace(0.0, 1.0, 10)
        xs = 0.0085 + 0.0485 * k
        zs_b = 1.7455 + 0.0085 * np.sin(np.clip(k * 1.25, 0, 1) * math.pi * 0.5) - 0.0050 * np.clip(k - 0.55, 0, 1) ** 1.5 / 0.3
        ob = np.stack([side * xs, np.full_like(xs, -0.02), zs_b], axis=1)
        tb = sdf.march(f, ob, rep(FRONT, len(xs)), 0.0, 0.12)
        pts = ob + FRONT[None, :] * tb[:, None]
        nrm = sdf.gradient(f, pts)
        pts = pts + nrm * 0.0010
        width = 0.0062 * (1.0 - 0.62 * k ** 1.6)
        mk.sweep_tube(eyes, pts, 0.0062, sides=6, up_hint=(0, 0, 1), caps=True, chart=("brow", side),
                      ry=0.0028, radii=width)
    eyes.set_rigid("head")
    return [part, eyes]
