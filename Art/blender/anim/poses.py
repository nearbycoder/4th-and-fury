"""Anchor poses and building blocks shared by the clips, as control dicts (see controls.py).

POSES maps a name to a function returning (controls, ball) where ball is "hand", "tuck", None or
a world matrix; `build_anims.py -- --pose NAME` renders one from four sides.
"""
from mathutils import Vector

from furylib import rig as furyrig

from .controls import ArmFK, ArmIK, LegFK, LegIK, Plant
from .preview import ball_matrix

# Rest-pose landmarks (world, metres).
SHOULDER_Z = 1.49
CHEST = (0.0, 0.0, 1.40)
BALL_REST = furyrig.JOINTS["ball_hand_r"].copy()   # rest centre of a ball in the right hand


# ---- arms ----------------------------------------------------------------------------------
def relaxed(**kw):
    """Arm hanging loose at the side."""
    return ArmFK(fwd=6, out=12, twist=30, elbow=25, grip=0.4, thumb=0.3).but(**kw)


def tuck(**kw):
    """Right arm carrying the ball high and tight (ball_tuck_r)."""
    spec = ArmIK(pos=(-0.249, -0.283, 1.296), space="chest", pole=(-0.5, 0.45, -0.8), pron=-47, flex=60,
                 grip=0.55, thumb=0.5)
    return spec.but(**kw)


def hold(pos, axis, palm, space="chest", **kw):
    """Right hand gripping the ball (ball_hand_r): ball centre, long axis, and the direction the
    palm presses on it. The fingers end up along palm x axis."""
    spec = ArmIK(pos=pos, space=space, at="ball", fingers=axis, palm=palm, hspace=space, grip=0.42, thumb=0.75)
    return spec.but(**kw)


def cup(side=(-0.75, 0.0, -0.66), **kw):
    """Left hand on the ball that the right hand holds. `side` is where on the ball the palm sits,
    in the ball's own frame (x = away from the right palm's wrist side, y = along the ball,
    z = the laces side; the right palm sits on +x+z, so the default is the opposite side). The
    fingers wrap whichever way the forearm arrives."""
    side_v = Vector(side).normalized()
    d = Vector((-side_v.x, -side_v.y, side_v.z))      # socket rest axes in world: X=-x, Y=-y, Z=+z
    c = abs(side_v.y)
    s = (1.0 - c * c) ** 0.5
    radius = 1.0 / ((c / 0.14) ** 2 + (s / 0.085) ** 2) ** 0.5
    pos = BALL_REST + d * radius
    spec = ArmIK(pos=tuple(pos), space="ball_hand_r", at="palm", palm=tuple(-d), hspace="ball_hand_r",
                 grip=0.38, thumb=0.6)
    return spec.but(**kw)


# ---- whole-body poses --------------------------------------------------------------------------
def idle():
    return dict(hip=(0.0, 0.0, 0.945), pitch=5.0, bend=6.0, nod=-9.0,
                armL=relaxed(), armR=relaxed(),
                legL=Plant(0.17, -0.01, out=10.0), legR=Plant(-0.17, 0.02, out=10.0))


def carry():
    c = idle()
    c.update(armR=tuck())
    return c


def two_hands(pos=(-0.07, -0.27, 1.33), axis=(0.25, -0.3, 0.92), palm=(0.85, -0.5, 0.1), space="chest"):
    """Both arms holding the ball in front of the body (ball_hand_r). Returns (armR, armL)."""
    right = hold(pos, axis=axis, palm=palm, space=space, pole=(-0.7, 0.3, -0.65))
    left = cup(pole=(0.7, 0.3, -0.65))
    return right, left


def qb_set():
    """In the pocket: body half turned to the right, ball at the chest in both hands, eyes downfield."""
    right, left = two_hands()
    return dict(hip=(0.0, 0.0, 0.925), yaw=-30.0, pitch=4.0, bend=6.0, twist=-8.0, gaze=1.0, nod=2.0, turn=0.0,
                armR=right, armL=left,
                legL=Plant(0.14, -0.14, yaw=-30.0, out=8.0, roll=10.0), legR=Plant(-0.13, 0.15, yaw=-30.0, out=8.0, roll=10.0))


def ready():
    """Two-point stance: knees bent, hands loose in front, weight on the balls of the feet."""
    arm = ArmFK(fwd=40, out=16, twist=30, elbow=66, pron=25, grip=0.25, thumb=0.2)
    return dict(hip=(0.0, 0.03, 0.80), pitch=22.0, bend=16.0, gaze=1.0, nod=4.0,
                armL=arm, armR=arm,
                legL=Plant(0.22, -0.09, out=10.0, roll=9.0), legR=Plant(-0.22, 0.09, out=10.0, roll=12.0))


def stance3():
    """Three-point lineman stance, right hand on the ground."""
    return dict(hip=(0.0, 0.22, 0.60), pitch=64.0, bend=18.0, nod=-48.0,
                armR=ArmIK(pos=(-0.15, -0.40, 0.012), at="tip", palm=(0.0, 1.0, -0.15), fingers=(0.0, -0.3, -1.0),
                           pole=(-0.5, 0.6, 0.3), pspace="world", grip=0.15, thumb=0.2),
                armL=ArmIK(pos=(0.25, -0.20, 0.47), pole=(0.6, 0.6, -0.4), pspace="world", flex=25.0, grip=0.5),
                legL=Plant(0.24, 0.02, out=14.0, roll=18.0), legR=Plant(-0.24, 0.24, out=10.0, roll=32.0))


def center():
    """Centre over the ball: right hand on a ball lying 0.45 m in front of the root."""
    return dict(hip=(0.0, 0.24, 0.60), pitch=66.0, bend=18.0, nod=-48.0,
                armR=ArmIK(pos=(-0.005, -0.475, 0.168), at="palm", palm=(0.0, 0.25, -1.0), fingers=(0.12, -1.0, -0.45),
                           pole=(-0.6, 0.5, 0.3), pspace="world", grip=0.35, thumb=0.5),
                armL=ArmIK(pos=(0.31, -0.14, 0.47), pole=(0.6, 0.6, -0.4), pspace="world", flex=25.0, grip=0.5),
                legL=Plant(0.30, 0.20, out=16.0, roll=20.0), legR=Plant(-0.30, 0.20, out=16.0, roll=20.0))


CENTER_BALL = (0.0, -0.45, 0.085)


def stance_qb():
    """Shotgun: slight crouch, open hands in front of the chest as a target for the snap."""
    def hand(s):
        return ArmIK(pos=(0.085 * s, -0.36, 1.37), space="torso", at="palm", palm=(-0.3 * s, -0.95, 0.1),
                     fingers=(0.3 * s, -0.1, 0.95), hspace="torso", pole=(0.6 * s, 0.35, -0.7), pspace="torso",
                     grip=0.08, thumb=0.0)
    return dict(hip=(0.0, 0.02, 0.88), pitch=13.0, bend=12.0, gaze=1.0, nod=3.0,
                armL=hand(1.0), armR=hand(-1.0),
                legL=Plant(0.20, 0.0, out=12.0), legR=Plant(-0.20, 0.02, out=12.0))


def block():
    """Engaged blocker: low base, both hands punched out at chest height."""
    def hand(s):
        return ArmIK(pos=(0.14 * s, -0.53, 1.45), space="torso", at="palm", palm=(0.0, -1.0, 0.1),
                     fingers=(0.2 * s, 0.0, 1.0), hspace="torso", pole=(0.7 * s, 0.3, -0.6), pspace="torso",
                     grip=0.1, thumb=0.1)
    return dict(hip=(0.0, 0.07, 0.78), pitch=26.0, bend=12.0, gaze=1.0, nod=0.0,
                armL=hand(1.0), armR=hand(-1.0),
                legL=Plant(0.26, -0.10, out=14.0, roll=6.0), legR=Plant(-0.26, 0.12, out=14.0, roll=14.0))


def down_back():
    """Flat on the back, head to the rear (+Y), feet to the front."""
    return dict(hip=(0.0, 0.25, 0.14), pitch=-89.0, ground=1.0, bend=-2.0, nod=10.0, turn=12.0,
                armL=ArmIK(pos=(0.56, 0.50, 0.035), pole=(0.7, -0.6, 0.12), pspace="world", palm=(0.0, 0.0, 1.0),
                           fingers=(0.75, -0.65, 0.0), grip=0.35),
                armR=ArmIK(pos=(-0.50, 0.38, 0.035), pole=(-0.7, -0.6, 0.12), pspace="world", palm=(0.0, 0.0, 1.0),
                           fingers=(-0.5, -0.85, 0.0), grip=0.35),
                legL=LegIK(pos=(0.20, -0.59, 0.105), knee=(0.35, 0.0, 1.0), kspace="world", ankle=-18.0),
                legR=LegIK(pos=(-0.24, -0.46, 0.108), knee=(-0.45, 0.0, 1.0), kspace="world", ankle=-12.0))


def down_front():
    """Face down, head to the front (-Y)."""
    return dict(hip=(0.0, -0.25, 0.125), pitch=95.0, ground=1.0, bend=-8.0, nod=-12.0, turn=55.0,
                armL=ArmIK(pos=(0.36, -1.00, 0.036), pole=(1.0, 0.3, 0.1), pspace="world", palm=(0.0, 0.0, -1.0),
                           fingers=(-0.35, -0.95, 0.0), grip=0.08, thumb=0.1),
                armR=ArmIK(pos=(-0.44, -0.80, 0.036), pole=(-1.0, 0.5, 0.1), pspace="world", palm=(0.0, 0.0, -1.0),
                           fingers=(0.3, -0.95, 0.0), grip=0.08, thumb=0.1),
                legL=LegIK(pos=(0.17, 0.60, 0.078), knee=(1.0, 0.0, -0.3), kspace="world", ankle=-52.0),
                legR=LegIK(pos=(-0.32, 0.42, 0.068), knee=(-1.0, -0.2, 0.0), kspace="world", ankle=-52.0))


POSES = {
    "idle": lambda: (idle(), None),
    "carry": lambda: (carry(), "tuck"),
    "qb_set": lambda: (qb_set(), "hand"),
    "ready": lambda: (ready(), None),
    "stance3": lambda: (stance3(), None),
    "center": lambda: (center(), ball_matrix(CENTER_BALL)),
    "stance_qb": lambda: (stance_qb(), None),
    "block": lambda: (block(), None),
    "down_back": lambda: (down_back(), None),
    "down_front": lambda: (down_front(), None),
}
