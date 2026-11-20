"""WAV input/output and the common "finish and save" step used by every generator."""
import os
import wave

import numpy as np

from . import measure
from .core import SR, biquad, circ_sos, db2lin, fade, n_of, rng_for
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.environ.get("FURY_AUDIO_OUT", os.path.join(REPO, "FourthAndFury", "AudioSource"))

PEAK_CEILING_DB = -1.0
_MARGIN_DB = 0.08          # normalise a hair under the ceiling so dither can never cross it

_log = []                  # (name, seconds, channels) of everything saved in this process


def read_wav(path):
    """Read a 16-bit PCM WAV as float64 in [-1, 1). Returns (samples, sample_rate)."""
    with wave.open(path, "rb") as w:
        ch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise ValueError(f"{path}: expected 16-bit PCM, got {width * 8}-bit")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch)
    return x, sr


def read_take(name):
    samples, rate = read_wav(os.path.join(REPO, "Audio", "takes", name + ".wav"))
    return signal.resample_poly(samples, SR, rate)


def write_wav(path, x, seed_name="", dither=True, zero_edges=0):
    """Quantise to 16-bit PCM with TPDF dither (seeded -> reproducible) and write.
    zero_edges: number of samples at head and tail kept free of dither (true digital zero)."""
    x = np.asarray(x, dtype=np.float64)
    y = x * 32767.0
    if dither:
        rng = rng_for("dither:" + seed_name)
        d = rng.random(y.shape) - rng.random(y.shape)          # triangular, +-1 LSB
        if zero_edges:
            g = np.ones(y.shape[0])
            k = min(zero_edges, y.shape[0] // 2)
            g[:k] = 0.0
            g[-k:] = 0.0
            d = d * (g if y.ndim == 1 else g[:, None])
        y = y + d
    q = np.clip(np.round(y), -32767, 32767).astype("<i2")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1 if q.ndim == 1 else q.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(q.tobytes())


def _dc_block(x, loop, hz):
    sos = np.vstack([biquad("hp", hz, 0.7071)])
    if loop:
        return circ_sos(x, sos)
    return signal.sosfilt(sos, x, axis=0)


def finish(x, loop=False, peak_db=PEAK_CEILING_DB, loud=None, lufs=None, rms_db=None,
           fade_in=0.0003, fade_out=0.008, dc_hz=22.0, duration=None):
    """Common last step: DC block, level, edge fades.

    Level targets (first one given wins):
      lufs    integrated loudness (BS.1770)           -- beds, music, voice
      loud    loudest 100 ms K-weighted window        -- one-shots, so they balance by ear not by peak
      rms_db  plain RMS
    The peak ceiling always wins: if the target would push the true peak above peak_db the
    sound is scaled down to fit instead.
    """
    x = np.asarray(x, dtype=np.float64)
    if duration is not None:
        n = n_of(duration)
        x = x[:n] if len(x) >= n else np.concatenate([x, np.zeros((n - len(x),) + x.shape[1:])])
    if dc_hz:
        x = _dc_block(x, loop, dc_hz)
    if not loop:
        x = fade(x, fade_in, fade_out)
    ceiling = db2lin(min(peak_db, PEAK_CEILING_DB) - _MARGIN_DB)
    tp = db2lin(measure.true_peak_db(x))
    if tp <= 0:
        return x
    if lufs is not None:
        g = db2lin(lufs - measure.lufs_integrated(x, loop=loop))
    elif loud is not None:
        g = db2lin(loud - measure.loud_short(x))
    elif rms_db is not None:
        g = db2lin(rms_db - measure.rms_db(x))
    else:
        g = ceiling / tp
    g = min(g, ceiling / tp)
    return x * g


def save(name, x, loop=False, quiet=False, **kw):
    """Finish and write FourthAndFury/AudioSource/<name>.wav. Returns the finished float signal."""
    y = finish(x, loop=loop, **kw)
    path = os.path.join(OUT_DIR, name + ".wav")
    write_wav(path, y, seed_name=name, zero_edges=0 if loop else 8)
    _log.append((name, len(y) / SR, 1 if y.ndim == 1 else 2))
    if not quiet:
        print(f"  {name:<24s} {len(y) / SR:6.2f}s  {'stereo' if y.ndim == 2 else 'mono  '}"
              f"  peak {measure.peak_db(y):6.1f} dBFS  rms {measure.rms_db(y):6.1f}"
              f"{'  loop' if loop else ''}", flush=True)
    return y


def saved():
    return list(_log)
