/**
 * Match flow: setting up plays, choosing them, downs, scoring, quarters (port of FurySim.cpp).
 * The live action is in simPlay.ts and the computer players' decisions are in simAI.ts.
 */
import {
  Act, Ball, BallState, Dir, DefenseSlot0, Ev, EndLineX, FMath, GoalX, HashY, Job, KickerSlot, MaxSeats, NONE, NumPlayers,
  OffenseSlot0, OffPlay, DefPlay, Phase, Pick, PlayKind, PlaysPerPage, PlayType, Pos, Seat, SeatInput, SidelineY, SimEvent,
  SimPlayer, Stance, TeamSize, TeamState, Vec2, Vec3, WorldX, Yard, YardLine, AngleOf, PI, cloneOffPlay, cloneDefPlay, cloneJob, makeJob,
} from './core';
import { Playbook } from './playbook';
import { FurySim } from './sim';

const SelectSeconds = 14;
const LineupSeconds = 1.5;
const FirstDownYards = 30;

function ordinal(n: number): string {
  switch (n) { case 1: return '1ST'; case 2: return '2ND'; case 3: return '3RD'; default: return '4TH'; }
}

const P = FurySim.prototype;

// ---------------------------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------------------------

P.emit = function (this: FurySim, type: Ev, team = NONE, player = NONE, other = NONE, value = 0): void {
  const event: SimEvent = {
    type,
    team,
    player,
    other,
    value,
    pos: player !== NONE ? new Vec3(this.players[player].p.x, this.players[player].p.y, 0) : this.ball.pos,
  };
  if (other !== NONE && player !== NONE &&
    (type === Ev.Tackle || type === Ev.BigHit || type === Ev.Shove || type === Ev.LateHit)) {
    const v = this.players[other];
    const pad = v.p.add(this.players[player].p.sub(v.p).safeNormal().mul(15));
    event.pos = Vec3.from2(pad, this.players[player].act === Act.Dive || this.players[player].act === Act.Tackle ? 85 : 120);
    if (type === Ev.LateHit) { this.whistleFocus = pad; }
  }
  this.events.push(event);
};

P.toWorld = function (this: FurySim, playSpaceYards: Vec2): Vec2 {
  const d = this.offenseDir();
  return new Vec2(this.losX + d * playSpaceYards.x * Yard, this.ballY + d * playSpaceYards.y * Yard);
};

P.clampToField = function (this: FurySim, point: Vec2, margin = 60): Vec2 {
  return new Vec2(FMath.clamp(point.x, -EndLineX + margin, EndLineX - margin), FMath.clamp(point.y, -SidelineY + margin, SidelineY - margin));
};

P.yardsToGo = function (this: FurySim): number {
  return Math.max(0, (this.firstDownX - this.losX) * this.offenseDir() / Yard);
};

P.goalToGo = function (this: FurySim): boolean {
  return this.firstDownX * this.offenseDir() >= GoalX - 1;
};

/** "2ND & 14", "1ST & GOAL", "KICKOFF". */
P.downText = function (this: FurySim): string {
  switch (this.playType) {
    case PlayType.Kickoff: return this.kickPossessed && this.ballTeam !== this.kickingTeam ? 'KICK RETURN' : 'KICKOFF';
    case PlayType.Punt: if (this.kickPossessed && this.ballTeam !== this.offense) { return 'PUNT RETURN'; } break;
    case PlayType.ExtraPoint: return 'EXTRA POINT';
    case PlayType.TwoPoint: return '2-POINT TRY';
    default: break;
  }
  if (this.goalToGo()) {
    return `${ordinal(this.down)} & GOAL`;
  }
  const toGo = Math.max(1, FMath.ceilToInt(this.yardsToGo() - 0.05));
  return `${ordinal(this.down)} & ${toGo}`;
};

/** "OWN 35", "OPP 12", "50". */
P.spotText = function (this: FurySim): string {
  const line = FMath.roundToInt(YardLine(this.offense, this.losX));
  if (line === 50) {
    return '50';
  }
  return line < 50 ? `OWN ${Math.max(line, 1)}` : `OPP ${Math.max(100 - line, 1)}`;
};

P.clockText = function (this: FurySim): string {
  const total = Math.max(0, FMath.ceilToInt(this.clock - 0.001));
  return `${Math.trunc(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};

P.winner = function (this: FurySim): number {
  return this.teams[0].score === this.teams[1].score ? NONE : (this.teams[0].score > this.teams[1].score ? 0 : 1);
};

/** Seat index calling plays for a team, or NONE (computer). */
P.captain = function (this: FurySim, team: number): number {
  // The play-caller rotates among a team's humans every drive, so everyone gets a turn.
  const seated: number[] = [];
  for (let i = 0; i < MaxSeats; ++i) {
    if (this.seats[i].active && this.seats[i].team === team) {
      seated.push(i);
    }
  }
  return seated.length === 0 ? NONE : seated[this.teamDrives[team] % seated.length];
};

P.isPassIconLive = function (this: FurySim): boolean {
  if (this.phase !== Phase.Live && this.phase !== Phase.PreSnap) {
    return false;
  }
  if (this.playType !== PlayType.Scrimmage && this.playType !== PlayType.TwoPoint) {
    return false;
  }
  return !this.passThrown && !this.ballCrossedLine && !this.changeOfPossession;
};

/** True while this athlete is a quarterback holding the ball behind the line, able to throw. */
P.isPasser = function (this: FurySim, index: number): boolean {
  const p = this.players[index];
  const scrimmage = this.playType === PlayType.Scrimmage || this.playType === PlayType.TwoPoint;
  return p.hasBall && scrimmage && p.team === this.offense && p.slot === 0 && !this.passThrown && !this.changeOfPossession
    && this.currentOff.kind !== PlayKind.Run && (p.p.x - this.losX) * this.offenseDir() < 0 && (this.phase === Phase.Live || this.phase === Phase.PreSnap);
};

/** The offense choices on a pick page (regular pages, then the kicking page). Shared objects: read-only. */
P.offenseChoice = function (this: FurySim, page: number, cell: number): OffPlay | null {
  const all = Playbook.offense();
  if (page < 2) {
    const index = page * PlaysPerPage + cell;
    return index >= 0 && index < all.length ? all[index] : null;
  }
  // The kicking page. Kicks make no sense on a two-point try.
  if (this.playType === PlayType.TwoPoint) {
    return null;
  }
  return cell === 0 ? Playbook.punt() : cell === 1 ? Playbook.fieldGoal() : null;
};

P.defenseChoice = function (this: FurySim, cell: number): DefPlay | null {
  const all = Playbook.defense();
  return cell >= 0 && cell < all.length ? all[cell] : null;
};

P.addFury = function (this: FurySim, team: number, amount: number): void {
  const state = this.teams[team];
  if (state.inFury() || this.phase === Phase.GameOver) {
    return;
  }
  state.fury = FMath.clamp(state.fury + amount, 0, 1);
  if (state.fury >= 1) {
    state.furyPlays = 3;
    this.emit(Ev.FuryStart, team);
  }
};

P.tickFuryAfterPlay = function (this: FurySim): void {
  for (let team = 0; team < 2; ++team) {
    const state = this.teams[team];
    if (this.furyAtSnap[team] && state.furyPlays > 0) {
      --state.furyPlays;
      state.fury = state.furyPlays / 3;
      if (state.furyPlays === 0) {
        this.emit(Ev.FuryEnd, team);
      }
    }
  }
};

// ---------------------------------------------------------------------------------------------
// Match setup
// ---------------------------------------------------------------------------------------------

P.setSeat = function (this: FurySim, index: number, active: boolean, team: number): void {
  const seat = new Seat();
  seat.active = active;
  seat.team = team;
  this.seats[index] = seat;
};

P.startMatch = function (this: FurySim, homeLeague: number, awayLeague: number, quarterSeconds: number, cpuSkill: number, seed: number): void {
  this.random.initialize(seed);
  for (let team = 0; team < 2; ++team) {
    this.teams[team] = new TeamState();
    this.teams[team].league = team === 0 ? homeLeague : awayLeague;
    this.teams[team].human = false;
  }
  for (const seat of this.seats) {
    if (seat.active) {
      this.teams[seat.team].human = true;
    }
  }
  this.quarterLength = quarterSeconds;
  this.clock = quarterSeconds;
  this.quarter = 1;
  this.cpuSkill = cpuSkill;
  this.overtime = false;
  this.twoMinuteCalled = false;
  this.playCount = 0;
  this.driveCount = 0;
  this.teamDrives[0] = this.teamDrives[1] = 0;
  this.clockExpired = false;
  this.pendingScoreTeam = NONE;
  this.scoringTeam = this.scorer = NONE;
  this.events.length = 0;
  for (let i = 0; i < NumPlayers; ++i) {
    // Reset in place so the player objects keep their identity (C++ assigns into the array slot).
    const p = Object.assign(this.players[i], new SimPlayer());
    p.team = Math.trunc(i / TeamSize);
    p.slot = i % TeamSize;
    // Start everyone on their own sideline so the first lineup has somewhere to come from.
    p.p = new Vec2((p.team === 0 ? -1 : 1) * (600 + 150 * p.slot), -SidelineY + 200);
  }
  for (const row of this.trail) { row.fill(Vec2.Zero); }
  this.openingKicker = this.random.randRange(0, 1);
  this.beginKickoff(this.openingKicker, 35);
};

/** Test hook: jump straight to a field-goal try by newOffense from the given yard line (0..100 from its own goal). */
P.debugFieldGoal = function (this: FurySim, newOffense: number, yardsFromOwnGoal: number): void {
  this.offense = newOffense;
  this.ballTeam = newOffense;
  this.playType = PlayType.FieldGoal;
  this.losX = WorldX(newOffense, yardsFromOwnGoal);
  this.ballY = 0;
  this.down = 4;
  this.firstDownX = this.offenseDir() * GoalX;
  this.currentOff = cloneOffPlay(Playbook.fieldGoal());
  this.currentDef = cloneDefPlay(Playbook.kickBlock());
  this.haveOffPlay = this.haveDefPlay = true;
  this.setupPlay();
  this.enter(Phase.Lineup);
};

P.enter = function (this: FurySim, newPhase: Phase): void {
  this.phase = newPhase;
  this.phaseTime = 0;
};

// ---------------------------------------------------------------------------------------------
// Units and line-ups
// ---------------------------------------------------------------------------------------------

// Return unit: a linebacker and the linemen up front, receivers in the middle, the back deep.
const ReturnRoster = [DefenseSlot0 + 3, 1, 2, 3, 4, 5, 6];

/** Puts the right seven athletes on the field for each team and gives them their base ratings. */
P.placeUnits = function (this: FurySim, offenseUnit: boolean[]): void {
  for (let team = 0; team < 2; ++team) {
    const info = this.teamInfo(team);
    for (let slot = 0; slot < TeamSize; ++slot) {
      const p = this.players[this.global(team, slot)];
      p.roster = offenseUnit[team] ? OffenseSlot0 + slot : DefenseSlot0 + slot;
      const kickPlay = this.playType === PlayType.FieldGoal || this.playType === PlayType.ExtraPoint || this.playType === PlayType.Punt;
      if (offenseUnit[team] && kickPlay && slot === 0) {
        p.roster = KickerSlot;
      }
      if (this.playType === PlayType.Kickoff) {
        if (team === this.kickingTeam) {
          p.roster = slot === 0 ? KickerSlot : DefenseSlot0 + slot;
        } else {
          p.roster = ReturnRoster[slot];
        }
      }
      p.pos = info.roster[p.roster].pos;

      // Ratings 1..5 nudge the base numbers a few percent either way.
      const speedBias = (info.speed - 3) * 0.022;
      const powerBias = (info.power - 3) * 0.08;
      let base = 760;
      p.radius = 42;
      p.power = 0.5 + powerBias;
      p.hands = 0.9;
      switch (p.pos) {
        case Pos.QB: base = 735; p.power = 0.38 + powerBias; break;
        case Pos.OL: base = 610; p.power = 0.82 + powerBias; p.radius = 52; p.hands = 0.6; break;
        case Pos.DL: base = 650; p.power = 0.8 + powerBias; p.radius = 52; p.hands = 0.6; break;
        case Pos.WR: base = 800; p.power = 0.4 + powerBias; p.hands = 0.93 + (info.passing - 3) * 0.012; break;
        case Pos.RB: base = 790; p.power = 0.62 + powerBias; p.hands = 0.88; break;
        case Pos.LB: base = 755; p.power = 0.68 + powerBias; p.hands = 0.72; break;
        case Pos.CB: base = 795; p.power = 0.42 + powerBias; p.hands = 0.78 + (info.defense - 3) * 0.02; break;
        case Pos.S: base = 785; p.power = 0.55 + powerBias; p.hands = 0.8 + (info.defense - 3) * 0.02; break;
        case Pos.K: base = 700; p.power = 0.3; p.hands = 0.7; break;
      }
      p.topSpeed = base * (1 + speedBias);
    }
  }
};

// Which athletes the team's humans take, in order of importance.
const OffenseRoles = [0, 4, 5, 6];
const DefenseRoles = [3, 6, 4, 5];
const KickRoles = [0, 3, 4, 2];
const ReturnRoles = [6, 4, 5, 0];
const PuntReturnRoles = [6, 3, 4, 5];
const BlockRoles = [3, 0, 2, 1];

P.assignSeats = function (this: FurySim): void {
  for (const p of this.players) {
    p.seat = NONE;
  }
  for (let team = 0; team < 2; ++team) {
    let roles: number[];
    const hasBall = team === this.offense;
    switch (this.playType) {
      case PlayType.Kickoff: roles = team === this.kickingTeam ? KickRoles : ReturnRoles; break;
      case PlayType.Punt: roles = hasBall ? OffenseRoles : PuntReturnRoles; break;
      case PlayType.FieldGoal:
      case PlayType.ExtraPoint: roles = hasBall ? OffenseRoles : BlockRoles; break;
      default: roles = hasBall ? OffenseRoles : DefenseRoles; break;
    }

    const seated: number[] = [];
    for (let i = 0; i < MaxSeats; ++i) {
      if (this.seats[i].active && this.seats[i].team === team) {
        seated.push(i);
      } else if (this.seats[i].team === team) {
        this.seats[i].player = NONE;
      }
    }
    const count = seated.length;
    for (let k = 0; k < count; ++k) {
      // Rotate with the team's possessions so the quarterback job (and the rest) gets shared around.
      const role = roles[(k + count - this.teamDrives[team] % count) % count];
      const index = this.global(team, role);
      this.seats[seated[k]].player = index;
      this.players[index].seat = seated[k];
    }
  }
};

const CoverLane = [0, -21, -13, -5, 5, 13, 21];
// Receiving team: four up front, two in the middle, one deep.
const ReturnSpot = [
  new Vec2(13, -17), new Vec2(13, -6), new Vec2(13, 6), new Vec2(13, 17),
  new Vec2(42, -9), new Vec2(42, 9), new Vec2(60, 0)];

P.setupKickoff = function (this: FurySim): void {
  const offenseUnit = [false, false];
  offenseUnit[1 - this.kickingTeam] = true;
  this.placeUnits(offenseUnit);

  const kick = this.kickingTeam, receive = 1 - this.kickingTeam;
  const kd = Dir(kick);
  const spotX = WorldX(kick, this.kickFromYard);
  this.losX = spotX;
  this.ballY = 0;
  this.haveOffPlay = this.haveDefPlay = false;

  for (let slot = 0; slot < TeamSize; ++slot) {
    const p = this.players[this.global(kick, slot)];
    p.job = makeJob();
    p.path = [];
    if (slot === 0) {
      p.job.job = Job.Kicker;
      p.home = new Vec2(spotX - kd * 3.6 * Yard, 0);
    } else {
      p.job.job = Job.Cover;
      p.home = new Vec2(spotX - kd * 1.2 * Yard, CoverLane[slot] * Yard);
    }
  }
  for (let slot = 0; slot < TeamSize; ++slot) {
    const p = this.players[this.global(receive, slot)];
    p.job = makeJob();
    p.path = [];
    p.job.job = slot === 6 ? Job.Returner : Job.ReturnBlock;
    p.home = this.clampToField(new Vec2(spotX + kd * ReturnSpot[slot].x * Yard, ReturnSpot[slot].y * Yard), 150);
  }

  this.ball = new Ball();
  this.ball.state = BallState.Tee;
  this.ball.pos = new Vec3(spotX, 0, 14);
  for (const p of this.players) {
    p.hasBall = false;
    p.passIcon = 0;
    p.mark = NONE;
  }
  this.assignSeats();
};

P.setupPlay = function (this: FurySim): void {
  const offenseUnit = [false, false];
  offenseUnit[this.offense] = true;
  this.placeUnits(offenseUnit);
  const def = this.defense();
  const d = this.offenseDir();

  // Offense: spots, jobs and world-space paths.
  for (let slot = 0; slot < TeamSize; ++slot) {
    const p = this.players[this.global(this.offense, slot)];
    const spot = this.currentOff.spot[slot];
    p.home = this.clampToField(this.toWorld(spot), 120);
    p.job = cloneJob(this.currentOff.job[slot]);
    p.path = [];
    const inward = spot.y > 0 ? -1 : 1;     // play-space direction toward the middle
    for (const step of p.job.path) {
      const offset = new Vec2(step.x, p.job.inward ? step.y * inward : step.y);
      p.path.push(this.clampToField(p.home.add(new Vec2(d * offset.x * Yard, d * offset.y * Yard)), 110));
    }
    p.mark = NONE;
  }

  // Defense: spots follow the job. Man defenders line up over their man; zone defenders in their zone.
  for (let slot = 0; slot < TeamSize; ++slot) {
    const p = this.players[this.global(def, slot)];
    p.job = cloneJob(this.currentDef.job[slot]);
    p.path = [];
    p.mark = NONE;
    let spot = this.currentDef.spot[slot];
    if (p.job.job === Job.Man && p.job.target !== NONE) {
      const receiver = this.currentOff.spot[p.job.target];
      const shade = receiver.y > 0 ? -0.7 : 0.7;
      spot = new Vec2(Math.max(p.job.cushion + 0.4, 1.2), receiver.y * (receiver.x < -2 ? 0.6 : 1) + shade);
      p.mark = this.global(this.offense, p.job.target);
    }
    // Never crowd the goal line from inside the end zone's back wall.
    p.home = this.clampToField(this.toWorld(spot), 120);
  }

  this.ball = new Ball();
  this.ball.state = BallState.Tee;
  this.ball.pos = new Vec3(this.losX, this.ballY, 12);
  for (const p of this.players) {
    p.hasBall = false;
    p.passIcon = 0;
  }

  // Pass icons for the three eligible receivers, ordered the way they appear on screen:
  // the far sideline (-Y) is the top of the picture.
  if (this.playType === PlayType.Scrimmage || this.playType === PlayType.TwoPoint) {
    const order = [4, 5, 6];
    order.sort((a, b) => this.players[this.global(this.offense, a)].home.y - this.players[this.global(this.offense, b)].home.y);
    for (let i = 0; i < 3; ++i) {
      this.players[this.global(this.offense, order[i])].passIcon = i + 1;
    }
  }
  this.assignSeats();
};

// ---------------------------------------------------------------------------------------------
// Starting each kind of play
// ---------------------------------------------------------------------------------------------

P.beginKickoff = function (this: FurySim, kicker: number, fromYard: number): void {
  this.playType = PlayType.Kickoff;
  this.kickingTeam = kicker;
  this.offense = 1 - kicker;
  this.ballTeam = kicker;
  this.kickFromYard = fromYard;
  this.down = 1;
  this.setupKickoff();
  this.firstDownX = this.losX;
  this.enter(Phase.Lineup);
  this.emit(Ev.PlayStart, kicker);
};

P.beginScrimmage = function (this: FurySim, newOffense: number, newLosX: number, newBallY: number, firstDown: boolean): void {
  if (newOffense !== this.offense || this.playType === PlayType.Kickoff || this.playType === PlayType.Punt) {
    ++this.driveCount;
    ++this.teamDrives[newOffense];
  }
  this.offense = newOffense;
  this.ballTeam = newOffense;
  this.playType = PlayType.Scrimmage;
  const d = this.offenseDir();
  // Keep the ball between the one-yard lines and between the hash marks.
  this.losX = d * FMath.clamp(newLosX * d, -GoalX + Yard, GoalX - Yard);
  this.ballY = FMath.clamp(newBallY, -HashY, HashY);
  if (firstDown) {
    this.down = 1;
    this.firstDownX = d * Math.min(this.losX * d + FirstDownYards * Yard, GoalX);
  }
  this.beginPlaySelect();
};

P.beginPlaySelect = function (this: FurySim): void {
  for (let team = 0; team < 2; ++team) {
    const pick = this.picks[team];
    pick.locked = false;
    pick.play = NONE;
    pick.flip = false;
    pick.page = 0;
    pick.cursor = 4;
    pick.cpuDelay = this.randRange(0.7, 1.5);
  }
  this.selectTimer = SelectSeconds;
  this.haveOffPlay = this.haveDefPlay = false;

  // Huddles: offense a few yards behind the ball, defense a few yards beyond it.
  const d = this.offenseDir();
  for (let i = 0; i < NumPlayers; ++i) {
    const p = this.players[i];
    const off = p.team === this.offense;
    const angle = 2 * PI * p.slot / TeamSize;
    const centre = new Vec2(this.losX + d * (off ? -7 : 6) * Yard, this.ballY);
    p.home = this.clampToField(centre.add(new Vec2(Math.cos(angle), Math.sin(angle)).mul(190)), 150);
    p.hasBall = false;
  }
  this.ball.state = BallState.Tee;
  this.ball.holder = NONE;
  this.ball.pos = new Vec3(this.losX, this.ballY, 12);
  this.enter(Phase.PlaySelect);
};

// ---------------------------------------------------------------------------------------------
// Choosing plays
// ---------------------------------------------------------------------------------------------

/** Set a kick call when distance, score and time favor special teams. */
P.chooseSituationalKick = function (this: FurySim, pick: Pick): boolean {
  const toGo = this.yardsToGo();
  const line = YardLine(this.offense, this.losX);
  const lead = this.teams[this.offense].score - this.teams[this.defense()].score;
  const late = this.quarter >= 4 && this.clock < 45;
  const desperate = late && lead < 0;

  if (this.playType !== PlayType.TwoPoint && this.down === 4) {
    const kickYards = (100 - line) + 17;
    const inRange = kickYards <= 52;
    const goForIt = desperate && lead < -3;
    if (inRange && !goForIt && (toGo > 2 || lead >= -3)) {
      pick.page = 2; pick.cursor = 1; pick.play = -3;
      return true;
    }
    if (!desperate && toGo > 7 && line < 62) {
      pick.page = 2; pick.cursor = 0; pick.play = -2;
      return true;
    }
  }
  // Last-second field goal to win or tie.
  if (this.playType !== PlayType.TwoPoint && late && this.clock < 8 && lead <= 0 && lead >= -3 && (100 - line) + 17 <= 55) {
    pick.page = 2; pick.cursor = 1; pick.play = -3;
    return true;
  }
  return false;
};

P.cpuPickOffense = function (this: FurySim, pick: Pick): void {
  pick.flip = this.chance(0.5);
  if (this.chooseSituationalKick(pick)) { return; }
  const toGo = this.yardsToGo();
  const line = YardLine(this.offense, this.losX);
  const desperate = this.quarter >= 4 && this.clock < 45 && this.teams[this.offense].score < this.teams[this.defense()].score;
  const all = Playbook.offense();
  const pool: number[] = [];
  const runChance = desperate ? 0.05 : toGo <= 5 ? 0.45 : toGo > 20 ? 0.12 : 0.26;
  const wantRun = this.chance(runChance);
  for (let i = 0; i < all.length; ++i) {
    const run = all[i].kind === PlayKind.Run;
    if (run !== wantRun) {
      continue;
    }
    const name = all[i].name;
    let weight = 2;
    const deep = name === 'SKYLINE' || name === 'POST MASTER' || name === 'DAGGER' || name === 'HAIL FURY' || name === 'PLAY ACTION';
    const quick = name === 'SLANT STORM' || name === 'QUICK HITCH' || name === 'MESH' || name === 'CURL UP';
    if (!run) {
      if (toGo > 18) { weight = deep ? 5 : quick ? 1 : 3; }
      else if (toGo < 8) { weight = quick ? 5 : deep ? 1 : 3; }
      if (name === 'HAIL FURY') { weight = (desperate || toGo > 28) ? 4 : 0; }
      if (100 - line < 12 && deep) { weight = 0; }      // no room for bombs at the goal line
    }
    for (let k = 0; k < weight; ++k) {
      pool.push(i);
    }
  }
  const choice = pool.length > 0 ? pool[this.random.randRange(0, pool.length - 1)] : this.random.randRange(0, all.length - 1);
  pick.page = Math.trunc(choice / PlaysPerPage);
  pick.cursor = choice % PlaysPerPage;
  pick.play = choice;
};

// Order matches Playbook.defense().
const D = { AllOut: 0, PressMan: 1, ZoneBlanket: 2, PicketFence: 3, BaseMan: 4, CornerFire: 5, SpyGame: 6, DoubleTrouble: 7, Prevent: 8 } as const;

P.cpuPickDefense = function (this: FurySim, pick: Pick): void {
  const toGo = this.yardsToGo();
  const line = YardLine(this.offense, this.losX);
  const weight = [2, 3, 3, 3, 4, 2, 2, 2, 0];
  if (toGo > 22) { weight[D.ZoneBlanket] = 6; weight[D.Prevent] = 3; weight[D.PicketFence] = 1; weight[D.PressMan] = 1; }
  if (toGo < 7) { weight[D.PicketFence] = 6; weight[D.PressMan] = 5; weight[D.AllOut] = 4; weight[D.ZoneBlanket] = 1; }
  if (100 - line < 10) { weight[D.PressMan] = 6; weight[D.AllOut] = 5; weight[D.Prevent] = 0; weight[D.ZoneBlanket] = 1; }
  if (this.quarter >= 4 && this.clock < 20 && this.teams[this.defense()].score > this.teams[this.offense].score) { weight[D.Prevent] = 9; }
  // Better computer teams blitz more.
  weight[D.AllOut] += FMath.roundToInt(this.cpuSkill * 2);
  weight[D.CornerFire] += FMath.roundToInt(this.cpuSkill * 2);

  let total = 0;
  for (const w of weight) { total += w; }
  let roll = this.random.randRange(0, total - 1);
  let choice = 0;
  for (let i = 0; i < 9; ++i) {
    if (roll < weight[i]) { choice = i; break; }
    roll -= weight[i];
  }
  pick.page = 0;
  pick.cursor = choice;
  pick.play = choice;
  pick.flip = this.chance(0.5);
};

P.stepPlaySelect = function (this: FurySim, dt: number, inputs: SeatInput[]): void {
  this.selectTimer -= dt;
  for (let team = 0; team < 2; ++team) {
    const pick = this.picks[team];
    if (pick.locked) {
      continue;
    }
    const off = team === this.offense;
    const seat = this.captain(team);
    if (seat === NONE) {
      pick.cpuDelay -= dt;
      if (pick.cpuDelay <= 0) {
        if (off) { this.cpuPickOffense(pick); } else { this.cpuPickDefense(pick); }
        pick.locked = true;
        this.emit(Ev.PlayPicked, team);
      }
      continue;
    }

    const input = inputs[seat];
    let col = pick.cursor % 3, row = Math.trunc(pick.cursor / 3);
    col = (col + input.navX + 3) % 3;
    row = (row - input.navY + 3) % 3;
    pick.cursor = row * 3 + col;
    if (off) {
      const pages = this.numOffensePages();
      if (input.RB) { pick.page = (pick.page + 1) % pages; }
      if (input.LB) { pick.page = (pick.page + pages - 1) % pages; }
      if (!this.offenseChoice(pick.page, pick.cursor)) {
        // Empty cell (the kicking page is short): fall back to the first play on the page.
        pick.cursor = this.offenseChoice(pick.page, 0) ? 0 : 4;
        if (!this.offenseChoice(pick.page, pick.cursor)) { pick.page = 0; }
      }
    }
    if (input.X) {
      pick.flip = !pick.flip;
    }
    const timeUp = this.selectTimer <= 0;
    if ((input.A && this.phaseTime > 0.3) || timeUp) {
      if (off) {
        const choice = this.offenseChoice(pick.page, pick.cursor);
        pick.play = !choice ? 0 : pick.page === 2 ? (pick.cursor === 0 ? -2 : -3) : pick.page * PlaysPerPage + pick.cursor;
      } else {
        pick.play = pick.cursor;
      }
      pick.locked = true;
      this.emit(Ev.PlayPicked, team);
    }
  }

  if (!this.picks[0].locked || !this.picks[1].locked) {
    return;
  }

  // Both sides are in: build the play.
  const offPick = this.picks[this.offense];
  const defPick = this.picks[this.defense()];
  if (offPick.play === -2 || offPick.play === -3) {
    this.currentOff = cloneOffPlay(offPick.play === -2 ? Playbook.punt() : Playbook.fieldGoal());
    this.currentDef = cloneDefPlay(Playbook.kickBlock());
    this.playType = offPick.play === -2 ? PlayType.Punt : PlayType.FieldGoal;
  } else {
    const base = Playbook.offense()[FMath.clamp(offPick.play, 0, Playbook.offense().length - 1)];
    this.currentOff = offPick.flip ? Playbook.flipOff(base) : cloneOffPlay(base);
    const defBase = Playbook.defense()[FMath.clamp(defPick.play, 0, Playbook.defense().length - 1)];
    this.currentDef = defPick.flip ? Playbook.flipDef(defBase) : cloneDefPlay(defBase);
  }
  this.haveOffPlay = this.haveDefPlay = true;
  this.setupPlay();
  this.enter(Phase.Lineup);
  this.emit(Ev.PlayStart, this.offense);
};

P.stepPatSelect = function (this: FurySim, _dt: number, inputs: SeatInput[]): void {
  const seat = this.captain(this.scoringTeam);
  let decided = false;
  if (seat === NONE) {
    if (this.phaseTime > 0.9) {
      // Go for two when it turns a deficit into a tie or a lead into a touchdown-plus cushion.
      const lead = this.teams[this.scoringTeam].score - this.teams[1 - this.scoringTeam].score;
      this.patChoice = (lead === -2 || lead === -5 || lead === 1 || (this.quarter >= 4 && lead === -1)) ? 1 : (this.chance(0.08) ? 1 : 0);
      decided = true;
    }
  } else {
    const input = inputs[seat];
    if (input.navX !== 0 || input.navY !== 0) {
      this.patChoice = 1 - this.patChoice;
    }
    decided = (input.A && this.phaseTime > 0.4) || this.phaseTime > 8;
  }
  if (!decided) {
    return;
  }

  this.offense = this.scoringTeam;
  this.ballTeam = this.scoringTeam;
  const d = this.offenseDir();
  this.ballY = 0;
  this.down = 1;
  if (this.patChoice === 0) {
    this.playType = PlayType.ExtraPoint;
    this.losX = d * (GoalX - 10 * Yard);
    this.firstDownX = d * GoalX;
    this.currentOff = cloneOffPlay(Playbook.fieldGoal());
    this.currentDef = cloneDefPlay(Playbook.kickBlock());
    this.haveOffPlay = this.haveDefPlay = true;
    this.setupPlay();
    this.enter(Phase.Lineup);
    this.emit(Ev.PlayStart, this.offense);
  } else {
    this.playType = PlayType.TwoPoint;
    this.losX = d * (GoalX - 3 * Yard);
    this.firstDownX = d * GoalX;
    this.beginPlaySelect();
  }
};

// ---------------------------------------------------------------------------------------------
// Lining up and the snap
// ---------------------------------------------------------------------------------------------

P.stepLineup = function (this: FurySim, dt: number): void {
  const d = this.offenseDir();
  let allSet = true;
  for (let i = 0; i < NumPlayers; ++i) {
    const p = this.players[i];
    if (this.phaseTime <= dt * 1.5) {
      // Fresh play: everyone is on their feet, and nobody has a marathon to run to the huddle.
      p.down = false; p.busy = false; p.engaged = NONE; p.downLeft = 0; p.launch = Vec2.Zero; p.height = 0;
      p.evadeLeft = p.stiffLeft = p.cooldown = p.jumpLeft = p.catchCool = p.burst = p.burstCool = 0;
      p.scramble = false; p.face = false; p.react = 0; p.pathIndex = 0; p.routeDone = false; p.broke = false;
      p.pursue = false; p.readLeft = -1;
      this.setAct(p, Act.Move, 0, 0, 0, false);
      const away = p.p.sub(p.home);
      if (away.size() > 6 * Yard) {
        p.p = p.home.add(away.safeNormal().mul(6 * Yard));
      }
    }
    const to = p.home.sub(p.p);
    const dist = to.size();
    if (dist > 12) {
      allSet = false;
      const speed = Math.min(p.topSpeed * 0.8, dist / Math.max(LineupSeconds - this.phaseTime, 0.12) + 120);
      p.v = to.div(dist).mul(speed);
      p.p = p.p.add(p.v.mul(Math.min(dt, dist / speed)));
      p.yaw = AngleOf(p.v);
    } else {
      p.p = p.home;
      p.v = Vec2.Zero;
    }
  }
  if (!allSet && this.phaseTime < LineupSeconds + 0.6) {
    return;
  }

  // Set: face the other side and drop into a stance.
  for (let i = 0; i < NumPlayers; ++i) {
    const p = this.players[i];
    p.p = p.home;
    p.v = Vec2.Zero;
    const off = this.playType === PlayType.Kickoff ? p.team === this.kickingTeam : p.team === this.offense;
    const facing = this.playType === PlayType.Kickoff ? Dir(p.team) : (off ? d : -d);
    p.yaw = facing > 0 ? 0 : PI;
    let stance = Stance.Ready;
    if (this.playType === PlayType.Kickoff) {
      stance = Stance.Ready;
    } else if (off) {
      switch (p.job.job) {
        case Job.Passer: case Job.Keeper: stance = Stance.QB; break;
        case Job.Punter: stance = Stance.QB; break;
        case Job.Kicker: stance = Stance.Idle; break;
        case Job.Holder: stance = Stance.Ready; break;
        default: stance = p.slot === 1 ? Stance.Center : (p.pos === Pos.OL ? Stance.ThreePoint : Stance.Ready); break;
      }
    } else {
      stance = p.pos === Pos.DL ? Stance.ThreePoint : Stance.Ready;
    }
    this.setAct(p, Act.Stand, stance, 0, 0, false);
  }

  const callingTeam = this.playType === PlayType.Kickoff ? this.kickingTeam : this.offense;
  this.snapDelay = this.captain(callingTeam) === NONE ? this.randRange(1.0, 1.9) : 7;
  this.hutTimer = 0.35;
  this.kickMeter = 0;
  this.kickAim = 0;
  this.kickMeterLive = false;
  this.kickLocked = false;
  this.kickSteer = Vec2.Zero;
  this.ballCrossedLine = false;
  this.passThrown = false;
  this.changeOfPossession = false;
  this.kickTouched = false;
  this.kickPossessed = false;
  this.returnEnteredField = false;
  this.firstDownMade = false;
  this.passSeat = NONE;
  this.startLosX = this.losX;
  this.returnStartX = this.losX;
  this.playYards = 0;
  this.liveTime = 0;
  this.enter(Phase.PreSnap);
};

P.stepPreSnap = function (this: FurySim, dt: number, inputs: SeatInput[]): void {
  const callingTeam = this.playType === PlayType.Kickoff ? this.kickingTeam : this.offense;
  const seat = this.captain(callingTeam);
  const scrimmage = this.playType === PlayType.Scrimmage || this.playType === PlayType.TwoPoint;

  // The quarterback barks the count.
  if (scrimmage) {
    this.hutTimer -= dt;
    if (this.hutTimer <= 0) {
      this.hutTimer = this.randRange(0.7, 1.1);
      this.emit(Ev.Hut, this.offense, this.global(this.offense, 0));
    }
  }

  // Human defenders may walk around on their side of the ball before the snap.
  if (scrimmage) {
    const d = this.offenseDir();
    for (let seatIndex = 0; seatIndex < MaxSeats; ++seatIndex) {
      const defender = this.seats[seatIndex];
      if (!defender.active || defender.player === NONE || defender.team === this.offense) {
        continue;
      }
      const p = this.players[defender.player];
      const input = inputs[seatIndex];
      const wish = new Vec2(input.stick.x, -input.stick.y);
      if (wish.sizeSquared() > 0.04) {
        p.p = p.p.add(wish.mul(p.topSpeed * 0.6).mul(dt));
        p.p = p.p.withX(d * Math.max(p.p.x * d, this.losX * d + 1.1 * Yard));
        p.p = this.clampToField(p.p, 100);
        p.home = p.p;
      }
      if (input.A && this.phaseTime > 0.3) {
        // Cycle to the next defender no human is steering.
        for (let k = 1; k < TeamSize; ++k) {
          const next = this.global(p.team, (p.slot + k) % TeamSize);
          if (this.players[next].seat === NONE) {
            this.switchSeat(p.seat, next);
            break;
          }
        }
      }
    }
  }

  let go = this.phaseTime >= this.snapDelay;
  if (seat !== NONE && inputs[seat].A && this.phaseTime > 0.35) {
    go = true;
  }
  if (!go) {
    return;
  }

  if (this.playType === PlayType.Kickoff) {
    for (const p of this.players) {
      this.setAct(p, Act.Move, 0, 0, 0, false);
      p.react = 0;
      p.think = 0;
    }
    this.startKick(this.global(this.kickingTeam, 0));
    this.enter(Phase.Live);
    this.liveTime = 0;
  } else {
    this.snapBall();
  }
};

P.snapBall = function (this: FurySim): void {
  this.enter(Phase.Live);
  this.liveTime = 0;
  ++this.playCount;
  for (let team = 0; team < 2; ++team) { this.furyAtSnap[team] = this.teams[team].inFury(); }
  const def = this.defense();
  const centre = this.global(this.offense, 1);

  // Who takes the snap: the passer, punter or holder.
  let taker = this.global(this.offense, 0);
  if (this.playType === PlayType.FieldGoal || this.playType === PlayType.ExtraPoint) {
    taker = this.global(this.offense, 6);
  }
  this.setAct(this.players[centre], Act.Snap, 0, 0.4, 0.1, true);
  this.ball.state = BallState.Snap;
  this.ball.holder = NONE;
  this.ball.target = taker;
  this.ball.from = new Vec3(this.losX, this.ballY, 25);
  this.ball.to = new Vec3(this.players[taker].p.x, this.players[taker].p.y,
    this.playType === PlayType.FieldGoal || this.playType === PlayType.ExtraPoint ? 30 : 105);
  this.ball.time = 0;
  this.ball.duration = 0.24 + this.ball.from.xy().sub(this.ball.to.xy()).size() / 3600;
  this.ball.pos = this.ball.from;
  this.emit(Ev.Snap, this.offense, centre);

  for (let i = 0; i < NumPlayers; ++i) {
    const p = this.players[i];
    if (i === centre) {
      continue;
    }
    const off = p.team === this.offense;
    this.setAct(p, Act.Move, 0, 0, 0, false);
    p.pathIndex = 0;
    p.routeDone = false;
    p.broke = false;
    p.think = this.randRange(0, 0.2);
    const defenseRating = (this.teamInfo(def).defense - 3) * 0.02;
    p.react = off ? this.randRange(0, 0.06) + p.job.delay : Math.max(0.04, this.randRange(0.1, 0.24) - defenseRating - this.cpuSkill * 0.05);
    if (!off && p.job.job === Job.Blitz) {
      p.react += p.job.delay;
    }
    // A play-action fake holds the linebacker and the safety for a beat.
    if (!off && this.currentOff.playAction && (p.slot === 3 || p.slot === 6) && p.job.job !== Job.Blitz && p.seat === NONE) {
      p.react += this.randRange(0.45, 0.75) * (1 - this.cpuSkill * 0.4);
    }
  }

  // Press coverage: a successful jam holds the receiver up at the line.
  for (let slot = 0; slot < TeamSize; ++slot) {
    const corner = this.players[this.global(def, slot)];
    if (corner.job.job === Job.Man && corner.job.press && corner.mark !== NONE && this.chance(0.6)) {
      this.players[corner.mark].react += this.randRange(0.35, 0.6);
      this.setAct(corner, Act.Shove, 0, 0.4, 0.12, false);
    }
  }

  if (this.playType === PlayType.FieldGoal || this.playType === PlayType.ExtraPoint) {
    this.kickMeterLive = true;
    this.startKick(this.global(this.offense, 0));
  }
  this.pairBlockers();
};

// ---------------------------------------------------------------------------------------------
// Ending a play, downs and scoring
// ---------------------------------------------------------------------------------------------

// DownBall (FurySim.cpp) is ported in simPlay.ts, where the sim.ts contract places it.

P.endPlay = function (this: FurySim, title: string, detail: string, team: number): void {
  this.resultTitle = title;
  this.resultDetail = detail;
  this.resultTeam = team;
  this.beginAfterWhistle(Phase.Dead, new Vec2(this.deadSpotX, this.deadSpotY));
};

P.beginAfterWhistle = function (this: FurySim, newPhase: Phase, spot: Vec2): void {
  this.kickMeterLive = false;
  this.readySeats = 0;
  this.whistleFocus = spot;
  this.ball.state = BallState.Dead;
  this.ball.holder = this.ball.target = NONE;
  this.ball.pos = Vec3.from2(spot, 10);
  this.ball.vel = Vec3.Zero;
  for (const p of this.players) {
    p.hasBall = false;
    if (p.engaged !== NONE) { this.disengage(this.global(p.team, p.slot)); }
    if (p.down) { p.downLeft = Math.min(p.downLeft, 2.2); }
    p.think = this.randRange(0.4, 1.4);
    p.mark = NONE;
  }
  this.emit(Ev.Whistle);
  this.enter(newPhase);
};

P.score = function (this: FurySim, team: number, points: number, playerIndex: number): void {
  this.teams[team].score += points;
  this.teams[team].scoreByQuarter[FMath.clamp(this.quarter - 1, 0, 4)] += points;
  this.scoringTeam = team;
  this.scorer = playerIndex;
};

/** After a score (and its conversion): kick off, unless the clock or overtime says otherwise. */
P.nextAfterScore = function (this: FurySim): void {
  if (this.overtime) {
    this.enter(Phase.GameOver);
    this.emit(Ev.GameOver, this.winner());
    return;
  }
  if (this.clockExpired) {
    this.endQuarter();
    if (this.phase === Phase.GameOver || this.quarter === 3 || this.overtime) {
      return;      // the new half / overtime starts with its own kickoff
    }
  }
  this.pendingScoreTeam = NONE;
  this.beginKickoff(this.scoringTeam, 35);
  if (this.clockExpired) {
    // A quarter break is showing; the kickoff is already set up behind it.
    this.clockExpired = false;
    this.enter(Phase.Break);
  }
};

P.resolveDown = function (this: FurySim, spotX: number, spotY: number): void {
  // Called when the aftermath of a play is over and the next one has to be set up.
  if (this.playType === PlayType.Scrimmage) {
    this.tickFuryAfterPlay();
  }
  const d = this.offenseDir();
  const scoreTry = this.playType === PlayType.ExtraPoint || this.playType === PlayType.TwoPoint;
  if (scoreTry) {
    this.nextAfterScore();
    return;
  }

  let nextIsKickoff = false;
  let nextOffense = this.offense;
  let nextX = spotX, nextY = spotY;
  let first = false;
  let nextKicker = 0;
  let nextKickFrom = 35;

  if (this.pendingScoreTeam !== NONE && this.overtime) {
    // Sudden death: a field goal or a safety wins it just as surely as a touchdown.
    this.pendingScoreTeam = NONE;
    this.enter(Phase.GameOver);
    this.emit(Ev.GameOver, this.winner());
    return;
  }
  if (this.pendingScoreTeam !== NONE) {
    // Field goal or safety already on the board.
    nextIsKickoff = true;
    nextKicker = this.resultTitle === 'SAFETY' ? 1 - this.pendingScoreTeam : this.pendingScoreTeam;
    nextKickFrom = this.resultTitle === 'SAFETY' ? 20 : 35;
    this.pendingScoreTeam = NONE;
  } else if (this.resultTitle === 'TOUCHBACK') {
    nextOffense = this.resultTeam;
    nextX = WorldX(this.resultTeam, 25);
    nextY = 0;
    first = true;
  } else if (this.resultTitle === 'NO GOOD') {
    // Missed field goal: the other side takes over where the ball was snapped, no closer than its 20.
    nextOffense = this.defense();
    nextX = Dir(nextOffense) * Math.max(this.startLosX * Dir(nextOffense), -GoalX + 20 * Yard);
    nextY = 0;
    first = true;
  } else if (this.playType === PlayType.Kickoff || this.playType === PlayType.Punt || this.changeOfPossession) {
    nextOffense = this.ballTeam;
    first = true;
  } else if (this.resultTitle === 'INCOMPLETE') {
    nextX = this.startLosX;
    nextY = this.ballY;
    ++this.down;
  } else {
    // An ordinary play from scrimmage: did it move the chains?
    if ((spotX - this.firstDownX) * d >= 0) {
      first = true;
      ++this.teams[this.offense].firstDowns;
      this.emit(Ev.FirstDown, this.offense);
      this.addFury(this.offense, 0.04);
    } else {
      ++this.down;
    }
  }

  if (!nextIsKickoff && !first && this.down > 4) {
    this.emit(Ev.TurnoverOnDowns, this.defense());
    this.addFury(this.defense(), 0.2);
    nextOffense = this.defense();
    first = true;
  }

  if (this.clockExpired) {
    const endedQuarter = this.quarter;
    this.endQuarter();
    if (this.phase === Phase.GameOver || endedQuarter === 2 || this.overtime) {
      return;
    }
    // Quarters one and three: play simply carries on after the break.
    this.clockExpired = false;
    if (nextIsKickoff) { this.beginKickoff(nextKicker, nextKickFrom); }
    else { this.beginScrimmage(nextOffense, nextX, nextY, first); }
    this.enter(Phase.Break);
    return;
  }

  if (nextIsKickoff) {
    this.beginKickoff(nextKicker, nextKickFrom);
  } else {
    this.beginScrimmage(nextOffense, nextX, nextY, first);
  }
};

P.endQuarter = function (this: FurySim): void {
  this.emit(Ev.QuarterEnd, NONE, NONE, NONE, this.quarter);
  if (this.quarter === 2) {
    this.quarter = 3;
    this.clock = this.quarterLength;
    this.clockExpired = false;
    this.emit(Ev.Halftime);
    // The side that received the opening kick kicks off the second half.
    this.beginKickoff(1 - this.openingKicker, 35);
    this.enter(Phase.Break);
    return;
  }
  if (this.quarter >= 4) {
    if (this.teams[0].score !== this.teams[1].score) {
      this.enter(Phase.GameOver);
      this.emit(Ev.GameOver, this.winner());
      return;
    }
    // Sudden death: first score wins, no clock.
    this.overtime = true;
    this.quarter = 5;
    this.clock = 0;
    this.clockExpired = false;
    this.emit(Ev.Overtime);
    this.beginKickoff(this.random.randRange(0, 1), 35);
    this.enter(Phase.Break);
    return;
  }
  ++this.quarter;
  this.clock = this.quarterLength;
};

P.stepAfterWhistle = function (this: FurySim, inputs: SeatInput[]): void {
  let active = 0;
  for (let i = 0; i < MaxSeats; ++i) {
    if (!this.seats[i].active) { continue; }
    active |= 1 << i;
    if (this.phaseTime > 0.5 && inputs[i].A) { this.readySeats |= 1 << i; }
  }
  if (this.phaseTime < FurySim.AfterWhistleSeconds && !(active && (this.readySeats & active) === active)) { return; }
  if (this.phase === Phase.Dead) { this.resolveDown(this.deadSpotX, this.deadSpotY); }
  else { this.finishCelebration(); }
};

P.finishCelebration = function (this: FurySim): void {
  if (this.playType === PlayType.Scrimmage) {
    this.tickFuryAfterPlay();
  }
  if (this.overtime) {
    this.enter(Phase.GameOver);
    this.emit(Ev.GameOver, this.winner());
    return;
  }
  this.patChoice = 0;
  this.enter(Phase.PatSelect);
};

P.stepBreak = function (this: FurySim, _dt: number): void {
  const length = this.quarter === 3 && this.clock >= this.quarterLength - 0.01 && this.playType === PlayType.Kickoff ? 7 : 3.5;
  if (this.phaseTime >= length) {
    // The next play was set up before the break; pick it up where it stood.
    if (this.playType === PlayType.Kickoff) {
      this.enter(Phase.Lineup);
    } else {
      this.enter(Phase.PlaySelect);
      this.selectTimer = SelectSeconds;
    }
  }
};

// ---------------------------------------------------------------------------------------------
// The step
// ---------------------------------------------------------------------------------------------

P.step = function (this: FurySim, dt: number, inputs: SeatInput[]): void {
  this.phaseTime += dt;
  switch (this.phase) {
    case Phase.PlaySelect:
      this.stepLive(dt, inputs);          // players drift to their huddles behind the play menu
      this.stepPlaySelect(dt, inputs);
      break;
    case Phase.Lineup:
      for (const p of this.players) { p.actTime += dt; }
      this.stepLineup(dt);
      break;
    case Phase.PreSnap:
      for (const p of this.players) { p.actTime += dt; }
      this.stepPreSnap(dt, inputs);
      break;
    case Phase.Live:
      this.stepLive(dt, inputs);
      break;
    case Phase.Dead:
    case Phase.Celebrate:
      this.stepLive(dt, inputs);
      this.stepAfterWhistle(inputs);
      break;
    case Phase.PatSelect:
      this.stepLive(dt, inputs);
      if (this.phase === Phase.PatSelect) { this.stepPatSelect(dt, inputs); }
      break;
    case Phase.Break:
      this.stepLive(dt, inputs);
      if (this.phase === Phase.Break) { this.stepBreak(dt); }
      break;
    case Phase.GameOver:
      this.stepLive(dt, inputs);
      break;
  }
};
