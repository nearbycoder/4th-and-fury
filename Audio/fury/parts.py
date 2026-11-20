"""Physical building blocks for sound effects: thuds, clacks, bursts, whooshes, crackle."""
import numpy as np

from .core import (SR, TAU, as_curve, contact, env_perc, lp, modal, n_of, shaped_noise, smooth_random,
                   sweep_filter, times, unit_peak)


def thud(n, f0, f1, tau_pitch, tau_amp, attack=0.0008):
    """Low body impact: a sine whose pitch drops from f0 to f1 (time constant tau_pitch) while it
    decays (tau_amp) -- the membrane/cavity "boom" of something heavy stopping suddenly."""
    t = times(n)
    f = f1 + (f0 - f1) * np.exp(-t / tau_pitch)
    ph = TAU * np.cumsum(f) / SR
    return np.sin(ph - ph[0]) * env_perc(n, attack, tau_amp)


def body_thud(n, rng, freqs=(85.0, 135.0, 205.0), q=5.0, soft_ms=2.0, noise=0.6, noise_band=(60.0, 320.0)):
    """A body or the ground taking a blow: heavily damped low resonances (Q of a few -- one or
    two cycles each, so no ringing pitch like a drum) plus a puff of low noise."""
    f = np.array(freqs) * rng.uniform(0.92, 1.08, len(freqs))
    taus = q / (np.pi * f)
    x = modal(n, f, taus, np.linspace(1.0, 0.6, len(f)), phases=np.linspace(0.0, 0.8, len(f)))
    x = unit_peak(x)
    if noise:
        x = x + noise * unit_peak(shaped_noise(n, rng, lo=noise_band[0], hi=noise_band[1]) * env_perc(n, 0.002, 2.0 * taus[0]))
    return unit_peak(contact(x, soft_ms))


def band_burst(n, rng, lo, hi, tau, attack=0.0005, tilt=0.0, hold=0.0):
    """Band-limited noise burst with a percussive envelope."""
    return shaped_noise(n, rng, tilt_db_oct=tilt, lo=lo, hi=hi) * env_perc(n, attack, tau, hold)


def clack(n, rng, f_lo, f_hi, modes=6, tau=(0.003, 0.012), noise=0.5, contact_ms=0.35, tilt=0.5, noise_lo=1500.0):
    """Hard shells colliding (shoulder pads, helmets): a handful of short-lived resonances
    between f_lo and f_hi plus the broadband click of the contact itself."""
    freqs = np.exp(rng.uniform(np.log(f_lo), np.log(f_hi), modes))
    taus = rng.uniform(tau[0], tau[1], modes) * (f_lo / freqs) ** 0.3
    amps = rng.uniform(0.4, 1.0, modes) * (freqs / f_lo) ** (-tilt)
    x = modal(n, freqs, taus, amps, phases=rng.uniform(0, TAU, modes))
    x = unit_peak(x)
    if noise:
        x = x + noise * unit_peak(band_burst(n, rng, noise_lo, 9000.0, 0.0018, 0.0002))
    x = contact(x, contact_ms)
    x *= 1.0 - np.exp(-times(n) / 0.0002)
    return unit_peak(x)


def swept_noise(n, rng, fc, q=2.0, tilt=0.0):
    """Noise through a band-pass whose centre follows fc (Hz, per sample): whooshes, scrapes."""
    return sweep_filter(shaped_noise(n, rng, tilt_db_oct=tilt), as_curve(fc, n), "bp", q=q)


def rough(n, rng, rate, depth=0.7):
    """Granular amplitude roughness (0..1 multiplier): friction, turf, cloth. Irregular on two
    time scales (slow catches and fast grit) so it reads as texture, not as a buzz."""
    r = np.abs(smooth_random(n, rng, rate, periodic=False)) * (0.6 + 0.4 * np.abs(smooth_random(n, rng, rate / 7.0, periodic=False)))
    return (1.0 - depth) + depth * np.minimum(r / 1.1, 1.0)


def vdelay(x, delay):
    """Read x through a time-varying delay (in samples, per-sample array) -- flanger/doppler."""
    idx = np.arange(len(x)) - as_curve(delay, len(x))
    return np.interp(idx, np.arange(len(x)), x, left=0.0, right=0.0)


def crackle(n, rng, rate, tau=(0.0004, 0.004), f=(1200.0, 7000.0), env=None, heavy=1.0, periodic=False):
    """Random pops (fire, sparks, bones): Poisson impulses, each a tiny decaying burst of
    band noise with a heavy-tailed loudness. env: optional per-sample rate multiplier."""
    out = np.zeros(n)
    count = rng.poisson(rate * n / SR)
    if env is None:
        pos = rng.integers(0, n, count)
    else:
        cdf = np.cumsum(np.maximum(env, 0.0))
        pos = np.searchsorted(cdf / cdf[-1], rng.random(count))
    amp = rng.pareto(2.2, count) * heavy + 0.2
    amp = np.minimum(amp, 6.0)
    for p, a in zip(pos, amp):
        m = int(rng.uniform(tau[0], tau[1]) * 6 * SR) + 8
        tt = np.arange(m) / SR
        fc = np.exp(rng.uniform(np.log(f[0]), np.log(f[1])))
        g = rng.standard_normal(m) * np.exp(-tt / (m / SR / 6.0))
        g = g - np.mean(g)
        k = max(int(SR / fc / 2), 1)
        g = np.convolve(g, np.ones(k) / k, mode="same")          # crude low-pass at the pop's own frequency
        g *= a
        if periodic:
            idx = (p + np.arange(m)) % n
            np.add.at(out, idx, g)
        else:
            e = min(p + m, n)
            out[p:e] += g[: e - p]
    return out


def pink_bed(n, rng, lo=None, hi=None, tilt=-3.0):
    return shaped_noise(n, rng, tilt_db_oct=tilt, lo=lo, hi=hi)


def one_pole_follow(x, tau):
    """Smooth a control signal with a one-pole low-pass (time constant tau seconds)."""
    return lp(x, 1.0 / (TAU * tau), 1)
