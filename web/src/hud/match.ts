/**
 * Everything drawn over a match: the score bug, play calling, banners, tags over the athletes
 * (port of FuryHUDMatch.cpp).
 */
import { Director } from '../game/director';
import { Button } from '../game/input';
import {
  BallState, DefPlay, FurySim, Job, MaxSeats, NONE, OffPlay, Option, Phase, PlayKind, PlayType, TeamSize, Team, Vec2, Vec3, Act,
} from './deps';
import { drawSoloHints } from './guide';
import { Align, Face, Kit } from './kit';
import { drawPause } from './menus';
import { Bad, Blaze, Dim, ease, fade, Gold, Good, hex, Ink, inkOn, luminance, rgba, Slate, UIButton, White, type Color } from './style';

const v = (x: number, y: number) => new Vec2(x, y);
const roundInt = (x: number) => Math.floor(x + 0.5);
const clamp = (x: number, lo: number, hi: number) => (x < lo ? lo : x > hi ? hi : x);

function quarterName(quarter: number): string {
  switch (quarter) {
    case 1: return '1ST';
    case 2: return '2ND';
    case 3: return '3RD';
    case 4: return '4TH';
    default: return 'OT';
  }
}

/** A team colour that still reads as a colour on a dark panel. */
function bright(team: Team): Color {
  const primary = hex(team.primary);
  return luminance(primary) < 0.035 ? hex(team.secondary) : primary;
}

/**
 * The stadium's video board (AFuryStadium::BoardTarget in the C++). The HUD redraws it a few times
 * a second when its content changes; the renderer can show `canvas` as a texture and re-upload it
 * whenever `version` changes.
 */
export class BoardState {
  readonly canvas: HTMLCanvasElement;
  readonly kit: Kit;
  version = 0;
  timer = 0;
  lastContent = '';
  lastTime = -1;
  constructor(width = 1024, height = 576) {
    this.canvas = document.createElement('canvas');
    this.canvas.width = width;
    this.canvas.height = height;
    this.kit = new Kit(this.canvas.getContext('2d')!);
  }
}

export function drawMatch(k: Kit, d: Director, board: BoardState | null): void {
  const sim = d.sim;
  drawFieldTags(k, d);
  if (sim.phase === Phase.PlaySelect) {
    drawPlaySelect(k, d);
  } else if (sim.phase === Phase.PatSelect) {
    drawPatSelect(k, d);
  }
  drawScorebug(k, d);
  drawTurbo(k, d);
  drawKickMeter(k, d);
  drawResult(k, d);
  if (d.quickMatch && !d.paused) drawSoloHints(k, d);
  drawBanner(k, d);

  if (d.demo) {
    const pulse = 0.6 + 0.4 * Math.sin(k.now() * 4);
    const small = d.uiTexture('T_TitleSmall');
    if (small) k.image(small, 40, 940, 440, 110, rgba(1, 1, 1, 0.9));
    k.slant(1250, 962, 620, 70, 20, fade(Ink, 0.8));
    k.text('DEMO  -  PRESS', 1290, 972, Face.BlackItalic, 40, fade(White, pulse));
    k.glyph(NONE, UIButton.A, 1556, 974, 44);
    k.text('TO PLAY', 1614, 972, Face.BlackItalic, 40, fade(White, pulse));
  }
  if (d.paused) drawPause(k, d);

  // The stadium's video board gets redrawn a few times a second.
  if (board) {
    const now = k.now();
    board.timer -= board.lastTime < 0 ? 0 : now - board.lastTime;
    board.lastTime = now;
    if (board.timer <= 0) {
      board.timer = 0.25;
      drawBoard(board, d);
    }
  }
}

// ---------------------------------------------------------------------------------------------
// Score bug
// ---------------------------------------------------------------------------------------------

function drawScorebug(k: Kit, d: Director): void {
  const sim = d.sim;
  const Y = 22, H = 82, TeamW = 380, MidW = 210;
  const X0 = 960 - MidW * 0.5 - TeamW - 8;
  const time = k.now();

  for (let team = 0; team < 2; ++team) {
    const info = sim.teamInfo(team);
    const st = sim.teams[team];
    const X = team === 0 ? X0 : 960 + MidW * 0.5 + 8;
    const base = hex(info.primary);
    const deep = rgba(base.r * 0.55, base.g * 0.55, base.b * 0.55);
    k.slantGradient(X, Y, TeamW, H, 22, base, deep);
    k.slant(team === 0 ? X : X + TeamW - 12, Y, 12, H, 22, hex(info.secondary));
    const ink2 = inkOn(base);

    // Emblem, name, score: mirrored for the right-hand team.
    const logoX = team === 0 ? X + 30 : X + TeamW - 104;
    const logo = d.teamLogo(st.league);
    if (logo) k.image(logo, logoX, Y + 4, 74, 74);
    const nameX = team === 0 ? X + 114 : X + TeamW - 122;
    k.text(info.abbr, nameX, Y + 12, Face.BlackItalic, 54, ink2, team === 0 ? Align.Left : Align.Right);
    const scoreX = team === 0 ? X + TeamW - 22 : X + 40;
    k.textShadow(String(st.score), scoreX, Y + 2, Face.BlackItalic, 74, ink2 === Ink ? Ink : White, team === 0 ? Align.Right : Align.Left, 0, ink2 === Ink ? 0 : 3);

    // Point downfield inside the team block, above the Fury gauge. BallTeam follows
    // catches, recoveries and interceptions before the next down is set.
    if (sim.phase !== Phase.GameOver && sim.ballTeam === team) {
      const PX = team === 0 ? X + TeamW - 106 : X + 128;
      const DX = team === 0 ? 1 : -1;
      k.triangle(v(PX, Y + 32), v(PX, Y + 54), v(PX + DX * 14, Y + 43), ink2);
    }

    // Fury meter under the team block.
    const MX = team === 0 ? X + 6 : X + TeamW - 246;
    const fury = st.inFury();
    const glow = fury ? 0.75 + 0.25 * Math.sin(time * 14) : 1;
    k.meter(MX, Y + H + 8, 240, 14, st.fury, fury ? rgba(1, 0.55 * glow, 0.05) : fade(Blaze, 0.9), fade(Ink, 0.75));
    const flame = d.uiTexture('T_Icon_Flame');
    if (flame) {
      const FX = team === 0 ? MX + 250 : MX - 34;
      k.image(flame, FX, Y + H + 1, 28, 28, fury ? rgba(1, 0.7 * glow, 0.1) : fade(Dim, 0.6));
    }
    if (fury) {
      const labelX = team === 0 ? MX + 290 : MX - 46;
      k.textShadow(`FURY x${st.furyPlays}`, labelX, Y + H + 2, Face.BlackItalic, 28, rgba(1, 0.6, 0.1), team === 0 ? Align.Left : Align.Right);
    }
  }

  // Clock.
  const MX = 960 - MidW * 0.5;
  k.slantGradient(MX, Y, MidW, H, 22, fade(Slate, 0.96), fade(Ink, 0.96));
  k.text(sim.overtime ? 'SUDDEN DEATH' : quarterName(sim.quarter), 960 + 11, Y + 6, Face.Bold, sim.overtime ? 20 : 24, Gold, Align.Center, 160);
  const late = sim.quarter >= 4 && sim.clock < 30 && !sim.overtime;
  k.text(sim.overtime ? '--:--' : sim.clockText(), 960 + 9, Y + 24, Face.BlackItalic, 56, late ? rgba(1, 0.35 + 0.3 * Math.sin(time * 8), 0.2) : White, Align.Center);

  // Down and distance.
  if (sim.phase !== Phase.GameOver && sim.phase !== Phase.Celebrate) {
    const down = sim.downText();
    const showSpot = sim.playType === PlayType.Scrimmage || sim.playType === PlayType.Punt || sim.playType === PlayType.FieldGoal;
    const spot = showSpot ? sim.spotText() : '';
    const DW = k.measure(down, Face.BlackItalic, 34).x;
    const SW = !spot ? 0 : k.measure(spot, Face.SemiBold, 28, 80).x + 34;
    const W = DW + SW + 56;
    k.slant(960 - W * 0.5, Y + H + 8, W, 46, 14, fade(Ink, 0.88));
    k.text(down, 960 - W * 0.5 + 34, Y + H + 11, Face.BlackItalic, 34, sim.down === 4 && showSpot ? Gold : White);
    if (spot) {
      k.rect(960 - W * 0.5 + 46 + DW, Y + H + 18, 2, 26, fade(White, 0.25));
      k.text(spot, 960 - W * 0.5 + 62 + DW, Y + H + 15, Face.SemiBold, 28, Dim, Align.Left, 80);
    }
  }
}

// ---------------------------------------------------------------------------------------------
// Banners and small readouts
// ---------------------------------------------------------------------------------------------

function drawBanner(k: Kit, d: Director): void {
  const B = d.banner;
  const age = k.now() - B.start;
  if (age < 0 || age > B.length || !B.title) return;
  // Whip in from the left, hold, whip out to the right.
  const In = ease(age / 0.22);
  const Out = ease((age - (B.length - 0.25)) / 0.25);
  const slide = d.options.get(Option.ReducedMotion) ? 0 : (1 - In) * -900 + Out * 1100;
  const alpha = clamp(In * (1 - Out), 0, 1);
  const titleSize = B.big ? 118 : 62;
  const bandH = B.big ? 150 : 84;
  const Y = B.big ? 250 : 210;
  const titleW = k.measure(B.title, Face.BlackItalic, titleSize).x;
  const W = Math.max(titleW + 220, B.big ? 900 : 560);
  const X = 960 - W * 0.5 + slide;
  const lean = bandH * 0.32;
  const deep = rgba(B.color.r * 0.5, B.color.g * 0.5, B.color.b * 0.5);

  k.slant(X - 26, Y + 12, W + 52, bandH, lean, fade(Ink, 0.85 * alpha));
  k.slantGradient(X, Y, W, bandH, lean, fade(B.color, alpha), fade(deep, alpha));
  // A bright streak that sweeps across once.
  const sweep = clamp(age / 0.5, 0, 1);
  if (sweep < 1) k.slant(X + W * sweep - 40, Y, 80, bandH, lean, fade(White, 0.5 * (1 - sweep)));
  const textColor = inkOn(B.color);
  const pop = B.big ? 1 + 0.06 * Math.max(0, 1 - age / 0.3) : 1;
  if (textColor === Ink) {
    k.text(B.title, 960 + slide + lean * 0.5, Y + (bandH - titleSize * pop * 1.16) * 0.5, Face.BlackItalic, titleSize * pop, fade(Ink, alpha), Align.Center);
  } else {
    k.textShadow(B.title, 960 + slide + lean * 0.5, Y + (bandH - titleSize * pop * 1.16) * 0.5, Face.BlackItalic, titleSize * pop, fade(White, alpha), Align.Center, 0, B.big ? 6 : 3);
  }
  if (B.detail) {
    const detailSize = B.big ? 40 : 28;
    const DW = k.measure(B.detail, Face.Bold, detailSize, 200).x + 80;
    k.slant(960 - DW * 0.5 + slide * 1.15, Y + bandH + 8, DW, detailSize + 22, 14, fade(Ink, 0.9 * alpha));
    k.text(B.detail, 960 + slide * 1.15 + 7, Y + bandH + 14, Face.Bold, detailSize, fade(White, alpha), Align.Center, 200);
  }
}

function drawResult(k: Kit, d: Director): void {
  const sim = d.sim;
  const time = k.now();

  // How the last play went, once the whistle has gone.
  if (sim.phase === Phase.Dead && sim.resultDetail && sim.phaseTime > 0.35 && sim.phaseTime < 2.4
    && !(d.banner.detail === sim.resultDetail && k.now() - d.banner.start < d.banner.length)) {
    const In = ease((sim.phaseTime - 0.35) / 0.25);
    const W = k.measure(sim.resultDetail, Face.BlackItalic, 44).x + 90;
    k.slant(960 - W * 0.5, 814 + 12 * (1 - In), W, 64, 20, fade(Ink, 0.86 * In));
    k.text(sim.resultDetail, 960 + 10, 820 + 12 * (1 - In), Face.BlackItalic, 44, fade(sim.playYards < -0.5 ? rgba(1, 0.45, 0.35) : White, In), Align.Center);
  }

  if (sim.afterWhistle()) {
    const seconds = Math.ceil(FurySim.AfterWhistleSeconds - sim.phaseTime);
    const label = `LATE HITS   ${String(seconds).padStart(2, '0')}`;
    const Y = 898;
    k.slant(800, Y, 320, 44, 14, fade(Ink, 0.9));
    k.text(label, 965, Y + 3, Face.BlackItalic, 32, Gold, Align.Center);
    if (!d.demo) {
      let joined = 0, ready = 0;
      for (let i = 0; i < MaxSeats; ++i) {
        if (!sim.seats[i].active) continue;
        ++joined;
        if (sim.readySeats & (1 << i)) ++ready;
      }
      const next = joined > 1 ? `NEXT PLAY  ${ready}/${joined}` : 'NEXT PLAY';
      k.slant(575, 958, 770, 58, 15, fade(Ink, 0.85));
      k.prompts(d.picker(0), [[UIButton.B, 'SHOVE'], [UIButton.X, 'DIVE / ELBOW'], [UIButton.A, next]], 970, 971, 32);
    }
  }

  // The prompt to snap (or kick), aimed at whoever is calling the shots.
  if (sim.phase === Phase.PreSnap && sim.phaseTime > 0.3) {
    const team = sim.playType === PlayType.Kickoff ? sim.kickingTeam : sim.offense;
    const seat = sim.captain(team);
    if (seat !== NONE) {
      const verb = sim.playType === PlayType.Kickoff ? 'KICK OFF' : sim.playType === PlayType.Punt ? 'SNAP AND PUNT'
        : (sim.playType === PlayType.FieldGoal || sim.playType === PlayType.ExtraPoint) ? 'SNAP IT' : 'HIKE!';
      const pulse = 0.75 + 0.25 * Math.sin(time * 7);
      const routes = (sim.playType === PlayType.Scrimmage || sim.playType === PlayType.TwoPoint)
        && !sim.teams[sim.defense()].human && !!sim.offensePlay();
      const W = k.measure(verb, Face.BlackItalic, 44).x + 230 + (routes ? 260 : 0);
      k.slant(960 - W * 0.5, 940, W, 66, 20, fade(Ink, 0.86));
      let X = 960 - W * 0.5 + 40;
      X += k.seatChip(seat, X, 952, 42) + 12;
      X += k.glyph(seat, UIButton.A, X, 950, 46) + 14;
      X += k.text(verb, X, 946, Face.BlackItalic, 44, fade(White, pulse));
      if (routes) {
        X += 34;
        X += k.glyph(seat, UIButton.LB, X, 956, 34) + 10;
        k.text('HOLD FOR ROUTES', X, 958, Face.Bold, 26, Dim);
      }
    }
  }
}

function drawTurbo(k: Kit, d: Director): void {
  // One turbo gauge per human, home on the left, away on the right.
  const sim = d.sim;
  const count = [0, 0];
  for (let i = 0; i < MaxSeats; ++i) {
    const seat = sim.seats[i];
    if (!seat.active) continue;
    const row = count[seat.team]++;
    const W = 214;
    const X = seat.team === 0 ? 34 : 1920 - 34 - W;
    const Y = 1022 - row * 50;
    k.slant(X, Y, W, 40, 12, fade(Ink, 0.82));
    const pad = d.seatPad(i);
    const covering = !d.seats[i].bot && !!pad && !pad.connected;
    let chipW = k.seatChip(i, X + 8, Y + 5, 30, d.seats[i].bot);
    if (covering) chipW += k.text('CPU', X + chipW + 12, Y + 5, Face.BoldItalic, 24, Gold) + 6;
    const fury = sim.teams[seat.team].inFury();
    const fill = fury ? rgba(1, 0.5, 0.05) : seat.turboSpent ? fade(Bad, 0.9) : rgba(0.25, 0.85, 1);
    k.meter(X + chipW + 14, Y + 12, W - chipW - 34, 16, fury ? 1 : seat.turbo, fill, fade(White, 0.12));
  }
}

function drawKickMeter(k: Kit, d: Director): void {
  const sim = d.sim;
  const kickPlay = sim.playType === PlayType.FieldGoal || sim.playType === PlayType.ExtraPoint;
  if (!kickPlay || (sim.phase !== Phase.Live && sim.phase !== Phase.PreSnap)) return;
  if (!sim.kickMeterLive && !sim.kickLocked) return;
  const kickYards = sim.fieldGoalYards();
  const sweet = (FurySim.CleanKickWidth - FurySim.KickScatter) / FurySim.kickSpread(kickYards);
  const X = 660, Y = 880, W = 600, H = 34;
  k.slant(X - 20, Y - 46, W + 40, H + 66, 16, fade(Ink, 0.86));
  k.text(`${roundInt(kickYards)} YARD ${sim.playType === PlayType.ExtraPoint ? 'EXTRA POINT' : 'FIELD GOAL'}`, 960, Y - 42, Face.Bold, 28, Gold, Align.Center, 160);
  k.rect(X, Y, W, H, fade(Bad, 0.75));
  if (kickYards <= FurySim.MaxKickYards) k.rect(X + W * 0.5 * (1 - sweet), Y, W * sweet, H, Good);
  const needle = sim.kickLocked ? sim.kickAim : sim.kickMeter;
  const NX = X + W * 0.5 * (1 + needle);
  k.rect(NX - 5, Y - 12, 10, H + 24, White);
  k.rect(NX - 2, Y - 12, 4, H + 24, Ink);
  const seat = sim.captain(sim.offense);
  if (seat !== NONE && !sim.kickLocked) {
    k.prompts(seat, [[UIButton.A, kickYards <= FurySim.MaxKickYards ? 'STOP IT IN THE GREEN' : 'KICK  /  OUT OF RANGE']], 960, Y + H + 14, 30);
  }
}

// ---------------------------------------------------------------------------------------------
// Tags that follow athletes
// ---------------------------------------------------------------------------------------------

const PassButtons = [UIButton.A, UIButton.Y, UIButton.X, UIButton.A];

function drawRoutes(k: Kit, d: Director, seat: number): void {
  const sim = d.sim;
  for (const P of sim.players) {
    const runner = P.job.job === Job.Carry || P.job.job === Job.Keeper;
    if (P.team !== sim.offense || (!runner && P.job.job !== Job.Route) || P.path.length === 0) continue;
    const tint = runner ? Blaze : Gold;
    let prev = k.worldToBoard(Vec3.from2(P.p, 8));
    let projected = !!prev;
    for (let i = 0; i < P.path.length; ++i) {
      const next = k.worldToBoard(Vec3.from2(P.path[i], 8));
      if (projected && prev && next) {
        k.line(prev, next, 7, fade(Ink, 0.72));
        k.line(prev, next, 3.5, tint);
        if (i === P.path.length - 1) {
          const dir = next.sub(prev).safeNormal();
          const side = v(-dir.y, dir.x);
          k.triangle(next.add(dir.mul(6)), next.sub(dir.mul(13)).add(side.mul(9)), next.sub(dir.mul(13)).sub(side.mul(9)), tint);
        }
      }
      projected = !!next;
      if (next) prev = next;
    }
    if (!runner && P.passIcon > 0) {
      const tag = k.worldToBoard(Vec3.from2(P.p, 252));
      if (tag) k.glyph(seat, PassButtons[P.passIcon], tag.x - 17, tag.y - 30, 34);
    }
  }
}

function drawFieldTags(k: Kit, d: Director): void {
  const sim = d.sim;
  if (sim.phase === Phase.PlaySelect || sim.phase === Phase.GameOver || sim.phase === Phase.PatSelect) return;
  const time = k.now();
  if (sim.phase === Phase.PreSnap && sim.offensePlay() && !sim.teams[sim.defense()].human &&
    (sim.playType === PlayType.Scrimmage || sim.playType === PlayType.TwoPoint)) {
    const seat = sim.captain(sim.offense);
    const pad = d.seatPad(seat);
    if (pad && pad.isDown(Button.LB)) drawRoutes(k, d, seat);
  }

  // Mark the ball in flight and in loose-ball scrambles. Open corners keep the
  // football itself visible against white yard lines and the crowd.
  const state = sim.ball.state;
  if (sim.phase === Phase.Live && (state === BallState.Pass || state === BallState.Kick ||
    state === BallState.FieldGoal || state === BallState.Loose)) {
    const at = k.worldToBoard(sim.ball.pos);
    if (at) {
      const top = Math.abs(at.x - 960) < 500 ? 186 : 38;
      const safe = v(clamp(at.x, 35, 1885), clamp(at.y, top, 1035));
      if (safe.equals(at, 1)) {
        for (const side of [-1, 1]) {
          const tip = at.add(v(14 * side, 0));
          const A = tip.add(v(5 * side, -7));
          const B = tip.add(v(5 * side, 7));
          k.line(A, tip, 5, Ink); k.line(tip, B, 5, Ink);
          k.line(A, tip, 2, Gold); k.line(tip, B, 2, Gold);
        }
      } else {
        const dir = at.sub(safe).safeNormal();
        const wing = v(-dir.y * 8, dir.x * 8);
        k.triangle(safe.add(wing), safe.sub(wing), safe.add(dir.mul(15)), Gold);
        k.textShadow('BALL', safe.x - dir.x * 20, safe.y - dir.y * 20 - 14, Face.Bold, 23, White, Align.Center);
      }
    }
  }

  // Pass icons: the button that throws to each receiver, when a human is at quarterback.
  if (sim.isPassIconLive()) {
    const QB = sim.offense * TeamSize;
    const qbSeat = sim.players[QB].seat;
    const play = sim.offensePlay();
    if (qbSeat !== NONE && play && play.kind !== PlayKind.Run) {
      for (let slot = 0; slot < TeamSize; ++slot) {
        const P = sim.players[sim.offense * TeamSize + slot];
        if (P.passIcon === 0 || P.down) continue;
        const at = k.worldToBoard(new Vec3(P.p.x, P.p.y, 235));
        if (at) {
          const size = 46;
          const x = clamp(at.x, 40, 1880), y = clamp(at.y, 150, 1000);
          k.glyph(qbSeat, PassButtons[P.passIcon], x - size * 0.5, y - size - 4 * Math.sin(time * 6 + slot), size);
        }
      }
    }
  }

  // "P3" over every athlete a human is steering; an arrow at the screen edge if they are out of shot.
  for (let i = 0; i < MaxSeats; ++i) {
    const seat = sim.seats[i];
    if (!seat.active || seat.player === NONE) continue;
    const P = sim.players[seat.player];
    let tagZ = 205;
    if (sim.afterWhistle() && P.down) {
      let stand = 0;
      if (P.act === Act.Hit) stand = 1 - ease(P.actTime / P.actLength);
      if (P.act === Act.GetUp) stand = ease(P.actTime / P.actLength);
      tagZ = 90 + (205 - 90) * stand;
    }
    const projected = k.worldToBoard(new Vec3(P.p.x, P.p.y, tagZ));
    if (!projected) continue;
    const off = projected.x < 30 || projected.x > 1890 || projected.y < 140 || projected.y > 1050;
    const at = v(clamp(projected.x, 46, 1874), clamp(projected.y, 176, 1040));
    const color = Director.seatColor(i);
    const H = 30;
    const label = `P${i + 1}`;
    const W = k.measure(label, Face.BlackItalic, 24).x + 22;
    const top = at.y - H - 16;
    k.rect(at.x - W * 0.5 - 2, top - 2, W + 4, H + 4, fade(Ink, 0.85));
    k.rect(at.x - W * 0.5, top, W, H, color);
    k.text(label, at.x, top + 1, Face.BlackItalic, 24, inkOn(color), Align.Center);
    const direction = off ? projected.sub(at).safeNormal() : v(0, 1);
    const across = v(-direction.y, direction.x);
    const edge = 1 / Math.max(Math.abs(direction.x) / (W * 0.5), Math.abs(direction.y) / (H * 0.5));
    const base = v(at.x, top + H * 0.5).add(direction.mul(edge + 2));
    k.triangle(base.sub(across.mul(8)), base.add(across.mul(8)), base.add(direction.mul(11)), off ? White : color);
  }

  // A marker over a computer-controlled ball carrier so the ball is never lost in a crowd.
  const carrier = sim.carrierIndex();
  if (carrier !== NONE && sim.players[carrier].seat === NONE && sim.phase === Phase.Live && !sim.isPasser(carrier)) {
    const at = k.worldToBoard(new Vec3(sim.players[carrier].p.x, sim.players[carrier].p.y, 215));
    if (at) {
      const bob = 4 * Math.sin(time * 8);
      const color = bright(sim.teamInfo(sim.players[carrier].team));
      k.triangle(v(at.x - 15, at.y - 30 + bob), v(at.x + 15, at.y - 30 + bob), v(at.x, at.y - 8 + bob), Ink);
      k.triangle(v(at.x - 11, at.y - 28 + bob), v(at.x + 11, at.y - 28 + bob), v(at.x, at.y - 12 + bob), color);
    }
  }
}

// ---------------------------------------------------------------------------------------------
// Calling plays
// ---------------------------------------------------------------------------------------------

/** Maps play space (yards: X downfield, Y to the offense's right) into a card. */
class CardSpace {
  near = -9; far = 21;      // yards behind / beyond the line that the card shows
  constructor(readonly x: number, readonly y: number, readonly w: number, readonly h: number, readonly flip: boolean) {}
  at(yards: Vec2): Vec2 {
    const lateral = this.flip ? -yards.y : yards.y;
    const u = clamp(lateral / 40 + 0.5, 0.03, 0.97);
    const vv = clamp(1 - (yards.x - this.near) / (this.far - this.near), 0.04, 0.97);
    return v(this.x + u * this.w, this.y + vv * this.h);
  }
  /** Card pixels per yard, for sizing zones. */
  scale(): number { return Math.min(this.w / 40, this.h / (this.far - this.near)); }
}

function drawOffenseCard(k: Kit, play: OffPlay, flip: boolean, X: number, Y: number, W: number, H: number, accent: Color): void {
  const space = new CardSpace(X, Y, W, H, flip);
  const routeColor = rgba(1, 0.82, 0.12);
  const runColor = rgba(1, 0.42, 0.1);
  // Line of scrimmage.
  k.line(space.at(v(0, -22)), space.at(v(0, 22)), 2, fade(White, 0.22));

  for (let slot = 0; slot < 7; ++slot) {
    const spot = play.spot[slot];
    const job = play.job[slot];
    const at = space.at(spot);
    const runner = job.job === Job.Carry || job.job === Job.Keeper;

    if (job.path.length > 0 && job.job !== Job.PassBlock && job.job !== Job.RunBlock) {
      const inward = spot.y > 0 ? -1 : 1;
      let prev = at;
      const color = runner ? runColor : job.job === Job.Passer ? fade(White, 0.6) : routeColor;
      for (let i = 0; i < job.path.length; ++i) {
        const step = job.path[i];
        const next = space.at(spot.add(v(step.x, job.inward ? step.y * inward : step.y)));
        k.line(prev, next, runner ? 4.5 : 3.5, color);
        if (i === job.path.length - 1) {
          const dir = next.sub(prev).safeNormal();
          const side = v(-dir.y, dir.x);
          k.triangle(next.add(dir.mul(9)), next.sub(dir.mul(4)).add(side.mul(7)), next.sub(dir.mul(4)).sub(side.mul(7)), color);
        }
        prev = next;
      }
    } else if (job.job === Job.Passer) {
      // Straight drop.
      k.line(at, space.at(spot.add(v(-play.drop, 0))), 2.5, fade(White, 0.45));
    } else if (job.job === Job.Punter || job.job === Job.Kicker) {
      const up = space.at(spot.add(v(26, 0)));
      k.line(at, up, 3.5, routeColor);
      k.triangle(up.add(v(0, -9)), up.add(v(7, 4)), up.add(v(-7, 4)), routeColor);
    }

    // The player: a ring for linemen, a filled dot for everyone else.
    if (slot >= 1 && slot <= 3) {
      k.rect(at.x - 6, at.y - 6, 12, 12, fade(White, 0.85));
    } else {
      k.circle(at, 7.5, Ink, 14);
      k.circle(at, 6, slot === 0 ? accent : White, 14);
    }
  }
}

const Reference = [v(-5, 0), v(-0.4, 0), v(-0.5, -1.8), v(-0.5, 1.8), v(-0.6, -13), v(-0.6, 13), v(-5, 2.4)];

function drawDefenseCard(k: Kit, play: DefPlay, flip: boolean, X: number, Y: number, W: number, H: number, _accent: Color): void {
  const space = new CardSpace(X, Y, W, H, flip);
  space.near = -7;
  space.far = 34;                       // defenses are drawn deeper so the zones fit on the card
  const rushColor = rgba(1, 0.3, 0.2);
  const manColor = rgba(1, 0.82, 0.12);
  const zoneColor = rgba(0.25, 0.6, 1);
  k.line(space.at(v(0, -22)), space.at(v(0, 22)), 2, fade(White, 0.22));

  // A generic offense for reference.
  for (const spot of Reference) k.circle(space.at(spot), 4, fade(White, 0.3), 10);

  for (let slot = 0; slot < 7; ++slot) {
    const job = play.job[slot];
    let spot = play.spot[slot];
    if (job.job === Job.Man && job.target >= 0 && job.target < 7) {
      const receiver = Reference[job.target];
      spot = v(Math.max(job.cushion + 0.4, 1.2), receiver.y * (receiver.x < -2 ? 0.6 : 1));
      k.line(space.at(spot), space.at(receiver), 2, fade(manColor, 0.7));
    }
    const at = space.at(spot);
    if (job.job === Job.Zone) {
      // Kept a little smaller than life so neighbouring zones stay readable.
      const radius = Math.min(job.radius * space.scale() * 0.8, H * 0.3);
      const c = space.at(job.zone);
      const centre = v(clamp(c.x, X + radius + 2, X + W - radius - 2), clamp(c.y, Y + radius + 2, Y + H - radius - 2));
      k.circle(centre, radius, fade(zoneColor, 0.22), 20);
      k.ring(centre, radius, 2, fade(zoneColor, 0.8), 20);
    } else if (job.job === Job.Rush || job.job === Job.Blitz) {
      const to = space.at(v(-4, spot.y * 0.35));
      k.line(at, to, job.job === Job.Blitz ? 4.5 : 3, rushColor);
      const dir = to.sub(at).safeNormal();
      const side = v(-dir.y, dir.x);
      k.triangle(to.add(dir.mul(8)), to.sub(dir.mul(3)).add(side.mul(6)), to.sub(dir.mul(3)).sub(side.mul(6)), rushColor);
    } else if (job.job === Job.Spy) {
      k.ring(at, 12, 2.5, manColor, 16);
    }
    const mark = job.job === Job.Blitz ? rushColor : job.job === Job.Zone ? zoneColor : White;
    k.line(at.add(v(-6, -6)), at.add(v(6, 6)), 3.5, mark);
    k.line(at.add(v(-6, 6)), at.add(v(6, -6)), 3.5, mark);
  }
}

function drawPickPanel(k: Kit, d: Director, team: number, X: number, Y: number, W: number, H: number): void {
  const sim = d.sim;
  const pick = sim.picks[team];
  const info = sim.teamInfo(team);
  const primary = hex(info.primary);
  const offense = team === sim.offense;
  const seat = sim.captain(team);
  const accent = bright(info);
  const time = k.now();

  k.panel(X, Y, W, H, primary, 0.9);
  k.gradientH(X, Y + 5, W, 64, fade(primary, 0.9), fade(primary, 0.25));
  const headInk = inkOn(primary);
  k.text(`${info.abbr}  ${offense ? 'OFFENSE' : 'DEFENSE'}`, X + 22, Y + 12, Face.BlackItalic, 44, headInk);
  if (seat !== NONE) {
    const chipX = X + W - 250;
    k.text('CALLS IT', chipX + 96, Y + 22, Face.Bold, 24, headInk === Ink ? Ink : fade(White, 0.8), Align.Left, 100);
    k.seatChip(seat, chipX, Y + 14, 42);
  } else {
    k.seatChip(0, X + W - 130, Y + 14, 42, true);
  }

  const gridX = X + 20, gridY = Y + 84, gap = 12;
  const cardW = (W - 40 - 2 * gap) / 3;
  const cardH = (H - 84 - 76 - 2 * gap) / 3;

  if (seat === NONE) {
    // The computer does not show its hand.
    const dots = '.'.repeat(1 + (Math.trunc(time * 3) % 3));
    k.text(pick.locked ? 'READY' : 'THINKING' + dots, X + W * 0.5, Y + H * 0.5 - 50, Face.BlackItalic, 96, pick.locked ? Good : fade(White, 0.5), Align.Center);
    return;
  }
  if (pick.locked) {
    // Chosen plays are hidden so the other bench cannot read them off the screen.
    k.slant(X + 60, Y + H * 0.5 - 70, W - 120, 140, 40, Good);
    k.text('PLAY IS IN', X + W * 0.5 + 20, Y + H * 0.5 - 60, Face.BlackItalic, 100, Ink, Align.Center);
    return;
  }

  const seatColor = Director.seatColor(seat);
  for (let cell = 0; cell < 9; ++cell) {
    const CX = gridX + (cell % 3) * (cardW + gap), CY = gridY + Math.trunc(cell / 3) * (cardH + gap);
    const hot = pick.cursor === cell;
    const off = offense ? sim.offenseChoice(pick.page, cell) : null;
    const def = offense ? null : sim.defenseChoice(cell);
    if (!off && !def) {
      k.rect(CX, CY, cardW, cardH, fade(White, 0.03));
      continue;
    }
    k.rect(CX, CY, cardW, cardH, hot ? rgba(0.1, 0.13, 0.1, 0.96) : rgba(0.03, 0.07, 0.045, 0.92));
    if (off) {
      drawOffenseCard(k, off, pick.flip, CX + 6, CY + 4, cardW - 12, cardH - 44, accent);
    } else if (def) {
      drawDefenseCard(k, def, pick.flip, CX + 6, CY + 4, cardW - 12, cardH - 44, accent);
    }
    const name = off ? off.name : def!.name;
    k.rect(CX, CY + cardH - 40, cardW, 40, hot ? seatColor : fade(Ink, 0.9));
    k.text(name, CX + cardW * 0.5, CY + cardH - 37, Face.BoldItalic, 28, hot ? inkOn(seatColor) : White, Align.Center, 20);
    if (hot) {
      const thick = 4 + 1.5 * Math.sin(time * 9);
      k.frame(CX - 2, CY - 2, cardW + 4, cardH + 4, thick, seatColor);
    }
    if (off && off.kind === PlayKind.FieldGoal) {
      const yards = sim.fieldGoalYards();
      const long = yards > FurySim.MaxKickYards;
      const label = `${roundInt(yards)} YD${long ? '  /  OUT OF RANGE' : ''}`;
      k.text(label, CX + 8, CY + 4, Face.Bold, 20, long ? Gold : White);
    } else if (off && off.kind === PlayKind.Run) {
      k.text('RUN', CX + 8, CY + 4, Face.Bold, 18, rgba(1, 0.5, 0.15), Align.Left, 100);
    }
  }

  // What the highlighted play is for, the page, and the buttons.
  const footY = Y + H - 70;
  const hotOff = offense ? sim.offenseChoice(pick.page, pick.cursor) : null;
  const hotDef = offense ? null : sim.defenseChoice(pick.cursor);
  const tagline = hotOff ? hotOff.tagline : hotDef ? hotDef.tagline : '';
  k.text(tagline + (pick.flip ? '   (FLIPPED)' : ''), X + 22, footY, Face.BoldItalic, 26, fade(White, 0.85));
  if (offense) {
    const pages = ['PASS', 'RUN & TRICK', 'KICK'];
    let PX = X + W - 22;
    for (let page = 2; page >= 0; --page) {
      const PW = k.measure(pages[page], Face.Bold, 22, 80).x + 26;
      PX -= PW;
      k.rect(PX, footY - 2, PW - 6, 32, pick.page === page ? accent : fade(White, 0.08));
      k.text(pages[page], PX + (PW - 6) * 0.5, footY, Face.Bold, 22, pick.page === page ? inkOn(accent) : Dim, Align.Center, 80);
    }
    k.prompts(seat, [[UIButton.A, 'CALL IT'], [UIButton.X, 'FLIP'], [UIButton.RB, 'PAGE']], X + W * 0.5, footY + 36, 26);
  } else {
    k.prompts(seat, [[UIButton.A, 'CALL IT'], [UIButton.X, 'FLIP']], X + W * 0.5, footY + 36, 26);
  }
}

function drawPlaySelect(k: Kit, d: Director): void {
  const sim = d.sim;
  const In = ease(sim.phaseTime / 0.3);
  k.screenShade(fade(Ink, 0.45 * In));
  const panelW = 880, panelH = 770, Y = 190 + 60 * (1 - In);
  drawPickPanel(k, d, 0, 40 - 300 * (1 - In), Y, panelW, panelH);
  drawPickPanel(k, d, 1, 1000 + 300 * (1 - In), Y, panelW, panelH);

  // Shared clock between the two panels.
  const anyHuman = sim.captain(0) !== NONE || sim.captain(1) !== NONE;
  if (anyHuman) {
    const left = Math.max(0, sim.selectTimer);
    const centre = v(960, Y + 60);
    k.circle(centre, 40, fade(Ink, 0.92), 28);
    k.ring(centre, 34, 6, left < 4 ? Bad : Gold, 40, 0, clamp(left / 14, 0, 1));
    k.text(String(Math.ceil(left)), 960, centre.y - 22, Face.BlackItalic, 40, White, Align.Center);
  }
}

function drawPatSelect(k: Kit, d: Director): void {
  const sim = d.sim;
  if (sim.scoringTeam === NONE) return;
  const info = sim.teamInfo(sim.scoringTeam);
  const seat = sim.captain(sim.scoringTeam);
  const In = ease(sim.phaseTime / 0.3);
  const X = 500, Y = 360 + 50 * (1 - In), W = 920, H = 330;
  k.screenShade(fade(Ink, 0.4 * In));
  k.panel(X, Y, W, H, hex(info.primary), 0.92);
  k.text('AFTER THE TOUCHDOWN', X + W * 0.5, Y + 20, Face.Bold, 30, Dim, Align.Center, 300);
  const titles = ['KICK IT', 'GO FOR TWO'];
  const notes = ['+1  SAFE', '+2  FROM THE 3'];
  for (let i = 0; i < 2; ++i) {
    const hot = sim.patChoice === i && seat !== NONE;
    const CX = X + 40 + i * 430, CW = 410;
    k.slant(CX, Y + 80, CW, 150, 34, hot ? bright(info) : fade(White, 0.07));
    const textColor = hot ? inkOn(bright(info)) : fade(White, 0.75);
    k.text(titles[i], CX + CW * 0.5 + 17, Y + 88, Face.BlackItalic, 72, textColor, Align.Center);
    k.text(notes[i], CX + CW * 0.5 + 17, Y + 172, Face.Bold, 28, textColor, Align.Center, 160);
  }
  if (seat !== NONE) {
    const chipW = k.seatChip(seat, X + 40, Y + H - 62, 40);
    k.text('DECIDES', X + 40 + chipW + 10, Y + H - 56, Face.Bold, 26, Dim, Align.Left, 120);
    k.prompts(seat, [[UIButton.Stick, 'CHOOSE'], [UIButton.A, 'GO']], X + W * 0.5 + 120, Y + H - 62, 30);
  } else {
    k.text('COMPUTER IS DECIDING...', X + W * 0.5, Y + H - 62, Face.BoldItalic, 34, fade(White, 0.6), Align.Center);
  }
}

// ---------------------------------------------------------------------------------------------
// The stadium's video board
// ---------------------------------------------------------------------------------------------

function drawBoard(board: BoardState, d: Director): void {
  const sim = d.sim;
  const banner = d.banner;
  const k = board.kit;
  k.hud = d;
  const showBanner = !!banner.title && d.now() - banner.start < banner.length;
  const headline = showBanner ? banner.title : sim.downText();
  const foot = sim.overtime ? 'SUDDEN DEATH' : `${quarterName(sim.quarter)}   ${sim.clockText()}`;
  const content = `${sim.teams[0].league}/${sim.teams[1].league}/${sim.teams[0].score}/${sim.teams[1].score}/${showBanner}/${headline}/${foot}`;
  if (content === board.lastContent) return;
  board.lastContent = content;
  // Borrow the kit: point it at the board's canvas.
  const { width, height } = board.canvas;
  k.S = width / 1920;
  k.OX = k.OY = 0;
  k.ctx.clearRect(0, 0, width, height);

  const home = sim.teamInfo(0), away = sim.teamInfo(1);
  k.gradientV(0, 0, 1920, 1080, rgba(0.02, 0.03, 0.07), rgba(0.005, 0.008, 0.02));
  for (let team = 0; team < 2; ++team) {
    const info = team === 0 ? home : away;
    const primary = hex(info.primary);
    const X = team === 0 ? 60 : 1010;
    k.slant(X, 60, 850, 420, 90, primary);
    const logo = d.teamLogo(sim.teams[team].league);
    if (logo) k.image(logo, X + 110, 90, 360, 360);
    k.text(String(sim.teams[team].score), X + 780, 60, Face.BlackItalic, 330, inkOn(primary), Align.Right);
  }
  const maxSize = 235;
  const titleSize = maxSize * Math.min(1, 1780 / Math.max(1, k.measure(headline, Face.BlackItalic, maxSize).x));
  k.text(headline, 960, 648 - titleSize * 0.55, Face.BlackItalic, titleSize, showBanner ? Gold : White, Align.Center);
  k.text(foot, 960, 860, Face.Bold, 120, Dim, Align.Center, 200);
  board.version++;
}

