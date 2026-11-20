/**
 * What every computer-controlled athlete wants to do each step (port of FurySimAI.cpp). Each think
 * function only says where to go and how fast (and occasionally triggers an action); simPlay.ts
 * moves them.
 *
 * The C++ Think functions write through OutWish/OutSpeed references and also read them (OutSpeed
 * is the incoming top speed; some branches return without writing either). Internally every
 * think function works on one shared mutable `Out` record so that behaviour is identical; the
 * public prototype methods start from the same defaults ThinkPlayer uses (zero wish,
 * MaxSpeed(P, false)) and return `{ wish, speed }`.
 */
import { FurySim } from './sim';
import {
  Act, AngleOf, BallState, Dir, EndLineX, Ev, FMath, FromAngle, GoalX, Job, NONE, NumPlayers, Phase, PI, PlayKind, PlayType,
  Pos, SidelineY, SimPlayer, Stance, TeamSize, Vec2, Vec3, Yard,
} from './core';

interface Out { wish: Vec2; speed: number }

/** Head for a point, easing off when nearly there. */
function seek(from: Vec2, to: Vec2, topSpeed: number, arrive: number, o: Out): void {
  const delta = to.sub(from);
  const dist = delta.size();
  if (dist < 8) {
    o.wish = Vec2.Zero;
    o.speed = 0;
    return;
  }
  o.wish = delta.div(dist);
  o.speed = arrive > 0 ? topSpeed * FMath.clamp(dist / arrive, 0.25, 1) : topSpeed;
}

FurySim.prototype.delayedPos = function (this: FurySim, index: number, seconds: number): Vec2 {
  const back = FMath.clamp(FMath.roundToInt(seconds * 30), 0, FurySim.TrailLength - 1);
  return this.trail[index][(this.trailHead - back + FurySim.TrailLength) % FurySim.TrailLength];
};

FurySim.prototype.pursuitPoint = function (this: FurySim, chaser: SimPlayer, runner: SimPlayer): Vec2 {
  // Run to where he is going, not where he is.
  const dist = Vec2.dist(chaser.p, runner.p);
  const time = Math.min(dist / Math.max(chaser.topSpeed, 1), 1.1);
  return this.clampToField(runner.p.add(runner.v.mul(time * 0.85)), -150);
};

FurySim.prototype.pairBlockers = function (this: FurySim): void {
  // Each lineman takes the rusher lined up nearest to him; nobody is taken twice.
  const def = this.defense();
  const taken: boolean[] = new Array(TeamSize).fill(false);
  for (let slot = 1; slot <= 3; ++slot) {
    const blocker = this.players[this.global(this.offense, slot)];
    blocker.mark = NONE;
    let best = Number.MAX_VALUE;
    for (let other = 0; other < TeamSize; ++other) {
      const rusher = this.players[this.global(def, other)];
      const rushing = rusher.job.job === Job.Rush || rusher.job.job === Job.Blitz;
      if (taken[other] || !rushing) {
        continue;
      }
      const dist = Math.abs(rusher.home.y - blocker.home.y) + Math.abs(rusher.home.x - blocker.home.x) * 0.5;
      if (dist < best) {
        best = dist;
        blocker.mark = this.global(def, other);
      }
    }
    if (blocker.mark !== NONE) {
      taken[blocker.mark % TeamSize] = true;
    }
  }
  // Receivers asked to block take the man across from them.
  for (let slot = 4; slot < TeamSize; ++slot) {
    const blocker = this.players[this.global(this.offense, slot)];
    if (blocker.job.job !== Job.RunBlock) {
      continue;
    }
    for (let other = 0; other < TeamSize; ++other) {
      const cover = this.players[this.global(def, other)];
      if (cover.job.job === Job.Man && cover.mark === this.global(this.offense, slot)) {
        blocker.mark = this.global(def, other);
      }
    }
  }
};

FurySim.prototype.pickBlockTarget = function (this: FurySim, blocker: number, protect: Vec2): number {
  const me = this.players[blocker];
  let best = NONE;
  let bestScore = 16 * Yard;
  for (let i = 0; i < NumPlayers; ++i) {
    const o = this.players[i];
    if (o.team === me.team || o.down || o.engaged !== NONE) {
      continue;
    }
    // Skip defenders a team-mate is already heading for.
    let claimed = false;
    for (let slot = 0; slot < TeamSize; ++slot) {
      const mate = this.global(me.team, slot);
      if (mate !== blocker && this.players[mate].mark === i && !this.players[mate].down && !this.players[mate].hasBall) {
        claimed = true;
      }
    }
    if (claimed) {
      continue;
    }
    const score = Vec2.dist(me.p, o.p) * 0.6 + Vec2.dist(o.p, protect);
    if (score < bestScore) {
      bestScore = score;
      best = i;
    }
  }
  return best;
};

/** How open a receiver is, in yards of separation at the catch, plus bonuses for depth. */
FurySim.prototype.openness = function (this: FurySim, receiver: number): { score: number; catchPoint: Vec2; time: number } {
  const r = this.players[receiver];
  const qbIndex = this.carrierIndex();
  // The C++ leaves the out-params untouched on the early returns; callers ignore them then.
  if (qbIndex === NONE || r.down || r.engaged !== NONE || r.react > 0.25) {
    return { score: -100, catchPoint: Vec2.Zero, time: 0 };
  }
  const q = this.players[qbIndex];
  let aim = r.p;
  let t = 0.5;
  const settled = r.routeDone && r.v.sizeSquared() < 200 * 200;
  for (let i = 0; i < 3; ++i) {
    t = 0.26 + Vec2.dist(q.p, aim) / 2700;
    aim = settled ? r.p : r.p.add(r.v.mul(t));
  }
  const catchPoint = aim;
  const time = t;
  if (Math.abs(aim.y) > SidelineY - 60 || Math.abs(aim.x) > EndLineX - 60) {
    return { score: -50, catchPoint, time };
  }

  let nearest = 1e6;
  let lanePenalty = 0;
  const lane = aim.sub(q.p);
  const laneLength = Math.max(lane.size(), 1);
  const laneDir = lane.div(laneLength);
  for (let i = 0; i < NumPlayers; ++i) {
    const o = this.players[i];
    if (o.team === r.team || o.down) {
      continue;
    }
    // Assume a defender keeps doing what he is doing for most of the ball's flight.
    const future = o.p.add(o.v.mul(Math.min(t, 0.85)));
    nearest = Math.min(nearest, Math.min(Vec2.dist(future, aim), Vec2.dist(o.p, r.p) + 60));
    // A defender sitting in the throwing lane can knock it down or pick it off.
    const along = Vec2.dot(o.p.sub(q.p), laneDir);
    if (along > 1.5 * Yard && along < laneLength * 0.8) {
      const off = Math.abs(Vec2.cross(o.p.sub(q.p), laneDir));
      if (off < 115) {
        lanePenalty = 3;
      }
    }
  }
  // Separation is what matters; depth, the designed first read and the end zone only break ties.
  const depth = ((aim.x - this.losX) * this.offenseDir()) / Yard;
  let score = Math.min(nearest / Yard, 8) + FMath.clamp(depth, -3, 25) * 0.05 - lanePenalty;
  if (r.slot === this.currentOff.primary) { score += 0.6; }
  if (aim.x * this.offenseDir() > GoalX) { score += 1; }
  return { score, catchPoint, time };
};

// ---------------------------------------------------------------------------------------------
// Dispatch
// ---------------------------------------------------------------------------------------------

function thinkPlayerImpl(sim: FurySim, p: SimPlayer, index: number, dt: number, o: Out): void {
  o.wish = Vec2.Zero;
  o.speed = sim.maxSpeed(p, false);
  if (p.react > 0) {
    p.react -= dt;
    return;
  }

  const ball = sim.ball;
  // Loose ball: the two nearest on each side go for it, everyone else gets between it and their goal.
  if (ball.state === BallState.Loose) {
    const spot = new Vec2(ball.pos.x, ball.pos.y).add(new Vec2(ball.vel.x, ball.vel.y).mul(0.25));
    let closer = 0;
    const myDist = Vec2.distSquared(p.p, spot);
    for (let slot = 0; slot < TeamSize; ++slot) {
      const mate = sim.players[sim.global(p.team, slot)];
      if (mate !== p && !mate.down && Vec2.distSquared(mate.p, spot) < myDist) {
        ++closer;
      }
    }
    if (closer < 2) {
      seek(p.p, spot, o.speed, 0, o);
      if (myDist < FMath.square(2.3 * Yard) && myDist > FMath.square(1.2 * Yard) && ball.pos.z < 60 && p.cooldown <= 0 && sim.chance(dt * 2.5)) {
        sim.setAct(p, Act.Dive, 0, 0.55, 0, true);
        p.launch = spot.sub(p.p).safeNormal().mul(1150);
        p.yaw = AngleOf(p.launch);
        p.cooldown = 1.2;
      }
    } else {
      seek(p.p, spot.sub(new Vec2(Dir(p.team) * 4 * Yard, 0)), o.speed * 0.8, 200, o);
    }
    return;
  }

  if (p.hasBall) {
    const passer = p.team === sim.offense && p.slot === 0 && !sim.changeOfPossession && !sim.passThrown && !sim.ballCrossedLine
      && (sim.playType === PlayType.Scrimmage || sim.playType === PlayType.TwoPoint);
    if (passer) {
      thinkPasserImpl(sim, p, index, dt, o);
    } else {
      thinkCarrierImpl(sim, p, index, dt, o);
    }
    return;
  }

  const kickInAir = ball.state === BallState.Kick;
  const carrier = sim.carrierIndex();
  let attacking = sim.ballTeam === p.team;
  if (kickInAir && ball.thrower !== NONE) {
    attacking = p.team !== sim.players[ball.thrower].team;      // the receiving side is "on offense" for a kick in the air
  }
  if (ball.state === BallState.Tee && sim.playType === PlayType.Kickoff) {
    return;                                                   // waiting for the kick
  }

  if (!attacking) {
    thinkDefenderImpl(sim, p, index, dt, o);
  } else if (p.job.job === Job.Route && !sim.ballCrossedLine && carrier !== NONE && sim.players[carrier].slot === 0) {
    thinkReceiverImpl(sim, p, index, dt, o);
  } else if (ball.state === BallState.Pass && (ball.target === index || p.job.job === Job.Route)) {
    thinkReceiverImpl(sim, p, index, dt, o);
  } else {
    thinkBlockerImpl(sim, p, index, dt, o);
  }
}

// ---------------------------------------------------------------------------------------------
// Offense
// ---------------------------------------------------------------------------------------------

function thinkReceiverImpl(sim: FurySim, p: SimPlayer, index: number, _dt: number, o: Out): void {
  const ball = sim.ball;
  // The ball is in the air for me: get under it.
  if (ball.state === BallState.Pass && ball.target === index) {
    const spot = ball.land();
    const left = ball.duration - ball.time;
    const dist = Vec2.dist(p.p, spot);
    if (left > 0.05) {
      // Arrive with the ball rather than early, so the catch is made in stride.
      seek(p.p, spot, o.speed, 0, o);
      o.speed = Math.min(o.speed, Math.max(dist / left, 200));
      if (left < 0.35 && ball.to.z > 150) {
        p.jumpLeft = 0.3;
      }
    } else {
      seek(p.p, new Vec2(ball.pos.x, ball.pos.y), o.speed, 0, o);
    }
    return;
  }

  if (!p.routeDone) {
    if (p.pathIndex >= p.path.length) {
      p.routeDone = true;
    } else {
      const target = p.path[p.pathIndex];
      if (Vec2.distSquared(p.p, target) < 75 * 75) {
        ++p.pathIndex;
      }
      seek(p.p, target, o.speed * 0.97, 0, o);
      return;
    }
  }

  // Route finished. A route that ends coming back to the ball settles; anything else keeps running.
  const count = p.path.length;
  const d = sim.offenseDir();
  const settle = count >= 2 && (p.path[count - 1].x - p.path[count - 2].x) * d < 0;
  if (settle || count === 0) {
    const qb = sim.global(sim.offense, 0);
    p.face = true;
    p.faceYaw = AngleOf(sim.players[qb].p.sub(p.p));
    // Drift away from the nearest defender to stay open.
    const near = sim.nearestOpponent(index, 3 * Yard);
    if (near !== NONE) {
      const away = p.p.sub(sim.players[near].p).safeNormal();
      o.wish = new Vec2(away.x * 0.3, away.y);
      o.speed *= 0.45;
    }
    return;
  }
  let heading = count >= 2 ? p.path[count - 1].sub(p.path[count - 2]).safeNormal() : new Vec2(d, 0);
  // Bend back into the field instead of running out of it.
  if (Math.abs(p.p.y) > SidelineY - 4 * Yard && p.p.y * heading.y > 0) {
    heading = new Vec2(d, -heading.y * 0.4);
  }
  if (p.p.x * d > EndLineX - 3 * Yard) {
    heading = new Vec2(0, p.p.y > 0 ? -1 : 1);
  }
  o.wish = heading.safeNormal();
  o.speed *= 0.85;
}

function thinkBlockerImpl(sim: FurySim, p: SimPlayer, index: number, dt: number, o: Out): void {
  const ball = sim.ball;
  const carrier = sim.carrierIndex();
  const d = Dir(p.team);
  const kickPlay = sim.playType === PlayType.Kickoff || sim.playType === PlayType.Punt;

  // Kick return: drop back in front of where the ball will come down, then lead the returner.
  if (kickPlay && ball.state === BallState.Kick && p.job.job === Job.ReturnBlock) {
    const wedge = ball.land().add(new Vec2(d * 11 * Yard, (p.slot - 2.5) * 3.2 * Yard));
    seek(p.p, sim.clampToField(wedge, 150), o.speed, 250, o);
    return;
  }
  // Punt coverage men and the kicking team after a kick simply chase the ball.
  if (kickPlay && ball.state === BallState.Kick) {
    thinkDefenderImpl(sim, p, index, dt, o);
    return;
  }

  const off = sim.currentOff;
  const carrierIsMate = carrier !== NONE && sim.players[carrier].team === p.team;
  const pocket = carrierIsMate && sim.players[carrier].slot === 0 && !sim.ballCrossedLine && !sim.changeOfPossession && off.kind !== PlayKind.Run
    && (sim.playType === PlayType.Scrimmage || sim.playType === PlayType.TwoPoint || sim.playType === PlayType.Punt || sim.playType === PlayType.FieldGoal || sim.playType === PlayType.ExtraPoint);
  const screenRelease = off.screen && sim.liveTime > 0.95 && p.pos === Pos.OL;

  let protect = carrierIsMate ? sim.players[carrier].p : new Vec2(ball.pos.x, ball.pos.y);
  if (ball.state === BallState.Pass) {
    protect = ball.land();
  }

  // Is the man I was blocking still worth blocking?
  if (p.mark !== NONE) {
    const m = sim.players[p.mark];
    if (m.down || (m.engaged !== NONE && m.engaged !== index) || m.team === p.team) {
      p.mark = NONE;
    }
  }

  if (pocket && !screenRelease) {
    // Pass protection: stay between my rusher and the quarterback.
    if (p.mark === NONE) {
      p.think -= dt;
      if (p.think <= 0) {
        p.think = 0.25;
        const threat = sim.pickBlockTarget(index, protect);
        if (threat !== NONE && Vec2.dist(sim.players[threat].p, protect) < 9 * Yard) {
          p.mark = threat;
        }
      }
    }
    if (p.mark === NONE) {
      const spot = p.home.sub(new Vec2(d * 1.4 * Yard, 0));
      seek(p.p, spot, o.speed * 0.6, 150, o);
      p.face = true;
      p.faceYaw = d > 0 ? 0 : PI;
      return;
    }
    const m = sim.players[p.mark];
    const between = m.p.add(protect.sub(m.p).safeNormal().mul(m.radius + p.radius + 6));
    seek(p.p, between, o.speed, 0, o);
    p.face = true;
    p.faceYaw = AngleOf(m.p.sub(p.p));
    if (Vec2.distSquared(p.p, m.p) < FMath.square(p.radius + m.radius + 20)) {
      // How long the block holds: muscle against muscle, with some luck.
      const lineman = p.pos === Pos.OL;
      let hold = (lineman ? sim.randRange(2.3, 3.7) : sim.randRange(0.9, 1.7)) - (m.power - p.power) * 1.4;
      if (m.seat === NONE) { hold -= sim.cpuSkill * 0.5; }
      sim.engage(index, p.mark, Math.max(hold, 0.6));
    }
    return;
  }

  // Run blocking and blocking downfield: find someone to hit near the ball, or escort the runner.
  if (p.mark === NONE) {
    p.think -= dt;
    if (p.think <= 0) {
      p.think = 0.2;
      p.mark = sim.pickBlockTarget(index, protect);
    }
  }
  if (p.mark !== NONE) {
    const m = sim.players[p.mark];
    seek(p.p, m.p.add(m.v.mul(0.15)), o.speed, 0, o);
    if (Vec2.distSquared(p.p, m.p) < FMath.square(p.radius + m.radius + 20)) {
      // Blocks in the open field (and on kick returns especially) do not last long.
      const hold = (kickPlay ? sim.randRange(0.5, 1.1) : sim.randRange(1.1, 2.2)) - (m.power - p.power) * 1.2;
      sim.engage(index, p.mark, Math.max(hold, 0.4));
    }
    return;
  }
  if (carrierIsMate) {
    const escort = sim.players[carrier].p.add(new Vec2(d * 4.5 * Yard, (p.slot - 3) * 1.6 * Yard));
    seek(p.p, sim.clampToField(escort, 100), o.speed, 200, o);
  } else {
    seek(p.p, protect, o.speed * 0.8, 300, o);
  }
}

function thinkPasserImpl(sim: FurySim, p: SimPlayer, index: number, dt: number, o: Out): void {
  const d = sim.offenseDir();
  const off = sim.currentOff;
  const ball = sim.ball;

  // Designed runs: get the ball to the back at the mesh point.
  if (off.kind === PlayKind.Run && p.job.job !== Job.Keeper) {
    let back = NONE;
    for (let slot = 0; slot < TeamSize; ++slot) {
      if (sim.players[sim.global(sim.offense, slot)].job.job === Job.Carry) {
        back = sim.global(sim.offense, slot);
      }
    }
    if (back !== NONE && !sim.players[back].down && sim.liveTime < 2) {
      const b = sim.players[back];
      p.face = true;
      p.faceYaw = AngleOf(b.p.sub(p.p));
      const mesh = b.path.length > 0 ? b.path[0] : p.p;
      const gap = Vec2.dist(p.p, b.p);
      if (Vec2.distSquared(b.p, mesh) < 120 * 120 || gap < 130) {
        p.hasBall = false;
        if (gap < 200) {
          sim.setAct(p, Act.Handoff, 0, 0.45, 0.2, false);
          ball.thrower = index;
          sim.giveBall(back);
          sim.emit(Ev.Handoff, sim.offense, index, back);
        } else {
          // A toss: a short flight that the back cannot miss.
          sim.setAct(p, Act.Throw, 0, 0.3, 0, false);
          ball.state = BallState.Snap;
          ball.holder = NONE;
          ball.thrower = index;
          ball.target = back;
          ball.from = Vec3.from2(p.p, 120);
          ball.to = Vec3.from2(b.p, 110);
          ball.time = 0;
          ball.duration = 0.26;
          sim.emit(Ev.Pitch, sim.offense, index, back);
        }
        sim.ballCrossedLine = true;
      }
      return;
    }
    thinkCarrierImpl(sim, p, index, dt, o);       // the back never showed: keep it
    return;
  }
  if (p.job.job === Job.Keeper) {
    thinkCarrierImpl(sim, p, index, dt, o);
    return;
  }

  // Drop back (or roll out), facing downfield.
  p.face = true;
  p.faceYaw = d > 0 ? 0 : PI;
  let spot = p.home.sub(new Vec2(d * off.drop * Yard, 0));
  if (p.path.length > 0) {
    if (p.pathIndex < p.path.length && Vec2.distSquared(p.p, p.path[p.pathIndex]) < 80 * 80) {
      ++p.pathIndex;
    }
    spot = p.path[Math.min(p.pathIndex, p.path.length - 1)];
  }
  const rusher = sim.nearestOpponent(index, 6 * Yard);
  const pressure = rusher !== NONE ? Vec2.dist(p.p, sim.players[rusher].p) : 1e6;

  if (!p.scramble) {
    seek(p.p, spot, o.speed * 0.82, 120, o);
    // Slide away from a rusher who has broken through.
    if (pressure < 3 * Yard) {
      const away = p.p.sub(sim.players[rusher].p).safeNormal();
      o.wish = o.wish.mul(0.3).add(new Vec2(away.x * 0.4, away.y)).safeNormal();
      o.speed = p.topSpeed * 0.9;
    }
  }

  // Read the field a few times a second.
  const firstLook = off.playAction ? 1.05 : off.drop <= 1.6 ? 0.5 : 0.85;
  p.think -= dt;
  if (sim.liveTime >= firstLook && p.think <= 0) {
    p.think = 0.16;
    let best = NONE;
    let bestScore = -1e6;
    for (let slot = 4; slot < TeamSize; ++slot) {
      const target = sim.global(sim.offense, slot);
      if (sim.players[target].job.job !== Job.Route) {
        continue;
      }
      // Weaker computer quarterbacks misjudge how open people are.
      const score = sim.openness(target).score + sim.randRange(-1, 1) * (1 - sim.cpuSkill) * 2.2;
      if (score > bestScore) {
        bestScore = score;
        best = target;
      }
    }
    // Wants about three yards of daylight at first; settles for less as the clock and the rush close in.
    let need = 3.6 - 0.8 * Math.max(0, sim.liveTime - 1.6);
    if (pressure < 3 * Yard) { need -= 1.2; }
    if (off.screen && sim.liveTime > 1) { need -= 1.5; }
    need = Math.max(need, 1.3);
    if (best !== NONE && bestScore >= need) {
      sim.startThrow(index, best);
      return;
    }
    // Nobody open and the pocket is gone: throw it up anyway, or run for it.
    if (pressure < 1.9 * Yard || sim.liveTime > 3.8) {
      if (best !== NONE && bestScore > 0.8 && sim.chance(0.45)) {
        sim.startThrow(index, best);
        return;
      }
      p.scramble = true;
    }
  }

  if (p.scramble) {
    thinkCarrierImpl(sim, p, index, dt, o);
    p.face = false;
  }
}

function thinkCarrierImpl(sim: FurySim, p: SimPlayer, index: number, dt: number, o: Out): void {
  const d = Dir(p.team);
  const lineDir = sim.offenseDir();

  // Bodies in the way - his own blockers, and defenders locked up with them - cannot be run
  // through. With one dead ahead the runner slides along the pile toward the nearer edge of it,
  // instead of jogging on the spot against somebody's back.
  const slidePastBodies = (wish: Vec2): Vec2 => {
    const forward = wish.safeNormal();
    if (forward.isNearlyZero()) {
      return wish;
    }
    const side = new Vec2(-forward.y, forward.x);
    let sum = 0;
    let count = 0;
    for (let i = 0; i < NumPlayers; ++i) {
      const other = sim.players[i];
      if (i === index || other.down || (other.team !== p.team && other.engaged === NONE)) {
        continue;      // free defenders are tacklers, and are dealt with as threats
      }
      const rel = other.p.sub(p.p);
      const ahead = Vec2.dot(rel, forward);
      const across = Vec2.dot(rel, side);
      if (ahead > -15 && ahead < 175 && Math.abs(across) < p.radius + other.radius + 22) {
        sum += across;
        ++count;
      }
    }
    if (count === 0) {
      return wish;
    }
    const mean = sum / count;
    // Round the side he is already nearer to; dead centre, toward the wide side of the field.
    let go = Math.abs(mean) > 6 ? -FMath.sign(mean) : FMath.sign(Vec2.dot(side, new Vec2(0, -p.p.y)));
    if (go === 0) { go = 1; }
    return forward.mul(0.3).add(side.mul(go)).safeNormal();
  };

  // A designed run follows its path until it is through the line - while the design holds up.
  // After a couple of seconds behind the line it has not: improvise.
  const designed = (p.job.job === Job.Carry || p.job.job === Job.Keeper) && p.team === sim.offense && !sim.changeOfPossession && sim.liveTime < 2.8;
  if (designed && p.pathIndex < p.path.length && (p.p.x - sim.losX) * lineDir < 3 * Yard) {
    const target = p.path[p.pathIndex];
    if (Vec2.distSquared(p.p, target) < 90 * 90) {
      ++p.pathIndex;
    }
    seek(p.p, target, o.speed, 0, o);
    o.wish = slidePastBodies(o.wish);
    return;
  }

  // Open field: head for the end zone, bending away from tacklers and the sideline.
  if (p.burst <= 0 && p.burstCool <= 0 && sim.nearestOpponent(index, 9 * Yard) !== NONE) {
    p.burst = 1.2 + sim.cpuSkill;
    p.burstCool = p.burst + 3 - sim.cpuSkill;
  }
  let steerX = d;
  let steerY = 0;
  let threat = NONE;
  let threatDist = 2.6 * Yard;
  for (let i = 0; i < NumPlayers; ++i) {
    const other = sim.players[i];
    if (other.team === p.team || other.down || other.engaged !== NONE) {
      continue;
    }
    const rel = other.p.add(other.v.mul(0.2)).sub(p.p);
    const ahead = rel.x * d;
    const dist = rel.size();
    if (ahead < -1.5 * Yard || dist > 9 * Yard) {
      continue;
    }
    const weight = FMath.square(1 - dist / (9 * Yard));
    steerY += (rel.y > 0 ? -1 : 1) * weight * (ahead > 0 ? 2.4 : 0.9);
    if (dist < threatDist && ahead > -40) {
      threatDist = dist;
      threat = i;
    }
  }
  const edge = Math.abs(p.p.y) - (SidelineY - 3.5 * Yard);
  if (edge > 0) {
    steerY -= FMath.sign(p.p.y) * (1 + edge / Yard);
  }
  steerX = d * Math.max(Math.abs(steerX), 0.35);
  o.wish = new Vec2(steerX, steerY).safeNormal();

  // A quarterback scrambling behind the line just tries to get outside the rush first.
  if (p.slot === 0 && p.team === sim.offense && (p.p.x - sim.losX) * lineDir < -1 * Yard && !sim.changeOfPossession && threat !== NONE) {
    o.wish = new Vec2(d * 0.45, p.p.y >= sim.players[threat].p.y ? 1 : -1).safeNormal();
  }
  o.wish = slidePastBodies(o.wish);

  // Moves. Better computer teams use them more.
  if (threat !== NONE && p.cooldown <= 0) {
    p.think -= dt;
    if (p.think <= 0) {
      p.think = 0.12;
      const t = sim.players[threat];
      const roll = sim.rand();
      const isReturn = sim.playType === PlayType.Kickoff || sim.playType === PlayType.Punt;
      const use = (0.25 + 0.45 * sim.cpuSkill) * (isReturn ? 0.5 : 1);
      if (t.act === Act.Dive && roll < use) {
        sim.setAct(p, Act.Hurdle, 0, 0.6, 0, true);
        p.evadeLeft = 0.5;
        p.launch = o.wish.mul(o.speed * 0.95);
        p.cooldown = 1.6;
        sim.emit(Ev.Hurdle, p.team, index);
      } else if (roll < use * 0.4) {
        sim.setAct(p, Act.Spin, 0, 0.5, 0, false);
        p.evadeLeft = 0.42;
        p.cooldown = 1.6;
        sim.emit(Ev.Spin, p.team, index);
      } else if (roll < use * 0.75) {
        sim.setAct(p, Act.StiffArm, 0, 0.45, 0.15, false);
        p.stiffLeft = 0.45;
        p.cooldown = 1.5;
      } else if (roll < use) {
        // Juke: a hard sidestep away from the tackler.
        const left = (t.p.y - p.p.y) * d > 0;
        sim.setAct(p, Act.Juke, left ? 0 : 1, 0.35, 0, false);
        p.v = new Vec2(p.v.x * 0.8, (t.p.y > p.p.y ? -1 : 1) * p.topSpeed * 0.8);
        p.evadeLeft = 0.2;
        p.cooldown = 1.4;
        sim.emit(Ev.Juke, p.team, index);
      } else {
        p.cooldown = 0.5;
      }
    }
  }
  if (p.act === Act.Spin) {
    o.speed *= 0.85;
  }
}

// ---------------------------------------------------------------------------------------------
// Defense
// ---------------------------------------------------------------------------------------------

function thinkDefenderImpl(sim: FurySim, p: SimPlayer, index: number, dt: number, o: Out): void {
  const d = sim.offenseDir();
  const carrier = sim.carrierIndex();
  const qb = sim.players[sim.global(sim.offense, 0)];
  const ball = sim.ball;

  // A kick in the air: cover it in lanes, converging as it comes down.
  if (ball.state === BallState.Kick) {
    const land = ball.land();
    const lane = p.home.y;
    const blend = FMath.clamp(ball.time / Math.max(ball.duration, 0.1), 0, 1);
    const target = new Vec2(land.x - Dir(p.team) * 1.5 * Yard, FMath.lerp(lane, land.y, 0.35 + 0.6 * blend));
    seek(p.p, target, p.job.job === Job.Kicker || p.job.job === Job.Punter ? o.speed * 0.5 : o.speed, 0, o);
    return;
  }

  // The ball is thrown: break on it after a beat.
  if (ball.state === BallState.Pass) {
    if (!p.broke) {
      p.think -= dt;
      if (p.think <= 0) {
        p.broke = true;
      }
    }
    const land = ball.land();
    const myMan = p.mark !== NONE && p.mark === ball.target;
    const near = Vec2.distSquared(p.p, land) < FMath.square(13 * Yard);
    if (p.broke && (myMan || near)) {
      // Aim for the catch point, slightly on the receiver's upfield shoulder.
      seek(p.p, land.add(new Vec2(d * 40, 0)), o.speed, 0, o);
      const left = ball.duration - ball.time;
      if (left < 0.3 && Vec2.distSquared(p.p, land) < FMath.square(2.2 * Yard)) {
        p.jumpLeft = 0.3;
      }
      return;
    }
    if (p.broke) {
      seek(p.p, land, o.speed * 0.9, 0, o);
      return;
    }
    // Not reacting yet: carry on with the assignment below.
  }

  // Rushers always go for whoever has the ball. Everyone else stays on assignment until they
  // read that the ball is out of the pocket (a hand-off, a scramble past the line, a catch) -
  // and that read takes a moment, so a defense never simply knows a run is coming.
  // A quarterback keeping it on a designed run stops being a passer once he tucks it, and nobody
  // gets to stand in the pocket all night: after a while the coverage comes down too.
  const pocketOver = carrier !== NONE && (sim.liveTime > 8 || (sim.players[carrier].job.job === Job.Keeper && sim.liveTime > 3));
  const passerInPocket = carrier !== NONE && sim.players[carrier].team === sim.offense && sim.players[carrier].slot === 0
    && !sim.ballCrossedLine && !sim.changeOfPossession && !pocketOver;
  const rushJob = p.job.job === Job.Rush || p.job.job === Job.Blitz;
  const enemyCarrier = carrier !== NONE && sim.players[carrier].team !== p.team;
  if (enemyCarrier && !passerInPocket && !p.pursue) {
    if (p.readLeft < 0) {
      const kick = sim.playType === PlayType.Kickoff || sim.playType === PlayType.Punt;
      p.readLeft = (rushJob || kick || sim.passThrown) ? 0 : sim.randRange(0.2, 0.42) * (1.35 - 0.7 * sim.cpuSkill);
    }
    p.readLeft -= dt;
    p.pursue = p.readLeft <= 0;
  }
  // A spy goes as soon as the quarterback heads for the line or breaks the pocket.
  if (passerInPocket && p.job.job === Job.Spy) {
    const q = sim.players[carrier];
    if ((q.p.x - sim.losX) * d > -1.8 * Yard || Math.abs(q.p.y - sim.ballY) > 7 * Yard) {
      p.pursue = true;
    }
  }
  if (enemyCarrier && (passerInPocket ? (rushJob || p.pursue) : p.pursue)) {
    const c = sim.players[carrier];
    // Computer defenders have a turbo of their own: a spurt when the runner is in range, then a breather.
    if (!passerInPocket && p.burst <= 0 && p.burstCool <= 0 && Vec2.distSquared(p.p, c.p) < FMath.square(16 * Yard)) {
      p.burst = 1.5 + sim.cpuSkill;
      p.burstCool = p.burst + 2.6 - sim.cpuSkill * 1.2;
    }
    const target = passerInPocket ? c.p : sim.pursuitPoint(p, c);
    seek(p.p, target, sim.maxSpeed(p, false), 0, o);
    // A runner on turbo does not simply run away from everybody: the chase matches most of it.
    if (c.seat !== NONE && c.v.sizeSquared() > FMath.square(c.topSpeed * 1.05)) {
      o.speed = Math.max(o.speed, p.topSpeed * (1 + 0.16 * (0.5 + 0.7 * sim.cpuSkill)));
    }

    // Leave the feet when he is about to get away.
    const dist = Vec2.dist(p.p, c.p);
    if (dist < 3.3 * Yard && dist > 1.3 * Yard && p.cooldown <= 0) {
      const closing = Vec2.dot(p.v.sub(c.v), c.p.sub(p.p).safeNormal());
      if (closing < 160 && sim.chance(dt * (1.2 + 2.5 * sim.cpuSkill))) {
        sim.setAct(p, Act.Dive, 0, 0.55, 0, true);
        p.launch = c.p.add(c.v.mul(0.18)).sub(p.p).safeNormal().mul(1250);
        p.yaw = AngleOf(p.launch);
        p.cooldown = 1.2;
        sim.emit(Ev.Dive, p.team, index);
      }
    }
    return;
  }

  switch (p.job.job) {
    case Job.Man: {
      if (p.mark === NONE) {
        break;
      }
      const r = sim.players[p.mark];
      // React a moment late, and give ground early in the route.
      const lag = FMath.clamp(0.3 - sim.cpuSkill * 0.22 - (sim.teamInfo(p.team).defense - 3) * 0.02, 0.06, 0.32);
      const seen = sim.delayedPos(p.mark, lag);
      const cushion = Math.max(1, p.job.cushion - sim.liveTime * 3.5);
      const target = seen.add(r.v.mul(0.12)).add(new Vec2(d * cushion * Yard, r.p.y > 0 ? -35 : 35));
      seek(p.p, target, o.speed, 60, o);
      if (Vec2.distSquared(p.p, target) < 150 * 150) {
        p.face = true;
        p.faceYaw = AngleOf(qb.p.sub(p.p));
      }
      return;
    }
    case Job.Zone: {
      // Sit in the zone; pick up the nearest receiver who wanders into it, staying on top of him.
      const centre = sim.clampToField(sim.toWorld(p.job.zone), 100);
      let target = centre;
      let best = p.job.radius * Yard;
      for (let slot = 4; slot < TeamSize; ++slot) {
        const r = sim.players[sim.global(sim.offense, slot)];
        const dist = Vec2.dist(r.p, centre);
        if (dist < best && !r.down) {
          best = dist;
          target = sim.delayedPos(sim.global(sim.offense, slot), 0.15).add(new Vec2(d * 1.6 * Yard, 0));
        }
      }
      seek(p.p, target, o.speed * 0.95, 120, o);
      p.face = true;
      p.faceYaw = AngleOf(qb.p.sub(p.p));
      return;
    }
    case Job.Spy: {
      const target = new Vec2(sim.losX + d * 4 * Yard, qb.p.y);
      seek(p.p, target, o.speed * 0.9, 120, o);
      p.face = true;
      p.faceYaw = AngleOf(qb.p.sub(p.p));
      return;
    }
    case Job.ReturnBlock:
    case Job.Returner:
      // Waiting for the kick.
      p.face = true;
      p.faceYaw = AngleOf(new Vec2(ball.pos.x, ball.pos.y).sub(p.p));
      return;
    default:
      break;
  }

  // Rushers with nobody in particular to hit, and anything unexpected: go to the ball.
  seek(p.p, new Vec2(ball.pos.x, ball.pos.y), o.speed, 0, o);
}

// ---------------------------------------------------------------------------------------------
// Between plays
// ---------------------------------------------------------------------------------------------

function thinkAfterWhistleImpl(sim: FurySim, p: SimPlayer, index: number, dt: number, o: Out): void {
  o.wish = Vec2.Zero;
  o.speed = p.topSpeed * 0.45;

  if ((sim.phase === Phase.Celebrate && sim.phaseTime <= 1.6) || sim.phase === Phase.GameOver) {
    const happy = sim.phase === Phase.GameOver ? sim.winner() : sim.scoringTeam;
    if (p.team !== happy) {
      if (p.act !== Act.Dejected && sim.phaseTime > 0.6) {
        sim.setAct(p, Act.Dejected, 0, 0, 0, true);
      }
      return;
    }
    if (index === sim.scorer && sim.phase === Phase.Celebrate) {
      if (p.act !== Act.Celebrate && sim.phaseTime > 0.25) {
        const style = sim.random.randRange(1, 2);
        sim.setAct(p, Act.Celebrate, style, 0, 0, true);
      }
      return;
    }
    // Team-mates run to the scorer (or just whoop it up after the final whistle).
    const party = sim.scorer !== NONE && sim.phase === Phase.Celebrate ? sim.players[sim.scorer].p : p.p;
    const spot = party.add(FromAngle(p.slot * 0.9).mul(230));
    if (Vec2.distSquared(p.p, spot) > 120 * 120 && sim.phase === Phase.Celebrate) {
      seek(p.p, spot, p.topSpeed * 0.8, 150, o);
    } else if (p.act !== Act.Celebrate) {
      sim.setAct(p, Act.Celebrate, 1 + (p.slot & 1), 0, 0, true);
      p.yaw = AngleOf(party.sub(p.p));
    }
    return;
  }

  if (sim.afterWhistle()) {
    // A couple of CPU players on each side join in. They take a breather
    // between attempts so a human can get back up and answer.
    if ((p.slot + sim.playCount) % 3 !== 0) { return; }
    p.think -= dt;
    if (p.cooldown > 0 || p.think > 0) { return; }
    const rival = sim.nearestOpponent(index, 16 * Yard, false);
    if (rival === NONE) { return; }
    const v = sim.players[rival];
    const to = v.p.sub(p.p);
    if (to.sizeSquared() > FMath.square(155)) {
      seek(p.p, v.p, p.topSpeed * 0.72, 0, o);
    } else if (v.act === Act.Down) {
      sim.startElbow(index, rival);
      p.think = sim.randRange(3.6, 5.8);
    } else if (!v.down) {
      sim.startStrike(index, sim.chance(0.33) ? Act.BigHit : Act.Shove, to.safeNormal());
      p.think = sim.randRange(3.6, 5.8);
    }
    return;
  }

  // Everything else: stroll to the huddle / the spot set for the next play.
  const to = p.home.sub(p.p);
  if (to.sizeSquared() > 60 * 60) {
    seek(p.p, p.home, p.topSpeed * 0.55, 200, o);
  } else if (p.act !== Act.Stand) {
    sim.setAct(p, Act.Stand, Stance.Idle, 0, 0, false);
  }
  if (p.act === Act.Stand && p.v.sizeSquared() > 60 * 60) {
    sim.setAct(p, Act.Move, 0, 0, 0, false);
  }
}

// ---------------------------------------------------------------------------------------------
// Public methods. Each starts from the defaults ThinkPlayer would hand in (no wish, the athlete's
// normal top speed) unless the caller passes its own incoming values: StepHuman calls ThinkPasser
// with OutWish = the stick and OutSpeed = MaxSpeed(P, bTurbo), and ThinkPasser leaves them as they
// are on a hand-off / pitch frame.
// ---------------------------------------------------------------------------------------------

type ThinkImpl = (sim: FurySim, p: SimPlayer, index: number, dt: number, o: Out) => void;

function wrap(impl: ThinkImpl) {
  return function (this: FurySim, player: SimPlayer, index: number, dt: number, inWish?: Vec2, inSpeed?: number): { wish: Vec2; speed: number } {
    const o: Out = { wish: inWish ?? Vec2.Zero, speed: inSpeed ?? this.maxSpeed(player, false) };
    impl(this, player, index, dt, o);
    return { wish: o.wish, speed: o.speed };
  };
}

FurySim.prototype.thinkPlayer = wrap(thinkPlayerImpl);
FurySim.prototype.thinkPasser = wrap(thinkPasserImpl);
FurySim.prototype.thinkCarrier = wrap(thinkCarrierImpl);
FurySim.prototype.thinkDefender = wrap(thinkDefenderImpl);
FurySim.prototype.thinkBlocker = wrap(thinkBlockerImpl);
FurySim.prototype.thinkReceiver = wrap(thinkReceiverImpl);
FurySim.prototype.thinkAfterWhistle = wrap(thinkAfterWhistleImpl);
