"""Small gear on the hips: belt buckle, the laced fly of the pants and a towel over the belt.

All of it rides on the pants surface and takes the same position-based skin weights as the pants
underneath, so it can never slide through them.
"""
import math
import numpy as np

from . import meshkit as mk
from . import sdf, skin
from .body import pants_field, rep, X, Y, Z, FRONT

BELT_LIFT = 0.003            # how far the belt band stands off the pants (see body.build_pants)


def build_extras(b):
    f = pants_field(b)
    weights = lambda p: skin.lower_body(p, b.crotch_z)

    def front_proj(x, z):
        x = np.atleast_1d(np.asarray(x, float)); z = np.atleast_1d(np.asarray(z, float))
        O = np.stack([x, np.zeros_like(x), z], axis=1)
        t = sdf.march(f, O, rep(FRONT, len(x)), 0.0, 0.45)
        P = O + FRONT[None, :] * t[:, None]
        return P, sdf.gradient(f, P)

    # ---- buckle: a rounded plate on the front of the belt
    gear = mk.Part("belt_gear", "Belt")
    gear.smooth_angle = 50.0
    mk.raised_patch(gear, "buckle", 0.0, 1.062, 0.0235, 0.0180, 0.0055, front_proj, BELT_LIFT + 0.0042, "Belt", n=(10, 8))

    # ---- laced fly: three crossed laces under the buckle
    for k, z0 in enumerate((1.0395, 1.0235, 1.0075)):
        for sgn in (1.0, -1.0):
            xs = np.linspace(-0.0115, 0.0115, 5) * sgn
            zs = np.linspace(z0, z0 - 0.0125, 5)
            P, N = front_proj(xs, zs)
            pts = P + N * 0.0016
            pts[0] -= N[0] * 0.0022; pts[-1] -= N[-1] * 0.0022
            mk.sweep_tube(gear, pts, 0.0019, sides=5, up_hint=(0, -1, 0), caps=True, chart=("lace", k, sgn))
    gear.set_weights(weights)

    # ---- towel: folded over the belt on the right hip, hanging down the front of the thigh
    towel = mk.Part("towel", "Belt")
    hip = float(sdf.pchip(0.98, [r[0] for r in b.core], [r[1] for r in b.core]))
    xc = -0.094 * hip / 0.173
    z_top, z_bot = 1.090, 0.838
    zc, hz = 0.5 * (z_top + z_bot), 0.5 * (z_top - z_bot)
    hw = 0.060

    def widen(z):
        return 0.72 + 0.28 * sdf.smoothstep(1.075, 0.93, z)

    def g(u, v):
        return -mk.rbox2((u - xc) / widen(v), v - zc, hw, hz, 0.012)
    us = np.linspace(xc - hw - 0.004, xc + hw + 0.004, 13)
    vs = np.linspace(z_bot - 0.004, z_top + 0.004, 16)
    uv, faces = mk.trim_grid(g, us, vs)
    P, N = front_proj(uv[:, 0], uv[:, 1])
    hang = sdf.smoothstep(1.060, 0.930, uv[:, 1])
    fold = 0.0042 * np.sin((uv[:, 0] - xc) / widen(uv[:, 1]) * (2.0 * math.pi / 0.040)) * hang
    off = BELT_LIFT + 0.0062 + 0.0030 * hang + fold
    Pt = P + N * off[:, None]
    f0 = faces[0]
    if np.cross(Pt[f0[1]] - Pt[f0[0]], Pt[f0[2]] - Pt[f0[0]]) @ N[f0[0]] < 0.0:
        faces = [list(reversed(fc)) for fc in faces]
    mk.shell_from_surface(towel, Pt, N, faces, 0.0042, mat="Belt", chart="towel", uvs=uv, rim_round=0.8, sharp_rim=False)
    def towel_weights(p):
        w = weights(p)
        # Pin the belt end. The loose end follows a spring bone parented to the thigh.
        w["towel"] = w["thigh_r"] * (1.0 - sdf.smoothstep(0.87, 1.015, p[:, 2]))
        w["thigh_r"] -= w["towel"]
        return w
    towel.set_weights(towel_weights)
    return [gear, towel]
