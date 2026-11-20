# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1"]
# ///
"""QC helper (macOS only): a machine "ear".

Runs Apple's built-in sound classifier (SoundAnalysis framework, 303 everyday-sound labels such
as crowd, cheering, whistling, fireworks, air_horn, thump_thud, speech, music) over the generated
WAVs and prints what it thinks each one is. Short one-shots are padded with silence so the
classifier's analysis window has something to chew on; loops are tiled.

    uv run Audio/qc/listen.py [--window 1.0] [--top 6] [-v] FILE.wav ...

Needs the Swift toolchain (swiftc) to build ear.swift once. Not needed to build the audio.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from fury.wavio import read_wav, write_wav  # noqa: E402
from fury.core import SR  # noqa: E402


def ear_binary():
    src = os.path.join(HERE, "ear.swift")
    out = os.path.join(HERE, ".build", "ear")
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["swiftc", "-O", src, "-o", out], check=True, stderr=subprocess.DEVNULL)
    return out


def prepare(path, window, tmpdir, loop):
    x, sr = read_wav(path)
    assert sr == SR
    need = int((window + 0.35) * SR)
    if loop:
        reps = max(int(np.ceil(need / len(x))), 2)
        y = np.concatenate([x] * reps)
    elif len(x) < need:
        lead = int(0.15 * SR)
        y = np.zeros((need,) + x.shape[1:])
        y[lead:lead + len(x)] = x
    else:
        return path
    out = os.path.join(tmpdir, os.path.basename(path))
    write_wav(out, y, dither=False)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--window", type=float, default=None,
                    help="analysis window in seconds (default: the shortest of 1, 1.5, 2, 3 that holds the whole one-shot; "
                         "a window that cuts a sound in half can change what it is taken for)")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--loop", action="store_true", help="tile the files instead of padding them")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    ear = ear_binary()
    groups = {}
    for f in a.files:
        w = a.window
        if w is None:
            x, sr = read_wav(f)
            w = 3.0 if a.loop else next((c for c in (1.0, 1.5, 2.0, 3.0) if c >= len(x) / sr + 0.15), 3.0)
        groups.setdefault(w, []).append(f)
    with tempfile.TemporaryDirectory() as tmp:
        for w, files in sorted(groups.items()):
            sub = os.path.join(tmp, str(w))
            os.makedirs(sub)
            prepared = [prepare(f, w, sub, a.loop) for f in files]
            cmd = [ear, "-n", str(a.top), "-w", str(w)] + (["-v"] if a.v else []) + prepared
            subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
