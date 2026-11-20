"""Clip: keyed controls + procedural modifiers + events, sampled into Poses; plus diagnostics."""
import math

from mathutils import Vector

from .controls import DEFAULTS, mirror_controls
from .curves import EASE, Channel

FPS = 30


class E:
    """A key value with its own easing: clip.key(10, pitch=E(40, "out"))."""

    def __init__(self, value, ease):
        self.value, self.ease = value, ease


class Clip:
    """One animation of `frames` frames (frame 0..frames inclusive).

    key(frame, base, ease, **controls)  key some controls (see controls.py for their meaning).
        `hip` may be keyed whole or per axis with hx / hy / hz.
    mod(fn)        fn(t, c) adjusts the interpolated control dict `c` in place at time t.
    event(name, frame)
    """

    def __init__(self, name, frames, *, loop=False, ball="none", speed=None, notes="", tier=1):
        self.name = name
        self.frames = frames
        self.loop = loop
        self.ball = ball                 # "hand" | "tuck" | "none"
        self.ball_frames = None          # (first, last) frames the ball is attached; None = all
        self.speed = speed               # locomotion only: m/s at which planted feet do not slide
        self.velocity = (0.0, 0.0)       # world (x, y) velocity of the root that `speed` stands for
        self.notes = notes
        self.tier = tier
        self.events = {}
        self.channels = {}
        self.mods = []
        self.source = None               # function t -> controls, for procedural / derived clips
        self.key_frame = None            # frame shown on the overview sheet
        self.prop = None                 # preview-only ball: fn(frame, pose) -> 4x4 | None
        self.views = None                # optional override of the preview azimuths
        self.extra = {}                  # extra manifest fields
        self._anchored = False

    # ---- authoring -----------------------------------------------------------------------
    def key(self, frame, base=None, ease="auto", **controls):
        values = dict(base or {})
        values.update(controls)
        if "hip" in values:
            hip = values.pop("hip")
            e = hip.ease if isinstance(hip, E) else None
            hip = hip.value if isinstance(hip, E) else hip
            for axis, v in zip(("hx", "hy", "hz"), hip):
                values.setdefault(axis, E(v, e) if e else v)
        for name, value in values.items():
            this_ease = ease
            if isinstance(value, E):
                value, this_ease = value.value, value.ease
            if this_ease != "auto" and this_ease not in EASE:
                raise KeyError(f"unknown ease {this_ease!r}")
            if name in ("hx", "hy", "hz"):
                default = DEFAULTS["hip"]["xyz".index(name[1])]
            elif name in DEFAULTS:
                default = DEFAULTS[name]
            else:
                raise KeyError(f"{self.name}: unknown control {name!r}")
            self.channels.setdefault(name, Channel(default)).set(frame, value, this_ease)
        return self

    def mod(self, fn):
        self.mods.append(fn)
        return self

    def event(self, name, frame):
        self.events[name] = int(frame)
        return self

    def close_loop(self):
        """Make every keyed channel end where it starts (loops only)."""
        for ch in self.channels.values():
            if ch.frames and ch.frames[0] == 0 and ch.frames[-1] != self.frames:
                ch.set(self.frames, ch.keys[0][1], "auto")

    def anchor_start(self):
        """A control first keyed after frame 0 starts from its default, not from that later key."""
        for ch in self.channels.values():
            if ch.frames and ch.frames[0] > 0:
                ch.set(0, ch.default, "auto")

    # ---- evaluation ----------------------------------------------------------------------
    def controls(self, t):
        period = self.frames if self.loop else None
        if not self._anchored:
            self.anchor_start()
            self._anchored = True
        if self.source is not None:
            c = dict(DEFAULTS)
            c.update(self.source(t))
        else:
            c = dict(DEFAULTS)
            hip = list(DEFAULTS["hip"])
            for name, ch in self.channels.items():
                v = ch.at(t, period)
                if name in ("hx", "hy", "hz"):
                    hip["xyz".index(name[1])] = v
                else:
                    c[name] = v
            c["hip"] = tuple(hip)
        for fn in self.mods:
            fn(t, c)
        return c

    def sample(self, rig):
        if self.loop:
            self.close_loop()
        poses = [rig.solve(self.controls(float(f))) for f in range(self.frames + 1)]
        self.loop_gap = 0.0
        if self.loop:
            first, last = poses[0], poses[-1]
            gap = max(min(a, 2.0 * math.pi - a) for a in
                      (first.q[n].rotation_difference(last.q[n]).angle for n in first.q))
            gap = max(gap, max((first.loc[n] - last.loc[n]).length for n in first.loc) * 10.0)
            self.loop_gap = gap
            poses[-1] = first.copy()
        return poses

    # ---- manifest ------------------------------------------------------------------------
    def manifest(self):
        entry = {"name": self.name, "frames": self.frames, "loop": self.loop}
        if self.speed is not None:
            entry["speed"] = self.speed
            entry["direction"] = [round(self.velocity[0] / self.speed, 3), round(self.velocity[1] / self.speed, 3)]
        entry["ball"] = self.ball
        if self.ball_frames is not None:
            entry["ball_frames"] = list(self.ball_frames)
        entry["events"] = dict(sorted(self.events.items(), key=lambda kv: kv[1]))
        entry.update(self.extra)
        entry["notes"] = self.notes
        return entry


def derived(name, source_clip, fn, **overrides):
    """A clip whose controls are a function of another clip's: fn(t, source_clip) -> controls."""
    clip = Clip(name, overrides.pop("frames", source_clip.frames), loop=overrides.pop("loop", source_clip.loop),
                ball=overrides.pop("ball", source_clip.ball), speed=overrides.pop("speed", source_clip.speed),
                notes=overrides.pop("notes", source_clip.notes), tier=overrides.pop("tier", source_clip.tier))
    clip.source = lambda t: fn(t, source_clip)
    clip.velocity = source_clip.velocity
    return clip


def mirrored(name, source_clip, shift=0.0, **overrides):
    """Left/right mirror image of a clip, optionally shifted in time (for keeping loop phase)."""
    period = source_clip.frames

    def fn(t, src):
        tt = t + shift
        if src.loop:
            tt = tt % period
        return mirror_controls(src.controls(tt))

    clip = derived(name, source_clip, fn, **overrides)
    clip.velocity = (-source_clip.velocity[0], source_clip.velocity[1])
    clip.events = {k: int(round((v - shift) % period)) if source_clip.loop else v for k, v in source_clip.events.items()}
    return clip


# --------------------------------------------------------------------------------------------
# Diagnostics: numbers that back up what the contact sheets show.
# --------------------------------------------------------------------------------------------
def report(clip, rig, poses):
    """Return (lines, problems) describing ground contact, sliding, reach and pops of a clip."""
    lines, problems = [], []
    sk = rig.skel
    n = len(poses)

    # IK targets out of reach
    reach = [(f, w) for f, p in enumerate(poses) for w in p.warn]
    if reach:
        problems.append(f"IK out of reach on {len({f for f, _ in reach})} frames, e.g. f{reach[0][0]}: {reach[0][1]}")

    # lowest body point per frame
    worst = (1e9, 0, None)
    for f, p in enumerate(poses):
        z, bone = rig.lowest(p)
        if z < worst[0]:
            worst = (z, f, bone)
    lines.append(f"lowest point {worst[0] * 100:+.1f} cm (f{worst[1]}, {worst[2]})")
    if worst[0] < -0.012:
        problems.append(f"sinks {-worst[0] * 100:.1f} cm into the ground at f{worst[1]} ({worst[2]})")

    # pelvis excursion
    far = max((math.hypot(p.head("pelvis").x, p.head("pelvis").y), f) for f, p in enumerate(poses))
    zs = [p.head("pelvis").z for p in poses]
    lines.append(f"pelvis: max horizontal offset {far[0]:.2f} m (f{far[1]}), height {min(zs):.2f}..{max(zs):.2f} m")
    if far[0] > 0.45:
        problems.append(f"pelvis strays {far[0]:.2f} m from the root at f{far[1]}")

    # root must not move
    if any(p.loc["root"].length > 1e-9 or p.q["root"].angle > 1e-9 for p in poses):
        problems.append("root moves")

    # loop closure
    if clip.loop and clip.loop_gap > math.radians(0.5):
        problems.append(f"loop does not close by itself (gap {math.degrees(clip.loop_gap):.1f} deg)")

    # pops: largest per-frame change of any bone's world orientation
    pop = (0.0, 0, None)
    for f in range(1, n):
        for b in sk.names:
            if b.startswith("ball_"):
                continue
            a = poses[f - 1].world(b).to_quaternion().rotation_difference(poses[f].world(b).to_quaternion()).angle
            a = min(a, 2.0 * math.pi - a)
            if a > pop[0]:
                pop = (a, f, b)
    lines.append(f"fastest bone: {math.degrees(pop[0]):.0f} deg/frame ({pop[2]} at f{pop[1]})")
    if math.degrees(pop[0]) > 95.0:
        problems.append(f"possible pop: {pop[2]} turns {math.degrees(pop[0]):.0f} deg between f{pop[1] - 1} and f{pop[1]}")

    # foot sliding while planted: compare each planted foot's motion with the ground's motion
    vx, vy = clip.velocity
    ground_step = Vector((-vx / FPS, -vy / FPS, 0.0))           # how the ground moves per frame, root space
    slide_max, slide_at, planted_frames = 0.0, None, {"L": [], "R": []}
    for side, suf in (("L", "_l"), ("R", "_r")):
        heel_rest = Vector((0.105 if side == "L" else -0.105, 0.055, 0.03))
        for f in range(1, n):
            a, b = poses[f - 1], poses[f]
            pts = []
            for pose in (a, b):
                ball = pose.head("ball" + suf)
                heel = pose.delta("foot" + suf) @ heel_rest
                pts.append((ball, heel))
            down_a = min(pts[0][0].z - 0.025, pts[0][1].z - 0.03)
            down_b = min(pts[1][0].z - 0.025, pts[1][1].z - 0.03)
            if down_a < 0.006 and down_b < 0.006:
                planted_frames[side].append(f)
                errs = []
                for k in (0, 1):
                    if max(pts[0][k].z, pts[1][k].z) - (0.025 if k == 0 else 0.03) < 0.008:
                        move = pts[1][k] - pts[0][k] - ground_step
                        errs.append(math.hypot(move.x, move.y))
                if errs and min(errs) > slide_max:
                    slide_max, slide_at = min(errs), (side, f)
    spans = {s: _spans(fr) for s, fr in planted_frames.items()}
    lines.append(f"feet on ground: L {spans['L'] or '-'}  R {spans['R'] or '-'}; "
                 f"max slide {slide_max * 100:.1f} cm/frame" + (f" ({slide_at[0]} f{slide_at[1]})" if slide_at else ""))
    if clip.speed is not None and slide_max > 0.03:
        problems.append(f"planted foot slides {slide_max * 100:.1f} cm/frame at {slide_at}")
    return lines, problems


def _spans(frames):
    if not frames:
        return ""
    out, start, prev = [], frames[0], frames[0]
    for f in frames[1:]:
        if f != prev + 1:
            out.append((start - 1, prev))
            start = f
        prev = f
    out.append((start - 1, prev))
    return " ".join(f"{a}-{b}" for a, b in out)
