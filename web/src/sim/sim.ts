/**
 * FFurySim: the football itself: rules, movement, contact, the ball, and the computer players' brains.
 *
 * Plain TypeScript with no rendering, stepped with a fixed or variable time step, so a whole match
 * can be played headless (see simtest.ts). The director feeds it the human players' input, then
 * reads its state to drive athletes, camera, sound and interface.
 *
 * The class body holds the state. Methods are split across files exactly like the C++:
 *   simFlow.ts  <- FurySim.cpp      (match flow: setup, play select, downs, scoring, quarters)
 *   simPlay.ts  <- FurySimPlay.cpp  (live play: movement, contact, ball, rules)
 *   simAI.ts    <- FurySimAI.cpp    (the computer players' brains)
 * Each of those files assigns its methods onto FurySim.prototype; the declarations below are the
 * single source of truth for names and signatures. Import the class from ./index, which loads all
 * three method files.
 */
import {
  Ball, BallState, DefPlay, Ev, Fall, makeDefPlay, makeOffPlay, MaxSeats, NONE, NumPlayers, OffPlay, Phase, Pick, PlayType,
  RandomStream, RosterEntry, Seat, SeatInput, SimEvent, SimPlayer, Team, TeamState, Vec2, Act, Dir, EndLineX, Yard,
} from './core';
import { leagueTeams } from './teams';

export class FurySim {
  // --- Constants ---
  static readonly AfterWhistleSeconds = 3;
  static readonly MaxKickYards = 61;
  static readonly UprightHalfWidth = 282;
  static readonly CleanKickWidth = FurySim.UprightHalfWidth - 18;
  static readonly KickScatter = 35;
  static kickSpread(yards: number): number { return 250 + 14 * yards; }
  /** Position history for coverage reaction lag: 30 samples per second. */
  static readonly TrailLength = 24;

  // --- Queries for presentation (inline in FurySim.h) ---
  teamInfo(team: number): Team { return leagueTeams()[this.teams[team].league]; }
  rosterOf(player: SimPlayer): RosterEntry { return this.teamInfo(player.team).roster[player.roster]; }
  offenseDir(): number { return Dir(this.offense); }
  defense(): number { return 1 - this.offense; }
  afterWhistle(): boolean { return this.phase === Phase.Dead || this.phase === Phase.Celebrate; }
  offensePlay(): OffPlay | null { return this.haveOffPlay ? this.currentOff : null; }
  defensePlay(): DefPlay | null { return this.haveDefPlay ? this.currentDef : null; }
  numOffensePages(): number { return 3; }
  carrierIndex(): number { return this.ball.state === BallState.Held ? this.ball.holder : NONE; }
  ballSpot(): Vec2 { return new Vec2(this.losX, this.ballY); }
  fieldGoalYards(): number { return Math.abs(this.offenseDir() * EndLineX - this.losX) / Yard + 7; }
  global(team: number, slot: number): number { return team * 7 + slot; }
  rand(): number { return this.random.fRand(); }
  randRange(a: number, b: number): number { return this.random.fRandRange(a, b); }
  chance(probability: number): boolean { return this.random.fRand() < probability; }

  // --- State ---
  whistleFocus: Vec2 = Vec2.Zero;
  readySeats = 0;                  // bitmask: joined seats that voted for the next play
  phase: Phase = Phase.GameOver;
  phaseTime = 0;
  playType: PlayType = PlayType.Kickoff;
  quarter = 1;
  clock = 120;
  quarterLength = 120;
  offense = 0;                     // team snapping / the team that will have the ball after a kick
  ballTeam = 0;                    // team in possession right now
  kickingTeam = 0;
  down = 1;
  losX = 0; firstDownX = 0; ballY = 0;
  liveTime = 0;
  cpuSkill = 0.5;
  playCount = 0; driveCount = 0;
  overtime = false;

  players: SimPlayer[] = Array.from({ length: NumPlayers }, () => new SimPlayer());
  ball = new Ball();
  teams: TeamState[] = [new TeamState(), new TeamState()];
  seats: Seat[] = Array.from({ length: MaxSeats }, () => new Seat());
  picks: Pick[] = [new Pick(), new Pick()];
  patChoice = 0;                   // 0 kick, 1 go for two
  selectTimer = 0;

  // Kick meter (field goals and extra points): swings -1..1; locked when the kicker commits.
  kickMeter = 0; kickAim = 0;
  kickMeterLive = false; kickLocked = false;
  kickSteer: Vec2 = Vec2.Zero;

  // Result of the last play, for banners.
  resultTitle = ''; resultDetail = '';
  resultTeam = NONE;
  playYards = 0;
  scoringTeam = NONE;
  scorer = NONE;

  events: SimEvent[] = [];

  // Counters for the balance test (simtest); they have no effect on play.
  tally: number[] = new Array(12).fill(0);

  // --- Private state ---
  random = new RandomStream();
  currentOff: OffPlay = makeOffPlay();
  currentDef: DefPlay = makeDefPlay();
  haveOffPlay = false; haveDefPlay = false;
  kickFromYard = 35;
  furyAtSnap: boolean[] = [false, false];
  snapDelay = 0;
  ballCrossedLine = false;         // run or completed pass: everyone converts to pursuit / lead blocking
  passThrown = false;
  changeOfPossession = false;      // interception or fumble recovery during this play
  kickTouched = false;
  kickPossessed = false;           // somebody has had hold of this kick
  returnEnteredField = false;
  firstDownMade = false;
  passSeat = NONE;                 // human who threw the current pass
  teamDrives: number[] = [0, 0];   // possessions so far, per team: rotates who calls plays and who plays quarterback
  clockExpired = false;
  twoMinuteCalled = false;
  openingKicker = 0;
  startLosX = 0;                   // line of scrimmage when the play began
  returnStartX = 0;
  hutTimer = 0;
  deadSpotX = 0; deadSpotY = 0;
  pendingScoreTeam = NONE;

  trail: Vec2[][] = Array.from({ length: NumPlayers }, () => Array.from({ length: FurySim.TrailLength }, () => Vec2.Zero));
  trailHead = 0;
  trailTimer = 0;
}

// Methods implemented in simFlow.ts / simPlay.ts / simAI.ts. Names are the C++ names in lowerCamelCase.
export interface FurySim {
  // ===== simFlow.ts (FurySim.cpp) =====
  // Setup
  startMatch(homeLeague: number, awayLeague: number, quarterSeconds: number, cpuSkill: number, seed: number): void;
  setSeat(index: number, active: boolean, team: number): void;
  // Step (the top-level per-frame entry point; dispatches by phase)
  step(dt: number, inputs: SeatInput[]): void;
  /** Test hook: jump straight to a field-goal try by newOffense from the given yard line (0..100 from its own goal). */
  debugFieldGoal(newOffense: number, yardsFromOwnGoal: number): void;
  // Queries
  yardsToGo(): number;
  goalToGo(): boolean;
  downText(): string;
  spotText(): string;
  clockText(): string;
  offenseChoice(page: number, cell: number): OffPlay | null;
  defenseChoice(cell: number): DefPlay | null;
  chooseSituationalKick(pick: Pick): boolean;
  captain(team: number): number;
  isPassIconLive(): boolean;
  isPasser(index: number): boolean;
  winner(): number;
  // Flow
  emit(type: Ev, team?: number, player?: number, other?: number, value?: number): void;
  enter(newPhase: Phase): void;
  beginKickoff(kicker: number, fromYard: number): void;
  beginScrimmage(newOffense: number, newLosX: number, newBallY: number, firstDown: boolean): void;
  beginPlaySelect(): void;
  stepPlaySelect(dt: number, inputs: SeatInput[]): void;
  stepPatSelect(dt: number, inputs: SeatInput[]): void;
  cpuPickOffense(pick: Pick): void;
  cpuPickDefense(pick: Pick): void;
  setupPlay(): void;
  setupKickoff(): void;
  placeUnits(offenseUnit: boolean[]): void;
  assignSeats(): void;
  stepLineup(dt: number): void;
  stepPreSnap(dt: number, inputs: SeatInput[]): void;
  snapBall(): void;
  beginAfterWhistle(newPhase: Phase, spot: Vec2): void;
  stepAfterWhistle(inputs: SeatInput[]): void;
  finishCelebration(): void;
  stepBreak(dt: number): void;
  endPlay(title: string, detail: string, team: number): void;
  resolveDown(spotX: number, spotY: number): void;
  score(team: number, points: number, playerIndex: number): void;
  nextAfterScore(): void;
  endQuarter(): void;
  addFury(team: number, amount: number): void;
  tickFuryAfterPlay(): void;
  toWorld(playSpaceYards: Vec2): Vec2;
  clampToField(point: Vec2, margin?: number): Vec2;

  // ===== simPlay.ts (FurySimPlay.cpp) =====
  stepLive(dt: number, inputs: SeatInput[]): void;
  /** C++ out-params OutWish/OutSpeed become the returned object. */
  stepHuman(player: SimPlayer, index: number, input: SeatInput, dt: number): { wish: Vec2; speed: number };
  movePlayers(dt: number, wish: Vec2[], speed: number[]): void;
  separate(): void;
  stepEngagements(dt: number): void;
  stepBall(dt: number): void;
  stepContacts(dt: number): void;
  stepRules(): void;
  setAct(player: SimPlayer, act: Act, variant: number, length: number, key: number, busy: boolean): void;
  actKey(index: number): void;
  startStrike(index: number, act: Act, aim: Vec2): void;
  startElbow(index: number, target: number): void;
  actEnd(index: number): void;
  finishCarrierDown(carrier: number, spotX: number, spotY: number, outOfBounds: boolean, tackler: number): void;
  finishLooseBallDown(spotX: number, spotY: number): void;
  knock(victim: number, by: number, fall: Fall, downSeconds: number, push: Vec2, lift: number): void;
  startThrow(passer: number, target: number): void;
  releaseThrow(passer: number): void;
  giveBall(to: number): void;
  resolveCatch(inReach: number[]): void;
  completeCatch(index: number): void;
  fieldKick(index: number): void;
  tackle(tackler: number, carrier: number, strength: number, dive: boolean): boolean;
  fumble(carrier: number, push: Vec2): void;
  engage(blocker: number, defender: number, shedSeconds: number): void;
  disengage(index: number): void;
  switchSeat(seatIndex: number, newPlayer: number): void;
  controlFollowsBall(newHolder: number): void;
  startKick(kicker: number): void;
  strikeKick(kicker: number): void;
  downBall(spotX: number, spotY: number, title: string, detail: string, team: number): void;
  maxSpeed(player: SimPlayer, turbo: boolean): number;
  nearestOpponent(index: number, maxDist: number, uprightOnly?: boolean): number;
  closestToBall(team: number, excludeHumans: boolean, exclude?: number): number;

  // ===== simAI.ts (FurySimAI.cpp) =====
  /** C++ out-params OutWish/OutSpeed become the returned object for all think* methods (optional incoming values = the C++ in/out). */
  thinkPlayer(player: SimPlayer, index: number, dt: number, inWish?: Vec2, inSpeed?: number): { wish: Vec2; speed: number };
  thinkPasser(player: SimPlayer, index: number, dt: number, inWish?: Vec2, inSpeed?: number): { wish: Vec2; speed: number };
  thinkCarrier(player: SimPlayer, index: number, dt: number, inWish?: Vec2, inSpeed?: number): { wish: Vec2; speed: number };
  thinkDefender(player: SimPlayer, index: number, dt: number, inWish?: Vec2, inSpeed?: number): { wish: Vec2; speed: number };
  thinkBlocker(player: SimPlayer, index: number, dt: number, inWish?: Vec2, inSpeed?: number): { wish: Vec2; speed: number };
  thinkReceiver(player: SimPlayer, index: number, dt: number, inWish?: Vec2, inSpeed?: number): { wish: Vec2; speed: number };
  thinkAfterWhistle(player: SimPlayer, index: number, dt: number, inWish?: Vec2, inSpeed?: number): { wish: Vec2; speed: number };
  /** C++ out-params OutCatchPoint/OutTime become fields of the returned object. */
  openness(receiver: number): { score: number; catchPoint: Vec2; time: number };
  pickBlockTarget(blocker: number, protect: Vec2): number;
  pursuitPoint(chaser: SimPlayer, runner: SimPlayer): Vec2;
  delayedPos(index: number, seconds: number): Vec2;
  pairBlockers(): void;
}
