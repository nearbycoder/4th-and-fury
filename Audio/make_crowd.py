# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1"]
# ///
"""4th & Fury -- crowd and stadium ambience (AMB_*.wav).

    uv run Audio/make_crowd.py [name-filter ...]

A stadium crowd is modelled the way it is physically built:
  * the far crowd -- tens of thousands of voices -- is statistically Gaussian noise with the
    long-term spectrum of (murmuring or shouting) voices, generated in the FFT domain so that it
    is exactly periodic over the loop;
  * the nearest few hundred people are synthesised one by one (glottal saw -> vowel formants,
    each with its own pitch, vocal-tract size, position and phrasing), which gives the bed its
    "made of people" texture;
  * applause is thousands of individual hand-clap grains; whistles and whoops are sprinkled in;
  * everything is placed in a large open-air bowl (long, dark, diffuse reverb).
"""
import sys

import numpy as np

from fury import catalog
from fury.core import (SR, TAU, Timeline, convolve, db2lin, env_points, hp, limiter, lp, n_of, pad_to,
                       periodic_lfo, reverb_ir, rng_for, shaped_noise, smooth_random, times, unit_rms)
from fury.voices import Crowd, distance_gain, person, vowel
from fury.wavio import save


# ----------------------------------------------------------------------------- spectra

def ltas(points):
    """Magnitude function from (Hz, dB) break-points, interpolated on a log-frequency axis."""
    lf = np.log2([p[0] for p in points])
    d = np.array([p[1] for p in points], dtype=float)
    return lambda f: 10.0 ** (np.interp(np.log2(np.maximum(f, 1.0)), lf, d) / 20.0)


# Long-term average spectra of a distant crowd (dB re. the peak).
# Murmur: relaxed speech, energy centred 300-800 Hz, falling ~10 dB/octave above 1 kHz.
# Roar: shouted vowels flatten the tilt (more 1-4 kHz) and applause/whistles fill the top.
LTAS_MURMUR = ltas([(20, -40), (50, -20), (100, -11), (200, -4), (400, 0), (700, -0.5), (1000, -3),
                    (2000, -11), (3000, -16), (4000, -21), (6000, -28), (8000, -34), (12000, -44), (20000, -60)])
LTAS_ROAR = ltas([(20, -44), (50, -24), (100, -15), (200, -8), (400, -3), (700, 0), (1000, 0),
                  (2000, -3), (3000, -6), (4000, -10), (6000, -16), (8000, -21), (12000, -30), (20000, -46)])


def stereo_noise(n, rng, mag, coherence_hz=180.0):
    """Stereo Gaussian noise with a designed spectrum, periodic over n. The two channels are
    coherent at low frequencies (as a diffuse field is) and independent above ~coherence_hz."""
    f = np.maximum(np.fft.rfftfreq(n, 1.0 / SR), 1.0)
    g = mag(f)
    g[0] = 0.0
    coh = 1.0 / (1.0 + (f / coherence_hz) ** 2)
    c = np.fft.rfft(rng.standard_normal(n))
    out = []
    for _ in range(2):
        i = np.fft.rfft(rng.standard_normal(n))
        out.append(np.fft.irfft((np.sqrt(coh) * c + np.sqrt(1.0 - coh) * i) * g, n))
    y = np.stack(out, axis=1)
    return y / np.sqrt(np.mean(y ** 2))


def breathe(x, rng, depths_db=(1.2, 2.0, 2.6), edges=(350.0, 2500.0), cycles=(1, 2, 3, 5, 7)):
    """Slow, loop-periodic level drift, different in the low / voice / high bands, so the bed
    swells and thins like a crowd instead of sitting still like a noise generator."""
    n = len(x)
    f = np.maximum(np.fft.rfftfreq(n, 1.0 / SR), 1.0)
    X = np.fft.rfft(x, axis=0)
    lo = 0.5 - 0.5 * np.tanh(np.log2(f / edges[0]) * 3.0)
    hi = 0.5 + 0.5 * np.tanh(np.log2(f / edges[1]) * 3.0)
    masks = [lo, 1.0 - lo - hi, hi]
    out = np.zeros_like(x)
    for m, d in zip(masks, depths_db):
        band = np.fft.irfft(X * m[:, None], n, axis=0)
        common = periodic_lfo(n, rng, cycles)
        for ch in range(2):
            g = db2lin(d * (0.75 * common + 0.45 * periodic_lfo(n, rng, cycles)))
            out[:, ch] += band[:, ch] * g
    return out


# ----------------------------------------------------------------------------- people

TALK_VOWELS = ["i", "I", "E", "ae", "a", "uh", "aw", "o", "U", "u", "er"]
LOCUS_LABIAL = np.array([290.0, 950.0, 2250.0, 3400.0, 4400.0])     # p b m w: everything pulled down
LOCUS_ALVEOLAR = np.array([300.0, 1750.0, 2650.0, 3400.0, 4400.0])  # t d n s l


def add_talkers(crowd, count, seconds, rng, level=1.0, r_min=14.0, r_max=70.0, tilt=(1500.0, 3500.0),
                pause=1.2, burst_amp=1.0):
    """People chatting: phrases of stressed and unstressed syllables with stops, fricatives and
    formant transitions between them, falling pitch over each phrase, pauses to breathe."""
    for _ in range(count):
        f0, scale = person(rng)
        names = rng.choice(TALK_VOWELS, size=4, replace=False)
        vowels = [vowel(nm, scale) for nm in names] + [LOCUS_LABIAL * scale, LOCUS_ALVEOLAR * scale]
        events = []
        start = rng.random() * seconds
        t = 0.0
        while t < seconds - 0.5:
            phrase = min(rng.uniform(0.7, 3.4), seconds - 0.35 - t)
            rate = rng.uniform(3.6, 5.8)
            tt = 0.0
            loud = np.exp(0.35 * rng.standard_normal())
            while tt < phrase:
                stressed = rng.random() < 0.42
                voiced = rng.uniform(0.75, 1.3) / rate * (1.15 if stressed else 0.8)
                kind = rng.random()
                frac = tt / max(phrase, 1e-3)
                base = 1.14 - 0.28 * frac + 0.05 * rng.standard_normal() + (0.07 if stressed else 0.0)
                ev = {"dur": voiced,
                      "f0": (base * rng.uniform(0.96, 1.03), base * rng.uniform(1.0, 1.12), base * rng.uniform(0.92, 1.02)),
                      "v": int(rng.integers(4)), "v2": int(rng.integers(4)),
                      "amp": loud * (rng.uniform(0.75, 1.0) if stressed else rng.uniform(0.25, 0.5)) * (1.0 - 0.3 * frac),
                      "att": rng.uniform(0.012, 0.03), "rel": rng.uniform(0.03, 0.06)}
                gap = 0.0
                if kind < 0.3:                       # stop: closure, then a burst
                    gap = rng.uniform(0.045, 0.085)
                    ev["cons"] = (int(rng.integers(2)), rng.uniform(0.018, 0.03), rng.uniform(0.5, 1.0) * burst_amp)
                    ev["locus"] = 4 + int(rng.integers(2))
                elif kind < 0.5:                     # fricative
                    gap = rng.uniform(0.05, 0.1)
                    ev["cons"] = (int(rng.integers(2)), gap + 0.01, rng.uniform(0.35, 0.8))
                    ev["locus"] = 5
                elif kind < 0.78:                    # nasal / glide: voiced all the way through
                    ev["locus"] = 4 + int(rng.integers(2))
                    ev["att"] = 0.035
                    gap = -0.02
                else:                                # vowel onset
                    gap = rng.uniform(0.0, 0.03)
                ev["t"] = start + t + tt + max(gap, 0.0)
                events.append(ev)
                tt += max(gap, 0.0) + voiced + min(gap, 0.0)
            t += tt + 0.3 + rng.exponential(pause)
        crowd.add_voice(events, vowels, f0, gain=level * distance_gain(rng, r_min, r_max),
                        pan=rng.uniform(-1, 1), tilt_hz=rng.uniform(*tilt), jitter=0.02,
                        breath=rng.uniform(0.04, 0.12), shimmer=0.08)


YELLS = [  # (vowel start, vowel end, weight)  -- "yeah", "woo", "aah", "go", "hey", "oh", "c'mon"
    ("E", "a", 3.0), ("u", "u", 2.0), ("a", "a", 3.0), ("o", "u", 1.5), ("e", "i", 1.5), ("aw", "o", 1.5), ("a", "aw", 1.0),
]


def add_yellers(crowd, count, seconds, rng, level=1.0, activity=None, r_min=12.0, r_max=65.0,
                first_burst=None, scream_prob=0.07, dur_scale=1.0, rough_prob=0.6, tilt=(4500.0, 9000.0),
                long_prob=0.5, burst_prob=0.35, breath=(0.08, 0.3), voicing=1.0, female_prob=0.38,
                pitch=(1.6, 2.3), effort=(0.5, 1.0), gap=0.45, yells=None, fall=(0.7, 0.98), burst_period=(0.24, 0.42)):
    """People cheering. Each person mixes long shouted vowels with an arching pitch, bursts of
    short shouts, and upward whoops; voices are rough, breathy and unsteady, as shouting is.

    activity(t) -> 0..1 thins the yelling over time (for one-shot cheers).
    first_burst = (time, spread): everybody's first yell starts around `time` (an eruption)."""
    yells = YELLS if yells is None else yells
    w = np.array([y[2] for y in yells])
    w /= w.sum()
    for _ in range(count):
        f0, scale = person(rng, female_prob)
        scream = rng.random() < scream_prob
        base = f0 * rng.uniform(*pitch)
        if scream:
            base = float(np.exp(rng.uniform(np.log(560.0), np.log(1050.0))))
        picks = rng.choice(len(yells), size=2, replace=False, p=w)
        names = []
        for p in picks:
            names += [yells[p][0], yells[p][1]]
        vowels = []
        for nm in names:
            fm = vowel(nm, scale, effort=rng.uniform(*effort))
            fm[0] = max(fm[0], base * 1.02)              # a shouted/sung vowel tunes F1 up to the pitch
            vowels.append(fm)
        vowels += [LOCUS_LABIAL * scale, np.array([300.0, 2150.0, 2900.0, 3400.0, 4400.0]) * scale]   # w-, y- onsets
        events = []
        if first_burst is not None:
            t = first_burst[0] + abs(rng.standard_normal()) * first_burst[1]
        else:
            t = -rng.random() * 1.5
        offset = rng.random() * seconds if first_burst is None else 0.0
        first = True
        while t < seconds - 0.3:
            act = 1.0 if activity is None else float(activity(max(t, 0.0)))
            style = rng.random()
            k = int(rng.integers(2))
            loud = np.exp(0.3 * rng.standard_normal()) * (0.4 + 0.6 * act)
            go = t >= 0 and rng.random() < act
            if style < long_prob or (first and first_burst is not None):    # one long yell
                dur = float(np.clip(np.exp(np.log(0.85) + 0.5 * rng.standard_normal()), 0.35, 2.6)) * dur_scale
                if first and first_burst is not None:
                    dur *= 1.5
                dur = min(dur, seconds - 0.25 - t)
                if dur < 0.2:
                    break
                if go:
                    events.append({"t": t + offset, "dur": dur,
                                   "f0": (rng.uniform(0.78, 0.95), rng.uniform(1.05, 1.3), rng.uniform(*fall)),
                                   "peak_at": rng.uniform(0.12, 0.45), "v": 2 * k, "v2": 2 * k + 1,
                                   "locus": 4 + int(rng.integers(2)), "amp": loud,
                                   "att": rng.uniform(0.025, 0.07), "rel": rng.uniform(0.1, 0.3) * min(dur, 1.0)})
                t += dur
            elif style < long_prob + burst_prob:                            # burst of short shouts
                reps = int(rng.integers(2, 6))
                period = rng.uniform(*burst_period)
                for i in range(reps):
                    d = period * rng.uniform(0.55, 0.8)
                    if t + d > seconds - 0.25:
                        break
                    if go:
                        ev = {"t": t + offset, "dur": d,
                              "f0": (rng.uniform(0.9, 1.0), rng.uniform(1.02, 1.18), rng.uniform(0.8, 0.95)),
                              "peak_at": 0.25, "v": 2 * k, "v2": 2 * k + (i % 2), "amp": loud * rng.uniform(0.7, 1.0),
                              "att": 0.02, "rel": 0.05, "locus": 4 + int(rng.integers(2))}
                        if rng.random() < 0.5:
                            ev["cons"] = (int(rng.integers(2)), rng.uniform(0.02, 0.05), 0.6)
                        events.append(ev)
                    t += period
            else:                                                           # whoop: pitch leaps up
                dur = rng.uniform(0.3, 0.7)
                if t + dur > seconds - 0.25:
                    break
                if go:
                    events.append({"t": t + offset, "dur": dur, "f0": (0.9, rng.uniform(1.6, 2.1), rng.uniform(1.3, 1.9)),
                                   "peak_at": rng.uniform(0.5, 0.8), "v": 2 * k, "v2": 2 * k + 1, "amp": loud * 0.8,
                                   "att": 0.04, "rel": 0.12, "locus": 4})
                t += dur
            first = False
            t += 0.12 + rng.exponential(gap if activity is None else gap / max(act, 0.15))
        crowd.add_voice(events, vowels, base, gain=level * distance_gain(rng, r_min, r_max) * (0.6 if scream else 1.0),
                        pan=rng.uniform(-1, 1), tilt_hz=rng.uniform(*tilt), jitter=rng.uniform(0.02, 0.045),
                        vibrato=rng.uniform(0.0, 0.012), breath=rng.uniform(*breath),
                        rough=(rng.uniform(0.2, 0.7) if rng.random() < rough_prob else 0.0), shimmer=rng.uniform(0.08, 0.2),
                        voicing=voicing)


# ----------------------------------------------------------------------------- hands, whistles

def clap_grains(rng, count=48, tau=(0.0012, 0.003), broad=0.22, fc=(600.0, 3000.0), q=(2.0, 5.0),
                diffuse=0.0, hf=7000.0):
    """A set of single hand claps, one per "pair of hands".

    A clap is a few ms of noise (the air squeezed out between the palms) ringing in the cavity
    between the hands: cupped palms resonate low (~0.6-1 kHz), flat fingers-on-palm claps high
    (~2-3 kHz). diffuse adds a short dense cloud of reflections (seats, neighbours, roof)."""
    grains = []
    m = n_of(0.09)
    t = times(m)
    f = np.maximum(np.fft.rfftfreq(m, 1.0 / SR), 1.0)
    for _ in range(count):
        f0 = np.exp(rng.uniform(np.log(fc[0]), np.log(fc[1])))
        qq = rng.uniform(*q)
        burst = rng.standard_normal(m) * (1.0 - np.exp(-t / 0.00015)) * np.exp(-t / rng.uniform(*tau))
        res = 1.0 / np.sqrt(1.0 + (qq * (f / f0 - f0 / f)) ** 2)
        wide = broad * np.minimum(f / 1500.0, 1.0) / np.sqrt(1.0 + (f / hf) ** 4)
        g = np.fft.irfft(np.fft.rfft(burst) * (res + wide), m)
        if diffuse:
            cloud = rng.standard_normal(m) * np.exp(-t / 0.018) * (1.0 - np.exp(-t / 0.004))
            cloud = np.fft.irfft(np.fft.rfft(cloud) * res, m)
            g = g + diffuse * cloud * np.sqrt(np.sum(g ** 2) / np.sum(cloud ** 2))
        g *= np.exp(-t / 0.03)
        grains.append(g / np.sqrt(np.sum(g ** 2)))
    return grains


def applause(n, rng, clappers, loop, grains, density=1.0, r_min=6.0, r_max=60.0, rate=(2.8, 5.2)):
    """Stereo applause made of `clappers` people. Each person claps steadily at their own tempo
    (with human timing jitter), with their own hands (one of `grains`), level and position.
    density: scalar or per-sample curve 0..1 -- the chance that a person is clapping at that time."""
    dens = None if np.isscalar(density) else density
    seconds = n / SR
    per_grain = [[] for _ in grains]
    for _ in range(clappers):
        gi = int(rng.integers(len(grains)))
        period = 1.0 / rng.uniform(*rate)
        r = np.sqrt(r_min ** 2 + rng.random() * (r_max ** 2 - r_min ** 2))
        amp = r_min / r
        a = (rng.uniform(-1, 1) + 1.0) * np.pi / 4.0
        count = int(seconds / period) + 1
        steps = period * (1.0 + 0.06 * rng.standard_normal(count))
        tt = rng.random() * period + np.cumsum(steps) - steps[0]
        tt = tt[tt < seconds]
        if dens is None:
            if density < 1.0:                                 # people join in for a while, then rest
                on = np.sin(TAU * (tt / seconds * rng.integers(1, 4) + rng.random())) > 1.0 - 2.0 * density
                tt = tt[on]
        else:
            thresh = rng.random()                             # each person has their own enthusiasm
            tt = tt[dens[np.minimum((tt * SR).astype(int), n - 1)] > thresh]
        if len(tt) == 0:
            continue
        amps = amp * np.exp(0.17 * rng.standard_normal(len(tt)))
        per_grain[gi].append((tt, amps * np.cos(a), amps * np.sin(a)))
    out = np.zeros((n, 2))
    for g, items in zip(grains, per_grain):
        if not items:
            continue
        imp = np.zeros((n, 2))
        for tt, al, ar in items:
            pos = (tt * SR).astype(int) % n
            np.add.at(imp[:, 0], pos, al)
            np.add.at(imp[:, 1], pos, ar)
        out += convolve(imp, g, circular=True) if loop else pad_to(convolve(imp, g), n)
    return out


def whistles(n, rng, count, loop, window=None):
    """Finger whistles from the stands: a breathy sine that scoops up to 2.5-3.8 kHz and falls away."""
    tl = Timeline(n=n, loop=loop)
    for _ in range(count):
        dur = rng.uniform(0.25, 0.9)
        m = n_of(dur)
        u = np.arange(m) / m
        f_top = rng.uniform(2500, 3800)
        f_lo = f_top * rng.uniform(0.55, 0.8)
        shape = rng.integers(3)
        if shape == 0:     # up and hold
            f = f_lo + (f_top - f_lo) * np.minimum(u / 0.3, 1.0) ** 0.6
        elif shape == 1:   # up - down
            f = f_lo + (f_top - f_lo) * np.sin(np.pi * np.minimum(u * 1.15, 1.0)) ** 0.8
        else:              # two-tone "wheet-whoo"
            f = np.where(u < 0.45, f_top, f_top * 0.74) * (1 + 0.03 * np.sin(TAU * 2 * u))
        f = f * (1.0 + 0.004 * smooth_random(m, rng, 60.0, periodic=False))
        s = np.sin(TAU * np.cumsum(f) / SR)
        s += 0.12 * np.sin(2 * TAU * np.cumsum(f) / SR)
        env = np.minimum(u / 0.08, 1.0) * np.minimum((1 - u) / 0.2, 1.0)
        s *= env * (1.0 + 0.25 * smooth_random(m, rng, 25.0, periodic=False))
        t0 = rng.random() * n / SR if window is None else rng.uniform(*window)
        tl.add(s, at=t0, gain=distance_gain(rng, 15.0, 90.0) * rng.uniform(0.4, 1.0), pan_pos=rng.uniform(-1, 1))
    return tl.buf[:n]


# ----------------------------------------------------------------------------- the place

def stadium_ir(seed=11, rt60=2.6):
    """Open-air bowl: long, dark, slow-building diffuse tail (far stands) and no close walls."""
    return reverb_ir(rt60=rt60, seed=seed, pre_delay=0.045, lf_mult=1.2, hf_mult=0.32, build=0.06,
                     lowcut=70.0, highcut=6500.0, stereo=True)


def in_stadium(x, ir, wet_db, loop):
    w = convolve(x, ir, circular=loop)
    if not loop:
        w = pad_to(w, len(x))
    return x + w * db2lin(wet_db)


# ----------------------------------------------------------------------------- beds

# Voice recipes. Found by rendering variants and scoring them with two independent machine
# listeners (see README: "How the crowd was tuned"): short shouted bursts with gaps between them
# read as a crowd; long sustained yells read as sirens/engines, dense equal-level voices as a
# drone, and stationary noise as water -- so those are kept low in the mix.
# Random seeds per file. Several realisations of each were rendered and the one both listeners
# scored most crowd-like was kept (the choice is frozen here, so output is reproducible).
SEEDS = {"AMB_CrowdLow": 3, "AMB_CrowdHigh": 2, "AMB_Cheer_1": 1, "AMB_Cheer_2": 0, "AMB_Cheer_3": 1,
         "AMB_Ooh_1": 0, "AMB_Ooh_2": 0, "AMB_Boo": 0, "AMB_Chant": 0}

ROAR = dict(rough_prob=0.15, long_prob=0.25, burst_prob=0.7, scream_prob=0.04)
CALM = dict(rough_prob=0.1, long_prob=0.0, burst_prob=0.95, scream_prob=0.0, pitch=(1.4, 2.0),
            effort=(0.2, 0.6), tilt=(2000.0, 4500.0), gap=2.5)


def unit_rms_st(x):
    r = np.sqrt(np.mean(x ** 2))
    return x / r if r > 0 else x


def far_field(crowd, copies=3):
    """Thicken a rendered voice field into a distant wash: a few circularly shifted copies
    (channels swapped on alternate copies). Shifts keep the buffer periodic."""
    x = crowd.render()
    n = len(x)
    out = x.copy()
    for k in range(1, copies):
        y = np.roll(x, (k * n) // copies + 7919 * k, axis=0)
        out += y[:, ::-1] if k % 2 else y
    return out


def crowd_bed(name, seconds, excited, salt=None, **over):
    """Seamless crowd loop. excited=False: murmuring between plays; True: roaring.
    Every layer is rendered as one exact period, so the loop has no seam to hide."""
    rng = rng_for(name, SEEDS[name] if salt is None else salt)
    n = n_of(seconds)
    n -= n % 3
    T = n / SR
    ir = stadium_ir(seed=11)

    near = Crowd(T, rng, loop=True)
    far = Crowd(T, rng, loop=True)
    if excited:
        add_yellers(near, 150, T, rng, **ROAR)
        add_yellers(far, 170, T, rng, r_min=40.0, r_max=120.0, **{**ROAR, "tilt": (1500.0, 3000.0), "scream_prob": 0.0})
        far_db, noise_db, rev_db = -12.0, -20.0, -14.0
    else:
        add_yellers(near, over.get("near", 150), T, rng, **{**CALM, **over.get("calm", {})})
        add_yellers(far, 130, T, rng, r_min=40.0, r_max=120.0, **{**CALM, "tilt": (1200.0, 2500.0), "gap": 1.5})
        far_db, noise_db, rev_db = -18.0, -22.0, -16.0
    far_db, noise_db, rev_db = over.get("far_db", far_db), over.get("noise_db", noise_db), over.get("rev_db", rev_db)
    mix = unit_rms_st(breathe(near.render(), rng, depths_db=(0.8, 1.3, 1.6)))
    farv = lp(far_field(far), 2500.0, 2, circular=True)
    farv = unit_rms_st(convolve(farv, ir, circular=True))            # the far stands are all reverberant
    mix += breathe(farv, rng, depths_db=(1.0, 1.5, 1.5)) * db2lin(far_db)

    air = lp(stereo_noise(n, rng, LTAS_ROAR if excited else LTAS_MURMUR), 3500.0, 2, circular=True)
    mix += unit_rms_st(breathe(air, rng)) * db2lin(noise_db)

    if excited:
        grains = clap_grains(rng, **CLAP_SOFT)
        dens = np.clip(0.7 + 0.25 * periodic_lfo(n, rng, (1, 2, 3)), 0.25, 1.0)
        clap = applause(n, rng, 400, True, grains, density=dens, r_min=5.0, r_max=40.0)
        mix += unit_rms_st(clap) * db2lin(-14.0)
        mix += unit_rms_st(whistles(n, rng, int(2.3 * T), True)) * db2lin(-18.0)
    elif over.get("whistle", True):
        mix += unit_rms_st(whistles(n, rng, 3, True)) * db2lin(-32.0)
    mix = in_stadium(mix, ir, rev_db, loop=True)
    return hp(mix, 60.0, 2, circular=True)


CLAP_SOFT = dict(broad=0.05, hf=4000.0, tau=(0.003, 0.006))


def make_crowd_low():
    save("AMB_CrowdLow", crowd_bed("AMB_CrowdLow", 14.0, False), loop=True, lufs=-27.0)


def make_crowd_high():
    save("AMB_CrowdHigh", crowd_bed("AMB_CrowdHigh", 15.0, True), loop=True, lufs=-19.0)


# ----------------------------------------------------------------------------- reactions

def cheer(name, seconds, voices=170, tau=2.0, burst=(0.04, 0.11), clap_db=-13.0, whistle_count=7, bright=1.0, salt=None):
    """Eruption: everybody's first yell lands within a few tenths of a second, then the yelling
    thins out exponentially while applause (which starts a beat later) carries the tail."""
    rng = rng_for(name, SEEDS[name] if salt is None else salt)
    n = n_of(seconds)
    T = seconds
    ir = stadium_ir(seed=13, rt60=2.2)
    act = lambda t: float(np.exp(-max(t - 0.4, 0.0) / tau))                    # noqa: E731
    recipe = {**ROAR, "long_prob": 0.4, "burst_prob": 0.55, "tilt": (4500.0 * bright, 9000.0 * bright)}
    near = Crowd(T, rng, loop=False)
    add_yellers(near, voices, T, rng, activity=act, first_burst=burst, **recipe)
    far = Crowd(T, rng, loop=False)
    add_yellers(far, voices, T, rng, activity=act, first_burst=(burst[0] + 0.1, burst[1] * 1.6), r_min=40.0, r_max=120.0,
                **{**recipe, "tilt": (1500.0, 3000.0), "scream_prob": 0.0})
    t = times(n)
    swell = np.minimum(t / 0.3, 1.0) ** 1.5 * np.exp(-np.maximum(t - 0.4, 0.0) / (tau * 1.25))
    mix = unit_rms_st(pad_to(near.render(), n))
    farv = unit_rms_st(pad_to(convolve(lp(pad_to(far.render(), n), 2500.0, 2), ir), n))
    mix += farv * db2lin(-10.0)
    air = stereo_noise(n, rng, LTAS_ROAR) * swell[:, None]
    mix += air / np.sqrt(np.mean(air ** 2)) * db2lin(-19.0) * np.sqrt(np.mean(swell ** 2))
    grains = clap_grains(rng, **CLAP_SOFT)
    dens = np.clip((t - 0.1) / 0.35, 0.0, 1.0) * np.exp(-np.maximum(t - 0.6, 0.0) / (tau * 1.8))
    clap = applause(n, rng, 450, False, grains, density=dens, r_min=5.0, r_max=40.0)
    mix += unit_rms_st(clap) * db2lin(clap_db)
    if whistle_count:
        mix += unit_rms_st(whistles(n, rng, whistle_count, False, window=(0.3, min(3.0, T - 1.2)))) * db2lin(-19.0)
    mix = pad_to(in_stadium(mix, ir, -12.0, loop=False), n)
    # one overall dynamic so the eruption really does peak early and die away
    shape = env_points(n, [(0.0, 0.0), (0.1, 0.6), (0.28, 1.0), (0.45, 0.97), (0.9, 0.74), (T * 0.5, 0.42), (T - 0.6, 0.14), (T, 0.0)])
    return hp(mix * shape[:, None], 60.0, 2)


BOO_VOWELS = [("u", "u", 3.0), ("U", "u", 2.0), ("o", "u", 2.0), ("aw", "o", 1.0)]
BOO = dict(rough_prob=0.45, long_prob=0.62, burst_prob=0.33, scream_prob=0.0, pitch=(0.95, 1.55), effort=(0.1, 0.45),
           tilt=(1500.0, 3200.0), yells=BOO_VOWELS, fall=(0.62, 0.82), dur_scale=1.35, breath=(0.15, 0.45),
           burst_period=(0.4, 0.7), gap=0.2, female_prob=0.25)


def reaction(name, seconds, kind, salt=None, boo=None, extra_db=-9.0, jeer_db=0.0, long_db=-9.0):
    """Collective reactions: "OOOH!" at a big hit, "BOO" at a bad call."""
    rng = rng_for(name, SEEDS[name] if salt is None else salt)
    n = n_of(seconds)
    T = seconds
    ir = stadium_ir(seed=17, rt60=2.0)
    near = Crowd(T, rng, loop=False)
    far = Crowd(T, rng, loop=False)
    if kind == "boo":
        # Booing is cheering turned sour: the same crowd machinery, but low, dark, closed vowels
        # ("oo"), long falling notes and slow repeated "boo! boo!" jeers. Scattered pitches and
        # restarts keep the mass from fusing into a single fog-horn note.
        act = lambda t: 1.0                                                   # noqa: E731
        recipe = {**BOO, **(boo or {})}
        add_yellers(near, 190, T, rng, activity=act, first_burst=(0.05, 0.3), **recipe)
        add_yellers(far, 170, T, rng, activity=act, first_burst=(0.15, 0.4), r_min=40.0, r_max=120.0,
                    **{**recipe, "tilt": (1100.0, 2200.0)})
    else:
        for crowd, count, lag, rr in ((near, 190, 0.0, (12.0, 65.0)), (far, 170, 0.09, (40.0, 120.0))):
            for _ in range(count):
                f0, scale = person(rng, female_prob=0.3)
                base = f0 * rng.uniform(1.35, 1.9)
                names = ("o", "u") if kind == "ooh" else ("aw", "o")
                vw = [vowel(names[0], scale, 0.35), vowel(names[1], scale, 0.2), np.array([300.0, 900.0, 2300.0, 3400.0, 4400.0]) * scale]
                for fm in vw:
                    fm[0] = max(fm[0], base * 1.02)
                dur = rng.uniform(0.75, 1.25) * (1.0 if kind == "ooh" else 1.15)
                ev = [{"t": 0.03 + lag + abs(rng.standard_normal()) * 0.07, "dur": min(dur, T - 0.35),
                       "f0": (rng.uniform(0.95, 1.05), rng.uniform(1.08, 1.2), rng.uniform(0.62, 0.8)),
                       "peak_at": rng.uniform(0.1, 0.22), "v": 0, "v2": 1, "amp": np.exp(0.3 * rng.standard_normal()),
                       "att": rng.uniform(0.04, 0.09), "rel": rng.uniform(0.3, 0.55), "locus": 2}]
                crowd.add_voice(ev, vw, base, gain=distance_gain(rng, *rr), pan=rng.uniform(-1, 1),
                                tilt_hz=rng.uniform(1800, 3800), jitter=0.02, breath=rng.uniform(0.06, 0.2), shimmer=0.1)
    mix = unit_rms_st(pad_to(near.render(), n))
    if kind == "boo":
        # ...under the long boos, the restless part of the crowd: short repeated "boo! boo!" jeers.
        jeers = Crowd(T, rng, loop=False)
        add_yellers(jeers, 150, T, rng, activity=lambda t: 1.0, first_burst=(0.05, 0.3),
                    **{**ROAR, "yells": BOO_VOWELS, "pitch": (1.3, 1.9), "effort": (0.3, 0.7), "fall": (0.6, 0.8),
                       "scream_prob": 0.0, "burst_period": (0.35, 0.6)})
        mix = mix * db2lin(long_db) + unit_rms_st(pad_to(jeers.render(), n)) * db2lin(jeer_db)
    if kind != "boo" and extra_db > -40:
        # not everybody goes "ooh": some shout and whoop at the hit, which is what makes it a crowd
        others = Crowd(T, rng, loop=False)
        add_yellers(others, 70, T, rng, activity=lambda t: float(np.exp(-t / 0.5)), first_burst=(0.03, 0.08),
                    **{**ROAR, "long_prob": 0.2, "burst_prob": 0.75, "dur_scale": 0.6})
        mix += unit_rms_st(pad_to(others.render(), n)) * db2lin(extra_db)
    farv = unit_rms_st(pad_to(convolve(lp(pad_to(far.render(), n), 2500.0, 2), ir), n))
    mix += farv * db2lin(-8.0)
    if kind == "boo":
        air = stereo_noise(n, rng, LTAS_MURMUR)
        mix += air / np.sqrt(np.mean(air ** 2)) * db2lin(-20.0)
        mix += unit_rms_st(whistles(n, rng, 4, False, window=(0.4, T - 1.2))) * db2lin(-24.0)
    mix = pad_to(in_stadium(mix, ir, -11.0, loop=False), n)
    if kind == "boo":
        shape = env_points(n, [(0.0, 0.0), (0.25, 0.5), (0.7, 1.0), (1.7, 0.95), (T - 0.5, 0.3), (T, 0.0)])
    else:
        shape = env_points(n, [(0.0, 0.0), (0.1, 1.0), (0.6, 1.0), (T - 0.5, 0.35), (T, 0.0)])
    return hp(mix * shape[:, None], 60.0, 2)


# ----------------------------------------------------------------------------- chant

def stomp_grains(rng, count=24):
    """One foot coming down on a grandstand: a dull, noisy low thump (the deck flexing) and the
    rattle of the aluminium plank. Mostly band-limited noise -- a clean sine here sounds like a
    kick drum, and a crowd is not a drum kit."""
    grains = []
    m = n_of(0.4)
    t = times(m)
    f = np.maximum(np.fft.rfftfreq(m, 1.0 / SR), 1.0)
    for _ in range(count):
        f_lo = rng.uniform(50.0, 110.0)
        low = np.fft.irfft(np.fft.rfft(rng.standard_normal(m)) / np.sqrt(1.0 + (2.2 * (f / f_lo - f_lo / f)) ** 2), m)
        g = low / np.max(np.abs(low)) * np.exp(-t / rng.uniform(0.05, 0.1))
        g += 0.35 * np.sin(TAU * f_lo * t) * np.exp(-t / 0.05)
        for _k in range(5):
            fm = rng.uniform(160.0, 900.0)
            g += rng.uniform(0.1, 0.3) * np.sin(TAU * fm * t + rng.random() * 6.28) * np.exp(-t / rng.uniform(0.015, 0.06))
        thump = lp(rng.standard_normal(m), 1400.0, 2) * np.exp(-t / 0.015)
        g += 0.6 * thump / np.max(np.abs(thump))
        g *= 1.0 - np.exp(-t / 0.003)
        grains.append(g / np.sqrt(np.sum(g ** 2)))
    return grains


def chant(salt=None):
    """Stomp-stomp-clap(-clap) with a shouted "HEY!" on four, eight bars, seamless."""
    spec = catalog.CHANT
    rng = rng_for("AMB_Chant", SEEDS["AMB_Chant"] if salt is None else salt)
    beat = 60.0 / spec["bpm"]
    n = n_of(spec["bars"] * 4 * beat)
    n -= n % 3
    T = n / SR
    beat = T / (spec["bars"] * 4)
    ir = stadium_ir(seed=19, rt60=1.9)
    stomps, claps, heys = [], [], []
    for bar in range(spec["bars"]):
        b0 = bar * 4 * beat
        stomps += [b0, b0 + beat]
        claps += [b0 + 2 * beat]
        if bar % 4 == 3:
            claps += [b0 + 2.5 * beat]
            heys += [(b0 + 3 * beat, 1.0), (b0 + 3.5 * beat, 0.85)]       # "HEY! HEY!" turnaround
        else:
            heys += [(b0 + 3 * beat, 1.0)]
    out = np.zeros((n, 2))

    def cloud(times_s, grains, people, sigma, r_min, r_max):
        buf = np.zeros((n, 2))
        for g in grains:
            imp = np.zeros((n, 2))
            k = max(people // len(grains), 1)
            for t0 in times_s:
                tt = t0 + sigma * rng.standard_normal(k) + 0.02          # (+20 ms: nobody is early)
                r = np.sqrt(r_min ** 2 + rng.random(k) * (r_max ** 2 - r_min ** 2))
                amp = (r_min / r) * np.exp(0.25 * rng.standard_normal(k))
                a = (rng.uniform(-1, 1, k) + 1.0) * np.pi / 4.0
                pos = (tt * SR).astype(int) % n
                np.add.at(imp[:, 0], pos, amp * np.cos(a))
                np.add.at(imp[:, 1], pos, amp * np.sin(a))
            buf += convolve(imp, g, circular=True)
        return buf

    st = cloud(stomps, stomp_grains(rng), 480, 0.042, 8.0, 60.0)
    cl = cloud(claps, clap_grains(rng, **CLAP_SOFT), 480, 0.032, 6.0, 50.0)
    crowd = Crowd(T, rng, loop=True)
    for _ in range(260):
        f0, scale = person(rng, female_prob=0.3)
        base = f0 * rng.uniform(1.5, 2.4)
        vw = [vowel("e", scale, 0.8), vowel("i", scale, 0.4)]
        for fm in vw:
            fm[0] = max(fm[0], base * 1.02)
        lagp = abs(rng.standard_normal()) * 0.03
        ev = []
        for t0, a in heys:
            if rng.random() < 0.9:
                ev.append({"t": t0 + lagp + 0.03 * rng.standard_normal(), "dur": rng.uniform(0.16, 0.26),
                           "f0": (rng.uniform(0.9, 1.0), rng.uniform(1.1, 1.3), rng.uniform(0.6, 0.8)), "peak_at": 0.2, "v": 0, "v2": 1,
                           "amp": a * np.exp(0.25 * rng.standard_normal()), "att": 0.015, "rel": 0.06, "cons": (0, 0.045, 0.6)})
        crowd.add_voice(ev, vw, base, gain=distance_gain(rng, 10.0, 60.0), pan=rng.uniform(-1, 1), tilt_hz=rng.uniform(4000, 8000),
                        jitter=0.04, breath=rng.uniform(0.2, 0.5), shimmer=0.15,
                        rough=(rng.uniform(0.2, 0.6) if rng.random() < 0.5 else 0.0))
    add_yellers(crowd, 60, T, rng, level=0.22, **CALM)             # the people who are not joining in
    hey = crowd.render()
    ref = np.sqrt(np.mean(st ** 2))
    out = st + cl * (ref / np.sqrt(np.mean(cl ** 2))) * db2lin(-3.0) + hey * (ref / np.sqrt(np.mean(hey ** 2))) * db2lin(-1.0)
    out = in_stadium(out, ir, -11.0, loop=True)
    out = hp(out, 38.0, 2, circular=True)
    # the stomps are far peakier than anything else in the game: rein them in (loop-safe limiter)
    out = out / np.sqrt(np.mean(out ** 2)) * db2lin(-21.0)
    return limiter(out, ceiling_db=-6.0, lookahead=0.004, circular=True)


# ----------------------------------------------------------------------------- night air

def night(seconds=10.0):
    """Empty-ish stadium at night: open air, distant city, the hum of the floodlights."""
    rng = rng_for("AMB_Night")
    n = n_of(seconds)
    air_mag = ltas([(20, -8), (40, 0), (120, -3), (400, -10), (1000, -17), (3000, -26), (8000, -36), (16000, -48)])
    air = breathe(stereo_noise(n, rng, air_mag, coherence_hz=120.0), rng, depths_db=(0.7, 0.9, 1.1), edges=(200.0, 1500.0))
    air = unit_rms_st(air)
    t = times(n)
    hum = np.zeros((n, 2))
    # 60 Hz mains: ballast/transformer hum is strongest at twice the line frequency. All partials
    # complete a whole number of cycles in 10 s, so the hum loops exactly.
    for f, a in ((60.0, 0.25), (120.0, 1.0), (180.0, 0.18), (240.0, 0.4), (360.0, 0.16), (480.0, 0.07)):
        for ch in range(2):
            drift = 1.0 + 0.2 * periodic_lfo(n, rng, (1, 2, 3))
            hum[:, ch] += a * drift * np.sin(TAU * f * t + rng.random() * 6.28)
    hum = unit_rms_st(hum)
    gust_mag = ltas([(60, -30), (150, -6), (350, 0), (800, -8), (2000, -24), (6000, -50)])
    gust = stereo_noise(n, rng, gust_mag, coherence_hz=300.0)
    g = np.clip(0.75 + 0.25 * periodic_lfo(n, rng, (1, 2, 3)), 0.3, None)
    gust = unit_rms_st(gust * g[:, None])
    return air + hum * db2lin(-10.0) + gust * db2lin(-11.0)


def make_cheers():
    save("AMB_Cheer_1", cheer("AMB_Cheer_1", 5.2, tau=1.9), lufs=-17.0, fade_out=0.3)
    save("AMB_Cheer_2", cheer("AMB_Cheer_2", 6.2, voices=200, tau=2.5, clap_db=-11.0, whistle_count=10), lufs=-17.0, fade_out=0.3)
    save("AMB_Cheer_3", cheer("AMB_Cheer_3", 4.6, voices=150, tau=1.5, burst=(0.03, 0.08), whistle_count=4, bright=1.15),
         lufs=-17.0, fade_out=0.3)


def make_reactions():
    save("AMB_Ooh_1", reaction("AMB_Ooh_1", 1.7, "ooh"), lufs=-18.0, fade_out=0.25)
    save("AMB_Ooh_2", reaction("AMB_Ooh_2", 1.95, "ohh"), lufs=-18.0, fade_out=0.25)
    save("AMB_Boo", reaction("AMB_Boo", 3.0, "boo"), lufs=-19.0, fade_out=0.3)


def make_chant():
    save("AMB_Chant", chant(), loop=True, lufs=-19.0)


def make_night():
    save("AMB_Night", night(), loop=True, lufs=-40.0)


JOBS = {
    "AMB_CrowdLow": make_crowd_low,
    "AMB_CrowdHigh": make_crowd_high,
    "AMB_Cheer": make_cheers,
    "AMB_Ooh AMB_Boo": make_reactions,
    "AMB_Chant": make_chant,
    "AMB_Night": make_night,
}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    print("Crowd / ambience")
    for name, fn in JOBS.items():
        if args and not any(a.lower() in name.lower() for a in args):
            continue
        fn()


if __name__ == "__main__":
    main()
