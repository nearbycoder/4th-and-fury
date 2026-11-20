/**
 * The play film: a top-down replay of the last play (or the longest touchdown) on a chalkboard
 * field, with a scrub bar and the play-by-play (port of FuryHUDFilm.cpp).
 */
import type { Director } from '../game/director';
import { Screen } from '../game/director';
import { EndLineX, NumPlayers, SidelineY, TeamSize, Vec2 } from './deps';
import { Align, Face, Kit } from './kit';
import { Dim, fade, Gold, hex, Ink, inkOn, lerpColor, luminance, rgba, Slate, UIButton, White, type Color } from './style';

const v = (x: number, y: number) => new Vec2(x, y);
const clamp = (x: number, lo: number, hi: number) => (x < lo ? lo : x > hi ? hi : x);

export function drawFilm(k: Kit, d: Director): void {
  const film = d.selectedFilm();
  if (!film.ready()) return;
  const time = d.filmTime;
  const duration = film.duration();
  // Algo::UpperBoundBy: the first frame later than the playhead.
  let upper = 0;
  while (upper < film.frames.length && film.frames[upper].time <= time) ++upper;
  const next = clamp(upper, 1, film.frames.length - 1);
  const aFrame = film.frames[next - 1];
  const bFrame = film.frames[next];
  const alpha = clamp((time - aFrame.time) / (bFrame.time - aFrame.time), 0, 1);
  const active = alpha < 0.5 ? aFrame : bFrame;

  const X = 278, Y = 218, W = 1364, H = 606;
  const at = (p: Vec2) => v(X + W * (0.5 + p.x / (2 * EndLineX)), Y + H * (0.5 + p.y / (2 * SidelineY)));
  k.screenShade(rgba(0.033, 0.045, 0.063), Ink);
  k.text(d.screen === Screen.Final && d.film.longestTouchdown.ready() ? 'LONGEST TOUCHDOWN' : 'PLAY FILM', X, 47, Face.BlackItalic, 82, White);
  const subhead = !film.scoreLine ? `${d.sim.teamInfo(film.offense).abbr}    /    ${film.downText}    /    ${film.result}` : film.scoreLine;
  k.text(subhead, X + 4, 153, Face.Bold, 31, Gold);
  const period = film.quarter > 4 ? 'OT' : `Q${film.quarter}`;
  k.text(period + '    ' + film.clock, X + W, 83, Face.BlackItalic, 48, White, Align.Right);

  const ten = W / 12;
  const fieldA = rgba(0.035, 0.112, 0.088), fieldB = rgba(0.044, 0.135, 0.101);
  const colors: Color[] = [White, White];
  k.rect(X, Y, W, H, fieldA);
  for (let team = 0; team < 2; ++team) {
    const info = d.sim.teamInfo(team);
    const primary = hex(info.primary);
    colors[team] = luminance(primary) < 0.085 ? hex(info.secondary) : primary;
    const start = team === 0 ? X : X + W - ten;
    k.rect(start, Y, ten, H, lerpColor(Ink, primary, 0.7));
    const logo = d.teamLogo(d.sim.teams[team].league);
    if (logo) k.image(logo, start + 8, Y + H * 0.5 - 49, ten - 16, ten - 16);
  }
  for (let yard = 0; yard <= 100; yard += 5) {
    const L = X + ten * (1 + yard * 0.1);
    if (yard % 10 === 0 && yard < 100) k.rect(L, Y, ten * 0.5, H, fieldB);
    const strength = yard % 10 === 0 ? 0.36 : 0.14;
    k.rect(L - 1, Y, 2, H, fade(White, strength));
    if (yard > 0 && yard < 100 && yard % 10 === 0) {
      const label = String(Math.min(yard, 100 - yard));
      for (const edge of [Y + 12, Y + H - 40]) k.text(label, L, edge, Face.BoldItalic, 24, fade(White, 0.5), Align.Center);
    }
  }
  if (film.chains) {
    k.rect(at(v(film.los, 0)).x, Y, 3, H, fade(rgba(0.2, 0.56, 1), 0.85));
    k.rect(at(v(film.toGain, 0)).x, Y, 3, H, fade(Gold, 0.85));
  }
  k.frame(X, Y, W, H, 3, fade(White, 0.8));

  // The trail follows only the ball. All fourteen numbers are the actual jerseys from the snap.
  const ball = at(Vec2.lerp(aFrame.ball, bFrame.ball, alpha));
  let tip = ball;
  for (let j = next - 1; j >= 0 && time - film.frames[j].time < 0.85; --j) {
    const previous = at(film.frames[j].ball);
    k.line(previous, tip, 4.5, fade(Gold, clamp(1 - (time - film.frames[j].time) / 0.85, 0, 1)));
    tip = previous;
  }
  for (let i = 0; i < NumPlayers; ++i) {
    const team = Math.trunc(i / TeamSize);
    const P = at(Vec2.lerp(aFrame.athlete[i], bFrame.athlete[i], alpha));
    const down = (active.down & (1 << i)) !== 0;
    const R = down ? 11 : 14;
    if (i === active.holder) k.ring(P, R + 5, 3, Gold, 24);
    if (team === 0) {
      k.circle(P, R + 2, White, 20);
      k.circle(P, R, colors[team], 20);
    } else {
      k.rect(P.x - R - 2, P.y - R - 2, 2 * R + 4, 2 * R + 4, White);
      k.rect(P.x - R, P.y - R, 2 * R, 2 * R, colors[team]);
    }
    k.text(String(film.number[i]), P.x, P.y - R * 0.88, Face.Black, R * 1.48, inkOn(colors[team]), Align.Center);
  }
  if (active.holder < 0) {
    k.circle(ball, 9, Ink, 20);
    k.circle(ball, 6, Gold, 20);
  }
  const FY = 889;
  const playhead = X + (W * time) / duration;
  const whistle = X + (W * film.whistle) / duration;
  k.rect(X, FY, W, 7, Slate);
  k.rect(X, FY, playhead - X, 7, Gold);
  let call: { athlete: number; action: string } | null = null;
  for (const moment of film.moments) {
    k.rect(X + (W * moment.time) / duration - 1, FY - 4, 2, 4, Dim);
    if (moment.time <= time) call = moment;
  }
  if (call) {
    const i = call.athlete;
    const team = d.sim.teamInfo(Math.trunc(i / TeamSize));
    const entry = team.roster[film.roster[i]];
    const caption = `${call.action}    /    ${team.abbr}  #${film.number[i]}  ${entry ? entry.name.toUpperCase() : ''}`;
    k.text(caption, X, FY - 46, Face.BoldItalic, 30, White);
  }
  k.rect(whistle - 1, FY - 5, 2, 17, White);
  k.circle(v(playhead, FY + 3), 8, Gold, 18);
  k.text('WHISTLE', Math.min(whistle, X + W - 100), FY + 16, Face.Bold, 19, Dim);
  k.text(`${time.toFixed(1)} / ${duration.toFixed(1)} s`, X + W, FY - 46, Face.SemiBold, 28, White, Align.Right);
  k.prompts(d.pauseSeat, [[UIButton.A, d.filmRolling ? 'PAUSE FILM' : time >= duration ? 'PLAY AGAIN' : 'PLAY'], [UIButton.Stick, 'LEFT / RIGHT TO SCRUB'], [UIButton.B, 'BACK']], 960, 964, 34);
}
