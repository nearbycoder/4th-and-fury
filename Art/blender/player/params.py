"""The three body builds. Same skeleton, different mass.

Everything here is a measurement in metres on the rest pose (Z up, facing -Y, left = +X).
`core` is the athlete's own torso as stacked cross-sections:
    z, half-width, front depth, back depth, front squareness, back squareness
"""
import copy
import numpy as np

from furylib import rig

J = {name: np.array(v, float) for name, v in rig.JOINTS.items()}
TAIL = {name: np.array(v, float) for name, v in rig.TAILS.items()}

CORE_COLS = ("z", "ws", "df", "db", "ef", "eb")

_MID = dict(
    name="mid",
    core=[
        (0.80, 0.146, 0.088, 0.102, 2.2, 2.2),
        (0.90, 0.166, 0.096, 0.110, 2.2, 2.2),
        (0.94, 0.174, 0.100, 0.112, 2.3, 2.2),
        (0.98, 0.173, 0.105, 0.110, 2.4, 2.2),
        (1.02, 0.168, 0.109, 0.106, 2.5, 2.3),
        (1.06, 0.163, 0.111, 0.103, 2.6, 2.4),
        (1.10, 0.158, 0.112, 0.102, 2.6, 2.4),
        (1.16, 0.160, 0.115, 0.104, 2.6, 2.4),
        (1.22, 0.169, 0.119, 0.109, 2.5, 2.4),
        (1.28, 0.181, 0.124, 0.116, 2.4, 2.4),
        (1.34, 0.192, 0.128, 0.123, 2.4, 2.4),
        (1.40, 0.194, 0.128, 0.126, 2.4, 2.4),
        (1.46, 0.165, 0.112, 0.116, 2.3, 2.3),
        (1.52, 0.108, 0.088, 0.095, 2.2, 2.2),
        (1.58, 0.072, 0.068, 0.074, 2.0, 2.0),
    ],
    crotch_z=0.862,
    glute=dict(c=(0.082, 0.062, 0.945), r=(0.090, 0.078, 0.100)),
    # shoulder pads under the jersey
    shelf=dict(rim=0.290, top=1.582, inner=0.030, depth=0.146, thick=0.150, cy=0.004, slope=0.075),
    chest_plate=dict(front=-0.162, half_w=0.176, top=1.515, bottom=1.236, depth=0.066),
    back_plate=dict(back=0.152, half_w=0.186, top=1.550, bottom=1.226, depth=0.058),
    pad_blend=0.034,
    collar=dict(a=0.076, bf=0.090, bb=0.070, cy=-0.004),
    cap=dict(off=0.008, r_out=0.070, r_fb=0.102, half_len=0.078, centre_s=0.108, cut=-0.030),
    sleeve=dict(r0=0.072, r1=0.064, end=0.215),
    arm=1.12,            # girth multipliers on the limb tables
    thigh=1.12,
    calf=1.14,
    neck=dict(r=0.064, rb=0.070),
    belly=None,
    pad_thick=0.014,     # thigh / knee pad stand-off under the pants
    glove=1.00,
)

_LEAN = copy.deepcopy(_MID)
_LEAN.update(
    name="lean",
    core=[
        (0.80, 0.134, 0.080, 0.092, 2.2, 2.2),
        (0.90, 0.150, 0.086, 0.098, 2.2, 2.2),
        (0.94, 0.156, 0.090, 0.100, 2.3, 2.2),
        (0.98, 0.155, 0.093, 0.097, 2.4, 2.2),
        (1.02, 0.150, 0.095, 0.092, 2.5, 2.3),
        (1.06, 0.145, 0.096, 0.089, 2.6, 2.4),
        (1.10, 0.142, 0.096, 0.088, 2.6, 2.4),
        (1.16, 0.144, 0.098, 0.090, 2.6, 2.4),
        (1.22, 0.151, 0.101, 0.094, 2.5, 2.4),
        (1.28, 0.158, 0.106, 0.099, 2.4, 2.4),
        (1.34, 0.168, 0.110, 0.106, 2.4, 2.4),
        (1.40, 0.171, 0.110, 0.109, 2.4, 2.4),
        (1.46, 0.148, 0.098, 0.102, 2.3, 2.3),
        (1.52, 0.098, 0.080, 0.086, 2.2, 2.2),
        (1.58, 0.066, 0.062, 0.068, 2.0, 2.0),
    ],
    glute=dict(c=(0.076, 0.056, 0.945), r=(0.082, 0.070, 0.094)),
    shelf=dict(rim=0.268, top=1.574, inner=0.030, depth=0.130, thick=0.138, cy=0.004, slope=0.075),
    chest_plate=dict(front=-0.144, half_w=0.156, top=1.508, bottom=1.248, depth=0.056),
    back_plate=dict(back=0.132, half_w=0.166, top=1.544, bottom=1.240, depth=0.050),
    pad_blend=0.024,
    collar=dict(a=0.072, bf=0.086, bb=0.066, cy=-0.004),
    cap=dict(off=0.008, r_out=0.063, r_fb=0.090, half_len=0.072, centre_s=0.100, cut=-0.028),
    sleeve=dict(r0=0.065, r1=0.057, end=0.200),
    arm=0.98,
    thigh=0.99,
    calf=1.02,
    neck=dict(r=0.056, rb=0.060),
    pad_thick=0.011,
    glove=0.97,
)

_BIG = copy.deepcopy(_MID)
_BIG.update(
    name="big",
    core=[
        (0.80, 0.170, 0.096, 0.112, 2.2, 2.2),
        (0.90, 0.196, 0.110, 0.124, 2.2, 2.2),
        (0.94, 0.208, 0.120, 0.128, 2.2, 2.2),
        (0.98, 0.210, 0.140, 0.128, 2.2, 2.2),
        (1.02, 0.208, 0.160, 0.124, 2.2, 2.3),
        (1.06, 0.205, 0.177, 0.120, 2.1, 2.3),
        (1.10, 0.203, 0.189, 0.118, 2.1, 2.3),
        (1.16, 0.202, 0.193, 0.118, 2.1, 2.3),
        (1.22, 0.203, 0.185, 0.121, 2.2, 2.4),
        (1.28, 0.207, 0.170, 0.126, 2.3, 2.4),
        (1.34, 0.213, 0.150, 0.132, 2.4, 2.4),
        (1.40, 0.214, 0.146, 0.134, 2.4, 2.4),
        (1.46, 0.184, 0.126, 0.126, 2.3, 2.3),
        (1.52, 0.122, 0.096, 0.104, 2.2, 2.2),
        (1.58, 0.082, 0.074, 0.082, 2.0, 2.0),
    ],
    crotch_z=0.856,
    glute=dict(c=(0.094, 0.070, 0.945), r=(0.104, 0.090, 0.108)),
    shelf=dict(rim=0.326, top=1.594, inner=0.034, depth=0.164, thick=0.168, cy=0.004, slope=0.075),
    chest_plate=dict(front=-0.190, half_w=0.204, top=1.524, bottom=1.262, depth=0.072),
    back_plate=dict(back=0.168, half_w=0.214, top=1.558, bottom=1.236, depth=0.064),
    pad_blend=0.030,
    collar=dict(a=0.086, bf=0.098, bb=0.080, cy=-0.004),
    cap=dict(off=0.008, r_out=0.082, r_fb=0.118, half_len=0.090, centre_s=0.128, cut=-0.034),
    sleeve=dict(r0=0.086, r1=0.078, end=0.243),
    arm=1.32,
    thigh=1.32,
    calf=1.26,
    neck=dict(r=0.072, rb=0.078),
    pad_thick=0.016,
    glove=1.06,
)

BUILDS = {"lean": _LEAN, "mid": _MID, "big": _BIG}
MESH_NAMES = {"lean": "SK_Player_Lean", "mid": "SK_Player_Mid", "big": "SK_Player_Big"}

HEAD_SCALE = 1.07        # helmet and head, about the base of the skull (arcade proportions)
HEAD_PIVOT = (0.0, 0.0, 1.615)

# Jersey number panels (metres). The engine draws a two-digit number in each 0..1 square.
PANEL_FRONT = dict(z=1.368, w=0.24, h=0.24)
PANEL_BACK = dict(z=1.372, w=0.30, h=0.30)
PANEL_CAP = dict(w=0.10, h=0.10)


class Build:
    """Attribute access to one build's numbers."""

    def __init__(self, name):
        self.__dict__.update(copy.deepcopy(BUILDS[name]))
        self.mesh_name = MESH_NAMES[name]
