# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.5", "scipy==1.18.1"]
# ///
"""4th & Fury -- music (MUS_*.wav). All four pieces are original compositions.

    uv run Audio/make_music.py [name-filter ...]

  MUS_Menu        E minor, 125 BPM, 32 bars: tom-driven intro -> the riff -> a rising brass
                  "chorus" -> riff with the chorus motif on top -> half-time break and a
                  stop-time turnaround that drops straight back into bar 1.
  MUS_PlaySelect  E minor, 120 BPM, 8 bars: ticking, pulsing, sparse.
  MUS_Halftime    E minor 9th groove, 96 BPM, 16 bars, swung.
  MUS_Victory     G major fanfare built on the menu's chorus motif (one-shot).

Loops are rendered as one period of a periodic signal: every note tail, echo and reverb tail
that runs past the last bar wraps round into the first, and every filter / compressor / limiter
on the buses runs in its circular form -- so there is no seam to cross-fade.
"""
import sys

import numpy as np

from fury import catalog
from fury import instruments as ins
from fury.core import (SR, TAU, Timeline, compress, convolve, db2lin, env_points, eq, hp, limiter, lp, n_of, pad_to,
                       periodic_lfo, reverb_ir, rng_for, saturate, saw, shaped_noise, sweep_filter, times, to_stereo,
                       unit_peak)
from fury.parts import band_burst
from fury.wavio import save

hz = ins.hz


class Song:
    """Bar/step clock plus a set of named stereo buses."""

    def __init__(self, name, bpm, bars, loop=True, tail=0.0):
        self.name, self.bpm, self.bars, self.loop = name, bpm, bars, loop
        self.beat = 60.0 / bpm
        self.step = self.beat / 4.0
        self.n = int(round(bars * 4 * self.beat * SR)) + n_of(tail)
        self.rng = rng_for(name)
        self.buses = {}
        self.cache = {}

    def t(self, bar, step=0.0):
        """Seconds at (0-based bar, step in 16ths)."""
        return (bar * 16 + step) * self.step

    def bus(self, name):
        if name not in self.buses:
            self.buses[name] = Timeline(n=self.n, loop=self.loop)
        return self.buses[name]

    def add(self, bus, sig, bar, step=0.0, gain=1.0, pan=0.0, late=0.0):
        self.bus(bus).add(sig, at=self.t(bar, step) + late, gain=gain, pan_pos=pan)

    def cached(self, key, make, variants=3):
        """Round-robin a few renderings of the same note so repeats are not sample-identical."""
        lst = self.cache.setdefault(key, [])
        if len(lst) < variants:
            lst.append(make())
            return lst[-1]
        k = self.cache.setdefault(("idx",) + key, [0])
        k[0] = (k[0] + 1) % variants
        return lst[k[0]]

    def rms_norm(self, bus, target_db):
        """Scale a bus so its RMS (over the whole piece) sits at target_db."""
        b = self.bus(bus).buf
        if not self.loop:
            b = pad_to(b, self.n)                 # one-shots: every bus the same length
        r = np.sqrt(np.mean(b ** 2))
        if r > 0:
            b = b * (db2lin(target_db) / r)
        return b


def swing(step, amount):
    """Delay the off-beat 16ths (odd steps) by amount of a step."""
    return step + (amount if int(round(step)) % 2 == 1 else 0.0)


# ----------------------------------------------------------------------------- shared parts

def drum_kit(song):
    """Render one of each drum (a few variants) for the song."""
    rng = song.rng
    return {
        "kick": [ins.kick(rng) for _ in range(3)],
        "snare": [ins.snare(rng, room=0.45) for _ in range(4)],
        "ghost": [ins.snare(rng, 0.2, wires=1.2, crack=0.4, ring=0.03) for _ in range(3)],
        "hat": [ins.hat(rng) for _ in range(4)],
        "hat_open": [ins.hat(rng, dur=0.4, tau=0.11) for _ in range(2)],
        "tom_hi": [ins.tom(rng, 165.0, 0.4, 0.14) for _ in range(2)],
        "tom_mid": [ins.tom(rng, 120.0, 0.5, 0.18) for _ in range(2)],
        "tom_lo": [ins.tom(rng, 84.0, 0.6, 0.24) for _ in range(2)],
        "crash": [ins.crash(rng, 2.4), ins.crash(rng, 2.0, tau=0.55)],
        "clap": [ins.clap(rng) for _ in range(2)],
        "shaker": [ins.shaker(rng) for _ in range(4)],
    }


def hit(song, kit, name, bar, step, gain=1.0, pan=0.0, bus="drums", late=0.0):
    v = kit[name]
    song.add(bus, v[int(song.rng.integers(len(v)))], bar, step, gain=gain, pan=pan, late=late)


def pattern(song, kit, name, bar, pat, gain=1.0, pan=0.0, accent=1.0, soft=0.55, bus="drums", human=0.004):
    """pat: 16 chars per bar. 'X' accent, 'x' normal, 'o' soft/ghost, '.' rest."""
    for i, c in enumerate(pat):
        if c == ".":
            continue
        g = gain * {"X": accent, "x": 0.8, "o": soft}[c] * song.rng.uniform(0.92, 1.0)
        hit(song, kit, name, bar, i, gain=g, pan=pan, bus=bus, late=song.rng.uniform(0.0, human))


def guitar_take(song, events, take, detune):
    """events: (bar, step, dur_steps, root_hz or None for a muted chug on E, accent 0..1).
    Returns the dry guitar track for one take (mono Timeline buffer)."""
    tl = Timeline(n=song.n, loop=song.loop, channels=1)
    rng = rng_for(song.name + f"gtr{take}")
    for bar, step, dur, root, acc in events:
        mute = 0.85 if root is None else 0.0
        f = hz("E2") if root is None else root
        seconds = dur * song.step * (0.92 if root is not None else 0.8)
        key = ("gtr", take, round(f, 2), round(seconds, 4), mute)
        note = song.cached(key, lambda: ins.power_chord(f, seconds, rng, mute=mute, decay=3.0, detune=detune))
        tl.add(note, at=song.t(bar, step) + rng.uniform(0.0, 0.006), gain=(0.55 if root is None else 1.0) * (0.75 + 0.25 * acc))
    return tl.buf


def guitars(song, events, gain_db=30.0, width=0.85):
    """Double-tracked rhythm guitar: two separately played and amplified takes, hard left/right."""
    out = np.zeros((song.n, 2))
    for take, (det, pos) in enumerate(((-4.0, -width), (5.0, width))):
        dry = guitar_take(song, events, take, det)
        wet = ins.amp(dry, gain_db, circular=song.loop)
        a = (pos + 1.0) * np.pi / 4.0
        out[:, 0] += wet * np.cos(a)
        out[:, 1] += wet * np.sin(a)
    return out


def bass_line(song, events, bus="bass"):
    """events: (bar, step, dur_steps, hz, accent)."""
    for bar, step, dur, f, acc in events:
        seconds = dur * song.step * 0.9
        key = ("bass", round(f, 2), round(seconds, 4))
        note = song.cached(key, lambda: ins.bass_note(f, seconds, song.rng), variants=2)
        song.add(bus, note, bar, step, gain=0.7 + 0.3 * acc)


def brass_hit(song, notes, bar, step, dur_steps, vel=1.0, gain=1.0, bus="brass", players=2, **kw):
    seconds = dur_steps * song.step
    freqs = [hz(x) if isinstance(x, str) else x for x in notes]
    key = ("brass", tuple(round(f, 1) for f in freqs), round(seconds, 4), round(vel, 2), players, tuple(sorted(kw.items())))
    sig = song.cached(key, lambda: ins.brass_section(freqs, seconds, song.rng, vel=vel, players=players, **kw), variants=2)
    song.add(bus, sig, bar, step, gain=gain)


def send_reverb(x, ir, wet_db, loop):
    w = convolve(x, ir, circular=loop)
    if not loop:
        w = pad_to(w, len(x))
    return w * db2lin(wet_db)


def master(song, mix, lufs, glue=True):
    """Bus glue compression, brick-wall limiting, loudness normalisation (all loop-safe)."""
    loop = song.loop
    mix = hp(mix, 36.0, 4, circular=loop)                # nothing a TV or a soundbar can play lives down there
    mix = eq(mix, [("loshelf", 70.0, 0.7, -2.0)], circular=loop)
    if glue:
        mix = compress(mix, thresh_db=-16.0, ratio=2.2, attack=0.012, release=0.16, knee_db=8.0, circular=loop)
    mix = mix / np.max(np.abs(mix))
    mix = saturate(mix * 0.9, 2.5)                       # a touch of tape-style rounding on the peaks
    from fury import measure
    g = db2lin(lufs - measure.lufs_integrated(mix, loop=loop))
    mix = limiter(mix * g, ceiling_db=-1.3, lookahead=0.004, circular=loop)
    return mix


# ----------------------------------------------------------------------------- MUS_Menu

E2, G2, A2, B2, D2, C3, D3 = (hz(x) for x in ("E2", "G2", "A2", "B2", "D2", "C3", "D3"))
M = None                                                  # palm-muted chug on the open low string

# The riff (two bars, 16ths). Top line: E E G . E . D | E E G . A A B B G.
RIFF = [
    [(0, 2, E2, 1.0), (2, 1, M, 0.3), (3, 1, E2, 0.7), (4, 3, G2, 0.9), (7, 1, M, 0.3), (8, 2, E2, 0.9), (10, 1, M, 0.3),
     (11, 1, M, 0.5), (12, 3, D2, 0.9), (15, 1, M, 0.4)],
    [(0, 2, E2, 1.0), (2, 1, M, 0.3), (3, 1, E2, 0.7), (4, 3, G2, 0.9), (7, 1, M, 0.3), (8, 2, A2, 0.9), (10, 1, M, 0.3),
     (11, 1, A2, 0.7), (12, 2, B2, 1.0), (14, 1, B2, 0.7), (15, 1, G2, 0.8)],
]


def menu():
    spec = catalog.MUSIC["MUS_Menu"]
    song = Song("MUS_Menu", spec["bpm"], spec["bars"])
    kit = drum_kit(song)
    rng = song.rng
    gtr = []       # guitar events
    bass = []

    def riff_bars(first_bar, count, with_bass=True):
        for b in range(count):
            for step, dur, root, acc in RIFF[b % 2]:
                gtr.append((first_bar + b, step, dur, root, acc))
                if with_bass:
                    f = (hz("E1") if root is None else root / 2.0)
                    if f < 38.0:
                        f *= 2.0
                    bass.append((first_bar + b, step, dur if root is not None else 0.8, f, acc))

    # ---- A: bars 1-4, tom-driven intro groove, muted guitar, brass hits
    for b in range(0, 4):
        pattern(song, kit, "kick", b, "X.....x.X..x....")
        pattern(song, kit, "snare", b, "....X.......X..." if b < 3 else "....X.......XxXX", gain=0.95)
        pattern(song, kit, "tom_lo", b, "..x.x...x.x.x.x." if b < 3 else "..x.x...x.x.....", gain=0.75, pan=0.35)
        pattern(song, kit, "tom_mid", b, "......x.......x." if b < 3 else "......x.........", gain=0.7, pan=-0.3)
        pattern(song, kit, "hat", b, "x.x.x.x.x.x.x.x.", gain=0.3, pan=0.25)
        for step in range(0, 16, 2):
            acc = 1.0 if step in (0, 6, 12) else 0.4
            root = E2 if step == 0 else M
            if b == 3 and step >= 12:
                continue
            gtr.append((b, step, 2 if step == 0 else 1.6, root, acc))
            bass.append((b, step, 1.7, hz("E1"), acc))
    for step, dur, root in ((12, 1, G2), (13, 1, A2), (14, 2, B2)):          # walk-up into the riff
        gtr.append((3, step, dur, root, 0.9))
        bass.append((3, step, dur, root / 2, 0.9))
    hit(song, kit, "crash", 0, 0, gain=0.9, pan=-0.3)
    brass_hit(song, ["E3", "B3", "E4", "G4", "B4"], 0, 0, 2.2, vib=0.0)
    brass_hit(song, ["E3", "B3", "E4", "G4", "B4"], 2, 0, 2.2, vib=0.0)
    brass_hit(song, ["G3", "D4", "G4"], 3, 12, 0.8, vib=0.0, gain=0.8)
    brass_hit(song, ["A3", "E4", "A4"], 3, 13, 0.8, vib=0.0, gain=0.85)
    brass_hit(song, ["B3", "F#4", "B4"], 3, 14, 1.8, vib=0.0, gain=0.95)

    # ---- B: bars 5-12, the riff (x4). Brass answers from bar 9.
    riff_bars(4, 8)
    for b in range(4, 12):
        odd = (b - 4) % 2 == 1
        pattern(song, kit, "kick", b, "X..x....x.x....." if not odd else "X..x....x..x....")
        pattern(song, kit, "snare", b, "....X.......X..." if not odd else "....X.......X.xx", gain=1.0)
        pattern(song, kit, "hat", b, "x.x.x.x.x.x.x.x.", gain=0.42, pan=0.25)
        if odd:
            hit(song, kit, "hat_open", b, 14, gain=0.4, pan=0.25)
        if b in (4, 8):
            hit(song, kit, "crash", b, 0, gain=0.85, pan=0.3 if b == 4 else -0.3)
    for b in (9, 11):                                                      # brass doubles the turnaround
        for step, dur, nm in ((8, 1.6, "A"), (11, 0.9, "A"), (12, 1.6, "B"), (14, 0.9, "B"), (15, 0.9, "G")):
            lo = {"A": ["A3", "E4", "A4"], "B": ["B3", "F#4", "B4"], "G": ["G3", "D4", "G4"]}[nm]
            brass_hit(song, lo, b, step, dur, vib=0.0, gain=0.9)
    for b in (8, 10):
        brass_hit(song, ["E3", "B3", "E4", "G4"], b, 0, 1.6, vib=0.0, gain=0.9)
        brass_hit(song, ["G3", "D4", "G4", "B4"], b, 4, 2.2, vib=0.0, gain=0.85)

    # ---- C: bars 13-20, "chorus": G - A - C - B (two bars each), brass melody rising in sequence
    chords = [(G2, ["G3", "B3", "D4"]), (A2, ["A3", "C#4", "E4"]), (C3, ["C4", "E4", "G4"]), (B2, ["B3", "D#4", "F#4"])]
    melody = [
        [(0, 6, "D5"), (6, 2, "D5"), (8, 4, "G5"), (12, 4, "B5"), (16, 8, "A5"), (24, 4, "G5"), (28, 4, "D5")],
        [(0, 6, "E5"), (6, 2, "E5"), (8, 4, "A5"), (12, 4, "C#6"), (16, 8, "B5"), (24, 4, "A5"), (28, 4, "E5")],
        [(0, 6, "G5"), (6, 2, "G5"), (8, 4, "C6"), (12, 4, "E6"), (16, 8, "D6"), (24, 4, "C6"), (28, 4, "G5")],
        [(0, 6, "F#5"), (6, 2, "F#5"), (8, 4, "B5"), (12, 4, "D#6"), (16, 12, "F#6")],
    ]
    for k, (root, pad) in enumerate(chords):
        for half in range(2):
            b = 12 + 2 * k + half
            for step in range(0, 16, 2):
                acc = step in (0, 6, 12)
                gtr.append((b, step, 2.0 if acc else 1.5, root if acc else root, 1.0 if acc else 0.35))
                bass.append((b, step, 1.8, root / 2 if root / 2 > 38 else root, 1.0 if acc else 0.5))
            pattern(song, kit, "kick", b, "X.....x.x.....x.")
            pattern(song, kit, "snare", b, "....X.......X..." if half == 0 else "....X.......X.x.", gain=1.0)
            pattern(song, kit, "hat_open", b, "x...x...x...x...", gain=0.32, pan=0.25)
            pattern(song, kit, "hat", b, "..x...x...x...x.", gain=0.35, pan=0.25)
            brass_hit(song, pad, b, 0, 15.0, vel=0.8, gain=0.55, vib=0.003, bus="brass_lo")
        hit(song, kit, "crash", 12 + 2 * k, 0, gain=0.8, pan=-0.3 if k % 2 else 0.3)
        for step, dur, nm in melody[k]:
            f = hz(nm)
            fall = 2.0 if (k == 3 and dur == 12) else 0.0
            brass_hit(song, [f / 2.0, f], 12 + 2 * k + step // 16, step % 16, dur * 0.93, vel=1.0, gain=1.0,
                      vib=0.005 if dur >= 6 else 0.0, fall=fall, bus="lead_brass", players=3)
    for step in (12, 13, 14, 15):                                          # fill out of the chorus
        hit(song, kit, ("tom_hi", "tom_hi", "tom_mid", "tom_lo")[step - 12], 19, step, gain=0.8, pan=(-0.4, -0.2, 0.1, 0.4)[step - 12])

    # ---- D: bars 21-28, riff again with brass on the accents; from bar 25 the chorus motif in E minor on top
    riff_bars(20, 8)
    for b in range(20, 28):
        odd = (b - 20) % 2 == 1
        pattern(song, kit, "kick", b, "X..x....x.x....." if not odd else "X..x....x..x..x.")
        pattern(song, kit, "snare", b, "....X.......X..." if not odd else "....X..o....X.xx", gain=1.0)
        pattern(song, kit, "hat_open", b, "x...x...x...x...", gain=0.3, pan=0.25)
        pattern(song, kit, "hat", b, "..x...x...x...x.", gain=0.36, pan=0.25)
        if b % 2 == 0:
            hit(song, kit, "crash", b, 0, gain=0.8, pan=0.3 if b % 4 == 0 else -0.3)
        brass_hit(song, ["E3", "B3", "E4"], b, 0, 1.6, vib=0.0, gain=0.8)
        brass_hit(song, ["G3", "D4", "G4"], b, 4, 2.2, vib=0.0, gain=0.75)
        if odd:
            for step, dur, lo in ((8, 1.6, ["A3", "E4", "A4"]), (11, 0.9, ["A3", "E4", "A4"]), (12, 1.6, ["B3", "F#4", "B4"]),
                                  (14, 0.9, ["B3", "F#4", "B4"]), (15, 0.9, ["G3", "D4", "G4"])):
                brass_hit(song, lo, b, step, dur, vib=0.0, gain=0.85)
    motif = [(0, 6, "B5"), (6, 2, "B5"), (8, 4, "E6"), (12, 4, "G6"), (16, 8, "F#6"), (24, 4, "E6"), (28, 4, "B5")]
    for rep in range(2):
        for step, dur, nm in motif:
            f = hz(nm) / 2.0
            sig = song.cached(("lead", nm, dur), lambda: ins.lead(f, dur * song.step * 0.95, rng), variants=1)
            song.add("lead", sig, 24 + 2 * rep + step // 16, step % 16, gain=1.0, pan=-0.15)
            song.add("lead", sig, 24 + 2 * rep + step // 16, step % 16 + 3.0, gain=0.28, pan=0.5)      # dotted-8th echo

    # ---- E: bars 29-32, half-time break (C, D), stop-time on B, roll back into bar 1
    for b, root, pad in ((28, C3, ["C4", "E4", "G4", "C5"]), (29, D3, ["D4", "F#4", "A4", "D5"])):
        gtr.append((b, 0, 14.0, root, 1.0))
        bass.append((b, 0, 14.0, root / 2, 1.0))
        hit(song, kit, "kick", b, 0, gain=1.0)
        hit(song, kit, "crash", b, 0, gain=0.8, pan=0.3 if b == 28 else -0.3)
        hit(song, kit, "snare", b, 8, gain=1.0)
        pattern(song, kit, "tom_lo", b, "....x.x.....x.xx", gain=0.75, pan=0.35)
        pattern(song, kit, "tom_mid", b, "..........x.....", gain=0.7, pan=-0.3)
        brass_hit(song, pad, b, 0, 14.0, vel=0.85 + 0.15 * (b - 28), gain=0.8 + 0.2 * (b - 28), vib=0.004)
    stops = [(30, 0, 3.0), (30, 6, 3.0), (30, 12, 2.5), (31, 0, 2.5), (31, 4, 2.5)]
    for b, step, dur in stops:
        gtr.append((b, step, dur, B2, 1.0))
        bass.append((b, step, dur, B2 / 2, 1.0))
        hit(song, kit, "kick", b, step, gain=1.0)
        hit(song, kit, "snare", b, step, gain=0.9)
        hit(song, kit, "crash", b, step, gain=0.45, pan=0.3 if step % 8 == 0 else -0.3)
        brass_hit(song, ["B3", "D#4", "F#4", "B4"], b, step, dur * 0.8, vib=0.0, gain=1.0)
    for i in range(16):                                                    # snare roll 16ths -> 32nds, swelling
        step = 8 + i * 0.5
        if i < 8 and i % 2 == 1:
            continue
        hit(song, kit, "ghost" if i < 8 else "snare", 31, step, gain=0.35 + 0.045 * i)
    for step, nm in ((12, "tom_hi"), (13, "tom_mid"), (14, "tom_lo"), (15, "tom_lo")):
        hit(song, kit, nm, 31, step, gain=0.85, pan=(-0.4, -0.1, 0.3, 0.4)[step - 12])
    rise_n = n_of(8 * song.step)
    tt = times(rise_n)
    rise = shaped_noise(rise_n, rng, tilt_db_oct=1.0, lo=1500.0, hi=14000.0) * (tt / tt[-1]) ** 3
    song.add("fx", rise, 31, 8, gain=0.5)
    brass_hit(song, ["B3", "F#4", "B4", "D#5", "F#5"], 31, 8, 7.5, vel=1.0, gain=0.9, vib=0.0, scoop=0.12)

    # ---- render buses
    song.bus("gtr").buf += guitars(song, gtr)
    bass_line(song, bass)
    hall = reverb_ir(1.5, seed=71, pre_delay=0.02, hf_mult=0.5, build=0.015, stereo=True)
    drums = song.rms_norm("drums", -17.5)
    drums = drums + send_reverb(hp(drums, 300.0, 2, circular=True), hall, -19.0, True)
    drums = compress(drums, thresh_db=-20.0, ratio=3.0, attack=0.02, release=0.12, makeup_db=3.0, circular=True)
    gt = song.rms_norm("gtr", -20.5)
    bs = saturate(song.rms_norm("bass", -20.0) * 2.0, 3.0) * 0.5
    bs = lp(bs, 3500.0, 2, circular=True)
    br = song.rms_norm("brass", -23.5)
    br = br + send_reverb(br, hall, -11.0, True)
    brl = song.rms_norm("brass_lo", -28.0)
    brl = brl + send_reverb(brl, hall, -9.0, True)
    lb = song.rms_norm("lead_brass", -22.0)
    lb = lb + send_reverb(lb, hall, -10.0, True)
    ld = song.rms_norm("lead", -27.0)
    ld = ld + send_reverb(ld, hall, -10.0, True)
    fx = song.bus("fx").buf * 0.25
    return master(song, drums + gt + bs + br + brl + lb + ld + fx, -15.0)


# ----------------------------------------------------------------------------- MUS_PlaySelect

def play_select():
    spec = catalog.MUSIC["MUS_PlaySelect"]
    song = Song("MUS_PlaySelect", spec["bpm"], spec["bars"])
    kit = drum_kit(song)
    rng = song.rng
    hall = reverb_ir(2.0, seed=73, pre_delay=0.03, hf_mult=0.45, build=0.03, stereo=True)
    n = song.n
    # pulse: muted bass on 8ths, the bite opening and closing once over the loop
    roots = ["E1"] * 3 + ["G1"] + ["E1"] * 2 + ["C2", "B1"]
    for b in range(8):
        f0 = hz(roots[b])
        for step in range(0, 16, 2):
            f = f0 * (2.0 if step in (6, 14) else 1.0)
            pos = (b * 16 + step) / 128.0
            pluck = 0.35 + 0.65 * (0.5 - 0.5 * np.cos(TAU * pos))
            note = ins.bass_note(f, song.step * 1.3, rng, pluck=pluck, drive=4.0)
            song.add("bass", note, b, step, gain=1.0 if step % 4 == 0 else 0.7)
        if b in (3, 7):
            song.add("bass", ins.bass_note(f0 * (1.122 if b == 3 else 0.944), song.step * 1.6, rng), b, 15, gain=0.8)
    # kit: no backbeat -- kick, rim, a clock
    for b in range(8):
        pattern(song, kit, "kick", b, "X.........x....." if b % 2 == 0 else "X.....x...x.....", gain=0.95)
        pattern(song, kit, "hat", b, "o.x.o.x.o.x.o.xo", gain=0.26, pan=0.3)
        for step in (4, 12):
            rim = ins.snare(rng, 0.12, tone=420.0, wires=0.15, crack=1.2, ring=0.02)
            song.add("drums", rim, b, step, gain=0.5, pan=-0.2)
        for beat in range(4):                                             # tick ... tock
            f = 1900.0 if beat % 2 == 0 else 1500.0
            m = n_of(0.06)
            tick = np.sin(TAU * f * times(m)) * np.exp(-times(m) / 0.006) + 0.5 * band_burst(m, rng, 3000.0, 9000.0, 0.002, 0.0002)
            song.add("tick", tick, b, beat * 4, gain=0.5, pan=-0.45 if beat % 2 == 0 else 0.45)
    for step, nm, g in ((12, "tom_mid", 0.5), (13, "tom_mid", 0.6), (14, "tom_lo", 0.75), (15, "tom_lo", 0.9)):
        hit(song, kit, nm, 7, step, gain=g, pan=0.2)
    song.add("drums", ins.timpani(rng, hz("E2"), 2.0, tau=0.9), 0, 0, gain=0.75)
    song.add("drums", ins.timpani(rng, hz("C2") * 2, 2.0, tau=0.9), 4, 0, gain=0.6)
    # pad: E minor add 9 -> C major 7 -> B (tension back to bar 1)
    pads = [(0, 4, ["E3", "B3", "F#4", "G4"]), (4, 2, ["C3", "G3", "E4", "B4"]), (6, 2, ["B2", "F#3", "D#4", "A4"])]
    for b0, bars, notes in pads:
        m = int(round(bars * 16 * song.step * SR))
        t = times(m)
        pad = np.zeros((m, 2))
        for nm in notes:
            for det, pos in ((-7.0, -0.6), (6.0, 0.6)):
                f = hz(nm) * 2 ** (det / 1200.0)
                v = lp(saw(f, m, start=rng.random()) + saw(f * 1.002, m, start=rng.random()), 950.0, 2)
                a = (pos + 1.0) * np.pi / 4.0
                pad[:, 0] += v * np.cos(a)
                pad[:, 1] += v * np.sin(a)
        env = env_points(m, [(0.0, 0.0), (0.8, 1.0), (m / SR - 0.6, 0.8), (m / SR, 0.0)])
        trem = 1.0 + 0.18 * np.sin(TAU * t * (song.bpm / 60.0) * 2.0)          # throbs in 8ths
        song.bus("pad").add(pad * (env * trem)[:, None], at=song.t(b0))
    # low brass: two ominous steps
    brass_hit(song, ["E2", "E3"], 2, 0, 11.0, vel=0.8, gain=0.8, vib=0.0)
    brass_hit(song, ["F2", "F3"], 2, 12, 16.0, vel=0.9, gain=0.9, vib=0.0, fall=0.5)
    brass_hit(song, ["G2", "G3"], 6, 0, 7.0, vel=0.85, gain=0.8, vib=0.0)
    brass_hit(song, ["F#2", "F#3"], 6, 8, 7.0, vel=0.9, gain=0.85, vib=0.0)
    brass_hit(song, ["B1", "B2", "F#3"], 7, 0, 14.0, vel=1.0, gain=0.95, vib=0.0)
    # swell into the downbeat
    rise_n = n_of(16 * song.step)
    tt = times(rise_n)
    rise = shaped_noise(rise_n, rng, tilt_db_oct=0.0, lo=900.0, hi=12000.0) * (tt / tt[-1]) ** 2.5
    song.add("fx", rise, 7, 0, gain=1.0, pan=0.0)

    drums = song.rms_norm("drums", -20.0)
    drums = drums + send_reverb(hp(drums, 200.0, 2, circular=True), hall, -15.0, True)
    bs = song.rms_norm("bass", -19.5)
    tick = song.rms_norm("tick", -30.0)
    tick = tick + send_reverb(tick, hall, -8.0, True)
    pad = song.rms_norm("pad", -27.0)
    pad = pad + send_reverb(pad, hall, -8.0, True)
    br = song.rms_norm("brass", -25.0)
    br = br + send_reverb(br, hall, -8.0, True)
    fx = song.rms_norm("fx", -34.0)
    return master(song, drums + bs + tick + pad + br + fx, -16.0, glue=False)


# ----------------------------------------------------------------------------- MUS_Halftime

def halftime():
    spec = catalog.MUSIC["MUS_Halftime"]
    song = Song("MUS_Halftime", spec["bpm"], spec["bars"])
    kit = drum_kit(song)
    rng = song.rng
    hall = reverb_ir(1.3, seed=75, pre_delay=0.02, hf_mult=0.5, build=0.02, stereo=True)
    sw = 0.3                                                                # swung 16ths
    lay = 0.012                                                             # backbeat sits behind the beat
    prog = [  # (bass root, approach note into the next chord, keys voicing)
        ("E2", "D#2", ["G3", "B3", "D4", "F#4"]),          # Em9
        ("A1", "B1", ["G3", "C#4", "F#4", "B4"]),          # A13
        ("C2", "C#2", ["E3", "G3", "B3", "D4"]),           # Cmaj9
        ("B1", "D#2", ["A3", "D#4", "G4", "D5"]),          # B7(#9, b13)
    ]
    for rep in range(2):
        for k, (root, appr, voicing) in enumerate(prog):
            for half in range(2):
                b = rep * 8 + k * 2 + half
                f = hz(root)
                # bass: root, octave pop, a ghosted return, and an approach into the next bar
                line = [(0, 3.0, f, 1.0), (3, 1.0, f * 2, 0.6), (6, 2.0, f, 0.8), (10, 1.0, f, 0.6), (11, 1.5, f * 1.4983, 0.7)]
                if half == 1:
                    line += [(14, 1.0, f * 2, 0.6), (15, 1.0, hz(appr), 0.8)]
                else:
                    line += [(14, 1.5, f * 1.7818, 0.7)]
                for step, dur, ff, acc in line:
                    note = ins.bass_note(ff, dur * song.step * 0.85, rng, pluck=0.6, drive=3.0)
                    song.add("bass", note, b, swing(step, sw), gain=0.7 + 0.3 * acc)
                # keys: syncopated stabs
                comp = [(0, 5.0, 0.8), (7, 1.5, 0.6), (10, 3.5, 0.75)] if half == 0 else [(0, 2.0, 0.7), (3, 4.0, 0.8), (10, 2.0, 0.65), (14, 1.5, 0.6)]
                for step, dur, vel in comp:
                    for i, nm in enumerate(voicing):
                        key = ("ep", nm, round(dur, 2), vel)
                        v = song.cached(key, lambda: ins.epiano(hz(nm), dur * song.step, rng, vel=vel), variants=1)
                        song.add("keys", v, b, swing(step, sw), gain=0.8, pan=-0.5 + 0.33 * i, late=0.004 * i)
                # drums
                kick = "X......x..x....." if half == 0 else "X.....x...x....x"
                for i, c in enumerate(kick):
                    if c != ".":
                        hit(song, kit, "kick", b, swing(i, sw), gain=1.0 if c == "X" else 0.8)
                for step in (4, 12):
                    hit(song, kit, "snare", b, step, gain=0.85, late=lay)
                    hit(song, kit, "clap", b, step, gain=0.45, late=lay + 0.006)
                for i in range(16):
                    g = (0.5 if i % 4 == 0 else 0.36 if i % 2 == 0 else 0.2) * rng.uniform(0.85, 1.0)
                    if half == 1 and i == 14:
                        hit(song, kit, "hat_open", b, i, gain=0.38, pan=0.3)
                    else:
                        hit(song, kit, "hat", b, swing(i, sw), gain=g, pan=0.3)
                    if i % 2 == 0:
                        hit(song, kit, "shaker", b, swing(i + 1, sw), gain=0.22, pan=-0.4)
                if half == 1 and k == 3:
                    for step, nm in ((13, "ghost"), (14.5, "ghost"), (15, "tom_mid")):
                        hit(song, kit, nm, b, swing(step, sw) if step == 15 else step, gain=0.5)
    # second half: a muted-horn line answering the chords
    phrases = [
        [(2, 2, "B4"), (4, 2, "D5"), (6, 6, "E5"), (16, 3, "G5"), (19, 3, "F#5"), (22, 2, "E5"), (24, 6, "D5")],
        [(2, 2, "C#5"), (4, 2, "E5"), (6, 6, "F#5"), (16, 3, "A5"), (19, 3, "F#5"), (22, 2, "E5"), (24, 6, "C#5")],
        [(2, 2, "E5"), (4, 2, "G5"), (6, 6, "B5"), (16, 3, "A5"), (19, 3, "G5"), (22, 2, "E5"), (24, 6, "D5")],
        [(2, 2, "D#5"), (4, 2, "F#5"), (6, 8, "A5"), (18, 2, "F#5"), (20, 2, "D#5"), (22, 7, "B4")],
    ]
    for k, ph in enumerate(phrases):
        for step, dur, nm in ph:
            v = ins.brass(hz(nm), dur * song.step * 0.9, rng, vel=0.55, bright=0.45, vib=0.006, attack=0.035, release=0.09)
            song.add("horn", v, 8 + 2 * k + step // 16, swing(step % 16, sw), gain=1.0, pan=0.15)
    # warm organ bed under the second half
    for k, (root, appr, voicing) in enumerate(prog):
        m_dur = 30.0 * song.step
        for nm in voicing[:3]:
            v = ins.organ(hz(nm), m_dur, rng, bars=(0.0, 0.0, 1.0, 0.4, 0.0, 0.15, 0.0, 0.0, 0.0), click=0.0, release=0.2)
            v *= env_points(len(v), [(0.0, 0.0), (0.5, 1.0), (m_dur, 0.9), (len(v) / SR, 0.0)])
            song.add("organ", v, 8 + 2 * k, 0, gain=1.0, pan=-0.2)

    drums = song.rms_norm("drums", -19.0)
    drums = drums + send_reverb(hp(drums, 400.0, 2, circular=True), hall, -20.0, True)
    bs = lp(song.rms_norm("bass", -19.0), 2800.0, 2, circular=True)
    keys = song.rms_norm("keys", -23.0)
    keys = eq(keys, [("hp", 150.0, 0.7, 0.0), ("peak", 2200.0, 1.0, 2.0)], circular=True)
    keys = keys + send_reverb(keys, hall, -12.0, True)
    horn = song.rms_norm("horn", -25.0)
    horn = horn + send_reverb(horn, hall, -8.0, True)
    org = song.rms_norm("organ", -31.0)
    org = org + send_reverb(org, hall, -10.0, True)
    return master(song, drums + bs + keys + horn + org, -16.5)


# ----------------------------------------------------------------------------- MUS_Victory

def victory():
    bpm = 132.0
    song = Song("MUS_Victory", bpm, 4, loop=False, tail=0.6)
    kit = drum_kit(song)
    rng = song.rng
    hall = reverb_ir(2.1, seed=77, pre_delay=0.03, hf_mult=0.5, build=0.02, stereo=True)

    def tune(notes, bar, beat, beats, vel=1.0, gain=1.0, **kw):
        brass_hit(song, notes, bar, beat * 4.0, beats * 4.0 * 0.93, vel=vel, gain=gain, players=3, **kw)

    def octaves(nm):
        f = hz(nm)
        return [f / 2.0, f]

    # bar 1 (G): the menu's chorus motif, in the major: D . D G B
    tune(octaves("D5"), 0, 0.0, 1.5, vib=0.0)
    tune(octaves("D5"), 0, 1.5, 0.5, vib=0.0)
    tune(octaves("G5"), 0, 2.0, 1.0, vib=0.0)
    tune(octaves("B5"), 0, 3.0, 1.0, vib=0.0)
    tune(["G2", "G3", "B3", "D4"], 0, 0.0, 3.9, vel=0.85, gain=0.8, bus="brass_lo")
    # bar 2 (C): answer, up a step in the sequence: E . E G C
    tune(octaves("E5"), 1, 0.0, 1.5, vib=0.0)
    tune(octaves("E5"), 1, 1.5, 0.5, vib=0.0)
    tune(octaves("G5"), 1, 2.0, 1.0, vib=0.0)
    tune(octaves("C6"), 1, 3.0, 1.0, vib=0.0)
    tune(["C3", "G3", "C4", "E4"], 1, 0.0, 3.9, vel=0.9, gain=0.8, bus="brass_lo")
    # bar 3 (D): held dominant, kettledrum roll, then three pick-ups
    tune(octaves("D6"), 2, 0.0, 2.7, vib=0.006)
    tune(["D3", "A3", "D4", "F#4", "A4"], 2, 0.0, 2.8, vel=0.95, gain=0.85, bus="brass_lo")
    for k in range(3):
        tune(["D4", "D5", "F#5", "A5"], 2, 3.0 + k / 3.0, 0.3, vib=0.0, gain=0.95)
        hit(song, kit, "snare", 2, (3.0 + k / 3.0) * 4.0, gain=0.6 + 0.12 * k)
    # bar 4 (G): the big chord, then the button
    tune(["G4", "B4", "D5", "G5", "B5", "D6"], 3, 0.0, 2.45, vib=0.006, gain=1.1)
    tune(["G2", "G3", "D4", "G4"], 3, 0.0, 2.45, vel=1.0, gain=0.95, bus="brass_lo")
    tune(["G3", "G4", "B4", "D5", "G5", "D6"], 3, 2.75, 0.3, vib=0.0, gain=1.15)
    tune(["G2", "G3"], 3, 2.75, 0.3, vib=0.0, gain=0.9, bus="brass_lo")
    # percussion
    for bar, beat, nm, g in ((0, 0.0, "G2", 1.0), (0, 2.0, "G2", 0.7), (0, 3.0, "D3", 0.7), (1, 0.0, "C3", 0.95), (1, 2.0, "C3", 0.7),
                             (1, 3.0, "G2", 0.7), (2, 0.0, "D3", 1.0), (3, 0.0, "G2", 1.1), (3, 2.75, "G2", 1.1)):
        song.add("perc", ins.timpani(rng, hz(nm), 1.6, tau=0.7), bar, beat * 4.0, gain=g, pan=0.15)
    for bar, beat in ((0, 0.0), (1, 0.0), (2, 0.0), (3, 0.0), (3, 2.75)):
        hit(song, kit, "kick", bar, beat * 4.0, gain=1.0)
        hit(song, kit, "snare", bar, beat * 4.0, gain=0.8)
    for bar, beat, pos in ((0, 0.0, -0.3), (2, 0.0, 0.3), (3, 0.0, -0.3), (3, 2.75, 0.3)):
        hit(song, kit, "crash", bar, beat * 4.0, gain=0.75, pan=pos)
    for bar, beat0, beats in ((2, 0.0, 2.9), (3, 0.0, 2.6)):                 # rolls
        k = 0
        tt = 0.0
        while tt < beats:
            g = 0.25 + 0.5 * tt / beats
            song.add("perc", ins.timpani(rng, hz("D3" if bar == 2 else "G2"), 0.6, tau=0.3), bar, (beat0 + tt) * 4.0, gain=g,
                     pan=0.3 if k % 2 else -0.1)
            if k % 2 == 0:
                hit(song, kit, "ghost", bar, (beat0 + tt) * 4.0, gain=0.25 + 0.35 * tt / beats)
            tt += 0.16
            k += 1
    for k, nm in enumerate(("G6", "B6", "D7", "G7", "D7", "B6", "G6")):       # bells over the last chord
        song.add("bell", ins.bell(hz(nm), 1.2, rng, tau=0.4), 3, k * 1.3, gain=0.5, pan=-0.6 + 0.2 * k)

    br = song.rms_norm("brass", -19.0)
    br = br + send_reverb(br, hall, -10.0, False)
    brl = song.rms_norm("brass_lo", -23.0)
    brl = brl + send_reverb(brl, hall, -10.0, False)
    perc = song.rms_norm("perc", -22.0)
    perc = perc + send_reverb(perc, hall, -12.0, False)
    drums = song.rms_norm("drums", -21.0)
    drums = drums + send_reverb(hp(drums, 300.0, 2), hall, -14.0, False)
    bell = song.rms_norm("bell", -34.0)
    bell = bell + send_reverb(bell, hall, -8.0, False)
    return master(song, br + brl + perc + drums + bell, -14.0)


JOBS = {
    "MUS_Menu": lambda: save("MUS_Menu", menu(), loop=True, lufs=-15.0),
    "MUS_PlaySelect": lambda: save("MUS_PlaySelect", play_select(), loop=True, lufs=-16.0),
    "MUS_Halftime": lambda: save("MUS_Halftime", halftime(), loop=True, lufs=-16.5),
    "MUS_Victory": lambda: save("MUS_Victory", victory(), lufs=-14.0, fade_out=0.35),
}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    print("Music")
    for name, fn in JOBS.items():
        if args and not any(a.lower() in name.lower() for a in args):
            continue
        fn()


if __name__ == "__main__":
    main()
