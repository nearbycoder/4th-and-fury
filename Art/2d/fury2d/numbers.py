"""Athletic block numerals (own polygon design) and the 10 x 10 jersey number atlas.

T_Numbers.png : 4096 x 4096, number n in column n % 10, row n // 10 (row 0 at the top).
                R = digit fill, G = outline ring outside the fill, B = 0, A = 255.
The same polygon numerals are reused (wider, lighter) for the numbers painted on the field.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import common as cm
from . import vec

ATLAS = 4096
GRID = 10
SS = 4


# --------------------------------------------------------------------------- numerals
def digit_shapes(d: int, W: float, H: float, t: float, c: float | None = None, ci: float | None = None,
                 notch: bool = True):
    """Polygon numeral `d` in a box with its top-left at (0, 0), y down.

    W, H : width / height of a full-width digit        t : stroke thickness
    c    : outer chamfer                                ci: inner (counter) chamfer
    notch: False drops the little waist notches of 3 and 8 (used for the outline layer,
           which is cut simpler than the number itself, as on a stitched jersey)
    Returns (outers, holes, width) - width is smaller than W for the '1'.
    """
    c = 0.70 * t if c is None else c
    ci = 0.26 * t if ci is None else ci
    m0 = (H - t) / 2.0  # top of the middle bar
    m1 = m0 + t  # bottom of the middle bar
    s = 0.62 * t  # length of the little return stubs on 2 3 5 6 7 9
    n = 0.30 * t if notch else 0.0  # waist notch on 3 and 8
    ch = vec.chamfer
    holes = []
    width = W

    if d == 0:
        outer = ch([(0, 0, c), (W, 0, c), (W, H, c), (0, H, c)])
        holes = [ch([(t, t, ci), (W - t, t, ci), (W - t, H - t, ci), (t, H - t, ci)])]
    elif d == 1:
        serif = 0.56 * t
        width = t + 2 * serif
        x0, x1 = serif, serif + t
        tb = 0.92 * t  # base slab thickness
        fh = 0.98 * t  # flag depth
        outer = ch([
            (0, 0, 0.80 * serif), (x1, 0, 0), (x1, H - tb, 0), (width, H - tb, 0), (width, H, 0),
            (0, H, 0), (0, H - tb, 0), (x0, H - tb, 0), (x0, fh, 0), (0, fh, 0),
        ])
    elif d == 2:
        outer = ch([
            (0, 0, c), (W, 0, c), (W, m1, c), (t, m1, ci), (t, H - t, 0), (W, H - t, 0), (W, H, 0),
            (0, H, 0), (0, m0, c), (W - t, m0, ci), (W - t, t, ci), (t, t, ci), (t, t + s, 0), (0, t + s, 0),
        ])
    elif d == 3:
        xm = 0.34 * W
        outer = ch([
            (0, 0, c), (W, 0, c), (W, H / 2 - n, 0), (W - n, H / 2, 0), (W, H / 2 + n, 0), (W, H, c),
            (0, H, c), (0, H - t - s, 0), (t, H - t - s, 0), (t, H - t, ci), (W - t, H - t, ci),
            (W - t, m1, ci), (xm, m1, 0), (xm, m0, 0), (W - t, m0, ci), (W - t, t, ci), (t, t, ci),
            (t, t + s, 0), (0, t + s, 0),
        ])
    elif d == 4:
        e = 0.30 * t  # crossbar overhang right of the stem
        xs1 = W - e
        xs0 = xs1 - t
        yb = 0.585 * H  # top of the crossbar
        xtl = xs0 - 0.30 * t  # where the diagonal's outer edge reaches the top
        th = 1.10 * t  # horizontal thickness of the diagonal
        yct = yb * (1.0 - (xs0 - th) / xtl)  # apex of the counter (inner edge parallel to outer)
        outer = ch([
            (xtl, 0, 0), (xs1, 0, 0), (xs1, yb, 0), (W, yb, 0), (W, yb + t, 0), (xs1, yb + t, 0),
            (xs1, H, 0), (xs0, H, 0), (xs0, yb + t, 0), (0, yb + t, 0), (0, yb, 0),
        ])
        holes = [vec.pts((xs0, yct), (xs0, yb), (th, yb))]
    elif d == 5:
        outer = ch([
            (0, 0, 0), (W, 0, 0), (W, t, 0), (t, t, 0), (t, m0, ci), (W, m0, c), (W, H, c), (0, H, c),
            (0, H - t - s, 0), (t, H - t - s, 0), (t, H - t, ci), (W - t, H - t, ci), (W - t, m1, ci),
            (0, m1, 0.5 * c),
        ])
    elif d in (6, 9):
        outer = ch([
            (0, 0, c), (W, 0, c), (W, t + s, 0), (W - t, t + s, 0), (W - t, t, ci), (t, t, ci),
            (t, m0, ci), (W, m0, c), (W, H, c), (0, H, c),
        ])
        holes = [ch([(t, m1, ci), (W - t, m1, ci), (W - t, H - t, ci), (t, H - t, ci)])]
        if d == 9:  # a 6 turned half a turn
            outer = (W, H) - outer
            holes = [(W, H) - h for h in holes]
    elif d == 7:
        tb = 1.16 * t  # horizontal thickness of the leg
        xb0 = 0.14 * W
        xb1 = xb0 + tb
        outer = ch([
            (0, 0, c), (W, 0, c), (W, t, 0), (xb1, H, 0), (xb0, H, 0), (W - tb, t, 0), (t, t, ci),
            (t, t + s, 0), (0, t + s, 0),
        ])
    elif d == 8:
        outer = ch([
            (0, 0, c), (W, 0, c), (W, H / 2 - n, 0), (W - n, H / 2, 0), (W, H / 2 + n, 0), (W, H, c),
            (0, H, c), (0, H / 2 + n, 0), (n, H / 2, 0), (0, H / 2 - n, 0),
        ])
        holes = [
            ch([(t, t, ci), (W - t, t, ci), (W - t, m0, ci), (t, m0, ci)]),
            ch([(t, m1, ci), (W - t, m1, ci), (W - t, H - t, ci), (t, H - t, ci)]),
        ]
    else:
        raise ValueError(d)
    return [_dedupe(outer)], [_dedupe(h) for h in holes], width


def _dedupe(poly) -> np.ndarray:
    """Drop consecutive duplicate vertices (zero-length edges)."""
    P = np.asarray(poly, np.float64)
    keep = np.hypot(*(P - np.roll(P, 1, axis=0)).T) > 1e-9
    return P[keep]


def number_shapes(n: int, W: float, H: float, t: float, gap: float, notch: bool = True):
    """Polygons for the number n laid out left to right from x = 0. Returns (outers, holes, total_width)."""
    text = str(n)
    outers, holes = [], []
    x = 0.0
    for i, chd in enumerate(text):
        o, h, w = digit_shapes(int(chd), W, H, t, notch=notch)
        outers += [p + (x, 0) for p in o]
        holes += [p + (x, 0) for p in h]
        x += w + (gap if i + 1 < len(text) else 0.0)
    return outers, holes, x


def mitred_ring_parts(poly, r: float, hole: bool = False, miter_limit: float = 2.6) -> list[np.ndarray]:
    """Pieces whose union is the band of width r outside `poly` with mitred (sharp) corners.
    For a hole the band grows into the hole."""
    P = np.asarray(poly, np.float64)
    n = len(P)
    sign = 1.0 if vec.poly_area(P) > 0 else -1.0
    if hole:
        sign = -sign
    normals, parts = [], []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        dx, dy = b - a
        L = math.hypot(dx, dy)
        nrm = sign * np.array([dy, -dx]) / L
        normals.append(nrm)
        parts.append(np.array([a, b, b + nrm * r, a + nrm * r]))
    for i in range(n):
        n1, n2 = normals[i - 1], normals[i]
        cross = n1[0] * n2[1] - n1[1] * n2[0]
        if cross * sign <= 1e-9:
            continue  # the two bands already overlap here
        V = P[i]
        den = 1.0 + float(n1 @ n2)
        if den > 2.0 / (miter_limit**2):
            tip = V + r * (n1 + n2) / den
            parts.append(np.array([V, V + n1 * r, tip, V + n2 * r]))
        else:  # too sharp: bevel
            parts.append(np.array([V, V + n1 * r, V + n2 * r]))
    return parts


# --------------------------------------------------------------------------- atlas
def layout():
    """Metrics of the atlas in final pixels."""
    cell = ATLAS / GRID  # 409.6
    margin = 0.09 * cell
    H = cell - 2 * margin  # digit height: 82% of the cell
    ring = 0.07 * H  # outline ring width
    gap = ring  # two digits share exactly one outline width
    W = (cell - 2 * margin - gap) / 2.0  # two digits + gap span 82% of the cell
    t = 0.285 * W
    return dict(cell=cell, margin=margin, H=H, W=W, t=t, gap=gap, ring=ring)


def render_atlas() -> np.ndarray:
    L = layout()
    S = ATLAS * SS
    fill = Image.new("L", (S, S), 0)
    outer = Image.new("L", (S, S), 0)
    df, do = ImageDraw.Draw(fill), ImageDraw.Draw(outer)

    def flat(p):
        return (np.asarray(p) * SS + 0.5).reshape(-1).tolist()

    for n in range(100):
        col, row = n % GRID, n // GRID
        outs, holes, w = number_shapes(n, L["W"], L["H"], L["t"], L["gap"])
        ox = (col + 0.5) * L["cell"] - w / 2.0
        oy = (row + 0.5) * L["cell"] - L["H"] / 2.0
        outs = [p + (ox, oy) for p in outs]
        holes = [p + (ox, oy) for p in holes]
        plain, _, _ = number_shapes(n, L["W"], L["H"], L["t"], L["gap"], notch=False)
        for p in outs:
            df.polygon(flat(p), fill=255)
        for p in plain:
            p = p + (ox, oy)
            do.polygon(flat(p), fill=255)
            for part in mitred_ring_parts(p, L["ring"]):
                do.polygon(flat(part), fill=255)
        for p in holes:
            df.polygon(flat(p), fill=0)
        # the ring also runs around the inside of each counter: cut the counters out of
        # the outline layer, then add the inward band back
        for p in holes:
            do.polygon(flat(p), fill=0)
        for p in holes:
            for part in mitred_ring_parts(p, L["ring"], hole=True):
                do.polygon(flat(part), fill=255)
    R = np.asarray(fill.reduce(SS), np.int16)
    O = np.asarray(outer.reduce(SS), np.int16)
    G = np.clip(O - R, 0, 255)
    out = np.zeros((ATLAS, ATLAS, 4), np.uint8)
    out[..., 0] = R
    out[..., 1] = G
    out[..., 3] = 255
    return out


def preview_colored(atlas: np.ndarray, base, fill, ring) -> np.ndarray:
    """How the mask looks once the engine tints it: jersey colour, number fill, outline."""
    r = atlas[..., 0:1].astype(np.float32) / 255.0
    g = atlas[..., 1:2].astype(np.float32) / 255.0
    col = np.asarray(base, np.float32) * (1 - r - g) + np.asarray(fill, np.float32) * r + np.asarray(ring, np.float32) * g
    return cm.to_u8(np.clip(col, 0, 1))


def down_faces() -> list[str]:
    files = []
    for down in range(1, 5):
        outer, holes, width = digit_shapes(down, 126.0, 174.0, 27.0)
        offset = ((256.0 - width) * 0.5, 41.0)
        face = Image.new("RGB", (256, 256), (20, 22, 24))
        draw = ImageDraw.Draw(face)
        for paths, color in ((outer, (255, 210, 90)), (holes, (20, 22, 24))):
            for poly in paths:
                draw.polygon((poly + offset).flatten().tolist(), fill=color)
        name = f"T_Down_{down}.png"
        cm.save_png(np.asarray(face), name)
        files.append(name)
    return files


def build() -> list[str]:
    cm.ensure_dirs()
    atlas = render_atlas()
    cm.save_png(atlas, "T_Numbers.png")
    # previews: raw mask, and a tinted mock-up in two team colourways
    raw = Image.fromarray(atlas[..., :3], "RGB")
    cm.save_preview(raw, "T_Numbers_mask.png")
    teams = {t["id"]: t for t in cm.load_teams()}
    a, b = teams["hellhounds"], teams["icebreakers"]
    left = preview_colored(atlas[:, : ATLAS // 2], cm.rgb(a["primary"]), cm.rgb("#F4F4F4"), cm.rgb(a["secondary"]))
    right = preview_colored(atlas[:, ATLAS // 2 :], cm.rgb("#F4F8FB"), cm.rgb(b["primary"]), cm.rgb(b["secondary"]))
    cm.save_preview(np.concatenate([left, right], 1), "T_Numbers.png")
    # a close crop so edge quality can be judged at 1:1
    c = int(layout()["cell"])
    crop = preview_colored(atlas[c * 2 : c * 5, c * 3 : c * 6 + 8], cm.rgb(a["primary"]), cm.rgb("#F4F4F4"), cm.rgb(a["secondary"]))
    cm.save_preview(crop, "T_Numbers_crop.png")
    return ["T_Numbers.png", *down_faces()]
