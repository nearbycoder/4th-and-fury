"""Shared paths, colours, fonts and image I/O for the 4th & Fury 2D art scripts."""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / "Art"
OUT = ART / "export" / "textures"
PREV = ART / "previews" / "2d"
SCRATCH = ART / "_scratch" / "2d"
GAME_FONTS = ROOT / "FourthAndFury" / "Content" / "Fonts"
ART_FONTS = ART / "fonts"

PREVIEW_MAX = 1400  # longest side of any preview image


def ensure_dirs() -> None:
    for d in (OUT, PREV, SCRATCH, ART_FONTS):
        d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- fonts
# Game UI fonts (already in the Unreal project, SIL OFL).
_GAME = {
    "anton": "Anton-Regular.ttf",
    "barlow-medium": "BarlowCondensed-Medium.ttf",
    "barlow-semibold": "BarlowCondensed-SemiBold.ttf",
    "barlow-bold": "BarlowCondensed-Bold.ttf",
    "barlow-extrabold": "BarlowCondensed-ExtraBold.ttf",
    "barlow-black": "BarlowCondensed-Black.ttf",
    "barlow-bolditalic": "BarlowCondensed-BoldItalic.ttf",
    "barlow-extrabolditalic": "BarlowCondensed-ExtraBoldItalic.ttf",
    "barlow-blackitalic": "BarlowCondensed-BlackItalic.ttf",
    "graduate": "Graduate-Regular.ttf",
}

# Extra SIL OFL display fonts fetched from google/fonts into Art/fonts/<Family>/.
# key -> (local family folder, google/fonts "ofl/<dir>", file name)
_EXTRA = {
    "kanit-blackitalic": ("Kanit", "kanit", "Kanit-BlackItalic.ttf"),
    "bowlby": ("BowlbyOne", "bowlbyone", "BowlbyOne-Regular.ttf"),
    "alfaslab": ("AlfaSlabOne", "alfaslabone", "AlfaSlabOne-Regular.ttf"),
    "blackops": ("BlackOpsOne", "blackopsone", "BlackOpsOne-Regular.ttf"),
    "germania": ("GermaniaOne", "germaniaone", "GermaniaOne-Regular.ttf"),
    "russo": ("RussoOne", "russoone", "RussoOne-Regular.ttf"),
    "bangers": ("Bangers", "bangers", "Bangers-Regular.ttf"),
    "pacifico": ("Pacifico", "pacifico", "Pacifico-Regular.ttf"),
    "dmserif": ("DMSerifDisplay", "dmserifdisplay", "DMSerifDisplay-Regular.ttf"),
    "fugaz": ("FugazOne", "fugazone", "FugazOne-Regular.ttf"),
    "saira-xcond": ("SairaExtraCondensed", "sairaextracondensed", "SairaExtraCondensed-Black.ttf"),
    "squada": ("SquadaOne", "squadaone", "SquadaOne-Regular.ttf"),
}
_FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/{dir}/{file}"


def font_path(key: str) -> Path:
    """Resolve a font key to a .ttf path (game fonts first, then Art/fonts)."""
    if key in _GAME:
        p = GAME_FONTS / _GAME[key]
        if not p.exists():
            raise FileNotFoundError(f"game font missing: {p}")
        return p
    if key in _EXTRA:
        fam, _, fname = _EXTRA[key]
        p = ART_FONTS / fam / fname
        if not p.exists():
            raise FileNotFoundError(
                f"font missing: {p}\n  run: uv run Art/2d/make_textures.py --fetch-fonts"
            )
        return p
    raise KeyError(f"unknown font key {key!r}")


def fetch_fonts(verbose: bool = True) -> None:
    """Download any missing extra OFL fonts (and their OFL.txt) into Art/fonts/<Family>/."""
    lock_path = ART_FONTS / "fonts.sha256.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    changed = False
    for fam, gdir, fname in sorted(_EXTRA.values()):
        dest = ART_FONTS / fam
        dest.mkdir(parents=True, exist_ok=True)
        for name in (fname, "OFL.txt"):
            target = dest / name
            rel = f"{fam}/{name}"
            if not target.exists():
                url = _FONT_URL.format(dir=gdir, file=name)
                if verbose:
                    print(f"  fetch {url}")
                try:
                    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 (fixed https host)
                        data = r.read()
                except OSError as exc:
                    raise RuntimeError(f"could not download {url} ({exc}); {target} is needed to build the art") from exc
                digest = hashlib.sha256(data).hexdigest()
                if rel in lock and lock[rel] != digest:
                    raise RuntimeError(f"checksum mismatch for {rel}: upstream file changed")
                target.write_bytes(data)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if lock.get(rel) != digest:
                if rel in lock:
                    raise RuntimeError(f"checksum mismatch for {rel}")
                lock[rel] = digest
                changed = True
    if changed:
        lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    if verbose:
        print(f"  fonts ok ({len(_EXTRA)} extra faces in {ART_FONTS})")


# --------------------------------------------------------------------------- teams / colour
def load_teams() -> list[dict]:
    return json.loads((ART / "teams.json").read_text())["teams"]


def rgb(hexstr: str) -> np.ndarray:
    """'#RRGGBB' -> float32 sRGB triple in 0..1."""
    h = hexstr.lstrip("#")
    return np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255.0


def mix(a, b, t: float) -> np.ndarray:
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    return a + (b - a) * np.float32(t)


def shade(c, k: float) -> np.ndarray:
    """k<0 darkens toward black, k>0 lightens toward white."""
    c = np.asarray(c, np.float32)
    return mix(c, (0, 0, 0), -k) if k < 0 else mix(c, (1, 1, 1), k)


def luma(c) -> float:
    c = np.asarray(c, np.float32)
    return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])


WHITE = np.array([1, 1, 1], np.float32)
BLACK = np.array([0, 0, 0], np.float32)


# --------------------------------------------------------------------------- image I/O
def to_u8(a: np.ndarray) -> np.ndarray:
    """Float 0..1 -> uint8 with round-half-up (so 0.5 -> 128)."""
    return np.clip(np.floor(a * 255.0 + 0.5), 0, 255).astype(np.uint8)


def as_image(a) -> Image.Image:
    if isinstance(a, Image.Image):
        return a
    a = np.asarray(a)
    if a.dtype != np.uint8:
        a = to_u8(a)
    if a.ndim == 2:
        return Image.fromarray(a, "L")
    return Image.fromarray(a, {3: "RGB", 4: "RGBA"}[a.shape[2]])


def save_png(a, name: str, folder: Path | None = None) -> Path:
    """Write a texture PNG. No gamma/ICC chunks are written, so masks stay linear."""
    folder = OUT if folder is None else folder
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    as_image(a).save(path, format="PNG", compress_level=6)
    return path


def fit_size(w: int, h: int, max_side: int = PREVIEW_MAX) -> tuple[int, int]:
    s = min(1.0, max_side / max(w, h))
    return max(1, round(w * s)), max(1, round(h * s))


def downscale(img: Image.Image, max_side: int = PREVIEW_MAX) -> Image.Image:
    size = fit_size(*img.size, max_side)
    if size == img.size:
        return img
    return img.resize(size, Image.LANCZOS, reducing_gap=3.0)


def checker(w: int, h: int, cell: int = 16, a=(54, 56, 64), b=(74, 77, 87)) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((xx // cell + yy // cell) % 2).astype(bool)
    out = np.empty((h, w, 3), np.uint8)
    out[~m] = a
    out[m] = b
    return Image.fromarray(out, "RGB")


def on_bg(img: Image.Image, bg) -> Image.Image:
    """Composite an RGBA image over a solid colour or a checkerboard ('checker')."""
    img = img.convert("RGBA")
    if isinstance(bg, str) and bg == "checker":
        base = checker(*img.size).convert("RGBA")
    else:
        base = Image.new("RGBA", img.size, tuple(bg) + (255,))
    base.alpha_composite(img)
    return base.convert("RGB")


def save_preview(img, name: str, max_side: int = PREVIEW_MAX, bg=None) -> Path:
    """Downscaled preview into Art/previews/2d (RGBA is flattened onto `bg` if given)."""
    img = as_image(img)
    if bg is not None and img.mode == "RGBA":
        img = on_bg(img, bg)
    PREV.mkdir(parents=True, exist_ok=True)
    path = PREV / name
    downscale(img, max_side).save(path, format="PNG", compress_level=6)
    return path


def hstack(images, gap: int = 12, bg=(24, 24, 30)) -> Image.Image:
    h = max(i.height for i in images)
    w = sum(i.width for i in images) + gap * (len(images) + 1)
    out = Image.new("RGB", (w, h + 2 * gap), bg)
    x = gap
    for i in images:
        out.paste(i.convert("RGB"), (x, gap + (h - i.height) // 2))
        x += i.width + gap
    return out


def vstack(images, gap: int = 12, bg=(24, 24, 30)) -> Image.Image:
    w = max(i.width for i in images)
    h = sum(i.height for i in images) + gap * (len(images) + 1)
    out = Image.new("RGB", (w + 2 * gap, h), bg)
    y = gap
    for i in images:
        out.paste(i.convert("RGB"), (gap + (w - i.width) // 2, y))
        y += i.height + gap
    return out
