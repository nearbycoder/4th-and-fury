/**
 * Plays are data (port of FuryPlaybook.cpp). Everything is in yards in "play space": X is downfield
 * from the ball (the offense attacks +X, so the defense lines up at positive X) and Y is toward the
 * offense's right. The simulation maps play space onto the field for whichever way the offense is heading.
 *
 * Offense slots: 0 QB, 1 C, 2 LG, 3 RG, 4 WR (split left), 5 WR (split right), 6 RB / slot.
 * Defense slots: 0 DE, 1 DT, 2 DE, 3 LB, 4 CB (on slot 4), 5 CB (on slot 5), 6 S.
 *
 * The lists and kicking plays are memoized and shared: treat them as read-only and clone
 * (cloneOffPlay / cloneDefPlay) before changing anything. flipOff / flipDef return new objects.
 */
import { cloneDefPlay, cloneOffPlay, DefPlay, Job, JobSpec, makeDefPlay, makeJob, makeOffPlay, OffPlay, PlayKind, Vec2 } from './core';

type Path = Vec2[];
const v = (x: number, y: number) => new Vec2(x, y);
const pts = (list: [number, number][]): Path => list.map(([x, y]) => v(x, y));

// --- Offensive building blocks -----------------------------------------------------------------
const QBSpot = v(-5, 0);
const CenterSpot = v(-0.4, 0), LeftGuardSpot = v(-0.5, -1.8), RightGuardSpot = v(-0.5, 1.8);
// Receivers split a little tighter than on a real field: it keeps the whole formation big on screen.
const WideLeft = v(-0.6, -13), WideRight = v(-0.6, 13);
const BackRight = v(-5, 2.4), BackLeft = v(-5, -2.4), SlotRight = v(-1, 7), SlotLeft = v(-1, -7);
// const TightRight = v(-0.5, 3.9);   // unused in the C++ as well

function passer(rollout: Path = []): JobSpec { return makeJob({ job: Job.Passer, path: rollout }); }
function passBlock(): JobSpec { return makeJob({ job: Job.PassBlock }); }
function runBlock(): JobSpec { return makeJob({ job: Job.RunBlock }); }
/** A route for a split receiver: Y is toward the middle of the field. */
function route(path: Path, delay = 0): JobSpec { return makeJob({ job: Job.Route, path, inward: true, delay }); }
/** A route in plain play space (Y toward the offense's right), for backs and slots. */
function backRoute(path: [number, number][], delay = 0): JobSpec {
  const spec = route(pts(path), delay);
  spec.inward = false;
  return spec;
}
function carry(path: [number, number][]): JobSpec { return makeJob({ job: Job.Carry, path: pts(path) }); }
function keeper(path: [number, number][]): JobSpec { return makeJob({ job: Job.Keeper, path: pts(path) }); }

// Common routes for split receivers (depth, toward the middle).
const Go = (): Path => pts([[45, 0]]);
const Slant = (): Path => pts([[2, 0], [10, 8], [24, 22]]);
const Curl = (): Path => pts([[13, 0], [11, 1.5]]);
const Hitch = (): Path => pts([[6, 0], [5, 1]]);
const Out = (): Path => pts([[12, 0], [12.5, -9]]);
const Post = (): Path => pts([[13, 0], [38, 13]]);
const Corner = (): Path => pts([[12, 0], [30, -9]]);
const Dig = (): Path => pts([[14, 0], [15, 16]]);
const Comeback = (): Path => pts([[16, 0], [12, -3]]);
const Drag = (depth: number): Path => pts([[depth - 1, 0], [depth, 30]]);
const DeepOver = (): Path => pts([[10, 0], [19, 30]]);

function offense(name: string, tagline: string, kind: PlayKind, backSpot: Vec2,
  qb: JobSpec, left: JobSpec, right: JobSpec, back: JobSpec, primary: number, drop = 3): OffPlay {
  const play = makeOffPlay();
  play.name = name;
  play.tagline = tagline;
  play.kind = kind;
  play.spot[0] = QBSpot; play.spot[1] = CenterSpot; play.spot[2] = LeftGuardSpot; play.spot[3] = RightGuardSpot;
  play.spot[4] = WideLeft; play.spot[5] = WideRight; play.spot[6] = backSpot;
  play.job[0] = qb;
  const run = kind === PlayKind.Run;
  play.job[1] = run ? runBlock() : passBlock();
  play.job[2] = run ? runBlock() : passBlock();
  play.job[3] = run ? runBlock() : passBlock();
  play.job[4] = left;
  play.job[5] = right;
  play.job[6] = back;
  play.primary = primary;
  play.drop = drop;
  return play;
}

// --- Defensive building blocks -----------------------------------------------------------------
const EndLeft = v(0.9, -2.6), Tackle = v(0.9, 0), EndRight = v(0.9, 2.6), Backer = v(4.5, 0), Deep = v(14, 0);

function rush(): JobSpec { return makeJob({ job: Job.Rush }); }
function blitz(delay: number): JobSpec { return makeJob({ job: Job.Blitz, delay }); }
function man(target: number, cushion: number, press = false): JobSpec { return makeJob({ job: Job.Man, target, cushion, press }); }
function zone(depth: number, lateral: number, radius: number): JobSpec { return makeJob({ job: Job.Zone, zone: v(depth, lateral), radius }); }
function spy(): JobSpec { return makeJob({ job: Job.Spy }); }

function defense(name: string, tagline: string, e1: JobSpec, t: JobSpec, e2: JobSpec,
  lb: JobSpec, cornerLeft: JobSpec, cornerRight: JobSpec, safety: JobSpec): DefPlay {
  const play = makeDefPlay();
  play.name = name;
  play.tagline = tagline;
  play.spot[0] = EndLeft; play.spot[1] = Tackle; play.spot[2] = EndRight; play.spot[3] = Backer;
  // Corners line up over their receivers; these are only fallbacks. Zone players start in their zone.
  play.spot[4] = v(5, -13); play.spot[5] = v(5, 13); play.spot[6] = Deep;
  play.job[0] = e1; play.job[1] = t; play.job[2] = e2;
  play.job[3] = lb; play.job[4] = cornerLeft; play.job[5] = cornerRight; play.job[6] = safety;
  for (let i = 3; i < 7; ++i) {
    if (play.job[i].job === Job.Zone) {
      play.spot[i] = play.job[i].zone;
    } else if (play.job[i].job === Job.Blitz) {
      // Blitzers creep toward the line so the rush actually gets home (and do not stack up).
      let lateral = play.spot[i].y * 0.45;
      if (Math.abs(lateral) < 0.5) {
        lateral = i === 3 ? -1.3 : 3.4;
      }
      play.spot[i] = v(Math.min(play.spot[i].x, 3), lateral);
    }
  }
  return play;
}

// --- The lists ---------------------------------------------------------------------------------

let offenseCache: OffPlay[] | null = null;
let defenseCache: DefPlay[] | null = null;
let puntCache: OffPlay | null = null;
let fieldGoalCache: OffPlay | null = null;
let kickBlockCache: DefPlay | null = null;

function buildOffense(): OffPlay[] {
  const P: OffPlay[] = [];

  // ---- Page 1: the passing game -------------------------------------------------------------
  P.push(offense('SKYLINE', 'Three go deep. Pick one.', PlayKind.Pass, BackRight,
    passer(), route(Go()), route(Go()), backRoute([[1, 6], [5, 9], [40, 9]]), 5, 4));
  P.push(offense('CROSSFIRE', 'Two crossers and a flat. Hit the gap.', PlayKind.Pass, BackLeft,
    passer(), route(Drag(5)), route(Dig()), backRoute([[1, -7], [2.5, -14]]), 4));
  P.push(offense('OUT RAGE', 'Sideline outs with a seam up the gut.', PlayKind.Pass, BackRight,
    passer(), route(Out()), route(Out()), backRoute([[8, -2.2], [38, -2.2]]), 5));
  P.push(offense('SLANT STORM', 'Quick slants. Get it out fast.', PlayKind.Pass, BackRight,
    passer(), route(Slant()), route(Slant()), backRoute([[-1, 6], [1, 12], [9, 14]]), 5, 1.5));
  P.push(offense('CURL UP', 'Sit down at the sticks.', PlayKind.Pass, BackRight,
    passer(), route(Curl()), route(Curl()), backRoute([[5, -2], [7, -2.4]]), 4));
  P.push(offense('POST MASTER', 'Post and corner split the safety.', PlayKind.Pass, BackRight,
    passer(), route(Post()), route(Corner()), backRoute([[2, -3], [4, -16]]), 4, 4));
  P.push(offense('FLOOD RIGHT', 'Three levels down one sideline.', PlayKind.Pass, SlotRight,
    passer(), route(DeepOver()), route(Go()), backRoute([[7, 0], [7.5, 9]]), 6));
  P.push(offense('DAGGER', 'Clear it out, then dig underneath.', PlayKind.Pass, SlotRight,
    passer(), route(Comeback()), route(Dig()), backRoute([[42, 1]]), 5, 4));
  P.push(offense('HAIL FURY', 'Everybody long. Pray.', PlayKind.Pass, SlotLeft,
    passer(), route(pts([[48, 3]])), route(pts([[48, 3]])), backRoute([[46, 4]]), 5, 5));

  // ---- Page 2: quick game, runs and tricks --------------------------------------------------
  P.push(offense('QUICK HITCH', 'Five yards, right now.', PlayKind.Pass, BackRight,
    passer(), route(Hitch()), route(Hitch()), backRoute([[0, 6], [2, 13]]), 4, 1.5));
  P.push(offense('MESH', 'Drags rub the defenders off.', PlayKind.Pass, BackRight,
    passer(), route(Drag(5)), route(Drag(4)), backRoute([[4, 4], [10, 6], [26, 15]]), 4));
  {
    const play = offense('SCREEN DOOR', 'Let them come. Then dump it off.', PlayKind.Pass, BackLeft,
      passer(), route(Go()), route(Go()), backRoute([[-0.5, -5], [-1.5, -9]], 0.5), 6, 5);
    play.screen = true;
    P.push(play);
  }
  P.push(offense('THUNDER DIVE', 'Hand it off and hit the hole.', PlayKind.Run, BackRight,
    passer(), runBlock(), runBlock(), carry([[0.7, -1.5], [5.5, -1.4], [16, -1.8]]), 6));
  P.push(offense('SWEEP', 'Toss it wide and turn the corner.', PlayKind.Run, BackLeft,
    passer(), runBlock(), runBlock(), carry([[0.2, 3.6], [0, 13], [5, 18], [30, 19]]), 6));
  P.push(offense('COUNTER PUNCH', 'Show right, cut back left.', PlayKind.Run, BackRight,
    passer(), runBlock(), runBlock(), carry([[0.6, -2.6], [5, -5], [16, -7]]), 6));
  P.push(offense('QB DRAW', 'Fake the drop. Take off.', PlayKind.Run, BackRight,
    keeper([[-1, 0.4], [1.5, 2.5], [8, 2.8], [22, 2]]), route(Go()), route(Go()), runBlock(), 0));
  P.push(offense('BOOTLEG', 'Roll right. Run it or throw it.', PlayKind.Pass, BackRight,
    passer(pts([[-2, 6], [-1, 11]])), route(DeepOver()), route(Comeback()), backRoute([[1, 6], [3, 13]]), 5, 0));
  {
    const play = offense('PLAY ACTION', 'Sell the run. Throw the bomb.', PlayKind.Pass, BackRight,
      passer(), route(Post()), route(Go()), backRoute([[0.7, -1.5], [4, -1.4]]), 4, 4);
    play.playAction = true;
    P.push(play);
  }
  return P;
}

function buildPunt(): OffPlay {
  const P = makeOffPlay();
  P.name = 'PUNT';
  P.tagline = 'Flip the field.';
  P.kind = PlayKind.Punt;
  P.spot[0] = v(-13, 0);
  P.spot[1] = CenterSpot; P.spot[2] = LeftGuardSpot; P.spot[3] = RightGuardSpot;
  P.spot[4] = v(-0.6, -9); P.spot[5] = v(-0.6, 9); P.spot[6] = v(-6, 2.5);
  P.job[0].job = Job.Punter;
  P.job[1] = passBlock(); P.job[2] = passBlock(); P.job[3] = passBlock();
  for (let i = 4; i < 6; ++i) { P.job[i].job = Job.Cover; }
  P.job[6] = passBlock();
  P.primary = 0;
  return P;
}

function buildFieldGoal(): OffPlay {
  const P = makeOffPlay();
  P.name = 'FIELD GOAL';
  P.tagline = 'Three points. Probably.';
  P.kind = PlayKind.FieldGoal;
  P.spot[0] = v(-9.5, -1.6);                    // kicker
  P.spot[1] = CenterSpot; P.spot[2] = LeftGuardSpot; P.spot[3] = RightGuardSpot;
  P.spot[4] = v(-0.6, -3.7); P.spot[5] = v(-0.6, 3.7);   // wings
  P.spot[6] = v(-7, 0.6);                       // holder
  P.job[0].job = Job.Kicker;
  for (let i = 1; i < 6; ++i) { P.job[i] = passBlock(); }
  P.job[6].job = Job.Holder;
  P.primary = 0;
  return P;
}

function buildDefense(): DefPlay[] {
  const P: DefPlay[] = [];
  P.push(defense('ALL-OUT FURY', 'Send the house.',
    rush(), rush(), rush(), blitz(0), man(4, 3), man(5, 3), blitz(0.25)));
  P.push(defense('PRESS MAN', 'Jam them at the line.',
    rush(), rush(), rush(), man(6, 3), man(4, 1.3, true), man(5, 1.3, true), zone(13, 0, 14)));
  P.push(defense('ZONE BLANKET', 'Three deep. Nothing over the top.',
    rush(), rush(), rush(), zone(6, 0, 9), zone(15, -13, 11), zone(15, 13, 11), zone(18, 0, 11)));
  P.push(defense('PICKET FENCE', 'Take away everything short.',
    rush(), rush(), rush(), zone(5, 0, 7), zone(5.5, -11, 7.5), zone(5.5, 11, 7.5), zone(13, 0, 13)));
  P.push(defense('BASE MAN', 'Everyone has a man. Safety roams.',
    rush(), rush(), rush(), man(6, 4), man(4, 5), man(5, 5), zone(15, 0, 14)));
  P.push(defense('CORNER FIRE', 'The corner comes off the edge.',
    rush(), rush(), rush(), man(6, 4), man(4, 5), blitz(0), man(5, 8)));
  P.push(defense('SPY GAME', 'Shadow the quarterback.',
    rush(), rush(), rush(), spy(), man(4, 5), man(5, 5), zone(13, 0, 14)));
  P.push(defense('DOUBLE TROUBLE', 'Two bodies on their left receiver.',
    rush(), rush(), rush(), man(6, 4), man(4, 2.5), man(5, 5), man(4, 10)));
  P.push(defense('PREVENT WALL', 'Rush two. Guard the end zone.',
    rush(), zone(4, 0, 6), rush(), zone(10, 0, 9), zone(20, -12, 12), zone(20, 12, 12), zone(27, 0, 14)));
  return P;
}

function buildKickBlock(): DefPlay {
  const P = defense('KICK BLOCK', '',
    rush(), rush(), rush(), rush(), makeJob(), makeJob(), makeJob());
  P.spot[3] = v(0.9, 4.6);
  P.spot[4] = v(3, -9); P.spot[5] = v(3, 9); P.spot[6] = v(42, 0);
  P.job[4].job = Job.ReturnBlock; P.job[5].job = Job.ReturnBlock;
  P.job[6].job = Job.Returner;
  return P;
}

/** Mirror image of an offensive play (left and right swapped). */
function flipOff(play: OffPlay): OffPlay {
  const out = cloneOffPlay(play);
  for (let i = 0; i < 7; ++i) {
    out.spot[i] = out.spot[i].withY(-out.spot[i].y);
    if (!out.job[i].inward) {
      out.job[i].path = out.job[i].path.map((point) => point.withY(-point.y));
    }
  }
  return out;
}

/** Mirror image of a defensive play (left and right swapped). */
function flipDef(play: DefPlay): DefPlay {
  const out = cloneDefPlay(play);
  for (let i = 0; i < 7; ++i) {
    out.spot[i] = out.spot[i].withY(-out.spot[i].y);
    out.job[i].zone = out.job[i].zone.withY(-out.job[i].zone.y);
    // Man assignments on the split receivers swap sides with the picture.
    if (out.job[i].job === Job.Man && (out.job[i].target === 4 || out.job[i].target === 5)) {
      out.job[i].target = 9 - out.job[i].target;
    }
  }
  return out;
}

export const Playbook = {
  offense(): OffPlay[] { return (offenseCache ??= buildOffense()); },
  defense(): DefPlay[] { return (defenseCache ??= buildDefense()); },
  punt(): OffPlay { return (puntCache ??= buildPunt()); },
  fieldGoal(): OffPlay { return (fieldGoalCache ??= buildFieldGoal()); },
  /** What a defense lines up in against a punt or field goal. */
  kickBlock(): DefPlay { return (kickBlockCache ??= buildKickBlock()); },
  flipOff,
  flipDef,
};
