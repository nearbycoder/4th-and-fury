"""Static props. Each function returns (MeshBuilder, [slot names in order]).

All props are real-world size, modelled in place around their stated origin.
UVs: box projection at 1 UV unit = 1 m unless noted (ball: cylindrical 0..1; DownFace: 0..1).
"""
import math

from mathutils import Matrix, Vector

from .meshkit import MeshBuilder, frame_z


def _rot_x(deg):
    return Matrix.Rotation(math.radians(deg), 4, "X")


def _rot_y(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Y")


def _rot_z(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def _tr(x, y, z):
    return Matrix.Translation((x, y, z))


# ------------------------------------------------------------------------------------------------
def goalpost():
    """Single-post gooseneck goal. Origin on the ground under the middle of the crossbar; the
    base post stands 2 m behind it, toward +X. Crossbar top at 3.05 m, 5.64 m clear between the
    uprights, which reach 13 m."""
    mb = MeshBuilder(uv_scale=1.0)
    r = 0.055
    zc = 3.05 - r
    yu = 5.64 / 2 + r
    top = 13.0
    Y = "GoalYellow"
    mb.tube([(0, -yu, top), (0, -yu, zc), (0, yu, zc), (0, yu, top)], r, Y, segs=14)
    rg = 1.25
    cx, cz = 2.0 - rg, zc - rg
    path = [(2.0, 0, 0.0), (2.0, 0, cz * 0.5), (2.0, 0, cz)]
    n = 14
    for i in range(1, n + 1):
        a = 0.5 * math.pi * i / n
        path.append((cx + rg * math.cos(a), 0, cz + rg * math.sin(a)))
    path.append((0.0, 0, zc))
    radii = [0.095 - 0.03 * i / (len(path) - 1) for i in range(len(path))]
    mb.tube(path, 0.09, Y, segs=16, radii=radii)
    mb.cyl_between((0, -0.16, zc), (0, 0.16, zc), r + 0.022, Y, segs=14)
    with mb.transform(_tr(2.0, 0, 0)):
        mb.cylinder(0.27, 0.0, 0.03, Y, segs=18, caps="Z")
        mb.lathe([(0.215, 0.03), (0.215, 1.80), (0.19, 1.86), (0.10, 1.86)], "GoalPad", segs=18)
        for z in (0.35, 1.0, 1.6):
            mb.lathe([(0.222, z - 0.03), (0.222, z + 0.03)], Y, segs=18)
    return mb, ["GoalYellow", "GoalPad"]


# ------------------------------------------------------------------------------------------------
def football():
    """Prolate ball 0.28 x 0.17 m, long axis X, laces on +Z. Four panels with grooved seams,
    raised laces, a stripe band near each end."""
    mb = MeshBuilder(uv_scale=4.0)
    a, b = 0.14, 0.085
    rho = (a * a + b * b) / (2 * b)

    def rad(x):
        return max(0.0, math.sqrt(max(rho * rho - x * x, 0.0)) - (rho - b))

    half = [0.0, 0.012, 0.024, 0.036, 0.048, 0.064, 0.076, 0.088, 0.100, 0.110, 0.119, 0.127,
            0.133, 0.1372, 0.14]
    xs = [-v for v in half[:0:-1]] + half
    quad = [0.0] + [2.2 + 8.56 * i for i in range(11)]           # seam, then 2.2 .. 87.8 degrees
    angs = [q * 90.0 + v for q in range(4) for v in quad]         # 48 around; seam where k % 12 == 0
    na = len(angs)

    def P(j, k):
        x = xs[j]
        r = rad(x)
        if k % 12 == 0:                                           # V-groove along each seam
            r = max(0.0, r - min(0.0021, 0.5 * r))
        ph = math.radians(angs[k % na])
        return (x, r * math.sin(ph), r * math.cos(ph))

    def U(k):
        return (angs[k] / 360.0) if k < na else 1.0

    n = len(xs)
    for j in range(n - 1):
        xm = abs(0.5 * (xs[j] + xs[j + 1]))
        mat = "BallStripe" if 0.064 - 1e-6 <= xm <= 0.088 + 1e-6 else "Leather"
        v0, v1 = (xs[j] + a) / (2 * a), (xs[j + 1] + a) / (2 * a)
        for k in range(na):
            k2 = k + 1
            p00, p10, p11, p01 = P(j, k), P(j + 1, k), P(j + 1, k2), P(j, k2)
            u0, u1 = U(k), U(k2)
            if j == 0:
                mb.face((p00, p10, p11), mat, ((0.5 * (u0 + u1), v0), (u0, v1), (u1, v1)), True)
            elif j == n - 2:
                mb.face((p00, p10, p01), mat, ((u0, v0), (0.5 * (u0 + u1), v1), (u1, v0)), True)
            else:
                mb.face((p00, p10, p11, p01), mat, ((u0, v0), (u0, v1), (u1, v1), (u1, v0)), True)

    def pt(x, ph, r):
        return (x, r * math.sin(ph), r * math.cos(ph))

    L = "Laces"
    # eight cross laces over the top seam
    for i in range(8):
        xc = -0.049 + 0.014 * i
        w = 0.0028
        r0 = rad(xc)
        rin, rout = r0 * 0.99, r0 + 0.0032
        phh = 0.0175 / r0
        segs = 4
        for s in range(segs):
            pa = -phh + 2 * phh * s / segs
            pb = -phh + 2 * phh * (s + 1) / segs
            mb.face((pt(xc - w, pa, rout), pt(xc + w, pa, rout), pt(xc + w, pb, rout), pt(xc - w, pb, rout)), L, None, True)
            mb.face((pt(xc - w, pa, rin), pt(xc - w, pa, rout), pt(xc - w, pb, rout), pt(xc - w, pb, rin)), L)
            mb.face((pt(xc + w, pb, rin), pt(xc + w, pb, rout), pt(xc + w, pa, rout), pt(xc + w, pa, rin)), L)
        mb.face((pt(xc - w, -phh, rin), pt(xc + w, -phh, rin), pt(xc + w, -phh, rout), pt(xc - w, -phh, rout)), L)
        mb.face((pt(xc - w, phh, rout), pt(xc + w, phh, rout), pt(xc + w, phh, rin), pt(xc - w, phh, rin)), L)
    # two long laces running under them
    for sg in (-1, 1):
        segs = 8
        x0, x1 = -0.058, 0.058
        for s in range(segs):
            xa = x0 + (x1 - x0) * s / segs
            xb = x0 + (x1 - x0) * (s + 1) / segs
            ra, rb = rad(xa), rad(xb)
            pha = sg * 0.0068 / ra
            phb = sg * 0.0068 / rb
            da, db = 0.0022 / ra, 0.0022 / rb
            oa, ob = ra + 0.0018, rb + 0.0018
            mb.face((pt(xa, pha - da, oa), pt(xb, phb - db, ob), pt(xb, phb + db, ob), pt(xa, pha + da, oa)), L, None, True)
            mb.face((pt(xa, pha - da, ra * 0.99), pt(xb, phb - db, rb * 0.99), pt(xb, phb - db, ob), pt(xa, pha - da, oa)), L)
            mb.face((pt(xa, pha + da, oa), pt(xb, phb + db, ob), pt(xb, phb + db, rb * 0.99), pt(xa, pha + da, ra * 0.99)), L)
        ra = rad(x0)
        pha, da, oa = sg * 0.0068 / ra, 0.0022 / ra, ra + 0.0018
        mb.face((pt(x0, pha + da, ra * 0.99), pt(x0, pha - da, ra * 0.99), pt(x0, pha - da, oa), pt(x0, pha + da, oa)), L)
        ra = rad(x1)
        pha, da, oa = sg * 0.0068 / ra, 0.0022 / ra, ra + 0.0018
        mb.face((pt(x1, pha - da, ra * 0.99), pt(x1, pha + da, ra * 0.99), pt(x1, pha + da, oa), pt(x1, pha - da, oa)), L)
    return mb, ["Leather", "Laces", "BallStripe"]


# ------------------------------------------------------------------------------------------------
def kick_tee():
    """Rubber kickoff tee: a chamfered base block with four prongs cradling the ball's point."""
    mb = MeshBuilder(uv_scale=8.0)
    T = "Tee"

    def octagon(hw, ch):
        return [(hw - ch, -hw), (hw, -hw + ch), (hw, hw - ch), (hw - ch, hw),
                (-hw + ch, hw), (-hw, hw - ch), (-hw, -hw + ch), (-hw + ch, -hw)]

    lo = octagon(0.055, 0.016)
    hi = octagon(0.047, 0.014)
    z0, z1, z2 = 0.0, 0.012, 0.024
    mb.prism(lo, z0, z1, T, caps="z")
    n = len(lo)
    for i in range(n):
        a0, a1 = lo[i], lo[(i + 1) % n]
        b0, b1 = hi[i], hi[(i + 1) % n]
        mb.face(((a0[0], a0[1], z1), (a1[0], a1[1], z1), (b1[0], b1[1], z2), (b0[0], b0[1], z2)), T)
    mb.face([(x, y, z2) for x, y in hi], T)
    # shallow cup in the middle
    mb.lathe([(0.0, z2 + 0.001), (0.014, z2 + 0.001), (0.02, z2 + 0.006), (0.024, z2 + 0.006), (0.026, z2)], T,
             segs=12)
    # prongs
    for sx in (-1, 1):
        for sy in (-1, 1):
            bx, by = sx * 0.027, sy * 0.027
            tx, ty = sx * 0.031, sy * 0.031
            wb, wt = 0.0085, 0.005
            base = [(bx - wb, by - wb, z2), (bx + wb, by - wb, z2), (bx + wb, by + wb, z2), (bx - wb, by + wb, z2)]
            topz = 0.052
            tp = [(tx - wt, ty - wt, topz), (tx + wt, ty - wt, topz), (tx + wt, ty + wt, topz), (tx - wt, ty + wt, topz)]
            for i in range(4):
                j = (i + 1) % 4
                mb.face((base[i], base[j], tp[j], tp[i]), T, None, True)
            mb.face(tp, T)
    return mb, ["Tee"]


def pylon():
    """End-zone pylon 0.10 x 0.10 x 0.46 m with softened edges."""
    mb = MeshBuilder(uv_scale=4.0)
    h, c = 0.05, 0.007
    out = [(h - c, -h), (h, -h + c), (h, h - c), (h - c, h), (-h + c, h), (-h, h - c), (-h, -h + c), (-h + c, -h)]
    top = 0.46
    mb.prism(out, 0.0, top - c, "Pylon", caps="z", smooth=True)
    ins = [(x * (h - c) / h, y * (h - c) / h) for x, y in out]
    n = len(out)
    for i in range(n):
        a0, a1 = out[i], out[(i + 1) % n]
        b0, b1 = ins[i], ins[(i + 1) % n]
        mb.face(((a0[0], a0[1], top - c), (a1[0], a1[1], top - c), (b1[0], b1[1], top), (b0[0], b0[1], top)),
                "Pylon", None, True)
    mb.face([(x, y, top) for x, y in ins], "Pylon")
    return mb, ["Pylon"]


# ------------------------------------------------------------------------------------------------
def bench():
    """Aluminium team bench, 6 m long, low back; the sitting side faces -Y."""
    mb = MeshBuilder(uv_scale=1.0)
    L = 3.0
    B, St = "BenchSeat", "Steel"
    seat_z = 0.47
    # two seat planks with rolled front/back edges
    for (y0, y1) in ((-0.21, -0.035), (-0.005, 0.17)):
        mb.box((-L, y0 + 0.012, seat_z - 0.045), (L, y1 - 0.012, seat_z), B)
        mb.box((-L, y0, seat_z - 0.04), (L, y0 + 0.012, seat_z - 0.006), B, skip="Y")
        mb.box((-L, y1 - 0.012, seat_z - 0.04), (L, y1, seat_z - 0.006), B, skip="y")
    # back rest: one wide plank leaning back about 12 degrees
    lean = math.radians(12)
    with mb.transform(_tr(0, 0.215, 0.70) @ Matrix.Rotation(-lean, 4, "X")):
        mb.box((-L, -0.018, 0.0), (L, 0.018, 0.21), B)
    # frames
    xs = [-2.72, -1.36, 0.0, 1.36, 2.72]
    for x in xs:
        t = 0.045
        mb.box((x - t / 2, -0.19, 0.0), (x + t / 2, -0.19 + t, seat_z - 0.045), St, skip="zZ")        # front leg
        mb.box((x - t / 2, 0.13, 0.0), (x + t / 2, 0.13 + t, seat_z - 0.045), St, skip="zZ")          # back leg
        mb.box((x - t / 2, -0.30, 0.0), (x + t / 2, 0.36, 0.035), St)                                 # foot
        mb.box((x - t / 2, -0.21, seat_z - 0.085), (x + t / 2, 0.19, seat_z - 0.045), St)             # seat bearer
        mb.beam((x, 0.165, seat_z - 0.06), (x, 0.262, 0.915), t, t, St, up=(0, 1, 0))                  # back post
        mb.beam((x, 0.34, 0.03), (x, 0.20, 0.50), 0.03, 0.03, St, up=(0, 1, 0), caps="")              # brace
    for y in (-0.165, 0.15):
        mb.box((-L + 0.1, y - 0.02, seat_z - 0.10), (L - 0.1, y + 0.02, seat_z - 0.05), St, skip="Z")  # rails
    mb.box((-L + 0.1, -0.02, 0.10), (L - 0.1, 0.02, 0.14), St)                                         # foot rail
    return mb, ["BenchSeat", "Steel"]


# ------------------------------------------------------------------------------------------------
def cooler():
    """Sideline drinks table: folding table, two big coolers, cup stacks. Spigots face -Y."""
    mb = MeshBuilder(uv_scale=1.0)
    C, St = "CoolerBody", "Steel"
    tw, td, tz = 0.92, 0.38, 0.74
    mb.box((-tw, -td, tz - 0.035), (tw, td, tz), St)
    mb.box((-tw + 0.03, -td + 0.03, tz - 0.075), (tw - 0.03, td - 0.03, tz - 0.035), St, skip="Z")
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.cyl_between((sx * (tw - 0.10), sy * (td - 0.07), 0.0), (sx * (tw - 0.10), sy * (td - 0.07), tz - 0.07),
                           0.016, St, segs=8, caps="z")
        mb.cyl_between((sx * (tw - 0.10), -(td - 0.07), 0.16), (sx * (tw - 0.10), (td - 0.07), 0.16), 0.012, St,
                       segs=8, caps="")
        mb.beam((sx * (tw - 0.10), 0.0, 0.16), (sx * 0.25, 0.0, tz - 0.08), 0.02, 0.02, St, caps="")
    for cx in (-0.50, 0.14):
        with mb.transform(_tr(cx, 0.03, tz)):
            mb.lathe([(0.0, 0.0), (0.175, 0.0), (0.195, 0.03), (0.195, 0.44), (0.205, 0.45), (0.205, 0.50),
                      (0.19, 0.52), (0.07, 0.535), (0.07, 0.56), (0.0, 0.56)], C, segs=20)
            # recessed band and handles
            mb.lathe([(0.199, 0.20), (0.199, 0.27)], St, segs=20)
            for sx in (-1, 1):
                mb.box((sx * 0.195 - 0.02, -0.05, 0.36), (sx * 0.195 + 0.02, 0.05, 0.40), C)
            # spigot
            mb.cyl_between((0.0, -0.19, 0.06), (0.0, -0.245, 0.06), 0.017, St, segs=8)
            mb.box((-0.012, -0.262, 0.03), (0.012, -0.238, 0.075), C)
    # cup stacks and loose cups
    def cup(x, y, z, h=0.095, r0=0.03, r1=0.04, mat=C):
        with mb.transform(_tr(x, y, z)):
            mb.lathe([(0.0, 0.0), (r0, 0.0), (r1, h), (r1 - 0.004, h), (r0 - 0.003, 0.012), (0.0, 0.012)], mat, segs=10)

    for (x, y, n) in ((0.56, -0.12, 9), (0.66, -0.12, 6)):
        with mb.transform(_tr(x, y, tz)):
            mb.lathe([(0.0, 0.0), (0.03, 0.0), (0.04, 0.095)], C, segs=10)
            for i in range(1, n):
                mb.lathe([(0.0385, 0.07 + i * 0.016), (0.041, 0.095 + i * 0.016), (0.037, 0.095 + i * 0.016)], C, segs=10)
    for (x, y) in ((0.52, 0.12), (0.63, 0.20), (0.76, 0.05), (-0.20, -0.25), (-0.12, -0.20), (0.80, -0.27), (-0.82, -0.2)):
        cup(x, y, tz)
    return mb, ["CoolerBody", "Steel"]


# ------------------------------------------------------------------------------------------------
def _pole(mb, height_to, sleeve=True):
    St, O = "Steel", "MarkerOrange"
    mb.cylinder(0.035, 0.0, 0.02, St, segs=10, caps="Z")
    mb.cylinder(0.017, 0.02, height_to, St, segs=10, caps="")
    if sleeve:
        mb.lathe([(0.017, 0.26), (0.034, 0.28), (0.034, 1.52), (0.017, 1.54)], O, segs=10)


def chain_pole():
    """First-down stick: 2.4 m, padded pole, round bullseye head facing +-Y."""
    mb = MeshBuilder(uv_scale=2.0)
    St, O = "Steel", "MarkerOrange"
    _pole(mb, 2.12)
    rc, zc, t = 0.15, 2.25, 0.016
    with mb.transform(_tr(0, 0, zc) @ _rot_x(90)):          # local Z -> world -Y
        for sgn in (1, -1):
            z = sgn * t
            rings = [(0.0, 0.055, O), (0.055, 0.105, St), (0.105, rc, O)]
            segs = 24
            for (ra, rb, m) in rings:
                for k in range(segs):
                    a0, a1 = 2 * math.pi * k / segs, 2 * math.pi * (k + 1) / segs
                    pa = (ra * math.cos(a0), ra * math.sin(a0), z)
                    pb = (rb * math.cos(a0), rb * math.sin(a0), z)
                    pc = (rb * math.cos(a1), rb * math.sin(a1), z)
                    pd = (ra * math.cos(a1), ra * math.sin(a1), z)
                    if ra < 1e-9:
                        f = (pa, pb, pc)
                    else:
                        f = (pa, pb, pc, pd)
                    mb.face(f if sgn > 0 else f[::-1], m)
        mb.cylinder(rc, -t, t, O, segs=24, caps="")
    mb.box((-0.03, -0.02, 2.07), (0.03, 0.02, 2.13), St)          # clamp
    return mb, ["MarkerOrange", "Steel"]


def down_box():
    """Down marker: pole with a square box on top; each side carries a blank DownFace (UV 0..1)."""
    mb = MeshBuilder(uv_scale=2.0)
    St, O, F = "Steel", "MarkerOrange", "DownFace"
    _pole(mb, 2.06)
    h = 0.17                                    # half width of the box
    z0, z1 = 2.06, 2.40
    b = 0.028                                   # frame border
    inset = 0.008
    mb.box((-h, -h, z0), (h, h, z1), O, skip="xXyY")
    for k in range(4):
        with mb.transform(_rot_z(90 * k)):
            y = -h
            # frame ring around the face
            for (xa, xb, za, zb) in ((-h, h, z0, z0 + b), (-h, h, z1 - b, z1), (-h, -h + b, z0 + b, z1 - b),
                                     (h - b, h, z0 + b, z1 - b)):
                mb.quad((xa, y, za), (xb, y, za), (xb, y, zb), (xa, y, zb), O)
            xa, xb, za, zb = -h + b, h - b, z0 + b, z1 - b
            yi = y + inset
            mb.quad((xa, y, za), (xb, y, za), (xb, yi, za), (xa, yi, za), O)
            mb.quad((xa, yi, zb), (xb, yi, zb), (xb, y, zb), (xa, y, zb), O)
            mb.quad((xa, y, za), (xa, yi, za), (xa, yi, zb), (xa, y, zb), O)
            mb.quad((xb, yi, za), (xb, y, za), (xb, y, zb), (xb, yi, zb), O)
            mb.quad((xa, yi, za), (xb, yi, za), (xb, yi, zb), (xa, yi, zb), F, uv=((0, 0), (1, 0), (1, 1), (0, 1)))
    # carry handle on top
    for sx in (-0.07, 0.07):
        mb.box((sx - 0.008, -0.008, z1), (sx + 0.008, 0.008, z1 + 0.05), St, skip="zZ")
    mb.box((-0.078, -0.008, z1 + 0.05), (0.078, 0.008, z1 + 0.066), St)
    return mb, ["MarkerOrange", "Steel", "DownFace"]


# ------------------------------------------------------------------------------------------------
def tv_camera():
    """Broadcast camera on a rolling pedestal, about 2 m tall, lens toward -Y."""
    mb = MeshBuilder(uv_scale=1.0)
    C, G = "CameraBody", "Glass"
    # three-legged dolly with twin casters
    for k in range(3):
        ang = math.radians(90 + 120 * k)
        ex, ey = 0.52 * math.cos(ang), 0.52 * math.sin(ang)
        mb.beam((0, 0, 0.17), (ex, ey, 0.17), 0.11, 0.07, C, caps="Z")
        with mb.transform(_tr(ex, ey, 0)):
            mb.cylinder(0.035, 0.085, 0.20, C, segs=8)
            with mb.transform(_rot_z(math.degrees(ang) + 90)):
                for sx in (-0.045, 0.045):
                    mb.cyl_between((sx - 0.018, 0, 0.07), (sx + 0.018, 0, 0.07), 0.07, C, segs=12)
    mb.cylinder(0.17, 0.12, 0.26, C, segs=16)
    # telescoping column
    mb.lathe([(0.125, 0.26), (0.125, 0.86), (0.10, 0.88), (0.085, 0.88), (0.085, 1.22), (0.11, 1.24),
              (0.11, 1.30), (0.0, 1.30)], C, segs=16)
    # steering ring on three spokes
    ring = [(0.33 * math.cos(2 * math.pi * k / 20), 0.33 * math.sin(2 * math.pi * k / 20), 0.80) for k in range(20)]
    mb.tube(ring, 0.014, C, segs=6, closed=True)
    for k in range(3):
        ang = math.radians(30 + 120 * k)
        mb.cyl_between((0.12 * math.cos(ang), 0.12 * math.sin(ang), 0.74),
                       (0.33 * math.cos(ang), 0.33 * math.sin(ang), 0.80), 0.011, C, segs=6, caps="")
    # fluid head
    mb.box((-0.13, -0.15, 1.30), (0.13, 0.15, 1.40), C)
    mb.cyl_between((-0.16, 0, 1.36), (0.16, 0, 1.36), 0.055, C, segs=12)
    # camera body
    z0, z1 = 1.40, 1.72
    mb.box((-0.16, -0.26, z0), (0.16, 0.40, z1), C)
    mb.box((-0.175, -0.05, z0 + 0.04), (0.175, 0.30, z1 - 0.05), C, skip="yY")      # side panels
    mb.box((-0.10, 0.40, z0 + 0.05), (0.10, 0.44, z1 - 0.06), C, skip="y")           # rear connector panel
    # box lens with a flared hood
    mb.box((-0.135, -0.84, z0 + 0.02), (0.135, -0.26, z1 - 0.02), C, skip="Yy")
    ya, yb = -0.84, -0.99
    xa, xb, za, zb = 0.135, 0.185, z0 + 0.02, z1 - 0.02
    zc, zd = za - 0.045, zb + 0.045
    front = [(-xb, yb, zc), (xb, yb, zc), (xb, yb, zd), (-xb, yb, zd)]
    back = [(-xa, ya, za), (xa, ya, za), (xa, ya, zb), (-xa, ya, zb)]
    for i in range(4):
        j = (i + 1) % 4
        mb.face((back[j], back[i], front[i], front[j]), C)           # outside of the hood
        mb.face((back[i], back[j], front[j], front[i]), C)           # inside
    mb.quad(back[0], back[1], back[2], back[3], C)
    with mb.transform(_tr(0, ya - 0.004, 0.5 * (za + zb)) @ _rot_x(90)):
        mb.lathe([(0.0, 0.0), (0.105, 0.0)], G, segs=20)             # front element, faces -Y
        mb.lathe([(0.105, 0.0), (0.125, 0.0), (0.125, -0.02)], C, segs=20)
    # viewfinder with hood, facing the operator (+Y)
    vz0, vz1 = z1 + 0.03, z1 + 0.25
    mb.box((-0.03, 0.10, z1), (0.03, 0.20, vz0), C)
    mb.box((-0.15, 0.08, vz0), (0.15, 0.30, vz1), C, skip="Y")
    mb.quad((0.13, 0.30, vz0 + 0.02), (-0.13, 0.30, vz0 + 0.02), (-0.13, 0.30, vz1 - 0.02), (0.13, 0.30, vz1 - 0.02), G)
    for (xa2, xb2, za2, zb2) in ((-0.15, 0.15, vz0, vz0 + 0.02), (-0.15, 0.15, vz1 - 0.02, vz1),
                                 (-0.15, -0.13, vz0 + 0.02, vz1 - 0.02), (0.13, 0.15, vz0 + 0.02, vz1 - 0.02)):
        mb.quad((xb2, 0.30, za2), (xa2, 0.30, za2), (xa2, 0.30, zb2), (xb2, 0.30, zb2), C)
    mb.box((-0.16, 0.30, vz1 - 0.012), (0.16, 0.40, vz1), C)                       # sun shade
    mb.box((-0.035, -0.20, z1), (0.035, -0.12, z1 + 0.045), C)                     # tally light
    # pan handles
    for sx in (-1, 1):
        p0 = (sx * 0.15, 0.10, 1.36)
        p1 = (sx * 0.27, 0.66, 1.17)
        mb.cyl_between(p0, p1, 0.013, C, segs=6, caps="")
        d = (Vector(p1) - Vector(p0)).normalized()
        p2 = tuple(Vector(p1) + d * 0.16)
        mb.cyl_between(p1, p2, 0.022, C, segs=8)
    return mb, ["CameraBody", "Glass"]


ALL = {
    "SM_Goalpost": goalpost,
    "SM_Football": football,
    "SM_KickTee": kick_tee,
    "SM_Pylon": pylon,
    "SM_Bench": bench,
    "SM_Cooler": cooler,
    "SM_ChainPole": chain_pole,
    "SM_DownBox": down_box,
    "SM_Camera": tv_camera,
}
