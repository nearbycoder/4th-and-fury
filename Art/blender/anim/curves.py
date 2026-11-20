"""Keyed channels: easing curves and interpolation of numbers, vectors and limb specs."""
import bisect
import math

from .controls import Mix, Spec


def _back(u, k=1.70158):
    u -= 1.0
    return 1.0 + u * u * ((k + 1.0) * u + k)


def _spring(u):
    return 1.0 - math.exp(-5.0 * u) * math.cos(u * math.pi * 2.5) * (1.0 - u)


EASE = {
    "lin": lambda u: u,
    "io": lambda u: u * u * (3.0 - 2.0 * u),                       # smooth both ends
    "io3": lambda u: u * u * u * (u * (6.0 * u - 15.0) + 10.0),    # smoother, longer holds
    "in": lambda u: u * u,                                         # slow start, fast arrival
    "in3": lambda u: u * u * u,
    "out": lambda u: 1.0 - (1.0 - u) ** 2,                         # fast start, soft arrival
    "out3": lambda u: 1.0 - (1.0 - u) ** 3,
    "back": _back,                                                 # overshoots, then settles
    "spring": _spring,
    "hold": lambda u: 1.0 if u >= 1.0 else 0.0,
}
# Does a segment with this easing reach / leave its key at rest?
_STOPS_AT_END = {"io", "io3", "out", "out3", "back", "spring", "hold"}
_STARTS_AT_REST = {"io", "io3", "in", "in3", "hold"}


def _as_list(v):
    if isinstance(v, Spec):
        return v.vec()
    if isinstance(v, (int, float)):
        return [float(v)]
    return [float(c) for c in v]


def _like(template, values):
    if isinstance(template, Spec):
        return template.with_vec(values)
    if isinstance(template, (int, float)):
        return values[0]
    return tuple(values)


def _compatible(a, b):
    if isinstance(a, Spec) or isinstance(b, Spec):
        return isinstance(a, Spec) and isinstance(b, Spec) and a.sig() == b.sig()
    return True


class Channel:
    """One control over time: keys of (frame, value, ease).

    `ease` describes how the value ARRIVES at that key from the previous one. "auto" (the
    default) is a smooth cubic through the keys with flat tangents at extremes; any name from
    EASE shapes that one segment on its own.
    """

    def __init__(self, default):
        self.default = default
        self.frames = []
        self.keys = []

    def set(self, frame, value, ease="auto"):
        i = bisect.bisect_left(self.frames, frame)
        if i < len(self.frames) and self.frames[i] == frame:
            self.keys[i] = (frame, value, ease)
        else:
            self.frames.insert(i, frame)
            self.keys.insert(i, (frame, value, ease))

    def _key(self, i, period):
        """Key i; for loops (period = clip length) indices beyond either end wrap around."""
        n = len(self.keys)
        if 0 <= i < n:
            return self.keys[i]
        if period is None or n < 3:
            return None
        # A loop stores the same value at frame 0 and frame `period`; step over that duplicate.
        if i < 0:
            f, v, e = self.keys[n - 1 + i]
            return (f - period, v, e)
        f, v, e = self.keys[i - n + 1]
        return (f + period, v, e)

    def at(self, t, period=None):
        if not self.keys:
            return self.default
        looped = period is not None and self.frames[0] == 0 and self.frames[-1] == period
        if looped and not 0 <= t <= period:
            t = t % period
        if t <= self.frames[0]:
            return self.keys[0][1]
        if t >= self.frames[-1]:
            return self.keys[-1][1]
        i = bisect.bisect_right(self.frames, t) - 1
        f0, v0, _ = self.keys[i]
        f1, v1, ease = self.keys[i + 1]
        u = (t - f0) / (f1 - f0)
        arc = getattr(v1, "arc", 0.0)
        if not _compatible(v0, v1):
            w = EASE["io" if ease == "auto" else ease](u)
            return Mix(v0, v1, w, arc)
        a, b = _as_list(v0), _as_list(v1)
        if ease != "auto":
            w = EASE[ease](u)
            out = [x + (y - x) * w for x, y in zip(a, b)]
        else:
            wrap = period if looped else None
            before, after = self._key(i - 1, wrap), self._key(i + 2, wrap)
            arrive_ease = self.keys[i][2] if (i > 0 or not looped) else self.keys[-1][2]
            m0 = self._tangent(before, (f0, a, v0), (f1, b, v1), arrive_ease in _STOPS_AT_END)
            after_ease = after[2] if after is not None else "auto"
            m1 = self._tangent((f0, a, v0), (f1, b, v1), after, after_ease in _STARTS_AT_REST, at_end=True)
            h = f1 - f0
            u2, u3 = u * u, u * u * u
            h00, h10 = 2 * u3 - 3 * u2 + 1, u3 - 2 * u2 + u
            h01, h11 = -2 * u3 + 3 * u2, u3 - u2
            out = [h00 * x + h10 * h * t0 + h01 * y + h11 * h * t1 for x, y, t0, t1 in zip(a, b, m0, m1)]
        value = _like(v1, out)
        if arc and hasattr(value, "pos"):
            p = value.pos
            value.pos = (p[0], p[1], p[2] + arc * math.sin(math.pi * u))
        elif arc and hasattr(value, "z"):
            value.z = value.z + arc * math.sin(math.pi * u)
        return value

    @staticmethod
    def _tangent(k0, k1, k2, at_rest, at_end=False):
        """Clamped Catmull-Rom tangent.

        at_end=False: tangent at k1's START key, given (k0 = raw key before | None, k1 = start,
        k2 = end).  at_end=True: tangent at the END key, given (k0 = start, k1 = end, k2 = raw key
        after | None). Raw keys are (frame, value, ease); segment keys are (frame, list, value).
        """
        if not at_end:
            raw, (f_here, here, v_here), (f_far, far, _) = k0, k1, k2
        else:
            (f_far, far, _), (f_here, here, v_here), raw = k0, k1, k2
        n = len(here)
        if at_rest or raw is None or not _compatible(raw[1], v_here):
            return [0.0] * n
        nb = _as_list(raw[1])
        if len(nb) != n:
            return [0.0] * n
        f_nb = raw[0]
        out = []
        for j in range(n):
            s_seg = (far[j] - here[j]) / (f_far - f_here)
            s_nb = (here[j] - nb[j]) / (f_here - f_nb)
            if s_seg * s_nb <= 0.0:
                out.append(0.0)
                continue
            m = (far[j] - nb[j]) / (f_far - f_nb)
            lim = 3.0 * min(abs(s_seg), abs(s_nb))
            out.append(max(-lim, min(lim, m)))
        return out
