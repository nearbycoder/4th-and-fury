"""Procedural stepping cycles (run, jog, backpedal, shuffle...) built from foot paths.

Phase 0 is LEFT foot contact, phase 0.5 RIGHT foot contact. While a foot is on the ground its
footprint moves exactly with the ground (opposite to the direction of travel at the clip's
speed), so the feet do not slide when the game moves the root at that speed. In the air the
ankle follows a spline through a few control points; the pelvis bobs, sways and turns on
sinusoids locked to the same phase.
"""
import math

from mathutils import Vector

from .clip import FPS
from .controls import ArmFK, LegIK, Mix, Plant

TAU = math.pi * 2.0


def smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def wave(ph, at=0.0):
    """Cosine in phase units: +1 at phase `at`, -1 half a cycle later."""
    return math.cos(TAU * (ph - at))


def hermite(knots, s, m_first, m_last):
    """Cubic through knots [(s_i, Vector)], Catmull-Rom tangents inside, given end tangents."""
    n = len(knots)
    i = 0
    while i < n - 2 and s > knots[i + 1][0]:
        i += 1
    (s0, p0), (s1, p1) = knots[i], knots[i + 1]

    def tangent(j):
        if j == 0:
            return m_first
        if j == n - 1:
            return m_last
        return (knots[j + 1][1] - knots[j - 1][1]) / (knots[j + 1][0] - knots[j - 1][0])

    h = s1 - s0
    u = (s - s0) / h
    u2, u3 = u * u, u * u * u
    return (p0 * (2 * u3 - 3 * u2 + 1) + tangent(i) * (h * (u3 - 2 * u2 + u))
            + p1 * (-2 * u3 + 3 * u2) + tangent(i + 1) * (h * (u3 - u2)))


def track(points, s):
    """Piecewise-smooth scalar through [(s, value), ...]."""
    if s <= points[0][0]:
        return points[0][1]
    for (s0, v0), (s1, v1) in zip(points, points[1:]):
        if s <= s1:
            return v0 + (v1 - v0) * smooth((s - s0) / (s1 - s0))
    return points[-1][1]


class Gait:
    """Parameters of one stepping cycle; see the attribute comments."""

    def __init__(self, **kw):
        self.frames = 16
        self.speed = 8.0
        self.travel = (0.0, -1.0)            # world xy direction the ROOT moves in
        self.duty = 0.19                     # part of the cycle each foot spends on the ground
        self.base = {"L": (0.085, 0.0), "R": (-0.085, 0.0)}   # footprint when `along` is 0
        self.mid = {"L": -0.12, "R": -0.12}  # footprint position along travel at mid-stance (m)
        self.toe_out = 5.0
        self.foot_yaw = 0.0                  # heading of the feet (deg, + left)
        self.roll = [(0.0, -6.0), (0.15, 0.0), (0.45, 0.0), (1.0, 58.0)]   # heel lift over stance
        # ankle path in the air: (part of the swing, metres along travel, ankle height)
        self.swing = [(0.14, -0.66, 0.42), (0.32, -0.36, 0.76), (0.52, -0.05, 0.50),
                      (0.72, 0.24, 0.42), (0.90, 0.44, 0.29)]
        self.swing_out = 0.0                 # sideways bulge of the swing path (m, outward)
        self.ankle = [(0.0, -30.0), (0.5, -12.0), (0.85, 6.0), (1.0, 6.0)]  # shin-relative, in the air
        self.swing_pitch = None              # instead of `ankle`: world pitch of the foot in the air,
                                             # [(part of swing, deg)], for feet that skim the ground
        self.blend = (0.22, 0.2)             # part of the swing spent leaving / regaining the ground attitude
        self.knee = None                     # optional knee direction (pelvis space)
        # pelvis
        self.hip = (0.0, 0.03, 0.905)
        self.bob = 0.035                     # half height of the vertical bounce
        self.bob_at = 0.05                   # phase of the LOW point (None: mid-stance)
        self.sway = 0.012                    # sideways shift toward the stance leg
        self.pitch = 14.0
        self.yaw0 = 0.0
        self.yaw = 9.0                       # pelvis turns so the swinging hip leads
        self.roll_amp = 4.0                  # pelvis drops on the swing side
        self.surge = 0.0                     # fore-aft pelvis oscillation (m)
        # spine / head
        self.bend = 12.0
        self.twist = 18.0                    # chest counter-rotation against the pelvis
        self.twist0 = 0.0
        self.nod = 0.0
        self.turn = 0.0
        self.arms = None                     # fn(gait, ph, side) -> arm spec
        for k, v in kw.items():
            if not hasattr(self, k):
                raise TypeError(f"Gait has no parameter {k!r}")
            setattr(self, k, v)

    # ---- feet ----------------------------------------------------------------------------
    def footprint(self, side, along):
        bx, by = self.base[side]
        return bx + self.travel[0] * along, by + self.travel[1] * along

    def stance_spec(self, rig, side, u):
        """Leg on the ground at stance fraction u (0 = contact, 1 = lift-off)."""
        length = self.duty * self.frames / FPS * self.speed
        along = self.mid[side] + (0.5 - u) * length
        x, y = self.footprint(side, along)
        return Plant(x, y, yaw=self.foot_yaw, out=self.toe_out, roll=track(self.roll, u), knee=self.knee)

    def leg(self, rig, side, ph):
        d = self.duty
        if ph < d:
            return self.stance_spec(rig, side, ph / d)
        s = (ph - d) / (1.0 - d)
        sign = 1.0 if side == "L" else -1.0
        t_dir = Vector((self.travel[0], self.travel[1], 0.0))
        out_dir = Vector((sign, 0.0, 0.0))
        off = rig.plant_to_ik(self.stance_spec(rig, side, 1.0), side)
        on = rig.plant_to_ik(self.stance_spec(rig, side, 0.0), side)
        eps = 1e-3
        off_b = rig.plant_to_ik(self.stance_spec(rig, side, 1.0 - eps), side)
        on_b = rig.plant_to_ik(self.stance_spec(rig, side, eps), side)
        # end tangents in units per swing: continue the ground speed
        k = (1.0 - d) / d
        m_first = (Vector(off.pos) - Vector(off_b.pos)) / eps * k
        m_last = (Vector(on_b.pos) - Vector(on.pos)) / eps * k
        bx, by = self.base[side]
        knots = [(0.0, Vector(off.pos))]
        swing = self.swing[side] if isinstance(self.swing, dict) else self.swing
        for ks, along, height in swing:
            bulge = self.swing_out * math.sin(math.pi * ks)
            knots.append((ks, Vector((bx, by, height)) + t_dir * along + out_dir * bulge))
        knots.append((1.0, Vector(on.pos)))
        pos = hermite(knots, s, m_first, m_last)
        pos.z = max(pos.z, 0.062)
        if self.swing_pitch is not None:
            pitch = track([(0.0, off.pitch)] + list(self.swing_pitch) + [(1.0, on.pitch)], s)
            toe = track([(0.0, max(0.0, -off.pitch)), (0.35, 0.0), (0.65, 0.0), (1.0, max(0.0, -on.pitch))], s)
            clear = 0.03 * smooth(min(s, 1.0 - s) / 0.12)
            need = (rig.ball_h + clear + rig.ab_len * math.sin(rig.ab_ang - math.radians(pitch))
                    + max(0.0, 0.08 * math.sin(math.radians(-pitch - toe))))
            pos.z = max(pos.z, need)
            return LegIK(pos=tuple(pos), pitch=pitch, yaw=on.yaw, toe=toe, knee=self.knee)
        air = LegIK(pos=tuple(pos), ankle=track(self.ankle, s), knee=self.knee)
        b0, b1 = self.blend
        if s < b0:
            toe = max(0.0, -off.pitch)
            hold = LegIK(pos=tuple(pos), pitch=off.pitch, yaw=off.yaw, toe=toe, knee=self.knee)
            return Mix(hold, air, smooth(s / b0))
        if s > 1.0 - b1:
            hold = LegIK(pos=tuple(pos), pitch=on.pitch, yaw=on.yaw, knee=self.knee)
            return Mix(air, hold, smooth((s - (1.0 - b1)) / b1))
        return air

    # ---- whole body -----------------------------------------------------------------------
    def controls(self, rig, t):
        ph = (t / self.frames) % 1.0
        d = self.duty
        low = self.bob_at if self.bob_at is not None else d * 0.5
        hx, hy, hz = self.hip
        yaw_wave = wave(ph)                         # +1 at left contact: left leg is forward
        c = dict(
            hip=(hx + self.sway * wave(ph, d * 0.5),
                 hy + self.surge * wave(ph * 2.0, low * 2.0 + 0.25),
                 hz - self.bob * wave(ph * 2.0, low * 2.0)),
            pitch=self.pitch,
            yaw=self.yaw0 - self.yaw * yaw_wave,
            roll=-self.roll_amp * wave(ph, d * 0.5 + 0.04),
            bend=self.bend,
            twist=self.twist0 + self.twist * yaw_wave,
            side=self.roll_amp * 0.8 * wave(ph, d * 0.5 + 0.04),
            nod=self.nod, turn=self.turn, gaze=1.0, clamp=0.0,
        )
        c["legL"] = self.leg(rig, "L", ph)
        c["legR"] = self.leg(rig, "R", (ph + 0.5) % 1.0)
        arms = self.arms or pump
        c["armL"] = arms(self, ph, "L")
        c["armR"] = arms(self, ph, "R")
        return c


def pump(gait, ph, side, fwd=(-8.0, 52.0), elbow=(92.0, 16.0), out=(10.0, -4.0), twist=(30.0, 12.0),
         lag=0.03, grip=0.75):
    """Running arm swing, opposite to the leg on the same side. Each pair is (centre, amplitude)."""
    lead = ph if side == "L" else (ph + 0.5) % 1.0
    sw = -wave(lead, lag)                       # -1 = arm back (its own leg is forward), +1 = front
    return ArmFK(fwd=fwd[0] + fwd[1] * sw, elbow=elbow[0] + elbow[1] * sw, out=out[0] + out[1] * sw,
                 twist=twist[0] + twist[1] * sw, grip=grip, thumb=0.6, flex=6.0)
