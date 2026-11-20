"""SM_Stadium: the whole arena as one mesh.

Plan
----
A rounded-rectangle bowl (see ring.py). All the way round: padded field wall with a continuous
ad-board band, a 26-row lower bowl with vomitories part-way up, a cross-walkway and an open
concourse behind it. The players' tunnel cuts through the lower rows at the west end of the +Y
stand.

The "horseshoe" (the +Y side, both ends and most of every corner) stacks a glazed suite strip, a
24-row upper deck with vomitories, a rear wall hung with banners and a cantilevered roof on masts
and stays above that. In the middle of the +Y stand the upper deck parts around the video board,
which stands between two piers.

The -Y side stays low in front of the broadcast camera: above its concourse is an open deck, and
a 16-row tier with its own roof starts only behind y = -62 (see spec.CLEAR_*).
"""
import math

from mathutils import Matrix, Vector

from . import spec as S
from .meshkit import MeshBuilder, frame_axes, frame_z
from .ring import Ring
from .terrace import Tier, Void, layout_columns

SLOTS = ["Concrete", "ConcreteDark", "SeatA", "SeatB", "Steel", "Glass", "WallPad", "AdBoard",
         "Screen", "ScreenSmall", "Lamp", "LampHousing", "Apron", "Roof"]

# prism-local (a, b, c) -> viewer frame (x = c, y = a, z = b): extrude a (d, z) outline sideways
SIDE = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def vframe(ring, s, d=0.0, z=0.0):
    """Frame at a station as a spectator on the field sees it: X = to the right, Y = away from
    the field (outward normal), Z = up."""
    px, py, nx, ny = ring.frame(s)
    return frame_axes((px + nx * d, py + ny * d, z), (ny, -nx, 0.0), (nx, ny, 0.0))


def cross_face(mb, ring, s, pts_dz, facing, mat):
    """Polygon in the station plane at s, given as (d, z) points; facing +1 looks toward
    increasing s."""
    area = 0.0
    n = len(pts_dz)
    for a in range(n):
        (d0, z0), (d1, z1) = pts_dz[a], pts_dz[(a + 1) % n]
        area += d0 * z1 - d1 * z0
    if (area > 0) == (facing > 0):          # counter-clockwise in (d, z) faces -T
        pts_dz = pts_dz[::-1]
    mb.poly([ring.p3(s, d, z) for d, z in pts_dz], mat)


def loft(mb, ring, stations, prof, close=False, smooth=True, caps=(None, None)):
    """Sweep a (d, z) profile along the ring.

    prof: [(d, z, material)], the material applying to the segment that starts at that point
    (None leaves the segment open). The visible side of a segment is on the LEFT of its direction
    of travel when d is drawn to the right and z up -- so walk clockwise around solid material.
    """
    sc = mb.uv_scale
    n = len(prof)
    segs = n if close else n - 1
    v = [0.0]
    for j in range(segs):
        d0, z0 = prof[j][0], prof[j][1]
        d1, z1 = prof[(j + 1) % n][0], prof[(j + 1) % n][1]
        v.append(v[-1] + math.hypot(d1 - d0, z1 - z0))
    frames = [ring.frame(s) for s in stations]
    thetas = [ring.theta(s) for s in stations]
    for j in range(segs):
        d0, z0, mat = prof[j]
        d1, z1 = prof[(j + 1) % n][0], prof[(j + 1) % n][1]
        if mat is None:
            continue
        dm = 0.5 * (d0 + d1)
        us = [-(s + dm * th) * sc for s, th in zip(stations, thetas)]
        pa = [(px + nx * d0, py + ny * d0, z0) for (px, py, nx, ny) in frames]
        pb = [(px + nx * d1, py + ny * d1, z1) for (px, py, nx, ny) in frames]
        va, vb = v[j] * sc, v[j + 1] * sc
        for i in range(len(stations) - 1):
            mb.quad(pa[i], pb[i], pb[i + 1], pa[i + 1], mat,
                    ((us[i], va), (us[i], vb), (us[i + 1], vb), (us[i + 1], va)), smooth)
    pts = [(p[0], p[1]) for p in prof]
    if caps[0]:
        cross_face(mb, ring, stations[0], pts, -1, caps[0])
    if caps[1]:
        cross_face(mb, ring, stations[-1], pts, +1, caps[1])


def strip(mb, ring, stations, a, b, mat, u_of_s=None, smooth=True):
    """One profile segment a -> b. With `u_of_s` the UVs are (u_of_s(s), 0 at a .. 1 at b)."""
    (da, za), (db, zb) = a, b
    if abs(da - db) < 1e-9 and abs(za - zb) < 1e-9:
        return
    pa = [ring.p3(s, da, za) for s in stations]
    pb = [ring.p3(s, db, zb) for s in stations]
    us = [u_of_s(s) for s in stations] if u_of_s else None
    for i in range(len(stations) - 1):
        uv = None
        if us:
            uv = ((us[i], 0.0), (us[i], 1.0), (us[i + 1], 1.0), (us[i + 1], 0.0))
        mb.quad(pa[i], pb[i], pb[i + 1], pa[i + 1], mat, uv, smooth)


def stepped_slab(mb, ring, s, facing, th, segs, mat, front=True, back=True, bottom_above=None):
    """A vertical slab standing in the station plane at `s` (parapets, end walls).

    segs: [(d_a, d_b, z_bot, z_top, z_in[, material])] in order of d. The outer face lies in the
    station plane, runs the full height and looks toward `facing` (+1 = increasing s); the slab is
    `th` thick behind it and its inner face is only built above z_in (None = no inner face).
    front/back: True = end face from z_bot, a number = from that height, False = none.
    bottom_above: also build undersides for segments whose z_bot is above this height.
    """
    x0, x1 = (0.0, th) if facing > 0 else (-th, 0.0)
    outer, inner = ("x", "X") if facing > 0 else ("X", "x")

    def only(letters):
        return "".join(c for c in "xXyYzZ" if c not in letters)

    with mb.transform(vframe(ring, s)):
        n = len(segs)
        for j, seg in enumerate(segs):
            da, db, zb, zt, zi = seg[:5]
            m = seg[5] if len(seg) > 5 and seg[5] else mat
            mb.box((x0, da, zb), (x1, db, zt), m, skip=only(outer + "Z"))
            if zi is not None and zt - max(zb, zi) > 1e-6:
                mb.box((x0, da, max(zb, zi)), (x1, db, zt), m, skip=only(inner))
            if bottom_above is not None and zb > bottom_above + 1e-6:
                mb.box((x0, da, zb), (x1, db, zt), m, skip=only("z"))
            if j == 0:
                if front is not False:
                    zf = zb if front is True else max(zb, front)
                    if zt - zf > 1e-6:
                        mb.box((x0, da, zf), (x1, db, zt), m, skip=only("y"))
            else:
                pb_, pt = segs[j - 1][2], segs[j - 1][3]
                if zt > pt + 1e-6:
                    mb.box((x0, da, max(pt, zb)), (x1, db, zt), m, skip=only("y"))
                if zb < pb_ - 1e-6:
                    mb.box((x0, da, zb), (x1, db, min(pb_, zt)), m, skip=only("y"))
            if j == n - 1:
                if back is not False:
                    zk = zb if back is True else max(zb, back)
                    if zt - zk > 1e-6:
                        mb.box((x0, da, zk), (x1, db, zt), m, skip=only("Y"))
            else:
                nb, nt = segs[j + 1][2], segs[j + 1][3]
                if zt > nt + 1e-6:
                    mb.box((x0, da, max(nt, zb)), (x1, db, zt), m, skip=only("Y"))
                if zb < nb - 1e-6:
                    mb.box((x0, da, zb), (x1, db, min(nb, zt)), m, skip=only("Y"))


def aisle_index(cols, station, period):
    for k, c in enumerate(cols):
        if c.kind == "aisle" and c.aisle is not None:
            diff = (c.aisle - station) % period
            if diff < 1e-3 or period - diff < 1e-3:
                return k
    raise KeyError(f"no aisle at station {station}")


# ================================================================================================
class Stadium:
    def __init__(self):
        self.ring = R = Ring(S.WALL_HX, S.WALL_HY, S.WALL_R, S.ARC_STEP_DEG)
        self.mb = MeshBuilder(uv_scale=0.25)
        self.P = P = R.length
        a, b = R.a, R.b

        # ---- named stations -------------------------------------------------------------------
        self.hs0 = R.s_corner("SE", 90.0 - S.HS_END_DEG)      # the horseshoe: hs0 .. hs1
        self.hs1 = R.s_corner("SW", S.HS_END_DEG)
        self.gap0 = R.s_north(S.PIER_X1)                      # video-board gap in the upper deck
        self.gap1 = R.s_north(-S.PIER_X1)
        self.st0 = R.by_name["S2"]["s0"]                      # -Y tier: st0 .. st1 (wraps past P)
        self.st1 = P + R.by_name["S1"]["s1"]
        side = {"N": R.s_north, "S": R.s_south, "E": R.s_east, "W": R.s_west}[S.TUN_SIDE]
        self.tun_s = side(S.TUN_POS)                          # players' tunnel: tun0 .. tun1
        self.tun0 = self.tun_s - S.TUN_HW
        self.tun1 = self.tun_s + S.TUN_HW

        self.side_x = [-a + S.SIDE_PITCH * k for k in range(int(round(2 * a / S.SIDE_PITCH)) + 1)]
        self.end_y = [-b + S.END_PITCH * k for k in range(int(round(2 * b / S.END_PITCH)) + 1)]
        straight = []
        for x in self.side_x:
            straight += [R.s_north(x), R.s_south(x)]
        for y in self.end_y:
            straight += [R.s_east(y), R.s_west(y)]

        def corner(degs):
            return [R.s_corner(c, g) for c in ("SE", "NE", "NW", "SW") for g in degs]

        self.aisles_lower = self._uniq(straight + corner((30, 60)))
        self.aisles_upper = self._uniq(straight + corner((15, 30, 45, 60, 75)))
        self.frames = self.aisles_upper                       # structural lines (trusses, masts)

        self.hole_stations = [R.s_east(-2 * S.END_PITCH), R.s_east(0.0), R.s_east(2 * S.END_PITCH),
                              R.s_corner("NE", 45), R.s_north(5 * S.SIDE_PITCH), R.s_north(3 * S.SIDE_PITCH),
                              R.s_north(-3 * S.SIDE_PITCH), R.s_north(-5 * S.SIDE_PITCH), R.s_corner("NW", 45),
                              R.s_west(2 * S.END_PITCH), R.s_west(0.0), R.s_west(-2 * S.END_PITCH)]
        self.st_hole_x = [-4 * S.SIDE_PITCH, -2 * S.SIDE_PITCH, 0.0, 2 * S.SIDE_PITCH, 4 * S.SIDE_PITCH]
        # vomitories part-way up the lower bowl, staggered against the ones in the deck above
        self.lb_hole_stations = ([R.s_north(k * S.SIDE_PITCH) for k in (-4, -2, 0, 2, 4)]
                                 + [R.s_south(k * S.SIDE_PITCH) for k in (-4, -2, 2, 4)]
                                 + [R.s_east(k * S.END_PITCH) for k in (-1, 1)]
                                 + [R.s_west(k * S.END_PITCH) for k in (-1, 1)])

        self.tiers = []
        self.extra_stations = []          # filled by _layout(); shared by every strip and loft
        self.lights = []
        self.small_screens = []
        self.screen = None
        self.tunnel_meta = None
        self.notes = {}

    # ---- station helpers ------------------------------------------------------------------------
    @staticmethod
    def _uniq(vals):
        out = []
        for v in sorted(vals):
            if not out or v - out[-1] > 1e-4:
                out.append(v)
        return out

    def within(self, stations, s0, s1, eps=1e-6):
        """Members of a station list (taken modulo the loop) that fall inside [s0, s1]."""
        out = set()
        for st in stations:
            base = st % self.P
            n0 = math.floor((s0 - base) / self.P)
            for n in (n0, n0 + 1, n0 + 2):
                v = base + n * self.P
                if s0 - eps <= v <= s1 + eps:
                    out.add(round(v, 6))
        return sorted(out)

    def st(self, s0, s1, extra=()):
        return self.ring.cuts(s0, s1, list(self.extra_stations) + list(extra))

    def spaced(self, s0, s1, d, step):
        """Stations spaced about `step` metres apart along the offset-d curve (ends included)."""
        R = self.ring
        length = R.arclen(s0, s1, d)
        n = max(1, int(round(length / step)))
        return [R.s_at_length(s0, length * k / n, d) for k in range(n + 1)]

    # ================================================================================================
    def build(self):
        self._layout()
        self.apron()
        self.field_wall()
        self.lower_bowl()
        self.concourse()
        self.suite_band()
        self.upper_deck()
        self.south_side()
        self.end_walls()
        self.roofs()
        self.video_board()
        self.small_boards()
        self.light_banks()
        self.tunnel()
        self.dressing()
        self.extras()
        self.entrances()
        return self

    # ---- column layouts (computed first so every strip can share the same stations) ---------------
    def _layout(self):
        R, P = self.ring, self.P
        # lower bowl: the full loop
        d_ref = S.LB_D0 + 0.5 * S.LB_ROWS * S.LB_TREAD
        flanks = {h: 0.8 for h in self.lb_hole_stations}
        flanks[self.tun_s] = S.TUN_HW - S.AISLE_W / 2
        self.lb_cols = layout_columns(R, 0.0, P, self.within(self.aisles_lower, 0.0, P), d_ref,
                                      first=0, aisle_w=S.AISLE_W, flanks=flanks)

        # upper deck: two wings either side of the video board
        d_ref = S.UD_D0 + 0.5 * S.UD_ROWS * S.UD_TREAD
        cap = 0.30 * (R.r0 + d_ref) / (R.r0 + S.SHELL_D)
        holes = self.hole_stations

        def lower_mat_at(s):
            for c in self.lb_cols:
                if c.kind == "seat" and c.s0 <= s <= c.s1:
                    return c.mat
            return None

        def wing(s0, s1, cap0, cap1, probe):
            lo = s0 + (1.5 if cap0 else 0.0)
            hi = s1 - (1.5 if cap1 else 0.0)
            aisles = self.within(self.aisles_upper, lo, hi)
            for first in (0, 1):
                cols = layout_columns(R, s0, s1, aisles, d_ref, first=first, aisle_w=S.AISLE_W,
                                      flanks=self.within(holes, s0, s1), flank_w=0.8,
                                      cap0=cap if cap0 else 0.0, cap1=cap if cap1 else 0.0)
                mine = next(c.mat for c in cols if c.kind == "seat" and c.s0 <= probe <= c.s1)
                if mine != lower_mat_at(probe):
                    break
            return cols

        self.ud_cols = [wing(self.hs0, self.gap0, True, False, R.s_north(25.0)),
                        wing(self.gap1, self.hs1, False, True, R.s_north(-25.0))]

        # -Y tier
        d_ref = S.ST_D0 + 0.5 * S.ST_ROWS * S.ST_TREAD
        st_holes = self.within([R.s_south(x) for x in self.st_hole_x], self.st0, self.st1)
        aisles = self.within(self.aisles_upper, self.st0 + 1.5, self.st1 - 1.5)
        for first in (0, 1):
            cols = layout_columns(R, self.st0, self.st1, aisles, d_ref, first=first, aisle_w=S.AISLE_W,
                                  flanks=st_holes, flank_w=0.8, cap0=0.30, cap1=0.30)
            probe = P + 5.0
            mine = next(c.mat for c in cols if c.kind == "seat" and c.s0 <= probe <= c.s1)
            if mine != lower_mat_at(5.0):
                break
        self.st_cols = cols
        self.st_holes = st_holes

        ex = set()
        for cols in [self.lb_cols] + self.ud_cols + [self.st_cols]:
            for c in cols:
                ex.add(round(c.s0 % P, 6))
                ex.add(round(c.s1 % P, 6))
        for f in self.frames:
            ex.add(round(f % P, 6))
        for v in (self.hs0, self.hs1, self.gap0, self.gap1, self.st0, self.st1, self.tun0, self.tun1,
                  R.s_north(S.PIER_X0), R.s_north(-S.PIER_X0)):
            ex.add(round(v % P, 6))
        self.extra_stations = sorted(ex)

    # ---- ground ----------------------------------------------------------------------------------------
    def apron(self):
        """Track between the engine's turf rectangle and the wall, and the plaza outside."""
        R, mb = self.ring, self.mb
        tx, ty = S.TURF_HX, S.TURF_HY
        over = 0.25                                   # tuck the edge under the wall
        sc = mb.uv_scale

        def uv(p):
            return (p[0] * sc, p[1] * sc)

        prev_inner = None
        for sec in R.sections:
            stn = self.st(sec["s0"], sec["s1"])
            if sec["kind"] == "line":
                _, _, (nx, ny) = sec["data"]

                def inner(s, nx=nx, ny=ny):
                    px, py, _, _ = R.frame(s)
                    return (px, ny * ty, 0.0) if abs(ny) > 0.5 else (nx * tx, py, 0.0)
            else:
                (cx, cy), _ = sec["data"]
                corner_pt = (math.copysign(tx, cx), math.copysign(ty, cy), 0.0)

                def inner(s, c=corner_pt):
                    return c
            o0 = R.p3(stn[0], over, 0.0)
            i0 = inner(stn[0])
            if prev_inner is not None and (abs(prev_inner[0] - i0[0]) + abs(prev_inner[1] - i0[1])) > 1e-6:
                mb.face((prev_inner, o0, i0), "Apron", (uv(prev_inner), uv(o0), uv(i0)))
            for a, b in zip(stn[:-1], stn[1:]):
                ia, ib = inner(a), inner(b)
                oa, ob = R.p3(a, over, 0.0), R.p3(b, over, 0.0)
                if abs(ia[0] - ib[0]) + abs(ia[1] - ib[1]) < 1e-9:
                    mb.face((ia, oa, ob), "Apron", (uv(ia), uv(oa), uv(ob)))
                else:
                    mb.face((ia, oa, ob, ib), "Apron", (uv(ia), uv(oa), uv(ob), uv(ib)))
            prev_inner = inner(stn[-1])
        # (the loop starts and ends mid-side, so no closing wedge is needed)

        stn = self.st(0.0, self.P)
        loft(mb, R, stn, [(S.SHELL_D - 0.2, 0.0, "Apron"), (S.SHELL_D + S.PLAZA_W, 0.0, None)])

    # ---- padded wall + ad boards ------------------------------------------------------------------------
    def field_wall(self):
        R, mb = self.ring, self.mb
        s0, s1 = self.tun1, self.tun0 + self.P
        run = s1 - s0
        n = int(round(run / S.AD_LEN))
        self.notes["ad_boards"] = n
        self.notes["ad_board_len"] = run / n
        joints = [s1 - run * k / n for k in range(n + 1)]
        stn = self.st(s0, s1, joints)
        zt, t = S.WALL_H, S.WALL_T
        z0, z1 = S.AD_Z0 - 0.02, S.AD_Z1 + 0.02
        prof = [
            (0.0, 0.0, "WallPad"), (0.0, z0, "Steel"), (-S.AD_PROUD, z0, None), (-S.AD_PROUD, z1, "Steel"),
            (0.0, z1, "WallPad"), (0.0, zt - 0.10, "WallPad"), (0.03, zt - 0.03, "WallPad"),
            (0.10, zt, "WallPad"), (t - 0.10, zt, "WallPad"), (t - 0.03, zt - 0.03, "WallPad"),
            (t, zt - 0.10, "Concrete"), (t, S.LB_ZS[0] - 0.02, "Concrete"),
            (S.LB_D0 + 0.03, S.LB_ZS[0] - 0.02, None),              # legroom ledge in front of row 0
        ]
        loft(mb, R, stn, prof)
        strip(mb, R, stn, (-S.AD_PROUD, z0), (-S.AD_PROUD, z1), "AdBoard",
              u_of_s=lambda s: (s1 - s) * n / run)
        # slim frame between boards
        for j in joints[1:-1]:
            with mb.transform(vframe(R, j, -S.AD_PROUD)):
                mb.box((-0.035, -0.012, z0), (0.035, 0.0, z1), "Steel", skip="Yz")

    # ---- lower bowl ----------------------------------------------------------------------------------------
    def lower_bowl(self):
        R = self.ring
        cols = self.lb_cols
        zs = S.LB_ZS
        k = aisle_index(cols, self.tun_s, self.P)
        voids = [Void(0, S.TUN_ROWS - 1, k - 1, k + 1, 0.0, "slot")]
        i0, i1 = S.LB_HOLE_ROWS
        holes = []
        for h in self.lb_hole_stations:
            k = aisle_index(cols, h, self.P)
            holes.append(Void(i0, i1, k - 1, k + 1, 0.5 * (zs[i0 - 1] + zs[i0]), "hole"))
        tier = Tier(R, "lower", S.LB_D0, zs, S.LB_TREAD, cols, voids + holes, riser0_bottom=zs[0] - 0.05,
                    stations=self.extra_stations)
        tier.build(self.mb)
        for v in holes:
            self.hole(tier, v, portal_w=2.0, depth=3.2)
        self.lb = tier
        self.tiers.append(tier)

    # ---- walkway + open concourse (all the way round) ----------------------------------------------------
    def concourse(self):
        R, mb = self.ring, self.mb
        stn = self.st(0.0, self.P)
        wz, dz = S.WALK_Z, S.DECK_Z
        cz = S.CEIL_Z
        loft(mb, R, stn, [(S.LB_D1, wz, "Concrete"), (S.WALK_D1, wz, "ConcreteDark"),
                          (S.REC_D1, wz, "ConcreteDark"), (S.REC_D1, cz, "ConcreteDark"),
                          (S.BAND_D, cz, None)])
        # columns along the concourse mouth: on every structural line and half-way between on the straights
        col_st = set(round(f % self.P, 4) for f in self.frames)
        fr = sorted(col_st)
        for a, b in zip(fr, fr[1:] + [fr[0] + self.P]):
            if R.section(0.5 * (a + b))["kind"] == "line" and R.section(a + 1e-4)["kind"] == "line" \
                    and R.section(b - 1e-4)["kind"] == "line":
                col_st.add(round((0.5 * (a + b)) % self.P, 4))
        pier_s = [R.s_north(x) for x in (S.PIER_X1, -S.PIER_X1)]
        for s in sorted(col_st):
            if any(abs(s - p) < 1.0 for p in pier_s):
                continue                               # the board piers stand here
            with mb.transform(vframe(R, s, 0.0, 0.0)):
                mb.box((-0.3, S.BAND_D, wz), (0.3, S.BAND_D + 0.6, cz), "Concrete", skip="zZ")
        self.column_stations = sorted(col_st)
        # kiosks / doors on the back wall of the concourse give the dark band some life
        for a, b in zip(fr, fr[1:] + [fr[0] + self.P]):
            if b - a < 3.0:
                continue
            mid = 0.5 * (a + b)
            wid = min(4.2, 0.5 * R.arclen(a, b, S.REC_D1))
            with mb.transform(vframe(R, mid, S.REC_D1, wz)):
                mb.box((-wid / 2, -0.12, 0.0), (wid / 2, 0.0, 2.35), "Steel", skip="Yz")
                mb.box((-wid / 2 + 0.25, -0.16, 0.95), (wid / 2 - 0.25, -0.12, 2.1), "Glass", skip="Yz")

    # ---- suite strip + upper-deck fascia ----------------------------------------------------------------
    def suite_band(self):
        R, mb = self.ring, self.mb
        dz = S.DECK_Z
        zg0 = dz + S.SUITE_SILL
        zg1 = zg0 + S.SUITE_GLASS
        stn = self.st(self.hs0, self.hs1)
        loft(mb, R, stn, [(S.BAND_D, S.CEIL_Z, "Concrete"), (S.BAND_D, zg0, "Concrete"),
                          (S.BAND_D + 0.15, zg0, "Glass"), (S.BAND_D + 0.15, zg1, "Concrete"),
                          (S.BAND_D, zg1, "Concrete"), (S.BAND_D, S.SOFFIT_Z, None)])
        # the rooms behind the glass (seen if the engine's glass is see-through)
        loft(mb, R, stn, [(S.BAND_D + 0.17, zg0, "ConcreteDark"), (S.BAND_D + 3.6, zg0, "ConcreteDark"),
                          (S.BAND_D + 3.6, zg1, "ConcreteDark"), (S.BAND_D + 0.17, zg1, None)])
        for f in self.within(self.frames, self.hs0 + 0.5, self.hs1 - 0.5):
            for facing in (-1, 1):
                cross_face(mb, R, f, [(S.BAND_D + 0.17, zg0), (S.BAND_D + 3.6, zg0),
                                      (S.BAND_D + 3.6, zg1), (S.BAND_D + 0.17, zg1)], facing, "ConcreteDark")
        # mullions
        for s in self.spaced(self.hs0, self.hs1, S.BAND_D, 2.55):
            with mb.transform(vframe(R, s, S.BAND_D)):
                mb.box((-0.06, -0.03, zg0), (0.06, 0.15, zg1), "Steel", skip="YzZ")

        # soffit, fascia with its LED ribbon, parapet -- only where there is an upper deck
        f0 = S.SOFFIT_Z + 0.25
        f1 = S.SOFFIT_Z + 1.45
        for (a, b) in ((self.hs0, self.gap0), (self.gap1, self.hs1)):
            stn = self.st(a, b)
            loft(mb, R, stn, [(S.BAND_D, S.SOFFIT_Z, "ConcreteDark"), (S.FASCIA_D, S.SOFFIT_Z, "Concrete"),
                              (S.FASCIA_D, f0, None), (S.FASCIA_D, f1, "Concrete"),
                              (S.FASCIA_D, S.PARAPET_Z, "Concrete"),
                              (S.FASCIA_D + S.PARAPET_T, S.PARAPET_Z, "Concrete"),
                              (S.FASCIA_D + S.PARAPET_T, S.UD_ZS[0] - 0.02, "Concrete"),
                              (S.UD_D0 + 0.03, S.UD_ZS[0] - 0.02, None)])
            length = R.arclen(a, b, S.FASCIA_D)
            n = max(1, int(round(length / S.AD_LEN)))
            lb = R.cum_length(b, S.FASCIA_D)
            strip(mb, R, stn, (S.FASCIA_D, f0), (S.FASCIA_D, f1), "AdBoard",
                  u_of_s=lambda s, lb=lb, n=n, length=length: (lb - R.cum_length(s, S.FASCIA_D)) * n / length)

    # ---- upper deck ---------------------------------------------------------------------------------------
    def upper_deck(self):
        R, mb = self.ring, self.mb
        zs = S.UD_ZS
        self.ud = []
        for cols, (a, b) in zip(self.ud_cols, ((self.hs0, self.gap0), (self.gap1, self.hs1))):
            voids = []
            for h in self.within(self.hole_stations, a, b):
                k = aisle_index(cols, h, self.P)
                voids.append(Void(5, 9, k - 1, k + 1, 0.5 * (zs[4] + zs[5]), "hole"))
            tier = Tier(R, "upper", S.UD_D0, zs, S.UD_TREAD, cols, voids, riser0_bottom=zs[0] - 0.05,
                        stations=self.extra_stations)
            tier.build(mb)
            for v in voids:
                self.hole(tier, v)
            self.ud.append(tier)
            self.tiers.append(tier)
            stn = self.st(a, b)
            loft(mb, R, stn, [(S.UD_D1, zs[-1], "Concrete"), (S.TOPWALK_D1, zs[-1], "Concrete"),
                              (S.TOPWALK_D1, S.RIM_Z, "Concrete"), (S.SHELL_D, S.RIM_Z, None)])
        # outside wall of the horseshoe (also behind the video board)
        stn = self.st(self.hs0, self.hs1)
        loft(mb, R, stn, self._shell_profile(S.RIM_Z))

    def _shell_profile(self, top):
        dz = S.DECK_Z
        prof = [(S.SHELL_D, top, "Concrete")]
        if top > dz + 3.4:
            prof += [(S.SHELL_D, dz + 3.0, "Glass"), (S.SHELL_D, dz + 0.4, "Concrete")]
        prof += [(S.SHELL_D, 4.6, "ConcreteDark"), (S.SHELL_D, 0.0, None)]
        return prof

    def hole(self, tier, void, portal_w=1.9, portal_h=2.35, ph=0.9, th=0.16, back_th=0.2, depth=2.6):
        """Vomitory: a pit cut into the rows, with stepped parapets and a dark portal at the back."""
        R, mb = self.ring, self.mb
        zs = tier.zs
        c0, c1 = tier.cols[void.k0], tier.cols[void.k1]
        sa, sb = c0.s0, c1.s1
        i0, i1 = void.i0, void.i1
        fz = void.floor_z
        d_front, d_back = tier.d(i0), tier.d(i1 + 1)
        d_bw = d_back - back_th
        sm = 0.5 * (sa + sb)
        ths = R.ds(sm, th, d_back)
        stn = self.st(sa, sb)
        strip(mb, R, stn, (d_front, fz), (d_bw, fz), "Concrete")
        for k in range(void.k0, void.k1 + 1):
            kind = tier.kind(i0 - 1, k)
            if kind not in ("seat", "aisle"):
                continue
            surf = zs[i0 - 1] if kind == "seat" else tier.half(i0 - 1)
            if abs(fz - surf) > 1e-4:
                c = tier.cols[k]
                strip(mb, R, self.st(c.s0, c.s1), (d_front, surf), (d_front, fz), "Concrete")
        segs = [(tier.d(i), tier.d(i + 1) if i < i1 else d_bw, fz, zs[i] + ph, zs[i])
                for i in range(i0, i1 + 1)]
        stepped_slab(mb, R, sa + ths, +1, th, segs, "Concrete", back=False)
        stepped_slab(mb, R, sb - ths, -1, th, segs, "Concrete", back=False)

        hw = 0.5 * R.arclen(sa, sb, d_bw)
        top = zs[i1 + 1] + ph
        pw = portal_w / 2
        with mb.transform(vframe(R, sm)):
            y0, y1 = d_bw, d_back
            for (xa, xb, za, zb) in ((-hw, -pw, fz, top), (pw, hw, fz, top), (-pw, pw, fz + portal_h, top)):
                mb.quad((xa, y0, za), (xb, y0, za), (xb, y0, zb), (xa, y0, zb), "Concrete")
            mb.box((-hw, y0, fz), (hw, y1 + 0.02, top), "Concrete", skip="xXyYz")          # top
            mb.box((-hw, y0, zs[i1 + 1]), (hw, y1 + 0.02, top), "Concrete", skip="xXyzZ")  # back
            mb.box((-hw, y0, zs[i1]), (hw, y1 + 0.02, top), "Concrete", skip="yYzZ")       # ends
            # the dark recess behind the portal
            ya = y0 + depth
            zc = fz + portal_h
            mb.quad((-pw, y0, fz), (pw, y0, fz), (pw, ya, fz), (-pw, ya, fz), "ConcreteDark")
            mb.quad((-pw, y0, zc), (-pw, ya, zc), (pw, ya, zc), (pw, y0, zc), "ConcreteDark")
            mb.quad((-pw, y0, fz), (-pw, ya, fz), (-pw, ya, zc), (-pw, y0, zc), "ConcreteDark")
            mb.quad((pw, ya, fz), (pw, y0, fz), (pw, y0, zc), (pw, ya, zc), "ConcreteDark")
            mb.quad((-pw, ya, fz), (pw, ya, fz), (pw, ya, zc), (-pw, ya, zc), "ConcreteDark")

    # ---- the -Y side ------------------------------------------------------------------------------------
    def south_side(self):
        R, mb = self.ring, self.mb
        dz = S.DECK_Z
        z0 = self.hs1
        z1 = self.P + self.hs0
        zs = S.ST_ZS
        # upstand at the front of the deck, then the deck itself
        loft(mb, R, self.st(z0, z1), [(S.BAND_D, S.CEIL_Z, "Concrete"), (S.BAND_D, dz + 0.3, "Concrete"),
                                      (S.BAND_D + 0.3, dz + 0.3, "Concrete"), (S.BAND_D + 0.3, dz, "Concrete"),
                                      (S.ST_FASCIA_D, dz, None)])
        # corner decks run out to a parapet on the outside wall
        for (a, b) in ((z0, self.st0), (self.st1, z1)):
            loft(mb, R, self.st(a, b),
                 [(S.ST_FASCIA_D, dz, "Concrete"), (S.SHELL_D - 0.3, dz, "Concrete"),
                  (S.SHELL_D - 0.3, dz + 1.1, "Concrete"), (S.SHELL_D, dz + 1.1, "Concrete")]
                 + self._shell_profile(dz + 1.1)[1:])
        # the set-back tier
        a, b = self.st0, self.st1
        stn = self.st(a, b)
        f0, f1 = dz + 0.6, dz + 1.8
        loft(mb, R, stn, [(S.ST_FASCIA_D, dz, "Concrete"), (S.ST_FASCIA_D, f0, None),
                          (S.ST_FASCIA_D, f1, "Concrete"), (S.ST_FASCIA_D, zs[0] + 1.0, "Concrete"),
                          (S.ST_FASCIA_D + S.PARAPET_T, zs[0] + 1.0, "Concrete"),
                          (S.ST_FASCIA_D + S.PARAPET_T, zs[0] - 0.02, "Concrete"),
                          (S.ST_D0 + 0.03, zs[0] - 0.02, None)])
        length = R.arclen(a, b, S.ST_FASCIA_D)
        n = max(1, int(round(length / S.AD_LEN)))
        lb = R.cum_length(b, S.ST_FASCIA_D)
        strip(mb, R, stn, (S.ST_FASCIA_D, f0), (S.ST_FASCIA_D, f1), "AdBoard",
              u_of_s=lambda s: (lb - R.cum_length(s, S.ST_FASCIA_D)) * n / length)
        cols = self.st_cols
        voids = []
        for h in self.st_holes:
            k = aisle_index(cols, h, self.P)
            voids.append(Void(3, 7, k - 1, k + 1, 0.5 * (zs[2] + zs[3]), "hole"))
        tier = Tier(R, "south", S.ST_D0, zs, S.ST_TREAD, cols, voids, riser0_bottom=zs[0] - 0.05,
                    stations=self.extra_stations)
        tier.build(mb)
        for v in voids:
            self.hole(tier, v)
        self.south = tier
        self.tiers.append(tier)
        loft(mb, R, stn, [(S.ST_D1, zs[-1], "Concrete"), (S.TOPWALK_D1, zs[-1], "Concrete"),
                          (S.TOPWALK_D1, S.ST_RIM_Z, "Concrete")] + self._shell_profile(S.ST_RIM_Z))

    # ---- stepped end walls ---------------------------------------------------------------------------------
    def end_walls(self):
        R, mb = self.ring, self.mb
        dz = S.DECK_Z
        th = 0.30
        # horseshoe ends
        zs = S.UD_ZS
        segs = [(S.FASCIA_D, S.UD_D0, S.SOFFIT_Z, S.PARAPET_Z, zs[0] - 0.02)]
        for i in range(S.UD_ROWS):
            da, db = S.UD_D0 + i * S.UD_TREAD, S.UD_D0 + (i + 1) * S.UD_TREAD
            top = zs[i] + 1.0
            if da < S.BAND_D < db:
                segs.append((da, S.BAND_D, S.SOFFIT_Z, top, zs[i]))
                segs.append((S.BAND_D, db, dz, top, zs[i]))
            else:
                segs.append((da, db, S.SOFFIT_Z if db <= S.BAND_D else dz, top, zs[i]))
        segs.append((S.UD_D1, S.TOPWALK_D1, dz, zs[-1] + 1.0, zs[-1]))
        segs.append((S.TOPWALK_D1, S.SHELL_D, dz, S.RIM_Z, None))
        stepped_slab(mb, R, self.hs0, -1, th, segs, "Concrete", bottom_above=dz)
        stepped_slab(mb, R, self.hs1, +1, th, segs, "Concrete", bottom_above=dz)
        # -Y tier ends
        zs = S.ST_ZS
        segs = [(S.ST_FASCIA_D, S.ST_D0, dz, zs[0] + 1.0, zs[0] - 0.02)]
        for i in range(S.ST_ROWS):
            segs.append((S.ST_D0 + i * S.ST_TREAD, S.ST_D0 + (i + 1) * S.ST_TREAD, dz, zs[i] + 1.0, zs[i]))
        segs.append((S.ST_D1, S.TOPWALK_D1, dz, zs[-1] + 1.0, zs[-1]))
        segs.append((S.TOPWALK_D1, S.SHELL_D, dz, S.ST_RIM_Z, None))
        stepped_slab(mb, R, self.st0, -1, th, segs, "Concrete")
        stepped_slab(mb, R, self.st1, +1, th, segs, "Concrete")

    # ---- roofs -----------------------------------------------------------------------------------------------
    def roof_top(self, d, south=False):
        if south:
            d0, zb, rise = S.ST_ROOF_D0, S.ST_ROOF_Z1, S.ST_ROOF_RISE
        else:
            d0, zb, rise = S.ROOF_D0, S.ROOF_Z1, S.ROOF_RISE
        return zb + rise * (S.ROOF_D1 - d) / (S.ROOF_D1 - d0)

    def roof_under(self, d, south=False):
        d0 = S.ST_ROOF_D0 if south else S.ROOF_D0
        t = S.ROOF_T0 + (S.ROOF_T1 - S.ROOF_T0) * (d - d0) / (S.ROOF_D1 - d0)
        return self.roof_top(d, south) - t

    def roofs(self):
        self._roof(self.hs0, self.gap0, False, (True, False))
        self._roof(self.gap1, self.hs1, False, (False, True))
        self._roof(self.st0, self.st1, True, (True, True))

    def _roof(self, a, b, south, caps):
        R, mb = self.ring, self.mb
        d0 = S.ST_ROOF_D0 if south else S.ROOF_D0
        d1 = S.ROOF_D1
        rim = S.ST_RIM_Z if south else S.RIM_Z
        mast_top = rim + (S.ST_MAST_H if south else S.MAST_H)
        top = lambda d: self.roof_top(d, south)
        und = lambda d: self.roof_under(d, south)
        stn = self.st(a, b)
        loft(mb, R, stn, [(d0, und(d0), "Roof"), (d0, top(d0), "Roof"), (d1, top(d1), "Roof"),
                          (d1, und(d1), "Roof")], close=True,
             caps=("Roof" if caps[0] else None, "Roof" if caps[1] else None))
        # steel edge beam along the leading edge
        loft(mb, R, stn, [(d0 - 0.14, und(d0) - 0.30, "Steel"), (d0 - 0.14, top(d0) + 0.12, "Steel"),
                          (d0 + 0.02, top(d0) + 0.12, "Steel"), (d0 + 0.02, und(d0) - 0.30, "Steel")],
             close=True, caps=("Steel" if caps[0] else None, "Steel" if caps[1] else None))
        # purlins
        span = S.SHELL_D - d0
        for frac in (0.2, 0.5, 0.8):
            d = d0 + span * frac
            loft(mb, R, stn, [(d - 0.11, und(d - 0.11) - 0.34, "Steel"), (d - 0.11, und(d - 0.11), None),
                              (d + 0.11, und(d + 0.11), "Steel"), (d + 0.11, und(d + 0.11) - 0.34, "Steel")],
                 close=True, caps=("Steel" if caps[0] else None, "Steel" if caps[1] else None))
        # frames: truss, mast, stays
        dm = S.SHELL_D + 0.35
        for f in self.within(self.frames, a + 0.5, b - 0.5) + ([a] if caps[0] else []) + ([b] if caps[1] else []):
            off = 0.0
            if abs(f - a) < 1e-6:
                off = 0.22
            elif abs(f - b) < 1e-6:
                off = -0.22
            M = vframe(R, f)
            with mb.transform(M):
                with mb.transform(Matrix.Translation((-off, 0.0, 0.0)) @ SIDE):
                    da, db = d0 + 0.5, dm
                    mb.prism([(da, und(da)), (db, und(db)), (db, und(db) - 1.15), (da, und(da) - 0.32)],
                             -0.17, 0.17, "Steel")
                x = -off
                zc = rim + 0.4                       # concrete pilaster below, steel mast above
                mb.box((x - 0.35, S.SHELL_D - 0.05, 0.0), (x + 0.35, S.SHELL_D + 0.7, zc), "Concrete", skip="zZ")
                mb.box((x - 0.35, S.SHELL_D - 0.05, zc), (x + 0.35, S.SHELL_D + 0.7, mast_top), "Steel", skip="z")
                tip = (x, dm, mast_top - 0.5)
                for frac in (0.22, 0.58):
                    d = d0 + span * frac
                    mb.beam(tip, (x, d, top(d) + 0.02), 0.16, 0.16, "Steel", caps="")
                mb.beam(tip, (x, S.SHELL_D + 9.5, 0.3), 0.2, 0.2, "Steel", caps="")       # ends inside its anchor block
                mb.box((x - 0.6, S.SHELL_D + 8.8, 0.0), (x + 0.6, S.SHELL_D + 10.2, 0.7), "Concrete", skip="z")

    # ---- video board ---------------------------------------------------------------------------------------
    def video_board(self):
        R, mb = self.ring, self.mb
        s = R.s_north(0.0)
        hw = S.SCREEN_W / 2
        z0 = S.SCREEN_Z0
        z1 = z0 + S.SCREEN_H
        bx = S.BOARD_HX
        zb, zt = S.SOFFIT_Z, S.RIM_Z
        yd = S.SCREEN_D
        inset = 0.18
        with mb.transform(vframe(R, s)):
            # housing: face frame, reveal, screen
            for (xa, xb, za, zc) in ((-bx, -hw, zb, zt), (hw, bx, zb, zt), (-hw, hw, zb, z0), (-hw, hw, z1, zt)):
                mb.quad((xa, yd, za), (xb, yd, za), (xb, yd, zc), (xa, yd, zc), "Steel")
            ys = yd + inset
            mb.quad((-hw, yd, z0), (-hw, ys, z0), (-hw, ys, z1), (-hw, yd, z1), "Steel")
            mb.quad((hw, ys, z0), (hw, yd, z0), (hw, yd, z1), (hw, ys, z1), "Steel")
            mb.quad((-hw, yd, z0), (hw, yd, z0), (hw, ys, z0), (-hw, ys, z0), "Steel")
            mb.quad((-hw, ys, z1), (hw, ys, z1), (hw, yd, z1), (-hw, yd, z1), "Steel")
            mb.quad((-hw, ys, z0), (hw, ys, z0), (hw, ys, z1), (-hw, ys, z1), "Screen",
                    uv=((0, 0), (1, 0), (1, 1), (0, 1)))
            mb.quad((-bx, yd, zb), (-bx, S.BAND_D, zb), (bx, S.BAND_D, zb), (bx, yd, zb), "ConcreteDark")
            mb.quad((-bx, yd, zt), (bx, yd, zt), (bx, S.SHELL_D, zt), (-bx, S.SHELL_D, zt), "Roof")
            # piers
            for sg in (-1.0, 1.0):
                xa, xb = sorted((sg * S.PIER_X0, sg * S.PIER_X1))
                with mb.transform(SIDE):
                    out = [(S.PIER_D0, S.WALK_Z), (S.PIER_D0, S.PIER_TOP), (S.PIER_D0 + 3.2, S.PIER_TOP),
                           (S.SHELL_D + 0.7, S.RIM_Z + 2.6), (S.SHELL_D + 0.7, S.WALK_Z)]
                    mb.prism(out, xa, xb, "Concrete")
                mb.box((xa, S.SHELL_D, 0.0), (xb, S.SHELL_D + 0.7, S.WALK_Z), "Concrete", skip="yzZ")
                # steel cap and a tall banner in a team colour on the face
                mb.box((xa - 0.06, S.PIER_D0 - 0.06, S.PIER_TOP - 0.5), (xb + 0.06, S.PIER_D0 + 3.26, S.PIER_TOP + 0.08),
                       "Steel")
                mb.box((xa + 0.35, S.PIER_D0 - 0.07, S.SOFFIT_Z + 1.2), (xb - 0.35, S.PIER_D0, S.RIM_Z + 4.6),
                       "SeatA" if sg < 0 else "SeatB", skip="Y")
            # header truss between the piers
            ya, yb = S.PIER_D0 + 0.35, S.PIER_D0 + 2.6
            za, zc = S.RIM_Z + 1.3, S.RIM_Z + 5.9
            for y in (ya, yb):
                for z in (za, zc):
                    mb.beam((-bx, y, z), (bx, y, z), 0.34, 0.34, "Steel", caps="")
            nb = 10
            for k in range(nb + 1):
                x = -bx + 2 * bx * k / nb
                for y in (ya, yb):
                    mb.beam((x, y, za), (x, y, zc), 0.2, 0.2, "Steel", caps="")
                mb.beam((x, ya, zc), (x, yb, zc), 0.2, 0.2, "Steel", caps="")
                mb.beam((x, ya, za), (x, yb, za), 0.2, 0.2, "Steel", caps="")
                if k < nb:
                    x2 = -bx + 2 * bx * (k + 1) / nb
                    lo, hi = (za, zc) if k % 2 == 0 else (zc, za)
                    for y in (ya, yb):
                        mb.beam((x, y, lo), (x2, y, hi), 0.16, 0.16, "Steel", caps="")
        px, py, nx, ny = R.frame(s)
        self.screen = dict(center=[px, py + yd + inset, 0.5 * (z0 + z1)], width=S.SCREEN_W, height=S.SCREEN_H,
                           normal=[0.0, -1.0, 0.0])

    # ---- end-zone scoreboards ------------------------------------------------------------------------------
    def small_boards(self):
        R, mb = self.ring, self.mb
        hw, z0 = S.SMALL_W / 2, S.SMALL_Z0
        z1 = z0 + S.SMALL_H
        for s in (R.s_east(0.0), R.s_west(0.0)):
            with mb.transform(vframe(R, s)):
                yd = S.SMALL_D
                # slim housing on the fascia, deeper below the soffit where it hangs in front of the suites
                mb.box((-hw - 0.5, yd - 0.12, S.SOFFIT_Z), (hw + 0.5, S.FASCIA_D, z1 + 0.22), "Steel", skip="Yz")
                mb.box((-hw - 0.5, yd - 0.12, z1), (hw + 0.5, S.FASCIA_D, z1 + 0.22), "Steel", skip="xXyzZ")
                mb.box((-hw - 0.5, yd - 0.12, z0 - 0.4), (hw + 0.5, S.BAND_D + 0.02, S.SOFFIT_Z), "Steel", skip="YZ")
                mb.quad((-hw, yd - 0.14, z0), (hw, yd - 0.14, z0), (hw, yd - 0.14, z1), (-hw, yd - 0.14, z1),
                        "ScreenSmall", uv=((0, 0), (1, 0), (1, 1), (0, 1)))
            px, py, nx, ny = R.frame(s)
            d = yd - 0.14
            self.small_screens.append(dict(center=[px + nx * d, py + ny * d, 0.5 * (z0 + z1)],
                                           width=S.SMALL_W, height=S.SMALL_H, normal=[-nx, -ny, 0.0]))

    # ---- floodlights -----------------------------------------------------------------------------------------
    def light_banks(self):
        R = self.ring
        x = 4 * S.SIDE_PITCH
        spots = [
            (R.s_north(-x), False, (-17.0, -5.0, 0.0)),
            (R.s_north(x), False, (17.0, -5.0, 0.0)),
            (R.s_south(-x), True, (-17.0, 5.0, 0.0)),
            (R.s_south(x), True, (17.0, 5.0, 0.0)),
            (R.s_west(0.0), False, (-37.0, 0.0, 0.0)),
            (R.s_east(0.0), False, (37.0, 0.0, 0.0)),
        ]
        for s, south, aim in spots:
            self._bank(s, south, aim)

    def _bank(self, s, south, aim):
        R, mb = self.ring, self.mb
        cols, rows, pitch, lr = S.BANK_COLS, S.BANK_ROWS, S.LAMP_PITCH, S.LAMP_R
        w = cols * pitch + 0.5
        h = rows * pitch + 0.5
        d0 = S.ST_ROOF_D0 if south else S.ROOF_D0
        d = d0 + (4.4 if south else 1.0)      # the -Y banks sit back so nothing leans into the camera gap
        zc = self.roof_top(d, south) + 0.9 + h / 2
        px, py, nx, ny = R.frame(s)
        c = Vector((px + nx * d, py + ny * d, zc))
        fwd = (Vector(aim) - c).normalized()
        right = fwd.cross(Vector((0, 0, 1))).normalized()
        up = right.cross(fwd).normalized()
        M = Matrix(((right.x, fwd.x, up.x, c.x), (right.y, fwd.y, up.y, c.y), (right.z, fwd.z, up.z, c.z),
                    (0, 0, 0, 1)))
        with mb.transform(M):
            mb.box((-w / 2, -0.75, -h / 2), (w / 2, 0.0, h / 2), "LampHousing")
            mb.box((-w / 2 - 0.12, -0.2, h / 2), (w / 2 + 0.12, 0.75, h / 2 + 0.1), "LampHousing")   # visor
            for sx in (-1, 1):
                mb.box((sx * (w / 2 + 0.06) - 0.06, -0.2, -h / 2), (sx * (w / 2 + 0.06) + 0.06, 0.55, h / 2),
                       "LampHousing")
            for i in range(cols):
                for j in range(rows):
                    lx = (i - (cols - 1) / 2) * pitch
                    lz = (j - (rows - 1) / 2) * pitch
                    m, _ = frame_z((lx, 0.0, lz), (lx, 1.0, lz), up=(0, 0, 1))
                    with mb.transform(m):
                        mb.lathe([(lr + 0.07, 0.0), (lr + 0.07, 0.24), (lr, 0.24), (0.0, 0.24)], "LampHousing",
                                 segs=16, mats=["LampHousing", "LampHousing", "Lamp"])
        # legs down to the roof
        wm = M
        for sx in (-1, 1):
            foot_local = Vector((sx * (w / 2 - 1.2), -0.4, -h / 2))
            top_pt = wm @ foot_local
            # straight down to the roof surface under it
            q = self._roof_point_below(top_pt, south)
            mb.beam(tuple(top_pt), q, 0.3, 0.3, "Steel")
            back_local = Vector((sx * (w / 2 - 1.2), -0.55, h / 2 - 0.4))
            bp = wm @ back_local
            anchor = self._roof_point_at(bp, south, 5.5)
            mb.beam(tuple(bp), anchor, 0.24, 0.24, "Steel")
        centre = M @ Vector((0.0, 0.24, 0.0))
        self.lights.append(dict(pos=[centre.x, centre.y, centre.z], aim=list(aim)))

    def _offset_of(self, p):
        """(station, offset) of a world point near a straight part of the ring (N, S, E or W)."""
        R = self.ring
        x, y = p[0], p[1]
        if abs(y) - S.WALL_HY >= abs(x) - S.WALL_HX:
            if y > 0:
                return R.s_north(x), y - S.WALL_HY
            return R.s_south(x) if x >= 0 else self.P + x, -y - S.WALL_HY
        if x > 0:
            return R.s_east(y), x - S.WALL_HX
        return R.s_west(y), -x - S.WALL_HX

    def _roof_point_below(self, p, south):
        s, d = self._offset_of(p)
        d0 = S.ST_ROOF_D0 if south else S.ROOF_D0
        d = max(d, d0 + 0.15)
        return self.ring.p3(s, d, self.roof_top(d, south) - 0.05)

    def _roof_point_at(self, p, south, back):
        s, d = self._offset_of(p)
        d0 = S.ST_ROOF_D0 if south else S.ROOF_D0
        d = max(d, d0) + back
        return self.ring.p3(s, d, self.roof_top(d, south) - 0.05)

    # ---- players' tunnel -------------------------------------------------------------------------------------
    def tunnel(self):
        R, mb = self.ring, self.mb
        zs = S.LB_ZS
        th = S.TUN_WALL_T
        rows = S.TUN_ROWS
        d_head = S.LB_D0 + rows * S.LB_TREAD            # riser of the first row that bridges the cut
        d_face = d_head - th
        top = zs[rows] + 1.0
        segs = [(-S.AD_PROUD, S.LB_D0, 0.0, S.WALL_H, 0.0, "WallPad")]      # caps the end of the field wall
        for i in range(rows):
            db = S.LB_D0 + (i + 1) * S.LB_TREAD
            segs.append((S.LB_D0 + i * S.LB_TREAD, db if i < rows - 1 else d_face, 0.0, zs[i] + 1.0, zs[i]))
        stepped_slab(mb, R, self.tun0 + th, +1, th, segs, "Concrete", back=False)
        stepped_slab(mb, R, self.tun1 - th, -1, th, segs, "Concrete", back=False)
        hw = S.TUN_HW
        pw, ph = S.TUN_PORTAL_W / 2, S.TUN_PORTAL_H
        y_end = S.SHELL_D - 0.6                     # stops short of the outside wall
        with mb.transform(vframe(R, self.tun_s)):
            # floor of the open cut
            mb.quad((-hw, 0.2, 0.0), (hw, 0.2, 0.0), (hw, d_face, 0.0), (-hw, d_face, 0.0), "Apron")
            # padding on the retaining walls
            for sx in (-1, 1):
                xa, xb = sorted((sx * (hw - th), sx * (hw - th - 0.07)))
                mb.box((xa, S.LB_D0 + 0.1, 0.0), (xb, d_face - 0.3, 1.7), "WallPad", skip="z")
            # headwall with the portal
            for (xa, xb, za, zb) in ((-hw, -pw, 0.0, top), (pw, hw, 0.0, top), (-pw, pw, ph, top)):
                mb.quad((xa, d_face, za), (xb, d_face, za), (xb, d_face, zb), (xa, d_face, zb), "Concrete")
            mb.box((-hw, d_face, 0.0), (hw, d_head + 0.02, top), "Concrete", skip="xXyYz")
            mb.box((-hw, d_face, zs[rows]), (hw, d_head + 0.02, top), "Concrete", skip="xXyzZ")
            mb.box((-hw, d_face, zs[rows - 1]), (hw, d_head + 0.02, top), "Concrete", skip="yYzZ")
            # steel lintel over the mouth and a band in the home colour above it
            mb.box((-pw - 0.25, d_face - 0.1, ph), (pw + 0.25, d_face, ph + 0.45), "Steel", skip="Y")
            mb.box((-hw + th + 0.08, d_face - 0.06, ph + 0.62), (hw - th - 0.08, d_face, top - 0.18), "SeatA", skip="Y")
            # the bore
            y0 = d_face
            mb.quad((-pw, y0, 0.0), (pw, y0, 0.0), (pw, y_end, 0.0), (-pw, y_end, 0.0), "Concrete")
            mb.quad((-pw, y0, ph), (-pw, y_end, ph), (pw, y_end, ph), (pw, y0, ph), "ConcreteDark")
            mb.quad((-pw, y0, 0.0), (-pw, y_end, 0.0), (-pw, y_end, ph), (-pw, y0, ph), "ConcreteDark")
            mb.quad((pw, y_end, 0.0), (pw, y0, 0.0), (pw, y0, ph), (pw, y_end, ph), "ConcreteDark")
            mb.quad((-pw, y_end, 0.0), (pw, y_end, 0.0), (pw, y_end, ph), (-pw, y_end, ph), "ConcreteDark")
            # roller door at the far end
            mb.box((-pw + 0.5, y_end - 0.1, 0.0), (pw - 0.5, y_end, ph - 0.5), "Steel", skip="Yz")
            # ribs and strip lights
            y = y0 + 2.5
            k = 0
            while y < y_end - 1.0:
                mb.box((-pw, y - 0.2, 0.0), (-pw + 0.22, y + 0.2, ph), "ConcreteDark", skip="xzZ")
                mb.box((pw - 0.22, y - 0.2, 0.0), (pw, y + 0.2, ph), "ConcreteDark", skip="XzZ")
                mb.box((-pw + 0.22, y - 0.2, ph - 0.25), (pw - 0.22, y + 0.2, ph), "ConcreteDark", skip="xXZ")
                yl = y + 2.5
                if yl < y_end - 1.0:
                    mb.box((-1.1, yl - 0.14, ph - 0.09), (1.1, yl + 0.14, ph), "LampHousing", skip="zZ")
                    mb.quad((-1.1, yl - 0.14, ph - 0.09), (-1.1, yl + 0.14, ph - 0.09),
                            (1.1, yl + 0.14, ph - 0.09), (1.1, yl - 0.14, ph - 0.09), "Lamp")
                y += 5.0
                k += 1
        px, py, nx, ny = R.frame(self.tun_s)
        self.tunnel_meta = dict(mouth=[px, py, 0.0], dir=[-nx, -ny, 0.0], width=2 * (hw - th),
                                portal=[px + nx * d_face, py + ny * d_face, 0.0],
                                portal_width=S.TUN_PORTAL_W, portal_height=S.TUN_PORTAL_H)

    # ---- rails, banners and other dressing -------------------------------------------------------------------
    def rail(self, a, b, d, z0, h, post_step=2.2, mid=True):
        R, mb = self.ring, self.mb
        stn = self.st(a, b)

        def bar(zc, hw, hh):
            loft(mb, R, stn, [(d - hw, zc - hh, "Steel"), (d - hw, zc + hh, "Steel"),
                              (d + hw, zc + hh, "Steel"), (d + hw, zc - hh, "Steel")], close=True,
                 caps=("Steel", "Steel"))

        bar(z0 + h - 0.03, 0.035, 0.03)
        if mid:
            bar(z0 + 0.5 * h, 0.022, 0.022)
        for s in self.spaced(a, b, d, post_step):
            with mb.transform(vframe(R, s, d, z0)):
                mb.box((-0.03, -0.03, 0.0), (0.03, 0.03, h - 0.03), "Steel", skip="z")

    def dressing(self):
        R, mb = self.ring, self.mb
        # rail on the upper-deck parapet and on the -Y tier parapet
        for (a, b) in ((self.hs0, self.gap0), (self.gap1, self.hs1)):
            self.rail(a, b, S.FASCIA_D + 0.09, S.PARAPET_Z, 0.28, post_step=2.5, mid=False)
        self.rail(self.st0, self.st1, S.ST_FASCIA_D + 0.09, S.ST_ZS[0] + 1.0, 0.28, post_step=2.5, mid=False)
        # guard rail along the front of the -Y deck
        self.rail(self.hs1, self.P + self.hs0, S.BAND_D + 0.15, S.DECK_Z + 0.3, 0.75, post_step=2.0)
        # banners on the rear wall under the roof, alternating team colours
        k = 0
        z0 = S.UD_ZS[-1] + 0.85
        for (a, b) in ((self.hs0, self.gap0), (self.gap1, self.hs1)):
            fr = [a] + self.within(self.frames, a + 0.5, b - 0.5) + [b]
            for f0, f1 in zip(fr[:-1], fr[1:]):
                for t in (0.27, 0.73):
                    s = f0 + (f1 - f0) * t
                    with mb.transform(vframe(R, s, S.TOPWALK_D1)):
                        mb.box((-1.5, -0.06, z0), (1.5, 0.0, z0 + 3.0), "SeatA" if k % 2 == 0 else "SeatB", skip="Y")
                        mb.box((-1.62, -0.1, z0 + 3.0), (1.62, 0.0, z0 + 3.1), "Steel", skip="Y")
                    k += 1

    def aisle_rails(self, tier, start=1, every=4, span=2, h=0.9):
        """Short centre handrails stepping up the aisles of the steep decks."""
        R, mb = self.ring, self.mb
        t = tier.tread
        s_lo, s_hi = tier.cols[0].s0, tier.cols[-1].s1
        for k, c in enumerate(tier.cols):
            if c.kind != "aisle" or c.aisle is None:
                continue
            if abs(c.aisle - s_lo) < 1e-3 or abs(c.aisle - s_hi) < 1e-3:
                continue                                  # half aisle against a pier or wall
            i = start
            while i + span <= tier.rows - 1:
                if all(tier.kind(j, k) == "aisle" for j in range(i, i + span + 1)):
                    ya, za = tier.d(i) + 0.25 * t, tier.zs[i]
                    yb, zb = tier.d(i + span) + 0.25 * t, tier.zs[i + span]
                    with mb.transform(vframe(R, c.aisle)):
                        mb.box((-0.022, ya - 0.022, za), (0.022, ya + 0.022, za + h), "Steel", skip="z")
                        mb.box((-0.022, yb - 0.022, zb), (0.022, yb + 0.022, zb + h), "Steel", skip="z")
                        mb.beam((0, ya, za + h), (0, yb, zb + h), 0.05, 0.05, "Steel")
                        mb.beam((0, ya, za + 0.5 * h), (0, yb, zb + 0.5 * h), 0.035, 0.035, "Steel")
                i += every

    def flag(self, base, height, size, mat, pole_r=0.09, wave=0.32, segs=6):
        """Flagpole with a (static, gently waving) flag flying toward +X. `base` is a world point."""
        mb = self.mb
        x, y, z = base
        mb.cyl_between((x, y, z), (x, y, z + height), pole_r, "Steel", segs=8, r1=pole_r * 0.6, caps="Z")
        mb.cyl_between((x, y, z + height), (x, y, z + height + 0.25), pole_r * 1.6, "Steel", segs=8)
        w, hgt = size
        zt = z + height - 0.15
        pts = []
        for i in range(segs + 1):
            t = i / segs
            pts.append((x + pole_r + w * t, y + wave * math.sin(t * math.pi * 1.7) * (0.35 + 0.65 * t)))
        o = 0.006                                     # half thickness: the flag is a closed thin slab
        zb = zt - hgt
        for i in range(segs):
            (xa, ya), (xb, yb) = pts[i], pts[i + 1]
            mb.face(((xa, ya - o, zb), (xb, yb - o, zb), (xb, yb - o, zt), (xa, ya - o, zt)), mat, None, True)
            mb.face(((xa, ya + o, zt), (xb, yb + o, zt), (xb, yb + o, zb), (xa, ya + o, zb)), mat, None, True)
            mb.face(((xa, ya - o, zt), (xb, yb - o, zt), (xb, yb + o, zt), (xa, ya + o, zt)), mat)
            mb.face(((xa, ya + o, zb), (xb, yb + o, zb), (xb, yb - o, zb), (xa, ya - o, zb)), mat)
        (xa, ya), (xb, yb) = pts[0], pts[-1]
        mb.face(((xb, yb - o, zb), (xb, yb + o, zb), (xb, yb + o, zt), (xb, yb - o, zt)), mat)
        mb.face(((xa, ya + o, zb), (xa, ya - o, zb), (xa, ya - o, zt), (xa, ya + o, zt)), mat)

    def entrances(self):
        """Glazed entry bays and cantilevered marquees facing the public plaza."""
        for station in self.spaced(0.0, self.P, S.SHELL_D, 15.0)[:-1]:
            with self.mb.transform(vframe(self.ring, station, S.SHELL_D + 0.55)):
                self.mb.box((-4.5, -0.40, 0.0), (4.5, 0.1, 6.0), "ConcreteDark")
                for x in (-3.0, -1.0, 1.0, 3.0):
                    self.mb.box((x-0.92, 0.10, 0.08), (x+0.92, 0.18, 4.7), "Glass")
                    self.mb.box((x-0.90, 0.18, 1.15), (x+0.90, 0.23, 1.22), "Steel")
                self.mb.box((-5.0, -0.5, 5.4), (5.0, 2.7, 5.85), "Roof")
                self.mb.box((-4.8, 2.71, 5.50), (4.8, 2.77, 5.62), "Lamp")
                # A second storey of clerestory glass carries the rhythm of the gates
                # up the facade. The shorter corner decks keep clear of the broadcast view.
                for x in (-3.4, -1.7, 0.0, 1.7, 3.4):
                    self.mb.box((x-0.78, -0.48, 8.0), (x+0.78, -0.25, 13.2), "Glass")
                self.mb.box((-4.5, -0.50, 13.2), (4.5, 0.1, 13.55), "Steel")
                for x in (-4.55, 4.55):
                    self.mb.box((x-0.15, 1.9, 0.0), (x+0.15, 2.2, 5.4), "Steel")

    def extras(self):
        R, mb = self.ring, self.mb
        # handrails up the aisles of the upper deck and the -Y tier
        for tier in self.ud:
            self.aisle_rails(tier)
        self.aisle_rails(self.south)
        # team flags on the two piers either side of the video board
        for sg, mat in ((-1.0, "SeatA"), (1.0, "SeatB")):
            xm = sg * 0.5 * (S.PIER_X0 + S.PIER_X1)
            self.flag((xm, S.WALL_HY + S.PIER_D0 + 1.6, S.PIER_TOP), 8.5, (5.2, 3.1), mat)
        # three flagpoles on each of the open corner decks at the camera side
        for name, mats in (("SE", ("SeatA", "SeatB", "SeatA")), ("SW", ("SeatB", "SeatA", "SeatB"))):
            for i, mat in enumerate(mats):
                deg = (22.5 + (i - 1) * 5.0) if name == "SE" else (67.5 + (i - 1) * 5.0)
                px, py = R.point(R.s_corner(name, deg), 36.5)
                mb.box((px - 0.4, py - 0.4, S.DECK_Z), (px + 0.4, py + 0.4, S.DECK_Z + 0.5), "Concrete", skip="z")
                self.flag((px, py, S.DECK_Z + 0.5), 13.0, (4.2, 2.6), mat, pole_r=0.08)
        # speaker clusters hung under the leading edge of the roof, one per bay
        def clusters(a, b, south):
            d0 = S.ST_ROOF_D0 if south else S.ROOF_D0
            fr = [a] + self.within(self.frames, a + 0.5, b - 0.5) + [b]
            for f0, f1 in zip(fr[:-1], fr[1:]):
                if R.arclen(f0, f1, d0) < 6.0:
                    continue
                sm = 0.5 * (f0 + f1)
                d = d0 + 1.5
                zu = self.roof_under(d, south)
                with mb.transform(vframe(R, sm, d)):
                    mb.box((-0.7, -0.45, zu - 2.0), (0.7, 0.45, zu - 0.55), "LampHousing")
                    mb.box((-0.62, -0.5, zu - 1.9), (0.62, -0.45, zu - 0.65), "Steel", skip="Y")
                    for sx in (-0.5, 0.5):
                        mb.box((sx - 0.03, -0.03, zu - 0.55), (sx + 0.03, 0.03, zu + 0.02), "Steel", skip="zZ")
        clusters(self.hs0, self.gap0, False)
        clusters(self.gap1, self.hs1, False)
        clusters(self.st0, self.st1, True)

    # ---- outputs ---------------------------------------------------------------------------------------------
    def seats(self):
        out = []
        for t in self.tiers:
            out.extend(t.seats())
        return out
