"""Tier 3: personality -- celebrations, gestures and the two silliest hits."""
import math

from mathutils import Vector

from . import poses
from .clip import Clip, E
from .clips_action import A, L, _jump, flight, palm_hand, upright, where, xyz
from .controls import ArmFK, ArmIK, LegFK, LegIK, Plant
from .gait import TAU, smooth, track
from .preview import ball_matrix, socket_matrix


def _fists(side, pos, **kw):
    """Fist placed by the wrist in the upright torso space."""
    s = 1.0 if side == "L" else -1.0
    spec = ArmIK(pos=(pos[0] * s, pos[1], pos[2]), space="torso", pole=(0.8 * s, 0.4, -0.45), pspace="torso",
                 grip=0.95, thumb=0.8, flex=10.0)
    return spec.but(**kw)


# ---- 40 CelebSpike ----------------------------------------------------------------------------
def celeb_spike(rig, made):
    c = Clip("CelebSpike", 50, ball="hand", tier=3,
             notes="")
    start, end = poses.carry(), poses.idle()
    c.key(0, start, hand2tuck=1.0, gaze=1.0, nod=0.0)
    c.key(5, hand2tuck=0.0)

    def grip(pos, palm, pole, **kw):
        return poses.hold(pos, axis=(1.0, 0.0, 0.0), palm=palm, space="torso", hspace="torso", pole=pole, pspace="torso", **kw)

    c.key(4, armR=grip((-0.26, -0.20, 1.52), (0.0, -0.6, 0.8), (-0.8, 0.4, -0.4)))
    c.key(9, armR=grip((-0.24, 0.10, 2.06), (0.0, -1.0, 0.1), (-0.7, -0.6, 0.0)), ease="out")
    c.key(11, armR=grip((-0.24, 0.12, 2.07), (0.0, -1.0, 0.0), (-0.7, -0.6, 0.0)))
    c.key(12.5, armR=grip((-0.24, -0.34, 1.86), (0.0, -0.9, -0.3), (-0.8, -0.2, 0.3)))
    c.key(14, armR=grip((-0.22, -0.52, 1.02), (0.0, -0.35, -0.94), (-0.8, 0.5, 0.2), grip=0.1, thumb=0.1), ease="lin")
    c.key(17, armR=A(18.0, out=4.0, twist=20.0, elbow=12.0, pron=60.0, grip=0.2), ease="out")
    # body: load up tall and arched, crunch down through the spike
    c.key(4, hip=(0.0, 0.02, 0.93), pitch=2.0, bend=2.0, twist=-10.0)
    c.key(9, hip=(0.0, 0.05, 0.99), pitch=-10.0, bend=-16.0, twist=-18.0, nod=-12.0, ease="out")
    c.key(11, hip=(0.0, 0.05, 1.0), pitch=-11.0, bend=-17.0, twist=-18.0, nod=-12.0)
    c.key(14, hip=(0.0, -0.06, 0.86), pitch=E(30.0, "in"), bend=E(30.0, "in"), twist=E(16.0, "in"), nod=20.0, ease="in")
    c.key(17, hip=(0.0, -0.08, 0.80), pitch=44.0, bend=34.0, twist=22.0, nod=24.0, ease="out")
    c.key(22, hip=(0.0, -0.04, 0.84), pitch=30.0, bend=22.0, twist=6.0, nod=0.0)
    # the flex: hop, stomp wide, crab the arms, roar forward
    c.key(26, hip=(0.0, -0.02, 0.97), pitch=8.0, bend=0.0, twist=0.0, nod=-10.0)
    c.key(29, hip=(0.0, -0.02, 0.80), pitch=E(24.0, "in"), bend=E(20.0, "in"), nod=-34.0)
    c.key(31, hip=(0.0, -0.02, 0.78), pitch=26.0, bend=22.0, nod=-36.0)
    c.key(36, hip=(0.0, -0.02, 0.81), pitch=22.0, bend=16.0, nod=-30.0)
    c.key(41, hip=(0.0, -0.02, 0.79), pitch=26.0, bend=22.0, nod=-36.0)
    c.key(50, hip=end["hip"], pitch=end["pitch"], bend=end["bend"], nod=end["nod"], gaze=0.0)
    c.key(41, gaze=1.0)
    crab = dict(armL=A(34.0, out=34.0, twist=74.0, elbow=96.0, flex=50.0, grip=1.0, thumb=1.0, shrug=8.0),
                armR=A(34.0, out=34.0, twist=74.0, elbow=96.0, flex=50.0, grip=1.0, thumb=1.0, shrug=8.0))
    loose = dict(armL=A(40.0, out=44.0, twist=50.0, elbow=80.0, flex=30.0, grip=1.0, thumb=1.0, shrug=4.0),
                 armR=A(40.0, out=44.0, twist=50.0, elbow=80.0, flex=30.0, grip=1.0, thumb=1.0, shrug=4.0))
    c.key(6, armL=A(40.0, out=50.0, twist=0.0, elbow=30.0, grip=0.3))
    c.key(10, armL=A(20.0, out=64.0, twist=0.0, elbow=20.0, grip=0.3))
    c.key(15, armL=A(-40.0, out=30.0, twist=10.0, elbow=40.0, grip=0.6), ease="in")
    c.key(23, armL=A(10.0, out=30.0, twist=30.0, elbow=60.0, grip=0.9), armR=A(20.0, out=20.0, twist=30.0, elbow=50.0, grip=0.9))
    c.key(26, loose)
    c.key(29.5, crab, ease="in")
    c.key(33, crab)
    c.key(36, loose)
    c.key(39, crab, ease="in")
    c.key(43, crab)
    c.key(50, armL=end["armL"], armR=end["armR"])
    # feet: up on the toes for the wind-up, flat for the slam, hop and stomp wide for the flex
    wide = dict(legL=Plant(0.30, -0.02, out=22.0), legR=Plant(-0.30, 0.02, out=22.0))
    c.key(4, legL=Plant(0.17, -0.01, out=10.0), legR=Plant(-0.17, 0.02, out=10.0))
    c.key(10, legL=Plant(0.17, -0.01, out=10.0, roll=44.0), legR=Plant(-0.17, 0.02, out=10.0, roll=44.0))
    c.key(14, legL=Plant(0.17, -0.01, out=10.0), legR=Plant(-0.17, 0.02, out=10.0), ease="in")
    c.key(24, legL=Plant(0.17, -0.01, out=10.0, roll=30.0), legR=Plant(-0.17, 0.02, out=10.0, roll=30.0))
    c.key(26.5, legL=Plant(0.25, -0.02, out=18.0, z=0.12, roll=20.0), legR=Plant(-0.25, 0.02, out=18.0, z=0.12, roll=20.0))
    c.key(29, wide, ease="in")
    c.key(44, wide)
    c.key(47, legL=Plant(0.30, -0.02, out=22.0), legR=Plant(-0.17, 0.02, out=10.0, arc=0.05))
    c.key(50, legL=Plant(0.17, -0.01, out=10.0, arc=0.05), legR=Plant(-0.17, 0.02, out=10.0))
    c.event("spike", 14)
    c.event("stomp", 29)
    c.ball_frames = (0, 14)
    c.key_frame = 11
    out = where(rig, c, 14, "ball_hand_r")
    fall = flight(out, (0.0, -1.0, -16.0), 14, gravity=0.0)
    bounce = flight((out.x, out.y - 0.04, 0.10), (0.3, -2.4, 5.2), 15)
    c.extra["release_point"] = [round(v, 2) for v in out]
    c.notes = ("Spike and flex: the ball goes up overhead in the right hand and is slammed into the turf at "
               f"`spike` (it leaves ball_hand_r at {xyz(out)}, going straight down), then a hop, a stomping low "
               "flex with two pulses, and back to the Idle stand. Starts with ball_hand_r sitting on ball_tuck_r, "
               "so it follows a tuck clip without a pop.")

    def prop(f, pose):
        if f <= 14:
            return socket_matrix(pose, "hand")
        if f < 16:
            return ball_matrix(fall(f), axis=(1.0, 0.0, 0.3))
        p = bounce(f)
        if f <= 24 and p.z > 0.09:
            return ball_matrix(p, axis=(1.0, 0.4 * (f - 15), 0.5))
        return None

    c.prop = prop
    return c


# ---- 41 CelebDance ----------------------------------------------------------------------------
def celeb_dance(rig, made):
    c = Clip("CelebDance", 40, loop=True, tier=3,
             notes="Looping end-zone dance: hips swing side to side with a step-touch (20-frame period) with alternating "
                   "cross-body punches, knees bouncing and the "
                   "head bobbing on every beat.")

    def source(t):
        sway = math.sin(TAU * t / 20.0)                # + = hips to the character's left
        lead = math.sin(TAU * t / 20.0 + 0.9)
        beat = math.cos(TAU * t / 10.0)                # +1 on the beat (down)
        k = dict(
            hip=(0.11 * sway, 0.0, 0.865 - 0.045 * beat),
            roll=-12.0 * sway, side=17.0 * sway, yaw=10.0 * lead, twist=-16.0 * lead,
            pitch=6.0 + 3.0 * beat, bend=6.0 + 4.0 * beat,
            nod=9.0 * beat, tilt=-12.0 * sway, turn=10.0 * lead, clamp=0.0,
        )
        # step-touch: the unloaded foot lifts and taps in next to the other
        for side, s in (("L", 1.0), ("R", -1.0)):
            free = max(0.0, -s * sway)                 # 1 when the hips are over the OTHER foot
            k["leg" + side] = Plant(s * (0.22 - 0.09 * free), 0.02 * s - 0.03 * free, out=14.0 - 6.0 * free,
                                    z=0.07 * math.sin(math.pi * free) ** 2, roll=26.0 * free)
        # Plant into the beat, then punch diagonally across the body with the opposite fist.
        for side, s in (("L", 1.0), ("R", -1.0)):
            hit = max(0.0, -s * math.sin(TAU * t / 40.0)) ** 1.6
            k["arm" + side] = _fists(side, (0.26 - 0.27 * hit, -0.22 - 0.20 * hit,
                                            1.20 + 0.54 * hit + 0.03 * beat), shrug=8.0 * hit)
        return k

    c.source = source
    c.key_frame = 5
    return c


# ---- 42 CelebFlex -----------------------------------------------------------------------------
def celeb_flex(rig, made):
    c = Clip("CelebFlex", 50, ball="none", tier=3,
             notes="Gather low, then explode into a double-biceps flex with the chest out and the head thrown "
                   "back, roaring at the sky; two pumps (frames 20 and 29), then back to an idle stand.")
    start = poses.idle()
    c.key(0, start)
    low = A(34.0, out=-8.0, twist=70.0, elbow=78.0, flex=30.0, grip=1.0, thumb=1.0)
    flex = A(4.0, out=94.0, twist=-90.0, elbow=118.0, flex=48.0, grip=1.0, thumb=1.0, shrug=10.0)
    half = A(4.0, out=84.0, twist=-90.0, elbow=92.0, flex=30.0, grip=1.0, thumb=1.0, shrug=2.0)
    c.key(6, hip=(0.0, 0.03, 0.80), pitch=20.0, bend=22.0, nod=26.0, armL=low, armR=low)
    c.key(11, hip=(0.0, -0.01, 0.95), pitch=E(-8.0, "in"), bend=E(-18.0, "in"), nod=E(-40.0, "in"), armL=flex, armR=flex, ease="in")
    c.key(14, hip=(0.0, -0.01, 0.93), pitch=-6.0, bend=-16.0, nod=-38.0, armL=flex, armR=flex, ease="out")
    for f in (20, 29):
        c.key(f - 3, hip=(0.0, -0.01, 0.905), pitch=-2.0, bend=-8.0, nod=-28.0, armL=half, armR=half)
        c.key(f, hip=(0.0, -0.01, 0.95), pitch=-8.0, bend=-18.0, nod=-42.0, armL=flex, armR=flex, ease="in")
    c.key(38, hip=(0.0, -0.01, 0.93), pitch=-6.0, bend=-16.0, nod=-38.0, armL=flex, armR=flex)
    c.key(50, start)
    wide = dict(legL=Plant(0.27, -0.02, out=20.0), legR=Plant(-0.27, 0.02, out=20.0))
    c.key(6, legL=start["legL"].but(roll=10.0), legR=start["legR"].but(roll=10.0))
    c.key(8.5, legL=Plant(0.22, -0.02, out=16.0, z=0.07, roll=30.0), legR=Plant(-0.22, 0.02, out=16.0, z=0.07, roll=30.0))
    c.key(11, wide, ease="in")
    c.key(41, wide)
    c.key(45, legL=Plant(0.27, -0.02, out=20.0), legR=start["legR"].but(arc=0.05))
    c.key(49, legL=start["legL"].but(arc=0.05), legR=start["legR"])

    def tremble(t, k):
        w = track([(11, 0.0), (13, 1.0), (38, 1.0), (42, 0.0)], t)
        if w <= 0.0:
            return
        shake = math.sin(TAU * t / 3.0) * w
        for side in "LR":
            arm = k["arm" + side]
            if isinstance(arm, ArmFK):
                k["arm" + side] = arm.but(elbow=arm.elbow + 2.5 * shake, out=arm.out + 1.2 * shake)
        k["turn"] = 3.0 * math.sin(TAU * t / 4.0) * w

    c.mod(tremble)
    c.event("flex", 11)
    c.key_frame = 14
    return c


# ---- 43 Dejected ------------------------------------------------------------------------------
def dejected(rig, made):
    c = Clip("Dejected", 60, loop=True, tier=3,
             notes="Head down, hands on hips, weight on one leg; a long sigh and a slow shake of the head.")

    def hand(s):
        return ArmIK(pos=(0.205 * s, -0.035, 1.035), space="pelvis", pole=(0.8 * s, 0.6, 0.1), pspace="pelvis",
                     palm=(-0.9 * s, 0.3, -0.3), hspace="pelvis", grip=0.35, thumb=0.2)

    c.key(0, hip=(0.03, 0.01, 0.935), roll=-4.0, side=5.0, pitch=5.0, bend=16.0, nod=40.0, tilt=3.0,
          armL=hand(1.0), armR=hand(-1.0),
          legL=Plant(0.16, 0.0, out=12.0), legR=Plant(-0.19, -0.05, out=18.0, roll=6.0))

    def life(t, k):
        sigh = math.sin(TAU * t / 60.0)
        shake = math.sin(TAU * t / 30.0) * (0.5 - 0.5 * math.cos(TAU * t / 60.0))
        k["bend"] += -3.0 * sigh
        k["nod"] += 3.0 * sigh
        k["turn"] = 11.0 * shake
        x, y, z = k["hip"]
        k["hip"] = (x + 0.006 * sigh, y, z + 0.005 * sigh)
        for side in "LR":
            k["arm" + side] = k["arm" + side].but(shrug=4.0 * sigh)

    c.mod(life)
    return c


# ---- 44 Signal1st -----------------------------------------------------------------------------
def signal_1st(rig, made):
    c = Clip("Signal1st", 30, ball="none", tier=3,
             notes="First-down signal: the right arm winds up by the ear and chops forward to point downfield with "
                   "a step of the left foot (`point`), a second small chop, then back to an idle stand.")
    start = poses.idle()
    c.key(0, start, gaze=1.0, nod=0.0)
    blade = dict(grip=0.0, thumb=0.0)
    c.key(5, hip=(0.0, 0.05, 0.955), pitch=-4.0, bend=-4.0, twist=-22.0,
          armR=A(118.0, out=26.0, twist=6.0, elbow=122.0, **blade), armL=A(20.0, out=14.0, twist=40.0, elbow=60.0, grip=0.8))
    c.key(9, hip=(0.0, -0.12, 0.90), pitch=E(15.0, "in"), bend=E(8.0, "in"), twist=E(26.0, "in"), ease="in")
    c.key(9, armR=A(114.0, out=2.0, twist=14.0, elbow=3.0, flex=-6.0, **blade), armL=A(-34.0, out=16.0, twist=30.0, elbow=78.0, grip=0.9))
    c.key(11, hip=(0.0, -0.13, 0.895), pitch=17.0, bend=9.0, twist=28.0, armR=A(110.0, out=2.0, twist=14.0, elbow=2.0, flex=-6.0, **blade),
          ease="out")
    c.key(14, armR=A(132.0, out=4.0, twist=14.0, elbow=28.0, **blade), hip=(0.0, -0.12, 0.91), pitch=13.0)
    c.key(16.5, armR=A(112.0, out=2.0, twist=14.0, elbow=2.0, flex=-6.0, **blade), hip=(0.0, -0.13, 0.895), pitch=17.0, ease="in")
    c.key(22, armR=A(112.0, out=2.0, twist=14.0, elbow=3.0, flex=-6.0, **blade), hip=(0.0, -0.13, 0.90), pitch=16.0, bend=9.0, twist=28.0,
          armL=A(-34.0, out=16.0, twist=30.0, elbow=78.0, grip=0.9))
    c.key(30, start, gaze=1.0, nod=0.0, twist=0.0)
    c.key(5, legL=start["legL"].but(roll=24.0), legR=start["legR"])
    c.key(9, legL=Plant(0.15, -0.34, out=4.0, roll=-8.0, arc=0.09), legR=start["legR"].but(roll=30.0), ease="in")
    c.key(11, legL=Plant(0.15, -0.34, out=4.0), legR=start["legR"].but(roll=38.0))
    c.key(23, legL=Plant(0.15, -0.34, out=4.0), legR=start["legR"].but(roll=38.0))
    c.key(28, legL=start["legL"].but(arc=0.06), legR=start["legR"])
    c.key(30, legL=start["legL"], legR=start["legR"])
    c.event("point", 9)
    c.key_frame = 10
    c.views = ((-42.0, 12.0), (-90.0, 3.0))          # the pointing arm is the right one
    return c


# ---- 45 HitSpin -------------------------------------------------------------------------------
def hit_spin(rig, made):
    c = Clip("HitSpin", 26, ball="none", tier=3,
             notes="Hit from the left side: knocked flat and face down in the air, the body helicopters a full "
                   "turn about the vertical (yaw 0 to 360 over frames 2-17) with arms and legs flung wide, belly "
                   "flops and settles into the DownFront pose. Airborne frames 3-16.")
    end = poses.down_front()
    c.key(0, upright())
    c.key(2, hx=-0.07, hy=0.0, hz=0.96, roll=-26.0, side=-18.0, tilt=-14.0, pitch=10.0, ease="out")
    c.key(0, yaw=0.0)
    c.key(2, yaw=E(14.0, "in"))
    c.key(17, yaw=E(352.0, "lin"))
    c.key(20, yaw=E(360.0, "out"))
    c.key(7, hz=E(1.06, "out"), hx=-0.04, hy=-0.10, pitch=E(84.0, "out"), roll=-8.0, side=0.0, tilt=0.0, bend=-12.0, nod=-30.0)
    c.key(12, pitch=90.0, roll=6.0, bend=-10.0)
    c.key(16, hz=E(0.22, "in"), hx=0.0, hy=-0.25, pitch=95.0, roll=0.0, bend=-4.0, nod=-20.0, ground=0.0)
    c.key(17, ground=1.0)
    c.key(19, bend=-14.0, nod=-34.0)
    c.key(26, hip=end["hip"], pitch=end["pitch"], bend=end["bend"], nod=end["nod"], turn=end["turn"], ground=1.0)
    c.key(18, turn=0.0)
    star = dict(armL=A(96.0, out=78.0, twist=0.0, elbow=14.0, grip=0.0), armR=A(84.0, out=82.0, twist=0.0, elbow=18.0, grip=0.0),
                legL=L(-6.0, knee=14.0, out=30.0, ankle=-30.0), legR=L(8.0, knee=24.0, out=34.0, ankle=-30.0))
    c.key(3, armL=A(40.0, out=50.0, elbow=30.0, grip=0.1), armR=A(60.0, out=10.0, elbow=40.0, grip=0.1), ease="lin")
    c.key(2, legL=Plant(0.17, -0.01, out=10.0, roll=30.0), legR=Plant(-0.17, 0.02, out=10.0, roll=50.0))
    c.key(6, star)
    c.key(15, armL=A(104.0, out=74.0, twist=0.0, elbow=10.0, grip=0.0), armR=A(92.0, out=78.0, twist=0.0, elbow=12.0, grip=0.0),
          legL=L(-10.0, knee=8.0, out=28.0, ankle=-30.0), legR=L(-4.0, knee=12.0, out=32.0, ankle=-30.0))
    c.key(18.5, armL=end["armL"].but(pos=(0.46, -0.98, 0.036)), armR=end["armR"].but(pos=(-0.52, -0.86, 0.036)))
    c.key(19, legL=L(-20.0, knee=50.0, out=22.0, ankle=-40.0), legR=L(-16.0, knee=36.0, out=26.0, ankle=-40.0), ease="out")
    c.key(24, legL=end["legL"], legR=end["legR"], ease="in")
    c.key(26, armL=end["armL"], armR=end["armR"], legL=end["legL"], legR=end["legR"])
    c.event("land", 16)
    c.key_frame = 9
    return c


# ---- 46 ElbowDrop -----------------------------------------------------------------------------
def elbow_drop(rig, made):
    c = Clip("ElbowDrop", 28, ball="none", tier=3, notes="")
    start, end = poses.idle(), poses.down_front()
    c.key(0, start)
    c.key(3, nod=24.0)                              # looks down at his victim
    # wind-up: elbow cocked high, left hand calling the shot
    cocked = A(150.0, out=34.0, twist=10.0, elbow=128.0, grip=1.0, thumb=1.0)
    c.key(5, hip=(0.0, 0.05, 0.80), pitch=14.0, bend=6.0, twist=-14.0, nod=30.0,
          armR=cocked, armL=A(46.0, out=6.0, twist=20.0, elbow=6.0, grip=0.7, thumb=0.0))
    c.key(0, hz=0.945)
    c.key(5, hz=E(0.80, "io"))
    _jump(c, 7.4, 10.4, 1.34, land_z=0.25)          # lands on frame 16
    c.key(8, hy=-0.02, pitch=10.0, bend=0.0, twist=-6.0, spin=0.0, roll=0.0, side=0.0)
    c.key(11, hy=-0.14, pitch=58.0, spin=62.0, bend=-6.0, twist=0.0, nod=10.0, side=6.0)
    # impact: flat on the right hip, the upper body held up on the elbow
    c.key(15.6, hy=-0.26, pitch=88.0, spin=84.0, bend=6.0, nod=16.0, side=42.0, ground=0.0)
    c.key(18.5, hz=0.27, side=36.0)
    c.key(22, hz=0.25, ground=0.0, pitch=88.0, spin=58.0, side=20.0)
    c.key(25, ground=1.0, spin=16.0, pitch=93.0, side=4.0)
    c.key(28, hip=end["hip"], pitch=end["pitch"], spin=0.0, side=0.0, bend=end["bend"], nod=end["nod"], turn=end["turn"], ground=1.0)
    c.key(22, turn=0.0)
    # right arm: stays cocked, the point of the elbow leading down; left arm thrown wide for the show
    drop = A(150.0, out=45.0, twist=30.0, elbow=132.0, grip=1.0, thumb=1.0)
    c.key(11, armR=A(130.0, out=48.0, twist=20.0, elbow=130.0, grip=1.0, thumb=1.0), armL=A(120.0, out=60.0, twist=0.0, elbow=10.0, grip=0.2))
    c.key(15.6, armR=drop, armL=A(150.0, out=40.0, twist=0.0, elbow=14.0, grip=0.2), ease="in")
    c.key(20, armR=drop.but(elbow=122.0), armL=A(120.0, out=30.0, twist=20.0, elbow=40.0, grip=0.3))
    c.key(26, armL=end["armL"].but(pos=(0.36, -1.00, 0.15)), armR=end["armR"].but(pos=(-0.44, -0.80, 0.15)))
    c.key(28, armL=end["armL"], armR=end["armR"])
    # legs: jump off both feet, kick out behind, slap down
    c.key(5, legL=start["legL"], legR=start["legR"])
    c.key(7.4, legL=start["legL"].but(roll=62.0), legR=start["legR"].but(roll=62.0), ease="in")
    c.key(11, legL=L(-20.0, knee=50.0, out=16.0, ankle=-35.0), legR=L(30.0, knee=70.0, out=10.0, ankle=-30.0))
    c.key(15.6, legL=L(-8.0, knee=20.0, out=14.0, ankle=-35.0), legR=L(6.0, knee=26.0, out=-4.0, ankle=-35.0))
    c.key(19, legL=L(-20.0, knee=52.0, out=20.0, ankle=-35.0), legR=L(4.0, knee=34.0, out=-2.0, ankle=-35.0))
    c.key(22, legL=L(-16.0, knee=40.0, out=14.0, ankle=-40.0), legR=L(-8.0, knee=30.0, out=8.0, ankle=-40.0))
    c.key(24.5, legL=end["legL"].but(pos=(0.17, 0.58, 0.22)), legR=end["legR"].but(pos=(-0.32, 0.42, 0.20)))
    c.key(26.5, legL=end["legL"], legR=end["legR"], ease="in")
    c.key(28, legL=end["legL"], legR=end["legR"])
    c.event("takeoff", 7)
    c.event("hit", 16)
    c.key_frame = 14
    elbow = where(rig, c, 16, "lowerarm_r")
    c.extra["target"] = [round(v, 2) for v in elbow]
    c.notes = ("A cartoonishly late hit: wind up over a player lying in front, jump, lay out sideways and drop "
               f"the right elbow at `hit` -- the point of the elbow comes down at {xyz(elbow)}, about chest "
               "height of someone lying on the ground there -- land on the right hip propped on that elbow, "
               "then roll off onto the front (ends in the DownFront pose). Airborne frames 8-15.")
    return c


def ground_reaction(name, rest, face_down):
    """A short pad bounce that starts and ends in the same floor pose."""
    c = Clip(name, 10, ball="none", tier=3, notes="Recoil from a late elbow, then settle back onto the turf.")
    c.key(0, rest)
    if face_down:
        c.key(2, hip=(-0.03, -0.25, 0.19), pitch=89.0, bend=8.0, nod=-22.0, roll=-10.0,
              legR=rest["legR"].but(pos=(-0.32, 0.40, 0.21)), ease="out")
        c.key(5, hip=(0.01, -0.26, 0.14), pitch=97.0, bend=-10.0, roll=4.0)
    else:
        c.key(2, hip=(0.02, 0.25, 0.18), pitch=-74.0, bend=17.0, nod=29.0, roll=9.0,
              armL=rest["armL"].but(pos=(0.48, 0.45, 0.17)), armR=rest["armR"].but(pos=(-0.41, 0.39, 0.11)),
              legL=rest["legL"].but(pos=(0.22, -0.52, 0.19)), ease="out")
        c.key(5, hip=(-0.01, 0.25, 0.15), pitch=-92.0, bend=-3.0, roll=-4.0)
    c.key(10, rest, roll=0.0)
    c.key_frame = 2
    return c


def ground_hit_back(rig, made):
    return ground_reaction("GroundHitBack", poses.down_back(), False)


def ground_hit_front(rig, made):
    return ground_reaction("GroundHitFront", poses.down_front(), True)
