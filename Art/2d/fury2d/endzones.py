"""End-zone art: T_EndZone_<id>.png, 4096 x 1024, opaque.

The texture is laid along the end zone's long side, 48.8 m x 9.1 m. That is 5.36 : 1, not
the texture's 4 : 1, so the art is composed in true field proportions (5488 x 1024) and
then squeezed to 4096 wide - emblems come out round and letters keep their shapes once the
engine stretches it back over the end zone.

Each team: primary-colour ground, a tone-on-tone pattern of its own, the name in huge heavy
letters (secondary colour, accent outline), an emblem at each end facing the name, and a
matte painted-on-grass finish.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import common as cm
from . import logos
from . import noise as nz
from . import vec
from .logos import tongue

OUT_W, OUT_H = 4096, 1024
WA = 5488  # width in true proportions (48.8 / 9.1 * 1024)
SS = 2
W, H = WA * SS, OUT_H * SS

EMBLEM_BOX = 640  # emblem square, px at 1x
EMBLEM_CX = 452  # its centre, in from each end
TEXT_MAX_W = 3660
TEXT_MAX_H = 600

# font, tracking (em), horizontal squeeze, shear, pattern
STYLE = {
    "sasquatch": dict(font="alfaslab", track=0.035, squeeze=0.84, shear=0.0, pattern="tracks"),
    "volcanoes": dict(font="anton", track=0.085, squeeze=1.0, shear=0.0, pattern="teeth"),
    "icebreakers": dict(font="barlow-blackitalic", track=0.030, squeeze=1.0, shear=0.0, pattern="shards"),
    "hellhounds": dict(font="saira-xcond", track=0.045, squeeze=1.0, shear=0.14, pattern="flames"),
    "twisters": dict(font="kanit-blackitalic", track=0.020, squeeze=1.0, shear=0.0, pattern="stripes"),
    "amps": dict(font="russo", track=0.300, squeeze=1.0, shear=0.0, pattern="equaliser"),
    "scorpions": dict(font="squada", track=0.060, squeeze=1.0, shear=0.0, pattern="chevrons"),
    "gargoyles": dict(font="germania", track=0.050, squeeze=1.0, shear=0.0, pattern="masonry"),
}


def P(polys=(), strokes=(), holes=()) -> np.ndarray:
    """Rasterise shapes given in 1x true-proportion pixels onto the working canvas."""
    return vec.f32(vec.raster((W, H), polys, holes, strokes, xf=(SS, 0, 0)))


# --------------------------------------------------------------------------- patterns
def pattern(team: dict, c: vec.Canvas) -> None:
    """Paint the team's ground pattern."""
    prim, sec, acc = cm.rgb(team["primary"]), cm.rgb(team["secondary"]), cm.rgb(team["accent"])
    kind = STYLE[team["id"]]["pattern"]
    r = nz.rng(8800 + sum(map(ord, team["id"])))
    dark, light = cm.shade(prim, -0.20), cm.shade(prim, 0.13)

    def bars(color, inset=44, thick=22):
        c.paint(P([vec.rect(0, inset, WA, inset + thick), vec.rect(0, OUT_H - inset - thick, WA, OUT_H - inset)]), color)

    if kind == "tracks":  # a trail of huge clawed footprints striding across, left foot / right foot
        pads, claws = logos.sasquatch_foot(tilt=0.0)
        shapes = pads + claws
        x0, y0, x1, y1 = vec.bbox(shapes)
        cx, cy, length = (x0 + x1) / 2, (y0 + y1) / 2, (y1 - y0)
        polys = []
        step, size = 430, 330
        for i, x in enumerate(np.arange(-80, WA + 300, step)):
            left = i % 2 == 0
            for q in shapes:
                q = (q - (cx, cy)) * (size / length)
                if left:
                    q = q * (-1, 1)
                q = vec.rotate(q, 90 + (-9 if left else 9))  # toes lead to the right
                polys.append(q + (x, OUT_H * 0.5 + (-205 if left else 205)))
        c.paint(P(polys), dark)
        bars(sec, inset=40, thick=20)
    elif kind == "teeth":  # sawtooth lava running along both long edges
        def saw(y_edge, direction, base, depth, pitch, phase):
            polys = []
            for x in np.arange(-pitch + phase, WA + pitch, pitch):
                polys.append(vec.pts((x, y_edge), (x + pitch, y_edge), (x + pitch / 2, y_edge + direction * depth)))
            polys.append(vec.rect(0, min(y_edge, y_edge - direction * base), WA, max(y_edge, y_edge - direction * base)))
            return polys

        c.paint(P(saw(86, 1, 86, 150, 220, 0) + saw(OUT_H - 86, -1, 86, 150, 220, 110)), sec)
        c.paint(P(saw(46, 1, 46, 92, 220, 0) + saw(OUT_H - 46, -1, 46, 92, 220, 110)), acc)
        cracks = []
        for _ in range(26):  # cooling cracks in the black
            x, y = r.uniform(0, WA), r.uniform(300, OUT_H - 300)
            pts_ = [(x, y)]
            a = r.uniform(0, math.pi)
            for _ in range(int(r.integers(3, 7))):
                a += r.normal(0, 0.7)
                x, y = x + 90 * math.cos(a), y + 60 * math.sin(a)
                pts_.append((x, y))
            cracks.append((np.array(pts_), r.uniform(7, 13), False))
        c.paint(P(strokes=cracks), cm.shade(prim, 0.16))
    elif kind == "shards":  # pack ice: pale angular floes drifting across the navy
        polys = []
        for _ in range(64):
            cx, cy = r.uniform(0, WA), r.uniform(0, OUT_H)
            n = int(r.integers(3, 6))
            ang = np.sort(r.uniform(0, 2 * math.pi, n))
            rad = r.uniform(60, 190, n)
            polys.append(np.stack([cx + rad * np.cos(ang) * 1.5, cy + rad * np.sin(ang) * 0.8], 1))
        c.paint(P(polys), light)
        leads = []
        for _ in range(18):  # dark leads of open water cutting between them
            x, y = r.uniform(0, WA), r.choice([0.0, OUT_H])
            pts_ = [(x, y)]
            for _ in range(7):
                x += r.normal(40, 110)
                y += (1 if pts_[0][1] == 0 else -1) * r.uniform(90, 200)
                pts_.append((x, y))
            leads.append((np.array(pts_), r.uniform(8, 16), False))
        c.paint(P(strokes=leads), dark)
        bars(sec, inset=38, thick=18)
    elif kind == "flames":  # fire sweeping up from the near edge, blown toward the right
        def row(base_y, hmin, hmax, pitch, seed_shift):
            rr = nz.rng(8830 + seed_shift)
            polys = [vec.rect(0, base_y, WA, OUT_H + 10)]
            x = -pitch
            while x < WA + pitch:
                hgt = rr.uniform(hmin, hmax)
                polys.append(tongue((x, base_y + 30), (x + rr.uniform(0.25, 0.6) * hgt, base_y - hgt),
                                    pitch * rr.uniform(1.5, 2.2), bow=-rr.uniform(0.10, 0.24), belly=0.3))
                x += pitch * rr.uniform(0.8, 1.2)
            return polys

        c.paint(P(row(OUT_H - 150, 210, 520, 210, 1)), dark)
        c.paint(P(row(OUT_H - 70, 120, 300, 160, 2)), cm.mix(prim, acc, 0.62))
        c.paint(P(row(OUT_H - 26, 60, 150, 120, 3)), acc)
        bars(acc, inset=40, thick=18)
        c.paint(P([vec.rect(0, OUT_H - 62, WA, OUT_H)]), acc)  # keep the lower bar from doubling the fire
    elif kind == "stripes":  # wind-driven diagonal bands
        polys_l, polys_d = [], []
        pitch, wide, slant = 420, 150, OUT_H * 0.62
        for i, x in enumerate(np.arange(-OUT_H, WA + OUT_H, pitch)):
            q = vec.pts((x + slant, 0), (x + slant + wide, 0), (x + wide, OUT_H), (x, OUT_H))
            (polys_l if i % 2 == 0 else polys_d).append(q)
            thin = vec.pts((x + slant + wide + 46, 0), (x + slant + wide + 76, 0), (x + wide + 76, OUT_H), (x + wide + 46, OUT_H))
            (polys_d if i % 2 == 0 else polys_l).append(thin)
        c.paint(P(polys_l), cm.shade(prim, 0.26))
        c.paint(P(polys_d), cm.shade(prim, -0.13))
    elif kind == "equaliser":  # a wall of level meters, top and bottom
        bar_w, pitch = 44, 62
        xs = np.arange(10, WA, pitch)
        env = 0.5 + 0.5 * np.sin(xs / WA * math.pi * 7.0 + 1.3) * np.cos(xs / WA * math.pi * 2.6)
        polys, caps = [], []
        for x, e in zip(xs, env):
            for edge in (0, 1):
                hgt = 70 + 250 * abs(e) * r.uniform(0.55, 1.0)
                hgt = round(hgt / 34) * 34
                y0, y1 = (0, hgt) if edge == 0 else (OUT_H - hgt, OUT_H)
                polys.append(vec.rect(x, y0, x + bar_w, y1))
                cy = hgt + 16 if edge == 0 else OUT_H - hgt - 30
                caps.append(vec.rect(x, cy, x + bar_w, cy + 14))
        c.paint(P(polys), cm.shade(prim, -0.30))
        c.paint(P(caps), acc)
    elif kind == "chevrons":  # armour plates marching toward the middle from both ends
        polys = []
        pitch, arm, thick = 250, 210, 96
        for edge_y in (150, OUT_H - 150):
            for x in np.arange(-pitch, WA + pitch, pitch):
                right = x < WA / 2
                d = arm if right else -arm
                polys.append(vec.pts((x, edge_y - 150), (x + thick, edge_y - 150), (x + thick + d * 0.55, edge_y),
                                     (x + thick, edge_y + 150), (x, edge_y + 150), (x + d * 0.55, edge_y)))
        c.paint(P(polys), dark)
        bars(sec, inset=0, thick=30)
    elif kind == "masonry":  # dressed stone blocks, the mortar lines a shade darker
        lines = []
        course, block = 256, 560
        for j, y in enumerate(np.arange(0, OUT_H + 1, course)):
            lines.append((vec.pts((0, y), (WA, y)), 15, False))
            off = (block / 2) if j % 2 else 0.0
            for x in np.arange(-block + off, WA + block, block):
                lines.append((vec.pts((x, y), (x, y + course)), 15, False))
        c.paint(P(strokes=lines), cm.shade(prim, -0.24))
        chips = []
        for _ in range(70):  # the odd lighter, weathered block face
            j = int(r.integers(0, 4))
            off = (block / 2) if j % 2 else 0.0
            i = int(r.integers(-1, WA // block + 1))
            x, y = i * block + off + 12, j * course + 12
            chips.append(vec.rect(x, y, x + block - 24, y + course - 24))
        c.paint(P(chips[:22]), cm.shade(prim, 0.07))
        c.paint(P(chips[22:40]), cm.shade(prim, -0.07))
        bars(acc, inset=0, thick=24)


# --------------------------------------------------------------------------- lettering
def name_mask(team: dict) -> np.ndarray:
    """The team name as a full-canvas float mask, fitted and centred between the emblems."""
    st = STYLE[team["id"]]
    text = team["name"].upper()
    path = cm.font_path(st["font"])
    shear = st["shear"]
    max_w = TEXT_MAX_W * SS / st["squeeze"]
    max_h = TEXT_MAX_H * SS
    _, m = vec.fit_text(text, path, max_w - shear * max_h, max_h, tracking_em=st["track"])
    img = Image.fromarray(m)
    if st["squeeze"] != 1.0:
        img = img.resize((max(1, round(img.width * st["squeeze"])), img.height), Image.LANCZOS)
    if shear:
        hgt = img.height
        extra = int(math.ceil(shear * hgt))
        # x' = x + shear * (hgt - y): the top leans right
        img = img.transform((img.width + extra, hgt), Image.AFFINE, (1, shear, -shear * hgt, 0, 1, 0), resample=Image.BICUBIC)
    m = np.asarray(img)
    return vec.place((H, W), m, (W - m.shape[1]) / 2.0, (H - m.shape[0]) / 2.0)


# --------------------------------------------------------------------------- paint finish
TURF = np.array([36, 122, 50], np.float32) / 255.0


def painted(rgbf: np.ndarray, seed: int) -> np.ndarray:
    """Matte paint on grass: blade texture, patchy coverage and a little turf showing through."""
    h, w = rgbf.shape[:2]
    fibre = nz.spectral((h, w), seed, beta=0.9, lo=260, hi=1500, aniso=(0.45, 1.0))
    blotch = nz.spectral((h, w), seed + 1, beta=2.1, lo=10, hi=140)
    broad = nz.spectral((h, w), seed + 2, beta=2.6, lo=1.5, hi=12)
    grain = nz.white((h, w), seed + 3)
    y = (np.arange(h, dtype=np.float32) + 0.5) / h
    stripe = np.where(y < 0.5, 1.0, -1.0)[:, None] * nz.smoothstep(0.0, 0.02, np.abs(y - 0.5))[:, None]
    lum = 1.0 + 0.050 * fibre + 0.036 * blotch + 0.030 * broad + 0.014 * grain + 0.016 * stripe
    out = rgbf * lum[..., None]
    thin = nz.smoothstep(0.55, 2.4, 0.8 * blotch + 0.5 * fibre + 0.5 * broad)  # where the paint went on thin
    out = out + (TURF * (0.8 + 0.2 * lum[..., None]) - out) * (0.14 * thin)[..., None]
    return np.clip(out, 0.0, 1.0)


# --------------------------------------------------------------------------- build
def render(team: dict) -> np.ndarray:
    prim, sec, acc = cm.rgb(team["primary"]), cm.rgb(team["secondary"]), cm.rgb(team["accent"])
    c = vec.Canvas(WA, OUT_H, SS, bg=prim)
    pattern(team, c)

    # lettering: shadow, keyline, accent outline, fill
    m = name_mask(team)
    out_w, key_w = 20 * SS, 9 * SS
    ring = vec.dilate(m, out_w)
    keyl = vec.dilate(ring, key_w)
    deep = cm.shade(prim, -0.55)
    c.paint(vec.shift_mask(keyl, 13 * SS, 15 * SS), deep, 0.80)
    c.paint(keyl, deep)
    c.paint(ring, acc)
    c.paint(m, sec)
    # a soft band of shade across the lower part of the letters gives the paint some body
    yy = (np.arange(H, dtype=np.float32) / H)[:, None] * np.ones((1, W), np.float32)
    c.paint(m * nz.smoothstep(0.52, 0.80, yy), cm.shade(sec, -0.16), 0.55)

    # an emblem at each end, both facing the name
    box = EMBLEM_BOX * SS
    emb = logos.render_team(team, size=box, ss=2).astype(np.float32) / 255.0
    y0 = (H - box) // 2
    for cx, mirror in ((EMBLEM_CX, False), (WA - EMBLEM_CX, True)):
        e = emb[:, ::-1] if mirror else emb
        x0 = int(round(cx * SS - box / 2))
        sh = np.zeros((box, box, 4), np.float32)
        sh[..., :3] = deep
        sh[..., 3] = e[..., 3]
        c.paint_rgba(sh, x0 + 10 * SS, y0 + 12 * SS, 0.70)
        c.paint_rgba(e, x0, y0)

    flat = vec.box_down(c.buf[..., :3], SS)  # WA x 1024, true proportions
    img = Image.fromarray(cm.to_u8(flat), "RGB").resize((OUT_W, OUT_H), Image.LANCZOS)
    rgbf = np.asarray(img, np.float32) / 255.0
    return cm.to_u8(painted(rgbf, 8900 + sum(map(ord, team["id"]))))


def build() -> list[str]:
    cm.ensure_dirs()
    files, strips = [], {}
    for team in logos.wanted_teams():
        arr = render(team)
        fn = f"T_EndZone_{team['id']}.png"
        cm.save_png(arr, fn)
        files.append(fn)
        img = Image.fromarray(arr, "RGB")
        # preview: the raw 4:1 texture, then as it lies on the field (stretched back to 48.8 x 9.1 m)
        on_field = img.resize((WA, OUT_H), Image.LANCZOS)
        detail = img.crop((560, 300, 560 + 1384, 300 + 420))  # 1:1 pixels: edge quality and paint finish
        cm.save_preview(cm.vstack([cm.downscale(img, 1100), cm.downscale(on_field, 1384), detail], gap=8), fn)
        strips[team["id"]] = on_field
    # one sheet with all eight as they lie on the field
    allz = []
    for team in cm.load_teams():
        p = cm.OUT / f"T_EndZone_{team['id']}.png"
        if team["id"] in strips:
            allz.append(strips[team["id"]])
        elif p.exists():
            allz.append(Image.open(p).convert("RGB").resize((WA, OUT_H), Image.LANCZOS))
    if allz:
        small = [z.resize((692, 129), Image.LANCZOS) for z in allz]
        rows = [cm.hstack(small[i : i + 2], gap=6) for i in range(0, len(small), 2)]
        cm.save_preview(cm.vstack(rows, gap=0), "T_EndZones_sheet.png")
    return files
