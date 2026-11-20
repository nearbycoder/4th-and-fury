/**
 * The field guide (pause menu) and the quick-solo hints (port of FuryHUDGuide.cpp).
 */
import type { Director } from '../game/director';
import { BallState, Job, NONE, Phase } from './deps';
import { Align, Face, Kit } from './kit';
import { Blaze, Dim, fade, Gold, Ink, Slate, UIButton, White } from './style';

const { A, B, X, Y, Start, Stick, Turbo } = UIButton;

export function drawFieldGuide(k: Kit, d: Director): void {
  const seat = d.pauseSeat;
  k.panel(204, 105, 1512, 864, Blaze, 0.97);
  k.text('FIELD GUIDE', 256, 132, Face.BlackItalic, 80, White);
  k.text('Four downs to gain 30 yards. A full Fury meter gives your team three plays of unlimited turbo.', 258, 239, Face.SemiBold, 31, Dim);

  const heads = ['WITH THE BALL', 'ON DEFENSE', 'AFTER THE WHISTLE'];
  const buttons: UIButton[][] = [[A, B, X, Y], [A, B, X, Y], [B, X, A, Turbo]];
  const labels = [
    ['Spin past a tackle', 'Stiff-arm', 'Dive forward', 'Hurdle'],
    ['Switch defender', 'Big hit', 'Diving tackle', 'Jump to swat'],
    ['Shove an opponent', 'Dive or drop an elbow', 'Vote for the next play', 'Hold with shove for a big hit'],
  ];
  for (let column = 0; column < 3; ++column) {
    const left = 258 + column * 475;
    k.rect(left, 324, 438, 4, Blaze);
    k.text(heads[column], left, 343, Face.ExtraBoldItalic, 40, Gold);
    for (let row = 0; row < 4; ++row) {
      const top = 424 + row * 80;
      const w = k.glyph(seat, buttons[column][row], left, top, 36);
      k.text(labels[column][row], left + w + 12, top - 1, Face.SemiBold, 29, White);
    }
  }
  k.rect(258, 762, 1404, 2, Slate);
  k.text('At quarterback, press the button above a receiver to throw. Hold turbo while moving to sprint.', 258, 785, Face.Medium, 30, White);
  k.prompts(seat, [[B, 'BACK'], [Start, 'RESUME']], 960, 892, 32);
}

export function drawSoloHints(k: Kit, d: Director): void {
  const sim = d.sim;
  if (sim.phase !== Phase.Live || sim.playCount > 3 || sim.kickMeterLive || sim.kickLocked) return;
  const seat = sim.seats[0];
  if (!seat.active || seat.player === NONE) return;
  const P = sim.players[seat.player];
  const returner = sim.ball.state === BallState.Kick && P.job.job === Job.Returner;
  k.slant(548, 949, 824, 63, 15, fade(Ink, 0.93));
  if (sim.isPasser(seat.player)) {
    k.text('PASS   /   PRESS THE BUTTON ABOVE A RECEIVER', 960, 960, Face.Bold, 32, White, Align.Center);
  } else if (P.hasBall || returner) {
    k.prompts(0, [[Stick, P.team === 0 ? 'RUN RIGHT' : 'RUN LEFT'], [Turbo, 'SPRINT'], [A, 'SPIN']], 954, 965, 31);
  } else if (P.team !== sim.ballTeam || sim.ball.state === BallState.Kick) {
    k.prompts(0, [[A, 'SWITCH'], [B, 'BIG HIT'], [X, 'DIVE TACKLE']], 960, 965, 31);
  } else {
    k.prompts(0, [[Stick, 'MOVE'], [X, 'JUMP FOR BALL'], [B, 'SHOVE']], 960, 965, 31);
  }
}
