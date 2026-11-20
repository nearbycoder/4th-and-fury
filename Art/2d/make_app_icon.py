# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow>=10.1", "numpy>=1.26", "scipy>=1.11"]
# ///
"""Generate the app and project icons from the lettering used on the title screen."""
import base64
import io
import json

import numpy as np
from PIL import Image, ImageDraw

from fury2d import common as cm, title


def emblem():
    glyph = title.Word("F", 600, style="fire", seed=title.SEED + 1)
    words = title.lay_out([glyph], (1024, 1024), (164, 862), [0.92], [], 0.21, -4)
    title.assign_near(words)
    art = Image.fromarray(title.finish(title.compose((1024, 1024), words, 1.6, embers=0), 1))
    art = art.crop(art.getbbox())
    art.thumbnail((740, 745), Image.Resampling.LANCZOS)
    mask = Image.new("L", (1024, 1024))
    ImageDraw.Draw(mask).rounded_rectangle((52, 52, 971, 971), radius=207, fill=255)
    y, x = np.mgrid[0:1024, 0:1024]
    light = np.clip(1 - np.hypot((x - 295) / 1080, (y - 120) / 1050), 0, 1)
    rgb = np.asarray((26, 9, 15)) + light[:, :, None] * np.asarray((63, 26, 23))
    icon = Image.fromarray(rgb.astype(np.uint8)).convert("RGBA")
    icon.putalpha(mask)
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((55, 55, 969, 969), radius=205, outline=(132, 67, 51, 255), width=5)
    icon.alpha_composite(art, ((1024 - art.width) // 2, (1024 - art.height) // 2))
    return icon


def main():
    root = cm.ROOT
    icon = emblem()
    mac = root / "FourthAndFury/Build/Mac/Resources/Assets.xcassets"
    icons = mac / "AppIcon.appiconset"
    icons.mkdir(parents=True, exist_ok=True)
    info = {"author": "xcode", "version": 1}
    rows = []
    for pts in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            name = f"icon_{pts}x{pts}{'@2x' if scale == 2 else ''}.png"
            icon.resize((pts * scale, pts * scale), Image.Resampling.LANCZOS).save(icons / name)
            rows.append(dict(idiom="mac", size=f"{pts}x{pts}", scale=f"{scale}x", filename=name))
    (mac / "Contents.json").write_text(json.dumps({"info": info}, indent=2) + "\n")
    (icons / "Contents.json").write_text(json.dumps({"images": rows, "info": info}, indent=2) + "\n")
    win = root / "FourthAndFury/Build/Windows"
    win.mkdir(parents=True, exist_ok=True)
    icon.save(win / "Application.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    buffer = io.BytesIO()
    icon.resize((128, 128), Image.Resampling.LANCZOS).save(buffer, "PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    (root / "assets/icon.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><image width="128" height="128" href="data:image/png;base64,{encoded}"/></svg>\n')


if __name__ == "__main__":
    main()
