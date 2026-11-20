"""Stepped seating tiers swept around the ring, and the seat positions they imply.

A tier is a grid: rows (stepping outward and upward) by columns (station intervals along the
ring). A column is either a seating block (`seat`, material SeatA/SeatB), an aisle (`aisle`,
concrete half-height steps) or a `wall` strip reserved for an end wall. Rectangular `Void`s remove
rows from a span of columns (vomitories, the players' tunnel).

Geometry and seats come from the same grid, so spectators sit exactly on the steps.
"""
import math

from .meshkit import frame_axes

SEAT_INSET = 0.30        # seat/feet point, metres behind the front edge of the step
SEAT_PITCH = 0.56        # minimum spacing along a row (effective pitch 0.56 .. ~0.60)
SEAT_MARGIN = 0.12       # kept clear at each end of a seating run


class Column:
    __slots__ = ("s0", "s1", "kind", "mat", "block", "aisle")

    def __init__(self, s0, s1, kind, mat=None, block=-1, aisle=None):
        self.s0, self.s1, self.kind, self.mat, self.block, self.aisle = s0, s1, kind, mat, block, aisle

    def __repr__(self):
        return f"Col({self.s0:.2f}..{self.s1:.2f} {self.kind} {self.mat})"


class Void:
    """Rows i0..i1 removed from columns k0..k1."""

    def __init__(self, i0, i1, k0, k1, floor_z, kind="hole"):
        self.i0, self.i1, self.k0, self.k1, self.floor_z, self.kind = i0, i1, k0, k1, floor_z, kind


def row_heights(z0, rows, riser0, riser_inc):
    """Tread heights for rows 0..rows (the last entry is the level behind the top row). The rake
    steepens toward the back, as real bowls do."""
    zs = [z0]
    for i in range(1, rows + 1):
        zs.append(zs[-1] + riser0 + riser_inc * i)
    return zs


def layout_columns(ring, s0, s1, aisles, d_ref, first=0, aisle_w=1.2, flanks=None, flank_w=0.8,
                   cap0=0.0, cap1=0.0, mats=("SeatA", "SeatB")):
    """Partition [s0, s1] into columns.

    aisles  stations of aisle centre lines (an aisle on s0 or s1 is clipped to its inner half)
    flanks  stations of aisles that get a narrow seat column each side (a void may claim them);
            a dict {station: width} gives each its own width, otherwise all use flank_w
    cap0/1  width in metres of a `wall` column at the start / end
    first   0 or 1: material index of the first block; blocks alternate at every aisle
    """
    if isinstance(flanks, dict):                       # {aisle station: flank width}
        flank_widths = {round(a, 4): w for a, w in flanks.items()}
    else:
        flank_widths = {round(a, 4): flank_w for a in (flanks or ())}

    def ws(s, w, side):
        return w / ring.scale(s + side * 1e-4, d_ref)

    reserved = []                                   # (a, b, kind, aisle_station)
    if cap0 > 0:
        reserved.append((s0, s0 + ws(s0, cap0, +1), "wall", None))
    for a in sorted(aisles):
        lo = max(s0, a - ws(a, aisle_w / 2, -1))
        hi = min(s1, a + ws(a, aisle_w / 2, +1))
        if hi - lo > 1e-6:
            reserved.append((lo, hi, "aisle", a))
    if cap1 > 0:
        reserved.append((s1 - ws(s1, cap1, -1), s1, "wall", None))
    reserved.sort()

    cols = []
    block = 0
    cursor = s0
    prev_aisle = None

    def add_block(a, b, left_aisle, right_aisle):
        nonlocal block
        if b - a < 1e-6:
            return
        mat = mats[(first + block) % 2]
        lw = flank_widths.get(round(left_aisle, 4)) if left_aisle is not None else None
        rw = flank_widths.get(round(right_aisle, 4)) if right_aisle is not None else None
        lf = ws(a, lw, +1) if lw else 0.0
        rf = ws(b, rw, -1) if rw else 0.0
        if lf + rf > (b - a) - 1e-3:
            lf = rf = 0.0
        if lf:
            cols.append(Column(a, a + lf, "seat", mat, block))
        cols.append(Column(a + lf, b - rf, "seat", mat, block))
        if rf:
            cols.append(Column(b - rf, b, "seat", mat, block))
        block += 1

    for (a, b, kind, st) in reserved:
        if a - cursor > 1e-6:
            add_block(cursor, a, prev_aisle, st if kind == "aisle" else None)
        cols.append(Column(a, b, kind, "Concrete", -1, st))
        cursor = b
        prev_aisle = st if kind == "aisle" else None
    if s1 - cursor > 1e-6:
        add_block(cursor, s1, prev_aisle, None)
    return cols


class Tier:
    def __init__(self, ring, name, d0, zs, tread, cols, voids=(), riser0_bottom=None,
                 back_riser=True, seat_inset=SEAT_INSET, stations=()):
        self.ring, self.name = ring, name
        self.d0, self.zs, self.tread = d0, zs, tread
        self.rows = len(zs) - 1
        self.cols = cols
        self.voids = list(voids)
        self.riser0_bottom = riser0_bottom
        self.back_riser = back_riser
        self.seat_inset = seat_inset
        self.stations = list(stations)      # extra stations every strip is cut at (shared with
        #                                     neighbouring geometry so edges meet vertex to vertex)
        self.d1 = d0 + self.rows * tread
        self._vmap = {}
        for v in self.voids:
            for i in range(v.i0, v.i1 + 1):
                for k in range(v.k0, v.k1 + 1):
                    self._vmap[(i, k)] = v

    # ---- grid queries ----------------------------------------------------------------------
    def d(self, i):
        return self.d0 + i * self.tread

    def half(self, i):
        """Level of the raised back half-step of an aisle in row i."""
        return 0.5 * (self.zs[i] + self.zs[i + 1])

    def kind(self, i, k):
        if k < 0 or k >= len(self.cols) or i < 0 or i >= self.rows:
            return None
        if (i, k) in self._vmap:
            return "void"
        return self.cols[k].kind

    def col_at(self, s):
        """Index of the column containing station s (nearest if on a boundary)."""
        best, bd = 0, 1e9
        for k, c in enumerate(self.cols):
            if c.s0 - 1e-6 <= s <= c.s1 + 1e-6:
                mid = 0.5 * (c.s0 + c.s1)
                if abs(mid - s) < bd:
                    best, bd = k, abs(mid - s)
        return best

    def aisle_col(self, station):
        for k, c in enumerate(self.cols):
            if c.kind == "aisle" and c.aisle is not None and abs(c.aisle - station) < 1e-3:
                return k
        raise KeyError(f"{self.name}: no aisle at station {station}")

    def runs(self, i):
        """Maximal runs of adjacent columns sharing a surface in row i: (k_first, k_last)."""
        out = []
        k = 0
        n = len(self.cols)
        while k < n:
            kd = self.kind(i, k)
            if kd in ("void", "wall"):
                k += 1
                continue
            j = k
            while (j + 1 < n and self.kind(i, j + 1) == kd
                   and self.cols[j + 1].mat == self.cols[k].mat
                   and abs(self.cols[j + 1].s0 - self.cols[j].s1) < 1e-6):
                j += 1
            out.append((k, j))
            k = j + 1
        return out

    # ---- geometry --------------------------------------------------------------------------
    def build(self, mb):
        ring = self.ring
        t = self.tread
        zs = self.zs
        prof = [0.0]                                   # unrolled profile length at each row start
        for i in range(self.rows):
            rise = zs[i] - (zs[i - 1] if i > 0 else (self.riser0_bottom if self.riser0_bottom is not None else zs[0]))
            prof.append(prof[-1] + rise + t)
        sc = mb.uv_scale

        def strip(stations, a, b, mat, va=None, vb=None, d_uv=None):
            (da, za), (db, zb) = a, b
            if abs(da - db) < 1e-9 and abs(za - zb) < 1e-9:
                return
            pa = [ring.p3(s, da, za) for s in stations]
            pb = [ring.p3(s, db, zb) for s in stations]
            if va is None:
                uvs = None
            else:
                us = [-ring.cum_length(s, d_uv) * sc for s in stations]
            for j in range(len(stations) - 1):
                uv = None
                if va is not None:
                    uv = ((us[j], va), (us[j], vb), (us[j + 1], vb), (us[j + 1], va))
                mb.quad(pa[j], pb[j], pb[j + 1], pa[j + 1], mat, uv, smooth=True)

        for i in range(self.rows):
            d_i, d_n = self.d(i), self.d(i + 1)
            z = zs[i]
            for (k0, k1) in self.runs(i):
                c0, c1 = self.cols[k0], self.cols[k1]
                st = ring.cuts(c0.s0, c1.s1, self.stations)
                if c0.kind == "seat":
                    zb = zs[i - 1] if i > 0 else self.riser0_bottom
                    v0 = prof[i] * sc
                    d_uv = d_i + self.seat_inset
                    if zb is not None and z - zb > 1e-6:
                        v1 = v0 + (z - zb) * sc
                        strip(st, (d_i, zb), (d_i, z), c0.mat, v0, v1, d_uv)
                    else:
                        v1 = v0
                    strip(st, (d_i, z), (d_n, z), c0.mat, v1, v1 + t * sc, d_uv)
                else:                                   # aisle: two half-height steps per row
                    zh = self.half(i)
                    zb = self.half(i - 1) if i > 0 else self.riser0_bottom
                    dm = d_i + 0.5 * t
                    if zb is not None and z - zb > 1e-6:
                        strip(st, (d_i, zb), (d_i, z), "Concrete")
                    strip(st, (d_i, z), (dm, z), "Concrete")
                    strip(st, (dm, z), (dm, zh), "Concrete")
                    strip(st, (dm, zh), (d_n, zh), "Concrete")
                    # cheeks of the raised half-step where it meets a seating block
                    if self.kind(i, k0 - 1) == "seat":
                        self._cross(mb, c0.s0, [(dm, z), (d_n, z), (d_n, zh), (dm, zh)], -1, "Concrete")
                    if self.kind(i, k1 + 1) == "seat":
                        self._cross(mb, c1.s1, [(dm, z), (d_n, z), (d_n, zh), (dm, zh)], +1, "Concrete")
        if self.back_riser:
            i = self.rows - 1
            for (k0, k1) in self.runs(i):
                c0, c1 = self.cols[k0], self.cols[k1]
                st = ring.cuts(c0.s0, c1.s1, self.stations)
                zb = zs[i] if c0.kind == "seat" else self.half(i)
                strip(st, (self.d1, zb), (self.d1, zs[self.rows]), "Concrete")
                if c0.kind == "aisle":
                    # the half-step cheek is covered by the walkway riser of the neighbours
                    pass

    def _cross(self, mb, s, pts_dz, facing, mat):
        """Polygon lying in the station plane at s; facing +1 looks toward increasing s."""
        ring = self.ring
        area = 0.0
        n = len(pts_dz)
        for a in range(n):
            (d0, z0), (d1, z1) = pts_dz[a], pts_dz[(a + 1) % n]
            area += d0 * z1 - d1 * z0
        # counter-clockwise in (d, z) faces -T
        if (area > 0) == (facing > 0):
            pts_dz = pts_dz[::-1]
        mb.poly([ring.p3(s, d, z) for d, z in pts_dz], mat)

    def local_frame(self, s, d=0.0, z=0.0):
        """Frame at a station: local X = outward normal, Y = tangent (+s), Z = up."""
        ring = self.ring
        px, py, nx, ny = ring.frame(s)
        return frame_axes((px + nx * d, py + ny * d, z), (nx, ny, 0.0), (-ny, nx, 0.0))

    # ---- seats -----------------------------------------------------------------------------
    def seats(self):
        """[(x, y, z, yaw, section)] for every seat on this tier."""
        ring = self.ring
        out = []
        for i in range(self.rows):
            d_seat = self.d(i) + self.seat_inset
            z = self.zs[i]
            for (k0, k1) in self.runs(i):
                c0, c1 = self.cols[k0], self.cols[k1]
                if c0.kind != "seat":
                    continue
                length = ring.arclen(c0.s0, c1.s1, d_seat)
                usable = length - 2 * SEAT_MARGIN
                n = int(math.floor(usable / SEAT_PITCH + 1e-9))
                if n < 1:
                    continue
                pitch = usable / n
                section = 0.0 if c0.mat == "SeatA" else 1.0
                for j in range(n):
                    s = ring.s_at_length(c0.s0, SEAT_MARGIN + (j + 0.5) * pitch, d_seat)
                    px, py, nx, ny = ring.frame(s)
                    out.append((px + nx * d_seat, py + ny * d_seat, z, math.atan2(-nx, ny), section))
        return out
