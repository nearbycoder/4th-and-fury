/**
 * Shared constants, math and data types for the 4th & Fury simulation.
 *
 * This is a TypeScript port of the Unreal project's plain C++ simulation (FuryTypes.h, FurySim.h,
 * FuryPlaybook.h, FuryTeams.h). Field space: X runs goal to goal (team 0 attacks +X, team 1
 * attacks -X), Y runs sideline to sideline, Z is up, everything in centimetres (Unreal units).
 * The broadcast camera sits on the +Y side.
 *
 * Porting conventions used across src/sim:
 *  - INDEX_NONE is NONE (-1).
 *  - FVector2D / FVector are the immutable Vec2 / Vec3 below; never mutate x/y in place, so
 *    copying a value is just assignment (matching C++ value semantics).
 *  - C++ struct copies of plays / job specs use clone helpers (cloneOffPlay, cloneDefPlay, cloneJob).
 *  - FString is string, TArray is array, FMath::X is the helper of the same name below.
 */

export const NONE = -1;

export const Yard = 91.44;
export const GoalX = 50 * Yard;            // goal lines at x = +-GoalX
export const EndLineX = 60 * Yard;         // backs of the end zones
export const SidelineY = 26.6667 * Yard;   // sidelines at y = +-SidelineY
export const HashY = 6.1 * 100;            // inbound hash rows

export const TeamSize = 7;
export const NumPlayers = TeamSize * 2;
export const MaxSeats = 8;
export const MaxSeatsPerTeam = 4;

export const OffenseSlot0 = 0;
export const DefenseSlot0 = 7;
export const KickerSlot = 14;

export const PI = Math.PI;
export const SMALL_NUMBER = 1e-8;
export const KINDA_SMALL_NUMBER = 1e-4;

// ---------------------------------------------------------------------------------------------
// Vectors
// ---------------------------------------------------------------------------------------------

export class Vec2 {
  constructor(readonly x = 0, readonly y = 0) {}
  static readonly Zero = new Vec2(0, 0);

  add(o: Vec2): Vec2 { return new Vec2(this.x + o.x, this.y + o.y); }
  sub(o: Vec2): Vec2 { return new Vec2(this.x - o.x, this.y - o.y); }
  mul(s: number): Vec2 { return new Vec2(this.x * s, this.y * s); }
  /** Component-wise multiply (FVector2D * FVector2D). */
  mulv(o: Vec2): Vec2 { return new Vec2(this.x * o.x, this.y * o.y); }
  div(s: number): Vec2 { return new Vec2(this.x / s, this.y / s); }
  neg(): Vec2 { return new Vec2(-this.x, -this.y); }
  size(): number { return Math.sqrt(this.x * this.x + this.y * this.y); }
  sizeSquared(): number { return this.x * this.x + this.y * this.y; }
  /** FVector2D::GetSafeNormal (tolerance SMALL_NUMBER on the squared length). */
  safeNormal(tolerance = SMALL_NUMBER): Vec2 {
    const sq = this.x * this.x + this.y * this.y;
    if (sq > tolerance) {
      const s = 1 / Math.sqrt(sq);
      return new Vec2(this.x * s, this.y * s);
    }
    return Vec2.Zero;
  }
  isNearlyZero(tolerance = KINDA_SMALL_NUMBER): boolean {
    return Math.abs(this.x) <= tolerance && Math.abs(this.y) <= tolerance;
  }
  isZero(): boolean { return this.x === 0 && this.y === 0; }
  clampedToMaxSize(max: number): Vec2 {
    if (max < KINDA_SMALL_NUMBER) return Vec2.Zero;
    const sq = this.sizeSquared();
    if (sq > max * max) {
      const s = max / Math.sqrt(sq);
      return new Vec2(this.x * s, this.y * s);
    }
    return this;
  }
  /** FVector2D::GetRotated: the angle is in DEGREES, like Unreal. */
  rotatedDeg(angleDeg: number): Vec2 {
    const r = (angleDeg * PI) / 180;
    const c = Math.cos(r), s = Math.sin(r);
    return new Vec2(c * this.x - s * this.y, s * this.x + c * this.y);
  }
  equals(o: Vec2, tolerance = KINDA_SMALL_NUMBER): boolean {
    return Math.abs(this.x - o.x) <= tolerance && Math.abs(this.y - o.y) <= tolerance;
  }
  withX(x: number): Vec2 { return new Vec2(x, this.y); }
  withY(y: number): Vec2 { return new Vec2(this.x, y); }

  static dot(a: Vec2, b: Vec2): number { return a.x * b.x + a.y * b.y; }
  static cross(a: Vec2, b: Vec2): number { return a.x * b.y - a.y * b.x; }
  static dist(a: Vec2, b: Vec2): number { return Math.hypot(a.x - b.x, a.y - b.y); }
  static distSquared(a: Vec2, b: Vec2): number { const dx = a.x - b.x, dy = a.y - b.y; return dx * dx + dy * dy; }
  static lerp(a: Vec2, b: Vec2, t: number): Vec2 { return new Vec2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t); }
}

export class Vec3 {
  constructor(readonly x = 0, readonly y = 0, readonly z = 0) {}
  static readonly Zero = new Vec3(0, 0, 0);
  static from2(v: Vec2, z = 0): Vec3 { return new Vec3(v.x, v.y, z); }

  add(o: Vec3): Vec3 { return new Vec3(this.x + o.x, this.y + o.y, this.z + o.z); }
  sub(o: Vec3): Vec3 { return new Vec3(this.x - o.x, this.y - o.y, this.z - o.z); }
  mul(s: number): Vec3 { return new Vec3(this.x * s, this.y * s, this.z * s); }
  div(s: number): Vec3 { return new Vec3(this.x / s, this.y / s, this.z / s); }
  neg(): Vec3 { return new Vec3(-this.x, -this.y, -this.z); }
  size(): number { return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z); }
  sizeSquared(): number { return this.x * this.x + this.y * this.y + this.z * this.z; }
  size2D(): number { return Math.hypot(this.x, this.y); }
  safeNormal(tolerance = SMALL_NUMBER): Vec3 {
    const sq = this.sizeSquared();
    if (sq > tolerance) return this.mul(1 / Math.sqrt(sq));
    return Vec3.Zero;
  }
  /** FVector2D(FVector): drop Z. */
  xy(): Vec2 { return new Vec2(this.x, this.y); }
  withZ(z: number): Vec3 { return new Vec3(this.x, this.y, z); }
  static dist(a: Vec3, b: Vec3): number { return a.sub(b).size(); }
  static distSquared(a: Vec3, b: Vec3): number { return a.sub(b).sizeSquared(); }
  static dot(a: Vec3, b: Vec3): number { return a.x * b.x + a.y * b.y + a.z * b.z; }
  static lerp(a: Vec3, b: Vec3, t: number): Vec3 { return new Vec3(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t); }
}

export const v2 = (x: number, y: number) => new Vec2(x, y);
export const v3 = (x: number, y: number, z: number) => new Vec3(x, y, z);

// ---------------------------------------------------------------------------------------------
// FMath
// ---------------------------------------------------------------------------------------------

export const FMath = {
  clamp: (v: number, lo: number, hi: number) => (v < lo ? lo : v < hi ? v : hi),
  min: Math.min,
  max: Math.max,
  abs: Math.abs,
  square: (v: number) => v * v,
  sign: (v: number) => (v > 0 ? 1 : v < 0 ? -1 : 0),
  lerp: (a: number, b: number, t: number) => a + (b - a) * t,
  exp: Math.exp,
  sin: Math.sin,
  cos: Math.cos,
  atan2: Math.atan2,
  sqrt: Math.sqrt,
  /** FMath::RoundToInt32: round half up. */
  roundToInt: (v: number) => Math.floor(v + 0.5),
  ceilToInt: (v: number) => Math.ceil(v),
  floorToInt: (v: number) => Math.floor(v),
  truncToInt: (v: number) => Math.trunc(v),
  radiansToDegrees: (r: number) => (r * 180) / PI,
  degreesToRadians: (d: number) => (d * PI) / 180,
  isNearlyZero: (v: number, tol = KINDA_SMALL_NUMBER) => Math.abs(v) <= tol,
  isNearlyEqual: (a: number, b: number, tol = KINDA_SMALL_NUMBER) => Math.abs(a - b) <= tol,
  /** FMath::FindDeltaAngleRadians. */
  findDeltaAngleRadians(a1: number, a2: number): number {
    let delta = a2 - a1;
    if (delta > PI) delta -= 2 * PI;
    if (delta < -PI) delta += 2 * PI;
    return delta;
  },
  /** FMath::UnwindRadians. */
  unwindRadians(a: number): number {
    while (a > PI) a -= 2 * PI;
    while (a < -PI) a += 2 * PI;
    return a;
  },
};

// ---------------------------------------------------------------------------------------------
// FRandomStream (same generator as Unreal's, so seeds behave alike)
// ---------------------------------------------------------------------------------------------

export class RandomStream {
  private seed = 0;
  initialSeed = 0;
  constructor(seed = 0) { this.initialize(seed); }
  initialize(seed: number): void { this.initialSeed = seed | 0; this.seed = seed >>> 0; }
  private mutate(): void { this.seed = (Math.imul(this.seed, 196314165) + 907633515) >>> 0; }
  /** 0 <= result < 1 */
  fRand(): number { this.mutate(); return (this.seed >>> 9) / 8388608; }
  fRandRange(min: number, max: number): number { return min + (max - min) * this.fRand(); }
  /** Integer in [min, max] inclusive. */
  randRange(min: number, max: number): number {
    const range = max - min + 1;
    return min + (range > 0 ? Math.min(Math.trunc(this.fRand() * range), range - 1) : 0);
  }
  randHelper(a: number): number { return a > 0 ? Math.min(Math.trunc(this.fRand() * a), a - 1) : 0; }
}

// ---------------------------------------------------------------------------------------------
// Field helpers (namespace Fury)
// ---------------------------------------------------------------------------------------------

/** +1 for the team attacking +X, -1 for the team attacking -X. */
export const Dir = (team: number) => (team === 0 ? 1 : -1);
/** Yards from a team's own goal line to a world X (0 = own goal line, 100 = opponent's). */
export const YardLine = (team: number, x: number) => (x * Dir(team) + GoalX) / Yard;
export const WorldX = (team: number, yardsFromOwnGoal: number) => (yardsFromOwnGoal * Yard - GoalX) * Dir(team);
export function Approach(value: number, target: number, step: number): number {
  return value < target ? Math.min(value + step, target) : Math.max(value - step, target);
}
export const FromAngle = (r: number) => new Vec2(Math.cos(r), Math.sin(r));
export const AngleOf = (v: Vec2) => Math.atan2(v.y, v.x);
export const AngleDelta = (from: number, to: number) => FMath.findDeltaAngleRadians(from, to);

// ---------------------------------------------------------------------------------------------
// Enums (same member names and order as the C++)
// ---------------------------------------------------------------------------------------------

export enum Pos { QB, OL, WR, RB, DL, LB, CB, S, K }
export enum Build { Lean, Mid, Big }
export function BuildFor(pos: Pos): Build {
  switch (pos) {
    case Pos.OL: case Pos.DL: return Build.Big;
    case Pos.QB: case Pos.RB: case Pos.LB: return Build.Mid;
    default: return Build.Lean;
  }
}

/** What an athlete is doing, as far as animation is concerned. The simulation sets it. */
export enum Act {
  Stand,        // variant: Stance
  Move,         // free locomotion, driven by velocity
  Snap, CatchSnap, Throw, Handoff,
  Catch,        // variant 0 chest, 1 high
  Swat,
  Block,        // engaged with an opponent
  Dive,         // diving tackle
  Tackle, BigHit, Shove,
  Hit,          // variant: Fall
  Down,         // variant 0 on the back, 1 face down
  GetUp,        // variant 0 from the back, 1 from the front
  Stumble, StiffArm, Spin,
  Juke,         // variant 0 left, 1 right
  Hurdle, DiveBall, Kick, Punt, PickUp,
  Celebrate,    // variant 0 spike, 1 dance, 2 flex
  Dejected, Signal, ElbowDrop, GroundRecoil,
}
export enum Stance { Idle, Ready, ThreePoint, Center, QB, QBSet }
export enum Fall { Back, Front, Flip, Spin }
export enum Grip { None, Hand, Tuck }

export enum Phase { PlaySelect, Lineup, PreSnap, Live, Dead, Celebrate, PatSelect, Break, GameOver }
export enum PlayType { Scrimmage, Kickoff, Punt, FieldGoal, ExtraPoint, TwoPoint }
export enum BallState { Held, Snap, Pass, Kick, FieldGoal, Loose, Tee, Dead }

export enum Ev {
  PlayStart, Snap, Hut, Throw, Pitch, Handoff, Catch, Drop, Incomplete, Tip, Intercept,
  Tackle, BigHit, Sack, Fumble, Recover, BrokenTackle, StiffArm, Spin, Juke, Hurdle, Dive, DiveMiss, Shove, Pancake, LateHit,
  Touchdown, FirstDown, TurnoverOnDowns, Safety, Touchback, OutOfBounds, Whistle,
  Kickoff, PuntKick, FieldGoalKick, FieldGoalGood, FieldGoalNoGood, ExtraPointGood, ExtraPointNoGood, TwoPointGood, TwoPointNoGood, Doink,
  FuryStart, FuryEnd, PlayPicked, QuarterEnd, Halftime, Overtime, GameOver, TwoMinute,
}

export enum Job {
  None,
  // Offense
  Passer, PassBlock, RunBlock, Route, Carry, Keeper,
  // Defense
  Rush, Blitz, Man, Zone, Spy,
  // Kicking game
  Kicker, Punter, Holder, Cover, Returner, ReturnBlock,
}

export enum PlayKind { Pass, Run, Punt, FieldGoal }

// ---------------------------------------------------------------------------------------------
// Plays (FuryPlaybook.h)
// ---------------------------------------------------------------------------------------------

export interface JobSpec {
  job: Job;
  path: Vec2[];          // waypoints relative to the player's own lineup spot
  inward: boolean;       // Path Y means "toward the middle of the formation" (split receivers)
  target: number;
  delay: number;
  cushion: number;
  press: boolean;        // Man: jam the receiver at the snap
  zone: Vec2;
  radius: number;
}
export function makeJob(init: Partial<JobSpec> = {}): JobSpec {
  return { job: Job.None, path: [], inward: false, target: NONE, delay: 0, cushion: 5, press: false, zone: Vec2.Zero, radius: 8, ...init };
}
export const cloneJob = (j: JobSpec): JobSpec => ({ ...j, path: j.path.slice() });

export interface OffPlay {
  name: string;
  tagline: string;
  kind: PlayKind;
  spot: Vec2[];          // 7
  job: JobSpec[];        // 7
  drop: number;          // how far the passer drops from his spot
  primary: number;       // first read for a computer quarterback
  playAction: boolean;   // fake hand-off that freezes linebackers and safeties
  screen: boolean;       // linemen release downfield after a beat
}
export interface DefPlay {
  name: string;
  tagline: string;
  spot: Vec2[];          // 7
  job: JobSpec[];        // 7
}
export function makeOffPlay(): OffPlay {
  return { name: '', tagline: '', kind: PlayKind.Pass, spot: Array.from({ length: 7 }, () => Vec2.Zero), job: Array.from({ length: 7 }, () => makeJob()), drop: 3, primary: 4, playAction: false, screen: false };
}
export function makeDefPlay(): DefPlay {
  return { name: '', tagline: '', spot: Array.from({ length: 7 }, () => Vec2.Zero), job: Array.from({ length: 7 }, () => makeJob()) };
}
export const cloneOffPlay = (p: OffPlay): OffPlay => ({ ...p, spot: p.spot.slice(), job: p.job.map(cloneJob) });
export const cloneDefPlay = (p: DefPlay): DefPlay => ({ ...p, spot: p.spot.slice(), job: p.job.map(cloneJob) });

export const PlaysPerPage = 9;

// ---------------------------------------------------------------------------------------------
// Teams (FuryTeams.h)
// ---------------------------------------------------------------------------------------------

export interface RosterEntry {
  name: string;
  number: number;
  pos: Pos;
  skinTone: number;   // index into SkinTones
  visor: boolean;
}

/** An sRGB hex colour ("#RRGGBB"); the renderer converts to linear. */
export type Hex = string;

export interface Team {
  id: string;
  city: string;
  name: string;
  abbr: string;
  primary: Hex;
  secondary: Hex;
  accent: Hex;
  helmet: Hex;
  speed: number;     // ratings 1..5
  power: number;
  passing: number;
  defense: number;
  motto: string;
  /** Slots 0..6: QB, C, LG, RG, WR, WR, RB. Slots 7..13: DE, DT, DE, LB, CB, CB, S. Slot 14: K. */
  roster: RosterEntry[];
}
export const fullName = (t: Team) => `${t.city} ${t.name}`;

// ---------------------------------------------------------------------------------------------
// Simulation state (FurySim.h)
// ---------------------------------------------------------------------------------------------

export interface SimEvent {
  type: Ev;
  team: number;
  player: number;   // global player index (0..13)
  other: number;
  pos: Vec3;
  value: number;
}

/** One human's input for a step. Stick is screen-relative: X right, Y up. */
export interface SeatInput {
  stick: Vec2;
  turbo: boolean;
  A: boolean; B: boolean; X: boolean; Y: boolean;   // pressed this step
  LB: boolean; RB: boolean;
  navX: number; navY: number;
}
export function makeSeatInput(): SeatInput {
  return { stick: Vec2.Zero, turbo: false, A: false, B: false, X: false, Y: false, LB: false, RB: false, navX: 0, navY: 0 };
}

export class Seat {
  active = false;
  team = 0;
  player = NONE;       // global index of the athlete this human controls
  turbo = 1;
  turboSpent = false;
  idle = 0;            // seconds since this human last touched the stick
  // For the post-game sheet
  tackles = 0; touchdowns = 0; sacks = 0; picks = 0; bigHits = 0;
}

export class SimPlayer {
  // Identity
  team = 0;
  slot = 0;              // 0..6 within the unit on the field
  roster = 0;            // index into the team's roster (name, number, build)
  pos: Pos = Pos.WR;
  topSpeed = 760; power = 0.5; hands = 0.9; radius = 42;

  // Kinematics
  p: Vec2 = Vec2.Zero;
  v: Vec2 = Vec2.Zero;
  yaw = 0;
  height = 0;            // lift for launches; jumps live in the animation

  // What the athlete is doing
  act: Act = Act.Stand;
  variant = 0;
  actSerial = 0;
  actTime = 0;
  actLength = 0;         // 0 = open-ended
  actKey = 0;            // moment within the action that matters (release, contact)
  busy = false;          // cannot steer until the action ends
  keyDone = false;
  diveSpent = false;     // one collision or evasion contest per dive

  // Status
  hasBall = false;
  down = false;          // on the ground
  downLeft = 0;          // seconds until getting up
  evadeLeft = 0;         // spin / hurdle window: tackles miss
  stiffLeft = 0;         // stiff-arm window
  cooldown = 0;          // special move cooldown
  catchCool = 0;         // cannot try for the ball again until this runs out
  jumpLeft = 0;          // leaping for the ball: extra reach
  burst = 0;             // seconds of extra speed left (computer players)
  burstCool = 0;         // seconds until a computer player can burst again
  engaged = NONE;        // global index of the player locked up with
  engageTime = 0; shedAt = 0;
  blocker = false;       // in an engagement: true for the blocking side
  seat = NONE;           // human in control, if any
  launch: Vec2 = Vec2.Zero;   // velocity while flying from a hit or a dive
  face = false;          // face faceYaw this step instead of the direction of travel
  faceYaw = 0;
  scramble = false;      // quarterback has given up on the pocket
  pursue = false;        // defender has read "run" (or a catch) and is chasing the ball
  readLeft = -1;         // seconds until that read sinks in (-1 = nothing to read yet)

  // Assignment
  job: JobSpec = makeJob();
  path: Vec2[] = [];     // world waypoints
  pathIndex = 0;
  home: Vec2 = Vec2.Zero;
  mark = NONE;           // global index: man to cover / block / chase
  react = 0;             // reaction delay left
  think = 0;             // decision timer
  routeDone = false;
  broke = false;         // defender has reacted to the throw
  passIcon = 0;          // 0 none, 1 Y (top of screen), 2 X/B (middle), 3 A (bottom)

  free(): boolean { return !this.down && !this.busy && this.engaged === NONE; }
  upright(): boolean { return !this.down; }
}

export class Ball {
  state: BallState = BallState.Dead;
  pos: Vec3 = Vec3.Zero;
  vel: Vec3 = Vec3.Zero;
  holder = NONE;       // global player index
  target = NONE;       // intended receiver
  thrower = NONE;
  from: Vec3 = Vec3.Zero;
  to: Vec3 = Vec3.Zero;
  time = 0; duration = 0;
  tipped = false;
  arrived = false;     // the contest at the catch point has been held
  kickGood = false;
  spin = 0;
  land(): Vec2 { return new Vec2(this.to.x, this.to.y); }
}

export class Pick {
  page = 0;
  cursor = 4;
  flip = false;
  locked = false;
  play = NONE;         // index into the offense or defense list; -2 punt, -3 field goal
  cpuDelay = 0;
}

export class TeamState {
  league = 0;          // index into teams()
  score = 0;
  fury = 0;            // meter, 0..1
  furyPlays = 0;       // plays of Fury mode left
  completions = 0; attempts = 0; passYards = 0; rushYards = 0; sacks = 0; picks = 0; fumblesLost = 0; firstDowns = 0; bigHits = 0; touchdowns = 0;
  scoreByQuarter: number[] = [0, 0, 0, 0, 0];
  longestTD = -1; longestScorer = NONE;
  longestType = '';
  human = false;
  inFury(): boolean { return this.furyPlays > 0; }
}
