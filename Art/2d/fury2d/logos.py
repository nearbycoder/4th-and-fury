"""Team emblems: T_Logo_<id>.png, 1024 x 1024 RGBA on a transparent background.

Every emblem is flat vector art drawn here from scratch (no traced or borrowed marks):
a few team-palette colours, a dark keyline and a light outer outline so it holds up on any
helmet or menu background. Emblems with a facing direction face RIGHT. The art is
auto-fitted so its longest side (outline included) fills 85% of the square.
"""
from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image

from . import common as cm
from . import vec

SIZE = 1024
SS = 4
FILL = 0.85


# =========================================================================== emblem container
class Emblem:
    """A display list in free design units plus the rings drawn around its silhouette."""

    def __init__(self, rings):
        # rings: inside -> outside, each (colour, width as a fraction of the image, closing radius)
        self.rings = rings
        self.items = []

    def add(self, color, polys=(), holes=(), strokes=(), sil=True, clip=None, name=None, opacity=1.0):
        """polys/holes: polygons; strokes: (points, width, closed). `sil` = part of the
        silhouette the rings wrap around. `clip` = name(s) of earlier items to stay inside."""
        self.items.append(dict(color=np.asarray(color, np.float32), polys=[np.asarray(p, np.float64) for p in polys],
                               holes=[np.asarray(p, np.float64) for p in holes],
                               strokes=[(np.asarray(p, np.float64), w, c) for p, w, c in strokes],
                               sil=sil, clip=clip, name=name, opacity=opacity))
        return self


def render(emb: Emblem, size: int = SIZE, ss: int = SS, fill: float = FILL) -> np.ndarray:
    """Rasterise an emblem to uint8 straight-alpha RGBA, size x size."""
    geo = []
    for it in emb.items:
        if not it["sil"]:
            continue
        geo += it["polys"]
        for p, w, _ in it["strokes"]:
            geo += [p + w / 2.0, p - w / 2.0]
    x0, y0, x1, y1 = vec.bbox(geo)
    ring_px = sum(w for _, w, _ in emb.rings) * size
    s = (fill * size - 2.0 * ring_px) / max(x1 - x0, y1 - y0)
    ox = size / 2.0 - s * (x0 + x1) / 2.0
    oy = size / 2.0 - s * (y0 + y1) / 2.0
    xf = (s * ss, ox * ss, oy * ss)
    S = size * ss

    def mask_of(it):
        return vec.raster((S, S), it["polys"], it["holes"], it["strokes"], xf=xf)

    sil = np.zeros((S, S), np.uint8)
    for it in emb.items:
        if it["sil"]:
            np.maximum(sil, mask_of(it), out=sil)

    canvas = vec.Canvas(size, size, ss)
    cur = vec.f32(sil)
    ring_masks = []
    for color, w, close in emb.rings:
        if close > 0:
            cur = vec.close_gaps(cur, close * size * ss)
        cur = vec.dilate(cur, w * size * ss)
        ring_masks.append((cur, color))
    for m, color in reversed(ring_masks):
        canvas.paint(m, color)
    del ring_masks, cur

    named = {}
    for it in emb.items:
        m = vec.f32(mask_of(it))
        if it["clip"]:
            names = [it["clip"]] if isinstance(it["clip"], str) else it["clip"]
            clip = named[names[0]]
            for nme in names[1:]:
                clip = np.maximum(clip, named[nme])
            m = m * clip
        if it["name"]:
            named[it["name"]] = m
        canvas.paint(m, it["color"], it["opacity"])
    return canvas.result(bleed=np.asarray(emb.rings[-1][0], np.float32))


# =========================================================================== shape helpers
def tongue(base, tip, width, bow=0.2, power=0.85, belly=0.35, n=22) -> np.ndarray:
    """A pointed, curved tongue (flame lick, horn, claw): flat base `width` wide centred on
    `base`, tapering to `tip`; `bow` bends it sideways as a fraction of its length."""
    base, tip = np.asarray(base, np.float64), np.asarray(tip, np.float64)
    axis = tip - base
    L = math.hypot(*axis)
    u = axis / L
    nr = np.array([-u[1], u[0]])
    ctrl = base + axis * 0.5 + nr * bow * L
    t = np.linspace(0.0, 1.0, n)[:, None]
    c = (1 - t) ** 2 * base + 2 * t * (1 - t) * ctrl + t**2 * tip
    d = 2 * (1 - t) * (ctrl - base) + 2 * t * (tip - ctrl)
    d /= np.hypot(d[:, 0], d[:, 1])[:, None]
    nn = np.stack([-d[:, 1], d[:, 0]], 1)
    w = width * 0.5 * (1 - t) ** power * (1 + belly * np.sin(np.pi * t))
    left, right = c + nn * w, c - nn * w
    return np.concatenate([left, right[::-1][1:]])


def sym(half, cx: float = 500.0) -> np.ndarray:
    """Close a shape by mirroring: `half` runs from the top of the axis, down one side, to
    the bottom of the axis."""
    half = np.asarray(half, np.float64)
    other = half[::-1].copy()
    other[:, 0] = 2 * cx - other[:, 0]
    return np.concatenate([half, other[1:-1]])


def sym_spec(spec, cx: float = 500.0):
    """Mirror a blob() point spec about x = cx (first and last points lie on the axis)."""
    out = list(spec)
    for p in reversed(spec[1:-1]):
        out.append((2 * cx - p[0], p[1]) + tuple(p[2:]))
    return out


def flip(p, cx: float = 500.0) -> np.ndarray:
    return vec.mirror_x(p, cx)


def both(p, cx: float = 500.0):
    """A shape and its mirror image."""
    return [np.asarray(p, np.float64), flip(p, cx)]


class Spine:
    """Arc-length parametrised centreline for building segmented bodies."""

    def __init__(self, points, n: int = 40):
        self.p = vec.blob(points, closed=False, n=n)
        seg = np.hypot(*np.diff(self.p, axis=0).T)
        self.s = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(self.s[-1])

    def at(self, t):
        """Points and unit tangents at fractions t (0..1) of the length."""
        t = np.atleast_1d(np.asarray(t, np.float64))
        s = np.clip(t, 0, 1) * self.length
        x = np.interp(s, self.s, self.p[:, 0])
        y = np.interp(s, self.s, self.p[:, 1])
        e = self.length * 1e-3
        xa, ya = np.interp(np.clip(s - e, 0, self.length), self.s, self.p[:, 0]), np.interp(np.clip(s - e, 0, self.length), self.s, self.p[:, 1])
        xb, yb = np.interp(np.clip(s + e, 0, self.length), self.s, self.p[:, 0]), np.interp(np.clip(s + e, 0, self.length), self.s, self.p[:, 1])
        d = np.stack([xb - xa, yb - ya], 1)
        d /= np.hypot(d[:, 0], d[:, 1])[:, None]
        return np.stack([x, y], 1), d

    def plate(self, t0, t1, w0, w1, lo=-1.0, hi=1.0, bulge=0.08, n=6, r=16.0):
        """A plate following the spine from t0 to t1. Width goes w0 -> w1; lo/hi pick the
        slice across the width (-1 = one edge, +1 = the other), so highlights can share it."""
        ts = np.linspace(t0, t1, n)
        c, d = self.at(ts)
        nn = np.stack([-d[:, 1], d[:, 0]], 1)
        u = np.linspace(0.0, 1.0, n)
        half = (w0 + (w1 - w0) * u) * (1.0 + bulge * np.sin(np.pi * u)) / 2.0
        a = c + nn * (half * hi)[:, None]
        b = c + nn * (half * lo)[:, None]
        return vec.round_corners(np.concatenate([a, b[::-1]]), r)


# =========================================================================== the eight emblems
def sasquatch_foot(tilt: float = 16.0):
    """The Sasquatch footprint in design units: (pads, claws). Reused by the end-zone art."""
    def rot(p):
        return vec.rotate(p, tilt, about=(530, 560))

    sole = vec.blob([
        (280, 512), (318, 430), (425, 380), (560, 350), (694, 336), (786, 384), (810, 480), (768, 580),
        (688, 664), (664, 770), (664, 868), (602, 944), (514, 946), (446, 888), (420, 786), (372, 684),
        (308, 596),
    ], k=0.34)

    def toe(cx, cy, w, h, ang):
        """A toe pad and the hooked claw growing out of it."""
        a, b = w / 2.0, h / 2.0
        pad = vec.blob([(0, -b), (a * 0.72, -b * 0.70), (a, 0), (a * 0.72, b * 0.74), (0, b), (-a * 0.72, b * 0.74),
                        (-a, 0), (-a * 0.72, -b * 0.70)], k=0.37)
        claw = tongue((0, -b * 0.80), (a * 0.42, -b * 0.80 - h * 1.02), w * 0.66, bow=-0.17, belly=0.16)
        return [vec.rotate(q, ang) + (cx, cy) for q in (pad, claw)]

    toes = [toe(738, 250, 168, 150, 10), toe(590, 262, 120, 120, 1), toe(470, 292, 106, 108, -8),
            toe(366, 336, 96, 98, -18), toe(262, 408, 88, 90, -31)]
    pads = [rot(sole)] + [rot(pd) for pd, _ in toes]
    claws = [rot(cl) for _, cl in toes]
    return pads, claws


def emblem_sasquatch(t) -> Emblem:
    """A huge bare footprint, every toe tipped with a claw, striding up and to the right."""
    green, cream, brown = cm.rgb(t["primary"]), cm.rgb(t["secondary"]), cm.rgb(t["accent"])
    e = Emblem([(cm.shade(brown, -0.30), 0.013, 0.0), (green, 0.027, 0.024), (cm.WHITE, 0.022, 0.0)])
    pads, claws = sasquatch_foot()
    e.add(cm.WHITE, claws)
    e.add(cm.mix(cm.WHITE, brown, 0.30), claws, holes=[vec.shift(q, 11, -6) for q in claws], sil=False)
    e.add(cream, pads, name="foot")
    # a wedge of shadow down the trailing edge gives the print some weight
    e.add(cm.mix(cream, brown, 0.34), pads, holes=[vec.shift(q, 24, -15) for q in pads], sil=False)
    return e


def emblem_volcanoes(t) -> Emblem:
    """A black cone blowing its top: a crown of fire above, lava running down the flanks."""
    black, orange, yellow = cm.rgb(t["primary"]), cm.rgb(t["secondary"]), cm.rgb(t["accent"])
    e = Emblem([(black, 0.012, 0.016), (cm.WHITE, 0.025, 0.0)])

    half = np.concatenate([[(500, 556), (548, 572), (590, 552), (616, 566)],
                           vec.cubic((616, 566), (668, 724), (760, 852), (946, 905), 20), [(500, 905)]])
    e.add(black, [sym(half)], name="cone")

    # the eruption: seven tongues of fire fanning out of the crater
    def fan(k, base_y):
        def bx(x):
            return 500 + (x - 500) * k

        parts = [tongue((500, base_y), (500, base_y - 486 * k), 236 * k, 0.0, belly=0.25)]
        for x, tipx, rise, wid, bow in ((552, 668, 408, 190, 0.11), (596, 812, 300, 176, 0.17), (618, 900, 132, 150, 0.22)):
            parts += both(tongue((bx(x), base_y + 6), (bx(tipx), base_y - rise * k), wid * k, bow, belly=0.30))
        parts.append(vec.ellipse(500, base_y + 4, 128 * k, 48 * k))
        return parts

    e.add(orange, fan(1.0, 560), name="plume")
    e.add(yellow, fan(0.56, 562), sil=False)

    # the lit flank of the cone, and lava pouring down its face
    facet = np.concatenate([[(500, 556), (452, 572), (410, 552), (384, 566)],
                            vec.cubic((384, 566), (332, 724), (240, 852), (54, 905), 20), [(330, 905)]])
    e.add(cm.shade(black, 0.13), [facet], sil=False, clip="cone")
    flow = vec.blob([(440, 566), (560, 566), (592, 662), (626, 752), (606, 818), (566, 788), (538, 852), (500, 800),
                     (462, 852), (434, 788), (394, 818), (374, 752), (408, 662)], k=0.36)
    side = Spine([(606, 572), (646, 660), (704, 748), (756, 824)]).plate(0.0, 1.0, 58, 34, n=7, r=16)
    e.add(orange, [flow] + both(side), sil=False, clip="cone")
    hot = vec.blob([(470, 570), (530, 570), (548, 660), (566, 736), (548, 770), (524, 742), (500, 772), (476, 742),
                    (452, 770), (434, 736), (452, 660)], k=0.36)
    e.add(yellow, [hot], sil=False, clip="cone")
    return e


def emblem_icebreakers(t) -> Emblem:
    """A ship's prow riding up and over the pack ice, driving to the right."""
    navy, ice, white = cm.rgb(t["primary"]), cm.rgb(t["secondary"]), cm.rgb(t["accent"])
    e = Emblem([(cm.shade(navy, -0.40), 0.012, 0.012), (white, 0.024, 0.0)])

    def tilt(p):  # bow lifted as the hull climbs onto the ice
        return vec.rotate(np.asarray(p, np.float64), -7.0, about=(470, 520))

    top, foot = (768, 150), (606, 772)
    # superstructure behind the bow (drawn first; the hull overlaps its base)
    house = vec.pts((176, 350), (176, 214), (292, 198), (292, 132), (424, 112), (440, 330))
    e.add(white, [tilt(house)], name="house")
    e.add(navy, [tilt(vec.pts((308, 160), (410, 144), (412, 172), (308, 188))),
                 tilt(vec.pts((192, 244), (424, 208), (426, 236), (192, 272)))], sil=False, clip="house")
    stack = vec.pts((206, 222), (212, 150), (262, 143), (268, 214))
    e.add(ice, [tilt(stack)], name="stack")
    e.add(navy, [tilt(vec.pts((208, 176), (266, 168), (266, 150), (208, 158)))], sil=False, clip="stack")

    # hull: the big near side and a sliver of the far side past the stem
    sheer = vec.quadratic((116, 336), (480, 306), top, 24)
    near = np.concatenate([[(116, 336)], sheer, [foot, (196, 772)]])
    e.add(navy, [tilt(near)], name="near")
    far = vec.pts(top, (892, 256), (812, 648), foot)
    e.add(cm.mix(navy, ice, 0.58), [tilt(far)], name="far")
    stripe = np.concatenate([[(116, 336)], sheer, [(758, 226)], vec.quadratic((758, 226), (478, 372), (124, 398), 24)])
    e.add(white, [tilt(stripe)], sil=False, clip="near")
    e.add(white, [tilt(vec.pts(top, (892, 256), (882, 322), (756, 222)))], sil=False, clip="far")
    e.add(white, strokes=[(tilt(vec.pts(top, foot)), 16, False)], sil=False)
    ax, ay = 486, 520
    e.add(white, [tilt(vec.ellipse(ax, ay - 66, 27))], holes=[tilt(vec.ellipse(ax, ay - 66, 11))], sil=False)
    e.add(white, strokes=[(tilt(vec.pts((ax, ay - 42), (ax, ay + 60))), 17, False),
                          (tilt(vec.pts((ax - 38, ay - 14), (ax + 38, ay - 14))), 15, False),
                          (tilt(vec.arc(ax, ay + 6, 58, 18, 162, 16)), 17, False)], sil=False, clip="near")

    # jagged ice thrown up along the waterline, biggest where the stem strikes
    def shard(bl, tip, br, split=0.5):
        bl, tip, br = (np.asarray(p, np.float64) for p in (bl, tip, br))
        bm = bl + (br - bl) * split
        return np.array([bl, tip, br]), np.array([bl, tip, bm])

    shards = [shard((40, 900), (96, 716), (240, 900), 0.40), shard((170, 900), (262, 628), (390, 900), 0.48),
              shard((320, 900), (428, 706), (530, 900), 0.52), shard((440, 900), (566, 520), (690, 900), 0.50),
              shard((610, 900), (790, 566), (850, 900), 0.56), shard((770, 900), (950, 684), (966, 900), 0.58)]
    floe = vec.pts((28, 884), (976, 884), (944, 958), (62, 958))
    e.add(ice, [floe] + [s[0] for s in shards], name="ice")
    e.add(white, [s[1] for s in shards], sil=False, clip="ice")
    chips = [vec.pts((868, 470), (924, 420), (952, 494), (896, 532)), vec.pts((918, 300), (954, 270), (968, 318), (936, 342)),
             vec.pts((806, 452), (838, 430), (850, 470), (820, 488))]
    e.add(ice, chips, name="chips")
    e.add(white, [np.array([c[0], c[1], (c[1] + c[3]) / 2.0]) for c in chips], sil=False, clip="chips")
    return e


def emblem_hellhounds(t) -> Emblem:
    """A snarling hound in profile, facing right, its mane a sheet of flame."""
    crimson, coal, orange = cm.rgb(t["primary"]), cm.rgb(t["secondary"]), cm.rgb(t["accent"])
    e = Emblem([(cm.shade(coal, -0.4), 0.012, 0.012), (cm.WHITE, 0.024, 0.0)])

    # mane: licks of flame streaming back off the skull and neck
    licks = [((440, 250), (236, 52), 200, -0.26), ((415, 340), (96, 112), 225, -0.25),
             ((390, 455), (14, 290), 235, -0.23), ((385, 590), (12, 520), 230, -0.20),
             ((400, 715), (64, 756), 215, -0.20), ((440, 820), (176, 962), 180, -0.22)]
    body = vec.pts((400, 170), (560, 250), (560, 740), (470, 880), (380, 820), (350, 500))  # no gaps behind the fur
    e.add(crimson, [tongue(b, tp, w, bow) for b, tp, w, bow in licks] + [body], name="mane")
    inner = []
    for b, tp, w, bow in licks:
        b, tp = np.asarray(b, float), np.asarray(tp, float)
        inner.append(tongue(b + (10, 0), b + (tp - b) * 0.62, w * 0.52, bow))
    e.add(orange, inner, sil=False)

    # head: skull, long muzzle, open jaw; the back edge breaks into tufts of fur
    head = vec.blob([
        (415, 245), (468, 214), (552, 236), (625, 266), (696, 300, "c"), (724, 352), (800, 368), (880, 386),
        (938, 404, "c"), (962, 442), (942, 480, "c"), (905, 488), (850, 502), (770, 515), (690, 533),
        (612, 562, "c"), (692, 596), (780, 630), (858, 662, "c"), (846, 706), (780, 734), (690, 728),
        (610, 716), (575, 770, "c"), (470, 862, "c"), (505, 762, "c"), (398, 764, "c"), (458, 668, "c"),
        (352, 642, "c"), (428, 562, "c"), (328, 512, "c"), (412, 452, "c"), (332, 382, "c"), (414, 342, "c"),
        (394, 299), (397, 265),
    ], k=0.33)
    e.add(coal, [head], name="head")

    # mouth: a red gape with white teeth
    gape = vec.pts((612, 562), (690, 533), (770, 515), (850, 502), (908, 490), (858, 662), (780, 630), (692, 596))
    e.add(cm.shade(crimson, -0.35), [gape], name="gape")
    teeth = [vec.pts((892, 494), (848, 502), (868, 588)),  # upper canine
             vec.pts((798, 637), (842, 655), (830, 562)),  # lower canine
             vec.pts((836, 504), (806, 509), (818, 540)), vec.pts((798, 510), (768, 515), (780, 544)),
             vec.pts((760, 517), (730, 524), (742, 550)), vec.pts((722, 526), (694, 532), (706, 554)),
             vec.pts((776, 628), (748, 617), (766, 590)), vec.pts((738, 613), (712, 603), (730, 580))]
    e.add(cm.WHITE, teeth, sil=False)

    # planes of the face picked out by the firelight
    ear = vec.blob([(510, 272), (540, 314), (508, 434), (453, 550), (406, 577),
                    (378, 541), (384, 446), (403, 339), (450, 277)], k=0.36)
    e.add(coal, [ear])
    e.add(crimson, [vec.blob([(469, 300), (499, 315), (473, 410), (417, 528),
                              (407, 481), (425, 371)], k=0.36)], sil=False)
    e.add(crimson, [vec.pts((560, 430), (650, 452), (716, 470), (668, 506), (606, 548), (566, 610), (520, 520))],
          sil=False, clip="head")  # cheek
    e.add(crimson, [vec.pts((742, 372), (884, 398), (930, 414), (922, 428), (744, 392))], sil=False, clip="head")  # bridge
    # brow and eye
    e.add(crimson, strokes=[(vec.pts((600, 296), (662, 312), (716, 340)), 13, False)], sil=False, clip="head")
    eye = vec.pts((622, 328), (722, 358), (702, 392), (646, 376))
    e.add(orange, [eye], sil=False)
    e.add(cm.WHITE, [vec.pts((636, 336), (678, 349), (664, 364), (646, 358))], sil=False)
    # snarl wrinkles over the lip
    e.add(orange, strokes=[(vec.pts((778, 412), (798, 462)), 11, False), (vec.pts((820, 420), (834, 466)), 11, False),
                           (vec.pts((860, 428), (868, 462)), 11, False)], sil=False, clip="head")
    return e


def emblem_twisters(t) -> Emblem:
    """A funnel cloud built from stacked, spinning bands, leaning into its run to the right."""
    gold, slate, white = cm.rgb(t["primary"]), cm.rgb(t["secondary"]), cm.rgb(t["accent"])
    e = Emblem([(slate, 0.013, 0.0), (white, 0.024, 0.0)])
    tilt = -10.0

    def band(cx, cy, w, th, tail=0):
        """A 'smile' crescent, th thick in the middle; tail=-1/+1 whips the left/right tip out."""
        L, R = np.array([-w / 2.0, 0.0]), np.array([w / 2.0, 0.0])
        if tail < 0:
            L = L + (-0.11 * w, -0.34 * th)
        if tail > 0:
            R = R + (0.11 * w, -0.34 * th)
        top, bot = 0.36 * th, 2.36 * th
        p = np.concatenate([[L], vec.quadratic(L, (0, top), R, 22), vec.quadratic(R, (0, bot), L, 26)[:-1]])
        return vec.rotate(p, tilt) + (cx, cy)

    rows = [(550, 306, 650, 116, 1), (520, 440, 504, 106, -1), (484, 562, 384, 94, 1), (460, 664, 280, 82, -1),
            (462, 754, 190, 68, 1)]
    # the mouth of the funnel, seen from a little above
    mouth = vec.ellipse(540, 168, 410, 96, rot=tilt)
    eye = vec.ellipse(546, 150, 268, 44, rot=tilt)
    tip = tongue((484, 800), (548, 948), 96, bow=-0.24, belly=0.1)
    # a solid core so the gaps between bands read as shadow, not as holes
    core = vec.blob([(170, 232), (540, 250), (905, 106), (760, 330), (640, 500), (560, 680), (536, 800), (500, 860),
                     (452, 800), (390, 690), (330, 560), (250, 400)], k=0.30)
    e.add(slate, [core])
    e.add(gold, [mouth] + [band(*r) for r in rows] + [tip], name="bands")
    e.add(slate, [eye], sil=False)
    shine = [band(cx - w * 0.14, cy + th * 0.10, w * 0.46, th * 0.30) for cx, cy, w, th, _ in rows]
    e.add(white, shine, sil=False, clip="bands")
    return e


def emblem_amps(t) -> Emblem:
    """A lightning bolt blasting through a guitar pick."""
    magenta, black, cyan = cm.rgb(t["primary"]), cm.rgb(t["secondary"]), cm.rgb(t["accent"])
    e = Emblem([(black, 0.013, 0.0), (cyan, 0.024, 0.0)])
    pick = vec.svg("M 500 150 C 640 150 770 175 835 235 C 880 280 880 340 850 400 C 800 520 660 760 560 880 "
                   "C 530 915 470 915 440 880 C 340 760 200 520 150 400 C 120 340 120 280 165 235 "
                   "C 230 175 360 150 500 150 Z", n=24)[0]
    e.add(magenta, [pick], name="pick")
    inset = vec.scale(pick, 0.80, about=(500, 455))
    e.add(black, strokes=[(inset, 17, True)], sil=False)
    bolt = vec.pts((596, 40), (316, 548), (486, 548), (396, 964), (728, 420), (552, 420), (744, 40))
    e.add(black, strokes=[(bolt, 46, True)], sil=True)
    e.add(cyan, [bolt])
    core = vec.pts((628, 96), (404, 500), (548, 500), (470, 800), (640, 468), (500, 468), (690, 96))
    e.add(cm.WHITE, [core], sil=False, clip=None)
    return e


def emblem_scorpions(t) -> Emblem:
    """A scorpion's tail arched up and over to the right, sting cocked to strike."""
    teal, sand, black = cm.rgb(t["primary"]), cm.rgb(t["secondary"]), cm.rgb(t["accent"])
    dark = cm.shade(teal, -0.38)
    e = Emblem([(black, 0.013, 0.014), (cm.WHITE, 0.024, 0.0)])
    sp = Spine([(392, 946), (262, 832), (184, 660), (196, 470), (296, 310), (456, 222), (636, 232), (772, 326),
                (842, 452), (858, 580), (826, 668)])
    cuts = [0.0, 0.168, 0.322, 0.468, 0.604, 0.730, 0.842, 1.0]
    widths = [252, 228, 206, 186, 168, 152, 138, 150]
    gap = 0.005
    plates, ridges, bellies = [], [], []
    for i in range(6):
        t0, t1 = cuts[i] + gap, cuts[i + 1] - gap
        plates.append(sp.plate(t0, t1, widths[i], widths[i + 1], bulge=0.10, r=20))
        # armour: a pale ridge along the outside of the curve, a shadow along the inside
        ridges.append(sp.plate(t0 + 0.013, t1 - 0.013, widths[i], widths[i + 1], lo=-0.84, hi=-0.50, bulge=0.10, r=9))
        bellies.append(sp.plate(t0, t1, widths[i], widths[i + 1], lo=0.50, hi=1.0, bulge=0.10, r=4))
    # telson: the venom bulb (a last, swollen plate) and the hooked sting
    b0, b1 = cuts[6] + gap, 0.985
    plates.append(sp.plate(b0, b1, 132, 78, bulge=0.42, n=9, r=26))
    ridges.append(sp.plate(b0 + 0.02, b1 - 0.035, 132, 78, lo=-0.74, hi=-0.40, bulge=0.42, n=9, r=9))
    bellies.append(sp.plate(b0, b1, 132, 78, lo=0.46, hi=1.0, bulge=0.42, n=9, r=4))
    end, d = sp.at(0.97)
    sting = tongue(end[0], end[0] + np.array([-300.0, 125.0]), 156, bow=-0.58, belly=0.10)
    # Broad carapace, swept legs and an open pincer anchor the arched tail.
    for x in (365, 495, 625):
        e.add(dark, [vec.pts((x, 937), (x + 56, 951), (x + 10, 1060),
                             (x - 98, 1090), (x - 32, 1024))])
    e.add(teal, [vec.blob([(289, 856), (403, 833), (584, 846), (714, 880),
                           (755, 931), (699, 993), (522, 1012), (350, 976)], k=0.34)])
    e.add(sand, [tongue((374, 878), (651, 897), 42, bow=-0.12)], sil=False)
    e.add(teal, [vec.blob([(675, 913), (775, 866), (824, 788), (923, 744), (1042, 753, "c"),
                           (936, 799), (899, 863, "c"), (991, 862), (1065, 828, "c"),
                           (1014, 917), (893, 947), (814, 927), (733, 978)], k=0.30)])
    e.add(black, [sting])
    e.add(sand, [tongue(end[0] + (-4, 18), end[0] + np.array([-240.0, 112.0]), 79, bow=-0.54, belly=0.0)], sil=False)
    e.add(teal, plates, name="tail")
    e.add(dark, bellies, sil=False, clip="tail")
    e.add(sand, ridges, sil=False, clip="tail")
    return e


def emblem_gargoyles(t) -> Emblem:
    """A horned stone face glaring out between spread bat wings."""
    purple, grey, pale = cm.rgb(t["primary"]), cm.rgb(t["secondary"]), cm.rgb(t["accent"])
    ink = cm.shade(purple, -0.74)
    lit = cm.mix(grey, pale, 0.55)
    shadow = cm.mix(grey, ink, 0.42)
    e = Emblem([(ink, 0.012, 0.010), (pale, 0.024, 0.0)])

    def F(p):  # the face is drawn at 1000-unit scale, then enlarged a touch
        return vec.scale(np.asarray(p, np.float64), 1.16, about=(500, 470))

    # wings: arm up to the wrist claw, three fingers, scalloped trailing edge
    wing = np.concatenate([
        [(600, 400)], vec.quadratic((600, 400), (690, 290), (806, 120), 14), [(852, 206)],
        vec.quadratic((852, 206), (944, 280), (990, 428), 14),
        vec.quadratic((990, 428), (908, 468), (890, 612), 12),
        vec.quadratic((890, 612), (812, 612), (776, 708), 12),
        vec.quadratic((776, 708), (706, 670), (650, 724), 12), [(600, 650)],
    ])
    e.add(purple, both(wing), name="wings")
    panel = np.concatenate([[(806, 150)], vec.quadratic((806, 150), (870, 420), (890, 612), 12),
                            vec.quadratic((890, 612), (812, 612), (776, 708), 12),
                            vec.quadratic((776, 708), (800, 430), (806, 150), 12)])
    e.add(cm.shade(purple, -0.26), both(panel), sil=False, clip="wings")
    bones = []
    for tip in ((990, 428), (890, 612), (776, 708)):
        bones.append((vec.quadratic((806, 150), ((806 + tip[0]) / 2 + 26, (150 + tip[1]) / 2 - 18), tip, 12), 14, False))
    bones.append((vec.quadratic((610, 424), (700, 312), (806, 150), 12), 24, False))
    e.add(ink, strokes=bones + [(flip(p), w, c) for p, w, c in bones], sil=False, clip="wings")

    # ears and horns
    ear = F(tongue((624, 398), (716, 318), 112, bow=0.10, belly=0.20))
    e.add(grey, both(ear), name="ears")
    e.add(purple, both(F(tongue((634, 396), (700, 336), 56, bow=0.10, belly=0.20))), sil=False, clip="ears")
    horn = F(tongue((566, 290), (692, 78), 112, bow=0.30, belly=0.10))
    e.add(pale, both(horn), name="horns")
    e.add(cm.mix(pale, shadow, 0.55), both(horn), holes=both(vec.shift(horn, -17, 4)), sil=False)

    # face: chiselled planes
    face = F(vec.blob(sym_spec([
        (500, 250), (560, 252), (620, 292), (644, 352), (654, 424), (636, 506), (606, 592), (566, 676),
        (500, 734, "c"),
    ]), k=0.32))
    e.add(grey, [face], name="face")
    e.add(lit, [F(sym(np.array([(500, 262), (556, 264), (604, 296), (560, 318), (500, 330)])))] +
          both(F(vec.pts((562, 462), (644, 430), (632, 502), (584, 522)))), sil=False, clip="face")
    e.add(shadow, both(F(vec.pts((584, 528), (632, 508), (606, 592), (568, 664), (556, 590)))), sil=False, clip="face")
    e.add(shadow, [F(sym(np.array([(500, 342), (562, 318), (644, 318), (648, 364), (562, 394), (500, 412)])))],
          sil=False, clip="face")  # brow ridge
    e.add(ink, both(F(vec.pts((512, 410), (640, 366), (644, 422), (562, 456)))), sil=False, clip="face")  # sockets
    e.add(pale, both(F(vec.pts((540, 420), (626, 390), (630, 414), (562, 442)))), sil=False)  # glowing eyes
    e.add(ink, [F(sym(np.array([(500, 488), (536, 542), (500, 556)])))], sil=False)
    mouth = F(sym(np.array([(500, 614), (574, 596), (554, 668), (500, 688)])))
    e.add(ink, [mouth], sil=False)
    fangs = [vec.pts((522, 607), (550, 600), (538, 652)), vec.pts((510, 684), (530, 679), (518, 646))]
    e.add(pale, [F(f) for f in fangs] + [F(flip(f)) for f in fangs], sil=False)
    return e


EMBLEMS = {
    "sasquatch": emblem_sasquatch, "volcanoes": emblem_volcanoes, "icebreakers": emblem_icebreakers,
    "hellhounds": emblem_hellhounds, "twisters": emblem_twisters, "amps": emblem_amps,
    "scorpions": emblem_scorpions, "gargoyles": emblem_gargoyles,
}


def render_team(team: dict, size: int = SIZE, ss: int = SS) -> np.ndarray:
    return render(EMBLEMS[team["id"]](team), size=size, ss=ss)


def wanted_teams() -> list[dict]:
    """All teams, or just those named in FURY2D_TEAMS (set by --team)."""
    teams = cm.load_teams()
    only = [s for s in os.environ.get("FURY2D_TEAMS", "").split(",") if s]
    return [t for t in teams if not only or t["id"] in only]


# =========================================================================== previews
def _thumb(img: Image.Image, px: int) -> Image.Image:
    return img.resize((px, px), Image.LANCZOS, reducing_gap=3.0)


def team_preview(img: Image.Image, team: dict) -> Image.Image:
    """One emblem on its helmet colour, on dark and on light, plus the small sizes."""
    helmet = tuple(int(v * 255) for v in cm.rgb(team["helmet"]))
    big = [cm.on_bg(_thumb(img, 440), bg) for bg in (helmet, (20, 21, 26), (238, 238, 234))]
    small = []
    for bg in (helmet, (20, 21, 26), (238, 238, 234)):
        strip = Image.new("RGB", (440, 140), bg)
        x = 14
        for px in (128, 96, 64, 48, 32):
            strip.paste(cm.on_bg(_thumb(img, px), bg), (x, (140 - px) // 2))
            x += px + 14
        small.append(strip)
    return cm.vstack([cm.hstack(big, gap=8), cm.hstack(small, gap=8)], gap=0)


def contact_sheet(images: dict) -> Image.Image:
    """All emblems at 256 px and 64 px, on a dark and on a light background (4 x 2 each)."""
    ids = list(images)
    pad, big, small, cols = 10, 256, 64, 4
    cw, chh = big + pad, big + 8 + small + pad
    rows = (len(ids) + cols - 1) // cols
    w, band_h = pad + cw * cols, pad + chh * rows
    sheet = Image.new("RGB", (w, band_h * 2), (0, 0, 0))
    for k, bg in enumerate(((22, 23, 29), (236, 236, 232))):
        band = Image.new("RGB", (w, band_h), bg)
        for i, tid in enumerate(ids):
            x, y = pad + (i % cols) * cw, pad + (i // cols) * chh
            band.paste(cm.on_bg(_thumb(images[tid], big), bg), (x, y))
            band.paste(cm.on_bg(_thumb(images[tid], small), bg), (x + (big - small) // 2, y + big + 8))
        sheet.paste(band, (0, k * band_h))
    return sheet


def build() -> list[str]:
    cm.ensure_dirs()
    files, images = [], {}
    for team in wanted_teams():
        arr = render_team(team)
        fn = f"T_Logo_{team['id']}.png"
        cm.save_png(arr, fn)
        files.append(fn)
        img = Image.fromarray(arr, "RGBA")
        images[team["id"]] = img
        cm.save_preview(team_preview(img, team), fn)
    # the contact sheet always shows all eight (reload any that were not rebuilt this run)
    allimgs = {}
    for team in cm.load_teams():
        p = cm.OUT / f"T_Logo_{team['id']}.png"
        if team["id"] in images:
            allimgs[team["id"]] = images[team["id"]]
        elif p.exists():
            allimgs[team["id"]] = Image.open(p).convert("RGBA")
    if allimgs:
        cm.save_preview(contact_sheet(allimgs), "T_Logos_sheet.png")
    return files
