"""The plan curve the whole bowl is swept around: a rounded rectangle.

The reference curve (offset d = 0) is the field-side face of the padded wall. It is parametrised
by arc length `s`, counter-clockwise seen from above, starting in the middle of the -Y side:

    S (right half) -> SE corner -> E end -> NE corner -> N side -> NW corner -> W end
    -> SW corner -> S (left half)

A *station* is a value of `s`; `frame(s)` gives the point on the reference curve and the outward
unit normal there, and `point(s, d)` moves `d` metres outward along that normal. Lines of constant
`s` are perpendicular to the wall on the straights and radial in the corners, so every aisle,
column line and roof truss is simply a station.

Seen by a spectator on the field looking outward, increasing `s` runs to the LEFT.
"""
import math


class Ring:
    def __init__(self, hx, hy, r0, arc_step_deg=6.0):
        self.hx, self.hy, self.r0 = hx, hy, r0
        self.a = hx - r0                       # half length of the N/S straights
        self.b = hy - r0                       # half length of the E/W straights
        q = 0.5 * math.pi * r0                 # quarter arc length at d = 0
        a, b = self.a, self.b
        # (kind, s0, s1, data)
        self.sections = []
        s = 0.0

        def add(kind, length, data, name):
            nonlocal s
            self.sections.append(dict(kind=kind, s0=s, s1=s + length, data=data, name=name))
            s += length

        add("line", a, ((0.0, -hy), (1.0, 0.0), (0.0, -1.0)), "S1")       # start, dir, normal
        add("arc", q, ((a, -b), -0.5 * math.pi), "SE")                    # centre, start angle
        add("line", 2 * b, ((hx, -b), (0.0, 1.0), (1.0, 0.0)), "E")
        add("arc", q, ((a, b), 0.0), "NE")
        add("line", 2 * a, ((a, hy), (-1.0, 0.0), (0.0, 1.0)), "N")
        add("arc", q, ((-a, b), 0.5 * math.pi), "NW")
        add("line", 2 * b, ((-hx, b), (0.0, -1.0), (-1.0, 0.0)), "W")
        add("arc", q, ((-a, -b), math.pi), "SW")
        add("line", a, ((-a, -hy), (1.0, 0.0), (0.0, -1.0)), "S2")
        self.length = s
        self.by_name = {sec["name"]: sec for sec in self.sections}
        self.arc_step = math.radians(arc_step_deg) * r0   # in units of s

    # ---- lookup ---------------------------------------------------------------------------
    def wrap(self, s):
        return s % self.length

    def section(self, s):
        s = self.wrap(s)
        for sec in self.sections:
            if s < sec["s1"] - 1e-9:
                return sec
        return self.sections[-1]

    def frame(self, s):
        """(px, py, nx, ny) on the reference curve."""
        sw = self.wrap(s)
        sec = self.section(sw)
        t = sw - sec["s0"]
        if sec["kind"] == "line":
            (x0, y0), (dx, dy), (nx, ny) = sec["data"]
            return x0 + dx * t, y0 + dy * t, nx, ny
        (cx, cy), a0 = sec["data"]
        ang = a0 + t / self.r0
        c, sn = math.cos(ang), math.sin(ang)
        return cx + self.r0 * c, cy + self.r0 * sn, c, sn

    def point(self, s, d=0.0):
        px, py, nx, ny = self.frame(s)
        return px + nx * d, py + ny * d

    def p3(self, s, d, z):
        px, py, nx, ny = self.frame(s)
        return (px + nx * d, py + ny * d, z)

    def normal(self, s):
        return self.frame(s)[2:]

    def tangent(self, s):
        _, _, nx, ny = self.frame(s)
        return -ny, nx

    def yaw_facing_field(self, s):
        """Yaw about +Z that turns a figure facing -Y so it faces the field."""
        _, _, nx, ny = self.frame(s)
        return math.atan2(-nx, ny)

    # ---- named stations --------------------------------------------------------------------
    def s_north(self, x):
        return self.by_name["N"]["s0"] + (self.a - x)

    def s_south(self, x):
        return x if x >= 0 else self.length + x

    def s_east(self, y):
        return self.by_name["E"]["s0"] + (y + self.b)

    def s_west(self, y):
        return self.by_name["W"]["s0"] + (self.b - y)

    def s_corner(self, name, deg):
        """Station `deg` degrees (0..90) into corner SE/NE/NW/SW, counted counter-clockwise."""
        sec = self.by_name[name]
        return sec["s0"] + math.radians(deg) * self.r0

    # ---- measuring -------------------------------------------------------------------------
    def scale(self, s, d):
        """d(arc length at offset d) / ds at station s."""
        sec = self.section(s)
        return 1.0 if sec["kind"] == "line" else (self.r0 + d) / self.r0

    def arclen(self, s0, s1, d):
        """Length of the offset curve between stations s0 <= s1 (s1 may exceed the loop length)."""
        total = 0.0
        for a, b in self._pieces(s0, s1):
            total += (b - a) * self.scale(0.5 * (a + b), d)
        return total

    def s_at_length(self, s0, dist, d):
        """Station reached after walking `dist` metres along the offset-d curve from s0."""
        s = s0
        remaining = dist
        guard = 0
        while remaining > 1e-9 and guard < 64:
            guard += 1
            sec = self.section(s + 1e-7)
            k = self.scale(s + 1e-7, d)
            base = math.floor((s + 1e-7) / self.length) * self.length
            room = (base + sec["s1"] - s) * k
            if remaining <= room:
                return s + remaining / k
            remaining -= room
            s = base + sec["s1"]
        return s

    def _pieces(self, s0, s1):
        """Split [s0, s1] at section joints."""
        out = []
        cuts = [s0]
        n0 = math.floor(s0 / self.length)
        n1 = math.floor(s1 / self.length)
        for n in range(n0, n1 + 1):
            for sec in self.sections:
                j = n * self.length + sec["s1"]
                if s0 + 1e-9 < j < s1 - 1e-9:
                    cuts.append(j)
        cuts.append(s1)
        cuts.sort()
        for a, b in zip(cuts[:-1], cuts[1:]):
            if b - a > 1e-9:
                out.append((a, b))
        return out

    def cuts(self, s0, s1, extra=(), max_step=None):
        """Sorted stations covering [s0, s1]: the end points, every section joint, the regular
        facet stations inside corners, any `extra` stations that fall in range, and (optionally)
        extra subdivisions so no straight piece is longer than `max_step`."""
        pts = {round(s0, 6), round(s1, 6)}
        n0 = math.floor(s0 / self.length)
        n1 = math.floor(s1 / self.length)
        for n in range(n0, n1 + 1):
            base = n * self.length
            for sec in self.sections:
                for j in (sec["s0"], sec["s1"]):
                    v = base + j
                    if s0 - 1e-9 <= v <= s1 + 1e-9:
                        pts.add(round(v, 6))
                if sec["kind"] == "arc":
                    count = max(1, int(round((sec["s1"] - sec["s0"]) / self.arc_step)))
                    for i in range(1, count):
                        v = base + sec["s0"] + (sec["s1"] - sec["s0"]) * i / count
                        if s0 + 1e-9 < v < s1 - 1e-9:
                            pts.add(round(v, 6))
        for e in extra:
            for n in range(n0 - 1, n1 + 2):
                v = e % self.length + n * self.length
                if s0 + 1e-9 < v < s1 - 1e-9:
                    pts.add(round(v, 6))
        out = sorted(pts)
        # merge stations closer than 1 mm
        merged = [out[0]]
        for v in out[1:]:
            if v - merged[-1] > 1e-3:
                merged.append(v)
            elif abs(v - s1) < 1e-6:
                merged[-1] = v
        if max_step:
            dense = [merged[0]]
            for v in merged[1:]:
                a = dense[-1]
                gap = v - a
                k = max(1, int(math.ceil(gap / max_step - 1e-9)))
                for i in range(1, k):
                    dense.append(a + gap * i / k)
                dense.append(v)
            merged = dense
        return merged

    def theta(self, s):
        """Total angle (radians) the curve has turned through between station 0 and s."""
        n = math.floor(s / self.length)
        sw = s - n * self.length
        th = n * 2.0 * math.pi
        for sec in self.sections:
            if sec["kind"] != "arc":
                continue
            if sw >= sec["s1"]:
                th += 0.5 * math.pi
            elif sw > sec["s0"]:
                th += (sw - sec["s0"]) / self.r0
        return th

    def cum_length(self, s, d):
        """Arc length along the offset-d curve from station 0 to s (s may be negative or exceed
        one loop). Offsetting a curve by d lengthens it by d times the angle turned."""
        return s + d * self.theta(s)

    def ds(self, s, metres, d):
        """Station increment that spans `metres` along the offset-d curve near s."""
        return metres / self.scale(s, d)
