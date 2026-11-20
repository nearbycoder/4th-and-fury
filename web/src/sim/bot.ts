/**
 * A scripted stand-in for a person holding a controller (port of FuryBot.cpp).
 *
 * It looks at the match the way a player would and produces the same button presses and stick
 * movements, so the human control paths (calling plays, snapping, passing by icon, tackling,
 * switching defenders, kicking with the meter) can be exercised with no hardware attached -
 * in the headless balance test, in demo mode, and when filling seats with bots.
 */
import type { FurySim } from './sim';
import {
  BallState, Dir, FMath, Job, makeSeatInput, NONE, Phase, Pick, RandomStream, SeatInput, SidelineY, SimPlayer, TeamSize, Vec2, Yard,
} from './core';

export class FuryBot {
  private seat = 0;
  private random = new RandomStream();
  private timer = 0;          // general-purpose wait before the next press
  private hold = 0;           // how long the quarterback means to hold the ball
  private weave = 0;
  private freelance = false;  // this play the bot leaves its coverage to hunt the quarterback
  private wantCell = 4;
  private wantPage = 0;
  private wantFlip = false;
  private lastPhase: Phase = Phase.GameOver;
  private pressedThisPhase = false;

  reset(seat: number, seed: number): void {
    this.seat = seat;
    this.random.initialize(seed + seat * 7919);
    this.timer = 0;
    this.hold = 0;
    this.lastPhase = Phase.GameOver;
    this.pressedThisPhase = false;
  }

  think(sim: FurySim, dt: number): SeatInput {
    const input = makeSeatInput();
    const me = sim.seats[this.seat];
    if (!me.active) {
      return input;
    }
    const random = this.random;
    if (sim.phase !== this.lastPhase) {
      this.lastPhase = sim.phase;
      this.pressedThisPhase = false;
      this.timer = random.fRandRange(0.5, 1.4);
      this.hold = random.fRandRange(1.1, 2.6);
      this.weave = random.fRandRange(0, 6.28);
      this.freelance = random.fRand() < 0.1;
      // Decide up front which play to call, then steer the cursor there like a person would.
      this.wantCell = random.randRange(0, 8);
      this.wantPage = random.fRand() < 0.72 ? 0 : 1;
      this.wantFlip = random.fRand() < 0.4;
      if (sim.phase === Phase.PlaySelect && me.team === sim.offense && sim.captain(me.team) === this.seat) {
        const kick = new Pick();
        if (sim.chooseSituationalKick(kick)) { this.wantPage = kick.page; this.wantCell = kick.cursor; this.wantFlip = false; }
      }
    }
    this.timer -= dt;
    const captain = sim.captain(me.team) === this.seat;
    // Screen space: stick X is +X on the field, stick Y is -Y on the field.
    const stickToward = (from: Vec2, to: Vec2): Vec2 => {
      const d = to.sub(from).safeNormal();
      return new Vec2(d.x, -d.y);
    };

    switch (sim.phase) {
      case Phase.PlaySelect:
        if (captain && !sim.picks[me.team].locked && this.timer <= 0) {
          const pick = sim.picks[me.team];
          const offense = me.team === sim.offense;
          const col = pick.cursor % 3, row = Math.trunc(pick.cursor / 3);
          if (offense && pick.page !== this.wantPage) { input.RB = true; }
          else if (col !== this.wantCell % 3) { input.navX = this.wantCell % 3 > col ? 1 : -1; }
          else if (row !== Math.trunc(this.wantCell / 3)) { input.navY = Math.trunc(this.wantCell / 3) > row ? -1 : 1; }
          else if (pick.flip !== this.wantFlip) { input.X = true; }
          else { input.A = true; }
          this.timer = random.fRandRange(0.12, 0.3);
        }
        return input;

      case Phase.PatSelect:
        if (captain && this.timer <= 0) {
          if (!this.pressedThisPhase && random.fRand() < 0.2) { input.navX = 1; }
          else { input.A = true; }
          this.pressedThisPhase = true;
          this.timer = 0.4;
        }
        return input;

      case Phase.PreSnap:
        if (captain && this.timer <= 0 && sim.phaseTime > 0.5) {
          input.A = true;
          this.timer = 0.5;
        }
        return input;

      default:
        break;
    }

    if (me.player === NONE) {
      return input;
    }
    const p = sim.players[me.player];
    const d = Dir(p.team);

    if (sim.afterWhistle()) {
      // Use the same buttons as a joined player. Space out attacks so a pile
      // breaks up naturally and follow the nearest opponent when they get up.
      input.A = sim.readySeats !== 0;  // yield to a person asking for the next play
      if (!p.free() || this.timer > 0) { return input; }
      let rival: SimPlayer | null = null;
      let best = FMath.square(22 * Yard);
      for (const other of sim.players) {
        const dist = Vec2.distSquared(p.p, other.p);
        if (p.team !== other.team && dist < best) { best = dist; rival = other; }
      }
      if (!rival) { return input; }
      input.stick = stickToward(p.p, rival.p);
      if (best < FMath.square(160) && p.cooldown <= 0) {
        input.X = rival.down || random.fRand() < 0.32;
        input.B = !input.X;
        input.turbo = input.B && random.fRand() < 0.45;
        this.timer = random.fRandRange(2.3, 4.0);
      }
      return input;
    }
    if (sim.phase !== Phase.Live) {
      return input;
    }

    // The kick meter: stop it near the middle.
    if (sim.kickMeterLive && !sim.kickLocked && p.job.job === Job.Kicker) {
      if (Math.abs(sim.kickMeter) < 0.16) {
        input.A = true;
      }
      return input;
    }

    const carrier = sim.carrierIndex();
    if (p.hasBall) {
      if (sim.isPasser(me.player)) {
        // Hold it for a beat (or until someone gets close), then hit a receiver's button.
        let nearest = 1e9;
        for (const o of sim.players) {
          if (o.team !== p.team && !o.down) {
            nearest = Math.min(nearest, Vec2.dist(o.p, p.p));
          }
        }
        if (sim.liveTime > this.hold || nearest < 260) {
          // Usually throw to whoever has the most room; sometimes just chuck it.
          let icon = random.randRange(1, 3);
          if (random.fRand() < 0.7) {
            let best = -1;
            for (let slot = 0; slot < TeamSize; ++slot) {
              const r = sim.players[p.team * TeamSize + slot];
              if (r.passIcon === 0 || r.down) {
                continue;
              }
              let room = 1e9;
              for (const o of sim.players) {
                if (o.team !== p.team && !o.down) {
                  room = Math.min(room, Vec2.dist(o.p, r.p));
                }
              }
              if (room > best) {
                best = room;
                icon = r.passIcon;
              }
            }
          }
          input.Y = icon === 1;
          input.X = icon === 2;
          input.A = icon === 3;
          this.hold = sim.liveTime + 0.3;
        }
        return input;
      }
      // Run for the end zone with a weave, leaning on turbo, throwing in a move when crowded.
      this.weave += dt * 2.2;
      let wish = new Vec2(d, Math.sin(this.weave) * 0.35);
      if (Math.abs(p.p.y) > SidelineY - 500) {
        wish = wish.withY(p.p.y > 0 ? -0.6 : 0.6);
      }
      input.stick = new Vec2(wish.x, -wish.y).safeNormal();
      input.turbo = true;
      if (this.timer <= 0) {
        for (const o of sim.players) {
          if (o.team !== p.team && !o.down && Vec2.distSquared(o.p, p.p) < 230 * 230) {
            const roll = random.fRand();
            input.A = roll < 0.3;
            input.B = roll >= 0.3 && roll < 0.6;
            input.Y = roll >= 0.6 && roll < 0.75;
            this.timer = 0.9;
            break;
          }
        }
      }
      return input;
    }

    const myBall = sim.ballTeam === p.team && sim.ball.state !== BallState.Loose;
    if (myBall) {
      // Offense without the ball: mostly let the route run itself; go up for a pass thrown my way.
      if (sim.ball.state === BallState.Pass && sim.ball.target === me.player) {
        input.stick = stickToward(p.p, sim.ball.land());
        input.turbo = true;
        if (sim.ball.duration - sim.ball.time < 0.3) { input.Y = true; }
      }
      return input;
    }

    // Defense. While the quarterback still has it, a sensible player stays on their assignment
    // (hands off the stick lets the athlete cover by himself); now and then they freelance and blitz.
    if (carrier !== NONE && sim.isPasser(carrier) && !this.freelance) {
      const covering = p.job.job === Job.Man || p.job.job === Job.Zone || p.job.job === Job.Spy;
      if (covering) {
        return input;
      }
    }
    // Otherwise: chase the ball, dive when close, switch if someone else is better placed.
    let goal = new Vec2(sim.ball.pos.x, sim.ball.pos.y);
    if (carrier !== NONE) {
      goal = sim.players[carrier].p.add(sim.players[carrier].v.mul(0.3));
    } else if (sim.ball.state === BallState.Pass || sim.ball.state === BallState.Kick) {
      goal = sim.ball.land();
    }
    input.stick = stickToward(p.p, goal);
    input.turbo = true;
    const dist = Vec2.dist(p.p, goal);
    if (this.timer <= 0) {
      if (carrier !== NONE && dist < 185 && dist > 105) {
        // Close enough to finish it: usually just run through him, sometimes leave the feet or unload.
        const roll = random.fRand();
        input.X = roll < 0.3;
        input.B = roll >= 0.3 && roll < 0.5;
        this.timer = 0.8;
      } else if (sim.ball.state === BallState.Pass && dist < 200 && sim.ball.duration - sim.ball.time < 0.3) {
        input.Y = true;
        this.timer = 0.8;
      } else if (dist > 1100) {
        input.A = true;      // somebody else is closer
        this.timer = 0.7;
      }
    }
    return input;
  }
}
