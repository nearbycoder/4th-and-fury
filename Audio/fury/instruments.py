"""Synthesised instruments for the music and the musical stingers.

Drums (kick, snare, toms, hats, crash, clap, timpani), a brass section, a Karplus-Strong
distorted guitar with a speaker-cabinet filter, bass, FM electric piano, organ, air horn.
Everything returns mono float arrays at SR unless noted.
"""
import numpy as np
from scipy import signal

from .core import (SR, TAU, as_curve, biquad, bp, circ_sos, contact, db2lin, env_adsr, env_perc, env_points, eq, hp,
                   lp, modal, n_of, pulse, saturate, saw, shaped_noise, sine, smooth_random, sweep_filter, times,
                   unit_peak)
from .parts import band_burst, thud

NOTE_INDEX = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(name):
    """'E2', 'F#3', 'Bb4' -> MIDI number (C4 = 60)."""
    if isinstance(name, (int, float)):
        return float(name)
    letter, rest = name[0].upper(), name[1:]
    acc = 0
    while rest and rest[0] in "#b":
        acc += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12.0 * (int(rest) + 1) + NOTE_INDEX[letter] + acc


def hz(name):
    return 440.0 * 2.0 ** ((midi(name) - 69.0) / 12.0)


# ----------------------------------------------------------------------------- drums

def kick(rng, dur=0.42, f0=160.0, f1=46.0, tp=0.026, ta=0.13, click=0.55, drive=7.0):
    """Rock kick: a fast pitch drop into a low thump, saturated, with the beater's click on top."""
    n = n_of(dur)
    body = thud(n, f0, f1, tp, ta) + 0.35 * thud(n, 85.0, 44.0, 0.05, ta * 1.5)
    body = saturate(unit_peak(body), drive)
    beater = band_burst(n, rng, 1800.0, 8000.0, 0.0035, 0.0002) + 0.6 * modal(n, [3300.0, 5100.0], [0.002, 0.0015], [1.0, 0.6])
    return unit_peak(body + click * unit_peak(beater))


def snare(rng, dur=0.42, tone=188.0, wires=1.0, crack=1.0, ring=0.07, room=0.0):
    """Snare: two shell/head modes that drop in pitch as the head relaxes, the buzz of the snare
    wires (broadband, 1-10 kHz), and the stick's crack. room adds a short dense "arena" bloom."""
    n = n_of(dur)
    t = times(n)
    glide = 1.0 + 0.25 * np.exp(-t / 0.012)
    body = modal(n, [tone, tone * 1.59, tone * 2.14, tone * 2.9], [ring, ring * 0.6, ring * 0.45, ring * 0.3],
                 [1.0, 0.55, 0.3, 0.2], f_curve=glide)
    wire = shaped_noise(n, rng, tilt_db_oct=-1.0, lo=1100.0, hi=11000.0) * (env_perc(n, 0.0006, 0.07) + 0.25 * env_perc(n, 0.004, 0.16))
    stick = band_burst(n, rng, 700.0, 7000.0, 0.004, 0.0002)
    x = 0.85 * unit_peak(body) + 0.8 * wires * unit_peak(wire) + 0.9 * crack * unit_peak(stick)
    x = saturate(unit_peak(x), 4.0)
    if room:
        rr = np.random.Generator(np.random.PCG64(777))
        m = n_of(0.3)
        ir = rr.standard_normal(m) * np.exp(-times(m) / 0.07) * (1 - np.exp(-times(m) / 0.004))
        ir = lp(hp(ir, 250.0, 2), 7000.0, 2)
        ir /= np.sqrt(np.sum(ir ** 2))
        wet = np.concatenate([signal.fftconvolve(x, ir), [0.0]])
        wet *= env_points(len(wet), [(0.0, 1.0), (0.22, 1.0), (0.3, 0.0), (len(wet) / SR, 0.0)])
        x = np.concatenate([x, np.zeros(m)]) + room * wet
    return x


def tom(rng, f=110.0, dur=0.5, ta=0.2):
    n = n_of(dur)
    t = times(n)
    body = thud(n, f * 1.45, f, 0.03, ta) + 0.35 * modal(n, [f * 1.5, f * 2.0], [ta * 0.5, ta * 0.35], [1.0, 0.6],
                                                         f_curve=1.0 + 0.3 * np.exp(-t / 0.03))
    hit = band_burst(n, rng, 500.0, 5000.0, 0.006, 0.0003)
    return saturate(unit_peak(unit_peak(body) + 0.45 * unit_peak(hit)), 4.0)


_HAT_F = np.array([205.3, 304.4, 369.6, 522.7, 540.0, 800.0])


def hat(rng, dur=0.08, tau=0.022, scale=9.0, bright=7000.0):
    """Cymbal-ish metal: six square waves at clashing ratios, high-passed -- the dense cluster
    of inharmonic partials a small cymbal gives -- plus a little noise."""
    n = n_of(dur)
    x = np.zeros(n)
    for f in _HAT_F * scale * (1.0 + 0.01 * rng.standard_normal(6)):
        x += pulse(f, n, width=0.5, start=rng.random())
    x = hp(x, bright, 4) + 0.5 * hp(rng.standard_normal(n), bright, 2) * 0.6
    return unit_peak(x * env_perc(n, 0.0004, tau))


def crash(rng, dur=2.2, tau=0.7):
    """Crash cymbal: a wash of dense inharmonic partials that starts bright and loses its top."""
    n = n_of(dur)
    t = times(n)
    x = np.zeros(n)
    for f in np.concatenate([_HAT_F * 5.3, _HAT_F * 8.9]) * (1.0 + 0.02 * rng.standard_normal(12)):
        x += pulse(f, n, width=0.5, start=rng.random())
    x = 0.5 * unit_peak(hp(x, 2500.0, 2)) + shaped_noise(n, rng, tilt_db_oct=1.0, lo=2500.0, hi=16000.0) * 0.5
    x = sweep_filter(x, 4500.0 + 12000.0 * np.exp(-t / (tau * 0.6)), "lp", q=0.7)
    return unit_peak(x * (env_perc(n, 0.001, tau) + 0.6 * env_perc(n, 0.001, 0.05)))


def clap(rng, dur=0.3):
    n = n_of(dur)
    x = np.zeros(n)
    for k, t0 in enumerate((0.0, 0.009, 0.019, 0.03)):
        b = band_burst(n_of(0.2), rng, 900.0, 4200.0, 0.006 if k < 3 else 0.07, 0.0003)
        i0 = n_of(t0)
        m = min(len(b), n - i0)
        x[i0:i0 + m] += b[:m] * (0.8 if k < 3 else 1.0)
    return unit_peak(x)


def shaker(rng, dur=0.09, tau=0.02):
    n = n_of(dur)
    return unit_peak(shaped_noise(n, rng, tilt_db_oct=2.0, lo=4500.0, hi=14000.0) * env_perc(n, 0.006, tau))


def timpani(rng, f=98.0, dur=1.6, tau=0.8):
    """Kettledrum: the tuned head modes (1 : 1.5 : 1.99 : 2.44 : 2.9) with a felt-mallet thump."""
    n = n_of(dur)
    t = times(n)
    ratios = np.array([1.0, 1.5, 1.99, 2.44, 2.9, 3.4])
    body = modal(n, f * ratios, tau * np.array([1.0, 0.75, 0.5, 0.35, 0.25, 0.18]), [1.0, 0.75, 0.45, 0.3, 0.2, 0.1],
                 f_curve=1.0 + 0.02 * np.exp(-t / 0.05))
    thump = band_burst(n, rng, 60.0, 600.0, 0.02, 0.002)
    return unit_peak(contact(unit_peak(body) + 0.5 * unit_peak(thump), 2.0))


# ----------------------------------------------------------------------------- brass

def brass(freq, dur, rng, vel=1.0, bright=1.0, vib=0.004, scoop=0.025, attack=None, release=0.05, fall=0.0,
          formant=1250.0, sustain=0.82, blat=1.0):
    """One brass player. The lips buzz a pulse-rich wave; the bore passes more harmonics the
    harder it is blown, so brightness follows loudness -- with an overshoot at the attack (the
    "blat") that settles, and a slow swell on long notes. Slight scoop into the pitch, delayed
    vibrato, breath in the attack, unsteady lips, and an optional fall."""
    n = n_of(dur + release)
    t = times(n)
    att = attack if attack is not None else 0.02 + 0.018 * (1.0 - vel)
    env = env_adsr(n, a=att, d=0.09, s=sustain, r=release, gate=dur)
    f = freq * (1.0 - scoop * np.exp(-t / 0.022))
    if vib:
        depth = vib * np.clip((t - 0.14) / 0.22, 0.0, 1.0)
        f = f * (1.0 + depth * np.sin(TAU * (5.3 + 0.5 * rng.random()) * t + rng.random() * 6.28))
    f = f * (1.0 + 0.003 * smooth_random(n, rng, 7.0, periodic=False) + 0.0015 * smooth_random(n, rng, 40.0, periodic=False))
    if fall:
        f = f * 2.0 ** (-fall * np.clip((t - dur * 0.55) / (dur * 0.45 + release), 0.0, 1.0) ** 1.6 / 12.0)
    ph0 = rng.random()
    src = 0.8 * saw(f, start=ph0) + 0.35 * pulse(f, width=0.24 + 0.05 * np.sin(TAU * 0.7 * t + rng.random() * 6.28), start=ph0)
    # brightness: overshoot at the attack, settle, then swell slowly if the note is long
    b_env = env * (1.0 + 0.55 * blat * np.exp(-np.maximum(t - att, 0.0) / 0.07))
    if dur > 0.5:
        b_env = b_env * (1.0 + 0.25 * np.clip((t - 0.25) / max(dur - 0.25, 0.1), 0.0, 1.0))
    cutoff = np.clip(freq * 1.3 + (1800.0 + 5200.0 * bright * vel) * b_env ** 1.5, 200.0, 15000.0)
    x = sweep_filter(src, cutoff, "lp", q=1.0, f_lo=150.0, f_hi=16000.0, n_bank=24)
    x = eq(x, [("peak", formant, 1.1, 5.0), ("peak", formant * 2.1, 1.4, 2.5), ("hp", max(freq * 0.6, 60.0), 0.7, 0.0)])
    x = x * env * (1.0 + 0.05 * smooth_random(n, rng, 25.0, periodic=False))
    x = saturate(x * 0.5, 4.0) * 1.2
    x += 0.09 * vel * band_burst(n, rng, 900.0, 5000.0, 0.02, 0.004)
    return x


def brass_section(freqs, dur, rng, vel=1.0, bright=1.0, players=2, spread=0.007, width=0.6, **kw):
    """Chord (or unison) played by a section: each note by `players` slightly detuned, slightly
    late players spread across the stereo field. Returns (n, 2)."""
    n = n_of(dur + kw.get("release", 0.05) + 0.03)
    out = np.zeros((n, 2))
    freqs = np.atleast_1d(freqs)
    for i, f in enumerate(freqs):
        low = f < 250.0
        for p in range(players):
            cents = rng.uniform(-7.0, 7.0)
            v = brass(f * 2.0 ** (cents / 1200.0), dur, rng, vel=vel * rng.uniform(0.9, 1.0),
                      bright=bright * (0.75 if low else 1.0), formant=650.0 if low else 1250.0, **kw)
            i0 = int(abs(rng.standard_normal()) * spread * SR)
            pos = (rng.uniform(-1, 1) * width) + (-0.25 if low else 0.2)
            a = (np.clip(pos, -1, 1) + 1.0) * np.pi / 4.0
            m = min(len(v), n - i0)
            out[i0:i0 + m, 0] += v[:m] * np.cos(a)
            out[i0:i0 + m, 1] += v[:m] * np.sin(a)
    return out / np.sqrt(max(len(freqs) * players, 1))


def air_horn(dur, rng, f=(466.0, 554.0), rough=0.16):
    """Hand-held air horn(s): a metal diaphragm chattering against its seat -- a harsh, pulse-like
    wave full of harmonics -- through a short flared horn that favours 1-3.5 kHz. The pitch sags
    as the can pressure drops and scoops up at the start."""
    n = n_of(dur + 0.08)
    t = times(n)
    env = env_points(n, [(0.0, 0.0), (0.025, 1.0), (dur, 0.92), (dur + 0.06, 0.0), (dur + 0.08, 0.0)])
    out = np.zeros(n)
    for f0 in f:
        fc = f0 * (1.0 - 0.07 * np.exp(-t / 0.03)) * (1.0 - 0.012 * t / max(dur, 0.1)) \
            * (1.0 + 0.004 * smooth_random(n, rng, 20.0, periodic=False))
        src = 0.7 * pulse(fc, width=0.22, start=rng.random()) + 0.5 * saw(fc * 1.003, start=rng.random())
        src *= 1.0 + rough * np.sin(TAU * np.cumsum(fc * 0.5) / SR + rng.random() * 6.28)
        out += src
    out = saturate(out * 0.6, 9.0, asym=0.3)
    out = eq(out, [("hp", 280.0, 0.8, 0.0), ("peak", 1500.0, 1.0, 6.0), ("peak", 2900.0, 1.4, 5.0), ("lp", 6500.0, 0.7, 0.0)])
    out += 0.05 * shaped_noise(n, rng, lo=1500.0, hi=8000.0)
    return unit_peak(out * env)


# ----------------------------------------------------------------------------- guitar

def ks_string(freq, dur, rng, decay=2.5, pick=0.17, bright=0.6, mute=0.0):
    """Karplus-Strong plucked string: a burst of noise circulating in a delay line one period
    long, losing a little (and its highs) on every trip. decay = seconds to fall 60 dB;
    pick = picking position along the string; mute (0..1) = palm on the bridge."""
    n = n_of(dur)
    period = SR / freq
    p_int = int(np.floor(period - 0.5))
    frac = period - 0.5 - p_int
    t60 = decay * (1.0 - 0.9 * mute)
    g = 10.0 ** (-3.0 * period / (SR * max(t60, 0.02)))
    burst = rng.standard_normal(p_int + 2)
    burst = lp(burst, 1500.0 + 6500.0 * bright * (1.0 - 0.7 * mute), 1)
    d = max(int(pick * period), 1)
    exc = np.zeros(n)
    exc[: len(burst)] += burst
    if d < n:
        exc[d: d + len(burst)] -= burst[: max(min(len(burst), n - d), 0)]
    a = np.zeros(p_int + 3)
    a[0] = 1.0
    blend = 0.5 + 0.3 * mute                                  # loop low-pass: average of neighbours
    taps = np.array([(1 - frac) * (1 - blend), (1 - frac) * blend + frac * (1 - blend), frac * blend])
    a[p_int: p_int + 3] -= g * taps / taps.sum()
    y = signal.lfilter([1.0], a, exc)
    return y * env_points(n, [(0.0, 1.0), (max(dur - 0.012, 0.001), 1.0), (dur, 0.0)])


def cabinet(x, circular=False):
    """Guitar speaker cabinet: no deep bass, a chesty bump, an upper-mid bite, nothing above ~5 kHz."""
    sos = np.vstack([
        signal.butter(2, 75.0 / (SR / 2), btype="high", output="sos"),
        biquad("peak", 115.0, 1.0, 3.0),
        biquad("peak", 420.0, 1.2, -3.5),
        biquad("peak", 2700.0, 1.4, 5.0),
        signal.butter(4, 4700.0 / (SR / 2), btype="low", output="sos"),
    ])
    return circ_sos(x, sos) if circular else signal.sosfilt(sos, x, axis=0)


def amp(x, gain_db=30.0, circular=False):
    """Distortion amp: tighten the lows, push the mids, clip hard (asymmetric), then the cabinet."""
    pre = np.vstack([signal.butter(2, 110.0 / (SR / 2), btype="high", output="sos"), biquad("peak", 850.0, 0.8, 6.0)])
    y = circ_sos(x, pre) if circular else signal.sosfilt(pre, x, axis=0)
    y = y / max(np.sqrt(np.mean(y ** 2)), 1e-9) * 0.12
    y = saturate(y, gain_db, asym=0.25)
    y = np.tanh(1.5 * y)
    return cabinet(y, circular=circular)


def power_chord(root, dur, rng, mute=0.0, decay=2.8, detune=0.0):
    """Root + fifth + octave on three strings (dry; run the whole take through amp())."""
    f = root * 2.0 ** (detune / 1200.0)
    out = ks_string(f, dur, rng, decay=decay, mute=mute)
    out += 0.9 * ks_string(f * 1.4983, dur, rng, decay=decay * 0.9, mute=mute)
    if not mute:
        out += 0.7 * ks_string(f * 2.0, dur, rng, decay=decay * 0.8, mute=mute)
    return out


# ----------------------------------------------------------------------------- bass, keys

def bass_note(freq, dur, rng, pluck=1.0, drive=5.0, release=0.03):
    """Electric bass-ish synth: saw + pulse with a bright pluck that decays to a round body, over a sine sub."""
    n = n_of(dur + release)
    env = env_adsr(n, a=0.004, d=0.12, s=0.75, r=release, gate=dur)
    src = saw(freq, n, start=rng.random()) + 0.6 * pulse(freq, n, width=0.35, start=rng.random())
    body = lp(src, min(freq * 4.0, 420.0), 2)
    bite = lp(src, 2200.0, 2) * env_perc(n, 0.002, 0.07) * pluck
    x = saturate(0.8 * unit_peak(body + 0.7 * bite), drive) + 0.55 * sine(freq, n)
    return x * env


def epiano(freq, dur, rng, vel=0.8, release=0.25):
    """FM electric piano: a tine (bright, quickly dying bell partial) over a mellow tone bar whose
    brightness follows how hard the key was struck."""
    n = n_of(dur + release)
    t = times(n)
    env = env_adsr(n, a=0.003, d=0.9, s=0.35, r=release, gate=dur) * (220.0 / max(freq, 110.0)) ** 0.15
    idx = (0.35 + 2.4 * vel) * np.exp(-t / 0.5) + 0.25
    mod = idx * np.sin(TAU * freq * t)
    tine = 0.5 * vel * np.exp(-t / 0.06) * np.sin(TAU * freq * 14.0 * t)
    x = np.sin(TAU * freq * t + mod + tine)
    x += 0.25 * np.sin(TAU * 2.0 * freq * t + 0.5 * mod) * np.exp(-t / 0.4)
    return x * env


def organ(freq, dur, rng, bars=(0.6, 0.5, 1.0, 0.7, 0.0, 0.35, 0.0, 0.0, 0.2), release=0.03, click=0.3):
    """Drawbar organ (16', 5 1/3', 8', 4', 2 2/3', 2', 1 3/5', 1 1/3', 1') with key click."""
    n = n_of(dur + release)
    t = times(n)
    ratios = (0.5, 1.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0)
    x = np.zeros(n)
    for r, b in zip(ratios, bars):
        if b and freq * r < 0.45 * SR:
            x += b * np.sin(TAU * freq * r * t + rng.random() * 6.28)
    env = env_adsr(n, a=0.004, d=0.01, s=1.0, r=release, gate=dur)
    x = x * env + click * band_burst(n, rng, 1500.0, 6000.0, 0.004, 0.0003)
    return x


def lead(freq, dur, rng, vel=1.0, glide_from=None, release=0.06, vib=0.006):
    """Singing synth lead: two detuned saws and a pulse through a resonant low-pass, with glide."""
    n = n_of(dur + release)
    t = times(n)
    f = np.full(n, float(freq))
    if glide_from:
        f = freq * (glide_from / freq) ** np.exp(-t / 0.03)
    f = f * (1.0 + vib * np.clip((t - 0.12) / 0.2, 0, 1) * np.sin(TAU * 5.8 * t))
    src = saw(f, start=rng.random()) + saw(f * 1.006, start=rng.random()) + 0.5 * pulse(f * 0.5, width=0.4)
    env = env_adsr(n, a=0.008, d=0.1, s=0.8, r=release, gate=dur)
    cutoff = np.clip(900.0 + 4200.0 * vel * env ** 1.3, 300.0, 9000.0)
    x = sweep_filter(src, cutoff, "lp", q=2.2, f_lo=200.0, f_hi=12000.0, n_bank=22)
    return saturate(x * 0.4, 6.0) * env


def bell(freq, dur, rng, tau=0.5):
    """Glockenspiel-like bar: bright, slightly inharmonic, long ring."""
    n = n_of(dur)
    return modal(n, [freq, freq * 2.756, freq * 5.404, freq * 8.933], [tau, tau * 0.45, tau * 0.25, tau * 0.12],
                 [1.0, 0.45, 0.25, 0.12]) * (1.0 - np.exp(-times(n) / 0.0006))
