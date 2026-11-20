#!/usr/bin/env python3
"""Downsize / recompress Art/export/textures/*.png for the web port.

    python web/tools/convert_textures.py [--out web/public/assets/textures]

Needs Pillow + numpy (web/tools/setup_venv.sh makes a venv with them). Writes the runtime textures
into textures/ and the ad strip used by export_gltf.py into $FURY_SCRATCH (default /private/tmp/fury_web).

Colour textures (field, end zones, logos, title, sky, ads, icons) are sRGB. Masks and normal maps
(numbers, field_lines, *_n, *_m) are linear data: load them with colorSpace = NoColorSpace.
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(REPO, "Art", "export", "textures")
SCRATCH = os.environ.get("FURY_SCRATCH", "/private/tmp/fury_web")
TEAMS = ["sasquatch", "volcanoes", "icebreakers", "hellhounds", "twisters", "amps", "scorpions", "gargoyles"]

Image.MAX_IMAGE_PIXELS = None
written = []


def src(name):
    return Image.open(os.path.join(SRC, name + ".png"))


def resized(img, size):
    return img if img.size == tuple(size) else img.resize(size, Image.LANCZOS)


def save(img, out, name, **opts):
    path = os.path.join(out, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ext = os.path.splitext(name)[1].lower()
    if ext == ".webp":
        img.save(path, "WEBP", method=6, **opts)
    elif ext == ".png":
        img.save(path, "PNG", optimize=True)
    elif ext in (".jpg", ".jpeg"):
        img.convert("RGB").save(path, "JPEG", optimize=True, progressive=True, **opts)
    written.append((name, img.size, os.path.getsize(path)))
    print("  %-28s %5dx%-5d %8.1f KB" % (name, img.size[0], img.size[1], os.path.getsize(path) / 1024))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "web", "public", "assets", "textures"))
    out = os.path.abspath(ap.parse_args().out)
    os.makedirs(SCRATCH, exist_ok=True)

    # Field: 128 m x 64 m, 8192x4096 -> 4096x2048 (3.1 cm per texel). Paint mask for roughness, same mapping.
    save(resized(src("T_Field").convert("RGB"), (4096, 2048)), out, "field.webp", quality=88)
    save(resized(src("T_FieldLines").convert("L"), (4096, 2048)), out, "field_lines.png")
    for team in TEAMS:
        save(resized(src("T_EndZone_" + team).convert("RGB"), (2048, 512)), out, "endzone_%s.webp" % team, quality=86)
        save(resized(src("T_Logo_" + team).convert("RGBA"), (512, 512)), out, "logo_%s.webp" % team, quality=90, alpha_quality=100)
    save(src("T_Title").convert("RGBA"), out, "title.webp", quality=90, alpha_quality=100)
    save(src("T_TitleSmall").convert("RGBA"), out, "title_small.webp", quality=90, alpha_quality=100)
    # Numbers: 10x10 sheet, R = fill, G = outline. Keep it lossless; drop B (always 0) and A (always 255).
    numbers = src("T_Numbers")
    rgb = np.asarray(numbers.convert("RGB")).copy()
    rgb[..., 2] = 0
    save(resized(Image.fromarray(rgb, "RGB"), (2048, 2048)), out, "numbers.png")
    ads = resized(src("T_Ads").convert("RGB"), (4096, 256))
    save(ads, out, "ads.webp", quality=90)
    ads.save(os.path.join(SCRATCH, "ads_gltf.jpg"), "JPEG", quality=90, optimize=True)
    save(src("T_NightSky").convert("RGB"), out, "night_sky.webp", quality=95)
    for n in range(1, 5):
        save(src("T_Down_%d" % n).convert("RGB"), out, "down_%d.png" % n)
    for icon in ("Arrow", "Ball", "Bolt", "Cpu", "Crown", "Flame", "Gamepad", "Keyboard", "Shield", "Star"):
        save(src("T_Icon_" + icon).convert("RGBA"), out, "icons/%s.png" % icon.lower())
    # Optional detail maps (tiling), 512 px: the game uses them for grass, cloth, leather and concrete.
    for name, mode in (("T_Grass_N", "RGB"), ("T_Grass_M", "L"), ("T_Fabric_N", "RGB"), ("T_Leather_N", "RGB"),
                       ("T_Concrete_N", "RGB"), ("T_Concrete_M", "L")):
        save(resized(src(name).convert(mode), (512, 512)), out, "detail/%s.webp" % name[2:].lower(), quality=90)
    total = sum(s for _, _, s in written)
    print("textures: %d files, %.2f MB" % (len(written), total / 1048576))
    with open(os.path.join(SCRATCH, "textures_written.json"), "w") as handle:
        json.dump(written, handle, indent=1)


if __name__ == "__main__":
    main()
