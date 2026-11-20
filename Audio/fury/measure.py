"""Measurement: levels, loudness (ITU-R BS.1770 K-weighting), spectra, loop-seam tests."""
import numpy as np
from scipy import linalg, signal

from .core import SR, circ_sos

# BS.1770-4 K-weighting at 48 kHz: high-shelf then high-pass.
_K_SOS = np.array([
    [1.53512485958697, -2.69169618940638, 1.19839281085285, 1.0, -1.69065929318241, 0.73248077421585],
    [1.0, -2.0, 1.0, 1.0, -1.99004745483398, 0.99007225036621],
])

BANDS = [("sub", 20, 60), ("bass", 60, 250), ("lowmid", 250, 1000),
         ("mid", 1000, 4000), ("high", 4000, 10000), ("air", 10000, 24000)]


def _chan(x):
    return x[:, None] if x.ndim == 1 else x


def db(v):
    return float(20.0 * np.log10(max(float(v), 1e-12)))


def peak_db(x):
    return db(np.max(np.abs(x))) if x.size else -240.0


def rms_db(x):
    return db(np.sqrt(np.mean(np.square(x)))) if x.size else -240.0


def true_peak_db(x, over=4):
    """Inter-sample peak estimate from an oversampled copy."""
    c = _chan(x)
    up = signal.resample_poly(c, over, 1, axis=0)
    return db(max(np.max(np.abs(up)), np.max(np.abs(c))))


def dc_offset(x):
    return float(np.max(np.abs(np.mean(_chan(x), axis=0))))


def k_weight(x):
    return signal.sosfilt(_K_SOS, _chan(x), axis=0)


def lufs_integrated(x, loop=False):
    """Gated integrated loudness. For loops the signal is treated as periodic: the K-weighting
    is the exact steady-state response and the 400 ms blocks wrap around the seam."""
    c = _chan(x)
    n = c.shape[0]
    block = int(0.4 * SR)
    hop = int(0.1 * SR)
    if loop:
        kw = circ_sos(c, _K_SOS)
        kw = np.concatenate([kw] * (1 + int(np.ceil(block / n))))[: n + block]
        starts = np.arange(0, n, hop)
    else:
        kw = k_weight(c)
        if kw.shape[0] < block:
            z = np.sum(np.mean(kw ** 2, axis=0))
            return float(-0.691 + 10 * np.log10(max(z, 1e-12)))
        starts = np.arange(0, kw.shape[0] - block + 1, hop)
    cs = np.concatenate([np.zeros((1, kw.shape[1])), np.cumsum(kw ** 2, axis=0)])
    z = np.sum((cs[starts + block] - cs[starts]) / block, axis=1)
    l = -0.691 + 10 * np.log10(np.maximum(z, 1e-12))
    keep = l > -70.0
    if not keep.any():
        return -70.0
    rel = -0.691 + 10 * np.log10(np.mean(z[keep])) - 10.0
    keep &= l > rel
    return float(-0.691 + 10 * np.log10(np.mean(z[keep])))


def loud_short(x, window=0.1, hop=0.01):
    """Loudest K-weighted window (default 100 ms), in LUFS-like dB. Short sounds are zero-padded
    to one window, which mimics the ear's temporal integration of brief events."""
    kw = k_weight(x)
    w = int(window * SR)
    if kw.shape[0] < w:
        kw = np.concatenate([kw, np.zeros((w - kw.shape[0], kw.shape[1]))])
    cs = np.concatenate([np.zeros((1, kw.shape[1])), np.cumsum(kw ** 2, axis=0)])
    starts = np.arange(0, kw.shape[0] - w + 1, max(int(hop * SR), 1))
    z = np.sum((cs[starts + w] - cs[starts]) / w, axis=1)
    return float(-0.691 + 10 * np.log10(max(np.max(z), 1e-12)))


def spectrum_db(x, nfft=8192):
    """Welch power spectrum of the mono sum. Returns (freqs, dB)."""
    m = _chan(x).mean(axis=1)
    nper = min(nfft, len(m))
    f, p = signal.welch(m, SR, nperseg=nper, noverlap=nper // 2, nfft=max(nfft, nper))
    return f, 10 * np.log10(np.maximum(p, 1e-20))


def band_energies(x):
    """Fraction of energy (in dB relative to total) in each of BANDS."""
    m = _chan(x).mean(axis=1)
    X = np.abs(np.fft.rfft(m)) ** 2
    f = np.fft.rfftfreq(len(m), 1.0 / SR)
    tot = max(X[f >= 20].sum(), 1e-20)
    return {name: float(10 * np.log10(max(X[(f >= lo) & (f < hi)].sum(), 1e-20) / tot))
            for name, lo, hi in BANDS}


def centroid(x):
    m = _chan(x).mean(axis=1)
    X = np.abs(np.fft.rfft(m)) ** 2
    f = np.fft.rfftfreq(len(m), 1.0 / SR)
    return float((f * X).sum() / max(X.sum(), 1e-20))


def edge_silence(x, thresh_db=-60.0):
    """Seconds before the first / after the last sample louder than thresh_db."""
    m = np.max(np.abs(_chan(x)), axis=1)
    idx = np.nonzero(m > 10 ** (thresh_db / 20.0))[0]
    if len(idx) == 0:
        return len(m) / SR, len(m) / SR
    return idx[0] / SR, (len(m) - 1 - idx[-1]) / SR


def time_to_peak(x, smooth=0.01):
    """Seconds until the smoothed energy envelope reaches its maximum."""
    m = np.max(np.abs(_chan(x)), axis=1)
    k = max(int(smooth * SR), 1)
    e = np.convolve(m ** 2, np.ones(k) / k, mode="same")
    return float(np.argmax(e) / SR)


def stereo_correlation(x):
    if x.ndim == 1:
        return 1.0
    a, b = x[:, 0], x[:, 1]
    d = np.sqrt(np.sum(a * a) * np.sum(b * b))
    return float(np.sum(a * b) / d) if d > 0 else 1.0


# ----------------------------------------------------------------------------- loop seam

def _lpc(x, order):
    X = np.fft.rfft(x)
    r = np.fft.irfft(np.abs(X) ** 2)[: order + 1]
    r[0] *= 1.0 + 1e-9
    a = linalg.solve_toeplitz(r[:-1], r[1:])
    return np.concatenate([[1.0], -a])


def seam_report(x, order=32):
    """Tests whether the last samples of a loop flow into the first.

    Returns the worst channel's figures:
      step_ratio   |x[0]-x[N-1]| divided by the RMS of ordinary sample-to-sample steps
      step_pct     percentile rank of the seam step among all steps (100 = largest in the file)
      curve_ratio  same for the second difference (slope continuity) at the seam
      lpc_ratio    linear-prediction residual at the seam / 99.9th percentile residual elsewhere
                   (a click is unpredictable, so it shows up as a ratio well above 1)
      band_db      largest octave-band level jump (dB) between the 50 ms before and after the seam
      band_ref_db  95th percentile of the same jump between adjacent 50 ms blocks inside the loop
    """
    c = _chan(x)
    n = c.shape[0]
    out = {"step_ratio": 0.0, "step_pct": 0.0, "curve_ratio": 0.0, "lpc_ratio": 0.0,
           "band_db": 0.0, "band_ref_db": 0.0}
    for ch in range(c.shape[1]):
        s = c[:, ch]
        d = np.diff(np.concatenate([s, s[:1]]))          # d[-1] is the seam step
        ordinary = np.abs(d[:-1])
        step_rms = max(np.sqrt(np.mean(ordinary ** 2)), 1e-12)
        seam = abs(d[-1])
        out["step_ratio"] = max(out["step_ratio"], seam / step_rms)
        out["step_pct"] = max(out["step_pct"], float(np.mean(ordinary <= seam) * 100.0))
        dd = np.diff(np.concatenate([s[-2:], s, s[:2]]), 2)   # second differences, wrapped
        seam_dd = np.max(np.abs(np.concatenate([dd[:2], dd[-2:]])))
        dd_rms = max(np.sqrt(np.mean(dd[2:-2] ** 2)), 1e-12)
        out["curve_ratio"] = max(out["curve_ratio"], seam_dd / dd_rms)

        a = _lpc(s, order)
        k = min(4096, n // 2)
        wrapped = np.concatenate([s[-k:], s[:k]])
        e_seam = signal.lfilter(a, [1.0], wrapped)
        seam_res = np.max(np.abs(e_seam[k - 1: k + order + 1]))
        e_all = np.abs(signal.lfilter(a, [1.0], s)[order:])
        ref = max(np.percentile(e_all, 99.9), 1e-12)
        out["lpc_ratio"] = max(out["lpc_ratio"], seam_res / ref)

        b = int(0.05 * SR)
        if n >= 6 * b:
            nb = n // b
            blocks = s[n - nb * b:].reshape(nb, b)             # aligned so the last block ends at the seam
            first = s[:b]
            oct_edges = [(63, 125), (125, 250), (250, 500), (500, 1000), (1000, 2000),
                         (2000, 4000), (4000, 8000), (8000, 16000)]
            f = np.fft.rfftfreq(b, 1.0 / SR)
            win = np.hanning(b)

            def bands(block):
                p = np.abs(np.fft.rfft(block * win, axis=-1)) ** 2
                return np.stack([10 * np.log10(np.maximum(p[..., (f >= lo) & (f < hi)].sum(axis=-1), 1e-20))
                                 for lo, hi in oct_edges], axis=-1)

            eb = bands(blocks)
            floor = eb.max() - 70.0                            # ignore bands that are essentially empty
            inner = np.abs(np.diff(np.maximum(eb, floor), axis=0))
            seam_jump = np.abs(np.maximum(bands(first), floor) - np.maximum(eb[-1], floor))
            out["band_db"] = max(out["band_db"], float(seam_jump.max()))
            out["band_ref_db"] = max(out["band_ref_db"], float(np.percentile(inner.max(axis=1), 95)))
    return out


def summarize(x, loop=False):
    """Standard set of figures used by the manifest and the verifier."""
    head, tail = edge_silence(x)
    return {
        "peak_dbfs": round(peak_db(x), 2),
        "true_peak_dbtp": round(true_peak_db(x), 2),
        "rms_dbfs": round(rms_db(x), 2),
        "lufs": round(lufs_integrated(x, loop=loop), 2),
        "loud_100ms": round(loud_short(x), 2),
        "dc": dc_offset(x),
        "head_silence_s": round(head, 4),
        "tail_silence_s": round(tail, 4),
        "centroid_hz": round(centroid(x), 1),
    }
