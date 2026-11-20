"""Tier 1: locomotion loops and stances."""
import math
from copy import copy

from . import poses
from .clip import Clip, E, mirrored
from .controls import ArmFK, ArmIK, LegFK, LegIK, Plant
from .gait import TAU, Gait, pump, wave
from .preview import VIEW_34, VIEW_SIDE

FRONT_VIEW = (0.0, 6.0)


def _gait_clip(rig, name, gait, **kw):
    clip = Clip(name, gait.frames, loop=True, speed=gait.speed, **kw)
    clip.source = lambda t: gait.controls(rig, t)
    clip.velocity = (gait.travel[0] * gait.speed, gait.travel[1] * gait.speed)
    clip.gait = gait
    return clip


def idle(rig, made):
    c = Clip("Idle", 60, loop=True, notes="Relaxed athletic stand; breathing and a slow weight shift. Frame 0 is the anchor pose.")
    c.key(0, poses.idle())

    def life(t, k):
        breath = math.sin(TAU * t / 30.0)                 # two breaths per loop, in at +1
        shift = math.sin(TAU * t / 60.0) + 0.25 * math.sin(TAU * t / 30.0)     # all zero on frame 0
        x, y, z = k["hip"]
        k["hip"] = (x + 0.022 * shift, y, z + 0.004 * breath - 0.004 * abs(shift))
        k["roll"] = -1.8 * shift
        k["side"] = 2.2 * shift
        k["bend"] += -1.6 * breath
        k["nod"] += 1.0 * breath
        k["tilt"] = -0.8 * shift
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            a = k["arm" + side]
            k["arm" + side] = a.but(shrug=3.0 * breath, out=a.out + 1.5 * breath + 1.2 * sgn * shift,
                                    fwd=a.fwd - 1.5 * breath, elbow=a.elbow + 2.0 * breath)

    c.mod(life)
    return c


RUN = Gait(frames=16, speed=8.0)


def run(rig, made):
    return _gait_clip(rig, "Run", RUN, notes="Full sprint. Frame 0 = left foot contact, frame 8 = right foot contact.")


JOG = Gait(frames=20, speed=4.5, duty=0.24, mid={"L": -0.03, "R": -0.03},
           roll=[(0.0, -14.0), (0.22, 0.0), (0.5, 0.0), (1.0, 50.0)],
           swing=[(0.2, -0.58, 0.33), (0.42, -0.26, 0.46), (0.66, 0.14, 0.34), (0.86, 0.36, 0.22)],
           ankle=[(0.0, -25.0), (0.5, -8.0), (0.85, 10.0), (1.0, 10.0)],
           hip=(0.0, 0.02, 0.925), bob=0.03, bob_at=0.07, sway=0.015, pitch=6.0, bend=8.0, yaw=6.0, twist=12.0,
           roll_amp=3.5,
           arms=lambda g, ph, side: pump(g, ph, side, fwd=(-4.0, 30.0), elbow=(86.0, 8.0), out=(9.0, -2.0),
                                         twist=(28.0, 8.0), grip=0.6))


def jog(rig, made):
    return _gait_clip(rig, "Jog", JOG, notes="Easy run. Frame 0 = left foot contact, frame 10 = right foot contact.")


def _carry_arms(g, ph, side):
    """Ball tucked in the right arm; the left arm pumps harder to make up for it."""
    if side == "L":
        return pump(g, ph, side, fwd=(-6.0, 58.0), elbow=(90.0, 18.0), out=(12.0, -5.0), twist=(28.0, 14.0))
    bounce = wave(ph * 2.0, 0.12)
    spec = poses.tuck()
    x, y, z = spec.pos
    return spec.but(pos=(x - 0.006 * wave(ph), y + 0.012 * wave(ph), z + 0.012 * bounce))


RUN_BALL = Gait(frames=16, speed=8.0, twist=11.0, yaw=9.0, arms=_carry_arms)


def run_ball(rig, made):
    return _gait_clip(rig, "RunBall", RUN_BALL, ball="tuck",
                      notes="Sprint with the ball tucked in the right arm; same phase and length as Run.")


def jog_ball(rig, made):
    """A shorter, planted stride for a back reading a block or gathering before a cut."""
    gait = copy(JOG)
    gait.hip = (0.0, 0.025, 0.89)
    gait.bob = 0.019
    gait.sway = 0.022
    gait.pitch = 10.0
    gait.bend = 13.0
    gait.twist = 6.5
    gait.base = {"L": (0.115, 0.0), "R": (-0.115, 0.0)}

    def read_block(g, ph, side):
        if side == "R":
            return _carry_arms(g, ph, side)
        return pump(g, ph, side, fwd=(14.0, 24.0), elbow=(72.0, 12.0), out=(22.0, -4.0),
                    twist=(24.0, 7.0), grip=0.22)

    gait.arms = read_block
    return _gait_clip(rig, "JogBall", gait, ball="tuck",
                      notes="Gather at half speed, carry tight, free hand ready to fend. Left cleat strikes on frame zero.")


def _low_arms(g, ph, side, swing=22.0):
    """Compact arm swing for backpedals: elbows bent, hands in front of the ribs."""
    lead = ph if side == "L" else (ph + 0.5) % 1.0
    sw = -wave(lead, 0.03)
    return ArmFK(fwd=6.0 + swing * sw, out=12.0, twist=34.0 + 6.0 * sw, elbow=96.0 + 8.0 * sw, grip=0.5, thumb=0.5)


BACKPEDAL = Gait(frames=20, speed=4.0, travel=(0.0, 1.0), duty=0.33, mid={"L": 0.02, "R": 0.02},
                 base={"L": (0.12, 0.0), "R": (-0.12, 0.0)}, toe_out=7.0,
                 roll=[(0.0, 40.0), (0.35, 6.0), (0.7, 0.0), (1.0, 14.0)],
                 swing=[(0.25, -0.22, 0.20), (0.55, 0.08, 0.235), (0.85, 0.36, 0.19)],
                 swing_pitch=[(0.45, -8.0)],
                 hip=(0.0, 0.05, 0.80), bob=0.022, bob_at=0.16, sway=0.02, pitch=20.0, bend=16.0,
                 yaw=-5.0, twist=-9.0, roll_amp=3.0, arms=_low_arms)


def backpedal(rig, made):
    clip = _gait_clip(rig, "Backpedal", BACKPEDAL,
                      notes="Defensive backpedal, hips low. Moves BACKWARD (+Y) at `speed` while facing -Y. "
                            "Frame 0 = left foot contact (reaching back), frame 10 = right foot contact.")
    return clip


def _ready_arms(g, ph, side):
    """Hands loose and open in front, ready to react; they ride the bounce of the shuffle."""
    b = wave(ph * 2.0, 0.1)
    s = 1.0 if side == "L" else -1.0
    lean = wave(ph, 0.1) * s
    return ArmFK(fwd=52.0 + 5.0 * b, out=22.0 + 4.0 * lean, twist=24.0, elbow=86.0 - 8.0 * b, pron=20.0,
                 grip=0.25, thumb=0.2)


SHUFFLE = Gait(frames=16, speed=2.8, travel=(1.0, 0.0), duty=0.32, mid={"L": 0.30, "R": -0.30},
               base={"L": (0.0, -0.03), "R": (0.0, 0.03)}, toe_out=12.0,
               roll=[(0.0, 10.0), (0.3, 0.0), (0.6, 2.0), (1.0, 34.0)],
               swing={"L": [(0.28, 0.14, 0.14), (0.72, 0.49, 0.17)], "R": [(0.28, -0.51, 0.16), (0.72, -0.13, 0.13)]},
               swing_pitch=[(0.5, -10.0)],
               hip=(0.0, 0.05, 0.775), bob=0.014, bob_at=0.15, sway=0.045, pitch=22.0, bend=14.0,
               yaw=3.0, twist=5.0, roll_amp=-3.0, arms=_ready_arms)


def shuffle_l(rig, made):
    clip = _gait_clip(rig, "ShuffleL", SHUFFLE,
                      notes="Lateral shuffle toward the character's LEFT (+X) at `speed`, facing -Y, feet never "
                            "cross. Frame 0 = left (lead) foot contact, frame 8 = right foot contact.")
    clip.views = (FRONT_VIEW, VIEW_34)
    return clip


def shuffle_r(rig, made):
    src = made["ShuffleL"]
    clip = mirrored("ShuffleR", src, shift=src.frames / 2.0,
                    notes="Mirror of ShuffleL: moves toward the character's RIGHT (-X). "
                          "Frame 0 = left (trailing) foot contact, frame 8 = right (lead) foot contact.")
    clip.views = (FRONT_VIEW, VIEW_34)
    return clip


def _breathing(period=60.0, amount=1.0):
    def fn(t, k):
        b = math.sin(TAU * t / period) * amount
        k["bend"] += -1.3 * b
        k["nod"] += 1.2 * b
        x, y, z = k["hip"]
        k["hip"] = (x, y, z + 0.003 * b)
    return fn


def ready(rig, made):
    c = Clip("Ready", 60, loop=True, notes="Two-point stance for receivers and defenders before the snap; light bounce on the balls of the feet.")
    c.key(0, poses.ready())

    def life(t, k):
        bounce = math.sin(TAU * t / 30.0)
        shift = math.sin(TAU * t / 60.0 + 0.6)
        x, y, z = k["hip"]
        k["hip"] = (x + 0.014 * shift, y, z + 0.010 * bounce)
        k["roll"] = -1.2 * shift
        k["turn"] = 7.0 * math.sin(TAU * t / 60.0 - 0.9)
        k["bend"] += -1.2 * bounce
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            leg = k["leg" + side]
            k["leg" + side] = leg.but(roll=leg.roll + 3.5 * bounce)
            arm = k["arm" + side]
            wiggle = 0.5 + 0.5 * math.sin(TAU * t / 20.0 + (0.0 if side == "L" else 1.3))
            k["arm" + side] = arm.but(fwd=arm.fwd - 4.0 * bounce, elbow=arm.elbow + 5.0 * bounce,
                                      out=arm.out + 2.0 * sgn * shift, grip=0.15 + 0.3 * wiggle)

    c.mod(life)
    return c


def stance3(rig, made):
    c = Clip("Stance3", 60, loop=True, notes="Three-point lineman stance, right hand on the ground; nearly still.")
    c.key(0, poses.stance3())
    c.mod(_breathing(60.0, 0.9))
    c.mod(lambda t, k: k.__setitem__("turn", 3.0 * math.sin(TAU * t / 60.0 + 1.0)))
    return c


def stance_center(rig, made):
    c = Clip("StanceCenter", 60, loop=True, ball="none",
             notes="Centre crouched over the ball: right hand on a ball lying on the ground 0.45 m in front of the "
                   "root (ball centre (0, -0.45, 0.085), long axis along Y). The ball is not socketed.")
    c.key(0, poses.center())
    c.mod(_breathing(60.0, 0.9))
    c.mod(lambda t, k: k.__setitem__("turn", 9.0 * math.sin(TAU * t / 60.0)))
    c.prop = lambda f, pose: poses.ball_matrix(poses.CENTER_BALL)
    c.extra["ball_on_ground"] = list(poses.CENTER_BALL)
    return c


def stance_qb(rig, made):
    c = Clip("StanceQB", 60, loop=True, notes="Quarterback in the shotgun: slight crouch, open hands in front of the chest.")
    c.key(0, poses.stance_qb())

    def life(t, k):
        shift = math.sin(TAU * t / 60.0)
        bounce = math.sin(TAU * t / 30.0)
        x, y, z = k["hip"]
        k["hip"] = (x + 0.016 * shift, y, z + 0.006 * bounce)
        k["roll"] = -1.3 * shift
        k["side"] = 1.3 * shift
        k["turn"] = 14.0 * math.sin(TAU * t / 30.0) * math.cos(TAU * t / 120.0) ** 2
        k["bend"] += -1.0 * bounce
        for side in "LR":
            arm = k["arm" + side]
            flex = math.sin(TAU * t / 20.0) * (1.0 if side == "L" else -1.0)
            px, py, pz = arm.pos
            k["arm" + side] = arm.but(grip=0.08 + 0.07 * flex, pos=(px, py - 0.012 * bounce, pz + 0.01 * bounce))

    c.mod(life)
    return c


def qb_set(rig, made):
    c = Clip("QBSet", 40, loop=True, ball="hand",
             notes="In the pocket, half turned to the right, ball at the chest in both hands, bouncing on the toes, "
                   "head scanning. Frame 0 is the pose CatchSnap ends in and Throw / Handoff start from.")
    c.key(0, poses.qb_set())

    def life(t, k):
        ph = t / 40.0
        bounce = math.sin(TAU * t / 10.0)                    # four little bounces
        x, y, z = k["hip"]
        k["hip"] = (x, y, z + 0.011 * bounce)
        k["turn"] = 24.0 * math.sin(TAU * ph)
        k["twist"] += 3.0 * math.sin(TAU * ph)
        k["bend"] += -0.8 * bounce
        for side, lag in (("L", 0.0), ("R", 0.5)):
            leg = k["leg" + side]
            patter = max(0.0, math.sin(TAU * (t / 20.0 + lag)))  # feet patter alternately
            k["leg" + side] = leg.but(roll=leg.roll + 8.0 * bounce + 10.0 * patter, z=0.012 * patter)
        arm = k["armR"]
        px, py, pz = arm.pos
        k["armR"] = arm.but(pos=(px, py, pz + 0.008 * math.sin(TAU * t / 10.0)))

    c.mod(life)
    return c


def _qb_arms(g, ph, side):
    right, left = poses.two_hands(pos=(-0.10, -0.25, 1.43), axis=(0.2, -0.25, 0.95), palm=(0.85, -0.5, 0.15))
    if side == "L":
        return left
    x, y, z = right.pos
    return right.but(pos=(x, y, z + 0.012 * wave(ph * 2.0, 0.2)))


QB_DROP = Gait(frames=20, speed=3.5, travel=(0.0, 1.0), duty=0.2, mid={"L": -0.215, "R": 0.28},
               base={"L": (0.07, 0.0), "R": (-0.07, 0.0)}, toe_out=6.0, foot_yaw=-40.0,
               roll=[(0.0, 14.0), (0.3, 0.0), (0.6, 2.0), (1.0, 34.0)],
               swing={"L": [(0.3, -0.36, 0.21), (0.7, -0.10, 0.20)], "R": [(0.3, 0.16, 0.20), (0.7, 0.42, 0.21)]},
               swing_pitch=[(0.5, -10.0)],
               hip=(0.0, 0.02, 0.865), bob=0.028, bob_at=0.1, sway=0.0, pitch=5.0, bend=6.0,
               yaw0=-40.0, yaw=0.0, twist0=-14.0, twist=0.0, roll_amp=2.0, arms=_qb_arms)


def qb_drop(rig, made):
    return _gait_clip(rig, "QBDrop", QB_DROP, ball="hand",
                      notes="Drop-back: moves BACKWARD (+Y) at `speed`, body turned to the right, ball high in both "
                            "hands, eyes downfield. Frame 0 = left foot contact, frame 10 = right foot contact.")


def block_loop(rig, made):
    c = Clip("BlockLoop", 30, loop=True, notes="Engaged blocker: low base, feet chopping (3 steps per foot), "
                                               "alternating hand strikes and a braced recovery.")
    c.key(0, poses.block())

    def life(t, k):
        u = (t % 15.0) / 15.0
        punch = math.sin(math.pi * 0.5 * min(u / 0.27, 1.0)) if u < 0.27 else 0.5 * (1.0 + math.cos(math.pi * (u - 0.27) / 0.73))
        x, y, z = k["hip"]
        chop = math.sin(TAU * t / 10.0)
        k["hip"] = (x + 0.012 * chop, y - 0.05 * punch, z + 0.008 * abs(chop) + 0.012 * punch)
        k["pitch"] += 4.0 * punch
        k["roll"] = -2.5 * chop
        k["twist"] += 7 * math.sin(TAU * t / 30.0)
        k["bend"] += -3.0 * punch
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            lift = max(0.0, sgn * chop)
            leg = k["leg" + side]
            k["leg" + side] = leg.but(z=0.045 * lift ** 2, roll=leg.roll + 16.0 * lift)
            arm = k["arm" + side]
            px, py, pz = arm.pos
            drive = max(0.0, math.sin(TAU * t / 30.0) * sgn) ** 1.3
            k["arm" + side] = arm.but(pos=(px + 0.024 * sgn * (1-drive), py + 0.09 - 0.16 * drive,
                                            pz - 0.04 + 0.07 * drive))

    c.mod(life)
    return c


def down_back(rig, made):
    c = Clip("DownBack", 30, loop=True, notes="Flat on the back, head toward +Y, pelvis 0.25 m behind the root. "
                                              "Anchor pose for HitBack / HitFlip / GetUpBack.")
    c.key(0, poses.down_back())

    def life(t, k):
        b = math.sin(TAU * t / 30.0)
        k["bend"] += -1.6 * b
        k["nod"] += 1.5 * b
        k["turn"] += 3.0 * b
        arm = k["armR"]
        k["armR"] = arm.but(grip=arm.grip + 0.15 * b)

    c.mod(life)
    return c


def down_front(rig, made):
    c = Clip("DownFront", 30, loop=True, notes="Face down, head toward -Y, pelvis 0.25 m in front of the root. "
                                               "Anchor pose for dives, HitFront / HitSpin and GetUpFront.")
    c.key(0, poses.down_front())

    def life(t, k):
        b = math.sin(TAU * t / 30.0)
        k["bend"] += -1.4 * b
        k["nod"] += -1.5 * b
        k["turn"] += 2.5 * b
        arm = k["armL"]
        k["armL"] = arm.but(grip=arm.grip + 0.05 * max(0.0, b))

    c.mod(life)
    return c
