/**
 * Title, lobby, team select, final score and the pause menu (port of FuryHUDMenus.cpp).
 */
import { Director } from '../game/director';
import { FuryInput } from '../game/input';
import { leagueTeams, MaxSeats, MaxSeatsPerTeam, NONE, Option, Vec2 } from './deps';
import { drawFieldGuide } from './guide';
import { drawFilm } from './film';
import { Align, Face, Kit } from './kit';
import { Blaze, Dim, ease, fade, Gold, Good, hex, Ink, inkOn, luminance, rgba, UIButton, White } from './style';

/** FPlatformProperties::SupportsQuit: a browser tab cannot quit itself. */
const SupportsQuit = false;
const pad2 = (n: number) => String(n).padStart(2, '0');
const roundInt = (x: number) => Math.floor(x + 0.5);

export function drawTitle(k: Kit, d: Director): void {
  const T = d.screenTime;
  k.screenShade(fade(Ink, 0.55), fade(Ink, 0.82));

  // The logo punches in, then breathes.
  const In = ease(T / 0.6);
  const scale = d.options.get(Option.ReducedMotion) ? 1 : (1.5 + (1 - 1.5) * In) * (1 + 0.012 * Math.sin(T * 2.1));
  const W = 1240 * scale, H = 620 * scale;
  const logo = d.uiTexture('T_Title');
  if (logo) {
    k.image(logo, 960 - W * 0.5, 400 - H * 0.5, W, H, rgba(1, 1, 1, In));
  } else {
    k.textOutline('4TH & FURY', 960, 260, Face.BlackItalic, 220, Gold, Ink, 8, Align.Center);
  }
  k.text('FOUR DOWNS FOR 30 YARDS   /   THREE SECONDS AFTER THE WHISTLE', 960, 688, Face.Bold, 31, fade(White, In), Align.Center, 140);

  const pads = FuryInput.get().numConnectedGamepads();
  for (let i = 0; i < 2; ++i) {
    const X = 342 + i * 629;
    k.panel(X, 768, 606, 132, i === 0 ? Blaze : Gold, 0.93);
    k.glyph(NONE, i === 0 ? UIButton.A : UIButton.X, X + 38, 802, 54);
    k.text(i === 0 ? 'SET UP MATCH' : 'QUICK SOLO', X + 116, 778, Face.BlackItalic, 52, White);
    k.text(i === 0 ? 'G / K   •   1–8 players, choose teams' : 'F / J   •   Rookie, one-minute quarters', X + 118, 848, Face.SemiBold, 26, Dim);
  }
  if (SupportsQuit) {
    k.prompts(NONE, [[UIButton.Y, 'SETTINGS  (T / I)'], [UIButton.B, 'QUIT GAME  (H / L)']], 960, 933, 30);
  } else {
    k.prompts(NONE, [[UIButton.Y, 'SETTINGS  (T / I)']], 960, 933, 30);
  }
  const devices = pads > 0 ? `${pads} CONTROLLER${pads === 1 ? '' : 'S'}   /   SHARED KEYBOARD` : 'KEYBOARD READY   /   CONNECT CONTROLLERS TO ADD PLAYERS';
  k.text(devices, 960, 994, Face.SemiBold, 23, Dim, Align.Center, 100);
}

export function drawLobby(k: Kit, d: Director): void {
  const T = d.screenTime;
  k.screenShade(fade(Ink, 0.7), fade(Ink, 0.88));
  const In = ease(T / 0.35);
  k.textShadow('PICK A SIDE', 960, 46 - 30 * (1 - In), Face.BlackItalic, 96, White, Align.Center);
  k.text('MOVE LEFT FOR HOME, RIGHT FOR AWAY  -  A SIDE WITH NOBODY ON IT IS PLAYED BY THE COMPUTER', 960, 152, Face.SemiBold, 24, Dim, Align.Center, 120);

  const league = leagueTeams();
  const ColumnY = 210, ColumnH = 640;
  const ColumnX = [70, 720, 1310];
  const ColumnW = [540, 480, 540];
  const Titles = ['HOME', 'WAITING', 'AWAY'];

  for (let column = 0; column < 3; ++column) {
    const side = column === 0 ? 0 : column === 2 ? 1 : NONE;
    const accent = side === NONE ? Dim : hex(league[d.teamPick[side]].primary);
    const X = ColumnX[column], W = ColumnW[column];
    const compact = side === NONE && d.numOnSide(NONE) > 4;
    const RowH = compact ? 68 : 138;
    k.panel(X, ColumnY, W, ColumnH, accent, side === NONE ? 0.5 : 0.84);
    k.text(Titles[column], X + W * 0.5, ColumnY + 14, Face.BlackItalic, 52, side === NONE ? Dim : White, Align.Center);

    let row = 0;
    for (let i = 0; i < MaxSeats; ++i) {
      const seat = d.seats[i];
      if (!seat.joined || seat.side !== side) continue;
      const Y = ColumnY + 86 + row * RowH;
      ++row;
      const color = Director.seatColor(i);
      k.rect(X + 18, Y, W - 36, RowH - 14, fade(color, seat.ready ? 0.3 : 0.14));
      k.rect(X + 18, Y, 8, RowH - 14, color);
      k.seatChip(i, X + 44, Y + (compact ? 6 : 18), compact ? 40 : 62, seat.bot);
      const pad = d.seatPad(i);
      const device = seat.bot ? 'COMPUTER PLAYER' : pad ? pad.label : 'CONTROLLER';
      k.text(device, X + (compact ? 140 : 168), Y + (compact ? 10 : 20), Face.Bold, 30, White, Align.Left, 60);
      if (compact) continue;
      if (side === NONE) {
        k.text('<  HOME      AWAY  >', X + 168, Y + 64, Face.SemiBold, 26, fade(Gold, 0.6 + 0.4 * Math.sin(T * 5)), Align.Left, 80);
      } else if (seat.ready) {
        k.text('READY', X + 168, Y + 60, Face.BlackItalic, 38, Good);
      } else {
        k.glyph(i, UIButton.A, X + 168, Y + 66, 34);
        k.text('READY UP', X + 214, Y + 68, Face.SemiBold, 28, Dim, Align.Left, 80);
      }
    }
    if (side !== NONE) {
      // Open places, or a note that the computer has this side.
      for (; row < MaxSeatsPerTeam; ++row) {
        const Y = ColumnY + 86 + row * RowH;
        k.frame(X + 18, Y, W - 36, RowH - 14, 2, fade(White, 0.07));
        const emptySide = d.numOnSide(side) === 0;
        k.text(emptySide && row === 0 ? 'COMPUTER' : 'OPEN', X + W * 0.5, Y + 36, Face.BoldItalic, 40, fade(Dim, emptySide && row === 0 ? 0.8 : 0.3), Align.Center, 120);
      }
    } else if (row === 0 && d.numJoined() === MaxSeats) {
      k.text('ALL SEATS FILLED', X + W * 0.5, ColumnY + 260, Face.BoldItalic, 40, Dim, Align.Center);
    } else if (row === 0) {
      const pulse = fade(White, 0.5 + 0.3 * Math.sin(T * 4));
      k.text('PRESS', X + W * 0.5 - 60, ColumnY + 250, Face.BoldItalic, 40, pulse, Align.Right);
      k.glyph(NONE, UIButton.A, X + W * 0.5 - 44, ColumnY + 252, 44);
      k.text('TO JOIN', X + W * 0.5 + 14, ColumnY + 250, Face.BoldItalic, 40, pulse);
      k.text('KEYBOARD: G OR K', X + W * 0.5, ColumnY + 314, Face.SemiBold, 24, fade(Dim, 0.8), Align.Center, 120);
    }
  }

  if (d.startCountdown >= 0) {
    const pulse = 0.7 + 0.3 * Math.sin(T * 12);
    k.slant(560, 884, 800, 92, 28, fade(Good, 0.3));
    k.textShadow("EVERYBODY'S IN  -  HERE WE GO", 960, 898, Face.BlackItalic, 56, fade(White, pulse), Align.Center);
  } else {
    k.prompts(d.picker(0), [[UIButton.A, 'JOIN / READY'], [UIButton.B, 'BACK OUT'], [UIButton.Stick, 'CHOOSE SIDE']], 960, 906, 34);
  }
  const pads = FuryInput.get().numConnectedGamepads();
  k.text(`${pads} CONTROLLER${pads === 1 ? '' : 'S'} CONNECTED  -  ${d.numJoined()} OF 8 SEATS TAKEN`, 960, 1000, Face.SemiBold, 24, fade(Dim, 0.9), Align.Center, 160);
}

function drawTeamCard(k: Kit, d: Director, side: number, X: number, Y: number, W: number): void {
  const team = leagueTeams()[d.teamPick[side]];
  const primary = hex(team.primary), secondary = hex(team.secondary);
  const T = d.screenTime;
  const H = 700;
  const locked = d.teamLocked[side];
  const seat = d.picker(side);
  const waiting = side === 1 && seat === d.picker(0) && !d.teamLocked[0];
  const active = !waiting && !locked && d.optionRow[side] === 0;

  k.panel(X, Y, W, H, primary, 0.88);
  // A band of the team's colours across the top.
  k.gradientH(X, Y + 5, W, 112, fade(primary, 0.95), fade(primary, 0.35));
  k.rect(X, Y + 117, W, 6, secondary);
  k.text(side === 0 ? 'HOME' : 'AWAY', X + 26, Y + 18, Face.Bold, 28, inkOn(primary), Align.Left, 300);
  if (seat !== NONE && d.numOnSide(side) > 0) {
    k.seatChip(seat, X + W - 130, Y + 22, 40);
  } else {
    k.seatChip(0, X + W - 150, Y + 22, 40, true);
  }
  k.text(team.city.toUpperCase(), X + 26, Y + 56, Face.SemiBold, 40, inkOn(primary), Align.Left, 160);

  const logo = d.teamLogo(d.teamPick[side]);
  if (logo) k.image(logo, X + W * 0.5 - 130, Y + 136, 260, 260);
  const nameSize = team.name.length > 9 ? 70 : 86;
  k.textShadow(team.name.toUpperCase(), X + W * 0.5, Y + 392, Face.BlackItalic, nameSize, White, Align.Center);

  // Ratings.
  const labels = ['SPEED', 'POWER', 'PASSING', 'DEFENSE'];
  const values = [team.speed, team.power, team.passing, team.defense];
  for (let i = 0; i < 4; ++i) {
    const rowY = Y + 492 + i * 38;
    k.text(labels[i], X + 40, rowY, Face.Bold, 24, Dim, Align.Left, 140);
    for (let n = 0; n < 5; ++n) {
      k.slant(X + 200 + n * 60, rowY + 4, 52, 20, 8, n < values[i] ? (luminance(primary) < 0.04 ? secondary : primary) : fade(White, 0.09));
    }
  }
  k.text(team.motto, X + W * 0.5, Y + 652, Face.BoldItalic, 24, fade(White, 0.75), Align.Center, 40);

  if (locked) {
    k.slant(X + 30, Y + 250, W - 60, 84, 26, fade(Good, 0.92));
    k.text('LOCKED IN', X + W * 0.5 + 12, Y + 258, Face.BlackItalic, 62, Ink, Align.Center);
  } else if (active) {
    // Arrows nudge in and out to say "left and right change this".
    const nudge = 8 * Math.sin(T * 6);
    k.triangle(new Vec2(X - 22 - nudge, Y + 266), new Vec2(X + 6 - nudge, Y + 236), new Vec2(X + 6 - nudge, Y + 296), Gold);
    k.triangle(new Vec2(X + W + 22 + nudge, Y + 266), new Vec2(X + W - 6 + nudge, Y + 236), new Vec2(X + W - 6 + nudge, Y + 296), Gold);
  }
}

export function drawTeams(k: Kit, d: Director): void {
  const T = d.screenTime;
  k.gradientV(0, 0, 1920, 300, fade(Ink, 0.85), fade(Ink, 0));
  k.gradientV(0, 700, 1920, 380, fade(Ink, 0), fade(Ink, 0.9));
  k.textShadow('CHOOSE YOUR TEAMS', 960, 30, Face.BlackItalic, 84, White, Align.Center);

  drawTeamCard(k, d, 0, 60, 150, 560);
  drawTeamCard(k, d, 1, 1300, 150, 560);
  k.textOutline('VS', 960, 150, Face.BlackItalic, 110, Gold, Ink, 6, Align.Center);

  // Match options, owned by whoever picks first.
  const owner = d.picker(0);
  const row = d.optionRow[0];
  const editing = owner !== NONE && !d.teamLocked[0];
  const PX = 690, PY = 800, PW = 540;
  k.panel(PX, PY, PW, 150, Gold, 0.86);
  const secs = roundInt(d.quarterSeconds());
  const quarter = `${Math.trunc(secs / 60)}:${pad2(secs % 60)}`;
  const names = ['QUARTER LENGTH', 'COMPUTER SKILL'];
  const values = [quarter, Director.skillName(d.skillChoice)];
  for (let i = 0; i < 2; ++i) {
    const Y = PY + 22 + i * 60;
    const hot = editing && row === i + 1;
    if (hot) k.rect(PX + 10, Y - 6, PW - 20, 54, fade(Gold, 0.18 + 0.08 * Math.sin(T * 6)));
    k.text(names[i], PX + 30, Y + 4, Face.Bold, 28, hot ? White : Dim, Align.Left, 120);
    k.text(`<  ${values[i]}  >`, PX + PW - 30, Y - 2, Face.BlackItalic, 38, hot ? Gold : White, Align.Right);
  }

  if (d.startCountdown >= 0) {
    k.textOutline('KICKOFF!', 960, 978, Face.BlackItalic, 70, White, Ink, 5, Align.Center);
  } else {
    const activeSide = d.teamLocked[0] ? 1 : 0;
    k.prompts(d.picker(activeSide), [[UIButton.Stick, 'CHANGE'], [UIButton.A, 'LOCK IN'], [UIButton.B, 'BACK']], 960, 990, 32);
  }
}

export function drawFinal(k: Kit, d: Director): void {
  if (d.viewingFilm) { drawFilm(k, d); return; }
  const sim = d.sim;
  const T = d.screenTime;
  k.screenShade(fade(Ink, 0.78), fade(Ink, 0.92));
  const winner = sim.winner();
  const headline = winner === NONE ? 'TIE GAME' : sim.teamInfo(winner).name.toUpperCase() + ' WIN!';
  const accent = winner === NONE ? Gold : hex(sim.teamInfo(winner).primary);
  const In = ease(T / 0.4);
  k.slant(260 - 800 * (1 - In), 40, 1400, 150, 46, fade(accent, 0.9));
  k.textShadow(headline, 960, 48, Face.BlackItalic, 124, inkOn(accent), Align.Center);

  // Scores with emblems.
  for (let team = 0; team < 2; ++team) {
    const info = sim.teamInfo(team);
    const X = team === 0 ? 220 : 1100;
    k.panel(X, 230, 600, 230, hex(info.primary), 0.88);
    const logo = d.teamLogo(sim.teams[team].league);
    if (logo) k.image(logo, X + 22, 256, 180, 180);
    k.text(info.city.toUpperCase(), X + 220, 248, Face.SemiBold, 30, Dim, Align.Left, 160);
    k.text(info.name.toUpperCase(), X + 220, 285, Face.BlackItalic, 50, White);
    k.textShadow(String(sim.teams[team].score), X + 572, 336, Face.BlackItalic, 104, team === winner ? Gold : White, Align.Right);
  }

  // Box score.
  const BX = 220, BY = 490, BW = 1480;
  k.panel(BX, BY, BW, 400, Gold, 0.86);
  const columns = ['1', '2', '3', '4', 'OT', 'PASS YDS', 'RUSH YDS', 'COMP', 'SACKS', 'PICKS', 'BIG HITS'];
  const colX = [420, 480, 540, 600, 668, 800, 950, 1090, 1210, 1320, 1440];
  for (let c = 0; c < 11; ++c) k.text(columns[c], BX + colX[c], BY + 26, Face.Bold, 22, Dim, Align.Right, 100);
  for (let team = 0; team < 2; ++team) {
    const st = sim.teams[team];
    const Y = BY + 64 + team * 62;
    k.rect(BX + 20, Y - 6, 10, 52, hex(sim.teamInfo(team).primary));
    k.text(sim.teamInfo(team).name.toUpperCase(), BX + 46, Y, Face.BoldItalic, 36, White);
    const cells = [String(st.scoreByQuarter[0]), String(st.scoreByQuarter[1]), String(st.scoreByQuarter[2]), String(st.scoreByQuarter[3]),
      sim.overtime ? String(st.scoreByQuarter[4]) : '-', String(Math.trunc(st.passYards)), String(Math.trunc(st.rushYards)),
      `${st.completions}/${st.attempts}`, String(st.sacks), String(st.picks), String(st.bigHits)];
    for (let c = 0; c < 11; ++c) k.text(cells[c], BX + colX[c], Y + 2, Face.Bold, 32, White, Align.Right);
  }

  // Who did what at the table.
  k.text('AT THE CONTROLS', BX + 46, BY + 210, Face.Bold, 22, Dim, Align.Left, 240);
  let shown = 0;
  for (let i = 0; i < MaxSeats; ++i) {
    const seat = sim.seats[i];
    if (!seat.active) continue;
    const X = BX + 46 + (shown % 4) * 360, Y = BY + 246 + Math.trunc(shown / 4) * 70;
    ++shown;
    const chipW = k.seatChip(i, X, Y, 44, d.seats[i].bot);
    k.text(`${seat.touchdowns} TD   ${seat.tackles} TKL   ${seat.picks} INT`, X + chipW + 12, Y + 6, Face.SemiBold, 26, White, Align.Left, 40);
  }
  if (shown === 0) k.text('COMPUTER VS COMPUTER', BX + 46, BY + 250, Face.BoldItalic, 34, fade(White, 0.6));

  const leader = d.film && d.film.bestTeam !== NONE ? d.film.bestTeam : (sim.teams[0].longestTD >= sim.teams[1].longestTD ? 0 : 1);
  const long = sim.teams[leader];
  const roster = sim.teamInfo(leader).roster;
  if (long.longestScorer >= 0 && long.longestScorer < roster.length) {
    const player = roster[long.longestScorer];
    const play = `LONGEST TOUCHDOWN    /    ${long.longestTD} YD ${long.longestType}    /    ${sim.teamInfo(leader).abbr}  #${player.number}  ${player.name.toUpperCase()}`;
    k.text(play, 960, 896, Face.Bold, 29, Gold, Align.Center);
  }
  if (T > 1) {
    if (d.film && d.selectedFilm().ready()) {
      k.prompts(d.picker(0), [[UIButton.A, 'REMATCH'], [UIButton.B, 'CHANGE TEAMS'], [UIButton.Y, d.film.longestTouchdown.ready() ? 'REPLAY TOUCHDOWN' : 'PLAY FILM']], 960, 946, 38);
    } else {
      k.prompts(d.picker(0), [[UIButton.A, 'REMATCH'], [UIButton.B, 'CHANGE TEAMS']], 960, 946, 38);
    }
    if (SupportsQuit) k.prompts(d.picker(0), [[UIButton.X, 'QUIT GAME']], 960, 1013, 26);
  }
}

export function drawPause(k: Kit, d: Director): void {
  k.screenShade(fade(Ink, 0.72));
  if (d.viewingFilm) { drawFilm(k, d); return; }
  if (d.fieldGuide) { drawFieldGuide(k, d); return; }
  k.panel(610, 268, 700, 602, Blaze, 0.94);
  k.textShadow('TIME OUT', 960, 304, Face.BlackItalic, 96, White, Align.Center);
  if (d.pauseSeat !== NONE) {
    k.seatChip(d.pauseSeat, 862, 414, 40);
    k.text('CALLED IT', 944, 418, Face.SemiBold, 28, Dim, Align.Left, 120);
  }
  if (d.confirmPauseAction) {
    const restart = d.pauseCursor === 2;
    k.text(restart ? 'RESTART THIS MATCH?' : 'LEAVE THIS MATCH?', 960, 506, Face.BlackItalic, 52, Gold, Align.Center);
    k.text('The current score will be cleared.', 960, 580, Face.SemiBold, 32, White, Align.Center);
    k.prompts(d.pauseSeat, [[UIButton.A, restart ? 'RESTART' : 'LEAVE'], [UIButton.B, 'CANCEL']], 960, 672, 32);
    return;
  }
  const items = ['BACK TO THE GAME', 'SETTINGS', 'RESTART MATCH', 'RETURN TO TITLE', 'QUIT GAME'];
  for (let i = 0; i < items.length - (SupportsQuit ? 0 : 1); ++i) {
    const Y = 481 + i * 74;
    const hot = d.pauseCursor === i;
    if (hot) k.slant(660, Y - 6, 600, 66, 20, Blaze);
    k.text(items[i], 960 + (hot ? 10 : 0), Y, Face.BlackItalic, 46, hot ? Ink : fade(White, 0.7), Align.Center);
  }
  if (d.film && d.film.last.ready()) {
    k.prompts(d.pauseSeat, [[UIButton.A, 'CHOOSE'], [UIButton.X, 'FIELD GUIDE'], [UIButton.Y, 'PLAY FILM'], [UIButton.B, 'RESUME']], 960, 894, 30);
  } else {
    k.prompts(d.pauseSeat, [[UIButton.A, 'CHOOSE'], [UIButton.X, 'FIELD GUIDE'], [UIButton.B, 'RESUME']], 960, 894, 30);
  }
}

