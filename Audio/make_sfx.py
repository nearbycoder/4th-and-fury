# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1"]
# ///
"""4th & Fury -- sound effects (SFX_*.wav).

    uv run Audio/make_sfx.py [football | fury | interface | stingers]

Every sound is assembled from the parts the real thing is made of (the crack of plastic shells,
the thud of a body, leather on skin, air through a pea whistle ...) rather than from bare
oscillator sweeps. Levels are set by perceived loudness (loudest 100 ms, K-weighted), not by
peak, so the set is roughly pre-mixed: big hits loud, footsteps and UI ticks quiet.
"""
import sys

import numpy as np

from fury.core import (SR, TAU, Timeline, bp, contact, convolve, db2lin, echo, env_adsr, env_perc, env_points, eq,
                       fade, harmonics, hp, limiter, lp, modal, n_of, pad_to, pan, periodic_lfo, place, pulse,
                       resample, reverb, reverb_ir, rng_for, saturate, saw, shaped_noise, sine, smooth_random, sweep_filter,
                       times, to_stereo, triangle, unit_peak, unit_rms)
from fury.parts import band_burst, body_thud, clack, crackle, rough, swept_noise, thud, vdelay
from fury.wavio import save
from fury import instruments as ins


# ============================================================================= football

def hit(name, weight=1.0, bright=1.0, clacks=3, dur=0.4, spread=1.0):
    """Pads on pads. Hard plastic shells crack together (1-5 kHz, a few ms each, two or three
    contacts as the pads rattle); the bodies behind them give a dull, heavily damped thud
    (80-220 Hz, a cycle or two -- flesh does not ring like a drum) and the foam a mid "whump";
    a moment later both players hit the turf and the gear settles."""
    rng = rng_for(name)
    n = n_of(dur)
    out = np.zeros(n)
    t_c = 0.0
    for k in range(clacks):
        c = clack(n_of(0.07), rng, 850.0 * bright, 5200.0 * bright, modes=7, tau=(0.003, 0.011), noise=0.6)
        out += place(n, [(c, t_c, 0.95 * 0.62 ** k)])
        t_c += rng.uniform(0.006, 0.018) * spread
    low = body_thud(n_of(0.2), rng, freqs=(82.0 / weight ** 0.4, 128.0 / weight ** 0.4, 196.0), q=5.5 * weight, soft_ms=1.5)
    out += place(n, [(low, 0.0, 1.15 * weight)])
    out += 0.7 * weight * band_burst(n, rng, 150.0, 900.0, 0.024 * weight, attack=0.002)
    t_g = rng.uniform(0.11, 0.17)                          # ... and down they go
    ground = body_thud(n_of(0.2), rng, freqs=(70.0, 112.0, 160.0), q=4.5 * weight, soft_ms=4.0, noise=0.9)
    out += place(n, [(ground, t_g, 0.5 * weight)])
    scuff = shaped_noise(n_of(0.16), rng, tilt_db_oct=-3.0, lo=700.0, hi=6000.0) * rough(n_of(0.16), rng, 60.0, 0.6)
    out += place(n, [(scuff * env_perc(len(scuff), 0.01, 0.04), t_g, 0.16)])
    for k in range(4):                                     # gear settling
        c = clack(n_of(0.04), rng, 1500.0, 6000.0, modes=4, tau=(0.002, 0.006), noise=0.8)
        out += place(n, [(c, rng.uniform(0.03, 0.22), 0.15 * 0.75 ** k)])
    return saturate(unit_peak(out), 5.0)


def big_hit(name, dur=0.9, crunch=1.0, ring=1.0, double=False):
    """The arcade hit: the same collision, exaggerated -- a saturated sub boom with a rumble of
    low noise, a blast that closes down like an explosion, a crunch of many small cracks, a
    helmet ringing and the air rushing out."""
    rng = rng_for(name)
    n = n_of(dur)
    t0 = 0.085 if double else 0.0
    out = np.zeros(n)
    if double:                                             # the first contact, then the real one
        pre = hit(name + "pre", weight=0.8, clacks=2, dur=0.2)
        out += place(n, [(pre, 0.0, 0.5)])
    m = n - n_of(t0)
    tt = times(m)
    boom = thud(m, 150.0, 38.0, 0.04, 0.16) + 0.5 * thud(m, 230.0, 74.0, 0.03, 0.08)
    rumble = shaped_noise(m, rng, tilt_db_oct=-6.0, lo=28.0, hi=160.0) * env_perc(m, 0.004, 0.2)
    boom = saturate(unit_peak(unit_peak(boom) + 0.8 * unit_peak(rumble)), 10.0)
    blast = sweep_filter(rng.standard_normal(m), 7500.0 * np.exp(-tt / 0.06) + 260.0, "lp", q=0.8)
    blast = unit_peak(blast * env_perc(m, 0.001, 0.11))
    shell = clack(n_of(0.1), rng, 480.0, 3200.0, modes=8, tau=(0.006, 0.02), noise=0.7)
    grit = np.zeros(m)
    for k in range(18):
        c = clack(n_of(0.05), rng, 600.0, 4200.0, modes=5, tau=(0.004, 0.012), noise=1.0)
        tk = rng.uniform(0.004, 0.24)
        grit += place(m, [(c, tk, rng.uniform(0.3, 1.0) * np.exp(-tk / 0.12))])
    freqs = np.sort(rng.uniform(700.0, 4200.0, 6))
    ringing = modal(m, freqs, rng.uniform(0.1, 0.28, 6), rng.uniform(0.4, 1.0, 6) / (freqs / 700.0) ** 0.6,
                    phases=rng.uniform(0, TAU, 6)) * (1.0 - np.exp(-tt / 0.004))
    air_fc = np.interp(tt, [0.0, 0.08, 0.5, dur], [600.0, 2600.0, 700.0, 350.0])
    air = swept_noise(m, rng, air_fc, q=1.1) * env_points(m, [(0.0, 0.0), (0.07, 0.4), (0.22, 1.0), (dur - 0.1, 0.0)])
    core = 1.0 * boom + 0.85 * blast + 0.8 * place(m, [(shell, 0.0, 1.0)]) + 0.6 * crunch * unit_peak(grit) \
        + 0.14 * ring * unit_peak(ringing) + 0.24 * unit_peak(air)
    out += place(n, [(core, t0, 1.0)])
    out = saturate(unit_peak(out), 7.0)
    wet = reverb(out, reverb_ir(0.55, seed=31, pre_delay=0.012, hf_mult=0.5, stereo=False), wet_db=-15.0)
    return wet[:n]


def dive(name, dur=0.4, slide=1.0, bump=False):
    """A body landing and sliding on turf: a soft, dead thud (bodies have no hard edges, so
    little high end), then the gritty hiss of fabric dragging over plastic grass and rubber crumb."""
    rng = rng_for(name)
    n = n_of(dur)
    out = place(n, [(body_thud(n_of(0.2), rng, freqs=(68.0, 104.0, 150.0), q=4.5, soft_ms=5.0, noise=0.9), 0.0, 1.0)])
    out += 0.5 * band_burst(n, rng, 130.0, 700.0, 0.03, 0.004)
    if bump:
        out += place(n, [(body_thud(n_of(0.15), rng, freqs=(90.0, 140.0), q=4.0, soft_ms=4.0), 0.11, 0.5)])
    env = env_points(n, [(0.0, 0.0), (0.03, 1.0), (0.12, 0.7 * slide), (dur - 0.03, 0.04), (dur, 0.0)])
    scrape = shaped_noise(n, rng, tilt_db_oct=-4.0, lo=900.0, hi=6500.0) * rough(n, rng, 45.0, 0.55)
    cloth = shaped_noise(n, rng, tilt_db_oct=-2.0, lo=280.0, hi=1300.0) * rough(n, rng, 25.0, 0.5)
    out += (0.5 * scrape + 0.4 * cloth) * env
    return unit_peak(out)


def throw(name, dur=0.25, speed=1.0):
    """Pass release: the arm cutting through the air -- a band of noise that swells, sweeps up
    and falls away. No hard onset: air has none."""
    rng = rng_for(name)
    n = n_of(dur)
    t = times(n)
    u = t / dur
    fc = np.interp(u, [0.0, 0.45, 1.0], [420.0 * speed, 2300.0 * speed, 1000.0 * speed])
    env = np.sin(np.pi * u) ** 2.0 * (0.6 + 0.4 * np.sin(np.pi * u ** 0.7))
    out = swept_noise(n, rng, fc, q=1.8) * env
    out += 0.3 * swept_noise(n, rng, fc * 2.6, q=1.3) * env ** 2
    return unit_peak(out)


def ball_air(dur=1.0, flutter_depth=0.06):
    """A spiral in flight, loopable: a soft rush of air with a breathy whistle over the laces
    that flutters very slightly at the spin rate (12 turns a second; any deeper and it turns
    into a helicopter). Built from periodic noise and
    whole-cycle modulators, so the loop point is not a point at all."""
    rng = rng_for("SFX_BallAir")
    n = n_of(dur)
    t = np.arange(n) / n

    def band(fc, q):
        return shaped_noise(n, rng, mag=lambda f: 1.0 / np.sqrt(1.0 + (q * (f / fc - fc / f)) ** 2))

    spin = 12
    flutter = 1.0 + flutter_depth * np.sin(TAU * spin * t) + 0.4 * flutter_depth * np.sin(TAU * 2 * spin * t + 1.1) \
        + 0.08 * periodic_lfo(n, rng, (3, 5, 7))
    wob = 0.5 + 0.5 * np.sin(TAU * 2 * t + 0.4)
    out = 0.7 * band(1900.0, 3.0) * flutter * (0.45 + 0.55 * wob)
    out += 0.6 * band(2800.0, 4.0) * flutter * (1.0 - 0.55 * wob)
    out += 0.9 * shaped_noise(n, rng, tilt_db_oct=-4.0, lo=350.0, hi=7000.0) * (1.0 + 0.15 * np.sin(TAU * 3 * t + 2.0))
    return out


def catch(name, dur=0.2, snap=1.0, body=1.0):
    """Ball into gloves: two hands slap leather a few ms apart -- a bright, dry smack of noise --
    and the ball answers with a short hollow "pock" as the arms absorb it."""
    rng = rng_for(name)
    n = n_of(dur)
    out = np.zeros(n)
    gap = rng.uniform(0.007, 0.014)
    for tk, a in ((0.0, 1.0), (gap, 0.65)):
        s = band_burst(n_of(0.08), rng, 700.0 * snap, 6500.0, rng.uniform(0.009, 0.014), 0.0003, tilt=-3.0)
        out += place(n, [(contact(s, 0.5), tk, a)])
    f_ball = rng.uniform(390.0, 520.0)
    pock = modal(n, [f_ball, f_ball * 2.35, f_ball * 3.6], [0.009, 0.006, 0.004], [1.0, 0.5, 0.25])
    out += 0.5 * body * pock * (1.0 - np.exp(-times(n) / 0.0006))
    out += place(n, [(body_thud(n_of(0.1), rng, freqs=(150.0, 240.0), q=3.0, soft_ms=1.5, noise=0.8, noise_band=(120.0, 500.0)), 0.002, 0.4 * body)])
    out += 0.07 * band_burst(n, rng, 900.0, 4000.0, 0.03, 0.012) * rough(n, rng, 50.0)
    return unit_peak(out)


def bounce(name="SFX_Bounce", dur=0.25, gain_tail=1.0):
    """Football on turf: the inflated bladder gives a dull low "pumf" (damped -- two or three
    cycles), the turf a soft puff, and the crumb rattles after it."""
    rng = rng_for(name)
    n = n_of(dur)
    t = times(n)
    ball = modal(n, [245.0, 492.0, 705.0, 1130.0], [0.013, 0.009, 0.006, 0.004], [1.0, 0.55, 0.3, 0.15])
    out = contact(ball * (1.0 - np.exp(-t / 0.0008)), 2.5)
    out += 0.7 * contact(band_burst(n, rng, 300.0, 3200.0, 0.016, 0.002, tilt=-3.0), 1.5)
    out += place(n, [(body_thud(n_of(0.1), rng, freqs=(95.0, 150.0), q=3.5, soft_ms=3.0), 0.0, 0.6)])
    out += 0.1 * gain_tail * band_burst(n, rng, 1500.0, 6000.0, 0.05, 0.02) * rough(n, rng, 40.0)
    return unit_peak(out)


def drop(dur=0.3):
    """Ball off the hands (two dull slaps -- skin, not a clean catch), a scrabble of fingers,
    then down onto the turf."""
    rng = rng_for("SFX_Drop")
    n = n_of(dur)
    out = np.zeros(n)
    for tk, a in ((0.0, 1.0), (0.038, 0.7)):
        s = contact(band_burst(n_of(0.08), rng, 450.0, 2600.0, 0.011, 0.0004, tilt=-3.0), 1.2)
        s += 0.4 * modal(len(s), [430.0, 1010.0], [0.008, 0.005], [1.0, 0.4])
        out += place(n, [(unit_peak(s), tk, a)])
    scrabble = shaped_noise(n_of(0.12), rng, tilt_db_oct=-3.0, lo=800.0, hi=5000.0) * rough(n_of(0.12), rng, 50.0, 0.7)
    out += place(n, [(scrabble * env_perc(len(scrabble), 0.01, 0.04), 0.02, 0.12)])
    out += place(n, [(bounce("SFX_Drop_b", 0.17), 0.125, 0.85)])
    return unit_peak(out)


def kick(name, dur=0.4, punt=False):
    """Boot into ball: a deep, dead thump (foot and ball compressing), the smack of leather,
    the ball's short hollow note bending down as it springs back, and a breath of air as it
    leaves."""
    rng = rng_for(name)
    n = n_of(dur)
    t = times(n)
    base = (58.0, 92.0, 140.0) if punt else (66.0, 104.0, 158.0)
    out = place(n, [(body_thud(n_of(0.25), rng, freqs=base, q=7.0 if punt else 6.0, soft_ms=1.5, noise=0.7), 0.0, 1.2)])
    out += 0.65 * contact(band_burst(n, rng, 650.0, 5200.0, 0.011, 0.0004, tilt=-2.0), 0.9 if not punt else 1.6)
    f_b = 300.0 if not punt else 255.0
    glide = 1.0 - 0.09 * (1 - np.exp(-t / 0.03))
    pung = modal(n, [f_b, f_b * 1.98, f_b * 2.86], [0.026, 0.016, 0.01], [1.0, 0.5, 0.25], f_curve=glide)
    out += 0.55 * pung * (1.0 - np.exp(-t / 0.001))
    out += 0.5 * band_burst(n, rng, 130.0, 700.0, 0.03, 0.003)
    air = swept_noise(n, rng, np.interp(t, [0, 0.1, dur], [700.0, 2200.0, 900.0]), q=1.3)
    out += 0.2 * air * env_points(n, [(0, 0), (0.035, 1.0), (0.15, 0.5), (dur, 0.0)])
    return saturate(unit_peak(out), 4.0)


def snap(dur=0.12):
    """The snap: fingers dragging off the laces as the ball is whipped back, then into the
    quarterback's hands."""
    rng = rng_for("SFX_Snap")
    n = n_of(dur)
    t = times(n)
    drag = shaped_noise(n, rng, tilt_db_oct=-2.0, lo=1500.0, hi=6500.0) * rough(n, rng, 120.0, 0.6)
    out = 0.6 * drag * env_points(n, [(0.0, 0.0), (0.03, 1.0), (0.05, 0.5), (0.065, 0.0), (dur, 0.0)])
    c = catch("SFX_Snap_c", 0.06, snap=1.1, body=0.7)
    out += place(n, [(c, 0.058, 1.0)])
    return unit_peak(out)


def steps(dur=0.5, count=3, thump=0.35, crunch=0.9, crunch_tau=(0.016, 0.026), scuff=0.0, seed="SFX_Steps"):
    """Cleats on turf, loopable: evenly spaced footfalls, each a small dead thump plus the
    crunch of studs biting into rubber crumb, alternating feet. Dry. Tails wrap round the loop."""
    rng = rng_for(seed)
    n = n_of(dur)
    tl = Timeline(n=n, loop=True, channels=1)
    for k in range(count):
        m = n_of(0.14)
        left = k % 2 == 0
        s = thump * body_thud(m, rng, freqs=(105.0, 170.0, 250.0) if left else (118.0, 185.0, 270.0), q=3.0, soft_ms=2.0,
                              noise=1.0, noise_band=(90.0, 500.0))
        grit = shaped_noise(m, rng, tilt_db_oct=-3.0, lo=900.0 if left else 1100.0, hi=6500.0) * rough(m, rng, 60.0, 0.7)
        s += crunch * grit * env_perc(m, 0.004, rng.uniform(*crunch_tau))
        if scuff:
            s += scuff * shaped_noise(m, rng, tilt_db_oct=-2.0, lo=2000.0, hi=8000.0) * env_points(m, [(0, 0), (0.03, 0.2), (0.06, 1.0), (0.1, 0.0), (0.14, 0.0)])
        s = fade(s, 0.0005, 0.02)
        tl.add(unit_peak(s), sample=k * n // count, gain=db2lin(rng.uniform(-1.5, 0.0)))
    return tl.buf


def whistle(name, dur=0.6, blow=0.5, f0=2600.0, swell=0.0, trill=0.45, rate=(36.0, 16.0), breath=0.38, hiss=1.0,
            tones=(1.0,), h2=0.28, settle=0.0):
    """Referee's pea whistle. A breathy cavity tone (rising with breath pressure) with harmonics;
    the cork pea tumbling round the chamber interrupts it irregularly 40-50 times a second
    (the trill) and pulls the pitch about; a lot of the sound is simply air."""
    rng = rng_for(name)
    n = n_of(dur)
    p = env_points(n, [(0.0, 0.0), (0.018, 0.75), (0.05, 1.0), (blow * 0.6, 1.0 + swell), (blow - 0.03, 0.9), (blow, 0.0), (dur, 0.0)])
    sq = np.sqrt(np.maximum(p, 0.0))
    r = (rate[0] + rate[1] * sq) * (1.0 + 0.18 * smooth_random(n, rng, 9.0, periodic=False))
    ph_t = np.cumsum(r) / SR
    pea = np.maximum(np.sin(TAU * ph_t), 0.0) ** 1.2 * (0.7 + 0.3 * np.abs(smooth_random(n, rng, 20.0, periodic=False)))
    pea = lp(pea, 180.0, 1)
    if settle:                                             # on a long blast the pea settles and the tone steadies
        pea = pea * (1.0 - settle * np.clip((times(n) - 0.15) / 0.3, 0.0, 1.0))
    f = f0 * (0.92 + 0.08 * sq) * (1.0 - 0.06 * pea * (trill / 0.5))
    f *= 1.0 + 0.012 * smooth_random(n, rng, 350.0, periodic=False) + 0.006 * smooth_random(n, rng, 30.0, periodic=False)
    tone = np.zeros(n)
    for k, mult in enumerate(tones):
        ph = TAU * np.cumsum(f * mult) / SR + k
        tone += (np.sin(ph) + h2 * np.sin(2 * ph + 0.5) + 0.5 * h2 * np.sin(3 * ph + 1.1) + 0.18 * h2 * np.sin(4 * ph)) / len(tones)
    amp = p * (1.0 - trill * pea) * (1.0 + 0.12 * smooth_random(n, rng, 60.0, periodic=False))
    air = shaped_noise(n, rng, tilt_db_oct=-1.5, lo=1500.0, hi=11000.0) * p * (0.6 + 0.6 * pea)
    edge = swept_noise(n, rng, f, q=3.5) * p
    out = tone * amp + breath * air + hiss * edge
    out = reverb(out, reverb_ir(0.5, seed=41, pre_delay=0.02, hf_mult=0.6, stereo=False), wet_db=-19.0)
    return out[:n]


def spin(dur=0.3):
    """Spin move: one fast swirl of air -- a whoosh whose band sweeps up and back, with a comb
    filter sweeping through it (the body turning past the ear)."""
    rng = rng_for("SFX_Spin")
    n = n_of(dur)
    t = times(n)
    u = t / dur
    fc = 500.0 * 2.0 ** (2.4 * np.sin(np.pi * u) ** 1.2)
    w = swept_noise(n, rng, fc, q=1.6) + 0.4 * shaped_noise(n, rng, tilt_db_oct=-3.0, lo=300.0, hi=6000.0)
    w = w + 0.75 * vdelay(w, SR * (0.0004 + 0.0022 * (0.5 - 0.5 * np.cos(TAU * u))))
    env = np.sin(np.pi * u) ** 1.3 * (1.0 + 0.25 * np.sin(TAU * 2 * u))
    return unit_peak(w * env)


def stiff_arm(dur=0.25):
    """Stiff-arm: the heel of a hand slamming into pads -- a short punchy thump, a dull plastic
    knock and the shove of air."""
    rng = rng_for("SFX_StiffArm")
    n = n_of(dur)
    out = place(n, [(body_thud(n_of(0.2), rng, freqs=(95.0, 150.0, 230.0), q=5.0, soft_ms=1.2), 0.0, 1.1)])
    knock = modal(n, [410.0, 890.0, 1450.0], [0.008, 0.005, 0.004], [1.0, 0.5, 0.3]) * (1 - np.exp(-times(n) / 0.0005))
    out += 0.5 * knock
    out += place(n, [(clack(n_of(0.05), rng, 1100.0, 4200.0, modes=5, tau=(0.003, 0.008), noise=0.6), 0.0, 0.5)])
    out += 0.4 * band_burst(n, rng, 250.0, 2200.0, 0.04, 0.008)
    return saturate(unit_peak(out), 5.0)


def juke(dur=0.2):
    """Juke: studs raking the turf as the runner plants and cuts -- a short, rough scrape that
    drops in pitch as the foot stops, and the plant itself."""
    rng = rng_for("SFX_Juke")
    n = n_of(dur)
    t = times(n)
    fc = np.interp(t, [0.0, 0.05, dur], [4600.0, 3200.0, 1800.0])
    scrape = swept_noise(n, rng, fc, q=0.9, tilt=-1.0) * rough(n, rng, 70.0, 0.75)
    out = 0.9 * scrape * env_points(n, [(0.0, 0.0), (0.008, 1.0), (0.05, 0.6), (dur - 0.02, 0.05), (dur, 0.0)])
    out += place(n, [(body_thud(n_of(0.1), rng, freqs=(100.0, 160.0), q=3.0, soft_ms=2.0, noise=1.0), 0.0, 0.6)])
    return unit_peak(out)


def fumble(dur=0.4):
    """Ball punched loose: the pop of a fist on the ball, the ball wobbling away (a hollow tone
    sagging in pitch -- the "uh-oh"), and its first skip on the turf."""
    rng = rng_for("SFX_Fumble")
    n = n_of(dur)
    t = times(n)
    m = n_of(0.12)
    pop = modal(m, [520.0, 1090.0, 1700.0], [0.022, 0.012, 0.007], [1.0, 0.6, 0.3],
                f_curve=1.0 - 0.3 * (1 - np.exp(-times(m) / 0.025)))
    pop = contact(pop * (1 - np.exp(-times(m) / 0.0004)), 0.6) + 0.5 * band_burst(m, rng, 1000.0, 5000.0, 0.005, 0.0003)
    out = place(n, [(unit_peak(pop), 0.0, 1.0)])
    f = 430.0 * (190.0 / 430.0) ** np.clip((t - 0.03) / 0.3, 0.0, 1.0)
    wob = 0.55 + 0.45 * np.cos(TAU * 8.5 * (t - 0.03))
    tone = lp(triangle(f) + 0.3 * sine(f * 2.0), 1500.0, 2)
    out += 0.42 * tone * wob * env_points(n, [(0.0, 0.0), (0.03, 0.0), (0.06, 1.0), (0.25, 0.6), (0.34, 0.0), (dur, 0.0)])
    out += place(n, [(bounce("SFX_Fumble_b", 0.12, gain_tail=0.5), 0.27, 0.5)])
    return unit_peak(out)


def goalpost(dur=0.8):
    """Ball off the upright. The ball is soft, so it mostly excites the tube's low bending
    modes (100-600 Hz, close-spaced pairs that beat against each other -- the wobble in a
    "doink"); a little of the pipe wall's own ring (about 1 kHz and 3 kHz for a 10 cm aluminium
    tube) gives the metallic edge."""
    rng = rng_for("SFX_Goalpost")
    n = n_of(dur)
    t = times(n)
    freqs, taus, amps = [], [], []
    for f, a, tau in ((118.0, 0.5, 0.28), (172.0, 0.7, 0.3), (236.0, 1.0, 0.3), (311.0, 1.0, 0.26), (395.0, 0.8, 0.22),
                      (489.0, 0.55, 0.19), (590.0, 0.4, 0.16), (702.0, 0.25, 0.13)):
        split = rng.uniform(2.5, 6.5)
        freqs += [f, f + split]
        taus += [tau, tau * rng.uniform(0.8, 1.1)]
        amps += [a, a * rng.uniform(0.6, 0.9)]
    for f, a, tau in ((1056.0, 0.2, 0.3), (1071.0, 0.16, 0.27), (2988.0, 0.035, 0.12), (3020.0, 0.03, 0.1)):
        freqs.append(f); taus.append(tau); amps.append(a)
    ring = modal(n, freqs, taus, amps, phases=rng.uniform(0, TAU, len(freqs)))
    ring = contact(ring * (1.0 - np.exp(-t / 0.002)), 5.0)
    strike = 0.9 * thud(n, 210.0, 120.0, 0.02, 0.03) + 0.5 * contact(band_burst(n, rng, 600.0, 3500.0, 0.007, 0.0004), 0.8)
    out = unit_peak(ring) + 0.55 * unit_peak(strike)
    return out


# ============================================================================= voices (synthetic)

def field_voice(name):
    from make_voice import trim
    from fury.wavio import read_take
    source = "SFX_Hut_1" if name == "SFX_Hut_3" else name
    dry = trim(read_take(source), thresh_db=-30, lead=0.008, trail=0.035)
    if name == "SFX_Hut_3":
        dry = lp(resample(dry, 1.06), 4500.0, 2)
    limit = 0.42 if "Hut" in name else 0.48
    return fade(hp(dry[:n_of(limit)], 75.0, 2), 0.002, 0.04)


def fire_roar(n, rng, periodic=False):
    """Flame: brown-ish noise whose loudness flickers with the turbulence (a few to ~25 Hz)."""
    body = shaped_noise(n, rng, tilt_db_oct=-5.0, lo=70.0, hi=6000.0)
    if periodic:
        fl = 1.0 + 0.3 * periodic_lfo(n, rng, (3, 5, 8, 13, 21, 34)) + 0.12 * periodic_lfo(n, rng, (40, 47, 55))
    else:
        fl = 1.0 + 0.3 * smooth_random(n, rng, 9.0, periodic=False) + 0.12 * smooth_random(n, rng, 28.0, periodic=False)
    return body * np.maximum(fl, 0.15)


def fury_ignite(dur=1.5):
    """Whoosh up -> ignition. Air is drawn in (rising band of noise and a rising growl), then the
    whole thing lights: a low "fwoomp", a burst that closes down like a fireball, and a roaring,
    crackling flame that dies back."""
    rng = rng_for("SFX_FuryIgnite")
    n = n_of(dur)
    t = times(n)
    t_ig = 0.52
    up = np.clip(t / t_ig, 0.0, 1.0)
    swell = (0.14 + 0.86 * up) ** 2.2                      # audible from the first frame, then surging
    rise = swept_noise(n, rng, 180.0 * 2.0 ** (4.6 * up ** 1.4), q=2.0) * swell * (t < t_ig + 0.02)
    growl_f = 55.0 * 2.0 ** (2.2 * up ** 1.5)
    growl = lp(saw(growl_f) + saw(growl_f * 1.5 * 1.004), 900.0, 2) * swell * (t < t_ig + 0.02)
    out = 0.75 * unit_peak(rise) + 0.35 * unit_peak(growl)
    m = n - n_of(t_ig)
    tt = times(m)
    boom = saturate(unit_peak(thud(m, 140.0, 42.0, 0.05, 0.2) + 0.5 * thud(m, 90.0, 60.0, 0.03, 0.3)), 8.0)
    ball = sweep_filter(rng.standard_normal(m), 9000.0 * np.exp(-tt / 0.16) + 350.0, "lp", q=0.8) * env_perc(m, 0.004, 0.22)
    flame = fire_roar(m, rng) * env_points(m, [(0.0, 0.0), (0.03, 1.0), (0.25, 0.8), (dur - t_ig - 0.05, 0.0)])
    crack = crackle(m, rng, 60.0, env=np.exp(-tt / 0.4)) * 1.0
    burst = 1.0 * boom + 0.9 * unit_peak(ball) + 0.7 * unit_peak(flame) + 0.25 * unit_peak(crack)
    out += place(n, [(burst, t_ig, 1.15)])
    out = saturate(unit_peak(out), 5.0)
    out = reverb(out, reverb_ir(0.6, seed=47, pre_delay=0.01, hf_mult=0.5, stereo=False), wet_db=-16.0)
    return out[:n]


def fury_loop(dur=2.0, crackle_rate=150.0, crackle_gain=2.5, flame_gain=1.0):
    """Burning energy bed, loopable: flame roar, sharp crackles, and a low electrical throb.
    All modulators run a whole number of cycles in the loop and the crackles wrap around."""
    rng = rng_for("SFX_FuryLoop")
    n = n_of(dur)
    t = np.arange(n) / SR
    flame = unit_rms(fire_roar(n, rng, periodic=True))
    cr = crackle(n, rng, crackle_rate, tau=(0.0005, 0.005), f=(900.0, 6000.0), periodic=True)
    cr = cr / max(np.max(np.abs(cr)), 1e-9)
    hiss = shaped_noise(n, rng, tilt_db_oct=-1.0, lo=2500.0, hi=11000.0) * (1.0 + 0.4 * periodic_lfo(n, rng, (2, 3, 5, 9)))
    f1, f2 = 55.0, 82.5                                   # whole cycles in 2.0 s: 110 and 165
    throb = lp(saw(f1, n) + 0.7 * saw(f2, n) + 0.5 * saw(f1 * 2 + 0.5, n), 420.0, 2, circular=True)
    throb *= 1.0 + 0.35 * np.sin(TAU * 4.0 * t) + 0.2 * np.sin(TAU * 6.5 * t + 1.0)
    return flame_gain * flame + crackle_gain * cr + 0.16 * unit_rms(hiss) + 0.42 * unit_rms(throb)


def fury_end(dur=0.8):
    """Power-down: the throb sags in pitch and the flame is starved -- a falling, darkening
    growl, the last crackles, and a puff."""
    rng = rng_for("SFX_FuryEnd")
    n = n_of(dur)
    t = times(n)
    u = t / dur
    f = 330.0 * (38.0 / 330.0) ** (u ** 0.75)
    g = saw(f) + 0.6 * saw(f * 1.498) + 0.5 * pulse(f * 0.5, width=0.3)
    g = sweep_filter(g, 3800.0 * (120.0 / 3800.0) ** u, "lp", q=1.6)
    out = 0.9 * unit_peak(g) * env_points(n, [(0, 0), (0.008, 1.0), (dur * 0.7, 0.55), (dur - 0.02, 0.0), (dur, 0)])
    flame = fire_roar(n, rng) * np.exp(-t / 0.18)
    out += 0.5 * unit_peak(flame)
    out += 0.2 * unit_peak(crackle(n, rng, 40.0, env=np.exp(-t / 0.2)))
    puff = band_burst(n_of(0.2), rng, 150.0, 1500.0, 0.05, 0.02)
    out += place(n, [(puff, dur * 0.62, 0.35)])
    return saturate(unit_peak(out), 3.0)


def meter_tick(dur=0.1):
    """One notch of the Fury meter: a hard little click with a quick upward chirp behind it."""
    rng = rng_for("SFX_MeterTick")
    n = n_of(dur)
    t = times(n)
    f = 950.0 * (1500.0 / 950.0) ** np.clip(t / 0.045, 0, 1)
    chirp = (np.sin(TAU * np.cumsum(f) / SR) + 0.35 * np.sin(2 * TAU * np.cumsum(f) / SR)) * env_perc(n, 0.001, 0.022)
    click = clack(n_of(0.03), rng, 1800.0, 6500.0, modes=4, tau=(0.001, 0.004), noise=0.7)
    out = 0.8 * chirp + place(n, [(click, 0.0, 0.7)]) + 0.4 * thud(n, 260.0, 170.0, 0.008, 0.012)
    return unit_peak(out)


# ============================================================================= interface

def ui_move():
    """Cursor move: a dry stick-on-rim tick."""
    rng = rng_for("SFX_UIMove")
    n = n_of(0.06)
    t = times(n)
    x = modal(n, [1180.0, 2750.0, 4300.0], [0.007, 0.004, 0.003], [1.0, 0.6, 0.3]) * (1 - np.exp(-t / 0.0003))
    x += 0.5 * band_burst(n, rng, 2000.0, 9000.0, 0.002, 0.0002) + 0.45 * thud(n, 420.0, 300.0, 0.004, 0.006)
    return unit_peak(x)


def ui_select():
    """Confirm: a tight drum "thwack" with a short bright note riding on it."""
    rng = rng_for("SFX_UISelect")
    n = n_of(0.17)
    t = times(n)
    x = 0.9 * thud(n, 260.0, 120.0, 0.012, 0.03) + place(n, [(clack(n_of(0.04), rng, 1200.0, 6000.0, modes=5, tau=(0.002, 0.006), noise=0.8), 0.0, 0.8)])
    note = lp(triangle(880.0, n) + 0.5 * saw(880.0, n) + 0.4 * saw(1320.0, n), 4200.0, 2) * env_perc(n, 0.001, 0.045)
    return unit_peak(x + 0.65 * note)


def ui_back():
    """Back out: the same family, pitched down and falling."""
    rng = rng_for("SFX_UIBack")
    n = n_of(0.15)
    t = times(n)
    f = 620.0 * (400.0 / 620.0) ** np.clip(t / 0.07, 0, 1)
    note = lp(triangle(f) + 0.4 * saw(f), 2600.0, 2) * env_perc(n, 0.001, 0.04)
    x = 0.8 * thud(n, 200.0, 95.0, 0.012, 0.03) + 0.5 * place(n, [(clack(n_of(0.04), rng, 800.0, 3500.0, modes=4, tau=(0.002, 0.006), noise=0.6), 0.0, 1.0)])
    return unit_peak(x + 0.6 * note)


def ui_join():
    """A player joins: two quick rising brass notes (a fifth apart) with a clap on the second."""
    rng = rng_for("SFX_UIJoin")
    n = n_of(0.38)
    a = ins.brass(ins.hz("E5"), 0.07, rng, vel=0.9, vib=0.0, release=0.03) + 0.7 * ins.brass(ins.hz("E4"), 0.07, rng, vel=0.9, vib=0.0, release=0.03)
    b = ins.brass(ins.hz("B5"), 0.17, rng, vel=1.0, vib=0.0, release=0.08) + 0.7 * ins.brass(ins.hz("B4"), 0.17, rng, vel=1.0, vib=0.0, release=0.08)
    x = place(n, [(a, 0.0, 0.8), (b, 0.095, 1.0), (ins.clap(rng, 0.2), 0.095, 0.5), (ins.kick(rng, 0.15, ta=0.05), 0.0, 0.5)])
    return unit_peak(x)


def ui_ready():
    """Locked in: a heavy latch going home ("ka-chunk") under a short power chord."""
    rng = rng_for("SFX_UIReady")
    n = n_of(0.4)
    t = times(n)

    def latch(f):
        m = n_of(0.12)
        return unit_peak(modal(m, [f, f * 2.4, f * 4.4, f * 7.1], [0.02, 0.012, 0.007, 0.004], [1.0, 0.7, 0.5, 0.3])
                         * (1 - np.exp(-times(m) / 0.0004)) + 0.6 * band_burst(m, rng, 1500.0, 7000.0, 0.003, 0.0002))

    x = place(n, [(latch(410.0), 0.0, 0.6), (latch(300.0), 0.05, 1.0)])
    x += place(n, [(ins.kick(rng, 0.3, f0=130.0, f1=52.0, ta=0.09), 0.05, 0.9)])
    chord = np.zeros(n)
    for nm, g in (("E3", 1.0), ("B3", 0.8), ("E4", 0.8), ("G#4", 0.5), ("B4", 0.5)):
        v = ins.brass(ins.hz(nm), 0.2, rng, vel=0.95, vib=0.0, release=0.09)
        chord += place(n, [(v, 0.05, g)])
    return unit_peak(unit_peak(x) + 0.55 * unit_peak(chord))


def ui_error():
    """Not allowed: two short flat buzzes, close and dissonant."""
    rng = rng_for("SFX_UIError")
    n = n_of(0.28)
    x = np.zeros(n)
    for t0 in (0.0, 0.14):
        m = n_of(0.11)
        b = pulse(116.5, m, width=0.3) + pulse(123.5, m, width=0.3) + 0.5 * saw(233.0, m)
        b = lp(b, 1300.0, 2) * env_points(m, [(0, 0), (0.004, 1.0), (0.095, 0.9), (0.11, 0.0)])
        x += place(n, [(b, t0, 1.0), (thud(n_of(0.05), 180.0, 110.0, 0.008, 0.012), t0, 2.0)])
    return saturate(unit_peak(x), 4.0)


def ui_page():
    """Playbook page: a laminated sheet swishing over and slapping flat."""
    rng = rng_for("SFX_UIPage")
    n = n_of(0.24)
    t = times(n)
    fc = np.interp(t, [0.0, 0.08, 0.17, 0.24], [1400.0, 5200.0, 3000.0, 2200.0])
    sw = swept_noise(n, rng, fc, q=0.9, tilt=1.0) * rough(n, rng, 55.0, 0.65)
    sw *= env_points(n, [(0, 0), (0.03, 0.6), (0.1, 1.0), (0.165, 0.5), (0.18, 0.0), (0.24, 0.0)])
    flap = contact(band_burst(n_of(0.06), rng, 300.0, 4500.0, 0.008, 0.0003, tilt=-3.0), 0.8)
    return unit_peak(sw + place(n, [(flap, 0.172, 1.1)]))


def play_picked():
    """A play is called: kick and snare together under a stab of low brass."""
    rng = rng_for("SFX_PlayPicked")
    n = n_of(0.36)
    x = place(n, [(ins.kick(rng, 0.3), 0.0, 1.0), (ins.snare(rng, 0.3, wires=0.8), 0.0, 0.75)])
    chord = np.zeros(n)
    for nm, g in (("E2", 0.9), ("E3", 1.0), ("B3", 0.8), ("E4", 0.7)):
        chord += place(n, [(ins.brass(ins.hz(nm), 0.16, rng, vel=1.0, vib=0.0, release=0.1), 0.0, g)])
    return saturate(unit_peak(unit_peak(x) + 0.6 * unit_peak(chord)), 3.0)


def countdown(go=False):
    """Countdown tick: a wood-block "tok". The final one is an octave up with drums and brass."""
    rng = rng_for("SFX_CountdownGo" if go else "SFX_Countdown")
    n = n_of(0.4 if go else 0.13)
    t = times(n)
    f = 1760.0 if go else 880.0
    block = modal(n, [f, f * 2.68, f * 4.9], [0.035 if not go else 0.06, 0.012, 0.006], [1.0, 0.5, 0.25]) * (1 - np.exp(-t / 0.0003))
    x = unit_peak(block) + 0.5 * band_burst(n, rng, 1500.0, 8000.0, 0.002, 0.0002) + 0.6 * thud(n, 300.0, 150.0, 0.008, 0.015)
    if go:
        x = unit_peak(x)
        x += place(n, [(ins.kick(rng, 0.3), 0.0, 0.9), (ins.crash(rng, 0.39, tau=0.12), 0.0, 0.3)])
        chord = np.zeros(n)
        for nm, g in (("E3", 0.9), ("B3", 0.8), ("E4", 1.0), ("B4", 0.7), ("E5", 0.8)):
            chord += place(n, [(ins.brass(ins.hz(nm), 0.22, rng, vel=1.0, vib=0.0, release=0.1), 0.0, g)])
        x += 0.6 * unit_peak(chord)
    return unit_peak(x)


# ============================================================================= stingers (stereo)

def hall(seed, rt60=1.5):
    return reverb_ir(rt60, seed=seed, pre_delay=0.025, lf_mult=1.05, hf_mult=0.45, build=0.02, stereo=True)


def finish_stinger(tl, dur, seed, wet_db=-13.0, rt60=1.5, drive=2.5):
    x = tl.buf
    x = x / max(np.max(np.abs(x)), 1e-9)
    x = saturate(x * 0.9, drive)
    wet = reverb(x, hall(seed, rt60), wet_db=wet_db)
    return pad_to(wet, n_of(dur))


def drums_hit(tl, rng, t, gain=1.0, kick=True, snare=True, crash=False, snare_room=0.5):
    if kick:
        tl.add(ins.kick(rng), at=t, gain=1.0 * gain)
    if snare:
        tl.add(ins.snare(rng, room=snare_room), at=t, gain=0.8 * gain)
    if crash:
        c = ins.crash(rng, 2.0)
        tl.add(c, at=t, gain=0.4 * gain, pan_pos=-0.35)
        tl.add(ins.crash(rng, 1.8, tau=0.55), at=t, gain=0.3 * gain, pan_pos=0.4)


def touchdown(dur=3.0):
    """Touchdown: everything at once -- drums, a G-major brass chord and a two-note air horn --
    then three pick-up notes into a long held chord over a kettledrum roll, and a last "button"."""
    rng = rng_for("SFX_Touchdown")
    tl = Timeline(dur + 1.0)
    G = [ins.hz(x) for x in ("G3", "D4", "G4", "B4", "D5")]
    drums_hit(tl, rng, 0.0, crash=True)
    tl.add(ins.timpani(rng, ins.hz("G2"), 1.2), at=0.0, gain=0.8)
    tl.add(ins.brass_section(G, 0.22, rng, vel=1.0, players=2, vib=0.0), at=0.0, gain=1.0)
    horn = ins.air_horn(0.8, rng, f=(ins.hz("B4"), ins.hz("D5")))
    tl.add(horn, at=0.02, gain=0.55, pan_pos=-0.15)
    for k, t0 in enumerate((0.95, 1.08, 1.21)):                 # pick-up triplet
        tl.add(ins.brass_section([ins.hz("D4"), ins.hz("D5")], 0.085, rng, vel=0.95, players=2, vib=0.0, release=0.03), at=t0, gain=0.8)
        tl.add(ins.snare(rng, 0.25, wires=0.9), at=t0, gain=0.4 + 0.1 * k)
    t_s = 1.34
    hold = 0.92
    drums_hit(tl, rng, t_s, crash=True)
    tl.add(ins.brass_section(G + [ins.hz("G5")], hold, rng, vel=1.0, players=3, vib=0.005), at=t_s, gain=1.1)
    tl.add(ins.brass_section([ins.hz("G2")], hold, rng, vel=0.9, players=2, vib=0.0), at=t_s, gain=0.5)
    k = 0
    tt = t_s
    while tt < t_s + hold:                                        # kettledrum roll, swelling
        g = 0.3 + 0.5 * (tt - t_s) / hold
        tl.add(ins.timpani(rng, ins.hz("G2"), 0.6, tau=0.3), at=tt, gain=g, pan_pos=0.2 if k % 2 else -0.2)
        tt += 0.072
        k += 1
    t_b = t_s + hold + 0.06
    drums_hit(tl, rng, t_b, gain=1.1, crash=True)
    tl.add(ins.timpani(rng, ins.hz("G2"), 1.0), at=t_b, gain=0.9)
    tl.add(ins.brass_section(G + [ins.hz("G5")], 0.13, rng, vel=1.0, players=3, vib=0.0, release=0.06), at=t_b, gain=1.15)
    return finish_stinger(tl, dur, 51, wet_db=-12.0, rt60=1.6)


def first_down(dur=0.8):
    """First down: "da-DAH" -- brass up a fourth onto the home chord, with a drum hit."""
    rng = rng_for("SFX_FirstDown")
    tl = Timeline(dur + 0.8)
    tl.add(ins.brass_section([ins.hz("D4"), ins.hz("D5")], 0.1, rng, vel=0.95, players=2, vib=0.0, release=0.03), at=0.0, gain=0.85)
    tl.add(ins.snare(rng, 0.25), at=0.0, gain=0.45)
    t1 = 0.145
    tl.add(ins.brass_section([ins.hz(x) for x in ("G3", "D4", "G4", "B4", "G5")], 0.3, rng, vel=1.0, players=2, vib=0.003), at=t1, gain=1.0)
    drums_hit(tl, rng, t1, gain=0.9)
    return finish_stinger(tl, dur, 53, wet_db=-13.0, rt60=1.0)


def turnover(dur=1.2):
    """Turnover: three hammered notes stepping down a diminished chord, landing on a low,
    growling tritone with a kettledrum."""
    rng = rng_for("SFX_Turnover")
    tl = Timeline(dur + 1.0)
    for k, (nm, t0) in enumerate((("G4", 0.0), ("E4", 0.15), ("C#4", 0.3))):
        f = ins.hz(nm)
        tl.add(ins.brass_section([f / 2, f], 0.1, rng, vel=1.0, players=2, vib=0.0, release=0.03), at=t0, gain=0.95)
        tl.add(ins.tom(rng, (130.0, 105.0, 85.0)[k], 0.4), at=t0, gain=0.7, pan_pos=(-0.3, 0.0, 0.3)[k])
        tl.add(ins.snare(rng, 0.25, wires=0.7), at=t0, gain=0.35)
    t1 = 0.46
    low = [ins.hz("C#2"), ins.hz("C#3"), ins.hz("G3"), ins.hz("A#3")]
    tl.add(ins.brass_section(low, 0.55, rng, vel=1.0, bright=1.2, players=3, vib=0.0, fall=1.5), at=t1, gain=1.2)
    tl.add(ins.timpani(rng, ins.hz("C#2"), 1.2, tau=0.5), at=t1, gain=1.0)
    tl.add(ins.kick(rng, 0.5, f0=120.0, f1=38.0, ta=0.2), at=t1, gain=0.9)
    tl.add(ins.crash(rng, 1.4, tau=0.4), at=t1, gain=0.2, pan_pos=0.2)
    return finish_stinger(tl, dur, 55, wet_db=-12.0, rt60=1.3, drive=4.0)


def sack(dur=0.9):
    """Sack: a crunching hit and the bottom dropping out -- low brass sliding down an octave."""
    rng = rng_for("SFX_Sack")
    tl = Timeline(dur + 0.8)
    tl.add(big_hit("SFX_Sack_hit", dur=0.6, crunch=1.6, ring=0.3), at=0.0, gain=1.0)
    slide = np.zeros(n_of(0.75))
    for det in (-9.0, 0.0, 8.0):
        v = ins.brass(ins.hz("E3") * 2 ** (det / 1200.0), 0.6, rng, vel=1.0, bright=1.3, vib=0.0, fall=13.0, release=0.08, scoop=0.0)
        slide[: len(v)] += v[: len(slide)]
        v2 = ins.brass(ins.hz("E2") * 2 ** (det / 1200.0), 0.6, rng, vel=1.0, bright=1.3, vib=0.0, fall=13.0, release=0.08, scoop=0.0)
        slide[: len(v2)] += 0.8 * v2[: len(slide)]
    tl.add(saturate(unit_peak(slide), 8.0), at=0.03, gain=0.7)
    tl.add(ins.snare(rng, 0.3, room=0.5), at=0.0, gain=0.5)
    return finish_stinger(tl, dur, 57, wet_db=-15.0, rt60=0.9, drive=4.0)


def field_goal_good(dur=1.5):
    """Field goal good: trumpets run up the G-major chord and hold the top, bells sparkling above."""
    rng = rng_for("SFX_FieldGoalGood")
    tl = Timeline(dur + 1.0)
    for k, nm in enumerate(("G4", "B4", "D5")):
        tl.add(ins.brass_section([ins.hz(nm)], 0.075, rng, vel=0.95, players=2, vib=0.0, release=0.03), at=0.09 * k, gain=0.85)
        tl.add(ins.snare(rng, 0.2, wires=0.9), at=0.09 * k, gain=0.3)
    t1 = 0.27
    tl.add(ins.brass_section([ins.hz(x) for x in ("G3", "D4", "G4", "B4", "D5", "G5")], 0.6, rng, vel=1.0, players=2, vib=0.005), at=t1, gain=1.05)
    drums_hit(tl, rng, t1, gain=0.85, crash=True)
    for k, nm in enumerate(("G6", "B6", "D7", "G7")):
        tl.add(ins.bell(ins.hz(nm), 0.9, rng, tau=0.3), at=t1 + 0.07 * k, gain=0.16, pan_pos=(-0.5, 0.5, -0.3, 0.3)[k])
    return finish_stinger(tl, dur, 59, wet_db=-12.0, rt60=1.3)


def no_good(dur=1.0):
    """No good: a muted trombone "wah" that sags -- the note slides down a tritone while the
    plunger closes over the bell."""
    rng = rng_for("SFX_NoGood")
    n = n_of(dur)
    t = times(n)
    f0 = ins.hz("B3")
    glide = np.clip((t - 0.24) / 0.5, 0.0, 1.0)
    f = f0 * 2.0 ** (-6.0 * glide ** 1.3 / 12.0)
    f = f * (1.0 + (0.004 + 0.012 * glide) * np.sin(TAU * 5.5 * t))
    x = np.zeros(n)
    for det in (-6.0, 5.0):
        src = saw(f * 2 ** (det / 1200.0), start=rng.random())
        wah = np.interp(t, [0.0, 0.09, 0.26, 0.8, dur], [420.0, 1500.0, 1250.0, 330.0, 300.0])
        x += sweep_filter(src, wah, "bp", q=3.0) * 1.6 + 0.35 * lp(src, 700.0, 2)
    env = env_points(n, [(0, 0), (0.03, 0.8), (0.1, 1.0), (0.3, 0.9), (0.85, 0.3), (dur - 0.03, 0.0), (dur, 0.0)])
    x = x * env + place(n, [(band_burst(n_of(0.05), rng, 600.0, 3000.0, 0.012, 0.003), 0.0, 0.2)])
    tl = Timeline(dur + 0.6)
    tl.add(unit_peak(x), at=0.0, pan_pos=-0.1)
    tl.add(ins.timpani(rng, ins.hz("B1"), 0.8, tau=0.3), at=0.0, gain=0.35)
    return finish_stinger(tl, dur, 61, wet_db=-16.0, rt60=0.9, drive=3.0)


def stadium_horn(dur=2.0, hold=1.5):
    """End of quarter: the big scoreboard horn -- a harsh diaphragm buzz (two slightly detuned
    units and a sub-octave), through the PA, slapping back off the far stand."""
    rng = rng_for("SFX_Horn")
    n = n_of(hold + 0.1)
    t = times(n)
    env = env_points(n, [(0, 0), (0.015, 1.0), (hold, 0.95), (hold + 0.045, 0.0), (hold + 0.1, 0.0)])
    x = np.zeros(n)
    for f0, g in ((233.1, 1.0), (235.6, 0.9), (116.5, 0.6), (350.5, 0.35)):
        fc = f0 * (1.0 - 0.03 * np.exp(-t / 0.02)) * (1.0 + 0.003 * smooth_random(n, rng, 15.0, periodic=False))
        x += g * (pulse(fc, width=0.14, start=rng.random()) + 0.6 * saw(fc, start=rng.random()))
    x *= 1.0 + 0.2 * np.sin(TAU * 58.0 * t)
    x = saturate(x * 0.35, 10.0, asym=0.2)
    x = eq(x, [("hp", 170.0, 0.8, 0.0), ("peak", 900.0, 0.9, 4.0), ("peak", 2400.0, 1.2, 5.0), ("lp", 5200.0, 0.7, 0.0)])
    x = unit_peak(x * env)
    st = pan(x, 0.0)
    st = echo(st, 0.19, gain_db=-10.0, repeats=2, feedback_db=-7.0, damp=2600.0)
    st[:, 1] = np.roll(st[:, 1], 180)                           # a few ms between the channels: width
    wet = reverb(st, reverb_ir(2.0, seed=63, pre_delay=0.05, hf_mult=0.35, build=0.05, stereo=True), wet_db=-12.0)
    return pad_to(wet, n_of(dur))


def firework(name, dur, launch=True, bursts=((0.95, 1.0, 0.0),), crackle_tail=0.0, whistle=True):
    """Shell: a mortar thump, the rising hiss (and falling whistle) of the climb, then the burst --
    a hard crack, a low boom rolling round the stadium, and (for some) a tail of crackling stars.
    bursts: (time, size, pan)."""
    rng = rng_for(name)
    tl = Timeline(dur + 1.2)
    n = n_of(dur)
    t_first = bursts[0][0]
    if launch:
        tl.add(lp(thud(n_of(0.3), 120.0, 60.0, 0.03, 0.06) + 0.6 * band_burst(n_of(0.3), rng, 100.0, 900.0, 0.03, 0.002), 1500.0, 2),
               at=0.0, gain=0.5)
        m = n_of(t_first - 0.08)
        tt = times(m)
        u = tt / tt[-1]
        hiss = swept_noise(m, rng, 900.0 * 2.0 ** (2.3 * u), q=1.2) * u ** 1.5 * (1.0 - u ** 6)
        tl.add(unit_peak(hiss), at=0.04, gain=0.28, pan_pos=bursts[0][2] * 0.5)
        if whistle:
            fw = 3100.0 * (1500.0 / 3100.0) ** u * (1.0 + 0.01 * np.sin(TAU * 31.0 * tt))
            w = (np.sin(TAU * np.cumsum(fw) / SR) + 0.2 * np.sin(2 * TAU * np.cumsum(fw) / SR)) * (0.7 + 0.3 * np.sin(TAU * 31.0 * tt))
            w *= np.sin(np.pi * u) ** 1.2
            tl.add(w, at=0.04, gain=0.14, pan_pos=bursts[0][2] * 0.5)
    for tb, size, pp in bursts:
        m = n_of(1.2)
        tt = times(m)
        crack = band_burst(n_of(0.06), rng, 500.0, 12000.0, 0.004, 0.0002)
        boom = saturate(unit_peak(thud(m, 100.0, 42.0, 0.05, 0.22 * size) + 0.8 * unit_peak(
            shaped_noise(m, rng, tilt_db_oct=-6.0, lo=30.0, hi=200.0) * env_perc(m, 0.003, 0.3 * size))), 8.0)
        for ch in range(2):
            blast = sweep_filter(rng.standard_normal(m), 9000.0 * np.exp(-tt / (0.09 * size)) + 300.0, "lp", q=0.8) * env_perc(m, 0.001, 0.2 * size)
            side = np.zeros((m, 2))
            side[:, ch] = unit_peak(blast)
            tl.add(side, at=tb, gain=0.75 * size)
        tl.add(crack, at=tb, gain=0.9 * size, pan_pos=pp)
        tl.add(boom, at=tb + 0.004, gain=1.0 * size, pan_pos=pp * 0.4)
        if crackle_tail:
            mc = n_of(crackle_tail)
            for ch in range(2):
                cr = crackle(mc, rng, 240.0, tau=(0.0003, 0.002), f=(2500.0, 9000.0), env=np.exp(-times(mc) / (crackle_tail * 0.35)))
                side = np.zeros((mc, 2))
                side[:, ch] = cr / max(np.max(np.abs(cr)), 1e-9)
                tl.add(side, at=tb + 0.12, gain=0.3 * size)
    x = tl.buf / max(np.max(np.abs(tl.buf)), 1e-9)
    x = saturate(x, 4.0)
    x = echo(x, 0.21, gain_db=-13.0, repeats=1, damp=1800.0)
    wet = reverb(x, reverb_ir(1.8, seed=65, pre_delay=0.04, hf_mult=0.35, build=0.04, stereo=True), wet_db=-13.0)
    return pad_to(wet, n)


def cannon(dur=1.5):
    """Touchdown cannon: a flat crack, then a great low boom with a long rumbling tail and its
    echo coming back off the stands."""
    rng = rng_for("SFX_Cannon")
    tl = Timeline(dur + 1.0)
    m = n_of(1.4)
    tt = times(m)
    crack = band_burst(n_of(0.08), rng, 300.0, 10000.0, 0.006, 0.0002)
    boom = thud(m, 115.0, 33.0, 0.06, 0.34) + 0.6 * thud(m, 190.0, 60.0, 0.035, 0.14)
    rumble = shaped_noise(m, rng, tilt_db_oct=-6.0, lo=22.0, hi=140.0) * env_perc(m, 0.004, 0.45)
    low = saturate(unit_peak(unit_peak(boom) + 0.9 * unit_peak(rumble)), 11.0)
    tl.add(low, at=0.0, gain=1.0)
    tl.add(crack, at=0.0, gain=0.8)
    for ch in range(2):
        blast = sweep_filter(rng.standard_normal(m), 6500.0 * np.exp(-tt / 0.1) + 160.0, "lp", q=0.8) * env_perc(m, 0.001, 0.26)
        side = np.zeros((m, 2))
        side[:, ch] = unit_peak(blast)
        tl.add(side, at=0.0, gain=0.8)
    x = tl.buf / np.max(np.abs(tl.buf))
    x = saturate(x, 5.0)
    x = echo(x, 0.23, gain_db=-11.0, repeats=2, feedback_db=-8.0, damp=1100.0)
    wet = reverb(x, reverb_ir(2.2, seed=67, pre_delay=0.05, lf_mult=1.3, hf_mult=0.3, build=0.05, stereo=True), wet_db=-12.0)
    return pad_to(wet, n_of(dur))


# ============================================================================= jobs

def football():
    save("SFX_Hit_1", hit("SFX_Hit_1", weight=1.0, bright=1.0, clacks=3, dur=0.4), loud=-11.5)
    save("SFX_Hit_2", hit("SFX_Hit_2", weight=0.75, bright=1.25, clacks=2, dur=0.34), loud=-12.5)
    save("SFX_Hit_3", hit("SFX_Hit_3", weight=1.35, bright=0.85, clacks=3, dur=0.46), loud=-11.0)
    save("SFX_Hit_4", hit("SFX_Hit_4", weight=1.1, bright=1.1, clacks=4, dur=0.42, spread=1.8), loud=-11.5)
    save("SFX_BigHit_1", big_hit("SFX_BigHit_1", dur=0.9), loud=-9.0, fade_out=0.05)
    save("SFX_BigHit_2", big_hit("SFX_BigHit_2", dur=0.85, crunch=1.5, ring=1.8), loud=-9.0, fade_out=0.05)
    save("SFX_BigHit_3", big_hit("SFX_BigHit_3", dur=1.0, double=True), loud=-9.0, fade_out=0.05)
    save("SFX_Dive_1", dive("SFX_Dive_1"), loud=-17.0, fade_out=0.02)
    save("SFX_Dive_2", dive("SFX_Dive_2", slide=1.35, bump=True), loud=-17.5, fade_out=0.02)
    save("SFX_Throw_1", throw("SFX_Throw_1"), loud=-20.0, fade_in=0.004, fade_out=0.02)
    save("SFX_Throw_2", throw("SFX_Throw_2", speed=1.3), loud=-20.0, fade_in=0.004, fade_out=0.02)
    save("SFX_BallAir", ball_air(), loop=True, lufs=-27.0)
    save("SFX_Catch_1", catch("SFX_Catch_1", 0.2), loud=-15.0)
    save("SFX_Catch_2", catch("SFX_Catch_2", 0.24, snap=0.8, body=1.5), loud=-15.5)
    save("SFX_Catch_3", catch("SFX_Catch_3", 0.16, snap=1.4, body=0.6), loud=-15.5)
    save("SFX_Drop", drop(), loud=-17.0)
    save("SFX_Bounce", bounce(), loud=-18.0)
    save("SFX_Kick_1", kick("SFX_Kick_1"), loud=-12.0, fade_out=0.03)
    save("SFX_Kick_2", kick("SFX_Kick_2", punt=True), loud=-12.5, fade_out=0.03)
    save("SFX_Snap", snap(), loud=-19.0, fade_out=0.006)
    for base, count, level in (("Hut", 3, -13), ("Grunt", 4, -15.5)):
        for i in range(1, count + 1):
            name = f"SFX_{base}_{i}"
            save(name, field_voice(name), loud=level, fade_out=0.02)
    for i in range(1, 7):
        name = f"SFX_Cleat_{i}"
        save(name, steps(dur=0.16, count=1, seed=name, scuff=0.12 * (i % 3)), loud=-24)
    save("SFX_Steps", steps(), loop=True, lufs=-27.0)
    save("SFX_Whistle", whistle("SFX_Whistle", 0.6, 0.5), loud=-13.0, fade_out=0.03)
    save("SFX_WhistleLong", whistle("SFX_WhistleLong", 1.2, 1.08, f0=2550.0, swell=0.12, settle=1.0), loud=-13.0, fade_out=0.03)
    save("SFX_Spin", spin(), loud=-18.0, fade_in=0.004, fade_out=0.02)
    save("SFX_StiffArm", stiff_arm(), loud=-14.0)
    save("SFX_Juke", juke(), loud=-18.0, fade_out=0.01)
    save("SFX_Fumble", fumble(), loud=-14.0)
    save("SFX_Goalpost", goalpost(), loud=-13.5, fade_out=0.08)


def fury():
    save("SFX_FuryIgnite", fury_ignite(), loud=-10.0, fade_in=0.01, fade_out=0.08)
    save("SFX_FuryLoop", fury_loop(), loop=True, lufs=-20.0)
    save("SFX_FuryEnd", fury_end(), loud=-14.0, fade_out=0.03)
    save("SFX_MeterTick", meter_tick(), loud=-21.0)


def interface():
    save("SFX_UIMove", ui_move(), loud=-22.0, fade_out=0.004)
    save("SFX_UISelect", ui_select(), loud=-17.0, fade_out=0.01)
    save("SFX_UIBack", ui_back(), loud=-19.0, fade_out=0.01)
    save("SFX_UIJoin", ui_join(), loud=-15.0, fade_out=0.03)
    save("SFX_UIReady", ui_ready(), loud=-14.0, fade_out=0.03)
    save("SFX_UIError", ui_error(), loud=-16.0, fade_out=0.01)
    save("SFX_UIPage", ui_page(), loud=-20.0, fade_in=0.003, fade_out=0.01)
    save("SFX_PlayPicked", play_picked(), loud=-13.0, fade_out=0.03)
    save("SFX_Countdown", countdown(False), loud=-16.0, fade_out=0.01)
    save("SFX_CountdownGo", countdown(True), loud=-12.0, fade_out=0.04)


def stingers():
    save("SFX_Touchdown", touchdown(), loud=-11.0, fade_out=0.25)
    save("SFX_FirstDown", first_down(), loud=-12.5, fade_out=0.1)
    save("SFX_Turnover", turnover(), loud=-11.5, fade_out=0.15)
    save("SFX_Sack", sack(), loud=-10.5, fade_out=0.1)
    save("SFX_FieldGoalGood", field_goal_good(), loud=-12.5, fade_out=0.2)
    save("SFX_NoGood", no_good(), loud=-13.5, fade_out=0.1)
    save("SFX_Horn", stadium_horn(), loud=-11.0, fade_out=0.2)
    save("SFX_Fireworks_1", firework("SFX_Fireworks_1", 2.0, bursts=((0.85, 1.0, -0.2),)), loud=-9.5, fade_out=0.25)
    save("SFX_Fireworks_2", firework("SFX_Fireworks_2", 2.4, bursts=((0.9, 0.85, 0.25),), crackle_tail=1.3), loud=-9.5, fade_out=0.25)
    save("SFX_Fireworks_3", firework("SFX_Fireworks_3", 1.7, bursts=((0.42, 0.8, -0.5), (0.78, 1.0, 0.5)), whistle=False),
         loud=-9.5, fade_out=0.25)
    save("SFX_Cannon", cannon(), loud=-8.5, fade_out=0.2)


JOBS = {"football": football, "fury": fury, "interface": interface, "stingers": stingers}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    print("Sound effects")
    for name, fn in JOBS.items():
        if args and not any(a.lower() in name.lower() for a in args):
            continue
        fn()


if __name__ == "__main__":
    main()
