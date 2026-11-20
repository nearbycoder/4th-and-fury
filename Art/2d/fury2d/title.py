"""The "4TH & FURY" title treatment.

T_Title.png      2048 x 1024 RGBA - two-line marquee logo for the main menu
T_TitleSmall.png 1024 x 256  RGBA - compact one-line version

Heavy forward-leaning letters; FURY burns from the inside (white-hot at the foot, through
yellow and orange to red), "4TH" is cold chrome and the ampersand is gold. Layered keyline /
neon ring / dark outline, a hard extruded shadow, flame licks off the top and a scatter of
embers. Lettering is Bowlby One (SIL OFL), sheared and rebuilt here.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from . import common as cm
from . import noise as nz
from . import vec
from .logos import tongue

SEED = 7700
FONT = "bowlby"

# palette
INK = cm.rgb("#12060A")
OUTER = cm.rgb("#07070D")
RING_HI = cm.rgb("#FFF3B0")
RING_MID = cm.rgb("#FFD84A")
RING_LO = cm.rgb("#FFB81C")
EXTRUDE = cm.rgb("#6E0C16")
RED_TOP = cm.rgb("#A30F1E")
RED_MID = cm.rgb("#E8281B")
RED_LOW = cm.rgb("#F2401C")
ORANGE_HI = cm.rgb("#FF8A14")
ORANGE_LO = cm.rgb("#FFA61F")
YELLOW_HI = cm.rgb("#FFD21A")
YELLOW_LO = cm.rgb("#FFF7B8")
CHROME = [cm.rgb("#FFFFFF"), cm.rgb("#DCE4F0"), cm.rgb("#8D9FBC"), cm.rgb("#E9EEF6")]
GOLD = [cm.rgb("#FFF6BE"), cm.rgb("#FFD21A"), cm.rgb("#FF9A14"), cm.rgb("#FFC233")]
BEVEL_SHADE = {"fire": cm.rgb("#5A0710"), "gold": cm.rgb("#A8500A"), "chrome": cm.rgb("#5C6C88")}


# --------------------------------------------------------------------------- one word
class Word:
    """A word in its own flat frame: the glyph mask plus (for 'fire') flame layers. All of
    its layers are later sheared / rotated / scaled onto the canvas with one transform."""

    def __init__(self, text: str, cap_px: float, tracking: float = 0.0, style: str = "fire", seed: int = 0,
                 head: float = 0.95):
        path = cm.font_path(FONT)
        probe = 400.0
        _, _, ph = vec.text_ink("H", path, probe)
        size = probe * cap_px / ph
        m, _, _ = vec.text_mask(text, path, size, tracking * size, pad=2)
        rows = np.flatnonzero(m.any(1))
        cols = np.flatnonzero(m.any(0))
        m = m[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
        self.text, self.style = text, style
        self.fire = style == "fire"
        self.h, self.w = m.shape
        self.head = int(self.h * head) if self.fire else 0  # room above the letters for flames
        self.side = int(self.h * 0.30)
        full = np.zeros((self.h + self.head, self.w + 2 * self.side), np.uint8)
        full[self.head :, self.side : self.side + self.w] = m
        self.mask = full
        self.shape = full.shape
        if self.fire:
            r = nz.rng(seed)
            self.inner_orange = self._flame_row(r, 0.36, (0.52, 0.90), 0.150)
            self.inner_yellow = self._flame_row(r, 0.14, (0.24, 0.56), 0.115)
            self.licks = self._licks(r)

    def _flame_row(self, r, base_frac, tip_range, pitch_frac) -> np.ndarray:
        """Flames inside the letters: a base band plus a row of tongues trailing to the left."""
        H, W = self.shape
        bottom = self.head + self.h
        base_y = bottom - base_frac * self.h
        polys = [vec.rect(0, base_y, W, bottom + 4)]
        pitch = pitch_frac * self.h
        x = -pitch
        while x < W + pitch:
            tip_h = r.uniform(*tip_range) * self.h
            width = pitch * r.uniform(1.5, 2.1)
            lean = -r.uniform(0.10, 0.34) * tip_h
            polys.append(tongue((x, base_y + 0.06 * self.h), (x + lean, bottom - tip_h), width,
                                bow=r.uniform(0.08, 0.22), belly=0.30))
            x += pitch * r.uniform(0.75, 1.25)
        return vec.raster((W, H), polys)

    def _licks(self, r):
        """Flames licking off the top edge of the letters (three nested layers)."""
        H, W = self.shape
        col = self.mask[self.head :].any(0)
        top_of = np.where(col, self.mask[self.head :].argmax(0) + self.head, -1)
        outer, mid, core = [], [], []
        pitch = 0.105 * self.h
        x = float(self.side)
        while x < self.side + self.w:
            xi = int(np.clip(x, 0, W - 1))
            if 0 <= top_of[xi] < self.head + 0.30 * self.h:  # only where a letter's top is close
                arch = 0.55 + 0.45 * math.sin(math.pi * (x - self.side) / self.w) ** 0.6
                hgt = r.uniform(0.34, 0.92) * self.head * arch
                width = pitch * r.uniform(1.7, 2.5)
                base = np.array([x, top_of[xi] + 0.10 * self.h])
                tip = np.array([x - r.uniform(0.25, 0.55) * hgt, top_of[xi] - hgt])
                bow = r.uniform(0.10, 0.26)
                outer.append(tongue(base, tip, width, bow=bow, belly=0.30))
                mid.append(tongue(base, base + (tip - base) * 0.66, width * 0.68, bow=bow, belly=0.28))
                core.append(tongue(base, base + (tip - base) * 0.36, width * 0.40, bow=bow, belly=0.25))
            x += pitch * r.uniform(0.7, 1.2)
        return [vec.raster((W, H), p) for p in (outer, mid, core)]


def place_word(word: Word, canvas_size, anchor, scale: float, shear: float, rot_deg: float) -> dict:
    """Affine-map a word's layers onto the canvas; `anchor` is where the left end of its
    baseline lands. Also returns per-pixel local coordinates for gradients that follow the lean."""
    W, H = canvas_size
    a = math.radians(rot_deg)
    ca, sa = math.cos(a), math.sin(a)
    bx, by = word.side, word.head + word.h
    A = np.array([[1.0, -shear, -bx + shear * by], [0.0, 1.0, -by]])  # shear about the baseline
    R = np.array([[ca, -sa], [sa, ca]]) * scale
    M = np.hstack([R @ A[:, :2], (R @ A[:, 2:3]) + np.array([[anchor[0]], [anchor[1]]])])
    out = {"mask": vec.f32(vec.affine_mask(word.mask, M, (W, H))), "style": word.style, "licks": None}
    if word.fire:
        out["orange"] = vec.f32(vec.affine_mask(word.inner_orange, M, (W, H)))
        out["yellow"] = vec.f32(vec.affine_mask(word.inner_yellow, M, (W, H)))
        out["licks"] = [vec.f32(vec.affine_mask(l, M, (W, H))) for l in word.licks]
    Minv = np.linalg.inv(np.vstack([M, [0, 0, 1]]))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    out["v"] = np.clip((Minv[1, 0] * xx + Minv[1, 1] * yy + Minv[1, 2] - word.head) / word.h, 0.0, 1.0)  # 0 cap .. 1 base
    out["u"] = (Minv[0, 0] * xx + Minv[0, 1] * yy + Minv[0, 2] - word.side) / word.w
    return out


def lay_out(words, canvas, anchor, scales, gaps, shear, rot, lifts=None) -> list[dict]:
    """Place words one after another along a (possibly rotated) baseline starting at `anchor`.
    scales[i] scales word i; gaps[i] is the space after it; lifts[i] raises it off the line."""
    a = math.radians(rot)
    ux, uy = math.cos(a), math.sin(a)
    x, y = anchor
    placed = []
    for i, word in enumerate(words):
        lift = lifts[i] if lifts else 0.0
        placed.append(place_word(word, canvas, (x + uy * lift, y - ux * lift), scales[i], shear, rot))
        adv = word.w * scales[i] + (gaps[i] if i < len(gaps) else 0.0)
        x, y = x + ux * adv, y + uy * adv
    return placed


def ramp(v: np.ndarray, stops) -> np.ndarray:
    """Piecewise-linear colour ramp; stops = [(position, rgb), ...]."""
    out = np.zeros(v.shape + (3,), np.float32)
    pos = [p for p, _ in stops]
    for ch in range(3):
        out[..., ch] = np.interp(v, pos, [float(col[ch]) for _, col in stops])
    return out


# --------------------------------------------------------------------------- composite
def compose(size, words, px: float, embers: int = 0, seed: int = SEED, rise: float = 1.0) -> np.ndarray:
    """Layer everything (back to front). `px` scales every outline width (1.0 = one pixel
    of the 2048-wide title at 1x)."""
    W, H = size
    c = vec.Canvas(W, H, ss=1)
    letters = np.zeros((H, W), np.float32)
    for w in words:
        np.maximum(letters, w["mask"], out=letters)

    key = vec.dilate(letters, 9 * px)
    ring = vec.dilate(key, 9 * px)
    outer = vec.dilate(ring, 15 * px)
    dx, dy = int(round(16 * px)), int(round(22 * px))
    steps = max(dx, dy)
    ext = outer.copy()
    for i in range(1, steps + 1):  # hard extruded shadow, down and to the right
        np.maximum(ext, vec.shift_mask(outer, int(round(dx * i / steps)), int(round(dy * i / steps))), out=ext)
    drop = vec.shift_mask(vec.dilate(ext, 5 * px), int(round(6 * px)), int(round(10 * px)))

    # 1. heat glow
    c.paint(np.clip(vec.blur(outer, 46 * px) * 1.25, 0, 1), cm.rgb("#FF5A12"), 0.42)
    # 2. flames off the tops of the burning letters
    lick_cols = [cm.rgb("#C3141C"), cm.rgb("#FF7A14"), cm.rgb("#FFD83A")]
    for w in words:
        if w["licks"] is not None:
            c.paint(vec.dilate(w["licks"][0], 6 * px), INK, 0.92)
            for m, col in zip(w["licks"], lick_cols):
                c.paint(m, col)
    # 3. embers drifting up and back off the fire (behind the lettering)
    if embers:
        r = nz.rng(seed + 5)
        hot = [w for w in words if w["licks"] is not None]
        ys, xs = np.nonzero(hot[0]["licks"][0] > 0.5)
        warm, bright = [], []
        for _ in range(embers):
            k = int(r.integers(0, len(xs)))
            x = xs[k] + r.normal(0, 80 * px) - r.uniform(0, 150 * px) * rise
            y = ys[k] - r.uniform(30, 210) * px * rise
            s = r.uniform(4.0, 11.0) * px
            p = vec.rotate(vec.pts((0, -s * 1.7), (s * 0.7, 0), (0, s * 1.7), (-s * 0.7, 0)), r.uniform(-50, -10)) + (x, y)
            (warm if r.random() < 0.55 else bright).append(p)
        for polys, col in ((warm, cm.rgb("#FFB31F")), (bright, cm.rgb("#FFF0A0"))):
            if polys:
                m = vec.f32(vec.raster((W, H), polys))
                c.paint(np.clip(vec.blur(m, 5 * px) * 1.6, 0, 1), cm.rgb("#FF6A14"), 0.55)
                c.paint(m, col)
    # 4. shadow, extrusion and the outline stack
    c.paint(drop, OUTER, 0.55)
    c.paint(ext, EXTRUDE)
    c.paint(ext * (1.0 - outer), cm.rgb("#3E060D"), 0.55)
    c.paint(outer, OUTER)
    ring_col = np.zeros((H, W, 3), np.float32)
    for w in words:  # each line's ring is lit from its own top edge
        grad = ramp(w["v"], [(0.0, RING_HI), (0.55, RING_MID), (1.0, RING_LO)])
        ring_col = np.where(w["near"][..., None], grad, ring_col)
    c.paint(ring, ring_col)
    c.paint(key, INK)
    # 5. the letters
    for w in words:
        m, v = w["mask"], w["v"]
        if w["style"] == "fire":
            c.paint(m, ramp(v, [(0.0, RED_TOP), (0.55, RED_MID), (1.0, RED_LOW)]))
            c.paint(m * w["orange"], ramp(v, [(0.0, ORANGE_HI), (1.0, ORANGE_LO)]))
            c.paint(m * w["yellow"], ramp(v, [(0.35, YELLOW_HI), (1.0, YELLOW_LO)]))
        elif w["style"] == "gold":
            c.paint(m, ramp(v, [(0.0, GOLD[0]), (0.44, GOLD[1]), (0.52, GOLD[2]), (1.0, GOLD[3])]))
        else:  # chrome: bright sky over a dark horizon
            wave = 0.50 + 0.035 * np.sin(w["u"] * 9.0)
            c.paint(m, np.where((v < wave)[..., None], ramp(v, [(0.0, CHROME[0]), (0.5, CHROME[1])]),
                                ramp(v, [(0.5, CHROME[2]), (1.0, CHROME[3])])))
        # bevel: light along the upper-left edge, shade along the lower-right
        ox, oy = int(round(4 * px)), int(round(5 * px))
        c.paint(np.clip(m - vec.shift_mask(m, -ox, -oy), 0, 1), BEVEL_SHADE[w["style"]], 0.50)
        c.paint(np.clip(m - vec.shift_mask(m, ox, oy), 0, 1), cm.WHITE, 0.80 if w["style"] == "fire" else 0.95)
    return c.buf


def assign_near(words) -> None:
    """Give every word a boolean map of the pixels it is the nearest lettering to."""
    if len(words) == 1:
        words[0]["near"] = np.ones(words[0]["mask"].shape, bool)
        return
    d = np.stack([ndi.distance_transform_edt(w["mask"] < 0.5) for w in words])
    best = np.argmin(d, axis=0)
    for i, w in enumerate(words):
        w["near"] = best == i


def finish(buf: np.ndarray, ss: int) -> np.ndarray:
    c = vec.Canvas(buf.shape[1] // ss, buf.shape[0] // ss, ss)
    c.buf = buf
    return c.result(bleed="edge")


# --------------------------------------------------------------------------- the two logos
def render_title(ss: int = 2) -> np.ndarray:
    """The two-line main-menu logo, 2048 x 1024."""
    W, H = 2048 * ss, 1024 * ss
    shear, rot = 0.21, -4.0
    fury = Word("FURY", 800, tracking=0.015, style="fire", seed=SEED + 1)
    fourth = Word("4TH", 520, tracking=0.02, style="chrome", seed=SEED + 2)
    amp = Word("&", 520, style="gold", seed=SEED + 3)
    words = lay_out([fury], (W, H), (232 * ss, 892 * ss), [0.478 * ss], [], shear, rot)
    words += lay_out([fourth, amp], (W, H), (384 * ss, 462 * ss), [0.474 * ss, 0.366 * ss], [50 * ss], shear, rot,
                     lifts=[0.0, 6 * ss])
    assign_near(words)
    return finish(compose((W, H), words, float(ss), embers=90), ss)


def render_small(ss: int = 4, width: int = 1024, height: int = 256) -> np.ndarray:
    """Compact one-line version."""
    W, H = width * ss, height * ss
    px = 0.50 * ss * (height / 256.0)
    shear = 0.20
    fourth = Word("4TH", 800, tracking=0.012, style="chrome", seed=SEED + 9)
    amp = Word("&", 800, style="gold", seed=SEED + 10)
    fury = Word("FURY", 800, tracking=0.012, style="fire", seed=SEED + 11, head=0.40)
    rel = [1.0, 0.76, 1.0]
    gap = 0.125 * fury.h  # between words, in the word's own units
    total = sum(w.w * r for w, r in zip((fourth, amp, fury), rel)) + 2 * gap + shear * fury.h
    k = min(0.86 * W / total, 0.50 * H / fury.h)
    x0 = (W - total * k) / 2.0 - 4 * px
    y0 = H * 0.5 + fury.h * k * 0.5 + 0.060 * H
    words = lay_out([fourth, amp, fury], (W, H), (x0, y0), [k * r for r in rel], [gap * k] * 2, shear, 0.0,
                    lifts=[0.0, 0.03 * fury.h * k, 0.0])
    assign_near(words)
    return finish(compose((W, H), words, px, embers=22, seed=SEED + 30, rise=0.42), ss)


def stadium_backdrop(size) -> Image.Image:
    """A dark blue-grey gradient standing in for a stadium shot (previews only)."""
    w, h = size
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    base = np.stack([0.05 + 0.05 * yy + 0 * xx, 0.07 + 0.10 * yy + 0 * xx, 0.12 + 0.10 * yy + 0 * xx], -1)
    base *= (1.0 - 0.35 * xx**2)[..., None]
    return Image.fromarray(cm.to_u8(np.clip(base, 0, 1)), "RGB").convert("RGBA")


def build() -> list[str]:
    cm.ensure_dirs()
    title = render_title()
    cm.save_png(title, "T_Title.png")
    small = render_small()
    cm.save_png(small, "T_TitleSmall.png")
    ti, si = Image.fromarray(title, "RGBA"), Image.fromarray(small, "RGBA")
    over = stadium_backdrop(ti.size)
    over.alpha_composite(ti)
    cm.save_preview(over.convert("RGB"), "T_Title.png")
    cm.save_preview(cm.hstack([cm.downscale(cm.on_bg(ti, "checker"), 690), cm.downscale(cm.on_bg(ti, (228, 228, 222)), 690)], gap=8),
                    "T_Title_backgrounds.png")
    cm.save_preview(cm.vstack([cm.on_bg(si, (16, 18, 26)), cm.on_bg(si, "checker"), cm.on_bg(si, (228, 228, 222))], gap=8),
                    "T_TitleSmall.png")
    return ["T_Title.png", "T_TitleSmall.png"]
