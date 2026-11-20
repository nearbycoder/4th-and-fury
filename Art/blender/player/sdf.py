"""Implicit-surface building blocks (numpy).

Every athlete form is described as a scalar field f(p) that is negative inside and roughly a
distance in metres outside. Fields are only ever sampled along rays and refined by bisection, so
they do not have to be exact distances - they have to be smooth and have the right zero set.

All functions take `p` as an (N, 3) array and return (N,).
"""
import numpy as np


def vlen(v):
    return np.sqrt(np.einsum("...i,...i->...", v, v))


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


# ------------------------------------------------------------------------------- combinators
def smin(a, b, k):
    """Smooth union: the two shapes melt together over a band about `k` metres wide."""
    if k <= 0.0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    """Smooth intersection."""
    return -smin(-a, -b, k)


def ssub(a, b, k):
    """Smoothly carve `b` out of `a`."""
    return smax(a, -b, k)


def union(parts, k):
    out = parts[0]
    for part in parts[1:]:
        out = smin(out, part, k)
    return out


# -------------------------------------------------------------------------------- primitives
def sphere(p, c, r):
    return vlen(p - np.asarray(c, float)) - r


def frame(x=None, y=None, z=None):
    """3x3 matrix whose COLUMNS are orthonormal local axes built from two hints."""
    if x is not None and y is not None:
        x = unit(x); z = unit(np.cross(x, y)); y = np.cross(z, x)
    elif y is not None and z is not None:
        y = unit(y); x = unit(np.cross(y, z)); z = np.cross(x, y)
    elif z is not None and x is not None:
        z = unit(z); y = unit(np.cross(z, x)); x = np.cross(y, z)
    else:
        raise ValueError("need two axes")
    return np.stack([x, y, z], axis=1)


def local(p, c, R=None):
    q = p - np.asarray(c, float)
    return q if R is None else q @ R


def ellipsoid(p, c, r, R=None):
    q = local(p, c, R)
    r = np.asarray(r, float)
    k0 = vlen(q / r)
    k1 = vlen(q / (r * r))
    return np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -r.min())


def superellipsoid(p, c, r, e, R=None):
    """Rounded-box-like blob: exponent e = 2 is an ellipsoid, 4+ approaches a box.
    Returns a first-order distance estimate (value / |gradient|)."""
    q = np.abs(local(p, c, R))
    r = np.asarray(r, float)
    e = np.broadcast_to(np.asarray(e, float), (3,))
    u = np.maximum(q / r, 1e-9)
    terms = u ** e
    s = np.maximum(terms.sum(axis=1), 1e-12)
    em = float(e.mean())
    k = s ** (1.0 / em)
    dk = (k / (em * s))[:, None] * (e * terms / np.maximum(q, 1e-9))
    g = np.maximum(vlen(dk), 0.35 / float(r.max()))
    return (k - 1.0) / g


def box(p, c, half, R=None, rnd=0.0):
    q = np.abs(local(p, c, R)) - (np.asarray(half, float) - rnd)
    outside = vlen(np.maximum(q, 0.0))
    inside = np.minimum(np.max(q, axis=1), 0.0)
    return outside + inside - rnd


def capsule(p, a, b, r):
    a = np.asarray(a, float); b = np.asarray(b, float)
    ab = b - a
    h = np.clip(((p - a) @ ab) / (ab @ ab), 0.0, 1.0)
    return vlen(p - a - h[:, None] * ab) - r


def cone(p, a, b, ra, rb):
    """Capsule whose radius runs linearly from ra at `a` to rb at `b` (round ends)."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    ab = b - a
    h = np.clip(((p - a) @ ab) / (ab @ ab), 0.0, 1.0)
    return vlen(p - a - h[:, None] * ab) - (ra + (rb - ra) * h)


def plane(p, point, normal):
    """Negative on the side the normal points AWAY from."""
    return (p - np.asarray(point, float)) @ unit(normal)


def torus(p, c, R, major, minor):
    """Ring whose axis is the local Z of frame R."""
    q = local(p, c, R)
    ring = np.sqrt(q[:, 0] ** 2 + q[:, 1] ** 2) - major
    return np.sqrt(ring ** 2 + q[:, 2] ** 2) - minor


# --------------------------------------------------------------------------- interpolation
def pchip(x, xs, ys):
    """Shape-preserving cubic through (xs, ys); clamps outside the table. Never overshoots."""
    xs = np.asarray(xs, float); ys = np.asarray(ys, float)
    x = np.asarray(x, float)
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros_like(ys)
    for k in range(1, len(xs) - 1):
        if d[k - 1] * d[k] > 0.0:
            w1 = 2.0 * h[k] + h[k - 1]
            w2 = h[k] + 2.0 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0] = d[0]
    m[-1] = d[-1]
    xc = np.clip(x, xs[0], xs[-1])
    k = np.clip(np.searchsorted(xs, xc, side="right") - 1, 0, len(xs) - 2)
    t = (xc - xs[k]) / h[k]
    t2 = t * t; t3 = t2 * t
    return ((2 * t3 - 3 * t2 + 1) * ys[k] + (t3 - 2 * t2 + t) * h[k] * m[k]
            + (-2 * t3 + 3 * t2) * ys[k + 1] + (t3 - t2) * h[k] * m[k + 1])


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def bump(x, centre, half_width):
    """Smooth 0..1..0 bump with compact support."""
    t = np.clip(1.0 - np.abs((np.asarray(x, float) - centre) / half_width), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Table:
    """Columns of numbers keyed by a station value, interpolated with `pchip`."""

    def __init__(self, names, rows):
        arr = np.asarray(rows, float)
        order = np.argsort(arr[:, 0])
        arr = arr[order]
        self.key = arr[:, 0]
        self.cols = {name: arr[:, i + 1] for i, name in enumerate(names[1:])}

    def __call__(self, name, x):
        return pchip(x, self.key, self.cols[name])


def section_tube(p, origin, R, table, girth=1.0, inner_limit=None, lo=None, hi=None, cap=0.012):
    """A body made of stacked super-elliptical cross-sections.

    `R` columns are (side, front, along); they need not be right-handed. `table` gives, per
    distance along the `along` axis:
    ws          half-width (or wo / wi for separate outer (+side) and inner (-side) widths)
    df / db     depth toward front / back
    ef / eb     super-ellipse exponent of the front / back half
    cs / cf     optional centre offset toward side / front
    `girth` scales every radius (a number, or fn(t)). `inner_limit(t)` caps the inner half-width.
    `lo` / `hi` end the solid along its axis with a softly rounded cap.
    """
    q = local(p, origin, R)
    t = q[:, 2]
    cols = table.cols
    g = girth(t) if callable(girth) else girth
    x = q[:, 0] - (table("cs", t) * g if "cs" in cols else 0.0)
    y = q[:, 1] - (table("cf", t) * g if "cf" in cols else 0.0)
    if "wo" in cols:
        wi = table("wi", t) * g
        if inner_limit is not None:
            wi = np.minimum(wi, inner_limit(t))
        ws = np.where(x >= 0.0, table("wo", t) * g, wi)
    else:
        ws = table("ws", t) * g
    front = y >= 0.0
    d = np.where(front, table("df", t), table("db", t)) * g
    e = np.where(front, table("ef", t), table("eb", t))
    ux = np.maximum(np.abs(x) / ws, 1e-9)
    uy = np.maximum(np.abs(y) / d, 1e-9)
    s = ux ** e + uy ** e
    k = s ** (1.0 / e)
    gx = (k / s) * ux ** (e - 1.0) / ws
    gy = (k / s) * uy ** (e - 1.0) / d
    grad = np.maximum(np.sqrt(gx * gx + gy * gy), 0.35 / np.maximum(ws, d))
    out = (k - 1.0) / grad
    if lo is not None:
        out = smax(out, lo - t, cap)
    if hi is not None:
        out = smax(out, t - hi, cap)
    return out


# ----------------------------------------------------------------------------------- rays
def march(field, origins, dirs, t0, t1, steps=72, mode="last", iters=16):
    """Distance along each ray to the surface of `field`.

    mode "last": the outermost exit (inside -> outside) between t0 and t1.
    mode "first": the first exit walking outward from t0.
    Rays that never leave the solid return t1; rays that are never inside return NaN.
    """
    origins = np.asarray(origins, float).reshape(-1, 3)
    dirs = np.asarray(dirs, float).reshape(-1, 3)
    n = origins.shape[0]
    t0 = np.broadcast_to(np.asarray(t0, float), (n,))
    t1 = np.broadcast_to(np.asarray(t1, float), (n,))
    frac = np.linspace(0.0, 1.0, steps)
    ts = t0[:, None] + (t1 - t0)[:, None] * frac[None, :]
    pts = origins[:, None, :] + dirs[:, None, :] * ts[:, :, None]
    inside = (field(pts.reshape(-1, 3)) < 0.0).reshape(n, steps)
    cross = inside[:, :-1] & ~inside[:, 1:]
    has = cross.any(axis=1)
    if mode == "first":
        idx = np.argmax(cross, axis=1)
    else:
        idx = steps - 2 - np.argmax(cross[:, ::-1], axis=1)
    rows = np.arange(n)
    lo = ts[rows, idx].copy()
    hi = ts[rows, idx + 1].copy()
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        f = field(origins + dirs * mid[:, None])
        neg = f < 0.0
        lo = np.where(neg, mid, lo)
        hi = np.where(neg, hi, mid)
    out = 0.5 * (lo + hi)
    never_out = ~has & inside[:, -1]
    out = np.where(never_out, t1, out)
    out = np.where(~has & ~inside[:, -1], np.nan, out)
    return out


def gradient(field, p, eps=5e-4):
    p = np.asarray(p, float).reshape(-1, 3)
    g = np.empty_like(p)
    for axis in range(3):
        step = np.zeros(3); step[axis] = eps
        g[:, axis] = field(p + step) - field(p - step)
    n = vlen(g)
    return g / np.maximum(n, 1e-12)[:, None]


def project(field, p, iters=6, eps=5e-4):
    """Pull points onto the zero set along the field gradient."""
    p = np.asarray(p, float).reshape(-1, 3).copy()
    for _ in range(iters):
        g = np.empty_like(p)
        for axis in range(3):
            step = np.zeros(3); step[axis] = eps
            g[:, axis] = (field(p + step) - field(p - step)) / (2.0 * eps)
        f = field(p)
        gg = np.einsum("ij,ij->i", g, g)
        p -= g * (f / np.maximum(gg, 1e-12))[:, None]
    return p
