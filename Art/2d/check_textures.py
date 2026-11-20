# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow>=10.1", "numpy>=1.26"]
# ///
"""Sanity-check everything make_textures.py wrote (sizes, modes, channel rules, geometry).

    uv run --with pillow --with numpy Art/2d/check_textures.py

Exits non-zero if any deliverable is missing or breaks its spec.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Art" / "export" / "textures"
TEAMS = [t["id"] for t in json.loads((ROOT / "Art" / "teams.json").read_text())["teams"]]
ICONS = ["Flame", "Ball", "Star", "Bolt", "Shield", "Arrow", "Crown", "Gamepad", "Keyboard", "Cpu"]

fails: list[str] = []
count = 0


def load(name: str, size: tuple[int, int], mode: str):
    global count
    p = OUT / name
    if not p.exists():
        fails.append(f"{name}: missing")
        return None
    im = Image.open(p)
    count += 1
    if im.size != size:
        fails.append(f"{name}: size {im.size}, expected {size}")
    if im.mode != mode:
        fails.append(f"{name}: mode {im.mode}, expected {mode}")
    return np.asarray(im)


def check(cond: bool, msg: str) -> None:
    if not cond:
        fails.append(msg)


def seam(a: np.ndarray) -> float:
    a = a.astype(np.float32)
    if a.ndim == 2:
        a = a[..., None]
    worst = 0.0
    for axis in (0, 1):
        b = np.moveaxis(a, axis, 0)
        inner = np.abs(b[1:] - b[:-1]).reshape(b.shape[0] - 1, -1).mean(axis=1)
        worst = max(worst, float(np.abs(b[0] - b[-1]).mean()) / max(float(np.percentile(inner, 99.5)), 1e-9))
    return worst


# ---- 1 logos
for t in TEAMS:
    a = load(f"T_Logo_{t}.png", (1024, 1024), "RGBA")
    if a is None:
        continue
    al = a[..., 3]
    ys, xs = np.nonzero(al > 8)
    ext = max(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1) / 1024.0
    check(0.835 <= ext <= 0.865, f"T_Logo_{t}: fills {ext:.3f} of the square (want ~0.85)")
    cx, cy = (xs.max() + xs.min()) / 2, (ys.max() + ys.min()) / 2
    check(abs(cx - 511.5) < 3 and abs(cy - 511.5) < 3, f"T_Logo_{t}: not centred ({cx:.1f}, {cy:.1f})")
    check(al[0, 0] == 0 and al[-1, -1] == 0 and al.max() == 255, f"T_Logo_{t}: alpha range looks wrong")

# ---- 2 numbers
a = load("T_Numbers.png", (4096, 4096), "RGBA")
if a is not None:
    R, G, B, A = (a[..., i].astype(np.int32) for i in range(4))
    check(B.max() == 0, "T_Numbers: blue channel is not 0")
    check(A.min() == 255, "T_Numbers: alpha is not 255 everywhere")
    check((R + G).max() <= 255, "T_Numbers: fill and ring overlap")
    cell = 409.6
    worst_edge, margins = 0, []
    for n in range(100):
        c, r = n % 10, n // 10
        x0, x1, y0, y1 = round(c * cell), round((c + 1) * cell), round(r * cell), round((r + 1) * cell)
        ink = np.maximum(R[y0:y1, x0:x1], G[y0:y1, x0:x1])
        worst_edge = max(worst_edge, int(ink[0].max()), int(ink[-1].max()), int(ink[:, 0].max()), int(ink[:, -1].max()))
        ys, xs = np.nonzero(R[y0:y1, x0:x1] > 127)
        check(len(xs) > 0, f"T_Numbers: cell {n} is empty")
        if len(xs):
            margins.append(((ys.min()) / cell, (y1 - y0 - 1 - ys.max()) / cell))
            if n >= 20 and n % 10 != 1 and n // 10 != 1:  # two full-width digits span the cell width
                mx = (xs.min() / cell, (x1 - x0 - 1 - xs.max()) / cell)
                check(abs(mx[0] - 0.09) < 0.006 and abs(mx[1] - 0.09) < 0.006, f"T_Numbers: {n} side margins {mx}")
    check(worst_edge == 0, "T_Numbers: ink touches a cell border")
    m = np.array(margins)
    check(bool(np.all(np.abs(m - 0.09) < 0.006)), f"T_Numbers: top/bottom margins {m.min():.3f}..{m.max():.3f}")

# ---- 3 end zones
for t in TEAMS:
    load(f"T_EndZone_{t}.png", (4096, 1024), "RGB")

# ---- 4 field
f = load("T_Field.png", (8192, 4096), "RGB")
L = load("T_FieldLines.png", (8192, 4096), "L")
if L is not None:
    def paint(xm, ym):  # metres from midfield -> mask value
        return int(L[int((ym + 32.0) * 64), int((xm + 64.0) * 64)])

    yd = 0.9144
    spots = [
        ("50-yard line", (0.0, 10.0), True), ("between yard lines", (2.286, 10.0), False),
        ("45-yard line", (5 * yd, 12.0), True), ("10-yard line", (-40 * yd, -3.0), True),
        ("goal line", (45.62, 5.0), True), ("far goal line", (-45.62, -5.0), True),
        ("end zone is plain turf", (50.0, 0.0), False), ("end zone is plain turf (far)", (-50.0, 12.0), False),
        ("midfield circle is clear", (0.0, 0.0), False), ("midfield circle is clear at 6.8 m", (0.0, 6.8), False),
        ("50 resumes outside the circle", (0.0, 7.3), True), ("45 is cut inside the circle", (5 * yd, 3.0), False),
        ("border, near side", (0.0, 25.2), True), ("border, far side", (10.0, -25.2), True),
        ("border behind the end line", (55.8, 0.0), True), ("apron", (60.0, 0.0), False), ("apron near side", (30.0, 29.0), False),
        ("team area near", (0.0, 29.7), True), ("team area far", (-17.0, -29.7), True), ("outside team area", (19.5, 29.7), False),
        ("inbound hash", (13 * yd, 6.1), True), ("no hash off the row", (13 * yd, 7.0), False),
        ("hash cleared inside the circle", (3 * yd, 6.1), False),
        ("sideline hash", (7 * yd, 24.0), True), ("conversion mark", (45.72 - 3 * yd, 0.0), True),
        ("near number (the 0 of 30)", (-20 * yd + 0.36 + 0.61, 17.9), True),
    ]
    for label, (xm, ym), want in spots:
        v = paint(xm, ym)
        check((v > 200) == want, f"T_FieldLines: {label} at ({xm:.2f}, {ym:.2f}) m -> {v}")
    check(L[:, :400].max() == 0 and L[:, -400:].max() == 0, "T_FieldLines: paint in the outer apron")
if f is not None:
    g = f[2048 + 600, 4096 + 150].astype(int)
    check(g[1] > g[0] + 40 and g[1] > g[2] + 40, f"T_Field: turf is not green at midfield {g}")

# ---- 5 ads
load("T_Ads.png", (8192, 512), "RGB")

# ---- 6 title
for name, size in (("T_Title.png", (2048, 1024)), ("T_TitleSmall.png", (1024, 256))):
    a = load(name, size, "RGBA")
    if a is not None:
        al = a[..., 3]
        check(al[0, 0] == 0 and al.max() == 255, f"{name}: alpha range looks wrong")
        edge = max(int(al[0].max()), int(al[-1].max()), int(al[:, 0].max()), int(al[:, -1].max()))
        check(edge < 40, f"{name}: art runs into the edge of the canvas (alpha {edge})")

# ---- 7 icons
for i in ICONS:
    a = load(f"T_Icon_{i}.png", (256, 256), "RGBA")
    if a is not None:
        check(a[..., :3].min() == 255, f"T_Icon_{i}: RGB is not pure white")
        check(a[..., 3].max() == 255 and a[0, 0, 3] == 0, f"T_Icon_{i}: alpha range looks wrong")

# ---- 8 tiling surfaces
for name in ("T_Grass_N", "T_Fabric_N", "T_Leather_N", "T_Concrete_N"):
    a = load(name + ".png", (1024, 1024), "RGB")
    if a is not None:
        mean = a.reshape(-1, 3).mean(0)
        check(abs(mean[0] - 128) < 3 and abs(mean[1] - 128) < 3 and mean[2] > 215, f"{name}: mean {mean.round(1)} is not a flat-ish normal")
        check(a[..., 2].min() > 128, f"{name}: normals point into the surface")
        check(seam(a) <= 1.10, f"{name}: seam ratio {seam(a):.2f}")
for name in ("T_Grass_M", "T_Concrete_M", "T_Scratches_M", "T_Noise_M"):
    a = load(name + ".png", (1024, 1024), "L")
    if a is not None:
        check(seam(a) <= 1.10, f"{name}: seam ratio {seam(a):.2f}")
        check(int(a.max()) - int(a.min()) > 200, f"{name}: uses only {a.min()}..{a.max()}")

# ---- 9 sky
a = load("T_NightSky.png", (4096, 2048), "RGB")
if a is not None:
    up = a[:1024].astype(np.float32)
    step = np.abs(up[:, 1:] - up[:, :-1]).mean()
    wrap = np.abs(up[:, 0] - up[:, -1]).mean()
    check(wrap < 2.5 * step + 0.5, f"T_NightSky: left/right edges do not meet ({wrap:.2f} vs {step:.2f})")
    check(a[1200:].mean() < 6.0, f"T_NightSky: lower half is not near-black ({a[1200:].mean():.1f})")

print(f"checked {count} textures in {OUT}")
if fails:
    print(f"{len(fails)} problem(s):")
    for m in fails:
        print("  -", m)
    sys.exit(1)
print("all good")
