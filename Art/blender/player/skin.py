"""Analytic skin weights.

Weights are functions of where a vertex sits in the rest pose, never of which garment it belongs
to, so stacked layers (sock under pants hem, arm under sleeve cuff, neck under collar) always
move together and cannot poke through each other. Hard parts are simply rigid.

Joint blends are deliberately lopsided: on the outside of a hinge the limb that forms the bony
point (thigh at the knee, forearm at the elbow) keeps full weight a little past the joint, so the
point stays put instead of collapsing; on the inside the blend is short so it reads as a crease.
"""
import numpy as np

from .params import J, TAIL
from .sdf import smoothstep, unit

FRONT = np.array([0.0, -1.0, 0.0])
MIRROR = np.array([-1.0, 1.0, 1.0])
SHELF_ARM = 0.40          # how much of the upper arm's swing the outer pad shelf follows


def _swap(name, side):
    return name if side == "l" else name[:-2] + "_r"


def _to_left(p, side):
    return p if side == "l" else p * MIRROR


def normalize(w):
    total = sum(w.values())
    total = np.maximum(total, 1e-9)
    return {k: v / total for k, v in w.items()}


# ---------------------------------------------------------------------------------- spine
def spine(z):
    b1 = smoothstep(1.03, 1.13, z)
    b2 = smoothstep(1.15, 1.25, z)
    b3 = smoothstep(1.29, 1.39, z)
    return {"pelvis": 1.0 - b1, "spine_01": b1 * (1.0 - b2), "spine_02": b2 * (1.0 - b3), "spine_03": b3}


def torso(p):
    """Jersey body: spine chain plus the clavicles under the outer shoulder shelf."""
    w = spine(p[:, 2])
    ax = np.abs(p[:, 0])
    high = smoothstep(1.385, 1.48, p[:, 2])
    wc = 0.78 * smoothstep(0.075, 0.21, ax) * high
    # the outer end of the pad shelf leans with the upper arm, the way real pads ride up
    wa = SHELF_ARM * smoothstep(0.185, 0.285, ax) * smoothstep(1.43, 1.50, p[:, 2])
    wc = wc * (1.0 - wa)
    left = p[:, 0] >= 0.0
    w = {k: v * (1.0 - wc - wa) for k, v in w.items()}
    w["clavicle_l"] = np.where(left, wc, 0.0)
    w["clavicle_r"] = np.where(~left, wc, 0.0)
    w["upperarm_l"] = np.where(left, wa, 0.0)
    w["upperarm_r"] = np.where(~left, wa, 0.0)
    return w


def neck(p):
    z = p[:, 2] + 0.25 * np.maximum(p[:, 1], 0.0)      # the back of the neck hinges a little lower
    b_n = smoothstep(1.50, 1.565, z)
    b_h = smoothstep(1.585, 1.655, z)
    return {"spine_03": 1.0 - b_n, "neck_01": b_n * (1.0 - b_h), "head": b_h}


# ----------------------------------------------------------------------------------- arms
def arm(p, side="l"):
    """upperarm -> lowerarm -> hand, for anything that lives on the arm."""
    q = _to_left(p, side)
    S, E, Wr = J["upperarm_l"], J["lowerarm_l"], J["hand_l"]
    a1, a2 = unit(E - S), unit(Wr - E)
    am = unit(a1 + a2)
    d = (q - E) @ am
    r = (q - E) - d[:, None] * am
    back = 0.5 - 0.5 * (r @ FRONT) / np.maximum(np.linalg.norm(r, axis=1), 1e-6)
    c = -0.028 * back + 0.004 * (1.0 - back)
    hw = 0.026 + 0.006 * back
    w_low = smoothstep(c - hw, c + hw, d)
    ah = unit(TAIL["hand_l"] - Wr)
    dw = (q - Wr) @ ah
    w_hand = smoothstep(-0.022, 0.018, dw)
    return {
        _swap("upperarm_l", side): 1.0 - w_low,
        _swap("lowerarm_l", side): w_low * (1.0 - w_hand),
        _swap("hand_l", side): w_low * w_hand,
    }


# ----------------------------------------------------------------------------------- legs
def _knee(q):
    H, K, A = J["thigh_l"], J["calf_l"], J["foot_l"]
    am = unit(unit(K - H) + unit(A - K))
    d = (q - K) @ am
    r = (q - K) - d[:, None] * am
    front = 0.5 + 0.5 * (r @ FRONT) / np.maximum(np.linalg.norm(r, axis=1), 1e-6)
    c = 0.040 * front - 0.006 * (1.0 - front)
    hw = 0.034
    return smoothstep(c - hw, c + hw, d)


def hip_claim(q, crotch_z):
    """How much of a (left-side) point belongs to the thigh rather than the pelvis."""
    H = J["thigh_l"]
    rel = q - H
    ang = np.arctan2(rel[:, 1], rel[:, 0])
    co = np.maximum(np.cos(ang), 0.0) ** 2
    ci = np.maximum(-np.cos(ang), 0.0) ** 2
    cb = np.maximum(np.sin(ang), 0.0) ** 2
    cf = np.maximum(-np.sin(ang), 0.0) ** 2
    zmid = co * 0.962 + cf * 0.925 + ci * (crotch_z + 0.014) + cb * 0.900
    hw = co * 0.055 + cf * 0.040 + ci * 0.030 + cb * 0.062
    return 1.0 - smoothstep(zmid - hw, zmid + hw, q[:, 2])


def lower_body(p, crotch_z):
    """Pants, belt and anything hanging on the hips: pelvis/spine_01 -> thighs -> calves."""
    z = p[:, 2]
    e = 0.002 + 0.030 * smoothstep(crotch_z - 0.05, crotch_z + 0.005, z)
    own_l = smoothstep(-e, e, p[:, 0])
    claim_l = hip_claim(p, crotch_z) * own_l
    claim_r = hip_claim(p * MIRROR, crotch_z) * (1.0 - own_l)
    rest = 1.0 - claim_l - claim_r
    w = {k: v * rest for k, v in spine(z).items()}
    kl = _knee(p)
    kr = _knee(p * MIRROR)
    w["thigh_l"] = claim_l * (1.0 - kl)
    w["calf_l"] = claim_l * kl
    w["thigh_r"] = claim_r * (1.0 - kr)
    w["calf_r"] = claim_r * kr
    return w


def leg(p, side="l"):
    """thigh -> calf -> foot for things wholly on one leg (socks)."""
    q = _to_left(p, side)
    k = _knee(q)
    w_foot = 1.0 - smoothstep(0.118, 0.178, q[:, 2])
    return {
        _swap("thigh_l", side): 1.0 - k,
        _swap("calf_l", side): k * (1.0 - w_foot),
        _swap("foot_l", side): k * w_foot,
    }


def foot(p, side="l"):
    """foot -> ball: the shoe flexes across the ball of the foot."""
    q = _to_left(p, side)
    B = J["ball_l"]
    d = (B[1] - q[:, 1])                      # > 0 in front of the ball joint
    w_ball = smoothstep(-0.014, 0.022, d - 0.25 * (q[:, 2] - B[2]))
    return {_swap("foot_l", side): 1.0 - w_ball, _swap("ball_l", side): w_ball}
