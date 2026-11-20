/**
 * The live action: human control, movement, blocking, the ball, tackles and the rules that end a play.
 *
 * Port of FurySimPlay.cpp. Every method here is assigned onto FurySim.prototype; the declarations
 * (names and signatures) live in sim.ts. DownBall is defined in FurySim.cpp in the C++ but the
 * contract places it here, so it is ported here too.
 */
import {
  Act, AngleDelta, AngleOf, BallState, Dir, EndLineX, Ev, Fall, FMath, FromAngle, GoalX, Job, MaxSeats, NONE,
  NumPlayers, Phase, PI, PlayKind, PlayType, SeatInput, SidelineY, SimPlayer, TeamSize, Vec2, Vec3, WorldX, Yard,
} from './core';
import { FurySim } from './sim';

// ---------------------------------------------------------------------------------------------
// File-local constants and helpers (the anonymous namespace in FurySimPlay.cpp)
// ---------------------------------------------------------------------------------------------

const Accel = 3400;          // cm/s^2: athletes hit top speed in about a quarter second
const Decel = 4800;
const TurnRate = 13;         // rad/s
const TurboBoost = 1.16;     // a human holding turbo
const BurstBoost = 1.12;     // a computer player's equivalent, used in spurts
const FuryBoost = 1.1;
const Gravity = 980;
const CatchReach = 92;
const BallRadius = 9;
const TWO_PI = 2 * PI;
const FLOAT_MAX = 3.4028234663852886e38;   // TNumericLimits<float>::Max()

function stickToWorld(stick: Vec2): Vec2 {
  // Screen right is +X; screen up is the far sideline, which is -Y.
  return new Vec2(stick.x, -stick.y);
}

function actDuration(fall: Fall): number {
  switch (fall) {
    case Fall.Front: return 0.62;
    case Fall.Flip: return 0.9;
    case Fall.Spin: return 0.82;
    default: return 0.7;
  }
}

// Blender rig measurements in field centimetres. The down loops put the chest
// 61 cm from the actor root. The elbow key is 113 cm forward and 17 cm left.
function floorChest(p: SimPlayer): Vec2 {
  const front = p.act === Act.Hit
    ? p.variant === Fall.Front || p.variant === Fall.Spin
    : p.variant === 1;
  return p.p.add(FromAngle(p.yaw).mul(front ? 61 : -61));
}

function elbowOffset(yaw: number): Vec2 {
  const f = FromAngle(yaw);
  return f.mul(113).add(new Vec2(f.y, -f.x).mul(17));
}

function onFloor(p: SimPlayer): boolean {
  return p.act === Act.Down || (p.act === Act.Hit && p.actTime >= p.actLength * 0.78);
}

// ---------------------------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------------------------

FurySim.prototype.setAct = function (this: FurySim, player: SimPlayer, act: Act, variant: number, length: number, key: number, busy: boolean): void {
  player.act = act;
  player.variant = variant;
  ++player.actSerial;
  player.actTime = 0;
  player.actLength = length;
  player.actKey = key;
  player.keyDone = key <= 0;
  player.busy = busy;
  player.diveSpent = false;
};

FurySim.prototype.maxSpeed = function (this: FurySim, player: SimPlayer, turbo: boolean): number {
  let speed = player.topSpeed;
  if (this.teams[player.team].inFury()) {
    speed *= FuryBoost;
  }
  if (turbo || player.burst > 0) {
    speed *= turbo ? TurboBoost : BurstBoost;
  }
  return speed;
};

FurySim.prototype.nearestOpponent = function (this: FurySim, index: number, maxDist: number, uprightOnly = true): number {
  const me = this.players[index];
  let best = NONE;
  let bestDist = maxDist * maxDist;
  for (let i = 0; i < NumPlayers; ++i) {
    const other = this.players[i];
    if (other.team === me.team || (uprightOnly && other.down)) {
      continue;
    }
    const dist = Vec2.distSquared(me.p, other.p);
    if (dist < bestDist) {
      bestDist = dist;
      best = i;
    }
  }
  return best;
};

FurySim.prototype.closestToBall = function (this: FurySim, team: number, excludeHumans: boolean, exclude = NONE): number {
  let point = this.ball.pos.xy();
  if (this.ball.state === BallState.Pass || this.ball.state === BallState.Kick) {
    point = this.ball.land();
  }
  let best = NONE;
  let bestDist = FLOAT_MAX;
  for (let slot = 0; slot < TeamSize; ++slot) {
    const index = this.global(team, slot);
    const p = this.players[index];
    if (index === exclude || (excludeHumans && p.seat !== NONE)) {
      continue;
    }
    const dist = Vec2.distSquared(p.p, point) + (p.down ? 1e9 : 0) + (p.engaged !== NONE ? 4e5 : 0);
    if (dist < bestDist) {
      bestDist = dist;
      best = index;
    }
  }
  return best;
};

FurySim.prototype.switchSeat = function (this: FurySim, seatIndex: number, newPlayer: number): void {
  if (newPlayer === NONE || !this.seats[seatIndex].active) {
    return;
  }
  const old = this.seats[seatIndex].player;
  if (old !== NONE) {
    this.players[old].seat = NONE;
  }
  if (this.players[newPlayer].seat !== NONE) {
    this.seats[this.players[newPlayer].seat].player = NONE;
  }
  this.players[newPlayer].seat = seatIndex;
  this.seats[seatIndex].player = newPlayer;
  this.seats[seatIndex].idle = 0;
};

/** Whoever ends up with the ball should be in a human's hands if that team has a human. */
FurySim.prototype.controlFollowsBall = function (this: FurySim, newHolder: number): void {
  const holder = this.players[newHolder];
  if (holder.seat !== NONE) {
    return;
  }
  // Prefer the human who just got rid of the ball; otherwise the team's first human.
  let choice = NONE;
  const thrower = this.ball.thrower;
  if (thrower !== NONE && this.players[thrower].team === holder.team && this.players[thrower].seat !== NONE) {
    choice = this.players[thrower].seat;
  }
  for (let i = 0; i < MaxSeats && choice === NONE; ++i) {
    if (this.seats[i].active && this.seats[i].team === holder.team) {
      choice = i;
    }
  }
  if (choice !== NONE) {
    this.switchSeat(choice, newHolder);
  }
};

FurySim.prototype.giveBall = function (this: FurySim, to: number): void {
  for (const p of this.players) {
    p.hasBall = false;
  }
  const holder = this.players[to];
  holder.hasBall = true;
  this.ball.state = BallState.Held;
  this.ball.holder = to;
  this.ball.vel = Vec3.Zero;
  const kickPlay = this.playType === PlayType.Kickoff || this.playType === PlayType.Punt;
  if (holder.team !== this.ballTeam || (kickPlay && !this.kickPossessed)) {
    this.returnStartX = holder.p.x;
    this.returnEnteredField = holder.p.x * Dir(holder.team) > -GoalX;
  }
  if (holder.team !== this.ballTeam) {
    // On a kick the ball simply belongs to whoever ends up with it; otherwise this is a turnover.
    if (!kickPlay) {
      this.changeOfPossession = true;
    }
    this.ballTeam = holder.team;
  }
  if (kickPlay) {
    this.kickPossessed = true;
  }
  this.controlFollowsBall(to);
};

FurySim.prototype.knock = function (this: FurySim, victim: number, by: number, fall: Fall, downSeconds: number, push: Vec2, lift: number): void {
  void lift;   // unused in the C++ too
  const v = this.players[victim];
  this.disengage(victim);
  const length = actDuration(fall);
  this.setAct(v, Act.Hit, fall, length, 0, true);
  v.down = true;
  v.downLeft = length + downSeconds;
  v.launch = push;
  v.height = 0;
  v.evadeLeft = v.stiffLeft = v.jumpLeft = 0;
  v.faceYaw = v.yaw;
  if (by !== NONE) {
    // Fall facing the way the hit dictates: knocked backward means facing the hitter.
    const toward = this.players[by].p.sub(v.p);
    if (!toward.isNearlyZero()) {
      const hitYaw = AngleOf(toward);
      v.faceYaw = fall === Fall.Front ? hitYaw + PI : hitYaw;
    }
  }
};

FurySim.prototype.engage = function (this: FurySim, blocker: number, defender: number, shedSeconds: number): void {
  const b = this.players[blocker];
  const d = this.players[defender];
  if (!b.free() || !d.free() || b.hasBall || d.hasBall) {
    return;
  }
  b.engaged = defender; d.engaged = blocker;
  b.blocker = true; d.blocker = false;
  b.engageTime = d.engageTime = 0;
  b.shedAt = d.shedAt = shedSeconds;
  this.setAct(b, Act.Block, 0, 0, 0, false);
  this.setAct(d, Act.Block, 0, 0, 0, false);
};

FurySim.prototype.disengage = function (this: FurySim, index: number): void {
  const p = this.players[index];
  if (p.engaged === NONE) {
    return;
  }
  const other = this.players[p.engaged];
  other.engaged = NONE;
  if (other.act === Act.Block) {
    this.setAct(other, Act.Move, 0, 0, 0, false);
  }
  p.engaged = NONE;
  if (p.act === Act.Block) {
    this.setAct(p, Act.Move, 0, 0, 0, false);
  }
};

// ---------------------------------------------------------------------------------------------
// Passing and kicking
// ---------------------------------------------------------------------------------------------

FurySim.prototype.startThrow = function (this: FurySim, passer: number, target: number): void {
  const q = this.players[passer];
  if (q.busy || !q.hasBall || target === NONE || target === passer) {
    return;
  }
  this.setAct(q, Act.Throw, 0, 0.42, 0.17, true);
  this.ball.target = target;
  this.ball.thrower = passer;
  q.yaw = AngleOf(this.players[target].p.sub(q.p));
  q.v = q.v.mul(0.45);
};

FurySim.prototype.releaseThrow = function (this: FurySim, passer: number): void {
  const q = this.players[passer];
  if (!q.hasBall || this.ball.target === NONE) {
    return;
  }
  const r = this.players[this.ball.target];

  // Lead the receiver: find where he will be when the ball gets there.
  let aim = r.p;
  let t = 0.5;
  const settled = r.routeDone && r.v.sizeSquared() < 200 * 200;
  for (let i = 0; i < 4; ++i) {
    const dist = Vec2.dist(q.p, aim);
    t = 0.26 + dist / 2700;
    aim = settled ? r.p : r.p.add(r.v.mul(t));
  }
  aim = this.clampToField(aim, 90);
  const dist = Vec2.dist(q.p, aim);

  // Accuracy: worse when long, hurried, or thrown on the run.
  let spread = 0.034 - 0.006 * (this.teamInfo(q.team).passing - 3);
  const rusher = this.nearestOpponent(passer, 2.6 * Yard);
  if (rusher !== NONE) { spread += 0.03; }
  if (q.v.sizeSquared() > 300 * 300) { spread += 0.02; }
  if (q.seat === NONE) { spread *= 1.35 - 0.55 * this.cpuSkill; }
  if (this.teams[q.team].inFury()) { spread = 0; }
  const r1 = this.random.fRandRange(-1, 1);
  const r2 = this.random.fRandRange(-1, 1);
  const miss = Math.min(Math.abs(r1 + r2), 1.7) * spread * dist;
  aim = aim.add(FromAngle(this.randRange(0, TWO_PI)).mul(miss));

  q.hasBall = false;
  this.ball.state = BallState.Pass;
  this.ball.holder = NONE;
  this.ball.from = new Vec3(q.p.x, q.p.y, 185);
  this.ball.to = new Vec3(aim.x, aim.y, 125);
  this.ball.time = 0;
  this.ball.duration = t;
  this.ball.tipped = false;
  this.ball.arrived = false;
  this.ball.pos = this.ball.from;
  this.passThrown = true;
  this.passSeat = q.seat;
  ++this.teams[q.team].attempts;
  this.emit(Ev.Throw, q.team, passer, this.ball.target, dist / Yard);

  // Defenders notice after a beat; nobody gets a second swipe at a ball they already missed.
  for (let i = 0; i < NumPlayers; ++i) {
    const p = this.players[i];
    p.catchCool = 0;
    if (p.team !== q.team) {
      p.broke = false;
      p.think = p.seat !== NONE ? 0 : this.randRange(0.14, 0.3) * (1.4 - 0.9 * this.cpuSkill) - (this.teamInfo(p.team).defense - 3) * 0.02;
    }
  }

  // A human who throws to a computer team-mate takes over the receiver.
  if (q.seat !== NONE && this.players[this.ball.target].seat === NONE) {
    this.switchSeat(q.seat, this.ball.target);
  }
};

FurySim.prototype.startKick = function (this: FurySim, kicker: number): void {
  const k = this.players[kicker];
  const punt = this.playType === PlayType.Punt;
  this.setAct(k, punt ? Act.Punt : Act.Kick, 0, punt ? 0.85 : 0.95, punt ? 0.5 : 0.6, true);
  k.launch = Vec2.Zero;
  if (!punt) {
    // Run up so the plant foot lands beside the ball at the moment of contact.
    let spot = this.ball.pos.xy();
    if (this.playType === PlayType.FieldGoal || this.playType === PlayType.ExtraPoint) {
      const holder = this.players[this.global(this.offense, 6)];
      spot = holder.p.add(new Vec2(0, -this.offenseDir() * 55));
    }
    const to = spot.sub(k.p);
    const dist = to.size();
    if (dist > 60) {
      k.launch = to.div(dist).mul((dist - 45) / k.actKey);
      k.yaw = AngleOf(to);
    }
  }
};

FurySim.prototype.strikeKick = function (this: FurySim, kicker: number): void {
  const k = this.players[kicker];
  k.launch = Vec2.Zero;
  const receiving = 1 - k.team;
  const ball = this.ball;
  ball.holder = NONE;
  ball.thrower = kicker;
  ball.time = 0;
  ball.tipped = false;
  for (const p of this.players) {
    p.hasBall = false;
    p.catchCool = 0;
  }

  if (this.playType === PlayType.Kickoff) {
    const depth = this.randRange(1, 8);
    const lateral = FMath.clamp(this.kickSteer.y * 16 + this.randRange(-7, 7), -20, 20);
    ball.state = BallState.Kick;
    ball.from = new Vec3(ball.pos.x, ball.pos.y, 20);
    ball.to = new Vec3(WorldX(receiving, depth), lateral * Yard, 110);
    ball.duration = this.randRange(3.3, 3.8);
    this.emit(Ev.Kickoff, k.team, kicker);
  } else if (this.playType === PlayType.Punt) {
    const d = this.offenseDir();
    const net = this.randRange(40, 52);
    const landX = d * Math.min(this.losX * d + net * Yard, GoalX + 2.5 * Yard);
    const lateral = FMath.clamp(this.ballY / Yard * 0.5 + this.kickSteer.y * 14 + this.randRange(-6, 6), -21, 21);
    ball.state = BallState.Kick;
    ball.from = new Vec3(k.p.x + d * 60, k.p.y, 70);
    ball.to = new Vec3(landX, lateral * Yard, 110);
    ball.duration = this.randRange(3.3, 3.8);
    this.ballTeam = k.team;
    this.emit(Ev.PuntKick, k.team, kicker);
  } else {
    // Field goal or extra point: the meter decides how far off line the ball flies.
    const d = this.offenseDir();
    const goalPlane = d * EndLineX;
    const kickYards = this.fieldGoalYards();
    if (!this.kickLocked) {
      if (k.seat === NONE) {
        const sigma = Math.max(0.05, 0.1 + 0.0045 * kickYards - 0.05 * this.cpuSkill);
        this.kickAim = FMath.clamp((this.rand() + this.rand() + this.rand() - 1.5) * 2 * sigma, -1, 1);
      } else {
        this.kickAim = this.kickMeter;
      }
      this.kickLocked = true;
    }
    this.kickMeterLive = false;
    const offset = this.kickAim * FurySim.kickSpread(kickYards) + this.randRange(-FurySim.KickScatter, FurySim.KickScatter);
    const short = kickYards > FurySim.MaxKickYards;
    ball.kickGood = !short && Math.abs(offset) < FurySim.CleanKickWidth;
    ball.state = BallState.FieldGoal;
    ball.from = new Vec3(ball.pos.x, ball.pos.y, 15);
    ball.to = new Vec3(goalPlane + d * (short ? -500 : 350), offset, short ? 60 : this.randRange(650, 900));
    ball.duration = 1.05 + kickYards * 0.027;
    ball.target = NONE;
    this.emit(Ev.FieldGoalKick, k.team, kicker, NONE, kickYards);
  }
  ball.pos = ball.from;
  this.kickPossessed = false;
  this.returnEnteredField = false;
  this.kickTouched = false;
};

// ---------------------------------------------------------------------------------------------
// Tackles and fumbles
// ---------------------------------------------------------------------------------------------

FurySim.prototype.fumble = function (this: FurySim, carrier: number, push: Vec2): void {
  const c = this.players[carrier];
  c.hasBall = false;
  this.ball.state = BallState.Loose;
  this.ball.holder = NONE;
  this.ball.thrower = NONE;
  this.ball.pos = new Vec3(c.p.x, c.p.y, 95);
  const dir = FromAngle(this.randRange(0, TWO_PI));
  const kick = push.mul(0.55).add(dir.mul(this.randRange(120, 320)));
  this.ball.vel = new Vec3(kick.x, kick.y, this.randRange(260, 430));
  this.ball.time = 0;
  this.emit(Ev.Fumble, c.team, carrier);
};

/** The ball carrier has been brought down (or stepped out) at spotX: sort out what that means. */
FurySim.prototype.finishCarrierDown = function (this: FurySim, carrier: number, spotX: number, spotY: number, outOfBounds: boolean, tackler: number): void {
  const c = this.players[carrier];
  const d = this.offenseDir();
  const scrimmage = this.playType === PlayType.Scrimmage;
  const ownPlay = c.team === this.offense && !this.changeOfPossession;
  const gain = (spotX - this.startLosX) * d / Yard;
  this.playYards = gain;

  if (this.playType === PlayType.TwoPoint) {
    this.emit(Ev.TwoPointNoGood, 1 - this.scoringTeam);
    this.downBall(spotX, spotY, 'NO GOOD', 'TWO-POINT TRY FAILS', 1 - this.scoringTeam);
    return;
  }

  // A returner who has already brought the ball into the field can concede a safety.
  if (spotX * Dir(c.team) <= -GoalX) {
    if ((scrimmage && ownPlay) || this.returnEnteredField) {
      const def = 1 - c.team;
      this.score(def, 2, tackler);
      this.pendingScoreTeam = def;
      this.addFury(def, 0.4);
      this.emit(Ev.Safety, def, tackler);
      this.downBall(spotX, spotY, 'SAFETY', 'TWO POINTS', def);
    } else {
      this.emit(Ev.Touchback, c.team);
      this.downBall(spotX, spotY, 'TOUCHBACK', '', c.team);
    }
    return;
  }

  if (scrimmage && ownPlay) {
    const stats = this.teams[this.offense];
    const sack = c.slot === 0 && !this.passThrown && !this.ballCrossedLine && gain < 0 && this.currentOff.kind === PlayKind.Pass;
    if (this.passThrown) { stats.passYards += FMath.roundToInt(gain); }
    else if (!sack) { stats.rushYards += FMath.roundToInt(gain); }
    this.firstDownMade = (spotX - this.firstDownX) * d >= 0;

    const whole = FMath.roundToInt(Math.abs(gain));
    const yards = gain >= 0.5 ? `+${whole} YARD${whole === 1 ? '' : 'S'}`
      : gain <= -0.5 ? `LOSS OF ${whole}` : 'NO GAIN';
    if (sack) {
      ++this.teams[this.defense()].sacks;
      if (tackler !== NONE && this.players[tackler].seat !== NONE) { ++this.seats[this.players[tackler].seat].sacks; }
      this.addFury(this.defense(), 0.22);
      this.emit(Ev.Sack, this.defense(), tackler, carrier);
      this.downBall(spotX, spotY, 'SACKED!', yards, this.defense());
    } else if (this.firstDownMade) {
      if (gain >= 20) { this.addFury(this.offense, 0.08); }
      this.downBall(spotX, spotY, 'FIRST DOWN!', yards, this.offense);
    } else {
      if (gain < -0.5) { this.addFury(this.defense(), 0.08); }
      this.downBall(spotX, spotY, outOfBounds ? 'OUT OF BOUNDS' : '', yards, this.offense);
    }
    return;
  }

  // A return: kick, punt, interception or fumble.
  const title = this.playType === PlayType.Kickoff ? 'KICK RETURN' : this.playType === PlayType.Punt ? 'PUNT RETURN' : 'TURNOVER';
  this.playYards = (spotX - this.returnStartX) * Dir(c.team) / Yard;
  this.downBall(spotX, spotY, title, `${FMath.roundToInt(this.playYards)} YD RETURN   /   ${this.teamInfo(c.team).abbr} BALL`, c.team);
};

FurySim.prototype.tackle = function (this: FurySim, tacklerIndex: number, carrierIndex: number, strength: number, dive: boolean): boolean {
  const t = this.players[tacklerIndex];
  const c = this.players[carrierIndex];
  if (this.phase !== Phase.Live || !c.hasBall) {
    return false;
  }
  const furyHit = this.teams[t.team].inFury();
  const toTackler = t.p.sub(c.p).safeNormal();
  const front = Vec2.dot(toTackler, FromAngle(c.yaw));     // 1 = tackler straight ahead

  // Evasion: a spin or a hurdle makes most tackles whiff.
  if (c.evadeLeft > 0 && !furyHit) {
    const hurdling = c.act === Act.Hurdle;
    const escape = hurdling ? (dive ? 0.95 : 0.25) : 0.72;
    if (this.chance(escape)) {
      // A move beats one tackler, not the whole pursuit.
      if (!hurdling) { c.evadeLeft = 0; }
      t.cooldown = 0.8;
      if (!t.busy) { this.setAct(t, Act.Stumble, 0, 0.5, 0, true); t.launch = t.v.mul(0.6); }
      this.addFury(c.team, 0.02);
      this.emit(Ev.BrokenTackle, c.team, carrierIndex, tacklerIndex);
      return false;
    }
  }
  // A stiff arm flattens a tackler coming from the front or the side.
  if (c.stiffLeft > 0 && front > -0.25 && !furyHit && this.chance(dive ? 0.4 : 0.78)) {
    c.stiffLeft = 0;
    this.knock(tacklerIndex, carrierIndex, Fall.Back, 1.1, toTackler.mul(420), 0);
    t.cooldown = 1;
    this.addFury(c.team, 0.03);
    this.emit(Ev.StiffArm, c.team, carrierIndex, tacklerIndex);
    return false;
  }

  // A quarterback caught holding the ball goes down easily. One running a designed keeper is a runner.
  const pocketQB = c.slot === 0 && c.team === this.offense && !this.ballCrossedLine && !this.changeOfPossession && c.job.job !== Job.Keeper;
  let odds = 0.74 + 0.2 * strength + 0.22 * (t.power - c.power);
  if (dive) { odds += 0.14; }
  if (this.playType === PlayType.Kickoff || this.playType === PlayType.Punt) { odds += 0.08; }    // coverage teams tackle surely
  if (front < -0.3) { odds += 0.06; }
  if (pocketQB) { odds += 0.2; }
  if (t.seat !== NONE) { odds += 0.05; }
  else { odds += 0.25 * (this.cpuSkill - 0.5); }       // better computer teams wrap up; weaker ones miss
  if (this.teams[c.team].inFury()) { odds -= 0.25; }
  odds = furyHit ? 1 : FMath.clamp(odds, 0.35, 0.99);

  if (!this.chance(odds)) {
    // Broken tackle: the defender bounces off, the runner loses a step.
    t.cooldown = 0.9;
    if (!t.busy) {
      if (this.chance(0.5)) { this.knock(tacklerIndex, carrierIndex, Fall.Back, 0.5, toTackler.mul(260), 0); }
      else { this.setAct(t, Act.Stumble, 0, 0.5, 0, true); t.launch = t.v.mul(0.5); }
    }
    c.v = c.v.mul(0.72);
    this.addFury(c.team, 0.02);
    this.emit(Ev.BrokenTackle, c.team, carrierIndex, tacklerIndex);
    return false;
  }

  // He is going down. How hard? A big hit is a deliberate one: the hit button, a defender
  // unloading, or a team in Fury.
  const big = furyHit || strength >= 0.99;
  let fall = front > 0.35 ? Fall.Back : front < -0.35 ? Fall.Front : (big ? Fall.Spin : Fall.Back);
  if (big && this.chance(0.45)) { fall = Fall.Flip; }
  const push = toTackler.neg().mul(big ? 520 : 300).add(t.v.mul(0.35));

  let fumbleOdds = 0.006 + 0.012 * strength + (big ? 0.035 : 0);
  if (furyHit) { fumbleOdds *= 2.5; }
  if (pocketQB) { fumbleOdds *= 1.6; }
  if (c.act === Act.Hurdle) { fumbleOdds *= 2; }
  if (this.teams[c.team].inFury()) { fumbleOdds *= 0.3; }
  if (this.playType === PlayType.TwoPoint) { fumbleOdds = 0; }
  const fumble = this.chance(Math.min(fumbleOdds, 0.45));

  const spotX = c.p.x, spotY = c.p.y;
  this.knock(carrierIndex, tacklerIndex, fall, fumble ? 1.2 : 1.45, push, 0);
  t.yaw = AngleOf(toTackler.neg());
  if (dive) {
    t.launch = push.mul(0.65);
  } else if (t.act !== Act.BigHit && t.act !== Act.Shove) {
    // A running collision has already reached the opponent. Begin the wrap or
    // shoulder on its authored contact frame while the runner starts reacting.
    const key = big ? 0.12 : 0.18;
    this.setAct(t, big ? Act.BigHit : Act.Tackle, 0, big ? 0.48 : 0.63, key, true);
    t.actTime = key;
    t.keyDone = true;
    t.launch = push.mul(big ? 0.45 : 0.8);
  } else {
    t.launch = push.mul(0.45);
  }

  if (t.seat !== NONE) {
    ++this.seats[t.seat].tackles;
    if (big) { ++this.seats[t.seat].bigHits; }
  }
  if (big) { ++this.teams[t.team].bigHits; }
  this.emit(big ? Ev.BigHit : Ev.Tackle, t.team, tacklerIndex, carrierIndex, strength);
  if (big) { this.addFury(t.team, 0.04); }

  if (fumble) {
    this.fumble(carrierIndex, push);
    return true;
  }
  this.finishCarrierDown(carrierIndex, spotX, spotY, false, tacklerIndex);
  return true;
};

// ---------------------------------------------------------------------------------------------
// Catching
// ---------------------------------------------------------------------------------------------

FurySim.prototype.fieldKick = function (this: FurySim, index: number): void {
  // A kickoff or punt coming down into somebody's arms.
  const p = this.players[index];
  const receiving = this.ball.thrower === NONE || p.team !== this.players[this.ball.thrower].team;
  const odds = p.job.job === Job.Returner ? 0.97 : receiving ? 0.82 : 0.5;
  this.kickTouched = true;
  if (this.chance(odds)) {
    this.setAct(p, Act.Catch, 0, 0.35, 0.1, false);
    this.giveBall(index);
    this.emit(Ev.Catch, p.team, index);
  } else {
    // Muffed: live ball.
    this.ball.state = BallState.Loose;
    const vx = this.randRange(-260, 260);
    const vy = this.randRange(-260, 260);
    const vz = this.randRange(150, 320);
    this.ball.vel = new Vec3(vx, vy, vz);
    this.ball.time = 0;
    this.emit(Ev.Drop, p.team, index);
  }
};

FurySim.prototype.completeCatch = function (this: FurySim, index: number): void {
  const p = this.players[index];
  const high = this.ball.pos.z > 185;
  this.setAct(p, Act.Catch, high ? 1 : 0, high ? 0.5 : 0.4, 0.12, false);
  if (this.ball.thrower !== NONE && p.team === this.players[this.ball.thrower].team) {
    const gainYards = (p.p.x - this.startLosX) * this.offenseDir() / Yard;
    ++this.teams[p.team].completions;
    this.giveBall(index);
    this.emit(Ev.Catch, p.team, index, this.ball.thrower, gainYards);
    if (gainYards >= 20) { this.addFury(p.team, 0.08); }
    return;
  }
  // Picked off.
  ++this.teams[p.team].picks;
  if (p.seat !== NONE) { ++this.seats[p.seat].picks; }
  this.giveBall(index);
  this.changeOfPossession = true;
  this.addFury(p.team, 0.35);
  this.emit(Ev.Intercept, p.team, index, this.ball.thrower);
  if (this.playType === PlayType.TwoPoint) {
    this.emit(Ev.TwoPointNoGood, p.team);
    this.downBall(p.p.x, p.p.y, 'NO GOOD', 'PICKED OFF', p.team);
  }
};

/**
 * The pass has arrived within reach of one or more players: one contest decides it.
 * An open receiver nearly always catches it. With a defender in the picture it becomes a fight
 * decided by who is closer to the ball; a defender alone on the ball has jumped the route.
 */
FurySim.prototype.resolveCatch = function (this: FurySim, inReach: number[]): void {
  const ball = this.ball;
  const flat = ball.pos.xy();
  const passTeam = ball.thrower !== NONE ? this.players[ball.thrower].team : this.offense;
  let receiver = NONE, defender = NONE;
  let receiverDist = 1e9, defenderDist = 1e9;
  for (const i of inReach) {
    const p = this.players[i];
    p.catchCool = 0.6;
    const dist = Vec2.dist(p.p, flat);
    if (p.team === passTeam) {
      // The intended man gets the nod over a team-mate who happens to be nearby.
      const rank = dist - (i === ball.target ? 200 : 0);
      if (rank < receiverDist) { receiverDist = rank; receiver = i; }
    } else if (dist < defenderDist) {
      defenderDist = dist;
      defender = i;
    }
  }
  if (receiver !== NONE) {
    receiverDist = Vec2.dist(this.players[receiver].p, flat);
  }

  let catchOdds = 0, pickOdds = 0, tipOdds = 0;
  if (receiver !== NONE) {
    const r = this.players[receiver];
    catchOdds = r.hands;
    if (receiver !== ball.target) { catchOdds *= 0.85; }
    if (ball.tipped) { catchOdds *= 0.65; }
    if (defender !== NONE) {
      const edge = FMath.clamp((defenderDist - receiverDist) / 70, -1, 1);    // +1: receiver has the ball to himself
      catchOdds *= 0.44 + 0.3 * edge;
      if (this.players[defender].seat === NONE) { catchOdds *= 1.08 - 0.16 * this.cpuSkill; }
      pickOdds = 0.045 - 0.04 * edge;
      tipOdds = 0.22 - 0.1 * edge;
    }
    if (r.jumpLeft > 0) { catchOdds += 0.08; }
    if (this.teams[r.team].inFury()) { catchOdds += 0.15; }
  } else if (defender !== NONE) {
    // Nobody on offense is near it. At the catch point that is a jumped route (or a bad throw);
    // on the way there, a ball batted at the line.
    const atCatchPoint = ball.time > ball.duration * 0.6;
    pickOdds = atCatchPoint ? 0.24 : 0.05;
    tipOdds = atCatchPoint ? 0.45 : 0.3;
  }
  if (defender !== NONE) {
    const df = this.players[defender];
    const humanTimed = df.seat !== NONE && df.jumpLeft > 0;
    pickOdds += (this.teamInfo(df.team).defense - 3) * 0.008 + (df.hands - 0.75) * 0.1;
    if (df.seat === NONE) { pickOdds *= 0.6 + 0.8 * this.cpuSkill; }
    if (humanTimed) { pickOdds += 0.18; tipOdds += 0.3; }
    if (ball.tipped) { pickOdds += 0.1; }
    if (this.teams[df.team].inFury()) { pickOdds += 0.12; catchOdds -= 0.15; }
    pickOdds = FMath.clamp(pickOdds, 0, 0.6);
  }
  catchOdds = FMath.clamp(catchOdds, 0, 0.99);

  const roll = this.rand();
  const high = ball.pos.z > 185;
  // Tally: 0 open catches tried, 1 contests, 2 defender-alone at the catch point, 3 defender-alone in the lane,
  // 4..6 picks from each of those, 7 tipped-ball contests.
  const kind = receiver !== NONE ? (defender !== NONE ? 1 : 0) : (ball.time > ball.duration * 0.6 ? 2 : 3);
  ++this.tally[kind];
  if (ball.tipped) { ++this.tally[7]; }
  if (roll < catchOdds) {
    this.completeCatch(receiver);
  } else if (roll < catchOdds + pickOdds) {
    ++this.tally[3 + kind];
    this.completeCatch(defender);
  } else if (defender !== NONE && roll < catchOdds + pickOdds + tipOdds) {
    // Batted. Usually it is knocked down; sometimes it pops up for anyone.
    ball.arrived = true;
    this.setAct(this.players[defender], Act.Swat, 0, 0.5, 0.1, false);
    if (receiver !== NONE) { this.setAct(this.players[receiver], Act.Catch, high ? 1 : 0, 0.4, 0.12, false); }
    const pop = this.chance(0.3);
    ball.tipped = true;
    const vx = ball.vel.x * 0.2 + this.randRange(-200, 200);
    const vy = ball.vel.y * 0.2 + this.randRange(-200, 200);
    const vz = pop ? this.randRange(300, 460) : this.randRange(-120, 80);
    ball.vel = new Vec3(vx, vy, vz);
    ball.time = ball.duration + 1;      // from here it is a free ballistic ball
    for (const i of inReach) { this.players[i].catchCool = pop ? 0.3 : 2; }
    this.emit(Ev.Tip, this.players[defender].team, defender);
  } else if (receiver !== NONE) {
    // Off his hands and down.
    ball.arrived = true;
    this.setAct(this.players[receiver], Act.Catch, high ? 1 : 0, 0.4, 0.12, false);
    ball.tipped = true;
    const vx = ball.vel.x * 0.25 + this.randRange(-120, 120);
    const vy = ball.vel.y * 0.25 + this.randRange(-120, 120);
    const vz = this.randRange(-60, 160);
    ball.vel = new Vec3(vx, vy, vz);
    ball.time = ball.duration + 1;
    for (const i of inReach) { this.players[i].catchCool = 2; }
    this.emit(Ev.Drop, this.players[receiver].team, receiver);
  }
  // Otherwise the defender simply missed it and the ball flies on.
};

// ---------------------------------------------------------------------------------------------
// Action timing
// ---------------------------------------------------------------------------------------------

FurySim.prototype.startStrike = function (this: FurySim, index: number, act: Act, aim: Vec2): void {
  const p = this.players[index];
  const big = act === Act.BigHit;
  const key = 0.12;
  const reach = big ? 82 : 102;
  const speed = big ? 900 : 560;
  let nearest = reach + speed * key;
  let heading = aim.safeNormal();
  let lunge = speed;
  for (const other of this.players) {
    if (other.team === p.team || other.down) { continue; }
    const to = other.p.sub(p.p);
    const dist = to.size();
    if (dist >= nearest || Vec2.dot(to, aim) < dist * 0.72) { continue; }
    const lead = to.add(other.v.mul(key).clampedToMaxSize(35));
    const direction = lead.safeNormal();
    if (Vec2.dot(direction, aim) < 0.68) { continue; }
    nearest = dist;
    heading = direction;
    lunge = FMath.clamp((lead.size() - reach) / key, 0, speed);
  }
  this.setAct(p, act, 0, big ? 0.48 : 0.42, key, true);
  p.yaw = AngleOf(heading);
  p.launch = heading.mul(lunge);
  p.cooldown = 0.8;
};

FurySim.prototype.startElbow = function (this: FurySim, index: number, target: number): void {
  const p = this.players[index];
  const v = this.players[target];
  const chest = floorChest(v);
  p.yaw = AngleOf(chest.sub(p.p));
  this.setAct(p, Act.ElbowDrop, 0, 0.95, 0.53, true);
  p.mark = target;
  const aim = chest.add(v.launch.mul(0.20).clampedToMaxSize(45));
  p.launch = aim.sub(elbowOffset(p.yaw)).sub(p.p).div(p.actKey).clampedToMaxSize(400);
  p.cooldown = 1.3;
};

FurySim.prototype.actKey = function (this: FurySim, index: number): void {
  const p = this.players[index];
  switch (p.act) {
    case Act.Throw:
      if (this.phase === Phase.Live) { this.releaseThrow(index); }
      break;
    case Act.Kick:
    case Act.Punt:
      if (this.phase === Phase.Live) { this.strikeKick(index); }
      break;
    case Act.BigHit:
    case Act.Shove: {
      if (this.phase !== Phase.Live && !this.afterWhistle()) { break; }
      const big = p.act === Act.BigHit;
      const facing = FromAngle(p.yaw);
      const contact = p.p.add(facing.mul(big ? 72 : 91));
      let victim = NONE;
      let best = FLOAT_MAX;
      for (let i = 0; i < NumPlayers; ++i) {
        const o = this.players[i];
        if (o.team === p.team || o.down) { continue; }
        const error = Vec2.distSquared(contact, o.p);
        if (error < best && error <= FMath.square(o.radius * 0.72)) {
          best = error;
          victim = i;
        }
      }
      if (victim === NONE) {
        break;
      }
      if (this.players[victim].hasBall && this.phase === Phase.Live) {
        this.tackle(index, victim, big ? 1 : 0.7, false);
      } else {
        const push = this.players[victim].p.sub(p.p).safeNormal().mul(big ? 460 : 330);
        const fall = Vec2.dot(FromAngle(this.players[victim].yaw), facing) > 0.35 ? Fall.Front : Fall.Back;
        this.knock(victim, index, fall, big ? 1.1 : 0.85, push, 0);
        p.launch = push.mul(0.38);
        this.emit(this.phase === Phase.Live ? (big ? Ev.BigHit : Ev.Shove) : Ev.LateHit, p.team, index, victim, big ? 0.9 : 0.5);
        if (this.phase === Phase.Live && big) { this.addFury(p.team, 0.03); }
      }
      break;
    }
    case Act.ElbowDrop:
      if (this.afterWhistle() && p.mark !== NONE) {
        const v = this.players[p.mark];
        const chest = floorChest(v);
        if (v.team !== p.team && onFloor(v) && Vec2.distSquared(p.p.add(elbowOffset(p.yaw)), chest) < FMath.square(40)) {
          const side = v.act === Act.Hit ? ((v.variant === Fall.Front || v.variant === Fall.Spin) ? 1 : 0) : v.variant;
          this.setAct(v, Act.GroundRecoil, side, 0.32, 0, true);
          v.launch = FromAngle(p.yaw).mul(85);
          this.emit(Ev.LateHit, p.team, index, p.mark, 1);
          this.events[this.events.length - 1].pos = Vec3.from2(chest, 30);
        }
      }
      p.launch = p.launch.mul(0.12);
      break;
    default:
      break;
  }
};

FurySim.prototype.actEnd = function (this: FurySim, index: number): void {
  const p = this.players[index];
  switch (p.act) {
    case Act.GroundRecoil:
      this.setAct(p, Act.Down, p.variant, 0, 0, true);
      break;
    case Act.Hit: {
      const fall = p.variant as Fall;
      this.setAct(p, Act.Down, (fall === Fall.Front || fall === Fall.Spin) ? 1 : 0, 0, 0, true);
      break;
    }
    case Act.Dive:
    case Act.Tackle:
    case Act.ElbowDrop:
      p.down = true;
      p.downLeft = p.act === Act.Dive ? 0.55 : 0.4;
      this.setAct(p, Act.Down, 1, 0, 0, true);
      break;
    case Act.DiveBall:
      p.down = true;
      p.downLeft = 1.4;
      this.setAct(p, Act.Down, 1, 0, 0, true);
      if (p.hasBall && this.phase === Phase.Live) {
        this.finishCarrierDown(index, p.p.x + Dir(p.team) * 40, p.p.y, false, NONE);
      }
      break;
    case Act.GetUp:
      p.down = false;
      p.launch = Vec2.Zero;
      this.setAct(p, Act.Move, 0, 0, 0, false);
      break;
    case Act.Celebrate:
      this.setAct(p, Act.Celebrate, 2, 0, 0, true);
      break;
    case Act.Hurdle:
      p.v = p.launch;
      p.launch = Vec2.Zero;
      this.setAct(p, Act.Move, 0, 0, 0, false);
      break;
    default:
      p.launch = Vec2.Zero;
      this.setAct(p, Act.Move, 0, 0, 0, false);
      break;
  }
};

// ---------------------------------------------------------------------------------------------
// Human control
// ---------------------------------------------------------------------------------------------

FurySim.prototype.stepHuman = function (this: FurySim, p: SimPlayer, index: number, input: SeatInput, dt: number): { wish: Vec2; speed: number } {
  const seat = this.seats[p.seat];
  const live = this.phase === Phase.Live;
  const stick = stickToWorld(input.stick);
  const steering = stick.sizeSquared() > 0.03;
  seat.idle = steering ? 0 : seat.idle + dt;

  // Turbo: a meter that drains while held and refills when released. Fury makes it bottomless.
  let turbo = false;
  if (input.turbo && steering && !seat.turboSpent) {
    turbo = true;
    if (!this.teams[p.team].inFury()) {
      seat.turbo -= dt * 0.4;
      if (seat.turbo <= 0) { seat.turbo = 0; seat.turboSpent = true; }
    }
  } else {
    seat.turbo = Math.min(1, seat.turbo + dt * 0.27);
    if (seat.turbo > 0.3) { seat.turboSpent = false; }
  }
  let wish = stick;
  let speed = this.maxSpeed(p, turbo);

  if (!live) {
    // After the whistle: wander, shove, flop. Nothing counts.
    if (this.afterWhistle() && p.cooldown <= 0) {
      const aim = steering ? stick.safeNormal() : FromAngle(p.yaw);
      if (input.B) {
        this.startStrike(index, input.turbo ? Act.BigHit : Act.Shove, aim);
      } else if (input.X) {
        // Aim at the nearest opponent in the input direction. A player
        // behind the controller should never steal the intended dive.
        let near = NONE;
        let best = 2.6 * Yard;
        for (let j = 0; j < NumPlayers; ++j) {
          const o = this.players[j];
          if (o.team === p.team) { continue; }
          const to = o.p.sub(p.p);
          const dist = to.size();
          if (dist < best && (!steering || Vec2.dot(to, aim) >= 0.5 * dist)) {
            best = dist;
            near = j;
          }
        }
        if (near !== NONE && this.players[near].down && this.players[near].act !== Act.GetUp) {
          this.startElbow(index, near);
        } else {
          this.setAct(p, Act.Dive, 0, 0.55, 0, true);
          const heading = near !== NONE ? this.players[near].p.sub(p.p).safeNormal() : aim;
          p.yaw = AngleOf(heading);
          p.launch = heading.mul(1100);
          p.cooldown = 1.1;
          this.emit(Ev.Dive, p.team, index);
        }
      }
    } else if (!this.afterWhistle()) {
      // Between plays the stick is busy with menus, so the computer walks everyone to the huddle.
      ({ wish, speed } = this.thinkAfterWhistle(p, index, dt));
    }
    return { wish, speed };
  }

  const scrimmage = this.playType === PlayType.Scrimmage || this.playType === PlayType.TwoPoint;

  if (p.hasBall) {
    const canPass = scrimmage && p.team === this.offense && !this.changeOfPossession && !this.passThrown && (p.p.x - this.losX) * this.offenseDir() < 0;
    if (canPass && p.slot === 0 && this.currentOff.kind !== PlayKind.Run) {
      // Quarterback: a button per receiver. Y = top of the screen, X or B = middle, A = bottom.
      const icon = input.Y ? 1 : (input.X || input.B) ? 2 : input.A ? 3 : 0;
      if (icon !== 0 && this.liveTime > 0.1) {
        for (let slot = 0; slot < TeamSize; ++slot) {
          const target = this.global(p.team, slot);
          if (this.players[target].passIcon === icon && !this.players[target].down) {
            this.startThrow(index, target);
            break;
          }
        }
      }
      p.face = true;
      p.faceYaw = this.offenseDir() > 0 ? 0 : PI;
      if (p.free() && !steering && seat.idle > 0.05 && this.liveTime < 1.2) {
        // Hands off the stick: drop back automatically.
        const spot = p.home.sub(new Vec2(this.offenseDir() * this.currentOff.drop * Yard, 0));
        const to = spot.sub(p.p);
        if (to.sizeSquared() > 30 * 30) {
          wish = to.safeNormal();
          speed = p.topSpeed * 0.8;
        }
      } else if (steering) {
        // Only keep facing downfield while backing up; turn and run when heading upfield.
        p.face = stick.x * this.offenseDir() < 0.3;
      }
      return { wish, speed };
    }
    if (canPass && p.slot === 0) {
      // A designed run with the quarterback still holding it: let the hand-off logic work.
      if (!steering) {
        // ThinkPasser reads the incoming OutWish/OutSpeed (stick, MaxSpeed) in the C++. simAI.ts's
        // think* wrappers take them as optional trailing arguments, beyond the sim.ts signature.
        const thinkPasserIn = this.thinkPasser as (player: SimPlayer, index: number, dt: number, inWish?: Vec2, inSpeed?: number) => { wish: Vec2; speed: number };
        return thinkPasserIn.call(this, p, index, dt, wish, speed);
      }
    }

    // Ball carrier moves.
    if (p.cooldown <= 0) {
      if (input.A) {
        this.setAct(p, Act.Spin, 0, 0.5, 0, false);
        p.evadeLeft = 0.38;
        p.cooldown = 1.6;
        this.emit(Ev.Spin, p.team, index);
      } else if (input.B) {
        this.setAct(p, Act.StiffArm, 0, 0.45, 0.15, false);
        p.stiffLeft = 0.4;
        p.cooldown = 1.6;
      } else if (input.Y) {
        this.setAct(p, Act.Hurdle, 0, 0.6, 0, true);
        p.evadeLeft = 0.5;
        p.launch = (p.v.sizeSquared() > 100 * 100 ? p.v.safeNormal() : FromAngle(p.yaw)).mul(speed * 0.9);
        p.cooldown = 1.8;
        this.emit(Ev.Hurdle, p.team, index);
      } else if (input.X) {
        this.setAct(p, Act.DiveBall, 0, 0.6, 0, true);
        p.launch = (steering ? stick.safeNormal() : FromAngle(p.yaw)).mul(speed * 1.1);
        p.yaw = AngleOf(p.launch);
        p.cooldown = 2;
        this.emit(Ev.Dive, p.team, index);
      }
    }
    if (p.act === Act.Spin) { speed *= 0.85; }
    return { wish, speed };
  }

  const myTeamHasBall = this.ballTeam === p.team && this.ball.state !== BallState.Loose;
  const ballInAir = this.ball.state === BallState.Pass || this.ball.state === BallState.Kick;

  if (myTeamHasBall && !(ballInAir && this.ball.state === BallState.Kick && this.players[this.ball.thrower].team === p.team)) {
    // Offense without the ball: run the route yourself, or leave the stick alone and it runs itself.
    if (input.A && scrimmage && !this.passThrown) {
      // Call for the ball from a computer quarterback.
      const qb = this.carrierIndex();
      if (qb !== NONE && this.players[qb].team === p.team && this.players[qb].seat === NONE && this.players[qb].slot === 0 && (this.players[qb].p.x - this.losX) * this.offenseDir() < 0) {
        this.startThrow(qb, index);
      }
    }
    if ((input.Y || input.X) && ballInAir) {
      p.jumpLeft = 0.45;
    }
    if (input.B && p.cooldown <= 0) {
      this.startStrike(index, Act.Shove, steering ? stick.safeNormal() : FromAngle(p.yaw));
    }
    if (p.free() && !steering && seat.idle > 0.12) {
      ({ wish, speed } = this.thinkPlayer(p, index, dt));
    }
    return { wish, speed };
  }

  // Defense (or a scramble for a loose ball).
  if (input.A) {
    const next = this.closestToBall(p.team, true, index);
    if (next !== NONE) {
      this.switchSeat(p.seat, next);
      return { wish, speed };
    }
  }
  if (p.cooldown <= 0) {
    const heading = steering ? AngleOf(stick) : p.yaw;
    if (input.X) {
      this.setAct(p, Act.Dive, 0, 0.55, 0, true);
      p.launch = FromAngle(heading).mul(1250);
      p.yaw = heading;
      p.cooldown = 1;
      this.emit(Ev.Dive, p.team, index);
    } else if (input.B) {
      this.startStrike(index, Act.BigHit, FromAngle(heading));
    } else if (input.Y) {
      this.setAct(p, Act.Swat, 0, 0.7, 0.28, true);
      p.jumpLeft = 0.55;
      p.launch = p.v.mul(0.5);
      p.cooldown = 0.9;
    }
  }
  if (p.free() && !steering && seat.idle > 0.6) {
    // A human who has let go of the stick is covered by the computer until they take over again.
    ({ wish, speed } = this.thinkPlayer(p, index, dt));
  }
  return { wish, speed };
};

// ---------------------------------------------------------------------------------------------
// Movement and contact
// ---------------------------------------------------------------------------------------------

FurySim.prototype.movePlayers = function (this: FurySim, dt: number, wish: Vec2[], speed: number[]): void {
  for (let i = 0; i < NumPlayers; ++i) {
    const p = this.players[i];
    if (p.engaged !== NONE) {
      continue;
    }
    if (p.down || p.busy) {
      // Carried by momentum: a dive, a lunge, or flying from a hit.
      let drag = 4;
      switch (p.act) {
        case Act.Dive: drag = p.actTime < 0.28 ? 0 : 6; break;
        case Act.DiveBall: drag = p.actTime < 0.3 ? 0 : 6; break;
        case Act.BigHit: case Act.Shove: drag = p.actTime < 0.14 ? 0 : 10; break;
        case Act.Hurdle: drag = 0; break;
        case Act.Kick: drag = p.keyDone ? 12 : 0; break;
        case Act.Hit:
          drag = 3.2;
          p.yaw += FMath.clamp(AngleDelta(p.yaw, p.faceYaw), -dt * 18, dt * 18);
          break;
        case Act.Tackle: drag = 5; break;
        case Act.ElbowDrop: drag = !p.keyDone ? 0 : 14; break;
        case Act.Down: case Act.GetUp: drag = 9; break;
        default: drag = 7; break;
      }
      const drive = p.act === Act.Dive && p.actTime < 0.055 ? 0.32 : 1;
      p.p = p.p.add(p.launch.mul(dt * drive));
      p.launch = p.launch.mul(Math.exp(-drag * dt));
      p.v = p.launch;
    } else {
      let want = wish[i];
      const size = want.size();
      if (size > 1) {
        want = want.div(size);
      }
      const target = want.mul(speed[i]);
      const delta = target.sub(p.v);
      const rate = (target.sizeSquared() >= p.v.sizeSquared() ? Accel : Decel) * dt;
      const deltaSize = delta.size();
      p.v = deltaSize <= rate ? target : p.v.add(delta.div(deltaSize).mul(rate));
      p.p = p.p.add(p.v.mul(dt));

      let wantYaw = p.yaw;
      if (p.face) {
        wantYaw = p.faceYaw;
      } else if (p.v.sizeSquared() > 70 * 70) {
        wantYaw = AngleOf(p.v);
      }
      const turn = AngleDelta(p.yaw, wantYaw);
      p.yaw += FMath.clamp(turn, -TurnRate * dt, TurnRate * dt);
    }
    // Athletes may leave the field of play but not the stadium floor.
    p.p = new Vec2(
      FMath.clamp(p.p.x, -EndLineX - 250, EndLineX + 250),
      FMath.clamp(p.p.y, -SidelineY - 280, SidelineY + 280),
    );
  }
};

FurySim.prototype.separate = function (this: FurySim): void {
  for (let a = 0; a < NumPlayers; ++a) {
    const A = this.players[a];
    if (A.down) {
      continue;
    }
    for (let b = a + 1; b < NumPlayers; ++b) {
      const B = this.players[b];
      if (B.down || A.engaged === b) {
        continue;
      }
      const delta = B.p.sub(A.p);
      const dist = delta.size();
      const min = (A.radius + B.radius) * 0.9;
      if (dist >= min || dist < 0.01) {
        continue;
      }
      const normal = delta.div(dist);
      const overlap = min - dist;
      const anchorA = A.engaged !== NONE || A.busy;
      const anchorB = B.engaged !== NONE || B.busy;
      const shareA = anchorA === anchorB ? 0.5 : anchorA ? 0 : 1;
      A.p = A.p.sub(normal.mul(overlap * shareA));
      B.p = B.p.add(normal.mul(overlap * (1 - shareA)));
    }
  }
};

FurySim.prototype.stepEngagements = function (this: FurySim, dt: number): void {
  const carrier = this.carrierIndex();
  for (let i = 0; i < NumPlayers; ++i) {
    const b = this.players[i];
    if (b.engaged === NONE || !b.blocker) {
      continue;
    }
    const j = b.engaged;
    const df = this.players[j];
    if (this.phase !== Phase.Live || b.down || df.down) {
      this.disengage(i);
      continue;
    }

    // The defender fights toward the ball; humans fight faster by holding turbo.
    let rate = 1;
    if (df.seat !== NONE && this.seats[df.seat].turbo > 0.05) { rate = 1.7; }
    if (b.seat !== NONE) { rate *= 0.75; }
    b.engageTime += dt * rate;

    let goal = this.ball.pos.xy();
    if (carrier !== NONE) {
      goal = this.players[carrier].p;
    }
    const toGoal = goal.sub(df.p).safeNormal();
    let push = 45 + 150 * (df.power - b.power);
    if (this.teams[df.team].inFury()) { push += 90; }
    if (this.teams[b.team].inFury()) { push -= 120; }
    if (b.job.job === Job.RunBlock || this.ballCrossedLine) { push -= 70; }
    df.p = df.p.add(toGoal.mul(push * dt));
    b.p = df.p.add(toGoal.mul((df.radius + b.radius) * 0.92));
    df.v = b.v = toGoal.mul(push);
    df.yaw = AngleOf(toGoal);
    b.yaw = df.yaw + PI;

    // Once the ball is well past them there is nothing left to fight over.
    let release = false;
    if (carrier !== NONE && this.players[carrier].team === b.team) {
      const past = (this.players[carrier].p.x - df.p.x) * Dir(b.team);
      release = past > 3.5 * Yard && b.engageTime > 0.5;
    }
    if (b.engageTime >= b.shedAt || release) {
      this.disengage(i);
      if (this.teams[b.team].inFury() && this.chance(0.5)) {
        this.knock(j, i, Fall.Back, 1.2, toGoal.mul(-380), 0);
        this.emit(Ev.Pancake, b.team, i, j);
      } else {
        df.burst = 1.2;
        df.react = release ? 0.25 : 0;
        this.setAct(b, Act.Stumble, 0, 0.5, 0, true);
        b.launch = toGoal.mul(-160);
        b.cooldown = 1;
      }
    }
  }
};

FurySim.prototype.stepContacts = function (this: FurySim, dt: number): void {
  void dt;   // unused in the C++ too
  const carrier = this.carrierIndex();

  // The arms reach out in front of the diver. Resolve one contest and play
  // the clamp on that step, even when a different defender ends the play.
  for (let i = 0; i < NumPlayers; ++i) {
    const p = this.players[i];
    if (p.act !== Act.Dive || p.diveSpent || p.down || p.actTime < 0.055 || p.actTime > 0.36) { continue; }
    const facing = FromAngle(p.yaw);
    const reach = p.p.add(facing.mul(97));
    let best = FLOAT_MAX;
    let victim = NONE;
    for (let j = 0; j < NumPlayers; ++j) {
      const o = this.players[j];
      if (o.team === p.team || o.down) { continue; }
      const error = Vec2.distSquared(reach, o.p);
      if (error < best && error <= FMath.square(o.radius + 9)) { victim = j; best = error; }
    }
    if (victim === NONE) { continue; }
    p.diveSpent = true;
    // The rig closes its arms eight frames into a 24-frame dive.
    p.actKey = p.actTime;
    p.actLength = p.actTime + 0.36;
    p.yaw = AngleOf(this.players[victim].p.sub(p.p));
    if (victim === carrier && this.phase === Phase.Live) {
      const c = this.players[carrier];
      if (c.act === Act.DiveBall) {
        this.emit(Ev.Tackle, p.team, i, carrier, 0.3);
        this.finishCarrierDown(carrier, c.p.x, c.p.y, false, i);
      } else { this.tackle(i, victim, 0.78, true); }
    } else {
      const drive = FromAngle(p.yaw);
      const fall = Vec2.dot(FromAngle(this.players[victim].yaw), drive) > 0.35 ? Fall.Front : Fall.Back;
      this.knock(victim, i, fall, 1, drive.mul(480), 0);
      p.launch = drive.mul(320);
      this.emit(this.afterWhistle() ? Ev.LateHit : Ev.Shove, p.team, i, victim, 0.8);
    }
  }

  if (this.phase !== Phase.Live || carrier === NONE) {
    return;
  }
  const c = this.players[carrier];
  if (c.down && c.act !== Act.DiveBall) {
    return;
  }
  for (let i = 0; i < NumPlayers && this.phase === Phase.Live; ++i) {
    const t = this.players[i];
    if (t.team === c.team || t.down || t.engaged !== NONE || t.cooldown > 0) {
      continue;
    }
    if (t.busy) {
      continue;
    }
    const reach = t.radius + c.radius + 8;
    if (Vec2.distSquared(t.p, c.p) > reach * reach) {
      continue;
    }
    if (c.act === Act.DiveBall) {
      // He has already given himself up: touched down where he is.
      this.emit(Ev.Tackle, t.team, i, carrier, 0.3);
      this.finishCarrierDown(carrier, c.p.x, c.p.y, false, i);
      break;
    }
    // Closing speed and muscle decide how hard the hit is.
    const closing = Vec2.dot(t.v.sub(c.v), c.p.sub(t.p).safeNormal());
    let strength = Math.min(FMath.clamp(closing / 900, 0, 1) * 0.6 + t.power * 0.4, 0.95);
    if (t.seat === NONE && this.chance(0.1 + 0.2 * (t.power - 0.5))) {
      strength = 1;      // a computer defender unloads
    }
    if (!this.tackle(i, carrier, strength, false)) {
      t.cooldown = Math.max(t.cooldown, 0.7);
    }
    if (this.carrierIndex() !== carrier) {
      break;
    }
  }
};

// ---------------------------------------------------------------------------------------------
// The ball
// ---------------------------------------------------------------------------------------------

FurySim.prototype.stepBall = function (this: FurySim, dt: number): void {
  if (this.afterWhistle()) { return; }
  const live = this.phase === Phase.Live;
  const ball = this.ball;
  ball.spin += dt * 14;
  switch (ball.state) {
    case BallState.Held:
      if (ball.holder !== NONE) {
        const h = this.players[ball.holder];
        ball.pos = new Vec3(h.p.x, h.p.y, h.down ? 25 : 110);
      }
      break;

    case BallState.Snap: {
      ball.time += dt;
      const alpha = FMath.clamp(ball.time / Math.max(ball.duration, 0.01), 0, 1);
      const taker = this.players[ball.target];
      const end = new Vec3(taker.p.x, taker.p.y, ball.to.z);
      ball.pos = Vec3.lerp(ball.from, end, alpha).add(new Vec3(0, 0, Math.sin(alpha * PI) * 28));
      if (alpha >= 1) {
        const catcher = this.players[ball.target];
        if (catcher.down) {
          ball.state = BallState.Loose;
          const vx = this.randRange(-200, 200);
          const vy = this.randRange(-200, 200);
          ball.vel = new Vec3(vx, vy, 200);
          ball.time = 0;
          this.emit(Ev.Fumble, catcher.team, ball.target);
        } else if (catcher.job.job === Job.Holder) {
          // Spotted for the kicker.
          ball.state = BallState.Tee;
          ball.pos = new Vec3(catcher.p.x, catcher.p.y - this.offenseDir() * 55, 14);
        } else {
          this.giveBall(ball.target);
          if (catcher.job.job === Job.Punter) {
            this.startKick(ball.target);
          } else if (catcher.act !== Act.Move || catcher.slot === 0) {
            this.setAct(catcher, Act.CatchSnap, 0, 0.3, 0.12, false);
          }
        }
      }
      break;
    }

    case BallState.Pass:
    case BallState.Kick:
    case BallState.FieldGoal: {
      ball.time += dt;
      if (ball.time <= ball.duration) {
        const t = ball.time;
        const total = Math.max(ball.duration, 0.05);
        const vz0 = (ball.to.z - ball.from.z + 0.5 * Gravity * total * total) / total;
        const flat = ball.to.sub(ball.from).div(total);
        ball.pos = new Vec3(ball.from.x + flat.x * t, ball.from.y + flat.y * t, ball.from.z + vz0 * t - 0.5 * Gravity * t * t);
        ball.vel = new Vec3(flat.x, flat.y, vz0 - Gravity * t);
      } else {
        ball.vel = ball.vel.withZ(ball.vel.z - Gravity * dt);
        ball.pos = ball.pos.add(ball.vel.mul(dt));
      }

      if (ball.state === BallState.FieldGoal) {
        const d = this.offenseDir();
        if ((ball.pos.x - d * EndLineX) * d >= 0 || ball.pos.z <= BallRadius) {
          const extra = this.playType === PlayType.ExtraPoint;
          const kicker = ball.thrower;
          ball.state = BallState.Dead;
          if (!live) {
            break;
          }
          if (ball.kickGood) {
            this.score(this.offense, extra ? 1 : 3, kicker);
            this.emit(extra ? Ev.ExtraPointGood : Ev.FieldGoalGood, this.offense, kicker);
            if (!extra) { this.pendingScoreTeam = this.offense; }
            this.downBall(ball.pos.x, 0, extra ? 'EXTRA POINT' : 'FIELD GOAL', "IT'S GOOD!", this.offense);
          } else {
            if (Math.abs(Math.abs(ball.pos.y) - FurySim.UprightHalfWidth) < 45) { this.emit(Ev.Doink, this.offense); }
            this.emit(extra ? Ev.ExtraPointNoGood : Ev.FieldGoalNoGood, this.offense, kicker);
            this.downBall(this.startLosX, this.ballY, 'NO GOOD', extra ? 'EXTRA POINT MISSED' : 'FIELD GOAL MISSED', this.defense());
          }
        }
        break;
      }

      // Out of the field of play in the air.
      if (live && (Math.abs(ball.pos.y) > SidelineY + 40 || Math.abs(ball.pos.x) > EndLineX + 40) && ball.pos.z < 250) {
        if (ball.state === BallState.Pass) {
          this.emit(Ev.Incomplete, this.offense);
          ball.state = BallState.Dead;
          if (this.playType === PlayType.TwoPoint) { this.emit(Ev.TwoPointNoGood, 1 - this.scoringTeam); }
          this.downBall(this.startLosX, this.ballY, this.playType === PlayType.TwoPoint ? 'NO GOOD' : 'INCOMPLETE', '', this.defense());
        } else {
          const receiving = 1 - this.players[ball.thrower].team;
          const endZone = ball.pos.x * Dir(receiving) < -GoalX;
          ball.state = BallState.Dead;
          this.ballTeam = receiving;
          if (endZone) { this.emit(Ev.Touchback, receiving); this.downBall(ball.pos.x, 0, 'TOUCHBACK', '', receiving); }
          else {
            const spotX = this.playType === PlayType.Kickoff ? WorldX(receiving, 35) : ball.pos.x;
            this.downBall(spotX, 0, 'OUT OF BOUNDS', `${this.teamInfo(receiving).name.toUpperCase()} BALL`, receiving);
          }
        }
        break;
      }

      // Who gets a hand on it?
      if (live && ball.state === BallState.Kick) {
        // A kick can be fielded as it comes down; the returner has first claim.
        if (ball.time > ball.duration - 0.45) {
          const flat = ball.pos.xy();
          let fielder = NONE;
          let fielderDist = 1e12;
          for (let i = 0; i < NumPlayers; ++i) {
            const p = this.players[i];
            if (p.down || p.catchCool > 0 || i === ball.thrower || p.engaged !== NONE || ball.pos.z > 235) {
              continue;
            }
            const dist = Vec2.distSquared(p.p, flat);
            if (dist > CatchReach * CatchReach) {
              continue;
            }
            p.catchCool = 0.6;
            const rank = dist - (p.job.job === Job.Returner ? 1e9 : 0);
            if (rank < fielderDist) { fielderDist = rank; fielder = i; }
          }
          if (fielder !== NONE) {
            this.fieldKick(fielder);
          }
        }
      } else if (live && ball.state === BallState.Pass) {
        // Three moments matter for a pass:
        //  - on the way, a defender standing in the lane can bat it (rare: most throws clear him);
        //  - at the catch point, everyone close by contests it once, receiver and defenders together;
        //  - after that (a tip, an overthrow) it is a free ball for anyone who can reach it.
        const flat = ball.pos.xy();
        const passTeam = ball.thrower !== NONE ? this.players[ball.thrower].team : this.offense;
        const atCatchPoint = !ball.arrived && ball.time >= ball.duration - dt * 0.5;
        const inLane = !ball.arrived && !atCatchPoint && ball.time > 0.2 && ball.time < ball.duration - 0.15;
        const free = ball.arrived;
        if (atCatchPoint || inLane || free) {
          const inReach: number[] = [];
          for (let i = 0; i < NumPlayers; ++i) {
            const p = this.players[i];
            if (p.down || p.catchCool > 0 || i === ball.thrower || p.engaged !== NONE) {
              continue;
            }
            const mate = p.team === passTeam;
            if (inLane && mate) {
              continue;
            }
            const jump = p.jumpLeft > 0;
            let reach = CatchReach + (jump ? 32 : 0);
            if (atCatchPoint) {
              // The designed catch: the receiver finishes his stride to it, defenders lunge.
              reach = (mate ? 150 : 122) + (jump ? 32 : 0);
            }
            const top = jump ? 300 : 222;
            if (ball.pos.z > top || ball.pos.z < 18 || Vec2.distSquared(p.p, flat) > reach * reach) {
              continue;
            }
            inReach.push(i);
          }
          if (atCatchPoint) {
            ball.arrived = true;
          }
          if (inReach.length > 0) {
            this.resolveCatch(inReach);
          }
        }
      }

      // Hits the turf.
      if ((ball.state === BallState.Pass || ball.state === BallState.Kick) && ball.pos.z <= BallRadius) {
        ball.pos = ball.pos.withZ(BallRadius);
        if (ball.state === BallState.Pass) {
          ball.state = BallState.Dead;
          ball.vel = new Vec3(ball.vel.x * 0.4, ball.vel.y * 0.4, 0);
          if (live) {
            this.emit(Ev.Incomplete, this.offense);
            if (this.playType === PlayType.TwoPoint) { this.emit(Ev.TwoPointNoGood, 1 - this.scoringTeam); }
            this.downBall(this.startLosX, this.ballY, this.playType === PlayType.TwoPoint ? 'NO GOOD' : 'INCOMPLETE', '', this.defense());
          }
        } else {
          // A kick nobody fielded: it bounces around, live.
          ball.state = BallState.Loose;
          const vy = ball.vel.y * 0.55 + this.randRange(-150, 150);
          ball.vel = new Vec3(ball.vel.x * 0.55, vy, Math.abs(ball.vel.z) * 0.42);
          ball.time = 0;
        }
      }
      break;
    }

    case BallState.Loose: {
      ball.time += dt;
      ball.vel = ball.vel.withZ(ball.vel.z - Gravity * dt);
      ball.pos = ball.pos.add(ball.vel.mul(dt));
      if (ball.pos.z <= BallRadius) {
        ball.pos = ball.pos.withZ(BallRadius);
        if (ball.vel.z < -120) {
          // A football never bounces straight.
          const kick = this.randRange(-0.5, 0.5);
          const flat = new Vec2(ball.vel.x, ball.vel.y).rotatedDeg(FMath.radiansToDegrees(kick)).mul(0.72);
          ball.vel = new Vec3(flat.x, flat.y, -ball.vel.z * this.randRange(0.35, 0.6));
        } else {
          ball.vel = new Vec3(ball.vel.x * Math.exp(-2.2 * dt), ball.vel.y * Math.exp(-2.2 * dt), 0);
        }
      }
      if (!live) {
        break;
      }

      const kickPlay = this.playType === PlayType.Kickoff || this.playType === PlayType.Punt;
      // Out of bounds or abandoned.
      const out = Math.abs(ball.pos.y) > SidelineY || Math.abs(ball.pos.x) > EndLineX;
      if (out || ball.time > 7) {
        let owner = this.ballTeam;
        if (kickPlay && ball.thrower !== NONE && !this.kickPossessed) {
          owner = 1 - this.players[ball.thrower].team;      // an untouched kick belongs to the receiving side
        }
        this.ballTeam = owner;
        ball.state = BallState.Dead;
        const ownEndZone = ball.pos.x * Dir(owner) <= -GoalX;
        if (ownEndZone && (kickPlay || this.changeOfPossession) && !this.returnEnteredField) {
          this.emit(Ev.Touchback, owner);
          this.downBall(ball.pos.x, 0, 'TOUCHBACK', '', owner);
        } else if (ownEndZone) {
          this.score(1 - owner, 2, NONE);
          this.pendingScoreTeam = 1 - owner;
          this.emit(Ev.Safety, 1 - owner);
          this.downBall(ball.pos.x, 0, 'SAFETY', 'TWO POINTS', 1 - owner);
        } else {
          const spotX = FMath.clamp(ball.pos.x, -GoalX + Yard, GoalX - Yard);
          if (!kickPlay && owner === this.offense && !this.changeOfPossession) {
            this.finishLooseBallDown(spotX, ball.pos.y);
          } else {
            this.downBall(spotX, ball.pos.y, 'OUT OF BOUNDS', `${this.teamInfo(owner).name.toUpperCase()} BALL`, owner);
          }
        }
        break;
      }
      // A kick that rolls dead in the end zone is a touchback.
      if (kickPlay && ball.thrower !== NONE && !this.kickPossessed) {
        const receiving = 1 - this.players[ball.thrower].team;
        if (ball.pos.x * Dir(receiving) < -GoalX - 30 && ball.pos.z < 40) {
          this.ballTeam = receiving;
          ball.state = BallState.Dead;
          this.emit(Ev.Touchback, receiving);
          this.downBall(ball.pos.x, 0, 'TOUCHBACK', '', receiving);
          break;
        }
      }

      // Recovery.
      if (ball.pos.z < 95 && ball.time > 0.25) {
        const flat = ball.pos.xy();
        for (let i = 0; i < NumPlayers; ++i) {
          const p = this.players[i];
          const sliding = p.act === Act.Dive && p.actTime < 0.5;
          if ((p.down && !sliding) || p.catchCool > 0 || p.engaged !== NONE) {
            continue;
          }
          if (Vec2.distSquared(p.p, flat) > FMath.square(p.radius + 38)) {
            continue;
          }
          p.catchCool = 0.5;
          if (!this.chance(sliding ? 0.95 : 0.72)) {
            // Booted it.
            const vx = p.v.x * 0.6 + this.randRange(-200, 200);
            const vy = p.v.y * 0.6 + this.randRange(-200, 200);
            const vz = this.randRange(150, 300);
            ball.vel = new Vec3(vx, vy, vz);
            continue;
          }
          const previous = this.ballTeam;
          // A punt first touched by the kicking team is simply downed there.
          if (this.playType === PlayType.Punt && !this.kickTouched && ball.thrower !== NONE && p.team === this.players[ball.thrower].team) {
            this.ballTeam = 1 - p.team;
            ball.state = BallState.Dead;
            this.downBall(ball.pos.x, ball.pos.y, 'PUNT DOWNED', `${this.teamInfo(this.ballTeam).name.toUpperCase()} BALL`, this.ballTeam);
            break;
          }
          this.kickTouched = true;
          if (!p.down && !sliding) {
            this.setAct(p, Act.PickUp, 0, 0.4, 0.2, false);
          }
          this.giveBall(i);
          this.emit(Ev.Recover, p.team, i);
          if (!kickPlay && p.team !== previous) {
            ++this.teams[previous].fumblesLost;
            this.addFury(p.team, 0.3);
          }
          if (this.playType === PlayType.TwoPoint && p.team !== this.offense) {
            this.emit(Ev.TwoPointNoGood, p.team);
            this.downBall(p.p.x, p.p.y, 'NO GOOD', 'TWO-POINT TRY FAILS', p.team);
          } else if (sliding) {
            this.finishCarrierDown(i, p.p.x, p.p.y, false, NONE);     // fell on it
          }
          break;
        }
      }
      break;
    }

    case BallState.Dead:
      // Let an incomplete pass skid to a stop instead of freezing in mid-air.
      if (ball.pos.z > BallRadius || !isNearlyZero3(ball.vel, 1)) {
        ball.vel = ball.vel.withZ(ball.vel.z - Gravity * dt);
        ball.pos = ball.pos.add(ball.vel.mul(dt));
        if (ball.pos.z <= BallRadius) {
          ball.pos = ball.pos.withZ(BallRadius);
          ball.vel = new Vec3(ball.vel.x * Math.exp(-3 * dt), ball.vel.y * Math.exp(-3 * dt), ball.vel.z < -150 ? -ball.vel.z * 0.35 : 0);
        }
      }
      break;

    default:
      break;
  }
};

/** FVector::IsNearlyZero: every component within the tolerance. (Vec3 in core.ts has no such method.) */
function isNearlyZero3(v: Vec3, tolerance: number): boolean {
  return Math.abs(v.x) <= tolerance && Math.abs(v.y) <= tolerance && Math.abs(v.z) <= tolerance;
}

/** A loose ball went out of bounds while the offense still owned it: an ordinary dead ball at that spot. */
FurySim.prototype.finishLooseBallDown = function (this: FurySim, spotX: number, spotY: number): void {
  const d = this.offenseDir();
  const gain = (spotX - this.startLosX) * d / Yard;
  this.playYards = gain;
  this.firstDownMade = (spotX - this.firstDownX) * d >= 0;
  this.downBall(spotX, spotY, 'OUT OF BOUNDS', 'FUMBLED OUT', this.offense);
};

/** FurySim.cpp: the whistle at a spot during live play. (Declared under simPlay.ts in the contract.) */
FurySim.prototype.downBall = function (this: FurySim, spotX: number, spotY: number, title: string, detail: string, team: number): void {
  if (this.phase !== Phase.Live) {
    return;
  }
  this.deadSpotX = spotX;
  this.deadSpotY = spotY;
  this.endPlay(title, detail, team);
};

// ---------------------------------------------------------------------------------------------
// Rules that end a live play
// ---------------------------------------------------------------------------------------------

FurySim.prototype.stepRules = function (this: FurySim): void {
  if (this.phase !== Phase.Live) {
    return;
  }
  const carrier = this.carrierIndex();
  if (carrier !== NONE) {
    const c = this.players[carrier];
    const d = Dir(c.team);
    if ((this.kickPossessed || this.changeOfPossession) && c.p.x * d > -GoalX) { this.returnEnteredField = true; }

    // Once the ball is past the line (or in anyone's hands but the passer's) the play is "on".
    if (!this.ballCrossedLine) {
      const kickPlay = this.playType === PlayType.Kickoff || this.playType === PlayType.Punt;
      const passer = c.team === this.offense && c.slot === 0 && !this.changeOfPossession;
      if (kickPlay ? this.kickPossessed : (!passer || (c.p.x - this.losX) * this.offenseDir() > 0.4 * Yard)) {
        this.ballCrossedLine = true;
      }
    }

    // Touchdown.
    if (c.p.x * d >= GoalX && !c.down) {
      if (this.playType === PlayType.TwoPoint) {
        if (c.team === this.offense) {
          this.score(this.offense, 2, carrier);
          this.emit(Ev.TwoPointGood, this.offense, carrier);
          this.downBall(c.p.x, c.p.y, 'TWO POINTS!', 'CONVERSION IS GOOD', this.offense);
        } else {
          this.downBall(c.p.x, c.p.y, 'NO GOOD', '', c.team);
        }
        return;
      }
      const fromScrimmage = c.team === this.offense && !this.changeOfPossession && this.playType === PlayType.Scrimmage;
      const gain = (GoalX - (fromScrimmage ? this.startLosX : this.returnStartX) * d) / Yard;
      if (c.team === this.offense && !this.changeOfPossession && this.playType === PlayType.Scrimmage) {
        if (this.passThrown) { this.teams[this.offense].passYards += FMath.roundToInt(gain); }
        else { this.teams[this.offense].rushYards += FMath.roundToInt(gain); }
      }
      ++this.teams[c.team].touchdowns;
      this.score(c.team, 6, carrier);
      if (c.seat !== NONE) { ++this.seats[c.seat].touchdowns; }
      if (this.passThrown && this.passSeat !== NONE && this.passSeat !== c.seat && this.seats[this.passSeat].team === c.team && !this.changeOfPossession) {
        ++this.seats[this.passSeat].touchdowns; // both seats contributed when another player caught the pass
      }
      const yards = Math.max(0, FMath.roundToInt(gain));
      const type = this.playType === PlayType.Kickoff ? 'KICK RETURN' : this.playType === PlayType.Punt ? 'PUNT RETURN'
        : this.changeOfPossession ? 'TURNOVER RETURN' : this.passThrown ? 'RECEPTION' : 'RUN';
      if (yards > this.teams[c.team].longestTD) {
        this.teams[c.team].longestTD = yards;
        this.teams[c.team].longestScorer = c.roster;
        this.teams[c.team].longestType = type;
      }
      this.addFury(c.team, 0.12);
      this.resultTitle = 'TOUCHDOWN!';
      const player = this.rosterOf(c);
      this.resultDetail = `${this.teamInfo(c.team).abbr}   /   #${player.number} ${player.name.toUpperCase()}   /   ${yards} YD ${type}`;
      this.resultTeam = c.team;
      this.ballTeam = c.team;
      this.emit(Ev.Touchdown, c.team, carrier, NONE, gain);
      this.beginAfterWhistle(Phase.Celebrate, c.p);
      return;
    }

    // Stepped out.
    if (Math.abs(c.p.y) > SidelineY || c.p.x * d < -EndLineX) {
      this.emit(Ev.OutOfBounds, c.team, carrier);
      this.finishCarrierDown(carrier, c.p.x, FMath.clamp(c.p.y, -SidelineY, SidelineY), true, NONE);
      return;
    }
  }

  // A play that somehow never ends is blown dead.
  if (this.liveTime > 30) {
    console.warn(`Play blown dead after 30 s (ball state ${this.ball.state}, play type ${this.playType})`);
    if (carrier !== NONE) {
      const c = this.players[carrier];
      const f0 = (v: number) => v.toFixed(0);
      const b = (v: boolean) => (v ? 1 : 0);
      console.warn(`  carrier team ${c.team} slot ${c.slot} seat ${c.seat} job ${c.job.job} act ${c.act} down ${b(c.down)} busy ${b(c.busy)} engaged ${c.engaged} pos (${f0(c.p.x)}, ${f0(c.p.y)}) vel (${f0(c.v.x)}, ${f0(c.v.y)}) los ${f0(this.losX)} crossed ${b(this.ballCrossedLine)} thrown ${b(this.passThrown)} kind ${this.currentOff.kind} scramble ${b(c.scramble)}`);
      for (let i = 0; i < NumPlayers; ++i) {
        const o = this.players[i];
        if (o.team !== c.team) {
          console.warn(`    def slot ${o.slot} job ${o.job.job} act ${o.act} down ${b(o.down)} busy ${b(o.busy)} engaged ${o.engaged} pursue ${b(o.pursue)} read ${o.readLeft.toFixed(2)} react ${o.react.toFixed(2)} pos (${f0(o.p.x)}, ${f0(o.p.y)}) cool ${o.cooldown.toFixed(2)}`);
        }
      }
    }
    if (carrier !== NONE) {
      this.finishCarrierDown(carrier, this.players[carrier].p.x, this.players[carrier].p.y, false, NONE);
    } else {
      this.ball.state = BallState.Dead;
      this.downBall(FMath.clamp(this.ball.pos.x, -GoalX + Yard, GoalX - Yard), this.ball.pos.y, '', '', this.ballTeam);
    }
  }
};

// ---------------------------------------------------------------------------------------------
// One step of everything that moves
// ---------------------------------------------------------------------------------------------

FurySim.prototype.stepLive = function (this: FurySim, dt: number, inputs: SeatInput[]): void {
  const live = this.phase === Phase.Live;
  if (live) {
    this.liveTime += dt;
    const timed = this.playType !== PlayType.ExtraPoint && this.playType !== PlayType.TwoPoint;
    if (timed && !this.overtime && this.clock > 0) {
      this.clock -= dt;
      if (this.clock <= 0) {
        this.clock = 0;
        this.clockExpired = true;
      }
      if (this.quarter === 4 && this.clock < 30 && !this.twoMinuteCalled) {
        this.twoMinuteCalled = true;
        this.emit(Ev.TwoMinute);
      }
    }
  }

  // Position history, for coverage that reacts a moment late.
  this.trailTimer += dt;
  while (this.trailTimer >= 1 / 30) {
    this.trailTimer -= 1 / 30;
    this.trailHead = (this.trailHead + 1) % FurySim.TrailLength;
    for (let i = 0; i < NumPlayers; ++i) {
      this.trail[i][this.trailHead] = this.players[i].p;
    }
  }

  // The kick meter swings faster the longer the kick.
  if (this.kickMeterLive && !this.kickLocked) {
    const kickYards = this.fieldGoalYards();
    this.kickMeter = Math.sin(this.liveTime * (4.2 + kickYards * 0.085));
    const kicker = this.global(this.offense, 0);
    if (this.players[kicker].seat !== NONE && inputs[this.players[kicker].seat].A && this.liveTime > 0.08) {
      this.kickAim = this.kickMeter;
      this.kickLocked = true;
    }
  }
  // Kickers and punters aim with the stick.
  if (this.phase === Phase.PreSnap || live) {
    const kicker = this.global(this.playType === PlayType.Kickoff ? this.kickingTeam : this.offense, 0);
    if (this.players[kicker].seat !== NONE) {
      this.kickSteer = stickToWorld(inputs[this.players[kicker].seat].stick);
    }
  }

  let handledSeats = 0;
  const wish: Vec2[] = new Array(NumPlayers);
  const speed: number[] = new Array(NumPlayers);
  for (let i = 0; i < NumPlayers; ++i) {
    const p = this.players[i];
    wish[i] = Vec2.Zero;
    speed[i] = 0;
    p.actTime += dt;
    p.cooldown = Math.max(0, p.cooldown - dt);
    p.catchCool = Math.max(0, p.catchCool - dt);
    p.evadeLeft = Math.max(0, p.evadeLeft - dt);
    p.stiffLeft = Math.max(0, p.stiffLeft - dt);
    p.jumpLeft = Math.max(0, p.jumpLeft - dt);
    p.burst = Math.max(0, p.burst - dt);
    p.burstCool = Math.max(0, p.burstCool - dt);
    p.face = false;
    if (this.phase === Phase.Celebrate && this.phaseTime > 1.6 && (p.act === Act.Celebrate || p.act === Act.Dejected)) {
      this.setAct(p, Act.Move, 0, 0, 0, false);
    }

    if (!p.keyDone && p.actTime >= p.actKey) {
      p.keyDone = true;
      this.actKey(i);
    }
    if (p.down) {
      p.downLeft -= dt;
      if (p.act === Act.Down) {
        // The tackled ball carrier stays put until the next play is set up.
        if (p.downLeft <= 0 && !p.hasBall) {
          this.setAct(p, Act.GetUp, p.variant, 0.75, 0, true);
        }
      } else if (p.actLength > 0 && p.actTime >= p.actLength) {
        this.actEnd(i);
      }
      continue;
    }
    if (p.actLength > 0 && p.actTime >= p.actLength) {
      this.actEnd(i);
    }
    if (p.engaged !== NONE || p.busy || p.down) {
      continue;
    }
    if (p.seat !== NONE) {
      // Switching to a later slot must not deliver the same press to both athletes.
      const seatBit = 1 << p.seat;
      if (!(handledSeats & seatBit)) {
        handledSeats |= seatBit;
        const out = this.stepHuman(p, i, inputs[p.seat], dt);
        wish[i] = out.wish;
        speed[i] = out.speed;
      }
    } else if (this.phase === Phase.Live) {
      const out = this.thinkPlayer(p, i, dt);
      wish[i] = out.wish;
      speed[i] = out.speed;
    } else {
      const out = this.thinkAfterWhistle(p, i, dt);
      wish[i] = out.wish;
      speed[i] = out.speed;
    }
  }

  this.movePlayers(dt, wish, speed);
  this.stepEngagements(dt);
  this.separate();
  this.stepBall(dt);
  if (this.phase === Phase.Live || this.afterWhistle()) {
    this.stepContacts(dt);
  }
  if (this.phase === Phase.Live) {
    this.stepRules();
  }
};
