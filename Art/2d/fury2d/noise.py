"""Seeded procedural noise. Everything spectral here is periodic, so it tiles seamlessly."""
from __future__ import annotations

import numpy as np
from scipy import fft as sfft
from scipy import ndimage as ndi
from scipy.spatial import cKDTree


def rng(seed) -> np.random.Generator:
    return np.random.default_rng(seed)


def _freq(shape):
    h, w = shape
    fy = sfft.fftfreq(h)[:, None] * h
    fx = sfft.rfftfreq(w)[None, :] * w
    return fy, fx


def spectral(shape, seed, beta: float = 2.0, lo: float = 0.0, hi: float | None = None,
             aniso: tuple[float, float] = (1.0, 1.0)) -> np.ndarray:
    """Periodic 1/f^beta noise, zero mean / unit std.

    lo, hi : band limits in cycles per image (soft edges)
    aniso  : (sy, sx) frequency scaling; e.g. (1, 6) squeezes detail along x -> vertical streaks
    """
    h, w = shape
    white = rng(seed).standard_normal((h, w), dtype=np.float32)
    F = sfft.rfft2(white, workers=-1)
    fy, fx = _freq(shape)
    f = np.sqrt((fy / aniso[0]) ** 2 + (fx / aniso[1]) ** 2)
    f[0, 0] = 1.0
    amp = f ** (-beta / 2.0)
    if lo > 0:
        amp *= 1.0 - np.exp(-((f / lo) ** 2))
    if hi is not None:
        amp *= np.exp(-((f / hi) ** 2))
    amp[0, 0] = 0.0
    out = sfft.irfft2(F * amp.astype(np.float32), s=shape, workers=-1).astype(np.float32)
    out -= out.mean()
    out /= max(float(out.std()), 1e-9)
    return out


def white(shape, seed) -> np.ndarray:
    return rng(seed).standard_normal(shape, dtype=np.float32)


def unit(a: np.ndarray, lo_pct: float = 0.5, hi_pct: float = 99.5) -> np.ndarray:
    """Rescale to 0..1 using robust percentiles."""
    lo, hi = np.percentile(a, [lo_pct, hi_pct])
    return np.clip((a - lo) / max(hi - lo, 1e-9), 0.0, 1.0).astype(np.float32)


def equalize(a: np.ndarray) -> np.ndarray:
    """Histogram-equalise to a flat 0..1 distribution (rank transform)."""
    flat = a.ravel()
    order = np.argsort(flat, kind="stable")
    ranks = np.empty(flat.size, np.float32)
    ranks[order] = np.linspace(0.0, 1.0, flat.size, dtype=np.float32)
    return ranks.reshape(a.shape)


def smoothstep(e0: float, e1: float, x):
    t = np.clip((np.asarray(x, np.float32) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def blur_wrap(a: np.ndarray, sigma) -> np.ndarray:
    return ndi.gaussian_filter(np.asarray(a, np.float32), sigma, mode="wrap")


def worley(shape, points: np.ndarray, k: int = 2) -> np.ndarray:
    """Tileable cellular noise: distances from every pixel centre to its k nearest feature
    points (given in pixel coordinates), measured on the torus. Returns (h, w, k)."""
    h, w = shape
    tiles = [points + (dx * w, dy * h) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    tree = cKDTree(np.concatenate(tiles))
    yy, xx = np.mgrid[0:h, 0:w]
    q = np.stack([xx.ravel() + 0.5, yy.ravel() + 0.5], 1)
    d, _ = tree.query(q, k=k, workers=-1)
    return d.reshape(h, w, k).astype(np.float32)


def jittered_points(shape, cell: float, seed, jitter: float = 0.45) -> np.ndarray:
    """Roughly evenly spaced random points (jittered grid), in pixel coordinates."""
    h, w = shape
    ny, nx = max(1, round(h / cell)), max(1, round(w / cell))
    r = rng(seed)
    gy, gx = np.mgrid[0:ny, 0:nx]
    px = (gx + 0.5 + (gy % 2) * 0.5 + r.uniform(-jitter, jitter, gx.shape)) * (w / nx)
    py = (gy + 0.5 + r.uniform(-jitter, jitter, gy.shape)) * (h / ny)
    return np.stack([px.ravel() % w, py.ravel() % h], 1)


# --------------------------------------------------------------------------- 3D gradient noise
def _perm(seed):
    p = rng(seed).permutation(256).astype(np.int32)
    return np.concatenate([p, p])


_GRAD3 = np.array(
    [[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
     [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1], [1, 1, 0], [-1, 1, 0], [0, -1, 1], [0, -1, -1]],
    np.float32,
)


def perlin3(x, y, z, seed) -> np.ndarray:
    """Classic 3D gradient noise in roughly -1..1; inputs are float arrays of one shape."""
    perm = _perm(seed)
    xi, yi, zi = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32), np.floor(z).astype(np.int32)
    xf, yf, zf = (x - xi).astype(np.float32), (y - yi).astype(np.float32), (z - zi).astype(np.float32)
    xi &= 255
    yi &= 255
    zi &= 255

    def fade(t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    u, v, w = fade(xf), fade(yf), fade(zf)

    def corner(dx, dy, dz):
        hsh = perm[perm[perm[xi + dx] + yi + dy] + zi + dz] & 15
        g = _GRAD3[hsh]
        return g[..., 0] * (xf - dx) + g[..., 1] * (yf - dy) + g[..., 2] * (zf - dz)

    n000, n100 = corner(0, 0, 0), corner(1, 0, 0)
    n010, n110 = corner(0, 1, 0), corner(1, 1, 0)
    n001, n101 = corner(0, 0, 1), corner(1, 0, 1)
    n011, n111 = corner(0, 1, 1), corner(1, 1, 1)
    x00 = n000 + u * (n100 - n000)
    x10 = n010 + u * (n110 - n010)
    x01 = n001 + u * (n101 - n001)
    x11 = n011 + u * (n111 - n011)
    y0 = x00 + v * (x10 - x00)
    y1 = x01 + v * (x11 - x01)
    return (y0 + w * (y1 - y0)).astype(np.float32)


def fbm3(x, y, z, seed, octaves: int = 5, lacunarity: float = 2.0, gain: float = 0.5) -> np.ndarray:
    out = np.zeros(np.shape(x), np.float32)
    amp, freq, norm = 1.0, 1.0, 0.0
    for o in range(octaves):
        out += amp * perlin3(x * freq, y * freq, z * freq, seed + 101 * o)
        norm += amp
        amp *= gain
        freq *= lacunarity
    return out / norm


# --------------------------------------------------------------------------- normal maps
def height_to_normal(height: np.ndarray, strength: float, wrap: bool = True) -> np.ndarray:
    """Tangent-space normal map from a height field, DirectX convention (green points DOWN
    the image). Returns float32 RGB in 0..1; a flat surface encodes to (0.5, 0.5, 1.0)."""
    h = np.asarray(height, np.float32)
    if wrap:
        dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
        dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5  # d/d(row), rows increase downward
    else:
        dy, dx = np.gradient(h)
    nx = -dx * strength
    ny = -dy * strength  # +Y is down the image, so no flip is needed for DirectX
    nz = np.ones_like(h)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx * inv * 0.5 + 0.5, ny * inv * 0.5 + 0.5, nz * inv * 0.5 + 0.5], 2).astype(np.float32)
