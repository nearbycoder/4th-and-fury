/**
 * Play film: a top-down recording of the last play (and the longest touchdown) for the pause menu
 * and the final screen (port of FFuryPlayFilm / FFuryFilmRecorder, FuryFilm.cpp).
 *
 * The director calls recorder.record(sim) once per frame after stepping the sim (not in demo mode)
 * and recorder.reset() when a match starts. Playback (TickFilm in FuryDirectorMatch.cpp) moves
 * director.filmTime; the HUD reads film.frameAt(filmTime) (the interpolation FuryHUDFilm.cpp does
 * inline) and film.momentAt(filmTime) for the caption.
 */
import { Ev, NONE, NumPlayers, Phase, PlayType, Vec2 } from '../sim/core';
import type { FurySim } from '../sim/index';

export interface FilmFrame {
  time: number;
  athlete: Vec2[];      // NumPlayers positions, field space (cm)
  ball: Vec2;
  down: number;         // bitmask: bit i set while athlete i is on the ground
  holder: number;       // ball carrier, or NONE
}

export interface FilmMoment { time: number; athlete: number; action: string }

/** What the film shows at a moment: athletes and ball interpolated between the two nearest frames. */
export interface FilmView {
  athletes: Vec2[];
  ball: Vec2;
  /** Carrier from the nearer frame, or NONE when the ball is loose / in the air. */
  holder: number;
  /** Down bitmask from the nearer frame. */
  down: number;
  /** Index of the later of the two frames (Algo::UpperBound, clamped to 1..frames-1); the ball trail walks back from next - 1. */
  next: number;
  alpha: number;
}

export class PlayFilm {
  frames: FilmFrame[] = [];
  moments: FilmMoment[] = [];
  downText = '';
  result = '';
  scoreLine = '';
  clock = '';
  quarter = 0;
  offense = 0;
  los = 0;
  toGain = 0;
  whistle = -1;
  chains = false;
  number: number[] = new Array(NumPlayers).fill(0);
  roster: number[] = new Array(NumPlayers).fill(0);

  ready(): boolean { return this.frames.length >= 2 && this.whistle >= 0; }
  duration(): number { return this.frames.length === 0 ? 0 : this.frames[this.frames.length - 1].time; }

  /** A copy that later recording cannot change (frames themselves are never mutated). */
  clone(): PlayFilm {
    const f = new PlayFilm();
    Object.assign(f, this);
    f.frames = this.frames.slice();
    f.moments = this.moments.slice();
    f.number = this.number.slice();
    f.roster = this.roster.slice();
    return f;
  }

  /** Adds a frame of the sim at the given film time (at most one per 45 ms unless forced). */
  sample(sim: FurySim, time: number, force = false): void {
    // The football simulation limits live plays to 30 s and the whistle window to 3 s.
    const n = this.frames.length;
    if (n > 0 && (time <= this.frames[n - 1].time || (!force && time < this.frames[n - 1].time + 0.045))) return;
    if (n >= 760) return;
    const athlete: Vec2[] = new Array(NumPlayers);
    let down = 0;
    for (let i = 0; i < NumPlayers; ++i) {
      const p = sim.players[i];
      athlete[i] = p.p;
      if (p.down) down |= 1 << i;
    }
    const holder = sim.carrierIndex();
    const ball = holder >= 0 ? athlete[holder] : new Vec2(sim.ball.pos.x, sim.ball.pos.y);
    this.frames.push({ time, athlete, ball, down, holder });
  }

  /** Interpolated view at a film time (FuryHUDFilm.cpp). Requires ready(). */
  frameAt(time: number): FilmView {
    const frames = this.frames;
    if (frames.length === 0) {
      return { athletes: new Array(NumPlayers).fill(Vec2.Zero), ball: Vec2.Zero, holder: NONE, down: 0, next: 0, alpha: 0 };
    }
    if (frames.length === 1) {
      const f = frames[0];
      return { athletes: f.athlete.slice(), ball: f.ball, holder: f.holder, down: f.down, next: 0, alpha: 0 };
    }
    // Upper bound: first frame with time > the film time.
    let lo = 0, hi = frames.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (frames[mid].time <= time) lo = mid + 1; else hi = mid;
    }
    const next = Math.min(Math.max(lo, 1), frames.length - 1);
    const a = frames[next - 1], b = frames[next];
    const span = b.time - a.time;
    const alpha = span > 0 ? Math.min(Math.max((time - a.time) / span, 0), 1) : 1;
    const active = alpha < 0.5 ? a : b;
    const athletes = a.athlete.map((p, i) => Vec2.lerp(p, b.athlete[i], alpha));
    return { athletes, ball: Vec2.lerp(a.ball, b.ball, alpha), holder: active.holder, down: active.down, next, alpha };
  }

  /** The latest moment at or before the film time (the HUD's caption), or null. */
  momentAt(time: number): FilmMoment | null {
    let call: FilmMoment | null = null;
    for (const m of this.moments) if (m.time <= time) call = m;
    return call;
  }
}

const MomentLabels = new Map<Ev, string>([
  [Ev.Throw, 'THROW'], [Ev.Catch, 'CATCH'], [Ev.Handoff, 'HANDOFF'], [Ev.Intercept, 'INTERCEPTION'],
  [Ev.BigHit, 'BIG HIT'], [Ev.Tackle, 'TACKLE'], [Ev.Fumble, 'FUMBLE'], [Ev.Recover, 'RECOVERY'],
  [Ev.LateHit, 'LATE HIT'], [Ev.Touchdown, 'TOUCHDOWN'],
  [Ev.Kickoff, 'KICK'], [Ev.PuntKick, 'KICK'], [Ev.FieldGoalKick, 'KICK'],
]);

/** Retains the last completed play while its successor is being recorded. */
export class FilmRecorder {
  last = new PlayFilm();
  current = new PlayFilm();
  longestTouchdown = new PlayFilm();
  play = NONE;
  bestYards = -1;
  bestTeam = NONE;
  wasLive = false;
  whistled = false;
  keepTouchdown = false;

  reset(): void {
    this.last = new PlayFilm();
    this.current = new PlayFilm();
    this.longestTouchdown = new PlayFilm();
    this.play = NONE;
    this.bestYards = -1;
    this.bestTeam = NONE;
    this.wasLive = false;
    this.whistled = false;
    this.keepTouchdown = false;
  }

  record(sim: FurySim): void {
    // Kickoffs do not count as a scrimmage snap in the box score.
    const start = !this.wasLive || this.play !== sim.playCount;
    this.wasLive = sim.phase === Phase.Live;
    if (this.keepTouchdown && (!sim.afterWhistle() || this.play !== sim.playCount)) {
      // Copy once after the late hits have finished.
      this.longestTouchdown = this.last.clone();
      this.keepTouchdown = false;
    }
    if (sim.phase === Phase.Live) {
      if (start) {
        const c = this.current;
        this.play = sim.playCount;
        this.whistled = false;
        c.frames = [];
        c.moments = [];
        c.downText = sim.downText();
        c.quarter = sim.quarter;
        c.offense = sim.playType === PlayType.Kickoff ? sim.kickingTeam : sim.offense;
        c.los = sim.losX;
        c.toGain = sim.firstDownX;
        c.chains = sim.playType === PlayType.Scrimmage || sim.playType === PlayType.Punt || sim.playType === PlayType.FieldGoal;
        c.whistle = -1;
        for (let i = 0; i < NumPlayers; ++i) {
          c.number[i] = sim.rosterOf(sim.players[i]).number;
          c.roster[i] = sim.players[i].roster;
        }
      }
      this.current.sample(sim, sim.liveTime);
    } else if (sim.afterWhistle() && this.play === sim.playCount) {
      if (!this.whistled) {
        const c = this.current;
        c.whistle = sim.liveTime;
        c.result = sim.resultTitle === '' ? sim.resultDetail : sim.resultTitle;
        c.scoreLine = sim.phase === Phase.Celebrate ? sim.resultDetail : '';
        c.clock = sim.clockText();
        c.sample(sim, sim.liveTime, true);
        this.current = this.last;
        this.last = c;
        this.whistled = true;
      }
      this.last.sample(sim, sim.liveTime + sim.phaseTime);
    } else {
      return;
    }
    const film = this.whistled ? this.last : this.current;
    for (const e of sim.events) {
      const label = MomentLabels.get(e.type);
      if (e.type === Ev.Touchdown) {
        const yards = Math.floor(e.value + 0.5);
        if (yards > this.bestYards) {
          this.bestYards = yards;
          this.bestTeam = e.team;
          this.keepTouchdown = true;
        }
      }
      if (label && e.player >= 0 && e.player < NumPlayers && film.moments.length < 50) {
        film.moments.push({ time: sim.liveTime + (this.whistled ? sim.phaseTime : 0), athlete: e.player, action: label });
      }
    }
  }
}
