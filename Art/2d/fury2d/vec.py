"""Small vector toolkit: paths -> polygons -> supersampled masks -> layered RGBA.

Everything is rasterised with Pillow at SS x the target resolution and box-filtered
down, which gives clean antialiased edges without any native vector library.
Outlines/offsets come from exact Euclidean distance transforms (scipy).
"""
from __future__ import annotations

import math
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

# =========================================================================== geometry


def pts(*xy) -> np.ndarray:
    return np.asarray(xy, dtype=np.float64).reshape(-1, 2)


def cubic(p0, p1, p2, p3, n: int = 20) -> np.ndarray:
    """Points on a cubic Bezier, excluding p0, including p3."""
    t = np.linspace(0.0, 1.0, n + 1)[1:, None]
    p0, p1, p2, p3 = (np.asarray(p, np.float64) for p in (p0, p1, p2, p3))
    u = 1.0 - t
    return u**3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t**3 * p3


def quadratic(p0, p1, p2, n: int = 14) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n + 1)[1:, None]
    p0, p1, p2 = (np.asarray(p, np.float64) for p in (p0, p1, p2))
    u = 1.0 - t
    return u * u * p0 + 2 * u * t * p1 + t * t * p2


def arc(cx, cy, r, a0, a1, n: int | None = None, ry: float | None = None) -> np.ndarray:
    """Arc points from angle a0 to a1 (degrees; 0 = +x, 90 = +y i.e. down on screen)."""
    if n is None:
        n = max(6, int(abs(a1 - a0) / 4))
    a = np.radians(np.linspace(a0, a1, n + 1))
    return np.stack([cx + r * np.cos(a), cy + (r if ry is None else ry) * np.sin(a)], 1)


def ellipse(cx, cy, rx, ry=None, n: int = 72, rot: float = 0.0) -> np.ndarray:
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    p = np.stack([rx * np.cos(a), (rx if ry is None else ry) * np.sin(a)], 1)
    if rot:
        p = rotate(p, rot)
    return p + (cx, cy)


def rect(x0, y0, x1, y1) -> np.ndarray:
    return pts((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def rotate(p, deg: float, about=(0.0, 0.0)) -> np.ndarray:
    """Rotate clockwise on screen (y down) by `deg`."""
    p = np.asarray(p, np.float64)
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    q = p - about
    return np.stack([q[:, 0] * c - q[:, 1] * s, q[:, 0] * s + q[:, 1] * c], 1) + about


def scale(p, sx: float, sy: float | None = None, about=(0.0, 0.0)) -> np.ndarray:
    p = np.asarray(p, np.float64)
    return (p - about) * (sx, sx if sy is None else sy) + about


def shift(p, dx: float, dy: float) -> np.ndarray:
    return np.asarray(p, np.float64) + (dx, dy)


def mirror_x(p, cx: float = 0.0) -> np.ndarray:
    """Mirror left<->right about x = cx (point order reversed to keep winding)."""
    p = np.asarray(p, np.float64).copy()
    p[:, 0] = 2 * cx - p[:, 0]
    return p[::-1]


def poly_area(p) -> float:
    """Signed area; > 0 means clockwise on screen (y down)."""
    p = np.asarray(p, np.float64)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def bbox(polys) -> tuple[float, float, float, float]:
    allp = np.concatenate([np.asarray(p, np.float64).reshape(-1, 2) for p in polys])
    return float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()), float(allp[:, 1].max())


# --------------------------------------------------------------------------- curves
def blob(points, k: float = 0.36, n: int = 14, closed: bool = True) -> np.ndarray:
    """Smooth curve through points. A point may be (x, y) or (x, y, 'c') for a sharp corner.

    Handles follow the chord between each point's neighbours, with length k * segment
    length, so unevenly spaced points do not overshoot.
    """
    P = np.array([(p[0], p[1]) for p in points], np.float64)
    corner = [len(p) > 2 and p[2] == "c" for p in points]
    N = len(P)
    if not closed:
        corner[0] = corner[-1] = True
    dirs = np.zeros_like(P)
    for i in range(N):
        a, b = P[(i - 1) % N], P[(i + 1) % N]
        d = b - a
        L = math.hypot(*d)
        dirs[i] = d / L if L > 1e-9 else 0
    out = [P[0][None]]
    segs = N if closed else N - 1
    for i in range(segs):
        j = (i + 1) % N
        p0, p1 = P[i], P[j]
        seg = p1 - p0
        L = math.hypot(*seg)
        c1 = p0 + (seg / 3.0 if corner[i] else dirs[i] * L * k)
        c2 = p1 - (seg / 3.0 if corner[j] else dirs[j] * L * k)
        if corner[i] and corner[j]:
            out.append(p1[None])
        else:
            out.append(cubic(p0, c1, c2, p1, n))
    res = np.concatenate(out)
    return res[:-1] if closed else res


def round_corners(poly, r: float, n: int = 6) -> np.ndarray:
    """Round every corner of a polygon with a quadratic fillet of (at most) radius r."""
    P = np.asarray(poly, np.float64)
    N = len(P)
    out = []
    for i in range(N):
        a, b, c = P[i - 1], P[i], P[(i + 1) % N]
        la, lc = math.hypot(*(a - b)), math.hypot(*(c - b))
        ra, rc = min(r, la * 0.5), min(r, lc * 0.5)
        if ra < 1e-6 or rc < 1e-6:
            out.append(b[None])
            continue
        p0 = b + (a - b) / la * ra
        p2 = b + (c - b) / lc * rc
        out.append(p0[None])
        out.append(quadratic(p0, b, p2, n))
    return np.concatenate(out)


def chamfer(verts) -> np.ndarray:
    """verts: (x, y, c) triples. Each corner with c > 0 is cut by c along both edges."""
    n = len(verts)
    out = []
    for i, (x, y, c) in enumerate(verts):
        if c <= 0:
            out.append((x, y))
            continue
        px, py = verts[i - 1][0], verts[i - 1][1]
        nx, ny = verts[(i + 1) % n][0], verts[(i + 1) % n][1]
        li, lo = math.hypot(px - x, py - y), math.hypot(nx - x, ny - y)
        out.append((x + (px - x) / li * c, y + (py - y) / li * c))
        out.append((x + (nx - x) / lo * c, y + (ny - y) / lo * c))
    return np.asarray(out, np.float64)


_TOK = re.compile(r"[MmLlHhVvCcSsQqTtZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_NARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "Z": 0}


def svg(d: str, n: int = 18) -> list[np.ndarray]:
    """Parse an SVG path string (M L H V C S Q T Z, absolute or relative) into polygons."""
    toks = _TOK.findall(d)
    i = 0
    out: list[np.ndarray] = []
    cur: list[np.ndarray] = []
    pos = np.zeros(2)
    start = np.zeros(2)
    last_c = None  # last control point for S/T
    cmd = None
    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
        elif cmd is None:
            raise ValueError("path must start with a command")
        C = cmd.upper()
        rel = cmd.islower()
        k = _NARGS[C]
        a = [float(t) for t in toks[i : i + k]]
        i += k
        base = pos if rel else np.zeros(2)
        if C == "M":
            if cur:
                out.append(np.concatenate(cur))
            pos = base + a
            start = pos.copy()
            cur = [pos[None].copy()]
            cmd = "l" if rel else "L"
            last_c = None
        elif C == "L":
            pos = base + a
            cur.append(pos[None].copy())
            last_c = None
        elif C == "H":
            pos = np.array([(pos[0] if rel else 0.0) + a[0], pos[1]])
            cur.append(pos[None].copy())
            last_c = None
        elif C == "V":
            pos = np.array([pos[0], (pos[1] if rel else 0.0) + a[0]])
            cur.append(pos[None].copy())
            last_c = None
        elif C == "C":
            c1, c2, p = base + a[0:2], base + a[2:4], base + a[4:6]
            cur.append(cubic(pos, c1, c2, p, n))
            pos, last_c = p, ("C", c2)
        elif C == "S":
            c1 = 2 * pos - last_c[1] if last_c and last_c[0] == "C" else pos
            c2, p = base + a[0:2], base + a[2:4]
            cur.append(cubic(pos, c1, c2, p, n))
            pos, last_c = p, ("C", c2)
        elif C == "Q":
            c1, p = base + a[0:2], base + a[2:4]
            cur.append(quadratic(pos, c1, p, n))
            pos, last_c = p, ("Q", c1)
        elif C == "T":
            c1 = 2 * pos - last_c[1] if last_c and last_c[0] == "Q" else pos
            p = base + a[0:2]
            cur.append(quadratic(pos, c1, p, n))
            pos, last_c = p, ("Q", c1)
        elif C == "Z":
            if cur:
                out.append(np.concatenate(cur))
            cur = []
            pos = start.copy()
            last_c = None
    if cur:
        out.append(np.concatenate(cur))
    return out


# =========================================================================== raster
def _flat(p) -> list[float]:
    # Pillow truncates polygon vertices to ints; +0.5 turns that into rounding.
    return (np.asarray(p, np.float64) + 0.5).reshape(-1).tolist()


def raster(size, polys=(), holes=(), strokes=(), xf=None) -> np.ndarray:
    """Rasterise to a uint8 (0/255) HxW array.

    size   : (w, h) pixels
    polys  : polygons filled (union)
    holes  : polygons cut out afterwards
    strokes: (points, width, closed) polylines with round joins/caps, drawn before holes
    xf     : optional (scale, dx, dy) applied to all coordinates and stroke widths
    """
    im = Image.new("L", size, 0)
    d = ImageDraw.Draw(im)
    s, dx, dy = xf if xf is not None else (1.0, 0.0, 0.0)

    def T(p):
        return np.asarray(p, np.float64) * s + (dx, dy)

    for p in polys:
        if len(p) >= 3:
            d.polygon(_flat(T(p)), fill=255)
    for p, w, closed in strokes:
        q = T(p)
        w = w * s
        if closed:
            q = np.concatenate([q, q[:1]])
        if w <= 1.5:
            d.line(_flat(q), fill=255, width=max(1, int(round(w))))
            continue
        r = w / 2.0
        seg = q[1:] - q[:-1]
        L = np.hypot(seg[:, 0], seg[:, 1])
        for a, b, v, l in zip(q[:-1], q[1:], seg, L):
            if l < 1e-9:
                continue
            nrm = np.array([-v[1], v[0]]) / l * r
            d.polygon(_flat([a + nrm, b + nrm, b - nrm, a - nrm]), fill=255)
        for c in q:
            d.ellipse([c[0] - r + 0.5, c[1] - r + 0.5, c[0] + r + 0.5, c[1] + r + 0.5], fill=255)
    for p in holes:
        if len(p) >= 3:
            d.polygon(_flat(T(p)), fill=0)
    return np.asarray(im)


def f32(mask) -> np.ndarray:
    """uint8 or float mask -> float32 0..1."""
    m = np.asarray(mask)
    if m.dtype == np.uint8:
        return m.astype(np.float32) / 255.0
    return m.astype(np.float32, copy=False)


def _crop_box(b: np.ndarray, pad: int):
    rows = np.flatnonzero(b.any(1))
    cols = np.flatnonzero(b.any(0))
    if rows.size == 0:
        return None
    H, W = b.shape
    return (max(0, rows[0] - pad), min(H, rows[-1] + 1 + pad), max(0, cols[0] - pad), min(W, cols[-1] + 1 + pad))


def dilate(mask, r: float) -> np.ndarray:
    """Grow a mask by r pixels (round corners), antialiased. Returns float32 0..1."""
    m = f32(mask)
    if r <= 0:
        return m.copy()
    b = m >= 0.5
    box = _crop_box(b, int(math.ceil(r)) + 3)
    out = np.zeros_like(m)
    if box is None:
        return out
    y0, y1, x0, x1 = box
    d = ndi.distance_transform_edt(~b[y0:y1, x0:x1]).astype(np.float32)
    out[y0:y1, x0:x1] = np.clip(r - d + 1.0, 0.0, 1.0)
    return np.maximum(out, m)


def erode(mask, r: float) -> np.ndarray:
    """Shrink a mask by r pixels, antialiased. Returns float32 0..1."""
    m = f32(mask)
    if r <= 0:
        return m.copy()
    b = m >= 0.5
    box = _crop_box(b, 2)
    out = np.zeros_like(m)
    if box is None:
        return out
    y0, y1, x0, x1 = box
    sub = np.pad(b[y0:y1, x0:x1], 1)  # make sure the outside counts as empty at image borders
    d = ndi.distance_transform_edt(sub)[1:-1, 1:-1].astype(np.float32)
    out[y0:y1, x0:x1] = np.clip(d - r, 0.0, 1.0)
    return np.minimum(out, m)


def close_gaps(mask, r: float) -> np.ndarray:
    """Morphological closing: fills notches/gaps narrower than ~2r."""
    return np.maximum(erode(dilate(mask, r), r), f32(mask))


def blur(a: np.ndarray, sigma: float, wrap: bool = False) -> np.ndarray:
    return ndi.gaussian_filter(np.asarray(a, np.float32), sigma, mode="wrap" if wrap else "nearest")


def box_down(a: np.ndarray, ss: int) -> np.ndarray:
    """Exact area-average downsample by an integer factor."""
    if ss == 1:
        return np.asarray(a, np.float32)
    a = np.asarray(a, np.float32)
    h, w = a.shape[0] // ss, a.shape[1] // ss
    a = a[: h * ss, : w * ss]
    if a.ndim == 2:
        return a.reshape(h, ss, w, ss).mean(axis=(1, 3), dtype=np.float32)
    return a.reshape(h, ss, w, ss, a.shape[2]).mean(axis=(1, 3), dtype=np.float32)


def shift_mask(m: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Translate a mask by whole pixels, filling with zero."""
    out = np.zeros_like(m)
    H, W = m.shape[:2]
    xs0, xs1 = max(0, -dx), min(W, W - dx)
    ys0, ys1 = max(0, -dy), min(H, H - dy)
    if xs1 > xs0 and ys1 > ys0:
        out[ys0 + dy : ys1 + dy, xs0 + dx : xs1 + dx] = m[ys0:ys1, xs0:xs1]
    return out


# =========================================================================== canvas
class Canvas:
    """Premultiplied float RGBA canvas at ss x resolution with 'over' compositing."""

    def __init__(self, w: int, h: int, ss: int = 4, bg=None):
        self.w, self.h, self.ss = w, h, ss
        self.W, self.H = w * ss, h * ss
        self.buf = np.zeros((self.H, self.W, 4), np.float32)
        if bg is not None:
            self.buf[..., :3] = np.asarray(bg, np.float32)
            self.buf[..., 3] = 1.0

    @property
    def size(self):
        return (self.W, self.H)

    def paint(self, mask, color, opacity: float = 1.0) -> None:
        """Composite `color` (rgb triple or HxWx3 array, 0..1) through a mask."""
        m = f32(mask)
        b = m > 0
        box = _crop_box(b, 0)
        if box is None:
            return
        y0, y1, x0, x1 = box
        a = m[y0:y1, x0:x1, None] * np.float32(opacity)
        col = np.asarray(color, np.float32)
        if col.ndim == 3:
            col = col[y0:y1, x0:x1]
        dst = self.buf[y0:y1, x0:x1]
        dst[..., :3] = col * a + dst[..., :3] * (1.0 - a)
        dst[..., 3:4] = a + dst[..., 3:4] * (1.0 - a)

    def paint_rgba(self, rgba, x: int = 0, y: int = 0, opacity: float = 1.0) -> None:
        """Composite a straight-alpha float RGBA image (same scale as the canvas) at (x, y)."""
        src = np.asarray(rgba, np.float32)
        h, w = src.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.W, x + w), min(self.H, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        s = src[y0 - y : y1 - y, x0 - x : x1 - x]
        a = s[..., 3:4] * np.float32(opacity)
        dst = self.buf[y0:y1, x0:x1]
        dst[..., :3] = s[..., :3] * a + dst[..., :3] * (1.0 - a)
        dst[..., 3:4] = a + dst[..., 3:4] * (1.0 - a)

    def result(self, bleed=None) -> np.ndarray:
        """Downsample to uint8 straight-alpha RGBA. `bleed` = rgb for fully transparent pixels,
        or 'edge' to extend the nearest opaque colour (avoids dark fringes when filtered)."""
        from .common import to_u8

        small = box_down(self.buf, self.ss)
        a = small[..., 3:4]
        rgbv = np.where(a > 1e-6, small[..., :3] / np.maximum(a, 1e-6), 0.0)
        if bleed is not None:
            clear = a[..., 0] <= (0.5 / 255.0)
            if isinstance(bleed, str) and bleed == "edge":
                if clear.any() and not clear.all():
                    idx = ndi.distance_transform_edt(clear, return_distances=False, return_indices=True)
                    rgbv = rgbv[idx[0], idx[1]]
            else:
                rgbv = np.where(clear[..., None], np.asarray(bleed, np.float32), rgbv)
        return to_u8(np.concatenate([np.clip(rgbv, 0, 1), a], axis=2))

    def result_rgb(self) -> np.ndarray:
        from .common import to_u8

        small = box_down(self.buf, self.ss)
        return to_u8(np.clip(small[..., :3], 0, 1))


# =========================================================================== text
_FONT_CACHE: dict = {}


def font(path, size: float) -> ImageFont.FreeTypeFont:
    key = (str(path), round(float(size), 2))
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(str(path), size)
    return _FONT_CACHE[key]


def text_mask(text: str, path, size: float, tracking: float = 0.0, pad: int = 4):
    """Render text to a tight uint8 mask.

    Returns (mask, ox, oy): the mask's top-left corner sits at (ox, oy) relative to the
    text origin (left edge of the first glyph's advance box, on the baseline).
    `tracking` is extra advance per glyph in pixels.
    """
    ft = font(path, size)
    xs = []
    x = 0.0
    for i, ch in enumerate(text):
        xs.append(x)
        x += ft.getlength(ch) + tracking
        if i + 1 < len(text):  # pair kerning, if the font has a kern table
            x += ft.getlength(text[i : i + 2]) - ft.getlength(ch) - ft.getlength(text[i + 1])
    boxes = [ft.getbbox(ch, anchor="ls") for ch in text]
    x0 = min(xs[i] + b[0] for i, b in enumerate(boxes))
    x1 = max(xs[i] + b[2] for i, b in enumerate(boxes))
    y0 = min(b[1] for b in boxes)
    y1 = max(b[3] for b in boxes)
    ox, oy = math.floor(x0) - pad, math.floor(y0) - pad
    W, H = math.ceil(x1) + pad - ox, math.ceil(y1) + pad - oy
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    for i, ch in enumerate(text):
        d.text((xs[i] - ox, -oy), ch, font=ft, fill=255, anchor="ls")
    return np.asarray(im), ox, oy


def text_ink(text: str, path, size: float, tracking: float = 0.0):
    """Tight ink mask of a string: (mask, width, height) with no padding."""
    m, _, _ = text_mask(text, path, size, tracking, pad=2)
    rows = np.flatnonzero(m.any(1))
    cols = np.flatnonzero(m.any(0))
    m = m[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
    return m, m.shape[1], m.shape[0]


def fit_text(text: str, path, max_w: float, max_h: float, tracking_em: float = 0.0, probe: float = 200.0):
    """Largest font size whose ink box fits (max_w, max_h). Returns (size, mask)."""
    _, w, h = text_ink(text, path, probe, tracking_em * probe)
    size = probe * min(max_w / w, max_h / h)
    for _ in range(3):  # ink size is not perfectly linear in font size; refine
        m, w, h = text_ink(text, path, size, tracking_em * size)
        k = min(max_w / w, max_h / h)
        if 0.997 <= k <= 1.0:
            break
        size *= k * 0.999
    m, w, h = text_ink(text, path, size, tracking_em * size)
    return size, m


def place(dst_shape, mask, x: float, y: float) -> np.ndarray:
    """Put a small mask into a full-size float32 canvas mask with its top-left at (x, y)."""
    out = np.zeros(dst_shape, np.float32)
    m = f32(mask)
    h, w = m.shape
    x, y = int(round(x)), int(round(y))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst_shape[1], x + w), min(dst_shape[0], y + h)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = m[y0 - y : y1 - y, x0 - x : x1 - x]
    return out


def affine_mask(mask, matrix, out_size) -> np.ndarray:
    """Apply a forward affine map dst = M @ (x, y, 1) to a mask (bicubic). matrix is 2x3."""
    M = np.vstack([np.asarray(matrix, np.float64), [0, 0, 1]])
    inv = np.linalg.inv(M)
    im = Image.fromarray(np.asarray(mask) if np.asarray(mask).dtype == np.uint8 else (f32(mask) * 255).astype(np.uint8))
    out = im.transform(out_size, Image.AFFINE, tuple(inv[:2].reshape(-1)), resample=Image.BICUBIC)
    return np.asarray(out)
