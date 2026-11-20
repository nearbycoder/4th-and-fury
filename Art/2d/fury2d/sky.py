"""T_NightSky.png - 4096 x 2048 equirectangular night sky.

Longitude runs across the image (it wraps seamlessly left to right), the zenith is the top
row, the horizon is the middle row and everything below it falls to near-black.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from . import common as cm
from . import noise as nz

W, H = 4096, 2048
SEED = 9100

ZENITH = np.array([0.010, 0.014, 0.036], np.float32)
MID_SKY = np.array([0.022, 0.032, 0.085], np.float32)
LOW_SKY = np.array([0.060, 0.062, 0.150], np.float32)
HAZE = np.array([0.155, 0.120, 0.215], np.float32)  # violet haze above the city
CITY = np.array([0.560, 0.300, 0.190], np.float32)  # sodium-orange glow on the horizon
FLOOD = np.array([0.300, 0.330, 0.400], np.float32)  # cool spill from the stadium lights
GROUND = np.array([0.007, 0.007, 0.011], np.float32)


def _axes():
    el = (0.5 - (np.arange(H, dtype=np.float32) + 0.5) / H) * math.pi  # +pi/2 top .. -pi/2 bottom
    az = (np.arange(W, dtype=np.float32) + 0.5) / W * 2 * math.pi
    return el, az


def city_profile(az: np.ndarray) -> np.ndarray:
    """How strong the city glow is around the horizon (periodic in azimuth), 0..1."""
    def bump(center_deg, width_deg, amp):
        d = np.angle(np.exp(1j * (az - math.radians(center_deg))))
        return amp * np.exp(-((d / math.radians(width_deg)) ** 2))

    g = 0.30 + bump(62, 44, 0.70) + bump(248, 62, 0.50) + bump(150, 22, 0.22) + bump(318, 30, 0.26)
    r = nz.rng(SEED + 7)
    for k in range(3, 14):  # skyline-scale wobble
        g = g + 0.05 / (k**0.5) * np.sin(k * az + r.uniform(0, 2 * math.pi))
    return np.clip(g, 0.08, 1.0).astype(np.float32)


def base_sky(el: np.ndarray, az: np.ndarray) -> np.ndarray:
    e = np.degrees(el)[:, None]  # (H, 1)
    city = city_profile(az)[None, :]  # (1, W)
    up = np.clip(e, 0.0, 90.0)
    t_mid = nz.smoothstep(90.0, 30.0, up)[..., None]
    t_low = nz.smoothstep(42.0, 4.0, up)[..., None]
    col = ZENITH + (MID_SKY - ZENITH) * t_mid
    col = col + (LOW_SKY - col) * t_low
    haze = np.exp(-up / 17.0) * (0.45 + 0.55 * city)
    col = col + (HAZE - col) * np.clip(haze, 0, 1)[..., None] * 0.85
    glow = np.exp(-up / 7.2) * city
    col = col + (CITY - col) * np.clip(glow, 0, 1)[..., None] * 0.92
    flood = np.exp(-up / 10.0) * 0.27
    col = col + FLOOD * flood[..., None]
    # below the horizon: the glow dies away quickly into near-black
    below = np.clip(-e, 0.0, 90.0)
    fade = np.exp(-below / 2.6)[..., None]
    col = np.where(e[..., None] >= 0, col, GROUND + (col - GROUND) * fade)
    return col.astype(np.float32)


def clouds(el: np.ndarray, az: np.ndarray):
    """Thin wisps: density 0..1 for the upper hemisphere (plus a sliver below the horizon)."""
    rows = int(H * 0.5 + 40)
    e = el[:rows, None]
    a = az[None, :]
    ce = np.cos(e)
    x = (ce * np.cos(a)).astype(np.float32)
    y = (np.sin(e) * np.ones_like(a)).astype(np.float32)
    z = (ce * np.sin(a)).astype(np.float32)
    # squash vertically so the wisps run along the horizon; warp for a wind-drawn look
    fx, fy = 3.1, 10.5
    wx = nz.fbm3(x * 1.7 + 11.0, y * 3.4, z * 1.7 - 5.0, SEED + 21, octaves=3)
    wz = nz.fbm3(x * 1.7 - 7.0, y * 3.4 + 3.0, z * 1.7 + 9.0, SEED + 22, octaves=3)
    n = nz.fbm3(x * fx + 0.55 * wx, y * fy + 0.35 * wz, z * fx + 0.55 * wz, SEED + 23, octaves=6, gain=0.55)
    fine = nz.fbm3(x * fx * 3.3, y * fy * 3.0, z * fx * 3.3, SEED + 24, octaves=4, gain=0.6)
    ed = np.degrees(e)
    # most cloud sits low; it thins out toward the zenith
    amount = nz.smoothstep(-1.0, 7.0, ed) * (0.30 + 0.70 * nz.smoothstep(78.0, 16.0, ed))
    dens = nz.smoothstep(0.02, 0.36, n + 0.16 * fine - 0.02) * amount
    dens = dens * (0.62 + 0.38 * nz.smoothstep(-0.35, 0.3, fine))  # feathered, streaky texture
    full = np.zeros((H, W), np.float32)
    full[:rows] = dens
    return full


def stars(el: np.ndarray, az: np.ndarray, n: int = 3000) -> np.ndarray:
    """Sparse stars, uniform on the sphere, stretched in x so they stay round once the
    equirectangular map is wrapped onto the sky dome."""
    r = nz.rng(SEED + 40)
    out = np.zeros((H, W, 3), np.float32)
    sin_el = r.uniform(math.sin(math.radians(3.0)), math.sin(math.radians(86.0)), n)
    e = np.arcsin(sin_el)
    a = r.uniform(0, 2 * math.pi, n)
    mag = r.pareto(1.55, n)  # many faint, a few bright
    bright = np.clip(0.06 + 0.085 * mag, 0.0, 1.0)
    sigma = 0.52 + 0.16 * np.clip(mag, 0, 6) ** 0.6 + r.uniform(0, 0.12, n)
    tint = r.uniform(0, 1, n)
    for i in range(n):
        ed = math.degrees(e[i])
        vis = float(nz.smoothstep(5.0, 30.0, ed))  # washed out by the glow near the horizon
        b = bright[i] * (0.25 + 0.75 * vis)
        if b < 0.035:
            continue
        cy = (0.5 - e[i] / math.pi) * H
        cx = a[i] / (2 * math.pi) * W
        sy = sigma[i]
        sx = sy / max(math.cos(e[i]), 0.02)
        ry, rx = int(math.ceil(3.2 * sy)), int(math.ceil(3.2 * sx))
        ys = np.arange(int(cy) - ry, int(cy) + ry + 1)
        xs = np.arange(int(cx) - rx, int(cx) + rx + 1)
        g = np.exp(-0.5 * ((ys[:, None] + 0.5 - cy) / sy) ** 2) * np.exp(-0.5 * ((xs[None, :] + 0.5 - cx) / sx) ** 2)
        t = tint[i]
        if t < 0.22:
            col = np.array([0.78, 0.86, 1.0])  # blue-white
        elif t > 0.86:
            col = np.array([1.0, 0.80, 0.62])  # warm giant
        elif t > 0.70:
            col = np.array([1.0, 0.95, 0.84])
        else:
            col = np.array([0.96, 0.97, 1.0])
        ys = np.clip(ys, 0, H - 1)
        out[ys[:, None], xs[None, :] % W] += (g[..., None] * (b * col)).astype(np.float32)
    return out


def perspective(img: np.ndarray, yaw_deg: float, pitch_deg: float, fov_deg: float = 80.0, size=(680, 430)):
    """Rectilinear camera view of the equirect map (for judging how it reads in game)."""
    w, h = size
    f = 0.5 * w / math.tan(math.radians(fov_deg) / 2)
    xs, ys = np.meshgrid(np.arange(w) - w / 2 + 0.5, np.arange(h) - h / 2 + 0.5)
    d = np.stack([xs, -ys, np.full_like(xs, f)], -1).astype(np.float64)
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    p, yw = math.radians(pitch_deg), math.radians(yaw_deg)
    rx = np.array([[1, 0, 0], [0, math.cos(p), math.sin(p)], [0, -math.sin(p), math.cos(p)]])
    ry = np.array([[math.cos(yw), 0, math.sin(yw)], [0, 1, 0], [-math.sin(yw), 0, math.cos(yw)]])
    d = d @ rx.T @ ry.T
    el = np.arcsin(np.clip(d[..., 1], -1, 1))
    az = np.arctan2(d[..., 0], d[..., 2]) % (2 * math.pi)
    u = az / (2 * math.pi) * W - 0.5
    v = (0.5 - el / math.pi) * H - 0.5
    out = np.stack([ndi.map_coordinates(img[..., c].astype(np.float32), [v, u], order=1, mode="grid-wrap")
                    for c in range(3)], -1)
    return np.clip(out, 0, 255).astype(np.uint8)


def build() -> list[str]:
    cm.ensure_dirs()
    el, az = _axes()
    col = base_sky(el, az)
    dens = clouds(el, az)
    st = stars(el, az)

    # clouds are lit from below by the stadium floods and the city, and they hide stars
    e = np.degrees(el)[:, None]
    up = np.clip(e, 0.0, 90.0)
    city = city_profile(az)[None, :]
    warm = np.clip(np.exp(-up / 20.0) * (0.25 + 0.75 * city), 0.0, 1.0)[..., None]
    lit_cool = np.array([0.250, 0.262, 0.345], np.float32)
    lit_warm = np.array([0.640, 0.420, 0.320], np.float32)
    height_dim = (0.30 + 0.70 * np.exp(-up / 30.0))[..., None]
    cloud_col = (lit_cool + (lit_warm - lit_cool) * warm) * height_dim
    col = col + st * (1.0 - 0.85 * dens)[..., None]
    col = col + (cloud_col - col) * (0.80 * dens)[..., None]

    # triangular dither so the long dark gradients do not band at 8 bits
    r = nz.rng(SEED + 60)
    dither = (r.random((H, W, 1), dtype=np.float32) - r.random((H, W, 1), dtype=np.float32)) / 255.0
    out = cm.to_u8(np.clip(col + dither, 0.0, 1.0))
    cm.save_png(out, "T_NightSky.png")

    cm.save_preview(Image.fromarray(out, "RGB"), "T_NightSky.png")
    views = [Image.fromarray(perspective(out, yaw, pitch)) for yaw, pitch in ((62, 14), (200, 24), (300, 58), (0, 8))]
    sheet = cm.vstack([cm.hstack(views[:2], gap=8), cm.hstack(views[2:], gap=8)], gap=0)
    cm.save_preview(sheet, "T_NightSky_views.png")
    # wrap check: the left and right edges must meet seamlessly
    seam = Image.fromarray(np.concatenate([out[:1100, -350:], out[:1100, :350]], 1), "RGB")
    cm.save_preview(seam, "T_NightSky_wrap.png")
    return ["T_NightSky.png"]
