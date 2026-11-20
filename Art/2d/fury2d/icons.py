"""UI icons: 256 x 256, white on transparent, so the engine can tint them.

Each icon is drawn in a 100 x 100 design box. RGB is pure white everywhere (no dark
fringe when filtered); the shape lives in the alpha channel.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import common as cm
from . import vec

SIZE = 256
SS = 8
U = SIZE * SS / 100.0  # design unit -> supersampled pixels


def _mask(polys=(), holes=(), strokes=(), cut_strokes=()) -> np.ndarray:
    """Union of polys/strokes minus holes/cut_strokes, as float32 0..1 at SS resolution."""
    size = (SIZE * SS, SIZE * SS)
    m = vec.f32(vec.raster(size, polys, (), strokes, xf=(U, 0, 0)))
    if holes or cut_strokes:
        cut = vec.f32(vec.raster(size, holes, (), cut_strokes, xf=(U, 0, 0)))
        m = m * (1.0 - cut)
    return m


def _rrect(x0, y0, x1, y1, r):
    return vec.round_corners(vec.rect(x0, y0, x1, y1), r, n=8)


# --------------------------------------------------------------------------- the icons
def flame():
    outer = vec.svg("M 53 4 C 57 22 80 35 81 61 C 82 81 68 96 50 96 C 32 96 18 82 19 63 "
                    "C 19 50 27 42 30 31 C 34 41 38 46 43 47 C 40 32 45 15 53 4 Z")
    inner = vec.svg("M 52 55 C 60 63 65 72 63 81 C 61 89 56 92 50 92 C 43 92 37 87 37 79 "
                    "C 37 72 41 68 44 62 C 46 66 48 68 51 67 C 50 62 50 58 52 55 Z")
    return _mask(outer, inner)


def ball():
    c = (50.0, 50.0)
    body = vec.svg("M -45 0 C -25 -31 25 -31 45 0 C 25 31 -25 31 -45 0 Z")
    cuts = [(vec.pts((-17, 0), (17, 0)), 3.4, False)]
    for x in (-14, -7, 0, 7, 14):
        cuts.append((vec.pts((x, -6.2), (x, 6.2)), 3.2, False))
    for s in (-1, 1):  # the two end stripes, bowed like the ball's surface
        cuts.append((vec.quadratic((s * 27.5, -15.5), (s * 32.5, 0), (s * 27.5, 15.5), 12), 3.6, False))
        cuts[-1] = (np.concatenate([[(s * 27.5, -15.5)], cuts[-1][0]]), 3.6, False)

    def place(p):
        return vec.rotate(np.asarray(p), -36.0) + c

    return _mask([place(p) for p in body], cut_strokes=[(place(p), w, cl) for p, w, cl in cuts])


def star():
    cx, cy, R, r = 50.0, 53.5, 47.0, 20.5
    pts_ = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rad = R if i % 2 == 0 else r
        pts_.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return _mask([vec.round_corners(pts_, 2.6)])


def bolt():
    p = [(63, 4), (20, 57), (44, 57), (33, 96), (80, 40), (55, 40), (73, 4)]
    return _mask([vec.round_corners(p, 2.0)])


def shield():
    outer = vec.svg("M 50 5 L 87 17 L 87 47 C 87 70 71 87 50 96 C 29 87 13 70 13 47 L 13 17 Z")
    m = _mask(outer)
    # an inset line cut out of the face, the classic double-edged crest
    ring = vec.erode(m, 6.2 * U) - vec.erode(m, 10.0 * U)
    return np.clip(m - np.clip(ring, 0, 1), 0.0, 1.0)


def arrow():
    p = [(7, 36), (50, 36), (50, 12), (94, 50), (50, 88), (50, 64), (7, 64)]
    return _mask([vec.round_corners(p, 3.2)])


def crown():
    body = vec.round_corners([(11, 30), (31, 51), (50, 15), (69, 51), (89, 30), (82, 70), (18, 70)], 2.4)
    band = _rrect(17, 76, 83, 90, 3.5)
    balls = [vec.ellipse(11, 26, 6.2), vec.ellipse(50, 11.5, 6.2), vec.ellipse(89, 26, 6.2)]
    gems = [vec.ellipse(50, 56.5, 4.6), vec.ellipse(32.5, 61.5, 3.2), vec.ellipse(67.5, 61.5, 3.2)]
    return _mask([body, band] + balls, gems)


def gamepad():
    body = vec.svg("M 30 27 L 70 27 C 85 27 93 38 96 56 C 98 71 96 82 87 82 C 78 82 74 71 66 67 "
                   "L 34 67 C 26 71 22 82 13 82 C 4 82 2 71 4 56 C 7 38 15 27 30 27 Z")
    a, w = 8.2, 2.6  # d-pad arm length / half width
    cx, cy = 29.0, 47.0
    dpad = [vec.round_corners(vec.rect(cx - a, cy - w, cx + a, cy + w), 1.2),
            vec.round_corners(vec.rect(cx - w, cy - a, cx + w, cy + a), 1.2)]
    bx, by, d = 70.5, 47.0, 7.6
    buttons = [vec.ellipse(bx, by - d, 3.5), vec.ellipse(bx + d, by, 3.5), vec.ellipse(bx - d, by, 3.5),
               vec.ellipse(bx, by + d, 3.5)]
    mid = [_rrect(44.5, 37, 48.5, 40.4, 1.2), _rrect(51.5, 37, 55.5, 40.4, 1.2)]
    return _mask(body, dpad + buttons + mid)


def keyboard():
    body = _rrect(5, 23, 95, 77, 8.5)
    keys = []
    x0, x1 = 13.0, 87.0
    n, kw = 8, 7.2
    gap = (x1 - x0 - n * kw) / (n - 1)
    for y in (34.0, 46.0):
        for i in range(n):
            x = x0 + i * (kw + gap)
            keys.append(_rrect(x, y, x + kw, y + 8.0, 1.6))
    y = 58.0
    keys += [_rrect(13, y, 23.5, y + 8.0, 1.6), _rrect(27, y, 73, y + 8.0, 1.6), _rrect(76.5, y, 87, y + 8.0, 1.6)]
    return _mask([body], keys)


def cpu():
    body = _rrect(23, 23, 77, 77, 6.5)
    pins = []
    for c in (32.0, 44.0, 56.0, 68.0):
        pins += [_rrect(c - 2.7, 7, c + 2.7, 26, 2.2), _rrect(c - 2.7, 74, c + 2.7, 93, 2.2),
                 _rrect(7, c - 2.7, 26, c + 2.7, 2.2), _rrect(74, c - 2.7, 93, c + 2.7, 2.2)]
    m = _mask([body] + pins)
    ring = _mask([_rrect(31.5, 31.5, 68.5, 68.5, 3.5)], [_rrect(37.5, 37.5, 62.5, 62.5, 2.5)])
    return np.clip(m - ring, 0.0, 1.0)


ICONS = {
    "Flame": flame, "Ball": ball, "Star": star, "Bolt": bolt, "Shield": shield,
    "Arrow": arrow, "Crown": crown, "Gamepad": gamepad, "Keyboard": keyboard, "Cpu": cpu,
}


def render(name: str) -> np.ndarray:
    a = vec.box_down(ICONS[name](), SS)
    out = np.full((SIZE, SIZE, 4), 255, np.uint8)
    out[..., 3] = cm.to_u8(a)
    return out


def build() -> list[str]:
    cm.ensure_dirs()
    files, tiles = [], []
    tints = ["#FFFFFF", "#FF8A1F", "#19E6FF", "#FFC21A", "#8FE3FF", "#FFFFFF", "#F2B90F", "#E6007E", "#EBCB8B", "#9AA1AB"]
    for (name, _), tint in zip(ICONS.items(), tints):
        img = render(name)
        fn = f"T_Icon_{name}.png"
        cm.save_png(img, fn)
        files.append(fn)
        cm.save_preview(Image.fromarray(img, "RGBA"), fn, bg=(30, 32, 40))
        tiles.append((img, tint))

    # contact sheet: white at 256 on dark, tinted at 128 / 64 / 32 as the UI would use them
    cell = 138
    sheet = Image.new("RGB", (cell * len(tiles), 138 + 96 + 64 + 46), (26, 27, 34))
    for i, (img, tint) in enumerate(tiles):
        im = Image.fromarray(img, "RGBA")
        col = tuple(int(v * 255) for v in cm.rgb(tint))
        x = i * cell
        big = im.resize((120, 120), Image.LANCZOS)
        sheet.paste(Image.new("RGB", big.size, (255, 255, 255)), (x + 9, 9), big.getchannel("A"))
        for size, y in ((72, 150), (40, 240), (24, 296)):
            sm = im.resize((size, size), Image.LANCZOS)
            sheet.paste(Image.new("RGB", sm.size, col), (x + (cell - size) // 2, y), sm.getchannel("A"))
    cm.save_preview(sheet, "T_Icons_sheet.png")
    return files
