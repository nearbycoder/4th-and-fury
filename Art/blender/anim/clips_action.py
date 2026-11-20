"""Tier 2: the core football actions (one-shots)."""
import math

from mathutils import Vector

from . import poses
from .clip import Clip, E
from .controls import ArmFK, ArmIK, LegFK, LegIK, Plant, mirror_controls
from .preview import ball_matrix, socket_matrix


def A(fwd, out=10.0, twist=0.0, elbow=10.0, **kw):
    return ArmFK(fwd=fwd, out=out, twist=twist, elbow=elbow, **kw)


def L(fwd, knee=0.0, out=0.0, twist=0.0, ankle=0.0, **kw):
    return LegFK(fwd=fwd, knee=knee, out=out, twist=twist, ankle=ankle, **kw)


def palm_hand(side, pos, palm=(0.0, -1.0, 0.1), up=(0.2, 0.0, 1.0), space="torso", pole=(0.7, 0.3, -0.6), **kw):
    """Open hand placed by its palm centre (mirrored automatically for the right side)."""
    s = 1.0 if side == "L" else -1.0
    spec = ArmIK(pos=(pos[0] * s, pos[1], pos[2]), space=space, at="palm", palm=(palm[0] * s, palm[1], palm[2]),
                 fingers=(up[0] * s, up[1], up[2]), hspace=space, pole=(pole[0] * s, pole[1], pole[2]), pspace=space,
                 grip=0.08, thumb=0.1)
    return spec.but(**kw)


def where(rig, clip, frame, bone, tail=False):
    """World position of a bone (head or tail) of `clip` at `frame`: for the numbers quoted in notes."""
    pose = rig.solve(clip.controls(float(frame)))
    return pose.tail(bone) if tail else pose.head(bone)


def xyz(v, digits=2):
    return "(" + ", ".join(f"{c:.{digits}f}" for c in v) + ")"


def flight(start, velocity, f0, gravity=9.81):
    """Preview-only ball in free flight from frame f0 (positions in metres, velocity in m/s)."""
    start, velocity = Vector(start), Vector(velocity)

    def at(f):
        t = (f - f0) / 30.0
        return start + velocity * t + Vector((0.0, 0.0, -0.5 * gravity * t * t))
    return at


# ---- 15 Snap ----------------------------------------------------------------------------------
def snap(rig, made):
    c = Clip("Snap", 12, ball="none", tier=2,
             notes="Centre fires a shotgun snap back between the legs, then comes up into the BlockLoop pose. "
                   "Starts from StanceCenter. The ball is not socketed: at `release` the right hand is at about "
                   "(0.0, 0.07, 0.27), under the hips, moving back at ~7 m/s.")
    start, end = poses.center(), made["BlockLoop"].controls(0.0)      # ends exactly on BlockLoop frame 0
    c.key(0, start)
    c.key(1, hip=(0.0, 0.25, 0.61), pitch=67.0,
          armR=start["armR"].but(pos=(-0.005, -0.47, 0.166), grip=0.5, thumb=0.7))
    # the whip: hand scoops the ball straight back between the legs
    whip = dict(pole=(-0.8, 0.2, 0.5), pspace="world", grip=0.5, thumb=0.6)
    c.key(3, hip=(0.0, 0.24, 0.63), pitch=66.0, bend=22.0,
          armR=ArmIK(pos=(-0.03, -0.16, 0.20), palm=(0.0, 0.6, -0.8), fingers=(0.0, -0.8, -0.6), **whip), ease="in")
    c.key(4, hip=(0.0, 0.23, 0.65), pitch=68.0, bend=26.0, nod=-40.0,
          armR=ArmIK(pos=(-0.04, 0.07, 0.27), palm=(0.0, 0.9, 0.4), fingers=(0.0, 0.4, -0.9), grip=0.1, thumb=0.1,
                     pole=(-0.8, 0.2, 0.5), pspace="world"), ease="lin")
    c.key(5.5, armR=ArmIK(pos=(-0.08, -0.04, 0.43), palm=(0.0, 0.8, 0.6), fingers=(0.0, 0.6, -0.8), grip=0.0, thumb=0.0,
                          pole=(-0.8, 0.2, 0.5), pspace="world"), ease="out")
    c.key(6, hip=(0.0, 0.20, 0.70), pitch=52.0, bend=18.0)
    # come up into the block: left hand first, right hand follows
    c.key(3, armL=start["armL"])
    c.key(8, armL=end["armL"])
    c.key(11, armR=end["armR"], ease="out")
    c.key(12, hip=E(end["hip"], "out"), pitch=E(end["pitch"], "out"), bend=end["bend"], armL=end["armL"], armR=end["armR"])
    c.key(4, nod=-40.0, gaze=0.0)
    c.key(9, nod=0.0, gaze=1.0)
    # feet: fire out, left foot steps first
    c.key(3, legL=start["legL"], legR=start["legR"])
    c.key(8, legL=end["legL"].but(arc=0.09))
    c.key(7, legR=start["legR"])
    c.key(11, legR=end["legR"].but(arc=0.06))
    c.key(12, legL=end["legL"], legR=end["legR"])
    c.event("release", 4)
    c.key_frame = 4

    ground = ball_matrix(poses.CENTER_BALL)
    fly = flight((-0.04, 0.10, 0.27), (0.0, 9.0, 2.2), 4)

    def prop(f, pose):
        if f <= 1:
            return ground
        if f <= 4:
            hand = pose.world("hand_r") @ rig.palm_point["R"]
            target = hand + Vector((0.0, 0.0, -0.07)) if f < 4 else hand + Vector((0.0, 0.03, -0.02))
            w = (f - 1) / 2.0 if f < 3 else 1.0
            return ball_matrix(ground.translation.lerp(target, min(1.0, w)), axis=(0.0, -1.0, 0.25 * (f - 1)))
        if f <= 8:
            return ball_matrix(fly(f), axis=(0.0, -1.0, 0.3))
        return None

    c.prop = prop
    return c


# ---- 16 CatchSnap -----------------------------------------------------------------------------
def catch_snap(rig, made):
    c = Clip("CatchSnap", 10, ball="hand", tier=2,
             notes="QB takes the shotgun snap at chest height and settles into QBSet frame 0. Starts from StanceQB. "
                   "Attach the ball to ball_hand_r at `catch`.")
    start, end = poses.stance_qb(), poses.qb_set()
    c.key(0, start)
    reach = dict(armL=start["armL"].but(pos=(0.095, -0.44, 1.385), grip=0.0),
                 armR=start["armR"].but(pos=(-0.095, -0.44, 1.385), grip=0.0))
    c.key(2, reach, hip=(0.0, 0.01, 0.885), bend=13.0, nod=6.0)
    right, left = poses.two_hands(pos=(-0.01, -0.44, 1.385), axis=(0.0, 1.0, 0.1), palm=(0.95, -0.3, 0.0), space="torso")
    c.key(4, armR=right, armL=left, ease="in")
    give_r, give_l = poses.two_hands(pos=(-0.03, -0.31, 1.36), axis=(0.1, 0.9, 0.4), palm=(0.9, -0.4, 0.05), space="torso")
    c.key(6, armR=give_r, armL=give_l, hip=(0.0, 0.03, 0.865), bend=16.0, nod=10.0, ease="out")
    c.key(10, end)
    c.key(4, yaw=0.0, twist=0.0, pitch=13.0, turn=0.0)
    c.key(6, legL=start["legL"], legR=start["legR"])
    c.key(4, legR=start["legR"])
    c.key(8, legR=end["legR"].but(arc=0.05))
    c.key(10, legL=end["legL"].but(arc=0.04), legR=end["legR"])
    c.event("catch", 4)
    c.ball_frames = (4, 10)
    c.key_frame = 4
    fly = flight((0.0, -1.55, 1.05), (0.0, 9.0, 1.9), 0)
    c.prop = lambda f, pose: (ball_matrix(fly(f), axis=(0.0, -1.0, 0.2)) if f < 4 else socket_matrix(pose, "hand"))
    return c


# ---- 17 Throw ---------------------------------------------------------------------------------
def throw(rig, made):
    c = Clip("Throw", 24, ball="hand", tier=2,
             notes="")
    start, end = poses.qb_set(), poses.idle()
    c.key(0, start)
    # body: load back, stride, open the hips, then the shoulders
    c.key(4, hip=(0.0, 0.07, 0.905), yaw=-58.0, twist=-26.0, pitch=0.0, bend=2.0, side=6.0)
    c.key(7, hip=(0.01, -0.02, 0.875), yaw=-38.0, twist=-40.0, pitch=2.0, bend=-4.0, side=10.0)
    c.key(9, hip=(0.02, -0.10, 0.88), yaw=E(0.0, "in"), twist=E(-14.0, "in"), pitch=8.0, bend=4.0, side=4.0)
    c.key(10, hip=(0.02, -0.13, 0.885), yaw=E(14.0, "lin"), twist=E(8.0, "lin"), pitch=12.0, bend=10.0, side=-4.0)
    c.key(13, hip=(0.03, -0.17, 0.86), yaw=E(30.0, "out"), twist=E(26.0, "out"), pitch=20.0, bend=24.0, side=-8.0)
    c.key(17, hip=(0.02, -0.16, 0.875), yaw=24.0, twist=14.0, pitch=14.0, bend=14.0, side=-3.0)
    c.key(24, hip=(0.0, -0.17, end["hip"][2]), yaw=0.0, twist=0.0, pitch=end["pitch"], bend=end["bend"], side=0.0)
    c.key(0, gaze=1.0, nod=2.0, turn=0.0)
    c.key(13, nod=10.0)
    c.key(24, gaze=1.0, nod=-2.0)
    # right arm: ball up by the ear, cocked behind the head, then whipped out and released
    # (positions in the upright "torso" space, which turns with the chest; directions in world)
    def grip(pos, axis, palm, pole, **kw):
        return poses.hold(pos, axis=axis, palm=palm, space="torso", hspace="world", pole=pole, pspace="torso", **kw)

    # The palm faces the way the chest faces while cocked and ends "thumb down, palm out" at the
    # release, so the forearm never has to twist past its natural range; the ball's long axis
    # stays on the target line throughout.
    c.key(4, armR=grip((-0.27, -0.05, 1.63), (0.0, -1.0, 0.15), (-1.0, 0.0, 0.0), (-0.8, 0.3, -0.5)))
    c.key(7, armR=grip((-0.35, 0.17, 1.67), (0.0, -1.0, 0.3), (-0.95, 0.0, 0.3), (-0.9, 0.35, 0.05)))
    c.key(9, armR=grip((-0.30, -0.04, 1.88), (0.0, -1.0, 0.25), (-1.0, -0.1, 0.1), (-0.7, -0.5, -0.1)), ease="in")
    c.key(10, armR=grip((-0.24, -0.40, 1.95), (0.0, -1.0, 0.16), (-1.0, 0.0, -0.1), (-1.0, -0.1, 0.15), grip=0.15,
                        thumb=0.2), ease="lin")
    c.key(14, armR=A(48.0, out=-22.0, twist=30.0, elbow=22.0, pron=80.0, flex=30.0, grip=0.15), ease="lin")
    c.key(17, armR=A(20.0, out=-8.0, twist=30.0, elbow=30.0, pron=35.0, flex=10.0, grip=0.3))
    c.key(24, armR=end["armR"])
    # left arm: off the ball, points at the target, then tucks in as the chest comes round
    c.key(2, armL=start["armL"])
    c.key(5, armL=A(52.0, out=58.0, twist=10.0, elbow=38.0, grip=0.3), ease="out")
    c.key(7, armL=A(60.0, out=62.0, twist=0.0, elbow=24.0, grip=0.3))
    c.key(10, armL=A(18.0, out=24.0, twist=50.0, elbow=95.0, grip=0.6), ease="in")
    c.key(13, armL=A(-18.0, out=20.0, twist=40.0, elbow=80.0, grip=0.6))
    c.key(24, armL=end["armL"])
    # feet: weight back, left foot strides at the target, right foot drags up onto the toe
    c.key(3, legL=start["legL"])
    c.key(7.5, legL=Plant(0.11, -0.40, yaw=-12.0, out=4.0, roll=-10.0, arc=0.12))
    c.key(9, legL=Plant(0.11, -0.40, yaw=-12.0, out=4.0))
    c.key(24, legL=Plant(0.11, -0.40, yaw=-12.0, out=4.0))
    c.key(4, legR=start["legR"].but(roll=0.0))
    c.key(8, legR=start["legR"].but(roll=8.0))
    c.key(10, legR=Plant(-0.13, 0.15, yaw=-12.0, out=8.0, roll=38.0), ease="in")
    c.key(14, legR=Plant(-0.15, 0.04, yaw=0.0, out=8.0, roll=58.0))
    c.key(17, legR=Plant(-0.15, 0.04, yaw=0.0, out=8.0, roll=50.0))
    c.key(22, legR=Plant(-0.17, -0.14, out=10.0, arc=0.07))
    c.key(24, legR=Plant(-0.17, -0.14, out=10.0))
    c.event("release", 10)
    c.ball_frames = (0, 10)
    c.key_frame = 10

    def prop(f, pose):
        if f <= 10:
            return socket_matrix(pose, "hand")
        if f <= 13:
            return ball_matrix(prop.fly(f), axis=(0.0, -1.0, 0.1))
        return None

    out = where(rig, c, 10, "ball_hand_r")
    prop.fly = flight(out, (0.0, -19.0, 4.5), 10)
    c.prop = prop
    c.extra["release_point"] = [round(v, 2) for v in out]
    c.notes = ("Overhand pass with the right arm: wind up, step with the left foot, whip, follow through. Starts "
               f"from QBSet frame 0; ends in a staggered athletic stand (left foot 0.4 m forward). Detach the ball "
               f"at `release`: ball_hand_r is then at {xyz(out)} and its Y axis points downfield, slightly up.")
    return c


# ---- 18 Handoff -------------------------------------------------------------------------------
def handoff(rig, made):
    c = Clip("Handoff", 14, ball="hand", tier=2,
             notes="QB turns to his right and extends the ball at belly height. Starts from QBSet frame 0. At `give` "
                   "the ball (ball_hand_r) is about 0.5 m to the right of the root, 1.05 m up, long axis along Y; "
                   "detach it there.")
    start = poses.qb_set()
    c.key(0, start)
    c.key(3, hip=(-0.02, 0.03, 0.90), yaw=-62.0, twist=-10.0, pitch=8.0, bend=12.0, side=-3.0)
    c.key(7, hip=(-0.07, 0.06, 0.875), yaw=E(-80.0, "out"), twist=-12.0, pitch=10.0, bend=16.0, side=-6.0)
    c.key(9, hip=(-0.07, 0.06, 0.88), yaw=-78.0, twist=-10.0, pitch=10.0, bend=14.0)
    c.key(14, hip=(-0.02, 0.02, 0.92), yaw=-40.0, twist=-4.0, pitch=5.0, bend=7.0, side=0.0)
    c.key(0, gaze=1.0, turn=0.0, nod=2.0)
    c.key(5, turn=-55.0, nod=14.0)
    c.key(9, turn=-60.0, nod=14.0)
    c.key(14, turn=-10.0, nod=2.0)
    low_r, low_l = poses.two_hands(pos=(-0.06, -0.30, 1.17), axis=(0.1, 0.75, 0.65), palm=(0.7, -0.2, 0.65))
    c.key(3, armR=low_r, armL=low_l)
    c.key(7, armR=poses.hold((-0.50, 0.10, 1.05), axis=(0.0, 1.0, 0.0), palm=(0.3, 0.0, 0.95), space="world",
                             pole=(0.2, 0.8, -0.6), pspace="world"), ease="out")
    c.key(8, armR=poses.hold((-0.52, 0.10, 1.04), axis=(0.0, 1.0, 0.0), palm=(0.3, 0.0, 0.95), space="world",
                             pole=(0.2, 0.8, -0.6), pspace="world", grip=0.05, thumb=0.1))
    c.key(11, armR=A(22.0, out=6.0, twist=55.0, elbow=70.0, grip=0.3))
    c.key(14, armR=A(14.0, out=8.0, twist=48.0, elbow=55.0, grip=0.4))
    c.key(4.5, armL=low_l)
    c.key(7, armL=A(28.0, out=-4.0, twist=70.0, elbow=88.0, grip=0.3), ease="out")
    c.key(14, armL=A(18.0, out=6.0, twist=55.0, elbow=60.0, grip=0.4))
    for f, yaw, roll in ((0, -30.0, 10.0), (4, -58.0, 16.0), (7, -66.0, 4.0), (14, -50.0, 4.0)):
        c.key(f, legL=Plant(0.14, -0.14, yaw=yaw, out=8.0, roll=roll),
              legR=Plant(-0.13, 0.15, yaw=yaw, out=8.0, roll=roll if f == 0 else roll * 0.5))
    c.event("give", 7)
    c.ball_frames = (0, 7)
    c.key_frame = 7
    c.views = ((0.0, 8.0), (-48.0, 12.0))          # the action faces the character's right
    return c


# ---- 19 CatchChest ----------------------------------------------------------------------------
def _hands_up(y=-0.42, z=1.40, spread=0.10):
    return dict(armL=palm_hand("L", (spread, y, z), palm=(-0.35, -0.93, 0.0), up=(0.25, -0.1, 0.96)),
                armR=palm_hand("R", (spread, y, z), palm=(-0.35, -0.93, 0.0), up=(0.25, -0.1, 0.96)))


def catch_chest(rig, made):
    c = Clip("CatchChest", 14, ball="hand", tier=2,
             notes="Catch at chest height: arms snap up, hands meet the ball, ball secured into the right-arm tuck. "
                   "Works standing or as an upper-body layer over a run (the legs only give a little). Attach the "
                   "ball to ball_hand_r at `catch`; by the last frame ball_hand_r has slid onto ball_tuck_r, so "
                   "switching to a tuck clip does not pop.")
    start = poses.idle()
    c.key(0, start, gaze=1.0, nod=0.0)
    c.key(3.5, _hands_up(), ease="lin")
    c.key(3, hip=(0.0, 0.0, 0.94), bend=4.0, nod=4.0)
    right, left = poses.two_hands(pos=(-0.01, -0.44, 1.39), axis=(0.0, 1.0, 0.05), palm=(0.95, -0.3, 0.0), space="torso")
    c.key(6, armR=right, armL=left, hip=(0.0, 0.01, 0.93), bend=6.0, nod=8.0)
    in_r, in_l = poses.two_hands(pos=(-0.05, -0.26, 1.30), axis=(0.25, 0.75, 0.6), palm=(0.8, -0.55, 0.2), space="torso")
    c.key(9, armR=in_r, armL=in_l, hip=(0.0, 0.03, 0.915), bend=E(15.0, "out"), pitch=7.0, nod=14.0, ease="out")
    c.key(9, hand2tuck=0.0)
    c.key(14, armR=poses.tuck(), armL=poses.relaxed(fwd=12.0, elbow=45.0), hand2tuck=1.0,
          hip=start["hip"], bend=start["bend"], pitch=start["pitch"], nod=0.0)
    c.event("catch", 6)
    c.ball_frames = (6, 14)
    c.key_frame = 6
    fly = flight((0.0, -2.45, 1.52), (0.0, 10.0, 0.6), 0)
    c.prop = lambda f, pose: (ball_matrix(fly(f), axis=(0.0, -1.0, 0.05)) if f < 6 else socket_matrix(pose, "hand"))
    return c


# ---- jumps ------------------------------------------------------------------------------------
def _jump(c, takeoff, apex, top, land_z=0.97, start_z=1.02):
    """Ballistic pelvis height: leaves the ground at `takeoff`, peaks at `apex` (m), lands when it has
    fallen back to land_z. Returns the landing frame."""
    rise = top - start_z
    k = rise / (apex - takeoff) ** 2
    land = apex + math.sqrt((top - land_z) / k)
    c.key(takeoff, hz=start_z)
    c.key(apex, hz=E(top, "out"))
    c.key(land, hz=E(land_z, "in"))
    return land


# ---- 20 CatchHigh -----------------------------------------------------------------------------
def catch_high(rig, made):
    c = Clip("CatchHigh", 26, ball="hand", tier=2,
             notes="")
    start = poses.idle()
    feet = dict(legL=Plant(0.17, -0.01, out=10.0), legR=Plant(-0.17, 0.02, out=10.0))
    c.key(0, start, gaze=0.0, nod=-9.0)
    c.key(0, hz=0.945)
    c.key(4, hz=E(0.70, "io"))
    land = _jump(c, 5.6, 10.0, 1.48)
    c.key(19, hz=E(0.74, "out"))
    c.key(26, hz=E(0.945, "io"))
    c.key(4, pitch=30.0, bend=14.0, nod=-40.0, hy=0.03)
    c.key(6, pitch=8.0, bend=0.0, nod=-30.0, hy=0.0)
    c.key(10, pitch=-2.0, bend=-8.0, nod=-28.0)
    c.key(14, pitch=4.0, bend=6.0, nod=-5.0)
    c.key(19, pitch=30.0, bend=16.0, nod=-12.0, hy=0.03)
    c.key(26, pitch=start["pitch"], bend=start["bend"], nod=-9.0, hy=0.0)
    # arms: swing back, throw up, catch overhead, pull down, tuck
    c.key(3.5, armL=A(-46.0, out=14.0, elbow=30.0, grip=0.2), armR=A(-46.0, out=14.0, elbow=30.0, grip=0.2))
    c.key(8, armL=A(145.0, out=14.0, twist=10.0, elbow=30.0, grip=0.0), armR=A(145.0, out=14.0, twist=10.0, elbow=30.0, grip=0.0))
    up_r, up_l = poses.two_hands(pos=(-0.02, -0.30, 2.03), axis=(0.0, 1.0, 0.1), palm=(0.97, -0.1, 0.2), space="chest")
    up_r, up_l = up_r.but(pole=(-0.8, -0.5, 0.0)), up_l.but(pole=(0.8, -0.5, 0.0))
    c.key(10, armR=up_r, armL=up_l)
    mid_r, mid_l = poses.two_hands(pos=(-0.04, -0.30, 1.62), axis=(0.1, 0.9, 0.4), palm=(0.9, -0.4, 0.1), space="chest")
    c.key(14, armR=mid_r, armL=mid_l)
    in_r, in_l = poses.two_hands(pos=(-0.06, -0.25, 1.30), axis=(0.25, 0.75, 0.6), palm=(0.8, -0.55, 0.2), space="chest")
    c.key(19, armR=in_r, armL=in_l, hand2tuck=0.0)
    c.key(26, armR=poses.tuck(), armL=poses.relaxed(fwd=12.0, elbow=45.0), hand2tuck=1.0)
    # legs
    c.key(4, feet)
    c.key(5.6, legL=Plant(0.17, -0.01, out=10.0, roll=62.0), legR=Plant(-0.17, 0.02, out=10.0, roll=62.0), ease="in")
    c.key(8, legL=L(-12.0, knee=22.0, ankle=-35.0), legR=L(6.0, knee=30.0, ankle=-35.0))
    c.key(10, legL=L(-16.0, knee=30.0, ankle=-38.0), legR=L(16.0, knee=52.0, ankle=-30.0))
    c.key(13, legL=L(4.0, knee=14.0, ankle=-30.0), legR=L(10.0, knee=20.0, ankle=-30.0))
    c.key(land, legL=Plant(0.19, -0.04, out=12.0, roll=42.0), legR=Plant(-0.19, 0.03, out=12.0, roll=42.0))
    c.key(18, legL=Plant(0.19, -0.04, out=12.0), legR=Plant(-0.19, 0.03, out=12.0), ease="out")
    c.key(26, legL=Plant(0.19, -0.04, out=12.0), legR=Plant(-0.19, 0.03, out=12.0))
    c.event("takeoff", 6)
    c.event("catch", 10)
    c.event("land", int(round(land)))
    c.ball_frames = (10, 26)
    c.key_frame = 10
    top = where(rig, c, 10, "ball_hand_r")
    fly = flight(top + Vector((0.0, -1.9, -0.33)), (0.0, 5.7, 2.6), 0)
    c.prop = lambda f, pose: (ball_matrix(fly(f), axis=(0.0, -1.0, 0.2)) if f < 10 else socket_matrix(pose, "hand"))
    c.extra["catch_point"] = [round(v, 2) for v in top]
    c.notes = ("Leaping overhead catch: gather, jump (the pelvis rises 0.5 m), full extension at the apex, land, "
               f"tuck. Attach the ball to ball_hand_r at `catch`, when it is at {xyz(top)}; it ends on the "
               "ball_tuck_r transform, so switching to a tuck clip does not pop.")
    return c


# ---- 21 Swat ----------------------------------------------------------------------------------
def swat(rig, made):
    c = Clip("Swat", 22, ball="none", tier=2,
             notes="")
    start = poses.idle()
    c.key(0, start, gaze=0.0, nod=-9.0)
    c.key(0, hz=0.945)
    c.key(3, hz=E(0.72, "io"))
    land = _jump(c, 4.4, 9.0, 1.44)
    c.key(18, hz=E(0.78, "out"))
    c.key(22, hz=E(0.945, "io"))
    c.key(3, pitch=28.0, bend=12.0, nod=-36.0, twist=-14.0, side=0.0, hy=0.03)
    c.key(6, pitch=6.0, bend=-4.0, nod=-32.0, twist=6.0, side=6.0, hy=0.0)
    c.key(9, pitch=2.0, bend=-6.0, nod=-30.0, twist=20.0, side=12.0)
    c.key(12, pitch=10.0, bend=14.0, nod=0.0, twist=30.0, side=4.0)
    c.key(18, pitch=28.0, bend=12.0, nod=-10.0, twist=6.0, side=0.0, hy=0.03)
    c.key(22, pitch=start["pitch"], bend=start["bend"], nod=-9.0, twist=0.0, hy=0.0)
    c.key(3, armR=A(-60.0, out=16.0, elbow=45.0, grip=0.1), armL=A(-30.0, out=20.0, elbow=40.0, grip=0.4))
    c.key(7.5, armR=A(150.0, out=10.0, twist=20.0, elbow=25.0, pron=40.0, grip=0.0, thumb=0.0), ease="in")
    c.key(9, armR=A(164.0, out=6.0, twist=20.0, elbow=3.0, pron=60.0, flex=-20.0, grip=0.0, thumb=0.0))
    c.key(11, armR=A(118.0, out=2.0, twist=25.0, elbow=6.0, pron=80.0, flex=45.0, grip=0.0, thumb=0.0), ease="in")
    c.key(14, armR=A(60.0, out=6.0, twist=30.0, elbow=30.0, pron=60.0, flex=20.0, grip=0.2), ease="out")
    c.key(22, armR=start["armR"])
    c.key(7.5, armL=A(40.0, out=35.0, elbow=50.0, grip=0.4))
    c.key(10, armL=A(-25.0, out=38.0, elbow=35.0, grip=0.4))
    c.key(18, armL=A(30.0, out=24.0, elbow=50.0, grip=0.4))
    c.key(22, armL=start["armL"])
    feet = dict(legL=Plant(0.17, -0.01, out=10.0), legR=Plant(-0.17, 0.02, out=10.0))
    c.key(3, feet)
    c.key(4.4, legL=Plant(0.17, -0.01, out=10.0, roll=62.0), legR=Plant(-0.17, 0.02, out=10.0, roll=62.0), ease="in")
    c.key(7, legL=L(-10.0, knee=20.0, ankle=-35.0), legR=L(12.0, knee=38.0, ankle=-32.0))
    c.key(9, legL=L(-20.0, knee=34.0, ankle=-38.0), legR=L(22.0, knee=58.0, ankle=-30.0))
    c.key(12, legL=L(6.0, knee=14.0, ankle=-30.0), legR=L(10.0, knee=22.0, ankle=-30.0))
    c.key(land, legL=Plant(0.19, -0.03, out=12.0, roll=42.0), legR=Plant(-0.19, 0.03, out=12.0, roll=42.0))
    c.key(17, legL=Plant(0.19, -0.03, out=12.0), legR=Plant(-0.19, 0.03, out=12.0), ease="out")
    c.key(22, legL=Plant(0.19, -0.03, out=12.0), legR=Plant(-0.19, 0.03, out=12.0))
    c.event("takeoff", 4)
    c.event("apex", 9)
    c.event("land", int(round(land)))
    c.key_frame = 9
    tip = where(rig, c, 9, "fingers_r", tail=True)
    c.notes = (f"Defender leaps and swats with the right arm at full stretch: the fingertips reach {xyz(tip)} at "
               "`apex`, then slap forward and down through frames 9-12.")
    return c


# ---- shared starting pose for contact clips -----------------------------------------------------
def upright(**kw):
    """Upright and moving: slight forward lean, arms bent as in mid-stride."""
    c = poses.idle()
    c.update(pitch=8.0, bend=8.0, nod=-10.0,
             armL=A(14.0, out=10.0, twist=30.0, elbow=75.0, grip=0.6), armR=A(-6.0, out=10.0, twist=30.0, elbow=80.0, grip=0.6))
    c.update(kw)
    return c


def prone(**kw):
    c = poses.down_front()
    c.update(kw)
    return c


# ---- 22 DiveTackle ----------------------------------------------------------------------------
def dive_tackle(rig, made):
    c = Clip("DiveTackle", 24, ball="none", tier=2,
             notes="Launch flat and horizontal with the arms reaching, clamp at `hit`, land and slide prone into "
                   "the DownFront pose. Airborne frames 4-12. The pelvis ends 0.25 m in front of the root.")
    end = poses.down_front()
    c.key(0, upright())
    c.key(2, hip=(0.0, 0.04, 0.76), pitch=40.0, bend=16.0, nod=-36.0,
          armL=A(-40.0, out=18.0, elbow=60.0, grip=0.2), armR=A(-40.0, out=18.0, elbow=60.0, grip=0.2))
    c.key(4, hx=0.0, hy=-0.03, hz=0.84, pitch=64.0, bend=4.0, nod=-44.0)
    c.key(6.5, hz=E(0.90, "out"), hy=-0.12, pitch=E(86.0, "out"), bend=-8.0, nod=-40.0)
    # Catch the far hip with one arm while the other clamps. Hold the line of
    # the shoulders for a beat before the legs swing around on the landing.
    c.key(8, hy=-0.16, pitch=84.0, bend=3.0, twist=12.0, roll=-7.0)
    c.key(9.5, hy=-0.19, pitch=86.0, bend=8.0, twist=16.0, roll=-8.0)
    c.key(13, twist=4.0, roll=-3.0)
    c.key(18, twist=0.0, roll=0.0)
    c.key(12, hz=E(0.20, "in"), hy=-0.25, pitch=93.0, bend=-8.0, nod=-30.0, ground=0.0)
    c.key(13, ground=1.0, pitch=95.0)
    c.key(15, bend=-14.0, nod=-36.0)
    c.key(24, hip=end["hip"], pitch=end["pitch"], bend=end["bend"], nod=end["nod"], turn=end["turn"], ground=1.0)
    c.key(13, turn=0.0)
    # arms reach, clamp, then spill forward on the ground
    c.key(4.5, armL=A(120.0, out=30.0, elbow=30.0, grip=0.0), armR=A(120.0, out=30.0, elbow=30.0, grip=0.0), ease="in")
    c.key(6.0, armL=A(162.0, out=34.0, twist=10.0, elbow=8.0, grip=0.0), armR=A(162.0, out=34.0, twist=10.0, elbow=8.0, grip=0.0))
    c.key(8, armL=palm_hand("L", (0.22, -1.16, 0.83), palm=(-1, 0, 0), up=(0, -1, 0), space="world", grip=0.4),
          armR=palm_hand("R", (0.20, -1.09, 0.77), palm=(-1, 0, 0), up=(0, -1, 0), space="world", grip=0.6), ease="lin")
    c.key(11, armL=palm_hand("L", (0.16, -1.12, 0.56), palm=(-1, 0, 0), up=(0, -1, 0), space="world", grip=0.8),
          armR=palm_hand("R", (0.18, -1.05, 0.51), palm=(-1, 0, 0), up=(0, -1, 0), space="world", grip=0.8))
    c.key(16, armL=end["armL"].but(pos=(0.30, -1.06, 0.036)), armR=end["armR"].but(pos=(-0.36, -1.00, 0.036)))
    c.key(24, armL=end["armL"], armR=end["armR"])
    # legs drive, trail, kick up on landing, settle
    c.key(2, legL=Plant(0.17, 0.02, out=10.0, roll=20.0), legR=Plant(-0.17, 0.16, out=10.0, roll=30.0))
    c.key(4, legL=Plant(0.17, 0.02, out=10.0, roll=64.0), legR=Plant(-0.17, 0.16, out=10.0, roll=66.0), ease="in")
    c.key(6.5, legL=L(-10.0, knee=6.0, ankle=-40.0), legR=L(-4.0, knee=14.0, out=8.0, ankle=-40.0))
    c.key(10, legL=L(-6.0, knee=10.0, out=6.0, ankle=-40.0), legR=L(-10.0, knee=6.0, out=10.0, ankle=-40.0))
    c.key(14, legL=L(-22.0, knee=58.0, out=10.0, ankle=-40.0), legR=L(-18.0, knee=40.0, out=14.0, ankle=-40.0), ease="out")
    c.key(19, legL=end["legL"], legR=end["legR"], ease="in")
    c.key(24, legL=end["legL"], legR=end["legR"])
    c.event("takeoff", 4)
    c.event("hit", 8)
    c.event("land", 12)
    c.key_frame = 8
    return c


# ---- 23 TackleWrap ----------------------------------------------------------------------------
def tackle_wrap(rig, made):
    c = Clip("TackleWrap", 20, ball="none", tier=2,
             notes="Lunge, wrap both arms at waist height (`hit`), drive the runner down; ends prone with the arms "
                   "still wrapped in front (DownFront with the arms forward). The pelvis ends 0.25 m ahead of the root.")
    end = poses.down_front()
    c.key(0, upright())
    c.key(3, hip=(0.0, -0.12, 0.74), pitch=46.0, bend=14.0, nod=-40.0, twist=8.0,
          armL=A(72.0, out=58.0, elbow=28.0, grip=0.0), armR=A(72.0, out=58.0, elbow=28.0, grip=0.0))
    c.key(6, hip=(0.03, -0.24, 0.70), pitch=54.0, bend=18.0, nod=-30.0, turn=-28.0, tilt=-12.0, twist=-10.0, ease="in")
    # Keep the palms on opposite sides of the runner's hips. The left hand
    # reaches a little farther around and the right pulls in first.
    c.key(6, armL=palm_hand("L", (0.20, -1.05, 0.87), palm=(-1, 0, 0), up=(0, -1, 0.15), space="world"),
          armR=palm_hand("R", (0.19, -0.98, 0.81), palm=(-1, 0, 0), up=(0, -1, 0.15), space="world"))
    # Absorb the collision in the hips before the second leg drives.
    c.key(7.25, hip=(0.05, -0.24, 0.65), pitch=55.0, bend=23.0, twist=-14.0, roll=3.0)
    c.key(9, hip=(0.04, -0.27, 0.74), pitch=62.0, bend=10.0, twist=-14.0, roll=6.0)
    c.key(13, hip=(0.02, -0.26, 0.42), pitch=84.0, bend=4.0, roll=10.0, twist=-8.0, ground=0.0)
    c.key(16, hx=0.0, hy=-0.25, hz=0.2, pitch=95.0, bend=-6.0, roll=0.0, twist=0.0, ground=1.0, nod=-20.0, turn=-40.0, tilt=0.0)
    c.key(20, hip=end["hip"], pitch=end["pitch"], bend=end["bend"], nod=end["nod"], turn=-50.0, ground=1.0)
    c.key(11, armL=A(96.0, out=-10.0, twist=55.0, elbow=70.0, grip=0.8), armR=A(92.0, out=-14.0, twist=55.0, elbow=76.0, grip=0.8))
    c.key(16, armL=ArmIK(pos=(0.20, -1.02, 0.07), pole=(1.0, 0.2, 0.2), pspace="world", palm=(-0.6, 0.0, -0.8),
                         fingers=(-0.8, -0.6, 0.0), grip=0.5),
          armR=ArmIK(pos=(-0.24, -0.98, 0.07), pole=(-1.0, 0.2, 0.2), pspace="world", palm=(0.6, 0.0, -0.8),
                     fingers=(0.8, -0.6, 0.0), grip=0.5))
    c.key(20, armL=ArmIK(pos=(0.20, -1.02, 0.05), pole=(1.0, 0.2, 0.2), pspace="world", palm=(-0.6, 0.0, -0.8),
                         fingers=(-0.8, -0.6, 0.0), grip=0.4),
          armR=ArmIK(pos=(-0.24, -0.98, 0.05), pole=(-1.0, 0.2, 0.2), pspace="world", palm=(0.6, 0.0, -0.8),
                     fingers=(0.8, -0.6, 0.0), grip=0.4))
    # legs: step with the left, drive off the right, knees go down, then both trail to the ground
    c.key(0, legL=Plant(0.17, -0.01, out=10.0), legR=Plant(-0.17, 0.02, out=10.0))
    c.key(3, legL=Plant(0.16, -0.30, out=8.0, arc=0.12), legR=Plant(-0.17, 0.02, out=10.0, roll=30.0))
    c.key(6, legL=Plant(0.16, -0.30, out=8.0), legR=Plant(-0.17, 0.02, out=10.0, roll=58.0))
    c.key(9, legR=Plant(-0.18, -0.20, out=8.0, roll=20.0, arc=0.10), legL=Plant(0.16, -0.30, out=8.0, roll=40.0))
    # Release the planted toes before the hips cross the feet. Leaving the
    # plant active into the fall makes the knee pole change sides in one frame.
    c.key(10, legL=Plant(0.16, -0.30, out=8.0, roll=55.0), legR=Plant(-0.18, -0.20, out=8.0, roll=44.0))
    c.key(12, legL=L(10.0, knee=67.0, out=8.0, ankle=-30.0), legR=L(4.0, knee=54.0, out=12.0, ankle=-30.0), ease="lin")
    c.key(16.5, legL=L(-14.0, knee=34.0, out=8.0, ankle=-40.0), legR=L(-10.0, knee=46.0, out=12.0, ankle=-40.0))
    c.key(20, legL=end["legL"], legR=end["legR"])
    c.event("hit", 6)
    c.key_frame = 6
    return c


# ---- 24 BigHit --------------------------------------------------------------------------------
def big_hit(rig, made):
    c = Clip("BigHit", 16, ball="none", tier=2,
             notes="Lower the right shoulder, explode up and through the target at `hit`, stay on the feet. The "
                   "body drives about 0.3 m forward of the root and ends in an athletic stance 0.2 m ahead of it.")
    c.key(0, upright())
    c.key(3, hip=(0.0, 0.08, 0.74), pitch=34.0, bend=24.0, twist=30.0, side=-6.0, nod=-30.0, tilt=14.0,
          armR=A(34.0, out=4.0, twist=85.0, elbow=118.0, grip=0.9), armL=A(-30.0, out=22.0, twist=20.0, elbow=95.0, grip=0.9))
    c.key(5, hip=(0.02, -0.26, 0.88), pitch=E(40.0, "in"), bend=E(6.0, "in"), twist=E(50.0, "in"), side=8.0,
          nod=-30.0, tilt=16.0, ease="in")
    c.key(5, armR=A(58.0, out=-6.0, twist=85.0, elbow=112.0, grip=0.9), armL=A(-52.0, out=30.0, twist=20.0, elbow=70.0, grip=0.9))
    # One compressed contact frame gives the shoulder weight before it rises.
    c.key(5.9, hip=(0.035, -0.265, 0.845), pitch=44.0, bend=10.0, twist=49.0, nod=-26.0)
    c.key(7, hip=(0.02, -0.34, 0.99), pitch=26.0, bend=-6.0, twist=44.0, side=6.0, nod=-18.0, tilt=8.0, ease="out")
    c.key(7, armR=A(74.0, out=4.0, twist=70.0, elbow=95.0, grip=0.9), armL=A(-40.0, out=34.0, twist=20.0, elbow=55.0, grip=0.9))
    c.key(10, hip=(0.0, -0.26, 0.86), pitch=16.0, bend=10.0, twist=14.0, side=0.0, nod=-10.0, tilt=0.0)
    c.key(16, upright(hip=(0.0, -0.20, 0.945)))
    c.key(0, legL=Plant(0.17, -0.01, out=10.0), legR=Plant(-0.17, 0.02, out=10.0))
    c.key(3, legL=Plant(0.19, -0.05, out=10.0, roll=6.0), legR=Plant(-0.19, 0.12, out=12.0, roll=24.0))
    c.key(5, legL=Plant(0.17, -0.34, out=6.0, roll=10.0, arc=0.07), legR=Plant(-0.19, 0.12, out=12.0, roll=62.0), ease="in")
    c.key(7, legL=Plant(0.17, -0.34, out=6.0, roll=50.0), legR=Plant(-0.19, 0.0, out=10.0, roll=66.0, z=0.05))
    c.key(10, legL=Plant(0.17, -0.34, out=6.0), legR=Plant(-0.18, -0.16, out=10.0, arc=0.05))
    c.key(16, legL=Plant(0.17, -0.22, out=10.0, arc=0.04), legR=Plant(-0.17, -0.18, out=10.0))
    c.event("hit", 5)
    c.key_frame = 5
    return c


# ---- 25 Shove ---------------------------------------------------------------------------------
def shove(rig, made):
    c = Clip("Shove", 14, ball="none", tier=2,
             notes="Violent two-hand shove at chest height: hands load at the chest, arms lock out at `hit` with a "
                   "step of the left foot.")
    start = poses.idle()
    c.key(0, start, gaze=1.0, nod=0.0)
    c.key(3, hip=(0.0, 0.06, 0.90), pitch=2.0, bend=2.0,
          armL=palm_hand("L", (0.13, -0.20, 1.37), up=(0.3, 0.0, 0.95), pole=(0.75, 0.55, -0.35)),
          armR=palm_hand("R", (0.13, -0.20, 1.37), up=(0.3, 0.0, 0.95), pole=(0.75, 0.55, -0.35)), ease="lin")
    c.key(5, hip=(0.0, -0.13, 0.89), pitch=E(24.0, "in"), bend=6.0, ease="in")
    c.key(5, armL=palm_hand("L", (0.14, -0.64, 1.43), up=(0.15, 0.0, 1.0), pole=(0.6, 0.2, -0.75)),
          armR=palm_hand("R", (0.14, -0.64, 1.43), up=(0.15, 0.0, 1.0), pole=(0.6, 0.2, -0.75)))
    c.key(7, hip=(0.0, -0.17, 0.885), pitch=28.0, bend=8.0, ease="out")
    c.key(7, armL=palm_hand("L", (0.15, -0.65, 1.44), up=(0.15, 0.0, 1.0), pole=(0.6, 0.2, -0.75)),
          armR=palm_hand("R", (0.15, -0.65, 1.44), up=(0.15, 0.0, 1.0), pole=(0.6, 0.2, -0.75)))
    c.key(14, start, hip=(0.0, -0.10, 0.945), gaze=1.0, nod=0.0)
    c.key(2, legL=Plant(0.17, -0.01, out=10.0), legR=Plant(-0.17, 0.02, out=10.0))
    c.key(5, legL=Plant(0.16, -0.30, out=8.0, arc=0.06), legR=Plant(-0.17, 0.02, out=10.0, roll=40.0), ease="in")
    c.key(8, legL=Plant(0.16, -0.30, out=8.0), legR=Plant(-0.17, 0.02, out=10.0, roll=46.0))
    c.key(14, legL=Plant(0.17, -0.28, out=10.0), legR=Plant(-0.17, -0.10, out=10.0, arc=0.05))
    c.event("hit", 5)
    c.key_frame = 5
    return c


# ---- 26 HitBack -------------------------------------------------------------------------------
def hit_back(rig, made):
    c = Clip("HitBack", 22, ball="none", tier=2,
             notes="Blasted from the front: chest caves, lifted off the feet, lands flat on the back and bounces "
                   "into the DownBack pose (pelvis 0.25 m behind the root). Airborne frames 3-11.")
    end = poses.down_back()
    c.key(0, upright())
    # The pads take the blow first. The hips lag, then the feet leave the turf.
    c.key(1, hip=(-0.02, 0.025, 0.88), pitch=-4.0, bend=26.0, nod=21.0, twist=-10.0, roll=5.0, ease="out")
    c.key(2.75, hx=-0.025, hy=0.09, hz=0.98, pitch=-18.0, bend=31.0, nod=30.0, twist=-14.0, roll=8.0)
    c.key(8, twist=-5.0, roll=6.0)
    c.key(13, twist=3.0, roll=-3.0)
    c.key(18, twist=0.0, roll=0.0)
    c.key(5.5, hz=E(1.14, "out"), hy=0.17, pitch=-52.0, bend=22.0, nod=10.0)
    c.key(9, pitch=-86.0, bend=6.0, nod=-16.0, hy=0.23)
    c.key(11.5, hz=E(0.19, "in"), hy=0.25, pitch=-100.0, bend=-4.0, nod=-10.0, ground=0.0)
    c.key(12.5, ground=1.0, pitch=-98.0)
    c.key(15, pitch=-84.0, bend=8.0, nod=20.0)
    c.key(18, pitch=-90.0, bend=-3.0, nod=6.0)
    c.key(22, hip=end["hip"], pitch=end["pitch"], bend=end["bend"], nod=end["nod"], turn=end["turn"], ground=1.0)
    c.key(12, turn=0.0)
    # arms are thrown forward by the hit, trail upward in flight, slam down
    fling = A(78.0, out=22.0, twist=10.0, elbow=22.0, grip=0.2)
    c.key(2, armL=fling, armR=fling.but(fwd=70.0), ease="out")
    c.key(7, armL=A(118.0, out=34.0, elbow=30.0, grip=0.1), armR=A(108.0, out=38.0, elbow=36.0, grip=0.1))
    c.key(11.5, armL=A(100.0, out=52.0, elbow=40.0, grip=0.1), armR=A(94.0, out=58.0, elbow=44.0, grip=0.1))
    c.key(14, armL=end["armL"].but(pos=(0.60, 0.62, 0.035)), armR=end["armR"].but(pos=(-0.56, 0.52, 0.035)), ease="in")
    c.key(22, armL=end["armL"], armR=end["armR"])
    # legs are swept out and fly up, fold over on landing, then drop
    c.key(2, legL=Plant(0.17, -0.01, out=10.0, roll=-20.0), legR=Plant(-0.17, 0.02, out=10.0, roll=-16.0))
    c.key(5.5, legL=L(48.0, knee=30.0, out=8.0, ankle=10.0), legR=L(34.0, knee=46.0, out=10.0, ankle=10.0))
    c.key(9, legL=L(66.0, knee=22.0, out=12.0), legR=L(54.0, knee=40.0, out=14.0))
    c.key(12.5, legL=L(92.0, knee=30.0, out=14.0), legR=L(78.0, knee=52.0, out=16.0))
    c.key(16.5, legL=end["legL"].but(pos=(0.21, -0.57, 0.16)), legR=end["legR"].but(pos=(-0.25, -0.44, 0.20)), ease="in")
    c.key(19, legL=end["legL"], legR=end["legR"], ease="in")
    c.key(22, legL=end["legL"], legR=end["legR"])
    c.event("land", 12)
    c.key_frame = 7
    return c


# ---- 27 HitFront ------------------------------------------------------------------------------
def hit_front(rig, made):
    c = Clip("HitFront", 20, ball="none", tier=2,
             notes="Hit from behind: back arches, thrown forward off the feet, face-plants with the legs kicking "
                   "up, settles into the DownFront pose (pelvis 0.25 m in front of the root). Airborne frames 3-9.")
    end = poses.down_front()
    c.key(0, upright())
    c.key(2, hx=0.0, hy=-0.07, hz=0.97, pitch=14.0, bend=-32.0, nod=-36.0, ease="out")
    c.key(5, hz=E(1.0, "out"), hy=-0.16, pitch=58.0, bend=-14.0, nod=-30.0)
    c.key(9, hz=E(0.34, "in"), hy=-0.24, pitch=104.0, bend=8.0, nod=-6.0, ground=0.0)
    c.key(10, ground=1.0)
    c.key(12, pitch=99.0, bend=-10.0, nod=-26.0)
    c.key(16, pitch=96.0, bend=-10.0, nod=-16.0)
    c.key(20, hip=end["hip"], pitch=end["pitch"], bend=end["bend"], nod=end["nod"], turn=end["turn"], ground=1.0)
    c.key(11, turn=0.0)
    back = A(-58.0, out=36.0, twist=0.0, elbow=24.0, grip=0.1)
    c.key(2.5, armL=back, armR=back.but(fwd=-50.0), ease="lin")
    c.key(6, armL=A(40.0, out=44.0, elbow=40.0, grip=0.0), armR=A(30.0, out=48.0, elbow=44.0, grip=0.0))
    c.key(9, armL=A(118.0, out=38.0, elbow=70.0, grip=0.0), armR=A(104.0, out=44.0, elbow=76.0, grip=0.0))
    c.key(12.5, armL=end["armL"].but(pos=(0.40, -0.98, 0.036)), armR=end["armR"].but(pos=(-0.46, -0.84, 0.036)))
    c.key(20, armL=end["armL"], armR=end["armR"])
    c.key(2, legL=Plant(0.17, -0.01, out=10.0, roll=40.0), legR=Plant(-0.17, 0.02, out=10.0, roll=50.0))
    c.key(5, legL=L(-26.0, knee=18.0, out=8.0, ankle=-35.0), legR=L(-14.0, knee=40.0, out=10.0, ankle=-35.0))
    c.key(9, legL=L(-22.0, knee=62.0, out=10.0, ankle=-40.0), legR=L(-30.0, knee=40.0, out=12.0, ankle=-40.0))
    c.key(12, legL=L(-30.0, knee=100.0, out=12.0, ankle=-40.0), legR=L(-34.0, knee=78.0, out=16.0, ankle=-40.0))
    c.key(16.5, legL=end["legL"].but(pos=(0.17, 0.58, 0.20)), legR=end["legR"].but(pos=(-0.32, 0.42, 0.16)), ease="in")
    c.key(19, legL=end["legL"], legR=end["legR"], ease="in")
    c.key(20, legL=end["legL"], legR=end["legR"])
    c.event("land", 9)
    c.key_frame = 6
    return c


# ---- 28 HitFlip -------------------------------------------------------------------------------
def hit_flip(rig, made):
    c = Clip("HitFlip", 28, ball="none", tier=2,
             notes="The signature huge hit: legs cut out from under him, the body turns a forward flip in the air "
                   "(pitch runs from 0 through upside-down to 270 deg, pelvis peaks 1.5 m up at frame 11) and "
                   "crashes onto the back, bouncing into the DownBack pose. Airborne frames 3-19.")
    end = poses.down_back()
    c.key(0, upright())
    # rotation: steady in the air, a hard stop on the ground with a little rebound
    c.key(0, pitch=8.0)
    c.key(3, pitch=E(40.0, "in"))
    c.key(19, pitch=E(262.0, "lin"))
    c.key(21, pitch=E(276.0, "out"))
    c.key(24, pitch=268.0)
    c.key(28, pitch=271.0)
    c.key(0, hx=0.0, hy=0.0, hz=0.945)
    c.key(3, hz=0.88, hy=-0.02)
    c.key(11, hz=E(1.50, "out"), hy=0.10)
    c.key(19, hz=E(0.22, "in"), hy=0.25, ground=0.0)
    c.key(20, ground=1.0)
    c.key(28, hy=0.25, hz=end["hip"][2], ground=1.0)
    c.key(3, bend=20.0, nod=20.0)
    c.key(8, bend=34.0, nod=30.0)             # tucking for the turn
    c.key(14, bend=10.0, nod=0.0)
    c.key(19, bend=-10.0, nod=-20.0)          # opening up before the crash
    c.key(21, bend=10.0, nod=24.0)            # head whips forward on impact
    c.key(28, bend=end["bend"], nod=end["nod"], turn=end["turn"])
    c.key(21, turn=0.0)
    # arms: flail up as the legs go, pull in for the tuck, spread for the landing
    c.key(3, armL=A(60.0, out=40.0, elbow=30.0, grip=0.1), armR=A(40.0, out=44.0, elbow=30.0, grip=0.1), ease="out")
    c.key(8, armL=A(70.0, out=18.0, twist=40.0, elbow=80.0, grip=0.4), armR=A(60.0, out=20.0, twist=40.0, elbow=84.0, grip=0.4))
    c.key(15, armL=A(110.0, out=64.0, elbow=24.0, grip=0.0), armR=A(100.0, out=68.0, elbow=28.0, grip=0.0))
    c.key(19, armL=A(96.0, out=70.0, elbow=20.0, grip=0.0), armR=A(92.0, out=72.0, elbow=24.0, grip=0.0))
    c.key(22, armL=end["armL"].but(pos=(0.62, 0.60, 0.035)), armR=end["armR"].but(pos=(-0.58, 0.50, 0.035)), ease="in")
    c.key(28, armL=end["armL"], armR=end["armR"])
    # legs: swept back and up, tucked through the turn, split wide, slam down after the back
    c.key(0, legL=Plant(0.17, -0.01, out=10.0), legR=Plant(-0.17, 0.02, out=10.0))
    c.key(3, legL=L(-34.0, knee=30.0, out=8.0, ankle=-30.0), legR=L(-20.0, knee=56.0, out=10.0, ankle=-30.0), ease="in")
    c.key(8, legL=L(70.0, knee=104.0, out=10.0), legR=L(54.0, knee=96.0, out=14.0))
    c.key(14, legL=L(50.0, knee=40.0, out=24.0), legR=L(20.0, knee=60.0, out=28.0))
    c.key(19, legL=L(62.0, knee=22.0, out=26.0), legR=L(36.0, knee=44.0, out=28.0))
    c.key(21, legL=L(84.0, knee=30.0, out=20.0), legR=L(66.0, knee=54.0, out=22.0))
    c.key(24.5, legL=end["legL"].but(pos=(0.21, -0.57, 0.18)), legR=end["legR"].but(pos=(-0.25, -0.44, 0.22)), ease="in")
    c.key(26.5, legL=end["legL"], legR=end["legR"], ease="in")
    c.key(28, legL=end["legL"], legR=end["legR"])
    c.event("land", 19)
    c.key_frame = 10
    return c


# ---- 29 GetUpBack -----------------------------------------------------------------------------
def get_up_back(rig, made):
    c = Clip("GetUpBack", 26, ball="none", tier=2,
             notes="From DownBack to Idle: knees tuck and the body rocks back, rocks forward onto the heels with a "
                   "push of both hands, rises out of a deep squat. The feet plant where Idle has them (frame 10) "
                   "and stay there; the pelvis travels from 0.25 m behind the root to over it.")
    start, end = poses.down_back(), poses.idle()
    feet = dict(legL=end["legL"], legR=end["legR"])
    c.key(0, start)
    c.key(4, pitch=-104.0, bend=22.0, nod=22.0, turn=0.0, ground=1.0, ease="out")
    c.key(8, hx=0.0, hy=0.25, hz=0.16, pitch=-50.0, bend=34.0, nod=14.0, ground=1.0, ease="in")
    c.key(10, hy=0.24, hz=0.22, pitch=-4.0, bend=30.0, nod=-10.0, ground=0.0)
    c.key(12.5, hy=0.19, hz=0.40, pitch=48.0, bend=14.0, nod=-34.0)
    c.key(18, hy=0.06, hz=0.80, pitch=24.0, bend=10.0, nod=-18.0)
    c.key(23, hip=E(end["hip"], "out"), pitch=end["pitch"], bend=end["bend"], nod=end["nod"])
    c.key(26, hip=end["hip"], pitch=end["pitch"], bend=end["bend"], nod=end["nod"])
    # legs: tuck to the chest, heels down close to the seat, then just stand up
    c.key(4, legL=L(112.0, knee=118.0, out=8.0), legR=L(104.0, knee=112.0, out=10.0), ease="out")
    c.key(7, legL=L(98.0, knee=124.0, out=10.0), legR=L(94.0, knee=120.0, out=12.0))
    c.key(9, legL=LegIK(pos=(0.17, -0.01, 0.17), ankle=4.0), legR=LegIK(pos=(-0.17, 0.02, 0.17), ankle=4.0))
    c.key(10, legL=end["legL"].but(roll=-6.0), legR=end["legR"].but(roll=-6.0))
    c.key(12.5, feet)
    c.key(26, feet)
    # arms: thrown forward for the rock-up, hands shove off the ground, then hang
    c.key(4, armL=A(70.0, out=18.0, elbow=30.0, grip=0.3), armR=A(70.0, out=18.0, elbow=30.0, grip=0.3), ease="out")

    def push(s):
        return ArmIK(pos=(0.29 * s, 0.47, 0.032), pole=(0.5 * s, 1.0, 0.4), pspace="world", palm=(0.0, 0.0, -1.0),
                     fingers=(0.35 * s, -0.94, 0.0), grip=0.05, thumb=0.1)

    c.key(7.2, armL=push(1.0), armR=push(-1.0))
    c.key(8.5, armL=push(1.0), armR=push(-1.0))
    c.key(12, armL=A(72.0, out=14.0, twist=20.0, elbow=26.0, grip=0.3), armR=A(72.0, out=14.0, twist=20.0, elbow=26.0, grip=0.3),
          ease="out")
    c.key(20, armL=A(18.0, out=12.0, twist=30.0, elbow=36.0, grip=0.4), armR=A(18.0, out=12.0, twist=30.0, elbow=36.0, grip=0.4))
    c.key(26, armL=end["armL"], armR=end["armR"])
    c.key_frame = 11
    return c


# ---- 30 GetUpFront ----------------------------------------------------------------------------
def get_up_front(rig, made):
    c = Clip("GetUpFront", 24, ball="none", tier=2,
             notes="From DownFront to Idle: hands plant, push-up, the right foot steps under the body, then the "
                   "left, and he stands. Both feet finish where Idle has them; the pelvis travels from 0.25 m in "
                   "front of the root to over it.")
    start, end = poses.down_front(), poses.idle()
    c.key(0, start)
    c.key(4, pitch=94.0, bend=-10.0, nod=-36.0, turn=0.0, ground=1.0)
    c.key(8, hx=0.0, hy=-0.22, hz=0.25, pitch=74.0, bend=-10.0, nod=-40.0, ground=0.0)
    c.key(11, hy=-0.11, hz=0.52, pitch=64.0, bend=6.0, nod=-36.0)
    c.key(14.5, hy=-0.03, hz=0.62, pitch=44.0, bend=12.0, nod=-30.0)
    c.key(19.5, hy=0.0, hz=0.90, pitch=14.0, bend=8.0, nod=-14.0)
    c.key(24, hip=end["hip"], pitch=end["pitch"], bend=end["bend"], nod=end["nod"])

    def plant(s):
        return ArmIK(pos=(0.28 * s, -0.61, 0.032), pole=(0.7 * s, 0.4, 0.6), pspace="world", palm=(0.0, 0.0, -1.0),
                     fingers=(-0.2 * s, -0.98, 0.0), grip=0.05, thumb=0.1)

    c.key(4, armL=plant(1.0), armR=plant(-1.0), ease="out")
    c.key(8.5, armL=plant(1.0), armR=plant(-1.0))
    c.key(12.5, armL=A(48.0, out=16.0, twist=20.0, elbow=40.0, grip=0.3), armR=A(60.0, out=14.0, twist=20.0, elbow=34.0, grip=0.3))
    c.key(19, armL=A(16.0, out=12.0, twist=30.0, elbow=38.0, grip=0.4), armR=A(16.0, out=12.0, twist=30.0, elbow=38.0, grip=0.4))
    c.key(24, armL=end["armL"], armR=end["armR"])
    # legs: toes dig in, right foot steps through first, left follows
    c.key(3, legL=start["legL"], legR=start["legR"])
    c.key(5.2, legL=start["legL"].but(pos=(0.17, 0.60, 0.27), ankle=-24.0), legR=start["legR"].but(pos=(-0.24, 0.52, 0.27), ankle=-24.0))
    c.key(7.2, legL=Plant(0.17, 0.66, out=6.0, roll=74.0), legR=Plant(-0.19, 0.60, out=6.0, roll=74.0))
    c.key(8, legR=Plant(-0.19, 0.60, out=6.0, roll=74.0))
    c.key(12, legR=end["legR"].but(arc=0.10, roll=-8.0))
    c.key(13.5, legR=end["legR"], legL=Plant(0.17, 0.66, out=6.0, roll=70.0))
    c.key(17.5, legL=end["legL"].but(arc=0.09, roll=-6.0))
    c.key(19, legL=end["legL"])
    c.key(24, legL=end["legL"], legR=end["legR"])
    c.key_frame = 11
    return c


# ---- ball-carrier moves (built on the RunBall cycle) --------------------------------------------
from .clips_loco import RUN, RUN_BALL  # noqa: E402
from .controls import Mix  # noqa: E402
from .gait import Gait, smooth, track  # noqa: E402

LOW_SWING = Gait(frames=16, speed=8.0, twist=11.0, yaw=9.0,
                 swing=[(0.14, -0.60, 0.26), (0.32, -0.32, 0.40), (0.52, -0.04, 0.30), (0.72, 0.22, 0.26), (0.90, 0.42, 0.22)])


def stumble(rig, made):
    c = Clip("Stumble", 16, ball="tuck", tier=2,
             notes="Staggered by a hit but stays up: pitches forward and drops, the free arm flails for the ground, "
                   "then he recovers. Built on one RunBall cycle, so it starts and ends on RunBall frame 0 (left "
                   "foot contact) and keeps its foot timing (authored for 8 m/s). Reads fine without a ball too.")
    flail = ArmFK(fwd=84.0, out=36.0, twist=10.0, elbow=16.0, pron=60.0, grip=0.05, thumb=0.0)

    def source(t):
        k = RUN_BALL.controls(rig, t)
        low = LOW_SWING.controls(rig, t)
        gone = track([(0, 0.0), (3, 1.0), (7, 0.9), (12, 0.35), (16, 0.0)], t)
        wobble = track([(0, 0.0), (3, 1.0), (8, -0.7), (13, 0.25), (16, 0.0)], t)
        x, y, z = k["hip"]
        k["hip"] = (x + 0.05 * wobble, y - 0.07 * gone, z - 0.13 * gone)
        k["pitch"] += 36.0 * gone
        k["bend"] += 16.0 * gone
        k["roll"] += 10.0 * wobble
        k["yaw"] += 8.0 * wobble
        k["gaze"] = 1.0 - 0.55 * gone
        k["nod"] = -8.0 * gone
        k["armL"] = Mix(k["armL"], flail, track([(0, 0.0), (3, 0.9), (7, 1.0), (12, 0.2), (16, 0.0)], t))
        for leg in ("legL", "legR"):
            k[leg] = Mix(k[leg], low[leg], min(1.0, gone * 1.2))
        return k

    c.source = source
    c.velocity = (0.0, -8.0)
    c.key_frame = 5
    return c


def stiff_arm(rig, made):
    c = Clip("StiffArm", 16, ball="tuck", tier=2,
             notes="Runner drives the LEFT arm out straight into a tackler; the ball stays tucked right. Built on "
                   "one RunBall cycle (16 frames instead of 14, so the legs are exactly RunBall's and the clip "
                   "starts and ends on RunBall frame 0): use it whole or as an upper-body layer over RunBall.")
    cocked = palm_hand("L", (0.22, -0.24, 1.43), palm=(-0.55, -0.83, 0.1), up=(-0.1, -0.3, 0.95), pole=(0.8, 0.5, -0.4), grip=0.3)
    out = palm_hand("L", (0.33, -0.60, 1.47), palm=(0.15, -0.98, 0.1), up=(-0.1, 0.0, 1.0), pole=(0.75, 0.2, -0.65), grip=0.0)
    lock = out.but(pos=(0.34, -0.63, 1.49))

    def source(t):
        k = RUN_BALL.controls(rig, t)
        w = track([(0, 0.0), (3, 0.7), (5, 1.0), (9, 1.0), (13, 0.3), (16, 0.0)], t)
        pump = k["armL"]
        if t <= 3.0:
            k["armL"] = Mix(pump, cocked, t / 3.0)
        elif t <= 5.0:
            u = (t - 3.0) / 2.0
            k["armL"] = Mix(cocked, out, u * u)
        elif t <= 9.0:
            k["armL"] = Mix(out, lock, smooth((t - 5.0) / 2.0) if t < 7.0 else 1.0 - 0.5 * smooth((t - 7.0) / 2.0))
        else:
            k["armL"] = Mix(out, pump, smooth((t - 9.0) / 7.0))
        k["twist"] = k["twist"] * (1.0 - 0.75 * w) - 18.0 * w
        k["side"] += 5.0 * w
        k["roll"] += 3.0 * w
        k["turn"] = 14.0 * w
        return k

    c.source = source
    c.velocity = (0.0, -8.0)
    c.event("hit", 5)
    c.key_frame = 5
    return c


def _gait_pose(rig, frame=0.0, gait=RUN_BALL):
    return gait.controls(rig, frame)


def spin(rig, made):
    c = Clip("Spin", 16, ball="tuck", tier=2,
             notes="Full 360 deg spin to the left (counter-clockwise seen from above) done through the pelvis; the "
                   "root does not turn. Pivots on the left foot (frames 0-5) then the right (6-12). Starts and ends "
                   "on RunBall frame 0. Planted feet drift back at roughly 3 m/s.")
    g0 = _gait_pose(rig)
    c.key(0, g0)
    c.key(16, g0)
    c.key(0, yaw=g0["yaw"])
    c.key(3, yaw=E(g0["yaw"] + 36.0, "in"))
    c.key(13, yaw=E(g0["yaw"] + 335.0, "lin"))
    c.key(16, yaw=E(g0["yaw"] + 360.0, "out"))
    hx, hy, hz = g0["hip"]
    c.key(4, hip=(0.04, hy, 0.83), pitch=16.0, bend=16.0, roll=9.0, twist=22.0, side=-4.0)
    c.key(8, hip=(0.0, hy + 0.02, 0.82), pitch=14.0, bend=18.0, roll=0.0, twist=8.0, side=0.0)
    c.key(12, hip=(-0.03, hy, 0.85), pitch=16.0, bend=14.0, roll=-8.0, twist=-14.0, side=4.0)
    c.key(0, gaze=1.0, turn=0.0)
    c.key(2, gaze=0.0, turn=40.0, nod=4.0)             # the head leads the turn
    c.key(13, gaze=0.0, turn=30.0, nod=4.0)
    c.key(16, gaze=1.0, turn=0.0, nod=g0["nod"])
    # free arm: whipped in tight for the turn, out again for the first stride
    c.key(2, armL=A(18.0, out=42.0, twist=30.0, elbow=76.0, grip=0.6))
    c.key(5, armL=A(30.0, out=6.0, twist=80.0, elbow=118.0, grip=0.8))
    c.key(12, armL=A(24.0, out=10.0, twist=70.0, elbow=110.0, grip=0.8))
    # feet: pivot on the left, step round onto the right, pivot, then drive out
    c.key(2, legL=Plant(0.075, -0.07, yaw=30.0, out=5.0, roll=24.0))
    c.key(5, legL=Plant(0.07, 0.20, yaw=103.0, out=5.0, roll=36.0))
    c.key(7.5, legL=LegIK(pos=(0.12, -0.16, 0.50), space="pelvis", ankle=-20.0))
    c.key(11, legL=LegIK(pos=(0.13, -0.20, 0.46), space="pelvis", ankle=-10.0))
    c.key(14, legL=LegIK(pos=(0.10, -0.40, 0.42), space="pelvis", ankle=4.0))
    c.key(3, legR=LegIK(pos=(-0.13, -0.14, 0.48), space="pelvis", ankle=-20.0))
    c.key(6, legR=Plant(-0.06, -0.16, yaw=158.0, out=5.0, roll=20.0))
    c.key(9, legR=Plant(-0.07, 0.10, yaw=232.0, out=5.0, roll=30.0))
    c.key(12, legR=Plant(-0.085, 0.36, yaw=330.0, out=5.0, roll=58.0))
    c.key_frame = 8
    return c


def _juke_left(rig):
    """Controls of the cut to the LEFT as a function of time (the plant foot is the right)."""
    c = Clip("_juke", 12, ball="tuck")
    g0 = _gait_pose(rig)
    hx, hy, hz = g0["hip"]
    c.key(0, g0)
    c.key(12, g0)
    c.key(2, hip=(-0.03, hy, 0.86), roll=-4.0, yaw=-6.0, twist=-16.0, pitch=14.0)        # sell the fake to the right
    c.key(5, hip=(-0.06, hy + 0.02, 0.79), roll=17.0, yaw=6.0, twist=2.0, pitch=18.0, bend=16.0, side=-6.0)
    c.key(8, hip=(0.11, hy - 0.03, 0.87), roll=13.0, yaw=16.0, twist=10.0, pitch=17.0, bend=12.0, side=-3.0)
    c.key(0, gaze=1.0, turn=0.0)
    c.key(2, turn=-26.0)
    c.key(6, turn=24.0)
    c.key(12, turn=0.0)
    # free arm flares for balance over the plant, then drives
    c.key(2, armL=A(-20.0, out=24.0, twist=20.0, elbow=80.0, grip=0.7))
    c.key(5, armL=A(10.0, out=58.0, twist=0.0, elbow=44.0, grip=0.4))
    c.key(8.5, armL=A(40.0, out=26.0, twist=30.0, elbow=95.0, grip=0.7))
    # left foot: short stance, then swings through low to its next contact
    c.key(1, legL=Plant(0.085, -0.13, out=5.0, roll=0.0))
    c.key(3, legL=Plant(0.085, 0.15, out=5.0, roll=52.0))
    c.key(4.3, legL=LegIK(pos=(0.09, 0.27, 0.31), pitch=-78.0))
    c.key(6, legL=LegIK(pos=(0.16, 0.10, 0.46), space="pelvis", ankle=-24.0))
    c.key(9.5, legL=LegIK(pos=(0.12, -0.44, 0.42), space="pelvis", ankle=2.0))
    # right foot: slams down wide, loads, explodes
    c.key(2, legR=LegIK(pos=(-0.20, -0.30, 0.40), space="pelvis", ankle=0.0))
    c.key(3.6, legR=Plant(-0.36, -0.16, yaw=14.0, out=0.0, roll=-10.0))
    c.key(5, legR=Plant(-0.36, -0.14, yaw=14.0, out=0.0, roll=0.0))
    c.key(8, legR=Plant(-0.36, -0.02, yaw=14.0, out=0.0, roll=58.0))
    return c


def juke_l(rig, made):
    src = _juke_left(rig)
    c = Clip("JukeL", 12, ball="tuck", tier=2,
             notes="Hard plant on the right foot (frames 4-8, 0.36 m out to the right) and cut to the LEFT. Starts "
                   "and ends on RunBall frame 0 (left foot contact).")
    c.source = src.controls
    c.event("plant", 4)
    c.key_frame = 6
    return c


def juke_r(rig, made):
    src = _juke_left(rig)
    g8 = _gait_pose(rig, 8.0)
    free = Clip("_juke_arm", 12)                               # the free arm is still the left one
    free.key(0, armL=g8["armL"])
    free.key(5, armL=A(-26.0, out=52.0, twist=0.0, elbow=48.0, grip=0.4))
    free.key(9, armL=A(6.0, out=28.0, twist=24.0, elbow=84.0, grip=0.7))
    free.key(12, armL=g8["armL"])

    def source(t):
        m = mirror_controls(src.controls(t))
        m["armL"] = free.controls(t)["armL"]
        m["armR"] = g8["armR"]                                 # and the ball stays in the right
        return m

    c = Clip("JukeR", 12, ball="tuck", tier=2,
             notes="Mirror of JukeL: hard plant on the left foot and cut to the RIGHT; the ball stays in the right "
                   "arm. Starts and ends on RunBall frame 8 (right foot contact).")
    c.source = source
    c.event("plant", 4)
    c.key_frame = 6
    return c


def hurdle(rig, made):
    c = Clip("Hurdle", 20, ball="tuck", tier=2,
             notes="Leap over a low tackler with both knees tucked: takes off from the left foot at frame 3, the "
                   "pelvis peaks 0.7 m up at frame 9, lands on the right foot at frame 15 and runs out. Starts and "
                   "ends on RunBall frame 0.")
    g0 = _gait_pose(rig)
    hx, hy, hz = g0["hip"]
    c.key(0, g0)
    c.key(20, g0)
    c.key(0, hz=hz)
    c.key(3, hz=0.99)
    c.key(9, hz=E(1.645, "out"))
    c.key(15, hz=E(0.95, "in"))
    c.key(17, hz=E(0.86, "out"))
    c.key(20, hz=hz)
    c.key(3, pitch=6.0, bend=4.0, yaw=0.0, twist=-10.0, roll=0.0, side=0.0, hx=0.0)
    c.key(9, pitch=16.0, bend=20.0, yaw=0.0, twist=6.0)
    c.key(15, pitch=12.0, bend=10.0, yaw=0.0, twist=0.0)
    c.key(17, pitch=20.0, bend=16.0)
    c.key(3, armL=A(60.0, out=26.0, twist=20.0, elbow=70.0, grip=0.6))
    c.key(9, armL=A(52.0, out=62.0, twist=0.0, elbow=38.0, grip=0.3))
    c.key(15, armL=A(-20.0, out=34.0, twist=20.0, elbow=70.0, grip=0.6))
    # left leg: drives off the ground, tucks under and out, trails in for the next stride
    c.key(1.5, legL=Plant(0.085, 0.0, out=5.0, roll=6.0))
    c.key(3, legL=Plant(0.085, 0.27, out=5.0, roll=62.0))
    c.key(6, legL=L(-20.0, knee=96.0, out=10.0, ankle=-30.0))
    c.key(9, legL=L(46.0, knee=136.0, out=24.0, twist=14.0, ankle=-10.0))
    c.key(13, legL=L(10.0, knee=110.0, out=14.0, ankle=-20.0))
    c.key(17, legL=LegIK(pos=(0.09, 0.08, 0.36), pitch=-44.0))
    c.key(19, legL=LegIK(pos=(0.085, -0.47, 0.25), pitch=14.0))
    # right leg: knee drives up, stays high over the top, reaches down to land
    c.key(3, legR=L(84.0, knee=100.0, out=4.0, ankle=0.0))
    c.key(9, legR=L(104.0, knee=118.0, out=8.0, ankle=6.0))
    c.key(13, legR=L(56.0, knee=40.0, out=4.0, ankle=6.0))
    c.key(15, legR=Plant(-0.085, -0.21, out=5.0, roll=-8.0))
    c.key(16.5, legR=Plant(-0.085, 0.0, out=5.0, roll=4.0))
    c.key(18, legR=Plant(-0.085, 0.26, out=5.0, roll=58.0))
    c.event("takeoff", 3)
    c.event("apex", 9)
    c.event("land", 15)
    c.key_frame = 9
    return c


# ---- 36 DiveBall ------------------------------------------------------------------------------
def dive_ball(rig, made):
    c = Clip("DiveBall", 22, ball="hand", tier=2,
             notes="Ball carrier dives headfirst with the ball stretched out in front in both hands, lands and "
                   "ends prone holding it out (DownFront with the arms forward; the ball lies about 1.35 m in "
                   "front of the root). Starts on RunBall frame 0 with ball_hand_r sitting on ball_tuck_r, so "
                   "coming from a tuck clip does not pop. Airborne frames 4-12.")
    g0 = _gait_pose(rig)
    end = poses.down_front()
    c.key(0, g0)
    c.key(0, hand2tuck=1.0, ground=0.0, gaze=1.0)
    c.key(4, hand2tuck=0.0, gaze=0.0)
    hx, hy, hz = g0["hip"]
    c.key(2, hip=(0.0, 0.02, 0.80), pitch=38.0, bend=14.0, yaw=0.0, twist=0.0, roll=0.0, side=0.0)
    c.key(4, hx=0.0, hy=-0.04, hz=0.86, pitch=64.0, bend=2.0, nod=-40.0)
    c.key(6.5, hz=E(0.93, "out"), hy=-0.13, pitch=E(86.0, "out"), bend=-8.0, nod=-38.0)
    c.key(12, hz=E(0.21, "in"), hy=-0.25, pitch=94.0, bend=-8.0, nod=-30.0)
    c.key(13, ground=1.0)
    c.key(15, bend=-14.0, nod=-36.0)
    c.key(22, hip=(0.0, -0.25, end["hip"][2]), pitch=end["pitch"], bend=end["bend"], nod=-24.0, turn=0.0, ground=1.0)
    # the ball goes from the tuck out to full stretch; both hands on it
    out_r = poses.hold((-0.06, -0.10, 2.085), axis=(0.0, 0.0, -1.0), palm=(0.92, 0.38, 0.0), space="chest",
                       pole=(-0.9, 0.3, -0.2))
    out_l = poses.cup(pole=(0.9, 0.3, -0.2))
    c.key(2, armR=poses.tuck())
    c.key(3, armL=A(96.0, out=24.0, twist=30.0, elbow=70.0, grip=0.2))
    c.key(6, armR=out_r, armL=out_l)
    c.key(11, armR=out_r, armL=out_l)
    down_r = poses.hold((-0.06, -1.35, 0.112), axis=(0.0, 1.0, 0.0), palm=(0.85, 0.0, -0.5), space="world",
                        pole=(-1.0, 0.3, 0.25), pspace="world")
    c.key(13.5, armR=down_r, armL=poses.cup(pole=(1.0, 0.3, 0.25), pspace="world"))
    c.key(22, armR=down_r, armL=poses.cup(pole=(1.0, 0.3, 0.25), pspace="world"))
    # legs: drive off the left, trail, kick up on landing, settle
    c.key(2, legL=Plant(0.085, -0.02, out=5.0, roll=10.0))
    c.key(4, legL=Plant(0.085, 0.22, out=5.0, roll=64.0), ease="in")
    c.key(6.5, legL=L(-10.0, knee=6.0, ankle=-40.0), legR=L(-2.0, knee=18.0, out=8.0, ankle=-40.0))
    c.key(10, legL=L(-6.0, knee=10.0, out=6.0, ankle=-40.0), legR=L(-10.0, knee=6.0, out=10.0, ankle=-40.0))
    c.key(14, legL=L(-20.0, knee=52.0, out=10.0, ankle=-40.0), legR=L(-16.0, knee=36.0, out=14.0, ankle=-40.0), ease="out")
    down_right = end["legR"].but(pos=(-0.32, 0.42, 0.088))
    c.key(19, legL=end["legL"], legR=down_right, ease="in")
    c.key(22, legL=end["legL"], legR=down_right)
    c.event("takeoff", 4)
    c.event("land", 12)
    c.key_frame = 8
    return c


# ---- 37 Kick ----------------------------------------------------------------------------------
def kick(rig, made):
    c = Clip("Kick", 30, ball="none", tier=2, notes="")
    start = poses.idle()
    c.key(0, start, hip=(0.0, 0.30, 0.945), gaze=1.0, nod=14.0)
    c.key(0, legL=Plant(0.15, 0.30, out=10.0), legR=Plant(-0.15, 0.32, out=10.0))
    # approach: right step, then the left foot plants beside the ball
    c.key(2, legR=Plant(-0.15, 0.32, out=10.0, roll=30.0))
    c.key(7, legR=Plant(-0.11, 0.10, out=6.0, roll=-10.0, arc=0.07))
    c.key(8, legR=Plant(-0.11, 0.10, out=6.0), legL=Plant(0.15, 0.30, out=10.0, roll=40.0))
    c.key(13, legL=Plant(0.13, -0.50, yaw=8.0, out=4.0, roll=-12.0, arc=0.10))
    c.key(14.5, legL=Plant(0.13, -0.50, yaw=8.0, out=4.0))
    c.key(11, legR=Plant(-0.11, 0.10, out=6.0, roll=50.0))
    # the swing: wind the leg back, whip through the ball, up high
    c.key(14.5, legR=L(-38.0, knee=104.0, out=6.0, twist=10.0, ankle=-30.0))
    c.key(18, legR=L(26.0, knee=14.0, out=4.0, twist=14.0, ankle=-34.0), ease="in")
    c.key(21.5, legR=L(92.0, knee=6.0, out=6.0, twist=10.0, ankle=-20.0), ease="out")
    c.key(25, legR=L(40.0, knee=40.0, out=6.0, ankle=0.0))
    c.key(28, legR=Plant(-0.15, -0.28, out=8.0, roll=-6.0))
    c.key(30, legR=Plant(-0.15, -0.28, out=8.0))
    c.key(18, legL=Plant(0.13, -0.50, yaw=8.0, out=4.0, roll=8.0))
    c.key(21.5, legL=Plant(0.13, -0.50, yaw=8.0, out=4.0, roll=44.0, z=0.05))        # the hop
    c.key(25, legL=Plant(0.13, -0.52, yaw=6.0, out=4.0, roll=10.0))
    c.key(30, legL=Plant(0.13, -0.52, yaw=6.0, out=6.0))
    # body: stays behind the plant foot and leans back through the ball
    c.key(7, hip=(-0.02, 0.18, 0.93), pitch=8.0, bend=8.0, yaw=0.0)
    c.key(13, hip=(0.03, -0.14, 0.89), pitch=2.0, bend=4.0, yaw=-16.0, twist=18.0, roll=6.0)
    c.key(14.5, hip=(0.04, -0.20, 0.88), pitch=-2.0, bend=0.0, yaw=-22.0, twist=26.0, roll=8.0)
    c.key(18, hip=(0.04, -0.25, 0.90), pitch=E(-6.0, "in"), bend=14.0, yaw=E(6.0, "in"), twist=E(-14.0, "in"), roll=8.0, ease="in")
    c.key(21.5, hip=(0.03, -0.30, 0.99), pitch=-10.0, bend=20.0, yaw=16.0, twist=-22.0, roll=4.0, ease="out")
    c.key(25, hip=(0.01, -0.31, 0.92), pitch=4.0, bend=10.0, yaw=8.0, twist=-8.0, roll=0.0)
    c.key(30, hip=(0.0, -0.32, 0.945), pitch=start["pitch"], bend=start["bend"], yaw=0.0, twist=0.0)
    c.key(13, nod=30.0)
    c.key(19, nod=30.0)
    c.key(24, nod=0.0)
    # arms: left out and across for balance, right back
    c.key(7, armL=A(-10.0, out=18.0, twist=30.0, elbow=40.0, grip=0.5), armR=A(20.0, out=14.0, twist=30.0, elbow=50.0, grip=0.5))
    c.key(14.5, armL=A(30.0, out=62.0, twist=0.0, elbow=24.0, grip=0.3), armR=A(-50.0, out=30.0, twist=10.0, elbow=30.0, grip=0.5))
    c.key(18, armL=A(54.0, out=40.0, twist=20.0, elbow=30.0, grip=0.3), armR=A(-62.0, out=36.0, twist=10.0, elbow=24.0, grip=0.5),
          ease="in")
    c.key(21.5, armL=A(70.0, out=-4.0, twist=40.0, elbow=50.0, grip=0.3), armR=A(-40.0, out=46.0, twist=10.0, elbow=30.0, grip=0.5))
    c.key(30, armL=start["armL"], armR=start["armR"])
    c.event("plant", 13)
    c.event("contact", 18)
    c.key_frame = 18
    # where the ball has to sit: just in front of the instep at contact, on its tee
    instep = (where(rig, c, 18, "foot_r") + where(rig, c, 18, "ball_r")) * 0.5
    ball = Vector((instep.x, instep.y - 0.10, 0.11))
    c.extra["ball_on_ground"] = [round(v, 2) for v in ball]
    c.notes = ("Placekick / kickoff with the right foot: two approach steps (right, then the left plant at frame "
               "13), swing through, follow through with a hop. The root stays still: the steps are real (the "
               "pelvis travels from 0.30 m behind the root to 0.32 m ahead of it and stays there). Put the ball "
               f"at {xyz(ball)} (tee height); the instep reaches it at `contact`.")
    fly = flight(ball, (0.0, -17.0, 9.0), 18)
    c.prop = lambda f, pose: (ball_matrix(ball, axis=(0.0, 0.25, 1.0)) if f <= 18
                              else (ball_matrix(fly(f), axis=(0.0, 0.5, 1.0)) if f <= 20 else None))
    return c


# ---- 38 Punt ----------------------------------------------------------------------------------
def punt(rig, made):
    c = Clip("Punt", 28, ball="hand", tier=2,
             notes="")
    start = poses.idle()
    hold_r, hold_l = poses.two_hands(pos=(-0.08, -0.36, 1.22), axis=(0.0, 1.0, 0.1), palm=(0.55, 0.0, 0.83), space="torso")
    c.key(0, start, hip=(0.0, 0.18, 0.945), gaze=1.0, nod=14.0, armR=hold_r, armL=hold_l)
    c.key(0, legL=Plant(0.15, 0.18, out=10.0), legR=Plant(-0.15, 0.20, out=10.0))
    c.key(1, legR=Plant(-0.15, 0.20, out=10.0, roll=20.0))
    c.key(5, legR=Plant(-0.12, 0.02, out=6.0, roll=-8.0, arc=0.06))
    c.key(6, legR=Plant(-0.12, 0.02, out=6.0), legL=Plant(0.15, 0.18, out=10.0, roll=40.0))
    c.key(11, legL=Plant(0.13, -0.34, yaw=6.0, out=4.0, roll=-12.0, arc=0.08))
    c.key(12.5, legL=Plant(0.13, -0.34, yaw=6.0, out=4.0))
    c.key(9, legR=Plant(-0.12, 0.02, out=6.0, roll=50.0))
    c.key(12.5, legR=L(-34.0, knee=96.0, out=6.0, ankle=-34.0))
    c.key(16, legR=L(56.0, knee=10.0, out=4.0, ankle=-40.0), ease="in")
    c.key(19.5, legR=L(124.0, knee=4.0, out=6.0, ankle=-30.0), ease="out")
    c.key(23, legR=L(50.0, knee=44.0, out=6.0, ankle=0.0))
    c.key(26, legR=Plant(-0.15, -0.28, out=8.0, roll=-6.0))
    c.key(28, legR=Plant(-0.15, -0.28, out=8.0))
    c.key(15, legL=Plant(0.13, -0.34, yaw=6.0, out=4.0, roll=21.0))
    c.key(16, legL=Plant(0.13, -0.34, yaw=6.0, out=4.0, roll=27.0))
    c.key(19.5, legL=Plant(0.13, -0.34, yaw=6.0, out=4.0, roll=56.0, z=0.09))        # lifted off the ground
    c.key(23, legL=Plant(0.13, -0.40, yaw=4.0, out=4.0, roll=14.0))
    c.key(28, legL=Plant(0.13, -0.40, yaw=4.0, out=6.0))
    c.key(5, hip=(-0.02, 0.08, 0.93), pitch=8.0, bend=8.0)
    c.key(11, hip=(0.03, -0.16, 0.91), pitch=6.0, bend=6.0, yaw=-8.0, twist=8.0)
    c.key(12.5, hip=(0.04, -0.22, 0.89), pitch=2.0, bend=2.0, yaw=-12.0, twist=12.0, roll=6.0)
    c.key(16, hip=(0.04, -0.27, 0.922), pitch=E(-10.0, "in"), bend=12.0, yaw=E(4.0, "in"), twist=-8.0, roll=6.0, ease="in")
    c.key(19.5, hip=(0.03, -0.31, 1.03), pitch=-18.0, bend=20.0, yaw=10.0, twist=-14.0, roll=2.0, ease="out")
    c.key(23, hip=(0.01, -0.30, 0.92), pitch=6.0, bend=10.0, yaw=4.0, twist=-4.0, roll=0.0)
    c.key(28, hip=(0.0, -0.28, 0.945), pitch=start["pitch"], bend=start["bend"], yaw=0.0, twist=0.0)
    c.key(12, nod=30.0)
    c.key(17, nod=24.0)
    c.key(22, nod=-10.0)
    c.key(28, nod=0.0)
    # the ball is carried forward and laid out flat off the right hand; then the arms balance
    ext_r, ext_l = poses.two_hands(pos=(-0.13, -0.44, 1.20), axis=(0.0, 1.0, 0.05), palm=(0.3, 0.0, 0.95), space="torso")
    c.key(8, armR=ext_r, armL=ext_l)
    c.key(10, armR=ext_r.but(pos=(-0.14, -0.43, 1.17), grip=0.05, thumb=0.1), ease="lin")
    c.key(9, armL=ext_l)
    c.key(13.5, armL=A(40.0, out=58.0, twist=0.0, elbow=26.0, grip=0.3), armR=A(50.0, out=20.0, twist=20.0, elbow=30.0, pron=40.0, grip=0.1))
    c.key(16, armL=A(20.0, out=70.0, twist=0.0, elbow=20.0, grip=0.3), armR=A(-30.0, out=40.0, twist=10.0, elbow=24.0, grip=0.4), ease="in")
    c.key(19.5, armL=A(60.0, out=30.0, twist=20.0, elbow=40.0, grip=0.3), armR=A(-50.0, out=50.0, twist=10.0, elbow=24.0, grip=0.4))
    c.key(28, armL=start["armL"], armR=start["armR"])
    c.event("drop", 10)
    c.event("contact", 16)
    c.ball_frames = (0, 10)
    c.key_frame = 16

    dropped = where(rig, c, 10, "ball_hand_r")
    instep = (where(rig, c, 16, "foot_r") + where(rig, c, 16, "ball_r")) * 0.5
    met = instep + Vector((0.0, -0.02, 0.10))

    def prop(f, pose):
        if f <= 10:
            return socket_matrix(pose, "hand")
        if f <= 16:
            u = (f - 10) / 6.0
            return ball_matrix(dropped.lerp(met, u * u * 0.6 + u * 0.4), axis=(0.0, 1.0, 0.0))
        if f <= 18:
            return ball_matrix(prop.fly(f), axis=(0.0, -1.0, 0.6))
        return None

    prop.fly = flight(met, (0.0, -13.0, 15.0), 16)
    c.prop = prop
    c.extra["contact_point"] = [round(v, 2) for v in met]
    c.notes = ("Punt with the right leg: two steps while the ball is held out in both hands, the right hand lets "
               f"it go at `drop` (ball_hand_r at {xyz(dropped)}), the instep meets it at `contact` around "
               f"{xyz(met)}, big follow-through with a hop. The root stays still: the steps are real and small "
               "(the pelvis travels from 0.18 m behind the root to 0.28 m ahead of it and stays there).")
    return c


# ---- 39 PickUp --------------------------------------------------------------------------------
PICKUP_BALL = (-0.24, -0.44, 0.092)


def pick_up(rig, made):
    c = Clip("PickUp", 14, ball="hand", tier=2,
             notes="Scoop a loose ball off the ground on the move with the right hand: dip over a long right step, "
                   "grab at about (-0.24, -0.44, 0.09) from the root, come up tucking it. Attach the ball to "
                   "ball_hand_r at `grab`; it ends on the ball_tuck_r transform. Starts on Run frame 0 and ends on "
                   "RunBall frame 0; planted feet drift back at about 5 m/s.")
    r0 = RUN.controls(rig, 0.0)
    b0 = _gait_pose(rig)
    hx, hy, hz = r0["hip"]
    c.key(0, r0)
    c.key(14, b0)
    c.key(0, hand2tuck=0.0, gaze=1.0)
    c.key(3, gaze=0.0, nod=-26.0)
    c.key(11, gaze=0.0, nod=-20.0)
    c.key(14, gaze=1.0, hand2tuck=1.0, nod=b0["nod"])
    c.key(9, hand2tuck=0.0)
    c.key(4, hip=(-0.03, hy, 0.69), pitch=48.0, bend=26.0, yaw=8.0, twist=-18.0, roll=-6.0, side=-8.0)
    c.key(7, hip=(-0.05, hy - 0.02, 0.52), pitch=68.0, bend=32.0, yaw=10.0, twist=-26.0, roll=-8.0, side=-12.0)
    c.key(10, hip=(-0.02, hy, 0.74), pitch=40.0, bend=22.0, yaw=4.0, twist=-10.0, roll=-3.0, side=-4.0)
    # right arm: reach, scoop, pull in, tuck
    c.key(4, armR=A(64.0, out=4.0, twist=20.0, elbow=30.0, pron=60.0, grip=0.0, thumb=0.0))
    c.key(7, armR=poses.hold(PICKUP_BALL, axis=(1.0, 0.0, 0.0), palm=(0.0, -0.5, -0.87), space="world",
                             pole=(-1.0, 0.3, 0.3), pspace="world"))
    c.key(10, armR=poses.hold((-0.12, -0.24, 1.22), axis=(0.35, 0.7, 0.6), palm=(0.7, -0.6, 0.4), space="chest",
                              pole=(-0.7, 0.4, -0.6)))
    c.key(14, armR=b0["armR"])
    # left arm: thrown back and out to balance the reach
    c.key(5, armL=A(-48.0, out=40.0, twist=10.0, elbow=36.0, grip=0.4))
    c.key(8, armL=A(-56.0, out=44.0, twist=10.0, elbow=30.0, grip=0.4))
    # feet: left stance, long low right step beside the ball, left drives through
    c.key(1.5, legL=Plant(0.085, -0.02, out=5.0, roll=0.0))
    c.key(3.5, legL=Plant(0.085, 0.30, out=5.0, roll=58.0))
    c.key(7, legL=LegIK(pos=(0.10, 0.62, 0.36), pitch=-80.0))
    c.key(11, legL=LegIK(pos=(0.09, -0.10, 0.34), pitch=-20.0))
    c.key(13, legL=LegIK(pos=(0.085, -0.46, 0.25), pitch=14.0))
    c.key(3, legR=LegIK(pos=(-0.10, -0.26, 0.34), pitch=0.0))
    c.key(6, legR=Plant(-0.10, -0.36, out=6.0, roll=-10.0))
    c.key(8, legR=Plant(-0.10, -0.03, out=6.0, roll=0.0))
    c.key(10.5, legR=Plant(-0.10, 0.36, out=6.0, roll=58.0))
    c.event("grab", 7)
    c.ball_frames = (7, 14)
    c.key_frame = 7
    c.prop = lambda f, pose: (ball_matrix((PICKUP_BALL[0], PICKUP_BALL[1] - (7 - f) * 5.0 / 30.0, PICKUP_BALL[2]),
                                          axis=(1.0, 0.0, 0.0)) if f < 7 else socket_matrix(pose, "hand"))
    return c
