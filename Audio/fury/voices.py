"""Vocal sounds built from a source-filter model.

Two engines:
  * formant_voice(): one detailed voice (additive harmonics weighted by a time-varying vocal-tract
    response, jitter, shimmer, sub-harmonic roughness, shaped breath noise). Used for the
    quarterback "hut", effort grunts and other close-up vocal effects.
  * Crowd: hundreds of cheap voices (saw-tooth glottal source -> formant resonators) rendered at
    16 kHz and summed into a stereo field. Every voice stream is exactly periodic over the buffer,
    so a crowd bed loops with no seam by construction.
"""
import numpy as np
from scipy import signal

from .core import SR, TAU, as_curve, n_of, saw, smooth_random, times, unit_rms

# Average adult-male formant frequencies F1..F3 (Hz); F4/F5 are added as constants below.
VOWELS = {
    "i": (280, 2250, 2950),    # beet
    "I": (400, 1950, 2550),    # bit
    "e": (480, 1900, 2550),    # bait (start)
    "E": (560, 1800, 2500),    # bet
    "ae": (680, 1700, 2450),   # bat
    "a": (750, 1150, 2500),    # father
    "uh": (640, 1200, 2400),   # but
    "aw": (590, 880, 2450),    # bought
    "o": (480, 880, 2450),     # boat (start)
    "U": (440, 1050, 2300),    # book
    "u": (320, 820, 2300),     # boot
    "er": (490, 1350, 1700),   # bird
    "m": (280, 1050, 2200),    # closed-mouth hum (nasal murmur)
}
F4, F5 = 3400.0, 4400.0
BW = (70.0, 95.0, 140.0, 220.0, 300.0)


def vowel(name, scale=1.0, effort=0.0):
    """Formant frequencies for a vowel. scale = vocal-tract length factor (women ~1.17).
    effort (0..1) opens the jaw: F1 rises, as in shouted speech."""
    f1, f2, f3 = VOWELS[name]
    f1 = f1 * (1.0 + 0.22 * effort)
    return np.array([f1, f2, f3, F4, F5]) * scale


def tract_mag(f, formants, bws=BW):
    """|V(f)| of a cascade of 2-pole formant resonators (unity gain at DC). f, formants may be arrays."""
    out = 1.0
    for fk, bk in zip(formants, bws):
        half = 0.5 * bk
        num = fk * fk + half * half
        out = out * num / np.sqrt(((f - fk) ** 2 + half * half) * ((f + fk) ** 2 + half * half))
    return out


def shape_noise_tv(x, mag_fn, nper=512):
    """Time-varying spectral shaping (STFT). mag_fn(freqs[:, None], times[None, :]) -> gains."""
    f, t, z = signal.stft(x, SR, window="hann", nperseg=nper, noverlap=nper * 3 // 4)
    z = z * mag_fn(f[:, None], t[None, :])
    _, y = signal.istft(z, SR, window="hann", nperseg=nper, noverlap=nper * 3 // 4)
    return y[: len(x)] if len(y) >= len(x) else np.concatenate([y, np.zeros(len(x) - len(y))])


def formant_voice(n, f0, formants, rng, tilt_db_oct=-8.0, jitter=0.008, shimmer=0.05, sub=0.0,
                  breath=0.04, max_f=9000.0, bws=BW, flutter=0.0):
    """One voice, unit RMS (apply the amplitude envelope afterwards).

    f0: Hz, scalar or (n,). formants: (K, n) array or list of K scalars/arrays.
    tilt_db_oct: net spectral slope of the glottal source after lip radiation
                 (about -9 relaxed, -6 loud, -3 shouted/pressed).
    sub: depth of period-doubling (every other glottal pulse weaker) -> growl / vocal fry.
    flutter: depth of slow irregular amplitude wobble (strained voice).
    """
    f0 = as_curve(f0, n)
    fm = [as_curve(fk, n) for fk in formants]
    f = f0 * (1.0 + jitter * smooth_random(n, rng, 45.0) + 0.6 * jitter * smooth_random(n, rng, 7.0))
    ph = TAU * np.cumsum(f) / SR
    hmax = int(max_f / max(np.min(f), 30.0))
    out = np.zeros(n)
    for h in range(1, hmax + 1):
        fh = h * f
        if np.min(fh) > max_f:
            break
        a = h ** (tilt_db_oct / 6.0206) * tract_mag(fh, fm, bws)
        a = np.where(fh < max_f, a, 0.0)
        out += a * np.sin(h * ph)
    if sub:
        out *= 1.0 + sub * np.sin(0.5 * ph + 0.7)
    if shimmer:
        out *= 1.0 + shimmer * smooth_random(n, rng, 35.0)
    if flutter:
        out *= 1.0 + flutter * smooth_random(n, rng, 14.0)
    out = unit_rms(out)
    if breath:
        nz = rng.standard_normal(n)

        def mag(ff, tt):
            idx = np.clip((tt * SR).astype(int), 0, n - 1)
            cur = [fk[idx] for fk in fm]
            return tract_mag(np.maximum(ff, 50.0), cur, [b * 2.2 for b in bws]) * np.minimum(ff / 800.0, 1.0)

        nz = shape_noise_tv(nz, mag)
        nz = unit_rms(nz) * (0.55 + 0.45 * np.maximum(np.sin(ph), 0.0))
        out = out + breath * nz
    return out


# ----------------------------------------------------------------------------- crowd

CROWD_DIV = 3
CSR = SR // CROWD_DIV


def _res_h(z1, f, bw):
    c = -np.exp(-TAU * bw / CSR)
    b = 2.0 * np.exp(-np.pi * bw / CSR) * np.cos(TAU * f / CSR)
    return (1.0 - b - c) / (1.0 - b * z1 - c * z1 * z1)


class Crowd:
    """Accumulates many simple voices into a stereo buffer at CSR, then upsamples to SR.

    A voice is a list of events (a syllable, a yell, an "ooh"). All of one voice's events share
    its glottal oscillator; each event picks one of the voice's vowels (optionally gliding to a
    second one), a pitch contour and an amplitude envelope.
    """

    def __init__(self, seconds, rng, loop=False, pad=0.25):
        self.loop = loop
        n = n_of(seconds)
        if not loop:
            n += n_of(pad)
        n -= n % CROWD_DIV
        self.n_out = n
        self.n = n // CROWD_DIV
        self.rng = rng
        self.buf = np.zeros((self.n, 2))
        self.w = TAU * np.fft.rfftfreq(self.n)
        self.z1 = np.exp(-1j * self.w)
        self.fhz = np.fft.rfftfreq(self.n, 1.0 / CSR)
        self.voices = 0

    def add_voice(self, events, vowels, f0_base, gain=1.0, pan=0.0, tilt_hz=1500.0, jitter=0.012,
                  vibrato=0.0, breath=0.0, rough=0.0, shimmer=0.06, voicing=1.0,
                  cons_bands=((1700.0, 4200.0), (3600.0, 7400.0))):
        """events: iterable of dicts with keys
             t, dur          start and length in seconds
             f0              (start_mult, peak_mult, end_mult) relative to f0_base, or a scalar
             peak_at         where in the event the pitch peak sits (0..1)
             v, v2           index into `vowels` at the start / end of the event (v2 optional)
             locus           optional vowel index the event starts from (a consonant-like formant
                             transition into v during the first ~45 ms)
             amp             linear amplitude
             att, rel        attack and release times in seconds (raised cosine)
             cons            optional (band, seconds, amp): a noise burst (fricative / stop release)
                             leading into the event; band indexes cons_bands
        vowels: list of formant arrays (see vowel()).
        tilt_hz: glottal source low-pass corner (voice effort). breath: aspiration noise mixed into
        the source. rough: period-doubling depth (raspy shout). shimmer: amplitude perturbation.
        voicing: 1 = normal voice, 0 = whispered / unvoiced (only the breath noise excites the tract)."""
        n = self.n
        rng = self.rng
        f0 = np.full(n, float(f0_base))
        weights = np.zeros((len(vowels), n))
        cons_w = np.zeros((len(cons_bands), n))
        any_event = False
        for ev in events:
            i0 = int(round(ev["t"] * CSR))
            m = max(int(round(ev["dur"] * CSR)), 16)
            idx = np.arange(i0, i0 + m)
            if self.loop:
                idx %= n
                sl = slice(None)
            else:
                keep = (idx >= 0) & (idx < n)
                if not keep.any():
                    continue
                idx = idx[keep]
                sl = keep
            u = (np.arange(m) + 0.5) / m
            att = max(int(ev.get("att", 0.03) * CSR), 2)
            rel = max(int(ev.get("rel", 0.06) * CSR), 2)
            env = np.ones(m)
            a = min(att, m // 2)
            r = min(rel, m - a)
            env[:a] = 0.5 - 0.5 * np.cos(np.pi * (np.arange(a) + 0.5) / a)
            env[m - r:] = 0.5 + 0.5 * np.cos(np.pi * (np.arange(r) + 0.5) / r)
            env *= ev.get("amp", 1.0)
            fm = ev.get("f0", 1.0)
            if np.isscalar(fm):
                contour = np.full(m, float(fm))
            else:
                a0, pk, a1 = fm
                peak_at = ev.get("peak_at", 0.3)
                contour = np.where(u < peak_at,
                                   a0 + (pk - a0) * np.sin(0.5 * np.pi * u / peak_at),
                                   a1 + (pk - a1) * np.cos(0.5 * np.pi * (u - peak_at) / (1 - peak_at)))
            f0[idx] = f0_base * contour[sl]
            v = ev.get("v", 0)
            v2 = ev.get("v2", v)
            w_main = env
            if "locus" in ev and ev["locus"] != v:
                lt = min(int(0.045 * CSR), m // 2)
                gl = np.ones(m)
                gl[:lt] = 0.5 - 0.5 * np.cos(np.pi * (np.arange(lt) + 0.5) / lt)
                weights[ev["locus"], idx] += (env * (1.0 - gl))[sl]
                w_main = env * gl
            if v2 == v:
                weights[v, idx] += w_main[sl]
            else:
                g = np.clip((u - 0.25) / 0.5, 0.0, 1.0)
                weights[v, idx] += (w_main * (1.0 - g))[sl]
                weights[v2, idx] += (w_main * g)[sl]
            if "cons" in ev:
                band, cdur, camp = ev["cons"]
                cm = max(int(cdur * CSR), 8)
                ci = np.arange(i0 - cm + int(0.008 * CSR), i0 + int(0.008 * CSR))
                cu = (np.arange(cm) + 0.5) / cm
                cenv = np.sin(np.pi * np.minimum(cu * 1.0, 1.0)) ** 0.7 * camp * ev.get("amp", 1.0)
                if self.loop:
                    cons_w[band, ci % n] += cenv
                else:
                    ck = (ci >= 0) & (ci < n)
                    cons_w[band, ci[ck]] += cenv[ck]
            any_event = True
        if not any_event:
            return
        f = f0 * (1.0 + jitter * (0.8 * smooth_random(n, rng, 6.0) + 0.5 * smooth_random(n, rng, 55.0)))
        if vibrato:
            cyc_v = max(round((5.0 + rng.random()) * n / CSR), 1)
            f *= 1.0 + vibrato * np.sin(TAU * (cyc_v * np.arange(n) / n + rng.random()))
        cycles = np.sum(f) / CSR
        target = 2.0 * np.round(cycles / 2.0) if rough else np.round(cycles)
        f *= target / cycles                              # whole number of cycles -> periodic oscillator
        ph = np.cumsum(f) / CSR
        ph += rng.random() * 2.0
        t = ph % 1.0
        dt = f / CSR
        src = 2.0 * t - 1.0
        m0 = t < dt
        x = t[m0] / dt[m0]
        src[m0] -= x + x - x * x - 1.0
        m1 = t > 1.0 - dt
        x = (t[m1] - 1.0) / dt[m1]
        src[m1] -= x * x + x + x + 1.0
        if rough:
            src *= 1.0 + rough * np.sin(np.pi * ph)
        if shimmer:
            src *= 1.0 + shimmer * smooth_random(n, rng, 28.0)
        noise = rng.standard_normal(n) if (breath or cons_w.any()) else None
        if breath:
            src = voicing * src + breath * 1.7 * noise * (0.6 + 0.4 * np.cos(TAU * ph))
        S = np.fft.rfft(src)
        S *= 1.0 / np.sqrt(1.0 + (self.fhz / tilt_hz) ** 2)        # glottal tilt (one-pole magnitude)
        S[0] = 0.0
        out = np.zeros(n)
        for k, fmts in enumerate(vowels):
            if not weights[k].any():
                continue
            H = np.ones(len(self.z1), dtype=complex)
            for fk, bk in zip(fmts, BW):
                if fk < 0.46 * CSR:
                    H *= _res_h(self.z1, fk, bk * 1.25)
            out += weights[k] * np.fft.irfft(S * H, n)
        if cons_w.any():
            N = np.fft.rfft(noise)
            for j, (lo, hi) in enumerate(cons_bands):
                if not cons_w[j].any():
                    continue
                fc = np.sqrt(lo * hi)
                q = fc / (hi - lo)
                fs = np.maximum(self.fhz, 1.0)
                mag = 1.0 / np.sqrt(1.0 + (q * (fs / fc - fc / fs)) ** 2)
                out += cons_w[j] * np.fft.irfft(N * mag, n) * 0.35
        a = (np.clip(pan, -1.0, 1.0) + 1.0) * np.pi / 4.0
        self.buf[:, 0] += out * (gain * np.cos(a))
        self.buf[:, 1] += out * (gain * np.sin(a))
        self.voices += 1

    def render(self):
        """Upsample the accumulated field to SR (band-limited, periodic). Returns (n_out, 2)."""
        n, m = self.n, self.n_out
        X = np.fft.rfft(self.buf, axis=0)
        Y = np.zeros((m // 2 + 1, 2), dtype=complex)
        k = min(len(X) - 1, len(Y))
        Y[:k] = X[:k]
        fade_bins = max(int(k * 0.04), 1)
        Y[k - fade_bins:k] *= np.linspace(1.0, 0.0, fade_bins)[:, None]
        return np.fft.irfft(Y, m, axis=0) * CROWD_DIV


def person(rng, female_prob=0.38, child_prob=0.0):
    """Random speaker: (base f0 for relaxed speech, vocal-tract scale)."""
    r = rng.random()
    if r < child_prob:
        return 260.0 * np.exp(0.10 * rng.standard_normal()), 1.32
    if r < child_prob + female_prob:
        return 205.0 * np.exp(0.11 * rng.standard_normal()), 1.16 * (1 + 0.03 * rng.standard_normal())
    return 118.0 * np.exp(0.13 * rng.standard_normal()), 1.0 * (1 + 0.04 * rng.standard_normal())


def distance_gain(rng, r_min=12.0, r_max=60.0):
    """Listener in the middle of uniformly seated people: p(r) ~ r, amplitude ~ 1/r (relative to r_min)."""
    r = np.sqrt(r_min ** 2 + rng.random() * (r_max ** 2 - r_min ** 2))
    return r_min / r
