"""The control rig: a small set of semantic controls that is solved into a skel.Pose.

A "control dict" describes one instant of the body:

    hip            pelvis joint position in world space (rest: (0, 0, 0.98))
    yaw pitch roll spin   pelvis orientation in degrees, applied as Rz(yaw) Rx(pitch) Ry(roll) Rz(spin):
                   yaw + turns left, pitch + leans forward (-90 = flat on the back, +90 = face
                   down), roll + leans to the character's left, spin turns about the body's own
                   long axis (what "yaw" would be for a lying or flying body)
    bend twist side       spine totals relative to the pelvis (forward / turn left / lean left)
    nod turn tilt         neck + head totals (look down / look left / ear to the left shoulder)
    gaze           0 = nod/turn/tilt are relative to the chest, 1 = they are world angles
    armL armR      ArmFK or ArmIK (see below)
    legL legR      LegFK, LegIK or Plant
    ground         0 = pelvis height as authored, 1 = pelvis height set so the body rests on z = 0
    clamp          1 = never let the body sink below z = 0 (the pelvis is pushed up if needed)
    hand2tuck      0..1 slides the ball_hand_r socket onto the ball_tuck_r socket's transform

Points and directions given "in a space" are written in REST-POSE WORLD coordinates and are then
carried rigidly by that space's bone ("world", "pelvis", "chest", "head" or any bone name), so a
chest-space target of (0, -0.30, 1.35) means "30 cm in front of the sternum" whatever the body
is doing. The extra space "torso" travels and turns with the chest but stays upright, for
things held level in front of a leaning body.
"""
import copy
import math

from mathutils import Matrix, Quaternion, Vector

from .skel import (BACK, DOWN, FRONT, LEFT, UP, X_AXIS, Y_AXIS, Z_AXIS, Pose, blend_poses,
                   frame_yz, rot3)

SIGN = {"L": 1.0, "R": -1.0}
SUF = {"L": "_l", "R": "_r"}
OTHER = {"L": "R", "R": "L"}
SPACE_ALIAS = {"chest": "spine_03", "hips": "pelvis", "ball": "ball_hand_r", "root": "world"}

BALL_LENGTH = 0.28
BALL_WIDTH = 0.17

DIGIT_BONES = tuple(f"{digit}_{joint}" for digit in ("index", "middle", "ring", "pinky") for joint in (1, 2))
ARM_BONES = ("clavicle", "upperarm", "lowerarm", "hand", "fingers", "thumb") + DIGIT_BONES
LEG_BONES = ("thigh", "calf", "foot", "ball")


def space_bone(name):
    return SPACE_ALIAS.get(name, name)


def _mirror_space(name):
    if name is None:
        return None
    if name.endswith("_l"):
        return name[:-2] + "_r"
    if name.endswith("_r") and not name.startswith("ball_"):
        return name[:-2] + "_l"
    return name


def _mx(v):
    return None if v is None else (-v[0], v[1], v[2])


# --------------------------------------------------------------------------------------------
# Limb specs
# --------------------------------------------------------------------------------------------
class Spec:
    """A limb description. NUM fields interpolate; CFG fields must match for two specs to be
    interpolated field by field (otherwise the two solved limbs are blended instead)."""
    NUM = ()
    CFG = ()
    arc = 0.0           # extra height (m) at the middle of the move that arrives at this key

    def __init__(self, **kw):
        for k, v in self.NUM + self.CFG:
            setattr(self, k, v)
        for k, v in kw.items():
            if k != "arc" and k not in self._fields():
                raise TypeError(f"{type(self).__name__} has no field {k!r}")
            setattr(self, k, v)

    @classmethod
    def _fields(cls):
        return {k for k, _ in cls.NUM + cls.CFG}

    def sig(self):
        cfg = tuple(getattr(self, k) for k, _ in self.CFG)
        opt = tuple(getattr(self, k) is None for k, _ in self.NUM)
        return (type(self).__name__, cfg, opt)

    def vec(self):
        out = []
        for k, _ in self.NUM:
            v = getattr(self, k)
            if v is None:
                continue
            if isinstance(v, (int, float)):
                out.append(float(v))
            else:
                out.extend(float(c) for c in v)
        return out

    def with_vec(self, values):
        new = copy.copy(self)
        i = 0
        for k, _ in self.NUM:
            v = getattr(self, k)
            if v is None:
                continue
            if isinstance(v, (int, float)):
                setattr(new, k, values[i])
                i += 1
            else:
                n = len(v)
                setattr(new, k, tuple(values[i:i + n]))
                i += n
        return new

    def but(self, **kw):
        new = copy.copy(self)
        for k, v in kw.items():
            if k != "arc" and k not in self._fields():
                raise TypeError(f"{type(self).__name__} has no field {k!r}")
            setattr(new, k, v)
        return new

    def mirrored(self):
        return copy.copy(self)

    def __repr__(self):
        body = ", ".join(f"{k}={getattr(self, k)!r}" for k, _ in self.NUM + self.CFG)
        return f"{type(self).__name__}({body})"


_HAND = (("pron", 0.0), ("flex", 0.0), ("dev", 0.0), ("grip", 0.3), ("thumb", 0.3),
         ("shrug", 0.0), ("prot", 0.0), ("palm", None), ("fingers", None))


class ArmFK(Spec):
    """Arm by angles, measured from "hanging straight down beside the body".

    fwd    swing forward (+) / back (-) in the sagittal plane; 90 = straight ahead, 180 = up
    out    away from the body sideways; 90 = straight out to the side
    twist  turn about the upper arm; 0 = a flexed forearm points to the front, + = across the body
    elbow  flexion, 0 = straight
    pron   forearm twist, + turns the palm down/back (0 = palm toward the body, thumb forward)
    flex / dev   wrist flexion toward the palm / toward the thumb
    grip / thumb 0 = open hand, 1 = fist
    palm + fingers   optional absolute hand orientation (directions in `hspace`); with `palm`
                     alone the fingers simply continue the forearm as far as the palm allows
    """
    NUM = (("fwd", 0.0), ("out", 8.0), ("twist", 0.0), ("elbow", 12.0)) + _HAND
    CFG = (("hspace", "world"),)

    def mirrored(self):
        return self.but(palm=_mx(self.palm), fingers=_mx(self.fingers),
                        hspace=_mirror_space(self.hspace))


class ArmIK(Spec):
    """Arm by a target for the hand.

    pos + space   where the hand goes (see `at`)
    at            "wrist" (default), "palm" (centre of the palm, needs palm + fingers),
                  "tip" (finger tips, needs palm + fingers), or "ball" (right hand only: `pos`
                  is the football's centre, `fingers` its long axis and `palm` the direction the
                  palm pushes on it; the hand is placed so ball_hand_r lands exactly there)
    pole + pspace the direction the elbow points
    """
    NUM = (("pos", (0.0, -0.3, 1.2)), ("pole", None)) + _HAND
    CFG = (("space", "world"), ("pspace", "chest"), ("hspace", "world"), ("at", "wrist"))

    def mirrored(self):
        return self.but(pos=_mx(self.pos), pole=_mx(self.pole), palm=_mx(self.palm),
                        fingers=_mx(self.fingers), space=_mirror_space(self.space),
                        pspace=_mirror_space(self.pspace), hspace=_mirror_space(self.hspace))


class LegFK(Spec):
    """Leg by angles relative to the pelvis, measured from "hanging straight down".

    fwd    hip flexion (+ lifts the knee to the front)      out    abduction (leg out sideways)
    twist  + turns the knee/toes outward                      knee   flexion, 0 = straight
    ankle  + toes up (relative to the shin)                   toe    + toes up
    """
    NUM = (("fwd", 0.0), ("out", 0.0), ("twist", 0.0), ("knee", 0.0), ("ankle", 0.0), ("toe", 0.0))


class LegIK(Spec):
    """Leg by an ankle target.

    pos + space    ankle joint position
    knee + kspace  the direction the knee points (default: the pelvis' front, slightly outward)
    pitch yaw bank foot orientation in `space` (pitch + = toes up, yaw + = turned left),
                   ignored when `ankle` is given
    ankle          if not None the foot is posed relative to the shin instead (+ = toes up)
    toe            toe bend relative to the foot (+ = up), unless flat_toe
    flat_toe       keep the toes flat in `space` (used by Plant when the heel lifts)
    """
    NUM = (("pos", (0.105, 0.01, 0.1)), ("knee", None), ("pitch", 0.0), ("yaw", 0.0), ("bank", 0.0),
           ("toe", 0.0), ("ankle", None))
    CFG = (("space", "world"), ("kspace", "pelvis"), ("flat_toe", False))

    def mirrored(self):
        return self.but(pos=_mx(self.pos), knee=_mx(self.knee), yaw=-self.yaw, bank=-self.bank,
                        space=_mirror_space(self.space), kspace=_mirror_space(self.kspace))


class Plant(Spec):
    """A foot standing on the ground.

    x, y   the ground point under the ankle when the foot is flat (rest: (+-0.105, 0.01))
    z      height of the whole footprint above the ground (0 = on it)
    yaw    absolute heading of the foot (+ = turned left); `out` adds toe-out on either side
    roll   + lifts the heel (pivot on the ball of the foot, toes stay flat),
           - lifts the toes (pivot on the heel)
    """
    NUM = (("x", 0.105), ("y", 0.01), ("z", 0.0), ("yaw", 0.0), ("out", 6.0), ("roll", 0.0),
           ("knee", None))
    CFG = (("kspace", "pelvis"),)

    def __init__(self, x=None, y=None, **kw):
        super().__init__(**kw)
        if x is not None:
            self.x = x
        if y is not None:
            self.y = y

    def mirrored(self):
        return self.but(x=-self.x, yaw=-self.yaw, knee=_mx(self.knee),
                        kspace=_mirror_space(self.kspace))


class Mix:
    """Two limb descriptions that cannot be interpolated field by field; blended after solving."""

    def __init__(self, a, b, w, arc=0.0):
        self.a, self.b, self.w, self.arc = a, b, w, arc

    def mirrored(self):
        return Mix(self.a.mirrored(), self.b.mirrored(), self.w, self.arc)


DEFAULTS = dict(
    hip=(0.0, 0.0, 0.98), yaw=0.0, pitch=0.0, roll=0.0, spin=0.0,
    bend=0.0, twist=0.0, side=0.0,
    nod=0.0, turn=0.0, tilt=0.0, gaze=0.0,
    armL=ArmFK(), armR=ArmFK(),
    legL=Plant(0.105, 0.01), legR=Plant(-0.105, 0.01),
    ground=0.0, clamp=1.0, hand2tuck=0.0,
)
NEGATE_ON_MIRROR = ("yaw", "roll", "spin", "twist", "side", "turn", "tilt")


def mirror_controls(c):
    """The same instant, mirrored left <-> right."""
    out = dict(c)
    out["hip"] = _mx(c["hip"])
    for k in NEGATE_ON_MIRROR:
        out[k] = -c[k]
    out["armL"], out["armR"] = c["armR"].mirrored(), c["armL"].mirrored()
    out["legL"], out["legR"] = c["legR"].mirrored(), c["legL"].mirrored()
    return out


# --------------------------------------------------------------------------------------------
# Solver
# --------------------------------------------------------------------------------------------
def two_bone(start, target, l1, l2, pole):
    """Middle joint of a two-bone chain. Returns (joint, reachable target, plane dir, reached)."""
    v = target - start
    d = v.length
    reached = True
    lo, hi = abs(l1 - l2) + 1e-4, (l1 + l2) * 0.9995
    if d < 1e-6:
        v, d = Vector((0.0, 0.0, -1.0)), lo
        reached = False
    n = v / v.length
    if d > hi:
        reached = d < (l1 + l2) + 1e-4
        d = hi
    elif d < lo:
        d, reached = lo, False
    perp = Vector(pole) - n * Vector(pole).dot(n)
    if perp.length < 1e-6:
        perp = n.orthogonal()
    perp.normalize()
    a = (l1 * l1 - l2 * l2 + d * d) / (2.0 * d)
    h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    return start + n * a + perp * h, start + n * d, perp, reached


class Rig:
    """Solves control dicts into Poses."""

    def __init__(self, skel):
        self.skel = sk = skel
        self.arm_l1 = sk.dist("upperarm_l", "lowerarm_l")
        self.arm_l2 = sk.dist("lowerarm_l", "hand_l")
        self.leg_l1 = sk.dist("thigh_l", "calf_l")
        self.leg_l2 = sk.dist("calf_l", "foot_l")
        self.hand_len = sk.length["hand_l"]
        self.reach = self.arm_l1 + self.arm_l2

        ankle, ball = sk.head["foot_l"], sk.head["ball_l"]
        self.ankle_h = ankle.z
        self.ball_h = ball.z
        self.ball_fwd = ankle.y - ball.y
        self.ab_len = math.hypot(self.ball_fwd, ankle.z - ball.z)
        self.ab_ang = math.atan2(ankle.z - ball.z, self.ball_fwd)
        self.heel_back = 0.055
        self.ha_len = math.hypot(self.heel_back, self.ankle_h)
        self.ha_ang = math.atan2(self.heel_back, self.ankle_h)

        u = sk.tail["clavicle_l"] - sk.head["clavicle_l"]
        self.clav_up0 = math.degrees(math.atan2(u.z, u.x))

        # Hands: local frames, palm normal, grip points, thumb closing axis.
        self.palm_local = {}
        self.palm_point = {}
        self.tip_point = {}
        self.thumb_axis = {}
        for side in "LR":
            hand, fingers, thumb = "hand" + SUF[side], "fingers" + SUF[side], "thumb" + SUF[side]
            palm = Vector((SIGN[side], 0.0, 0.0))            # palm normal in hand-local axes
            self.palm_local[side] = palm
            self.palm_point[side] = Vector((0.0, 0.055, 0.0)) + palm * 0.018
            self.tip_point[side] = Vector((0.0, sk.length[hand] + sk.length[fingers], 0.0))
            palm_world = sk.rest_rot[hand] @ palm
            t_dir = (sk.tail[thumb] - sk.head[thumb]).normalized()
            axis_world = t_dir.cross(palm_world).normalized()
            self.thumb_axis[side] = sk.rest_rot[thumb].inverted() @ axis_world

        # Ball sockets relative to the bone that carries them.
        self.sock_hand_rel = sk.offset["ball_hand_r"]         # in hand_r's frame
        self.ball_center_local = self.sock_hand_rel.translation.copy()
        self.ball_axis_local = (self.sock_hand_rel.to_3x3() @ Y_AXIS).normalized()
        self.spheres = _body_spheres(sk)

    # ---- small helpers -------------------------------------------------------------------
    def plant_ankle(self, x, y, z, yaw, roll):
        """Ankle position and foot pitch for a footprint at (x, y); see Plant."""
        fwd = rot3(Z_AXIS, yaw) @ FRONT
        if roll >= 0.0:
            ball = Vector((x, y, self.ball_h + z)) + fwd * self.ball_fwd
            a = self.ab_ang + math.radians(roll)
            return ball - fwd * (self.ab_len * math.cos(a)) + UP * (self.ab_len * math.sin(a))
        heel = Vector((x, y, z)) - fwd * self.heel_back
        b = self.ha_ang + math.radians(roll)
        return heel + fwd * (self.ha_len * math.sin(b)) + UP * (self.ha_len * math.cos(b))

    def plant_to_ik(self, spec, side):
        yaw = spec.yaw + SIGN[side] * spec.out
        pos = self.plant_ankle(spec.x, spec.y, spec.z, yaw, spec.roll)
        return LegIK(pos=tuple(pos), knee=spec.knee, pitch=-spec.roll, yaw=yaw, space="world",
                     kspace=spec.kspace, flat_toe=spec.roll >= 0.0)

    def ball_radius(self, direction, axis):
        """Distance from the ball's centre to its surface along `direction`."""
        c = abs(Vector(direction).normalized().dot(Vector(axis).normalized()))
        s = math.sqrt(max(1.0 - c * c, 0.0))
        a, b = BALL_LENGTH * 0.5, BALL_WIDTH * 0.5
        return 1.0 / math.sqrt((c / a) ** 2 + (s / b) ** 2)

    # ---- the solve -----------------------------------------------------------------------
    def solve(self, controls):
        c = dict(DEFAULTS)
        c.update(controls)
        ground = float(c["ground"])
        clamp = float(c["clamp"]) > 0.5
        lift = 0.0
        pose = self._solve_once(c, lift)
        if ground > 0.0 or clamp:
            groups = self._clamp_groups(c)
            low0 = self.lowest(pose, groups)[0]
            want = (1.0 - ground) * max(low0, 0.0) if clamp else (1.0 - ground) * low0
            if abs(low0 - want) > 1e-5:
                low = low0
                for _ in range(6):
                    lift += want - low
                    pose = self._solve_once(c, lift)
                    low = self.lowest(pose, groups)[0]
                    if abs(low - want) < 2e-4:
                        break
        pose.lift = lift
        return pose

    def _clamp_groups(self, c):
        groups = {"core"}
        for side in "LR":
            arm, leg = c["arm" + side], c["leg" + side]
            if not _is_world_ik(arm):
                groups.add("hand" + side)
            if not _is_world_ik(leg):
                groups.add("foot" + side)
        return groups

    def lowest(self, pose, groups=None):
        best, name = 1e9, None
        for bone, group, point, radius in self.spheres:
            if groups is not None and group not in groups:
                continue
            z = (pose.delta(bone) @ point).z - radius
            if z < best:
                best, name = z, bone
        return best, name

    def _solve_once(self, c, lift):
        pose = Pose(self.skel)
        sk = self.skel
        # pelvis
        hip = Vector(c["hip"]) + Vector((0.0, 0.0, lift))
        rot = (rot3(Z_AXIS, c["yaw"]) @ rot3(X_AXIS, c["pitch"]) @ rot3(Y_AXIS, c["roll"])
               @ rot3(Z_AXIS, c["spin"]))
        m = (rot @ sk.rest_rot["pelvis"]).to_4x4()
        m.translation = hip
        pose.set_world("pelvis", m)
        # spine
        for bone, wb, wt in (("spine_01", 0.25, 0.20), ("spine_02", 0.35, 0.35), ("spine_03", 0.40, 0.45)):
            q = (Quaternion(Y_AXIS, math.radians(c["twist"] * wt))
                 @ Quaternion(X_AXIS, math.radians(c["bend"] * wb))
                 @ Quaternion(Z_AXIS, math.radians(-c["side"] * wb)))
            pose.set_q(bone, q)
        self._solve_head(pose, c)
        self._solve_limb(pose, "R", c["armR"], self._arm)
        self._solve_socket(pose, c)
        self._solve_limb(pose, "L", c["armL"], self._arm)
        self._solve_limb(pose, "L", c["legL"], self._leg)
        self._solve_limb(pose, "R", c["legR"], self._leg)
        return pose

    def _solve_head(self, pose, c):
        nod, turn, tilt, gaze = c["nod"], c["turn"], c["tilt"], c["gaze"]

        def local(w):
            return (Quaternion(Y_AXIS, math.radians(turn * w)) @ Quaternion(X_AXIS, math.radians(nod * w))
                    @ Quaternion(Z_AXIS, math.radians(-tilt * w)))

        pose.set_q("neck_01", local(0.4))
        pose.set_q("head", local(0.6))
        if gaze > 0.0:
            sk = self.skel
            stable = (rot3(Z_AXIS, turn) @ rot3(X_AXIS, nod) @ rot3(Y_AXIS, tilt))
            follow = pose.wrot("head") @ sk.rest_rot["head"].inverted()
            fix = (stable @ follow.inverted()).to_quaternion()          # world correction
            part = Quaternion().slerp(fix, 0.4 * gaze).to_matrix()
            pose.set_world_rot("neck_01", part @ pose.wrot("neck_01"))
            follow = pose.wrot("head") @ sk.rest_rot["head"].inverted()
            target = follow.to_quaternion().slerp(stable.to_quaternion(), gaze).to_matrix()
            pose.set_world_rot("head", target @ sk.rest_rot["head"])

    def _solve_socket(self, pose, c):
        w = float(c["hand2tuck"])
        if w <= 0.0:
            return
        a = pose.world("ball_hand_r")
        b = pose.world("ball_tuck_r")
        ya, yb = (a.to_3x3() @ Y_AXIS).normalized(), (b.to_3x3() @ Y_AXIS).normalized()
        if ya.dot(yb) < 0.0:
            yb = -yb                                # the ball looks the same end for end
        swing = ya.rotation_difference(yb)
        rot = Quaternion().slerp(swing, w).to_matrix() @ a.to_3x3()
        m = rot.to_4x4()
        m.translation = a.translation.lerp(b.translation, w)
        pose.set_world("ball_hand_r", m)

    # ---- limbs ---------------------------------------------------------------------------
    def _solve_limb(self, pose, side, spec, solver):
        if isinstance(spec, Mix):
            if spec.w <= 0.0 or spec.w >= 1.0:          # exactly on a key: that key's own description
                self._solve_limb(pose, side, spec.a if spec.w <= 0.0 else spec.b, solver)
                return
            a, b = spec.a, spec.b
            wa, wb = self._to_world(pose, side, a), self._to_world(pose, side, b)
            if wa is not None and wb is not None and wa.sig() == wb.sig():
                va, vb = wa.vec(), wb.vec()
                mixed = wa.with_vec([x + (y - x) * spec.w for x, y in zip(va, vb)])
                if spec.arc and hasattr(mixed, "pos"):
                    p = mixed.pos
                    mixed.pos = (p[0], p[1], p[2] + spec.arc * math.sin(math.pi * spec.w))
                solver(pose, side, mixed)
                return
            bones = [b_ + SUF[side] for b_ in (ARM_BONES if solver == self._arm else LEG_BONES)]
            other = pose.copy()
            notes = len(pose.warn)
            self._solve_limb(pose, side, a, solver)
            self._solve_limb(other, side, b, solver)
            blend_poses(pose, other, spec.w, bones)
            del pose.warn[notes:]          # a target that is being blended away is not a constraint
            return
        solver(pose, side, spec)

    def _to_world(self, pose, side, spec):
        """A world-space IK equivalent of an IK-like spec (None for FK specs)."""
        if isinstance(spec, Plant):
            spec = self.plant_to_ik(spec, side)
        if isinstance(spec, LegIK):
            if spec.ankle is not None:
                return None
            if spec.space == "world" and spec.kspace == "world" and spec.knee is not None and not spec.flat_toe:
                return spec
            rot = pose.delta(space_bone(spec.space)).to_3x3() if spec.space != "world" else Matrix.Identity(3)
            foot = rot @ self._foot_rot(spec, "foot" + SUF[side])
            fwd = foot @ self.skel.rest_rot["foot" + SUF[side]].inverted() @ FRONT
            yaw = math.degrees(math.atan2(fwd.x, -fwd.y))
            pitch = math.degrees(math.asin(max(-1.0, min(1.0, fwd.z))))
            pitch = pitch if spec.space != "world" else spec.pitch
            # toes held flat on the ground are simply bent up by the heel lift
            toe = max(0.0, -pitch) if spec.flat_toe else spec.toe
            return LegIK(pos=tuple(pose.point(space_bone(spec.space), spec.pos)),
                         knee=tuple(self._knee_pole(pose, side, spec)),
                         pitch=pitch, yaw=yaw if spec.space != "world" else spec.yaw,
                         bank=spec.bank, toe=toe, space="world", kspace="world", flat_toe=False)
        if isinstance(spec, ArmIK):
            if spec.at != "wrist" or spec.palm is not None or spec.fingers is not None:
                return None
            pole = spec.pole if spec.pole is not None else self._default_pole(side)
            return spec.but(pos=tuple(pose.point(space_bone(spec.space), spec.pos)),
                            pole=tuple(pose.direction(space_bone(spec.pspace), pole)),
                            space="world", pspace="world")
        return None

    @staticmethod
    def _default_pole(side):
        return (0.45 * SIGN[side], 0.55, -0.75)

    def _knee_pole(self, pose, side, spec):
        """World direction the knee points for an IK leg."""
        if spec.knee is not None:
            return pose.direction(space_bone(spec.kspace), spec.knee)
        pole = pose.direction("pelvis", (0.16 * SIGN[side], -1.0, 0.0)).normalized()
        if spec.ankle is None:
            space = space_bone(spec.space)
            srot = pose.delta(space).to_3x3() if space != "world" else Matrix.Identity(3)
            pole = pole * 0.6 + (srot @ rot3(Z_AXIS, spec.yaw) @ FRONT) * 0.4
        return pole

    def _clavicle(self, pose, side, shrug, prot):
        s = SIGN[side]
        dc = pose.delta("spine_03").to_3x3()
        left, front, up = dc @ LEFT, dc @ FRONT, dc @ UP
        u, p = math.radians(self.clav_up0 + shrug), math.radians(prot)
        d = (left * s * math.cos(p) + front * math.sin(p)) * math.cos(u) + up * math.sin(u)
        pose.aim("clavicle" + SUF[side], d, front)

    def _arm(self, pose, side, spec):
        s, suf = SIGN[side], SUF[side]
        ua, la, ha = "upperarm" + suf, "lowerarm" + suf, "hand" + suf
        dc = pose.delta("spine_03").to_3x3()
        left, front, up = dc @ LEFT, dc @ FRONT, dc @ UP
        out_axis = left * s
        hand_rot = None
        auto = spec.palm is not None and spec.fingers is None       # fingers follow the forearm
        if spec.palm is not None and spec.fingers is not None:
            hand_rot = self._hand_frame(pose, side, spec)
        palm_dir = pose.direction(space_bone(spec.hspace), spec.palm).normalized() if auto else None

        if isinstance(spec, ArmFK):
            fw, ou, tw, el = (math.radians(v) for v in (spec.fwd, spec.out, spec.twist, spec.elbow))
            sag = front * math.sin(fw) - up * math.cos(fw)
            d = out_axis * math.sin(ou) + sag * math.cos(ou)
            elev = math.degrees(math.asin(max(-1.0, min(1.0, d.dot(up)))))
            self._clavicle(pose, side, spec.shrug + max(0.0, elev + 15.0) * 0.30, spec.prot)
            f0 = front * math.cos(fw) + up * math.sin(fw)
            inward = d.cross(f0) * s
            f = f0 * math.cos(tw) + inward * math.sin(tw)
            pose.aim(ua, d, f)
            fore = d * math.cos(el) + f * math.sin(el)
            pose.aim(la, fore, f * math.cos(el) - d * math.sin(el))
            if auto:
                hand_rot = self._hand_from(fore, palm_dir, side)
        else:
            goal = pose.point(space_bone(spec.space), spec.pos)

            def wrist_goal(rot):
                if spec.at == "ball":
                    return goal - rot @ self.ball_center_local
                if spec.at == "palm":
                    return goal - rot @ self.palm_point[side]
                if spec.at == "tip":
                    return goal - rot @ self.tip_point[side]
                return goal

            self._clavicle(pose, side, spec.shrug, spec.prot)
            reach = goal - pose.head(ua)
            length = max(reach.length, 1e-6)
            elev = math.degrees(math.asin(max(-1.0, min(1.0, reach.dot(up) / length))))
            far = max(0.0, min(1.0, (length - 0.75 * self.reach) / (0.25 * self.reach)))
            self._clavicle(pose, side, spec.shrug + max(0.0, elev + 15.0) * 0.30,
                           spec.prot + 14.0 * far * max(0.0, reach.dot(front) / length))
            pole = spec.pole if spec.pole is not None else self._default_pole(side)
            pole = pose.direction(space_bone(spec.pspace), pole)
            start = pose.head(ua)
            guess = goal - start
            for _ in range(3 if auto else 1):
                if auto:
                    hand_rot = self._hand_from(guess, palm_dir, side)
                target = wrist_goal(hand_rot) if hand_rot is not None else goal
                elbow, wrist, perp, ok = two_bone(start, target, self.arm_l1, self.arm_l2, pole)
                guess = wrist - elbow
            if not ok:
                pose.warn.append(f"arm{side} target out of reach by {(target - wrist).length:.3f} m")
            pose.aim(ua, elbow - start, -perp)
            pose.aim_x(la, wrist - elbow, pose.wrot(ua).col[0])

        if hand_rot is None:
            if spec.pron:
                pose.rotate_local(la, Y_AXIS, s * spec.pron)
            pose.set_q(ha, Quaternion(Z_AXIS, math.radians(-s * spec.flex))
                       @ Quaternion(X_AXIS, math.radians(spec.dev)))
        else:
            pose.set_world_rot(ha, hand_rot)
            twist = math.degrees(pose.q[ha].to_swing_twist("Y")[1])
            # The forearm takes half of the twist, fading out toward +-180 so that it never
            # flips when an (unnatural) hand orientation crosses the wrap-around.
            share = 0.5 * twist if abs(twist) <= 90.0 else math.copysign(45.0 * (180.0 - abs(twist)) / 90.0, twist)
            pose.rotate_local(la, Y_AXIS, share)
            pose.set_world_rot(ha, hand_rot)
        pose.set_q("fingers" + suf, Quaternion(Z_AXIS, math.radians(-s * 58.0 * spec.grip)))
        for digit in DIGIT_BONES:
            curl = 52.0 if digit.endswith("_1") else 30.0
            pose.set_q(digit + suf, Quaternion(X_AXIS, math.radians(curl * spec.grip)))
        pose.set_q("thumb" + suf, Quaternion(self.thumb_axis[side], math.radians(55.0 * spec.thumb)))

    @staticmethod
    def _hand_from(along, palm, side):
        """Hand frame whose palm faces `palm` and whose fingers continue `along` as far as that allows."""
        y = Vector(along) - palm * Vector(along).dot(palm)
        if y.length < 1e-4:
            y = palm.orthogonal()
        y.normalize()
        z = palm.cross(y) if side == "L" else y.cross(palm)
        return frame_yz(y, z)

    def _hand_frame(self, pose, side, spec):
        """World rotation of the hand bone from the spec's absolute palm / fingers directions."""
        space = space_bone(spec.hspace)
        palm = pose.direction(space, spec.palm).normalized()
        y = pose.direction(space, spec.fingers).normalized()
        if isinstance(spec, ArmIK) and spec.at == "ball":
            # `fingers` is the ball's long axis, `palm` the push direction (hand -> ball centre).
            a_loc = self.ball_axis_local
            n_loc = self.palm_local["R"].copy()            # palm normal in hand space
            n_loc = (n_loc - a_loc * n_loc.dot(a_loc)).normalized()
            src = _frame2(a_loc, n_loc)
            palm = (palm - y * palm.dot(y)).normalized()
            dst = _frame2(y, palm)
            return dst @ src.inverted()
        palm = palm - y * palm.dot(y)
        if palm.length < 1e-6:
            palm = y.orthogonal()
        palm.normalize()
        z = palm.cross(y) if side == "L" else y.cross(palm)      # thumb side
        return frame_yz(y, z)

    def _foot_rot(self, spec, foot):
        return (rot3(Z_AXIS, spec.yaw) @ rot3(X_AXIS, -spec.pitch) @ rot3(Y_AXIS, spec.bank)
                @ self.skel.rest_rot[foot])

    def _leg(self, pose, side, spec):
        s, suf = SIGN[side], SUF[side]
        th, ca, ft, bl = "thigh" + suf, "calf" + suf, "foot" + suf, "ball" + suf
        if isinstance(spec, LegFK):
            dp = pose.delta("pelvis").to_3x3()
            left, front, up = dp @ LEFT, dp @ FRONT, dp @ UP
            fw, ou, tw, kn = (math.radians(v) for v in (spec.fwd, spec.out, spec.twist, spec.knee))
            sag = front * math.sin(fw) - up * math.cos(fw)
            d = left * s * math.sin(ou) + sag * math.cos(ou)
            f0 = front * math.cos(fw) + up * math.sin(fw)
            outward = -d.cross(f0) * s
            f = f0 * math.cos(tw) + outward * math.sin(tw)
            pose.aim(th, d, f)
            pose.aim(ca, d * math.cos(kn) - f * math.sin(kn), f * math.cos(kn) + d * math.sin(kn))
            pose.set_q(ft, Quaternion(X_AXIS, math.radians(spec.ankle)))
            pose.set_q(bl, Quaternion(X_AXIS, math.radians(spec.toe)))
            return
        if isinstance(spec, Plant):
            spec = self.plant_to_ik(spec, side)
        space = space_bone(spec.space)
        target = pose.point(space, spec.pos)
        pole = self._knee_pole(pose, side, spec)
        start = pose.head(th)
        knee, ankle, perp, ok = two_bone(start, target, self.leg_l1, self.leg_l2, pole)
        if not ok:
            pose.warn.append(f"leg{side} target out of reach by {(target - ankle).length:.3f} m")
        pose.aim(th, knee - start, perp)
        pose.aim_x(ca, ankle - knee, pose.wrot(th).col[0])
        if spec.ankle is not None:
            pose.set_q(ft, Quaternion(X_AXIS, math.radians(spec.ankle)))
            pose.set_q(bl, Quaternion(X_AXIS, math.radians(spec.toe)))
            return
        srot = pose.delta(space).to_3x3() if space != "world" else Matrix.Identity(3)
        pose.set_world_rot(ft, srot @ self._foot_rot(spec, ft))
        if spec.flat_toe:
            pose.set_world_rot(bl, srot @ rot3(Z_AXIS, spec.yaw) @ self.skel.rest_rot[bl])
        else:
            pose.set_q(bl, Quaternion(X_AXIS, math.radians(spec.toe)))


def _frame2(a, b):
    """Orthonormal 3x3 with columns (a, b, a x b); a and b must already be perpendicular."""
    m = Matrix((a, b, a.cross(b)))
    m.transpose()
    return m


def _is_world_ik(spec):
    if isinstance(spec, Mix):
        return _is_world_ik(spec.a) and _is_world_ik(spec.b)
    if isinstance(spec, Plant):
        return True
    return isinstance(spec, (ArmIK, LegIK)) and spec.space == "world"


def _body_spheres(sk):
    """Collision spheres for ground contact: (bone, group, rest-world centre, radius)."""
    out = []

    def add(bone, group, point, radius):
        out.append((bone, group, Vector(point), radius))

    # Sized from the mid-build athlete mesh (Art/blend/player_mid.blend): padded chest and
    # shoulders, helmet with facemask, thigh pads.
    add("pelvis", "core", (0.0, 0.025, 0.97), 0.115)
    add("pelvis", "core", (0.0, -0.015, 0.99), 0.105)
    add("spine_01", "core", (0.0, -0.005, 1.14), 0.105)
    add("spine_02", "core", (0.0, -0.007, 1.27), 0.15)
    add("spine_03", "core", (0.0, -0.007, 1.42), 0.158)
    add("spine_03", "core", (0.19, 0.0, 1.49), 0.115)
    add("spine_03", "core", (-0.19, 0.0, 1.49), 0.115)
    add("head", "core", (0.0, 0.0, 1.745), 0.15)
    add("head", "core", (0.0, -0.105, 1.70), 0.07)
    for side in "LR":
        s, suf = SIGN[side], SUF[side]

        def along(bone, t):
            return sk.head[bone].lerp(sk.tail[bone], t)

        add("upperarm" + suf, "core", along("upperarm" + suf, 0.5), 0.065)
        add("lowerarm" + suf, "core", along("lowerarm" + suf, 0.0), 0.05)
        add("lowerarm" + suf, "core", along("lowerarm" + suf, 0.55), 0.042)
        add("hand" + suf, "hand" + side, along("hand" + suf, 0.0), 0.035)
        add("hand" + suf, "hand" + side, along("hand" + suf, 0.9), 0.025)
        add("fingers" + suf, "hand" + side, along("fingers" + suf, 1.0), 0.012)
        add("thigh" + suf, "core", along("thigh" + suf, 0.3), 0.105)
        add("calf" + suf, "core", along("calf" + suf, 0.0), 0.065)
        add("calf" + suf, "core", along("calf" + suf, 0.5), 0.06)
        add("foot" + suf, "foot" + side, along("foot" + suf, 0.0), 0.04)
        add("foot" + suf, "foot" + side, (0.105 * s, 0.055, 0.03), 0.03)
        add("ball" + suf, "foot" + side, along("ball" + suf, 0.0), 0.025)
        add("ball" + suf, "foot" + side, along("ball" + suf, 1.0), 0.025)
    return out
