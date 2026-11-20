# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1"]
# ///
"""4th & Fury -- stadium PA announcer (VO_*.wav).

    uv run Audio/make_voice.py [name-filter ...]

Process the dry US stadium calls in Audio/takes through the arena PA.
See make_takes.py to regenerate the source performances.
"""
import sys

import numpy as np

from fury import catalog, measure
from fury.core import (compress, db2lin, echo, eq, fade, hp, limiter, lp, n_of, resample, reverb,
                       reverb_ir, saturate)
from fury.wavio import read_take, save

DEEPEN_SEMITONES = 0.4
TARGET_LUFS = -16.0
ECHO_DB = -14.0             # slap-back level
REVERB_DB = -18.0           # reverb level
PRESENCE_DB = 6.0           # horn "bite" around 3.2 kHz (consonants)


def trim(x, thresh_db=-45.0, lead=0.01, trail=0.03):
    """Cut leading/trailing silence (relative to the line's own peak)."""
    env = np.abs(x)
    idx = np.nonzero(env > np.max(env) * db2lin(thresh_db))[0]
    if len(idx) == 0:
        return x
    a = max(idx[0] - n_of(lead), 0)
    b = min(idx[-1] + n_of(trail), len(x))
    return fade(x[a:b], 0.004, 0.02)


def tighten(x, longest=0.16, floor_db=-42.0):
    """Shorten the pauses between sentences ("He's in! ... Touchdown!") so the delivery is punchy."""
    win = n_of(0.01)
    nb = len(x) // win
    level = np.sqrt(np.mean(x[: nb * win].reshape(nb, win) ** 2, axis=1))
    quiet = level < np.max(level) * db2lin(floor_db)
    out, i = [], 0
    while i < nb:
        j = i
        while j < nb and quiet[j] == quiet[i]:
            j += 1
        seg = x[i * win: j * win]
        if quiet[i] and 0 < i and j < nb and (j - i) * 0.01 > longest:
            keep = n_of(longest)
            seg = np.concatenate([fade(seg[: keep // 2], 0.0, 0.01), fade(seg[-(keep // 2):], 0.01, 0.0)])
        out.append(seg)
        i = j
    out.append(x[nb * win:])
    return np.concatenate(out)


_IR = None


def stadium_pa(x):
    """Dry speech -> stadium PA (mono)."""
    global _IR
    if _IR is None:
        _IR = reverb_ir(1.3, seed=91, pre_delay=0.04, lf_mult=1.0, hf_mult=0.35, build=0.03,
                        lowcut=220.0, highcut=4200.0, stereo=False)
    x = resample(x, 2.0 ** (DEEPEN_SEMITONES / 12.0))
    x = x / max(np.max(np.abs(x)), 1e-9)
    # horn loudspeakers: band-limited, nasal
    x = lp(hp(x, 250.0, 4), 5000.0, 4)
    x = eq(x, [("peak", 520.0, 1.0, -3.0), ("peak", 1800.0, 1.2, 5.0), ("peak", 3200.0, 2.0, PRESENCE_DB)])
    # the amplifier: levelled hard, pushed a little into clipping
    x = compress(x, thresh_db=-24.0, ratio=4.0, attack=0.004, release=0.09, knee_db=6.0, makeup_db=10.0)
    x = saturate(x / max(np.max(np.abs(x)), 1e-9) * 0.9, 4.0)
    x = lp(x, 5200.0, 2)
    speech_len = len(x)
    # the bowl: one clear slap off the far stand (and its faint repeat), then the wash
    x = echo(x, 0.21, gain_db=ECHO_DB, repeats=2, feedback_db=-8.0, damp=2800.0)
    x = reverb(x, _IR, wet_db=REVERB_DB)
    # keep at most ~1.1 s of tail after the last word, and end it gently
    n = min(len(x), speech_len + n_of(1.1))
    x = fade(x[:n], 0.002, 0.3)
    return limiter(x / max(np.max(np.abs(x)), 1e-9), ceiling_db=-1.5)


def make(name):
    dry = tighten(trim(read_take(name)))
    y = stadium_pa(dry)
    for _ in range(3):          # same loudness for every line: gain to target, catch the peaks, repeat
        y = limiter(y * db2lin(TARGET_LUFS - measure.lufs_integrated(y)), ceiling_db=-1.6)
    save(name, y, lufs=TARGET_LUFS, fade_in=0.002, fade_out=0.05, dc_hz=60.0)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    print("Stadium announcer")
    for name in catalog.VO_LINES:
        if args and not any(a.lower() in name.lower() for a in args):
            continue
        make(name)


if __name__ == "__main__":
    main()
