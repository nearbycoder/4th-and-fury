"""Sideline ad boards: T_Ads.png, 8192 x 512 = eight 1024 x 512 cells side by side.

A board is shown 6 m x 1 m, so each design is a 6 : 1 banner living in the middle
1024 x 170 band of its cell; the background (colour and pattern) carries on to fill the
whole cell so nothing odd shows if the sampling strays or the mips blur.

Sponsors are all invented for the game (and one board is the game's own):
  0 4TH & FURY            the game
  1 THIRST DOWN           sports drink
  2 BIG HANK'S TRUCK BARN truck dealership
  3 CRYIN' BRIAN'S        hot wings
  4 OAT FIST              energy bar
  5 THE BED ZONE          mattress superstore
  6 FUMBLE MUTUAL         insurance
  7 REF SPECS             opticians
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import common as cm
from . import noise as nz
from . import title as title_art
from . import vec
from .logos import tongue

CW, CH = 1024, 512
SS = 4
BAND = CH / 3.0  # 170.67
BY0, BY1, BC = (CH - BAND) / 2.0, (CH + BAND) / 2.0, CH / 2.0
N = 8


class Board:
    """One 1024 x 512 cell. All coordinates are 1x cell pixels; y = 256 is the band's centre."""

    def __init__(self, bg):
        self.c = vec.Canvas(CW, CH, SS, bg=cm.rgb(bg) if isinstance(bg, str) else bg)
        self.shape = (CH * SS, CW * SS)

    # ---- shapes
    def mask(self, polys=(), holes=(), strokes=()) -> np.ndarray:
        return vec.f32(vec.raster((CW * SS, CH * SS), polys, holes, strokes, xf=(SS, 0, 0)))

    def fill(self, color, polys=(), holes=(), strokes=(), opacity=1.0, outline=None, shadow=None) -> np.ndarray:
        m = self.mask(polys, holes, strokes)
        col = cm.rgb(color) if isinstance(color, str) else color
        if shadow:
            sc, dx, dy = shadow
            self.c.paint(vec.shift_mask(m, int(dx * SS), int(dy * SS)), cm.rgb(sc))
        if outline:
            oc, ow = outline
            self.c.paint(vec.dilate(m, ow * SS), cm.rgb(oc))
        self.c.paint(m, col, opacity)
        return m

    def gradient(self, top, bottom, y0=0.0, y1=CH) -> None:
        yy = np.clip((np.arange(CH * SS, dtype=np.float32) / SS - y0) / (y1 - y0), 0, 1)[:, None, None]
        self.c.buf[..., :3] = cm.rgb(top) * (1 - yy) + cm.rgb(bottom) * yy

    # ---- lettering
    def text(self, s, font, x, y, color, cap=None, h=None, anchor="lm", track=0.0, max_w=None, shear=0.0,
             outline=None, shadow=None, opacity=1.0):
        """Draw a line of text. Size by `cap` (height of a capital H) or `h` (ink height of
        the string). Anchor is the ink box: l/m/r + t/m/b. `outline` = (colour, width) or a
        list of them (inner first); `shadow` = (colour, dx, dy). Returns the ink box."""
        path = cm.font_path(font)
        probe = 240.0
        if cap is not None:
            _, _, ph = vec.text_ink("H", path, probe)
            size = probe * cap * SS / ph
        else:
            _, _, ph = vec.text_ink(s, path, probe, track * probe)
            size = probe * h * SS / ph
        m, w, hh = vec.text_ink(s, path, size, track * size)
        if max_w is not None and w > max_w * SS:
            size *= max_w * SS / w
            m, w, hh = vec.text_ink(s, path, size, track * size)
        if shear:
            extra = int(math.ceil(abs(shear) * hh))
            img = Image.fromarray(m).transform((w + extra, hh), Image.AFFINE,
                                               (1, shear, -shear * hh if shear > 0 else 0, 0, 1, 0), resample=Image.BICUBIC)
            m = np.asarray(img)
            w = m.shape[1]
        ax = {"l": 0.0, "m": w / 2.0, "r": float(w)}[anchor[0]]
        ay = {"t": 0.0, "m": hh / 2.0, "b": float(hh)}[anchor[1]]
        x0, y0 = x * SS - ax, y * SS - ay
        full = vec.place(self.shape, m, x0, y0)
        outlines = [outline] if isinstance(outline, tuple) else (outline or [])
        grown = [full]
        for _, ow in outlines:
            grown.append(vec.dilate(grown[-1], ow * SS))
        if shadow:
            sc, dx, dy = shadow
            self.c.paint(vec.shift_mask(grown[-1], int(dx * SS), int(dy * SS)), cm.rgb(sc))
        for (oc, _), g in reversed(list(zip(outlines, grown[1:]))):
            self.c.paint(g, cm.rgb(oc))
        self.c.paint(full, cm.rgb(color) if isinstance(color, str) else color, opacity)
        return (x0 / SS, y0 / SS, (x0 + w) / SS, (y0 + hh) / SS)

    def result(self) -> np.ndarray:
        return self.c.result_rgb()


def rrect(x0, y0, x1, y1, r):
    return vec.round_corners(vec.rect(x0, y0, x1, y1), r, n=8)


def slant(x0, y0, x1, y1, k=0.22):
    """A parallelogram leaning to the right."""
    d = (y1 - y0) * k
    return vec.pts((x0 + d, y0), (x1 + d, y0), (x1, y1), (x0, y1))


def diagonals(b: Board, color, pitch, width, k=0.6, opacity=1.0, y0=0.0, y1=CH, x0=-CH, x1=CW + CH):
    polys = []
    d = (y1 - y0) * k
    for x in np.arange(x0, x1, pitch):
        polys.append(vec.pts((x + d, y0), (x + d + width, y0), (x + width, y1), (x, y1)))
    b.fill(color, polys, opacity=opacity)


# =========================================================================== the boards
def board_fury() -> np.ndarray:
    b = Board("#10121B")
    b.gradient("#0B0C13", "#1B1E2C")
    diagonals(b, "#FFFFFF", 46, 16, opacity=0.035)
    # hot bars along the top and bottom of the banner
    for y, col in ((BY0 + 5, "#FF8A14"), (BY1 - 11, "#FF8A14")):
        b.fill(col, [vec.rect(0, y, CW, y + 6)])
    # the compact title, drawn straight at the working resolution (640 x 160 once reduced)
    art = title_art.render_small(ss=1, width=640 * SS, height=160 * SS).astype(np.float32) / 255.0
    b.c.paint_rgba(art, int(8 * SS), int((BC - 80 - 4) * SS))
    b.fill("#FFB81C", [slant(664, BC - 52, 672, BC + 52, 0.20)])
    b.text("GO FOR IT.", "barlow-blackitalic", 696, BC - 25, "#FFFFFF", cap=37, anchor="lm", track=0.02, max_w=290)
    b.text("EVERY TIME.", "barlow-blackitalic", 688, BC + 26, "#FFC21A", cap=37, anchor="lm", track=0.02, max_w=300)
    return b.result()


def board_thirst() -> np.ndarray:
    b = Board("#0A6FD0")
    b.gradient("#0B8AE8", "#0652B0")
    diagonals(b, "#FFFFFF", 150, 54, k=0.9, opacity=0.07)
    diagonals(b, "#062E73", 150, 12, k=0.9, opacity=0.25, x0=-CH + 70)
    # a drop that is also a first-down arrow
    cx, cy = 88, BC + 4
    drop = vec.blob([(cx, cy - 66, "c"), (cx + 30, cy - 18), (cx + 44, cy + 22), (cx + 26, cy + 56), (cx, cy + 66),
                     (cx - 26, cy + 56), (cx - 44, cy + 22), (cx - 30, cy - 18)], k=0.36)
    b.fill("#C8FF3A", [drop], outline=("#04255E", 6), shadow=("#04255E", 5, 6))
    arrow = vec.pts((cx - 24, cy + 14), (cx + 2, cy + 14), (cx + 2, cy - 2), (cx + 28, cy + 26), (cx + 2, cy + 54),
                    (cx + 2, cy + 38), (cx - 24, cy + 38))
    b.fill("#04255E", [vec.round_corners(arrow, 2.5)])
    b.fill("#FFFFFF", [vec.ellipse(cx - 14, cy - 12, 6, 12, rot=18)], opacity=0.85)
    x0, _, x1, _ = b.text("THIRST DOWN", "fugaz", 160, BC - 16, "#FFFFFF", cap=76, anchor="lm", track=0.01, max_w=560,
                          outline=[("#04255E", 6)], shadow=("#C8FF3A", 5, 6))
    b.text("SPORTS DRINK", "barlow-extrabold", 164, BC + 58, "#C8FF3A", cap=22, anchor="lm", track=0.20)
    b.fill("#C8FF3A", [slant(748, BC - 52, 756, BC + 52, 0.22)])
    b.text("MOVE", "barlow-blackitalic", 782, BC - 34, "#FFFFFF", cap=30, anchor="lm", track=0.03)
    b.text("THE CHAINS", "barlow-blackitalic", 775, BC + 5, "#FFFFFF", cap=30, anchor="lm", track=0.03)
    b.text("ELECTROLYTES & HUSTLE", "barlow-bold", 767, BC + 44, "#9FD6FF", cap=15, anchor="lm", track=0.08)
    return b.result()


def board_hank() -> np.ndarray:
    b = Board("#F2B705")
    b.gradient("#F7C416", "#E9A800")
    # hazard chevrons at both ends
    for x0, x1 in ((0, 22), (CW - 22, CW)):
        b.fill("#17130D", [vec.rect(x0, 0, x1, CH)])
    # a lifted pickup, all tyre
    def truck(ox, oy, s=1.0):
        body = vec.pts((0, 58), (0, 30), (56, 30), (64, 6), (112, 6), (128, 30), (168, 34), (172, 58))
        window = vec.pts((70, 12), (108, 12), (118, 30), (66, 30))
        parts = [vec.round_corners(body, 5), vec.rect(4, 56, 170, 66)]
        wheels = [vec.ellipse(38, 70, 27), vec.ellipse(134, 70, 27)]
        hubs = [vec.ellipse(38, 70, 10), vec.ellipse(134, 70, 10)]
        T = lambda p: np.asarray(p) * s + (ox, oy)  # noqa: E731
        return [T(p) for p in parts], [T(window)], [T(p) for p in wheels], [T(p) for p in hubs]

    body, window, wheels, hubs = truck(44, BC - 58, 0.98)
    b.fill("#B3171C", body, outline=("#17130D", 4))
    b.fill("#F7E7B4", window)
    b.fill("#17130D", wheels)
    b.fill("#F2B705", hubs)
    b.text("BIG HANK'S", "alfaslab", 240, BC - 22, "#17130D", cap=66, anchor="lm", max_w=430, shadow=("#B3171C", 4, 5))
    plate = slant(238, BC + 30, 668, BC + 70, 0.20)
    b.fill("#B3171C", [plate])
    b.text("TRUCK BARN", "barlow-black", 462, BC + 50.5, "#FFF3D0", cap=25, anchor="mm", track=0.30)
    b.fill("#17130D", [slant(700, BC - 54, 707, BC + 54, 0.20)])
    b.text("MORE TRUCK", "barlow-blackitalic", 734, BC - 32, "#17130D", cap=33, anchor="lm", track=0.02, max_w=236)
    b.text("THAN YOU NEED", "barlow-blackitalic", 727, BC + 12, "#B3171C", cap=33, anchor="lm", track=0.02, max_w=240)
    b.text("0% SHAME FINANCING", "barlow-bold", 720, BC + 50, "#17130D", cap=15, anchor="lm", track=0.10)
    return b.result()


def board_wings() -> np.ndarray:
    b = Board("#E8300C")
    b.gradient("#F2420E", "#C81A0A")
    r = nz.rng(6201)
    # flames along the bottom of the whole cell and of the banner
    for base, hmin, hmax, col, op in ((CH, 60, 150, "#FF8A14", 1.0), (BY1 + 4, 34, 86, "#FF8A14", 1.0), (BY1 + 4, 16, 46, "#FFD21A", 1.0)):
        polys = [vec.rect(0, base - 6, CW, base + 6)]
        x = -20.0
        while x < CW + 20:
            hgt = r.uniform(hmin, hmax)
            polys.append(tongue((x, base), (x - r.uniform(0.1, 0.4) * hgt, base - hgt), r.uniform(34, 56), bow=r.uniform(0.08, 0.2), belly=0.3))
            x += r.uniform(26, 44)
        b.fill(col, polys, opacity=op)
    b.fill("#C81A0A", [vec.rect(0, BY1 + 4, CW, CH)], opacity=0.0)
    # a drumette, crying
    cx, cy = 92, BC - 6
    meat = vec.blob([(cx - 48, cy - 26), (cx - 12, cy - 48), (cx + 30, cy - 34), (cx + 46, cy + 2), (cx + 26, cy + 36),
                     (cx - 16, cy + 42), (cx - 50, cy + 16)], k=0.37)
    bone = [(vec.pts((cx + 30, cy + 22), (cx + 66, cy + 54)), 15, False)]
    knobs = [vec.ellipse(cx + 62, cy + 62, 11), vec.ellipse(cx + 74, cy + 50, 11)]
    b.fill("#FFF1D6", knobs, strokes=bone, outline=("#5A0A04", 4))
    b.fill("#D9760F", [meat], outline=("#5A0A04", 5))
    b.fill("#F5A533", [vec.blob([(cx - 34, cy - 22), (cx - 8, cy - 36), (cx + 14, cy - 28), (cx - 4, cy - 14), (cx - 28, cy - 6)])])
    eye = [vec.ellipse(cx - 18, cy + 4, 5.5), vec.ellipse(cx + 12, cy + 2, 5.5)]
    b.fill("#5A0A04", eye, strokes=[(vec.arc(cx - 3, cy + 30, 13, 200, 340, 10), 4.5, False)])
    tears = [vec.blob([(x, y - 13, "c"), (x + 6, y), (x, y + 7), (x - 6, y)]) for x, y in ((cx - 24, cy + 24), (cx + 20, cy + 22), (cx + 24, cy + 44))]
    b.fill("#9FE4FF", tears, outline=("#0A4A7A", 2.5))
    b.text("CRYIN' BRIAN'S", "bangers", 172, BC - 20, "#FFD21A", cap=74, anchor="lm", track=0.02, max_w=520,
           outline=[("#5A0A04", 6)], shadow=("#5A0A04", 5, 6))
    b.fill("#5A0A04", [slant(170, BC + 34, 470, BC + 72, 0.2)])
    b.text("HOT WINGS", "barlow-black", 322, BC + 53.5, "#FFFFFF", cap=24, anchor="mm", track=0.30)
    b.fill("#5A0A04", [slant(484, BC + 40, 694, BC + 66, 0.2)], opacity=0.55)
    b.text("EST. LAST TUESDAY", "barlow-bold", 500, BC + 53.5, "#FFFFFF", cap=14, anchor="lm", track=0.12)
    b.fill("#FFD21A", [slant(722, BC - 54, 729, BC + 54, 0.2)])
    b.text("YOU'LL CRY.", "barlow-blackitalic", 756, BC - 28, "#FFFFFF", cap=36, anchor="lm", track=0.02, max_w=236,
           shadow=("#5A0A04", 3, 3))
    b.text("IT'S FINE.", "barlow-blackitalic", 748, BC + 22, "#FFD21A", cap=36, anchor="lm", track=0.02,
           shadow=("#5A0A04", 3, 3))
    return b.result()


def board_oat() -> np.ndarray:
    b = Board("#E7D4A6")
    b.gradient("#EDDCB2", "#DDC692")
    r = nz.rng(6301)
    # oat flecks in the kraft-paper ground
    flecks = [vec.ellipse(r.uniform(0, CW), r.uniform(0, CH), r.uniform(3, 7), r.uniform(1.5, 3), rot=r.uniform(0, 180)) for _ in range(520)]
    b.fill("#B99657", flecks[:300], opacity=0.55)
    b.fill("#F8EED2", flecks[300:], opacity=0.75)
    ink, red = "#3A2413", "#D9480F"
    # a fist made of oat-bar slabs
    x, y = 46, BC - 54
    fingers = [rrect(x + 4 + i * 24, y + 6 - (3 if i in (1, 2) else 0), x + 26 + i * 24, y + 60, 7) for i in range(4)]
    palm = rrect(x, y + 44, x + 104, y + 106, 13)
    thumb = vec.round_corners(vec.pts((x + 56, y + 62), (x + 118, y + 50), (x + 126, y + 74), (x + 66, y + 90)), 8)
    b.fill("#C98A3A", fingers + [palm], outline=(ink, 5), shadow=(ink, 5, 6))
    b.fill("#DDA24E", [thumb], outline=(ink, 4.5))
    b.fill(ink, strokes=[(vec.pts((x + 14, y + 26), (x + 16, y + 26)), 5, False), (vec.pts((x + 38, y + 23), (x + 40, y + 23)), 5, False),
                         (vec.pts((x + 62, y + 23), (x + 64, y + 23)), 5, False), (vec.pts((x + 86, y + 26), (x + 88, y + 26)), 5, False)])
    for px_, py_ in ((x - 20, y + 10), (x - 30, y + 46), (x - 18, y + 84)):  # speed lines: it is mid-punch
        b.fill(ink, [slant(px_ - 2, py_, px_ + 22, py_ + 6, 0.0)])
    b.text("OAT FIST", "blackops", 196, BC - 14, ink, cap=82, anchor="lm", track=0.02, max_w=470, shadow=(red, 5, 6))
    b.fill(red, [rrect(198, BC + 44, 384, BC + 74, 5)])
    b.text("ENERGY BAR", "barlow-black", 291, BC + 59.5, "#FFF3D0", cap=18, anchor="mm", track=0.28)
    b.text("900 CALORIES OF HUSTLE", "barlow-bold", 400, BC + 60, ink, cap=15, anchor="lm", track=0.10)
    b.fill(ink, [slant(700, BC - 54, 707, BC + 54, 0.2)])
    b.text("PUNCH HUNGER", "barlow-blackitalic", 734, BC - 26, ink, cap=34, anchor="lm", track=0.01, max_w=256)
    b.text("IN THE MOUTH", "barlow-blackitalic", 726, BC + 22, red, cap=34, anchor="lm", track=0.01, max_w=256)
    return b.result()


def board_bed() -> np.ndarray:
    b = Board("#1B1F4E")
    b.gradient("#141845", "#2B2470")
    r = nz.rng(6401)
    stars = []
    for _ in range(150):
        x, y, s = r.uniform(0, CW), r.uniform(0, CH), r.uniform(1.6, 4.4)
        stars.append(vec.pts((x, y - s * 1.7), (x + s * 0.5, y - s * 0.5), (x + s * 1.7, y), (x + s * 0.5, y + s * 0.5),
                             (x, y + s * 1.7), (x - s * 0.5, y + s * 0.5), (x - s * 1.7, y), (x - s * 0.5, y - s * 0.5)))
    b.fill("#FFF4C2", stars[:90], opacity=0.55)
    b.fill("#B9C3FF", stars[90:], opacity=0.75)
    # a crescent moon tucked up on a pillow
    cx, cy = 86, BC - 10
    moon = b.mask([vec.ellipse(cx, cy, 50)]) * (1.0 - b.mask([vec.ellipse(cx + 24, cy - 12, 44)]))
    b.c.paint(vec.dilate(moon, 4 * SS), cm.rgb("#0C0F33"))
    b.c.paint(moon, cm.rgb("#FFE38A"))
    pillow = vec.blob([(cx - 62, cy + 44), (cx - 30, cy + 38), (cx + 30, cy + 38), (cx + 64, cy + 44), (cx + 60, cy + 70),
                       (cx, cy + 76), (cx - 60, cy + 70)], k=0.3)
    b.fill("#F2F0FF", [pillow], outline=("#0C0F33", 4))
    for zx, zy, zs in ((cx + 34, cy - 26, 15), (cx + 58, cy - 48, 20), (cx + 88, cy - 68, 13)):
        b.text("Z", "barlow-blackitalic", zx, zy, "#B9C3FF", cap=zs, anchor="mm")
    b.text("The Bed Zone", "pacifico", 190, BC - 14, "#FFE9A8", h=104, anchor="lm", max_w=500, shadow=("#0C0F33", 4, 5))
    b.text("MATTRESS SUPERSTORE", "barlow-semibold", 196, BC + 62, "#B9C3FF", cap=17, anchor="lm", track=0.30)
    b.fill("#FFE38A", [rrect(716, BC - 44, 1000, BC + 6, 25)], shadow=("#0C0F33", 4, 5))
    b.text("EVERYTHING", "barlow-black", 858, BC - 19, "#1B1F4E", cap=25, anchor="mm", track=0.12)
    b.text("MUST DOZE", "barlow-blackitalic", 858, BC + 38, "#FFE9A8", cap=34, anchor="mm", track=0.04)
    return b.result()


def board_fumble() -> np.ndarray:
    b = Board("#F3F5F2")
    green, deep, grey = "#0B6B3A", "#084D2A", "#5E6B63"
    b.fill("#E4E9E3", [vec.rect(0, BC + 46, CW, CH)])
    b.fill(green, [vec.pts((0, 0), (196, 0), (150, CH), (0, CH))])
    b.fill(deep, [vec.pts((196, 0), (212, 0), (166, CH), (150, CH))])
    # a shield, and the ball that has just squirted out of it
    cx, cy = 86, BC
    shield = vec.svg(f"M {cx} {cy - 62} L {cx + 50} {cy - 46} L {cx + 50} {cy - 2} C {cx + 50} {cy + 30} {cx + 28} {cy + 52} {cx} {cy + 64} "
                     f"C {cx - 28} {cy + 52} {cx - 50} {cy + 30} {cx - 50} {cy - 2} L {cx - 50} {cy - 46} Z")
    b.fill("#FFFFFF", shield)
    ball = vec.svg("M -30 0 C -17 -20 17 -20 30 0 C 17 20 -17 20 -30 0 Z")[0]
    bp = vec.rotate(ball, -32) + (cx + 2, cy - 2)
    b.fill(green, [bp])
    laces = [(vec.rotate(vec.pts((-10, 0), (10, 0)), -32) + (cx + 2, cy - 2), 3.2, False)]
    laces += [(vec.rotate(vec.pts((x, -5), (x, 5)), -32) + (cx + 2, cy - 2), 2.8, False) for x in (-7, 0, 7)]
    b.fill("#FFFFFF", strokes=laces)
    b.fill("#FFFFFF", strokes=[(vec.arc(cx + 30, cy - 30, 26, 200, 250, 8), 3.5, False), (vec.arc(cx + 34, cy - 34, 38, 205, 245, 8), 3.5, False)],
           opacity=0.0)
    b.text("FUMBLE MUTUAL", "dmserif", 236, BC - 18, green, cap=62, anchor="lm", max_w=520)
    b.fill(green, [vec.rect(238, BC + 26, 756, BC + 29)])
    b.text("INSURANCE  ·  SINCE THE LAST TIME", "barlow-semibold", 238, BC + 52, grey, cap=16, anchor="lm", track=0.24)
    b.fill(grey, [vec.rect(790, BC - 50, 792, BC + 50)], opacity=0.5)
    b.text("Oops", "dmserif", 818, BC - 22, deep, h=52, anchor="lm")
    b.text("happens.", "dmserif", 818, BC + 30, green, h=44, anchor="lm")
    return b.result()


def board_ref() -> np.ndarray:
    b = Board("#FFD400")
    b.gradient("#FFDC1F", "#F7C600")
    ink = "#15151A"
    # referee stripes on the end panels
    for x0, x1, lean in ((0, 150, 1), (CW - 150, CW, -1)):
        panel = vec.pts((x0, 0), (x1, 0), (x1, CH), (x0, CH))
        b.fill("#F6F6F2", [panel])
        b.fill(ink, [vec.rect(x, 0, x + 21, CH) for x in np.arange(x0 + (0 if lean > 0 else 3), x1, 42)])
    b.fill(ink, [vec.rect(147, 0, 156, CH), vec.rect(CW - 156, 0, CW - 147, CH)])
    # glasses
    cx, cy, rr = 262, BC - 14, 35
    lenses = [vec.ellipse(cx - 42, cy, rr), vec.ellipse(cx + 42, cy, rr)]
    inner = [vec.ellipse(cx - 42, cy, rr - 9), vec.ellipse(cx + 42, cy, rr - 9)]
    b.fill("#FFFFFF", inner, opacity=0.70)
    b.fill(ink, lenses, holes=inner,
           strokes=[(vec.arc(cx, cy + 4, 12, 200, 340, 8), 8, False), (vec.pts((cx - 74, cy - 8), (cx - 96, cy - 22)), 8, False),
                    (vec.pts((cx + 74, cy - 8), (cx + 96, cy - 22)), 8, False)])
    b.fill(ink, strokes=[(vec.pts((cx - 56, cy - 6), (cx - 44, cy - 16)), 4, False), (vec.pts((cx + 28, cy - 6), (cx + 40, cy - 16)), 4, False)])
    b.text("REF SPECS", "anton", 376, BC - 16, ink, cap=76, anchor="lm", track=0.03, max_w=330)
    b.text("OFFICIAL EYEWEAR OF THE OFFICIALS", "barlow-black", 178, BC + 52, ink, cap=17, anchor="lm", track=0.13, max_w=540)
    b.fill(ink, [slant(730, BC - 52, 737, BC + 52, 0.18)])
    b.text("SEE THE", "barlow-blackitalic", 762, BC - 27, ink, cap=31, anchor="lm", track=0.02, max_w=100)
    b.text("HOLD.", "barlow-blackitalic", 755, BC + 20, "#B3171C", cap=38, anchor="lm", track=0.02, max_w=100)
    return b.result()


BOARDS = [board_fury, board_thirst, board_hank, board_wings, board_oat, board_bed, board_fumble, board_ref]


def build() -> list[str]:
    cm.ensure_dirs()
    cells = [fn() for fn in BOARDS]
    atlas = np.concatenate(cells, axis=1)
    assert atlas.shape == (CH, CW * N, 3)
    cm.save_png(atlas, "T_Ads.png")
    # preview 1: the eight banners as shown in the stadium (the middle band of each cell), near 1:1
    y0, y1 = int(round(BY0)), int(round(BY1))
    bands = [Image.fromarray(c[y0:y1], "RGB") for c in cells]
    cm.save_preview(cm.vstack(bands, gap=6), "T_Ads.png")
    # preview 2: the whole cells, to check the background fill around each band
    rows = [cm.hstack([Image.fromarray(c, "RGB").resize((340, 170), Image.LANCZOS) for c in cells[i : i + 4]], gap=4) for i in (0, 4)]
    cm.save_preview(cm.vstack(rows, gap=0), "T_Ads_cells.png")
    return ["T_Ads.png"]
