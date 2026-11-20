# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow>=10.1", "numpy>=1.26", "scipy>=1.11"]
# ///
"""Build every 2D texture for 4th & Fury.

    uv run --with pillow --with numpy Art/2d/make_textures.py            # everything
    uv run --with pillow --with numpy Art/2d/make_textures.py --only logos,icons
    uv run --with pillow --with numpy Art/2d/make_textures.py --only logos,endzones --team amps
    uv run --with pillow --with numpy Art/2d/make_textures.py --list

Extra package: scipy (distance transforms, FFT noise, k-d tree). It is declared in the
inline script metadata above, so the plain command already pulls it in; if you run the
file some other way, add `--with scipy`.

Output : Art/export/textures/*.png      Previews: Art/previews/2d/*.png
Fonts  : game fonts from FourthAndFury/Content/Fonts plus a few SIL OFL display faces in
         Art/fonts/<Family>/ (re-downloaded by --fetch-fonts if they are missing).
All randomness is seeded: re-running reproduces the same images.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# group name -> module in fury2d (each exposes build() -> list of written file names)
GROUPS = {
    "logos": "logos",
    "numbers": "numbers",
    "endzones": "endzones",
    "field": "field",
    "ads": "ads",
    "title": "title",
    "icons": "icons",
    "surfaces": "surfaces",
    "sky": "sky",
}


def run_group(name: str) -> tuple[str, list[str], float]:
    t0 = time.time()
    mod = importlib.import_module(f"fury2d.{GROUPS[name]}")
    files = mod.build()
    return name, files, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated groups to rebuild (default: all)")
    ap.add_argument("--list", action="store_true", help="list the groups and exit")
    ap.add_argument("--jobs", type=int, default=4, help="groups built in parallel (default 4; 1 = serial)")
    ap.add_argument("--fetch-fonts", action="store_true", help="download any missing OFL fonts and exit")
    ap.add_argument("--team", default="", help="comma-separated team ids: limit logos/endzones to these teams")
    args = ap.parse_args()
    if args.team:
        os.environ["FURY2D_TEAMS"] = args.team  # read by the per-team groups (also in worker processes)

    if args.list:
        import numpy, PIL, scipy

        print("groups:", ", ".join(GROUPS))
        print(f"python {sys.version.split()[0]}, pillow {PIL.__version__}, numpy {numpy.__version__}, scipy {scipy.__version__}")
        return 0

    from fury2d import common as cm

    cm.ensure_dirs()
    cm.fetch_fonts(verbose=args.fetch_fonts)
    if args.fetch_fonts:
        return 0

    wanted = [g.strip() for g in args.only.split(",") if g.strip()] or list(GROUPS)
    bad = [g for g in wanted if g not in GROUPS]
    if bad:
        ap.error(f"unknown group(s): {', '.join(bad)} (choose from {', '.join(GROUPS)})")

    t0 = time.time()
    results = []
    if args.jobs > 1 and len(wanted) > 1:
        with ProcessPoolExecutor(max_workers=min(args.jobs, len(wanted))) as ex:
            for name, files, dt in ex.map(run_group, wanted):
                results.append((name, files, dt))
                print(f"[{name:8s}] {len(files):2d} file(s) in {dt:6.1f}s", flush=True)
    else:
        for g in wanted:
            name, files, dt = run_group(g)
            results.append((name, files, dt))
            print(f"[{name:8s}] {len(files):2d} file(s) in {dt:6.1f}s", flush=True)
    n = sum(len(f) for _, f, _ in results)
    print(f"done: {n} texture(s) -> {cm.OUT}  ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
