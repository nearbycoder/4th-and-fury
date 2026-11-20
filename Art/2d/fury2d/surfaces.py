"""Seamlessly tiling 1024 x 1024 surface textures.

Normal maps are tangent-space, DirectX convention (green points DOWN the image), flat =
(128, 128, 255). Everything is built from periodic functions or drawn with wrap-around,
so the tiles are seamless by construction; build() also measures the seams.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import common as cm
from . import noise as nz

S = 1024


# --------------------------------------------------------------------------- helpers
def fold(canvas: np.ndarray, pad: int, mode: str = "max") -> np.ndarray:
    """Fold a (S+2*pad)^2 canvas back onto the S x S torus."""
    n = canvas.shape[0]
    out = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            y0, x0 = pad + dy * S, pad + dx * S
            ys0, ys1 = max(0, y0), min(n, y0 + S)
            xs0, xs1 = max(0, x0), min(n, x0 + S)
            if ys1 <= ys0 or xs1 <= xs0:
                continue
            tile = np.zeros((S, S), canvas.dtype)
            tile[ys0 - y0 : ys1 - y0, xs0 - x0 : xs1 - x0] = canvas[ys0:ys1, xs0:xs1]
            out = tile if out is None else (np.maximum(out, tile) if mode == "max" else out + tile)
    return out


def normal_from(height: np.ndarray, rms_tilt: float) -> np.ndarray:
    """Normal map whose xy components have the requested RMS (keeps the relief subtle)."""
    h = np.asarray(height, np.float32)
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    g = float(np.sqrt(np.mean(dx * dx + dy * dy)))
    strength = rms_tilt / max(g, 1e-9)
    for _ in range(4):  # normalisation shrinks steep slopes; iterate to hit the target
        n = nz.height_to_normal(h, strength)
        xy = (n[..., :2] - 0.5) * 2.0
        got = float(np.sqrt(np.mean(np.sum(xy * xy, axis=2))))
        strength *= rms_tilt / max(got, 1e-9)
    return nz.height_to_normal(h, strength)


def lit(normal_u8: np.ndarray, light=(-0.55, -0.6, 0.6)) -> np.ndarray:
    """Simple shaded preview of a DirectX normal map (light from the upper left)."""
    n = normal_u8[..., :3].astype(np.float32) / 255.0 * 2.0 - 1.0
    L = np.asarray(light, np.float32)
    L /= np.linalg.norm(L)
    d = np.clip(n @ L, 0.0, 1.0)
    flat = float(L[2])
    return np.clip(0.5 + (d - flat) * 1.6, 0.0, 1.0)


def seam_ratio(a: np.ndarray) -> float:
    """How the step across each wrap-around seam compares with ordinary neighbouring
    rows/columns: seam step / 99.5th percentile of the interior steps (<= ~1 is seamless)."""
    a = a.astype(np.float32)
    if a.ndim == 2:
        a = a[..., None]
    worst = 0.0
    for axis in (0, 1):
        b = np.moveaxis(a, axis, 0)
        inner = np.abs(b[1:] - b[:-1]).reshape(b.shape[0] - 1, -1).mean(axis=1)
        seam = float(np.abs(b[0] - b[-1]).mean())
        worst = max(worst, seam / max(float(np.percentile(inner, 99.5)), 1e-9))
    return worst


def tiled_preview(img_u8: np.ndarray, name: str, shaded: np.ndarray | None = None) -> None:
    """Three panels: the tile repeated 2 x 2 (seams/repetition), a 1:1 crop straddling the
    corner where four tiles meet, and for normal maps the same two views shaded by a light."""
    def panels(a8):
        t = np.tile(a8, (2, 2, 1) if a8.ndim == 3 else (2, 2))
        im = cm.as_image(t).convert("RGB")
        return [im.resize((460, 460), Image.LANCZOS), im.crop((S - 230, S - 230, S + 230, S + 230))]

    parts = panels(img_u8)
    if shaded is not None:
        lit8 = cm.to_u8(shaded)
        parts = [parts[0]] + panels(lit8)
    else:
        parts.append(cm.as_image(img_u8).convert("RGB").crop((0, 0, 460, 460)))
    cm.save_preview(cm.hstack(parts, gap=6), name)


# --------------------------------------------------------------------------- grass
def grass_height(seed: int = 5101) -> np.ndarray:
    """Top-down turf: thousands of tufts, each a fan of short curved blades that rise from a
    low root to a high tip. Taller blades are drawn last so they lie on top."""
    r = nz.rng(seed)
    ss, pad = 2, 60
    size = (S + 2 * pad) * ss
    tufts = 8200
    tx, ty = r.uniform(0, S, tufts), r.uniform(0, S, tufts)
    lean = r.normal(math.pi / 2, 0.9, tufts)  # mild common grain, as if brushed along +y
    count = r.integers(4, 9, tufts)
    blades = []
    for i in range(tufts):
        for _ in range(int(count[i])):
            a0 = lean[i] + r.normal(0, 1.25)
            length = float(np.clip(r.gamma(5.0, 5.0), 10, 50))
            blades.append((tx[i] + r.normal(0, 1.6), ty[i] + r.normal(0, 1.6), a0, length,
                           r.normal(0, 0.34), r.uniform(1.5, 2.9), r.beta(2.2, 2.0)))
    blades.sort(key=lambda b: b[6])
    im = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(im)
    for x, y, a0, length, bend, width, v in blades:
        p0 = np.array([x + pad, y + pad])
        p1 = p0 + 0.5 * length * np.array([math.cos(a0), math.sin(a0)])
        a1 = a0 + bend
        p2 = p1 + 0.5 * length * np.array([math.cos(a1), math.sin(a1)])
        w = width * ss
        d.line([tuple(p0 * ss), tuple(p1 * ss)], fill=int(36 + 150 * v), width=max(1, int(round(w))))
        d.line([tuple(p1 * ss), tuple(p2 * ss)], fill=int(70 + 185 * v), width=max(1, int(round(w * 0.7))))
    big = np.asarray(im.reduce(ss), np.float32) / 255.0
    h = fold(big, pad, "max")
    h = nz.blur_wrap(h, 0.7)
    clump = nz.spectral((S, S), seed + 1, beta=2.4, lo=3, hi=40)
    return h + 0.10 * clump


def grass_mask(seed: int = 5120) -> np.ndarray:
    """Clumps (lighter = lusher) and soft thin patches (darker = worn) for breaking up the
    turf colour. Kept statistically even so the repeat does not jump out when tiled."""
    broad = nz.spectral((S, S), seed, beta=2.4, lo=2.5, hi=12)
    clump = nz.spectral((S, S), seed + 1, beta=2.0, lo=9, hi=70)
    tuft = nz.spectral((S, S), seed + 3, beta=1.4, lo=40, hi=200)
    fibre = nz.spectral((S, S), seed + 2, beta=1.0, lo=60, hi=420, aniso=(0.35, 1.0))
    v = 0.34 * broad + 0.62 * clump + 0.30 * tuft + 0.20 * fibre
    wear = nz.smoothstep(0.5, 2.4, -(0.55 * broad + 0.85 * clump))
    v = v - 1.1 * wear * (0.8 + 0.2 * nz.unit(fibre))
    return nz.unit(v, 0.3, 99.7)


# --------------------------------------------------------------------------- jersey mesh
def fabric_height(seed: int = 5201) -> np.ndarray:
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    xx += 0.5
    yy += 0.5
    px_, py_ = 32.0, 16.0  # hole pitch across / row spacing (rows are staggered)
    row = np.floor(yy / py_)
    cx = (np.floor((xx - (row % 2) * (px_ / 2)) / px_) + 0.5) * px_ + (row % 2) * (px_ / 2)
    cy = (row + 0.5) * py_
    # nearest hole centre also needs the neighbouring rows
    d = np.full((S, S), 1e9, np.float32)
    for dr in (-1, 0, 1):
        r2 = row + dr
        cx2 = (np.floor((xx - (r2 % 2) * (px_ / 2)) / px_ + 0.5)) * px_ + (r2 % 2) * (px_ / 2)
        cy2 = (r2 + 0.5) * py_
        d = np.minimum(d, np.hypot(xx - cx2, (yy - cy2) * 1.0))
    del cx, cy
    hole_r = 5.2
    hole = nz.smoothstep(hole_r + 2.2, hole_r - 1.6, d)  # 1 inside the eyelet
    rim = np.exp(-(((d - (hole_r + 3.0)) / 2.2) ** 2))
    # knit: vertical wales with little V stitches
    u = xx / 8.0
    wale = np.cos(2 * math.pi * u)
    tri = np.abs((u % 1.0) - 0.5) * 2.0
    stitch = np.cos(2 * math.pi * (yy / 8.0 + 0.5 * tri))
    knit = 0.11 * wale + 0.07 * stitch
    irregular = nz.spectral((S, S), seed, beta=1.5, lo=20, hi=300)
    h = (0.62 + knit) * (1.0 - hole) - 0.55 * hole + 0.16 * rim * (1.0 - hole) + 0.02 * irregular
    return nz.blur_wrap(h, 0.6)


# --------------------------------------------------------------------------- leather
def leather_height(seed: int = 5301) -> np.ndarray:
    pts = nz.jittered_points((S, S), 15.5, seed, jitter=0.36)
    d = nz.worley((S, S), pts, k=2)
    f1, f2 = d[..., 0], d[..., 1]
    edge = f2 - f1  # 0 in the grooves between pebbles
    groove = nz.smoothstep(0.0, 4.2, edge) ** 0.7
    cap = np.sqrt(np.clip(1.0 - (f1 / 10.5) ** 2, 0.0, 1.0))  # rounded pebble tops
    size_var = nz.spectral((S, S), seed + 1, beta=2.2, lo=2, hi=18)
    grain = nz.spectral((S, S), seed + 2, beta=0.8, lo=120, hi=480)
    h = groove * (0.35 + 0.65 * cap) * (1.0 + 0.10 * size_var) + 0.03 * grain + 0.10 * size_var
    return nz.blur_wrap(h, 1.0)


# --------------------------------------------------------------------------- concrete
def _wrapped_lines(lines, widths, values, ss: int = 2) -> np.ndarray:
    """Draw polylines on the torus (each one at the nine wrapped offsets). Later = on top."""
    im = Image.new("L", (S * ss, S * ss), 0)
    d = ImageDraw.Draw(im)
    for pts_, w, v in zip(lines, widths, values):
        for oy in (-S, 0, S):
            for ox in (-S, 0, S):
                q = (np.asarray(pts_) + (ox, oy)) * ss
                if q[:, 0].max() < -8 or q[:, 0].min() > S * ss + 8 or q[:, 1].max() < -8 or q[:, 1].min() > S * ss + 8:
                    continue
                d.line([tuple(p) for p in q], fill=int(v), width=max(1, int(round(w * ss))), joint="curve")
    return np.asarray(im.reduce(ss), np.float32) / 255.0


def concrete_layers(seed: int = 5401):
    r = nz.rng(seed)
    broad = nz.spectral((S, S), seed, beta=2.6, lo=1.5, hi=14)
    mid = nz.spectral((S, S), seed + 1, beta=1.8, lo=14, hi=120)
    grain = nz.spectral((S, S), seed + 2, beta=0.5, lo=140, hi=500)
    # pits / bug holes: sparse feature points with varied radii
    npit = 420
    pp = r.uniform(0, S, (npit, 2))
    rad = r.gamma(2.0, 1.6, npit).clip(1.4, 9.0)
    pit = np.zeros((S, S), np.float32)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    for (cx, cy), rr in zip(pp, rad):
        x0, x1 = int(cx - rr - 3), int(cx + rr + 4)
        y0, y1 = int(cy - rr - 3), int(cy + rr + 4)
        xs = np.arange(x0, x1)
        ys = np.arange(y0, y1)
        dd = np.hypot(xs[None, :] + 0.5 - cx, ys[:, None] + 0.5 - cy)
        depth = nz.smoothstep(rr + 1.0, rr * 0.25, dd) * min(1.0, 0.45 + rr / 9.0)
        np.maximum.at(pit, (ys[:, None] % S, xs[None, :] % S), depth)
    del yy, xx
    # hairline cracks: a few wandering polylines
    lines, widths, vals = [], [], []
    for _ in range(5):
        p = r.uniform(0, S, 2)
        a = r.uniform(0, 2 * math.pi)
        seg = [p.copy()]
        for _ in range(int(r.integers(14, 46))):
            a += r.normal(0, 0.20) + (0.9 * r.choice([-1, 1]) if r.random() < 0.10 else 0.0)
            p = p + r.uniform(9, 26) * np.array([math.cos(a), math.sin(a)])
            seg.append(p.copy())
        lines.append(np.array(seg))
        widths.append(r.uniform(0.8, 1.6))
        vals.append(r.uniform(140, 255))
    crack = nz.blur_wrap(_wrapped_lines(lines, widths, vals), 0.5)
    height = 0.50 * broad + 0.16 * mid + 0.050 * grain - 1.25 * pit - 1.0 * crack
    # grime: clouds, vertical water streaks, dirt gathered in pits and cracks
    streak = nz.spectral((S, S), seed + 5, beta=1.6, lo=6, hi=160, aniso=(0.05, 1.0))
    cloud = nz.spectral((S, S), seed + 6, beta=2.3, lo=1.5, hi=30)
    speck = nz.spectral((S, S), seed + 7, beta=0.9, lo=90, hi=400)
    grime = 0.5 + 0.22 * cloud + 0.10 * streak + 0.07 * mid + 0.035 * speck
    grime = grime - 0.33 * nz.blur_wrap(pit, 1.2) - 0.42 * nz.blur_wrap(crack, 1.0)
    return height, nz.unit(grime, 0.3, 99.7)


# --------------------------------------------------------------------------- helmet scratches
def scratches(seed: int = 5501) -> np.ndarray:
    r = nz.rng(seed)
    lines, widths, vals = [], [], []

    def scratch(p, a, length, v, w, curl):
        seg = [np.asarray(p, np.float64)]
        steps = max(2, int(length / 14))
        for _ in range(steps):
            a_ = a + curl * len(seg)
            seg.append(seg[-1] + (length / steps) * np.array([math.cos(a_), math.sin(a_)]))
        lines.append(np.array(seg))
        widths.append(w)
        vals.append(v)

    # long fine hairlines
    for _ in range(330):
        scratch(r.uniform(0, S, 2), r.uniform(0, math.pi), r.gamma(2.0, 62.0) + 18, r.uniform(26, 150),
                r.uniform(0.5, 0.9), r.normal(0, 0.012))
    # scuff clusters: bundles of short parallel strokes from one hit
    for _ in range(26):
        c = r.uniform(0, S, 2)
        a = r.uniform(0, math.pi)
        spread = r.uniform(6, 26)
        for _ in range(int(r.integers(7, 22))):
            off = r.normal(0, spread, 2)
            scratch(c + off, a + r.normal(0, 0.07), r.gamma(2.5, 16.0) + 8, r.uniform(60, 200),
                    r.uniform(0.6, 1.3), r.normal(0, 0.006))
    # a few deep gouges
    for _ in range(16):
        scratch(r.uniform(0, S, 2), r.uniform(0, math.pi), r.uniform(60, 260), r.uniform(190, 255),
                r.uniform(1.1, 1.9), r.normal(0, 0.008))
    order = np.argsort(vals)
    m = _wrapped_lines([lines[i] for i in order], [widths[i] for i in order], [vals[i] for i in order])
    # soft rubbed haze so the mask is not pure black between scratches
    haze = nz.smoothstep(0.2, 2.2, nz.spectral((S, S), seed + 1, beta=2.2, lo=2, hi=30)) * 0.085
    dust = nz.unit(nz.spectral((S, S), seed + 2, beta=0.4, lo=150, hi=500)) * 0.035
    return np.clip(np.maximum(m, haze) + dust * (1 - m), 0.0, 1.0)


def general_noise(seed: int = 5601) -> np.ndarray:
    """Multi-octave fractal noise, full range, flat-ish histogram."""
    n = nz.spectral((S, S), seed, beta=2.0, lo=1.0)
    return 0.6 * nz.equalize(n) + 0.4 * nz.unit(n, 0.1, 99.9)


# --------------------------------------------------------------------------- build
def build() -> list[str]:
    cm.ensure_dirs()
    files = []
    report = []

    def put_normal(name, height, tilt):
        n8 = cm.to_u8(normal_from(height, tilt))
        cm.save_png(n8, name)
        tiled_preview(n8, name, lit(n8))
        files.append(name)
        report.append((name, seam_ratio(n8)))

    def put_mask(name, m):
        m8 = cm.to_u8(m)
        cm.save_png(m8, name)
        tiled_preview(m8, name)
        files.append(name)
        report.append((name, seam_ratio(m8)))

    put_normal("T_Grass_N.png", grass_height(), 0.30)
    put_mask("T_Grass_M.png", grass_mask())
    put_normal("T_Fabric_N.png", fabric_height(), 0.22)
    put_normal("T_Leather_N.png", leather_height(), 0.24)
    c_height, c_grime = concrete_layers()
    put_normal("T_Concrete_N.png", c_height, 0.13)
    put_mask("T_Concrete_M.png", c_grime)
    put_mask("T_Scratches_M.png", scratches())
    put_mask("T_Noise_M.png", general_noise())

    lines = [f"{n:20s} seam step / p99.5 interior step = {v:.3f}" for n, v in report]
    (cm.SCRATCH / "surface_seams.txt").write_text("\n".join(lines) + "\n")
    worst = max(v for _, v in report)
    if worst > 1.10:
        raise RuntimeError("a tiling texture has a visible seam:\n" + "\n".join(lines))
    return files
