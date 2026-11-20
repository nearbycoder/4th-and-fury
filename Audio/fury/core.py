"""DSP toolkit: oscillators, noise, envelopes, filters, dynamics, reverb, mixing.

Everything works on float64 numpy arrays at SR. Mono signals are shape (n,),
stereo signals are shape (n, 2). Loop-safe ("circular") variants exist for every
process that has memory, so a loop can be rendered as one exact period of a
periodic signal instead of being cross-faded after the fact.
"""
import zlib

import numpy as np
from scipy import ndimage, signal

SR = 48000
TAU = 2.0 * np.pi


# ----------------------------------------------------------------------------- basics

def rng_for(name, salt=0):
    """Deterministic random generator derived from a sound's name."""
    seed = (zlib.crc32(name.encode("utf-8")) + 1000003 * int(salt)) & 0xFFFFFFFF
    return np.random.Generator(np.random.PCG64(seed))


def n_of(seconds):
    return int(round(seconds * SR))


def db2lin(d):
    return 10.0 ** (np.asarray(d, dtype=float) / 20.0)


def lin2db(x):
    return 20.0 * np.log10(np.maximum(np.abs(x), 1e-12))


def times(n):
    return np.arange(n) / SR


def as_curve(v, n):
    """Scalar or array -> array of length n."""
    if np.isscalar(v):
        return np.full(n, float(v))
    v = np.asarray(v, dtype=float)
    if len(v) != n:
        v = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(v)), v)
    return v


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def unit_rms(x):
    r = rms(x)
    return x / r if r > 0 else x


def unit_peak(x):
    p = np.max(np.abs(x)) if len(x) else 0.0
    return x / p if p > 0 else x


def pad_to(x, n):
    """Zero-pad or truncate to n samples (first axis)."""
    if len(x) == n:
        return x
    if len(x) > n:
        return x[:n]
    shape = (n - len(x),) + x.shape[1:]
    return np.concatenate([x, np.zeros(shape)])


# ----------------------------------------------------------------------------- oscillators

def phase(freq, n=None, start=0.0):
    """Running phase in cycles. freq is a scalar (needs n) or a per-sample array."""
    if np.isscalar(freq):
        return start + float(freq) * np.arange(n) / SR
    f = np.asarray(freq, dtype=float)
    ph = np.cumsum(f) / SR
    return start + ph - ph[0]


def sine(freq, n=None, start=0.0):
    return np.sin(TAU * phase(freq, n, start))


def _polyblep(t, dt):
    out = np.zeros_like(t)
    m = t < dt
    x = t[m] / dt[m]
    out[m] = x + x - x * x - 1.0
    m = t > 1.0 - dt
    x = (t[m] - 1.0) / dt[m]
    out[m] = x * x + x + x + 1.0
    return out


def saw(freq, n=None, start=0.0):
    """Band-limited (polyBLEP) rising sawtooth in [-1, 1]."""
    ph = phase(freq, n, start)
    t = ph % 1.0
    dt = as_curve(freq, len(t)) / SR
    return 2.0 * t - 1.0 - _polyblep(t, dt)


def pulse(freq, n=None, width=0.5, start=0.0):
    """Band-limited pulse wave (difference of two saws); width may be an array."""
    ph = phase(freq, n, start)
    nn = len(ph)
    dt = as_curve(freq, nn) / SR
    w = as_curve(width, nn)
    t1 = ph % 1.0
    t2 = (ph + w) % 1.0
    return (2.0 * t1 - 1.0 - _polyblep(t1, dt)) - (2.0 * t2 - 1.0 - _polyblep(t2, dt))


def triangle(freq, n=None, start=0.0):
    t = phase(freq, n, start) % 1.0
    return 4.0 * np.abs(t - 0.5) - 1.0


def harmonics(freq, n, amps, phases=None):
    """Additive oscillator. amps: sequence of harmonic amplitudes (index 0 = fundamental),
    each a scalar or a per-sample array. Harmonics above 0.45*SR are dropped."""
    ph = TAU * phase(freq, n)
    f = as_curve(freq, len(ph))
    out = np.zeros(len(ph))
    for h, a in enumerate(amps, start=1):
        if np.isscalar(a) and a == 0.0:
            continue
        ok = (f * h) < 0.45 * SR
        if not ok.any():
            break
        p0 = 0.0 if phases is None else phases[h - 1]
        out += np.where(ok, a, 0.0) * np.sin(h * ph + p0)
    return out


# ----------------------------------------------------------------------------- noise

def white(n, rng):
    return rng.standard_normal(n)


def shaped_noise(n, rng, tilt_db_oct=0.0, lo=None, hi=None, mag=None, edge_oct=0.5):
    """Gaussian noise with a designed magnitude spectrum, built in the FFT domain.

    The result is exactly periodic with period n (so it loops seamlessly) and has unit RMS.
    tilt_db_oct: spectral slope (-3 = pink, -6 = brown). lo/hi: band edges with raised-cosine
    skirts edge_oct octaves wide. mag: optional extra magnitude function of frequency (Hz).
    """
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1.0 / SR)
    fs = np.maximum(f, 1.0)
    g = (fs / 1000.0) ** (tilt_db_oct / 6.0206)
    if lo is not None:
        g = g * _skirt(np.log2(fs / lo) / edge_oct)
    if hi is not None:
        g = g * _skirt(np.log2(hi / fs) / edge_oct)
    if mag is not None:
        g = g * mag(fs)
    g[0] = 0.0
    y = np.fft.irfft(X * g, n)
    return unit_rms(y)


def _skirt(u):
    """0 below u=-1, 1 above u=0, raised cosine in between."""
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(u + 1.0, 0.0, 1.0))


def smooth_random(n, rng, rate_hz, periodic=True):
    """Slow random control signal, roughly unit variance, band-limited to ~rate_hz."""
    m = n if periodic else int(n * 1.5) + 16
    X = np.fft.rfft(rng.standard_normal(m))
    f = np.fft.rfftfreq(m, 1.0 / SR)
    X *= np.exp(-0.5 * (f / max(rate_hz, 1e-6)) ** 2)
    X[0] = 0.0
    y = np.fft.irfft(X, m)[:n]
    s = np.std(y)
    return y / s if s > 0 else y


def periodic_lfo(n, rng, cycles=(1, 2, 3, 5), weights=None):
    """Smooth pseudo-random curve that is exactly periodic over n samples (std ~1)."""
    t = np.arange(n) / n
    y = np.zeros(n)
    if weights is None:
        weights = [1.0 / np.sqrt(c) for c in cycles]
    for c, w in zip(cycles, weights):
        y += w * np.sin(TAU * (c * t + rng.random()))
    return y / np.sqrt(0.5 * np.sum(np.square(weights)))


# ----------------------------------------------------------------------------- envelopes

def env_points(n, pts, curve="lin"):
    """Piecewise envelope through (time_seconds, value) points. curve='exp' interpolates in dB."""
    tt = np.array([p[0] for p in pts], dtype=float)
    vv = np.array([p[1] for p in pts], dtype=float)
    t = times(n)
    if curve == "exp":
        return np.exp(np.interp(t, tt, np.log(np.maximum(vv, 1e-5))))
    return np.interp(t, tt, vv)


def env_perc(n, attack=0.001, tau=0.05, hold=0.0):
    """Percussive envelope: raised-cosine attack, optional hold, exponential decay (time constant tau)."""
    t = times(n)
    a = max(attack, 1.0 / SR)
    e = np.where(t < a, 0.5 - 0.5 * np.cos(np.pi * t / a), 1.0)
    td = np.maximum(t - a - hold, 0.0)
    return e * np.exp(-td / tau)


def env_adsr(n, a=0.01, d=0.05, s=0.7, r=0.05, gate=None):
    """ADSR. gate = note-on duration in seconds (default: n minus release)."""
    t = times(n)
    total = n / SR
    g = total - r if gate is None else gate
    g = max(g, 1e-4)
    att = np.clip(t / max(a, 1e-5), 0, 1)
    dec = s + (1 - s) * np.exp(-np.maximum(t - a, 0) / max(d, 1e-5) * 3.0)
    e = np.minimum(att, 1.0) * np.where(t < a, 1.0, dec)
    lvl_at_gate = float(np.interp(g, t, e))
    rel = lvl_at_gate * np.exp(-np.maximum(t - g, 0) / max(r, 1e-5) * 4.0)
    return np.where(t < g, e, rel)


def fade(x, t_in=0.001, t_out=0.005):
    """Raised-cosine fade at head and tail (in place on a copy)."""
    y = np.array(x, dtype=float, copy=True)
    n = len(y)
    a = min(n_of(t_in), n // 2)
    b = min(n_of(t_out), n // 2)
    if a > 0:
        w = 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
        y[:a] = (y[:a].T * w).T
    if b > 0:
        w = 0.5 + 0.5 * np.cos(np.pi * (np.arange(b) + 1) / b)
        y[-b:] = (y[-b:].T * w).T
    return y


# ----------------------------------------------------------------------------- filters

def _sos(kind, fc, order):
    nyq = SR / 2.0
    if kind in ("lp", "hp"):
        w = min(max(fc / nyq, 1e-5), 0.999)
        return signal.butter(order, w, btype="low" if kind == "lp" else "high", output="sos")
    lo, hi = fc
    w = [min(max(lo / nyq, 1e-5), 0.99), min(max(hi / nyq, 2e-5), 0.999)]
    return signal.butter(order, w, btype="band" if kind == "bp" else "bandstop", output="sos")


def _run(sos, x, circular):
    if circular:
        return circ_sos(x, sos)
    return signal.sosfilt(sos, x, axis=0)


def lp(x, fc, order=2, circular=False):
    return _run(_sos("lp", fc, order), x, circular)


def hp(x, fc, order=2, circular=False):
    return _run(_sos("hp", fc, order), x, circular)


def bp(x, lo, hi, order=2, circular=False):
    return _run(_sos("bp", (lo, hi), order), x, circular)


def notch(x, lo, hi, order=2, circular=False):
    return _run(_sos("bs", (lo, hi), order), x, circular)


def biquad(kind, f0, q=0.7071, gain_db=0.0):
    """RBJ cookbook biquad as a 1-section SOS. kind: lp, hp, bp (0 dB peak), peak, loshelf, hishelf, ap."""
    a_lin = 10.0 ** (gain_db / 40.0)
    w0 = TAU * min(f0, 0.49 * SR) / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2.0 * q)
    if kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "bp":
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "ap":
        b = [1 - alpha, -2 * cw, 1 + alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * a_lin, -2 * cw, 1 - alpha * a_lin]
        a = [1 + alpha / a_lin, -2 * cw, 1 - alpha / a_lin]
    elif kind in ("loshelf", "hishelf"):
        sq = 2.0 * np.sqrt(a_lin) * alpha
        if kind == "loshelf":
            b = [a_lin * ((a_lin + 1) - (a_lin - 1) * cw + sq), 2 * a_lin * ((a_lin - 1) - (a_lin + 1) * cw),
                 a_lin * ((a_lin + 1) - (a_lin - 1) * cw - sq)]
            a = [(a_lin + 1) + (a_lin - 1) * cw + sq, -2 * ((a_lin - 1) + (a_lin + 1) * cw),
                 (a_lin + 1) + (a_lin - 1) * cw - sq]
        else:
            b = [a_lin * ((a_lin + 1) + (a_lin - 1) * cw + sq), -2 * a_lin * ((a_lin - 1) + (a_lin + 1) * cw),
                 a_lin * ((a_lin + 1) + (a_lin - 1) * cw - sq)]
            a = [(a_lin + 1) - (a_lin - 1) * cw + sq, 2 * ((a_lin - 1) - (a_lin + 1) * cw),
                 (a_lin + 1) - (a_lin - 1) * cw - sq]
    else:
        raise ValueError(kind)
    b = np.array(b) / a[0]
    a = np.array(a) / a[0]
    return np.array([[b[0], b[1], b[2], 1.0, a[1], a[2]]])


def eq(x, bands, circular=False):
    """Apply a list of (kind, f0, q, gain_db) biquads in series."""
    sos = np.vstack([biquad(k, f, q, g) for (k, f, q, g) in bands])
    return _run(sos, x, circular)


def resonator(x, f0, q=10.0, circular=False):
    return _run(biquad("bp", f0, q), x, circular)


def circ_sos(x, sos):
    """Exact steady-state response of an SOS filter to the periodic extension of x."""
    n = x.shape[0]
    w = TAU * np.fft.rfftfreq(n)
    _, h = signal.sosfreqz(sos, worN=w)
    if x.ndim == 1:
        return np.fft.irfft(np.fft.rfft(x) * h, n)
    return np.fft.irfft(np.fft.rfft(x, axis=0) * h[:, None], n, axis=0)


def circ_mag(x, mag):
    """Zero-phase periodic filtering with an arbitrary magnitude function of frequency (Hz)."""
    n = x.shape[0]
    g = mag(np.maximum(np.fft.rfftfreq(n, 1.0 / SR), 1e-3))
    if x.ndim == 1:
        return np.fft.irfft(np.fft.rfft(x) * g, n)
    return np.fft.irfft(np.fft.rfft(x, axis=0) * g[:, None], n, axis=0)


def sweep_filter(x, fc, kind="lp", q=0.7071, order=1, n_bank=30, f_lo=30.0, f_hi=18000.0):
    """Time-varying filter: a bank of fixed biquads (log-spaced) cross-faded sample by sample.

    fc: per-sample cutoff/centre (Hz). order = number of cascaded identical biquads.
    """
    n = len(x)
    fc = np.clip(as_curve(fc, n), f_lo, f_hi)
    pos = np.log(fc / f_lo) / np.log(f_hi / f_lo) * (n_bank - 1)
    i0 = np.clip(np.floor(pos).astype(int), 0, n_bank - 2)
    frac = pos - i0
    fb = np.geomspace(f_lo, f_hi, n_bank)
    out = np.zeros(n)
    idx = np.arange(n)
    for k in range(int(i0.min()), int(i0.max()) + 2):
        m0 = i0 == k
        m1 = i0 == k - 1
        if not (m0.any() or m1.any()):
            continue
        sos = np.vstack([biquad(kind, fb[k], q)] * order)
        y = signal.sosfilt(sos, x)
        out[idx[m0]] += y[m0] * (1.0 - frac[m0])
        out[idx[m1]] += y[m1] * frac[m1]
    return out


def modal(n, freqs, taus, amps, phases=None, f_curve=None):
    """Impulse response of a struck object: sum of exponentially decaying sinusoids.
    f_curve: optional per-sample frequency multiplier (e.g. a pitch drop)."""
    t = times(n)
    out = np.zeros(n)
    if f_curve is not None:
        ph_base = np.cumsum(as_curve(f_curve, n)) / SR
    for i, (f, tau, a) in enumerate(zip(freqs, taus, amps)):
        if f >= 0.45 * SR:
            continue
        p0 = 0.0 if phases is None else phases[i]
        ph = TAU * f * (t if f_curve is None else ph_base) + p0
        out += a * np.exp(-t / tau) * np.sin(ph)
    return out


def contact(x, ms):
    """Soften an impact by convolving with a half-sine contact pulse of the given duration."""
    k = max(int(ms * 1e-3 * SR), 1)
    if k < 2:
        return x
    w = np.sin(np.pi * (np.arange(k) + 0.5) / k)
    w /= w.sum()
    return signal.fftconvolve(x, w)[: len(x)]


# ----------------------------------------------------------------------------- dynamics

def saturate(x, drive_db=6.0, asym=0.0, out_norm=True):
    """tanh waveshaper. asym adds even harmonics (bias inside the shaper, DC removed after)."""
    g = db2lin(drive_db)
    if asym:
        y = np.tanh(g * x + asym) - np.tanh(asym)
    else:
        y = np.tanh(g * x)
    return y / np.tanh(g) if out_norm else y


def _follow(level, att_coef, rel_coef, start=0.0):
    out = np.empty_like(level)
    e = start
    for i, v in enumerate(level.tolist()):
        c = att_coef if v > e else rel_coef
        e = v + c * (e - v)
        out[i] = e
    return out, e


def envelope_follow(x, attack=0.005, release=0.1, hop=16, circular=False):
    """Peak envelope with separate attack/release, computed at control rate and interpolated."""
    mono = np.abs(x) if x.ndim == 1 else np.max(np.abs(x), axis=1)
    n = len(mono)
    nb = max(int(np.ceil(n / hop)), 1)
    bounds = (np.arange(nb) * n) // nb
    blocks = np.maximum.reduceat(mono, bounds)
    step = n / nb
    ac = np.exp(-step / (SR * max(attack, 1e-5)))
    rc = np.exp(-step / (SR * max(release, 1e-5)))
    env, last = _follow(blocks, ac, rc, 0.0)
    centres = (np.arange(nb) + 0.5) * step
    if circular:
        env, _ = _follow(blocks, ac, rc, last)
        return np.interp(np.arange(n), centres, env, period=n)
    return np.interp(np.arange(n), centres, env)


def compress(x, thresh_db=-18.0, ratio=4.0, attack=0.005, release=0.12, knee_db=6.0,
             makeup_db=0.0, sidechain=None, circular=False, return_gain=False):
    """Feed-forward compressor (soft knee). Works on mono or stereo (linked)."""
    sc = x if sidechain is None else sidechain
    env = envelope_follow(sc, attack, release, circular=circular)
    lvl = lin2db(env)
    over = lvl - thresh_db
    k = max(knee_db, 1e-6)
    gr = np.where(over <= -k / 2, 0.0,
                  np.where(over >= k / 2, over * (1 - 1 / ratio),
                           (1 - 1 / ratio) * (over + k / 2) ** 2 / (2 * k)))
    g = db2lin(makeup_db - gr)
    y = x * g if x.ndim == 1 else x * g[:, None]
    return (y, g) if return_gain else y


def limiter(x, ceiling_db=-1.0, lookahead=0.003, circular=False):
    """Look-ahead brick-wall limiter: the gain never lets a sample exceed the ceiling."""
    c = db2lin(ceiling_db)
    mono = np.abs(x) if x.ndim == 1 else np.max(np.abs(x), axis=1)
    need = np.minimum(1.0, c / np.maximum(mono, 1e-12))
    w = max(int(lookahead * SR), 1) * 2 + 1
    mode = "wrap" if circular else "nearest"
    g = ndimage.minimum_filter1d(need, size=w, mode=mode)
    g = ndimage.uniform_filter1d(g, size=w // 2 + 1, mode=mode)
    g = np.minimum(g, need)
    return x * g if x.ndim == 1 else x * g[:, None]


def transient_shape(x, attack_gain_db=0.0, sustain_gain_db=0.0, fast=0.001, slow=0.03):
    """Simple transient designer: boost/cut where the fast envelope exceeds the slow one."""
    ef = envelope_follow(x, fast, 0.03, hop=4)
    es = envelope_follow(x, slow, 0.03, hop=4)
    ratio = np.clip((ef - es) / np.maximum(ef, 1e-9), 0.0, 1.0)
    g = db2lin(attack_gain_db * ratio + sustain_gain_db * (1.0 - ratio))
    return x * g if x.ndim == 1 else x * g[:, None]


# ----------------------------------------------------------------------------- stereo

def pan(x, p=0.0):
    """Constant-power pan of a mono signal; p in [-1 (left), 1 (right)]. Returns (n, 2)."""
    a = (np.clip(p, -1.0, 1.0) + 1.0) * np.pi / 4.0
    return np.stack([x * np.cos(a), x * np.sin(a)], axis=1)


def to_stereo(x):
    return x if x.ndim == 2 else np.stack([x, x], axis=1)


def to_mono(x):
    return x if x.ndim == 1 else x.mean(axis=1)


def width(x, w):
    """Scale the side signal of a stereo signal (w=0 mono, 1 unchanged, >1 wider)."""
    mid = x.mean(axis=1)
    side = (x[:, 0] - x[:, 1]) * 0.5 * w
    return np.stack([mid + side, mid - side], axis=1)


# ----------------------------------------------------------------------------- space

_RT_F = np.log2([63.0, 125, 250, 500, 1000, 2000, 4000, 8000, 16000])


def reverb_ir(rt60=1.5, seed=1, pre_delay=0.015, lf_mult=1.15, hf_mult=0.45, build=0.012,
              er=(), lowcut=90.0, highcut=11000.0, stereo=True, length=None):
    """Synthetic room impulse response: band-wise exponentially decaying Gaussian noise
    (frequency-dependent RT60) plus optional discrete early reflections [(seconds, gain), ...].
    Normalised to unit energy per channel."""
    chans = []
    n = n_of(length if length else rt60 * 1.2)
    t = times(n)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    lf = np.log2(np.maximum(f, 1.0))
    centres = np.log2([62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000])
    mult = np.interp(centres, _RT_F, [lf_mult, lf_mult, (1 + lf_mult) / 2, 1.0, 1.0,
                                      1 - 0.35 * (1 - hf_mult), 1 - 0.7 * (1 - hf_mult), hf_mult, 0.7 * hf_mult])
    for ch in range(2 if stereo else 1):
        rng = np.random.Generator(np.random.PCG64(seed * 7919 + ch * 104729 + 17))
        X = np.fft.rfft(rng.standard_normal(n))
        tail = np.zeros(n)
        for i, c in enumerate(centres):
            d = lf - c
            w = np.cos(0.5 * np.pi * np.clip(np.abs(d), 0.0, 1.0)) ** 2
            if i == 0:
                w = np.where(d < 0, 1.0, w)
            if i == len(centres) - 1:
                w = np.where(d > 0, 1.0, w)
            band = np.fft.irfft(X * w, n)
            tail += band * np.exp(-6.9078 * t / (rt60 * mult[i]))
        tail *= 1.0 - np.exp(-t / max(build, 1e-4))
        tail = hp(lp(tail, highcut, 2), lowcut, 2)
        tail /= np.sqrt(np.sum(tail ** 2))
        ir = tail
        if er:
            e = np.zeros(n)
            for k, (tt, gg) in enumerate(er):
                jitter = 1.0 + (0.07 * rng.standard_normal() if stereo else 0.0)
                i0 = min(int(tt * jitter * SR), n - 1)
                e[i0] += gg * (1.0 if (k + ch) % 2 == 0 else -1.0)
            e = lp(e, 6000.0, 1)
            ir = ir + e
        pd = n_of(pre_delay)
        ir = np.concatenate([np.zeros(pd), ir])
        ir /= np.sqrt(np.sum(ir ** 2))
        chans.append(ir)
    return np.stack(chans, axis=1) if stereo else chans[0]


def convolve(x, ir, circular=False):
    """Convolve mono/stereo x with mono/stereo ir. Non-circular output keeps the full tail."""
    xs = [x] if x.ndim == 1 else [x[:, 0], x[:, 1]]
    irs = [ir] if ir.ndim == 1 else [ir[:, 0], ir[:, 1]]
    nch = max(len(xs), len(irs))
    out = []
    for c in range(nch):
        a = xs[c % len(xs)]
        b = irs[c % len(irs)]
        if circular:
            n = len(a)
            m = int(np.ceil(len(b) / n)) * n
            folded = pad_to(b, m).reshape(-1, n).sum(axis=0)
            out.append(np.fft.irfft(np.fft.rfft(a) * np.fft.rfft(folded), n))
        else:
            out.append(signal.fftconvolve(a, b))
    return out[0] if nch == 1 else np.stack(out, axis=1)


def reverb(x, ir, wet_db=-12.0, dry_db=0.0, circular=False, tail=True):
    """Dry + wet mix. Returns stereo if either input is stereo. tail=False keeps the input length."""
    w = convolve(x, ir, circular=circular)
    n = len(w) if (tail and not circular) else len(x)
    d = x
    if w.ndim == 2 and d.ndim == 1:
        d = to_stereo(d)
    out = pad_to(w, n) * db2lin(wet_db)
    out[: len(d)] += d[:n] * db2lin(dry_db)
    return out


def echo(x, delay, gain_db=-9.0, repeats=1, feedback_db=-6.0, damp=None, circular=False):
    """Discrete echoes (slap-back). Output is extended to hold the echoes unless circular."""
    d = n_of(delay)
    n = len(x) if circular else len(x) + d * repeats
    out = pad_to(np.array(x, dtype=float), n)
    src = x
    g = db2lin(gain_db)
    for r in range(1, repeats + 1):
        if damp:
            src = lp(src, damp, 1, circular=circular)
        if circular:
            out += np.roll(src, d * r, axis=0) * g
        else:
            out[d * r: d * r + len(src)] += src * g
        g *= db2lin(feedback_db)
    return out


# ----------------------------------------------------------------------------- timeline

class Timeline:
    """Stereo (or mono) mixing buffer. With loop=True everything that runs past the end wraps
    around to the start, so the buffer is one period of a periodic signal."""

    def __init__(self, seconds=None, n=None, loop=False, channels=2):
        self.n = n if n is not None else n_of(seconds)
        self.loop = loop
        self.channels = channels
        self.buf = np.zeros((self.n, channels)) if channels == 2 else np.zeros(self.n)

    def add(self, sig, at=0.0, gain=1.0, pan_pos=0.0, sample=None):
        s = np.asarray(sig, dtype=float)
        if self.channels == 2 and s.ndim == 1:
            s = pan(s, pan_pos)
        elif self.channels == 1 and s.ndim == 2:
            s = s.mean(axis=1)
        i0 = int(sample) if sample is not None else int(round(at * SR))
        m = len(s)
        if self.loop:
            i0 %= self.n
            pos = 0
            while pos < m:
                room = self.n - i0
                take = min(room, m - pos)
                self.buf[i0:i0 + take] += s[pos:pos + take] * gain
                pos += take
                i0 = 0
        else:
            if i0 < 0:
                s = s[-i0:]
                m = len(s)
                i0 = 0
            if i0 + m > self.n:
                extra = i0 + m - self.n
                pad_shape = (extra, 2) if self.channels == 2 else (extra,)
                self.buf = np.concatenate([self.buf, np.zeros(pad_shape)])
                self.n = len(self.buf)
            self.buf[i0:i0 + m] += s * gain
        return self


def place(n, events):
    """Mono helper: sum (signal, start_seconds, gain) events into an n-sample buffer (truncating)."""
    out = np.zeros(n)
    for s, t0, g in events:
        i0 = max(int(round(t0 * SR)), 0)
        if i0 >= n:
            continue
        m = min(len(s), n - i0)
        out[i0:i0 + m] += s[:m] * g
    return out


def resample(x, ratio):
    """Resample by ratio (>1 = longer and lower pitch when played at SR)."""
    from fractions import Fraction
    fr = Fraction(ratio).limit_denominator(400)
    return signal.resample_poly(x, fr.numerator, fr.denominator, axis=0)
