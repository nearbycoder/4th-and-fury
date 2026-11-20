"""The playing field: T_Field.png (8192 x 4096 colour) and T_FieldLines.png (paint mask).

The image covers 128 m x 64 m centred on midfield, so 1 px = 1.5625 cm (64 px per metre).
+x (image right) is toward the right-hand end zone; the image TOP is the far sideline and
the BOTTOM is the near sideline as seen by the TV camera.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import common as cm
from . import noise as nz
from . import vec
from .numbers import digit_shapes

W, H = 8192, 4096
PPM = 64.0  # pixels per metre
YD = 0.9144

GOAL = 50 * YD  # 45.72   goal line, from midfield
END = 60 * YD  # 54.864  end line
SIDE = 160 * 0.3048 / 2  # 24.384  sideline, from the centre line
BORDER = 1.8  # white border width
LINE = 0.10  # yard line width
# Goal line: twice as wide, painted on the FIELD side of the goal plane so the end-zone art
# (laid from x = GOAL outward) butts against it instead of covering it; a 3 cm lip of paint
# runs under that art so no turf can peek through. For a line centred on the plane use
# GOAL_LINE_FIELD = GOAL_LINE_ENDZONE = 0.10.
GOAL_LINE_FIELD = 0.20
GOAL_LINE_ENDZONE = 0.03
HASH_Y = 6.1  # inbound hash rows, from the centre line
HASH_LEN = 0.61
NUM_H = 1.83  # field numbers: 6 ft tall, 4 ft wide
NUM_W = 1.22
NUM_T = 0.31
NUM_TOP_IN = 8.2  # tops of the numbers, in from each sideline
NUM_GAP = 0.36  # yard line centre to the digit
MID_R = 7.0  # 14 m clear circle at midfield
TEAM_X = 20 * YD  # team areas run between the 30-yard lines
TEAM_Y0 = SIDE + BORDER + 2.0
TEAM_DEPTH = 3.0
SEED = 4100


def px(xm):
    return (np.asarray(xm, np.float64) + 64.0) * PPM


def py(ym):
    return (np.asarray(ym, np.float64) + 32.0) * PPM


# --------------------------------------------------------------------------- paint mask
def _cover(lo: float, hi: float, n: int):
    """Exact 1D pixel coverage of the interval [lo, hi) (in pixels) -> (start, weights)."""
    i0, i1 = max(0, math.floor(lo)), min(n, math.ceil(hi))
    if i1 <= i0:
        return 0, np.zeros(0, np.float32)
    idx = np.arange(i0, i1, dtype=np.float64)
    return i0, np.clip(np.minimum(hi, idx + 1) - np.maximum(lo, idx), 0.0, 1.0).astype(np.float32)


def add_rect(mask: np.ndarray, x0, x1, y0, y1, sign: float = 1.0) -> None:
    """Union an axis-aligned rectangle (metres) into the mask with exact antialiasing.
    Overlapping perpendicular strips combine exactly ('screen' union)."""
    ix, cx = _cover(float(px(x0)), float(px(x1)), W)
    iy, cy = _cover(float(py(y0)), float(py(y1)), H)
    if cx.size == 0 or cy.size == 0:
        return
    cov = cy[:, None] * cx[None, :]
    sub = mask[iy : iy + cy.size, ix : ix + cx.size]
    if sign > 0:
        sub[...] = 1.0 - (1.0 - sub) * (1.0 - cov)
    else:
        sub[...] = sub * (1.0 - cov)


def add_polys(mask: np.ndarray, polys, holes=(), ss: int = 4) -> None:
    """Union polygons given in metres (supersampled in a local tile)."""
    P = [np.stack([px(p[:, 0]), py(p[:, 1])], 1) for p in polys]
    Hh = [np.stack([px(p[:, 0]), py(p[:, 1])], 1) for p in holes]
    x0, y0, x1, y1 = vec.bbox(P)
    ix0, iy0 = max(0, math.floor(x0) - 1), max(0, math.floor(y0) - 1)
    ix1, iy1 = min(W, math.ceil(x1) + 1), min(H, math.ceil(y1) + 1)
    if ix1 <= ix0 or iy1 <= iy0:
        return
    tile = vec.raster(((ix1 - ix0) * ss, (iy1 - iy0) * ss), P, Hh, xf=(ss, -ix0 * ss, -iy0 * ss))
    cov = vec.box_down(vec.f32(tile), ss)
    sub = mask[iy0:iy1, ix0:ix1]
    sub[...] = 1.0 - (1.0 - sub) * (1.0 - cov)


def number_group(yards: int, x0: float, near: bool):
    """Polygons (metres) for one painted field number and its arrow.

    The near-side row is upright for the camera; the far-side row is the same thing turned
    half a turn about the yard line. Arrows always point at the nearer goal line.
    """
    tens, units = divmod(yards, 10)
    y_top = SIDE - NUM_TOP_IN  # near row: top of the numerals (toward midfield)
    o1, h1, w1 = digit_shapes(tens, NUM_W, NUM_H, NUM_T)
    o2, h2, w2 = digit_shapes(units, NUM_W, NUM_H, NUM_T)
    polys = [p + (x0 - NUM_GAP - w1, y_top) for p in o1] + [p + (x0 + NUM_GAP, y_top) for p in o2]
    holes = [p + (x0 - NUM_GAP - w1, y_top) for p in h1] + [p + (x0 + NUM_GAP, y_top) for p in h2]
    left, right = x0 - NUM_GAP - w1, x0 + NUM_GAP + w2
    if not near:  # half-turn about (x0, 0)
        polys = [np.stack([2 * x0 - p[:, 0], -p[:, 1]], 1) for p in polys]
        holes = [np.stack([2 * x0 - p[:, 0], -p[:, 1]], 1) for p in holes]
        left, right = 2 * x0 - right, 2 * x0 - left
    arrow = None
    if abs(x0) > 1e-6:  # no arrow at the 50
        a_len, a_base, a_gap, a_drop = 0.91, 0.46, 0.20, 0.38
        ya = y_top + a_drop
        ys = (ya, ya + a_base / 2, ya + a_base)
        if x0 < 0:  # nearer goal is to the left
            xb = left - a_gap
            arrow = np.array([(xb, ys[0]), (xb, ys[2]), (xb - a_len, ys[1])])
        else:
            xb = right + a_gap
            arrow = np.array([(xb, ys[0]), (xb + a_len, ys[1]), (xb, ys[2])])
        if not near:
            arrow = arrow * (1, -1)
    return polys, holes, arrow


def paint_mask() -> tuple[np.ndarray, np.ndarray]:
    """Returns (lines, team): coverage of white line paint and of the two team areas."""
    m = np.zeros((H, W), np.float32)
    over = 0.30  # lines run a little into the border so the joins are solid

    # 5-yard lines between the goal lines
    for k in range(-9, 10):
        x = k * 5 * YD
        add_rect(m, x - LINE / 2, x + LINE / 2, -SIDE - over, SIDE + over)
    for s in (-1, 1):  # goal lines (see GOAL_LINE_* above)
        a, b = sorted((s * (GOAL - GOAL_LINE_FIELD), s * (GOAL + GOAL_LINE_ENDZONE)))
        add_rect(m, a, b, -SIDE - over, SIDE + over)
    # one-yard hash marks: along both sidelines and both inbound rows
    for k in range(-49, 50):
        x = k * YD
        if k % 5 == 0:
            # on the 5-yard lines the inbound rows get a short crossing tick instead
            for s in (-1, 1):
                add_rect(m, x - 0.30, x + 0.30, s * HASH_Y - LINE / 2, s * HASH_Y + LINE / 2)
            continue
        for s in (-1, 1):
            a, b = sorted((s * (SIDE - 0.10 - HASH_LEN), s * (SIDE - 0.10)))
            add_rect(m, x - LINE / 2, x + LINE / 2, a, b)
            add_rect(m, x - LINE / 2, x + LINE / 2, s * HASH_Y - HASH_LEN / 2, s * HASH_Y + HASH_LEN / 2)
    # conversion marks on the 3-yard lines
    for s in (-1, 1):
        x = s * (GOAL - 3 * YD)
        add_rect(m, x - LINE / 2, x + LINE / 2, -0.457, 0.457)
    # numbers and arrows
    for i, yards in enumerate((10, 20, 30, 40, 50, 40, 30, 20, 10)):
        x0 = (i - 4) * 10 * YD
        for near in (True, False):
            polys, holes, arrow = number_group(yards, x0, near)
            add_polys(m, polys, holes)
            if arrow is not None:
                add_polys(m, [arrow])
    # the 14 m circle at midfield stays plain turf (engine puts an emblem there)
    yy = (np.arange(H, dtype=np.float32) + 0.5) / PPM - 32.0
    xx = (np.arange(W, dtype=np.float32) + 0.5) / PPM - 64.0
    r0 = int(px(-MID_R - 0.5)), int(px(MID_R + 0.5))
    r1 = int(py(-MID_R - 0.5)), int(py(MID_R + 0.5))
    d = np.hypot(xx[None, r0[0] : r0[1]], yy[r1[0] : r1[1], None])
    m[r1[0] : r1[1], r0[0] : r0[1]] *= np.clip((d - MID_R) * PPM + 0.5, 0.0, 1.0)
    # white border around the whole field of play (outer rectangle minus inner rectangle)
    outer = np.zeros((H, W), np.float32)
    add_rect(outer, -END - BORDER, END + BORDER, -SIDE - BORDER, SIDE + BORDER)
    inner = np.zeros((H, W), np.float32)
    add_rect(inner, -END, END, -SIDE, SIDE)
    border = outer - inner
    m = 1.0 - (1.0 - m * inner) * (1.0 - border)  # nothing but the border outside the field of play
    # team areas
    team = np.zeros((H, W), np.float32)
    for s in (-1, 1):
        a, b = sorted((s * TEAM_Y0, s * (TEAM_Y0 + TEAM_DEPTH)))
        add_rect(team, -TEAM_X, TEAM_X, a, b)
    return m, team


# --------------------------------------------------------------------------- turf
TURF_LIGHT = np.array([58, 145, 81], np.float32) / 255.0
TURF_DARK = np.array([45, 126, 70], np.float32) / 255.0
TURF_DRY = np.array([133, 155, 81], np.float32) / 255.0
APRON = np.array([36, 56, 46], np.float32) / 255.0
TEAM_AREA = np.array([203, 206, 199], np.float32) / 255.0
PAINT = np.array([244, 247, 242], np.float32) / 255.0


def turf_rgb() -> tuple[np.ndarray, np.ndarray]:
    """Returns (turf rgb HxWx3, detail luminance field HxW ~ N(0,1)) for the whole image."""
    shape = (H, W)
    x = (np.arange(W, dtype=np.float32) + 0.5) / PPM - 64.0
    y = (np.arange(H, dtype=np.float32) + 0.5) / PPM - 32.0

    # mowing stripes: 5-yard bands, boundaries on the yard lines, slightly soft edges
    ph = x / (5 * YD)
    f = ph - np.floor(ph)
    par = np.mod(np.floor(ph), 2.0) * 2.0 - 1.0
    edge = nz.smoothstep(0.0, 0.16 / (5 * YD), np.minimum(f, 1.0 - f))
    stripe = (par * edge)[None, :] * np.ones((H, 1), np.float32)  # -1 dark .. +1 light

    # natural variation (cycles per image; the image is 128 m wide)
    broad = nz.spectral(shape, SEED + 1, beta=3.0, lo=1.5, hi=24)  # ~5-40 m drifts
    patch = nz.spectral(shape, SEED + 2, beta=2.2, lo=20, hi=260)  # ~0.5-5 m clumps
    streak = nz.spectral(shape, SEED + 3, beta=1.2, lo=40, hi=900, aniso=(0.06, 1.0))  # mower lines along y
    fine = nz.spectral(shape, SEED + 4, beta=0.6, lo=300, hi=2600)  # fibrous grain, a few px
    grain = nz.white(shape, SEED + 5)

    # the mower leaves the stripe edge a touch ragged
    stripe = stripe * (1.0 + 0.10 * patch)

    # wear: lighter, drier grass where play concentrates (between the hashes, goal mouths)
    cx = np.exp(-((np.abs(y)[:, None] / 7.5) ** 2))
    along = 0.55 + 0.45 * np.exp(-((np.abs(x)[None, :] / 26.0) ** 2))
    mouth = np.exp(-(((np.abs(x)[None, :] - (GOAL - 4.0)) / 5.0) ** 2)) * np.exp(-((y[:, None] / 9.0) ** 2))
    wear_zone = np.clip(cx * along + 0.7 * mouth, 0.0, 1.0)
    wear = wear_zone * nz.smoothstep(-1.0, 1.8, 0.85 * broad + 0.45 * patch)
    wear += 0.30 * nz.smoothstep(0.9, 2.6, broad + 0.4 * patch)  # the odd tired patch elsewhere
    wear = np.clip(wear, 0.0, 1.0)

    t = (0.5 + 0.5 * stripe)[..., None]
    col = TURF_DARK + (TURF_LIGHT - TURF_DARK) * t
    lum = 1.0 + 0.024 * broad + 0.021 * patch + 0.020 * streak + 0.034 * fine + 0.012 * grain
    col = col * lum[..., None]
    # hue drift: lusher (bluer green) vs sunnier (yellower) areas
    hue = 0.020 * broad + 0.012 * patch
    col[..., 0] *= 1.0 + 1.6 * hue
    col[..., 2] *= 1.0 - 1.2 * hue
    col = col + (TURF_DRY - col) * (0.18 * wear)[..., None]
    detail = 0.6 * fine + 0.5 * patch + 0.3 * grain
    return col, detail


def build() -> list[str]:
    cm.ensure_dirs()
    lines, team = paint_mask()
    col, detail = turf_rgb()

    # apron outside the border
    inside = np.zeros((H, W), np.float32)
    add_rect(inside, -END - BORDER, END + BORDER, -SIDE - BORDER, SIDE + BORDER)
    a_noise = nz.spectral((H, W), SEED + 8, beta=1.6, lo=30, hi=1500)
    apron = APRON * (1.0 + 0.05 * a_noise + 0.02 * detail)[..., None]
    # a soft contact shadow / dirt line where the apron meets the white border
    col = apron + (col - apron) * inside[..., None]

    # team areas: pale, scuffed, with a slightly darker worn edge
    scuff = 1.0 + 0.030 * nz.spectral((H, W), SEED + 9, beta=1.8, lo=60, hi=1200) + 0.012 * detail
    col = col + (TEAM_AREA * scuff[..., None] - col) * team[..., None]

    # paint sits on the grass: slightly uneven coverage, grass texture showing through
    cover = lines * np.clip(0.955 + 0.035 * detail, 0.86, 1.0)
    paint = PAINT * np.clip(1.0 + 0.022 * detail, 0.9, 1.03)[..., None]
    col = col + (paint - col) * cover[..., None]

    out = cm.to_u8(np.clip(col, 0.0, 1.0))
    cm.save_png(out, "T_Field.png")
    mask = cm.to_u8(np.clip(1.0 - (1.0 - lines) * (1.0 - team), 0.0, 1.0))
    cm.save_png(mask, "T_FieldLines.png")

    img = Image.fromarray(out, "RGB")
    cm.save_preview(img, "T_Field.png")
    cm.save_preview(Image.fromarray(mask, "L"), "T_FieldLines.png")

    def crop(name, cx_m, cy_m, w_m, h_m):
        box = (int(px(cx_m - w_m / 2)), int(py(cy_m - h_m / 2)), int(px(cx_m + w_m / 2)), int(py(cy_m + h_m / 2)))
        cm.save_preview(img.crop(box), name)

    crop("T_Field_crop_midfield.png", 0.0, 9.0, 40.0, 30.0)  # 50, numbers, hashes, clear circle
    crop("T_Field_crop_goal.png", GOAL - 6.0, 16.0, 21.0, 21.0)  # goal line, 10, arrow, corner
    crop("T_Field_crop_detail.png", -9.144, 17.1, 10.5, 5.25)  # 1:1 pixels around a number
    return ["T_Field.png", "T_FieldLines.png"]
