# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1", "matplotlib"]
# ///
"""QC helper: render log-frequency spectrograms (plus level envelope) of WAV files to a PNG sheet.

    uv run Audio/qc/spectro.py -o sheet.png [--cols 4] [--loop] FILE.wav ...

--loop draws each file twice in a row so the loop seam sits in the middle of the picture.
Not needed to build the audio; it is how the sounds were inspected without ears.
"""
import argparse
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fury.wavio import read_wav  # noqa: E402


def panel(ax, path, a):
    x, sr = read_wav(path)
    m = x if x.ndim == 1 else x.mean(axis=1)
    if a.loop:
        m = np.concatenate([m, m])
    full = len(m) / sr
    t0 = a.t0 or 0.0
    t1 = a.t1 or full
    seg = m[int(t0 * sr):int(t1 * sr)]
    dur = len(seg) / sr
    nper = a.nper or (512 if dur < 0.6 else (1024 if dur < 4 else 2048))
    nper = min(nper, len(seg))
    hop = max(nper // 8, int(len(seg) / 1200), 1)
    f, t, s = signal.spectrogram(seg, sr, window="hann", nperseg=nper, noverlap=nper - min(hop, nper - 1),
                                 nfft=max(nper, 2048), mode="magnitude")
    d = 20 * np.log10(np.maximum(s, 1e-9))
    top = d.max()
    keep = (f >= a.fmin) & (f <= a.fmax)
    ax.pcolormesh(t + t0, f[keep], d[keep], vmin=top - a.dyn, vmax=top, cmap="magma", shading="auto")
    if not a.linear:
        ax.set_yscale("log")
        ticks = [v for v in (50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000) if a.fmin <= v <= a.fmax]
        ax.set_yticks(ticks)
        ax.set_yticklabels([f"{v // 1000}k" if v >= 1000 else str(v) for v in ticks], fontsize=6)
    else:
        ax.tick_params(axis="y", labelsize=6)
    ax.set_ylim(a.fmin, a.fmax)
    ax.tick_params(axis="x", labelsize=6)
    if a.env:
        k = max(int(sr * 0.005), 1)
        env = np.sqrt(np.convolve(seg ** 2, np.ones(k) / k, mode="same"))
        ax2 = ax.twinx()
        ax2.plot(np.arange(len(seg)) / sr + t0, 20 * np.log10(np.maximum(env, 1e-6)), color="#7fffd4", lw=0.6, alpha=0.9)
        ax2.set_ylim(-90, 0)
        ax2.tick_params(axis="y", labelsize=5, colors="#2a9d8f")
    if a.loop:
        ax.axvline(full / 2, color="white", lw=0.5, ls=":")
    pk = 20 * np.log10(max(np.max(np.abs(x)), 1e-9))
    ax.set_title(f"{os.path.basename(path)[:-4]}  {len(x) / sr:.2f}s  pk {pk:.1f}", fontsize=7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--loop", action="store_true", help="draw each file twice so the seam is mid-picture")
    ap.add_argument("--env", action="store_true", help="overlay the level envelope (dBFS, right axis)")
    ap.add_argument("--linear", action="store_true", help="linear frequency axis")
    ap.add_argument("--height", type=float, default=2.3)
    ap.add_argument("--width", type=float, default=4.2)
    ap.add_argument("--t0", type=float, default=None)
    ap.add_argument("--t1", type=float, default=None)
    ap.add_argument("--fmin", type=float, default=40.0)
    ap.add_argument("--fmax", type=float, default=24000.0)
    ap.add_argument("--dyn", type=float, default=80.0)
    ap.add_argument("--nper", type=int, default=None)
    a = ap.parse_args()
    cols = min(a.cols, len(a.files))
    rows = int(np.ceil(len(a.files) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(a.width * cols, a.height * rows), squeeze=False)
    for ax in axes.flat:
        ax.axis("off")
    for ax, path in zip(axes.flat, a.files):
        ax.axis("on")
        panel(ax, path, a)
    fig.tight_layout()
    fig.savefig(a.out, dpi=110)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
