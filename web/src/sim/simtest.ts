/**
 * Headless balance test (port of FuryTest.cpp's RunSimTest).
 *
 * Plays whole computer-vs-computer matches as fast as the machine allows and logs what happened:
 * scores, play outcomes, event counts, and any game that hung. Bots > 0 seats that many scripted
 * "humans" (alternating sides), which exercises the same control paths a person with a controller
 * uses.
 *
 *   npx tsx src/sim/simtest.ts [games=10] [skill=0.5] [bots=0] [verbose=0]
 */
import { FurySim } from './index';
import { FuryBot } from './bot';
import { leagueTeams } from './teams';
import { Ev, makeSeatInput, MaxSeats, Phase, PlayType, RandomStream, SeatInput, Yard } from './core';

// --- printf-style helpers -----------------------------------------------------------------------
const f = (v: number, decimals: number, width = 0) => v.toFixed(decimals).padStart(width);
const d = (v: number, width = 0) => String(Math.trunc(v)).padStart(width);
const sl = (s: string, width: number) => s.padEnd(width);
const log = (line: string) => console.log(`SIMTEST ${line}`);
const eventName = (type: Ev) => Ev[type] ?? '?';

interface PlayStats {
  calls: number; throws: number; catches: number; picks: number; sacks: number; scores: number; fumbles: number;
  yards: number; airYards: number; catchYards: number; throwTime: number;
}
const newStats = (): PlayStats => ({ calls: 0, throws: 0, catches: 0, picks: 0, sacks: 0, scores: 0, fumbles: 0, yards: 0, airYards: 0, catchYards: 0, throwTime: 0 });
function findOrAdd<V>(map: Map<string, V>, key: string, make: () => V): V {
  let v = map.get(key);
  if (v === undefined) { v = make(); map.set(key, v); }
  return v;
}

export function runSimTest(games: number, skill: number, bots: number, verbose: boolean): void {
  const dt = 1 / 60;
  const numEvents = Ev.TwoMinute + 1;
  const totals: number[] = new Array(numEvents).fill(0);
  let points = 0, plays = 0, attempts = 0, completions = 0, passYards = 0, rushYards = 0, stuck = 0, overtimes = 0, ties = 0;
  let simSeconds = 0, longestPlay = 0;
  let highScore = 0, lowScore = 999;
  const titles = new Map<string, number>();
  const inputs: SeatInput[] = Array.from({ length: MaxSeats }, () => makeSeatInput());

  // Per-play breakdown for plays from scrimmage.
  const byPlay = new Map<string, PlayStats>(), byDefense = new Map<string, PlayStats>();
  let kickReturns = 0, kickReturnScores = 0;
  const tally: number[] = new Array(12).fill(0);
  let kickReturnYards = 0;
  const numBots = Math.min(bots, MaxSeats);

  for (let game = 0; game < games; ++game) {
    const sim = new FurySim();
    const pick = new RandomStream(1000 + game);
    const numTeams = leagueTeams().length;
    const home = pick.randRange(0, numTeams - 1);
    const away = (home + 1 + pick.randRange(0, numTeams - 2)) % numTeams;
    const bot: FuryBot[] = Array.from({ length: MaxSeats }, () => new FuryBot());
    for (let i = 0; i < numBots; ++i) {
      sim.setSeat(i, true, i % 2);
      bot[i].reset(i, 500 + game);
    }
    sim.startMatch(home, away, 120, skill, 77 + game * 13);

    let steps = 0, afterWhistleSteps = 0;
    let playStart = 0;
    let playName = '', defenseName = '';
    let scrimmagePlay = false, returnPlay = false, counted = false;
    let kickCatchX = 0;
    let lastPhase = sim.phase;
    let aborted = false;
    while (sim.phase !== Phase.GameOver) {
      for (let i = 0; i < numBots; ++i) {
        inputs[i] = bot[i].think(sim, dt);
      }
      if (sim.afterWhistle()) { ++afterWhistleSteps; }
      sim.step(dt, inputs);
      ++steps;
      for (const event of sim.events) {
        ++totals[event.type];
        if (event.type === Ev.Snap) {
          scrimmagePlay = sim.playType === PlayType.Scrimmage && sim.offensePlay() !== null;
          counted = false;
          if (scrimmagePlay) {
            playName = sim.offensePlay()!.name;
            defenseName = sim.defensePlay()!.name;
            ++findOrAdd(byPlay, playName, newStats).calls;
            ++findOrAdd(byDefense, defenseName, newStats).calls;
          }
        }
        if (event.type === Ev.Kickoff) { returnPlay = true; scrimmagePlay = false; kickCatchX = 0; }
        if (returnPlay && event.type === Ev.Catch) { kickCatchX = event.pos.x; }
        if (returnPlay && (event.type === Ev.Whistle || event.type === Ev.Touchdown)) {
          ++kickReturns;
          kickReturnYards += Math.abs(sim.ball.pos.x - kickCatchX) / Yard;
          kickReturnScores += event.type === Ev.Touchdown ? 1 : 0;
          returnPlay = false;
        }
        if (scrimmagePlay) {
          const touchdown = event.type === Ev.Touchdown && event.team === sim.offense;
          for (const stats of [findOrAdd(byPlay, playName, newStats), findOrAdd(byDefense, defenseName, newStats)]) {
            switch (event.type) {
              case Ev.Throw: ++stats.throws; stats.airYards += event.value; stats.throwTime += sim.liveTime; break;
              case Ev.Catch: ++stats.catches; stats.catchYards += event.value; break;
              case Ev.Intercept: ++stats.picks; break;
              case Ev.Sack: ++stats.sacks; break;
              case Ev.Fumble: ++stats.fumbles; break;
              case Ev.Touchdown: if (touchdown && !counted) { ++stats.scores; stats.yards += event.value; } break;
              case Ev.Whistle: if (!counted) { stats.yards += sim.ballTeam === sim.offense ? sim.playYards : 0; } break;
              default: break;
            }
          }
          counted ||= touchdown || event.type === Ev.Whistle;
        }
        if (verbose && game === 0) {
          log(`  ${f(steps * dt, 1, 6)}s Q${sim.quarter} ${sim.clockText()}  ${sl(eventName(event.type), 16)} team=${event.team} player=${event.player} value=${f(event.value, 1)} | ${sim.downText()} ${sim.spotText()}`);
        }
      }
      sim.events.length = 0;
      if (sim.phase !== lastPhase) {
        if (sim.phase === Phase.Live) { playStart = steps * dt; }
        if (lastPhase === Phase.Live) {
          longestPlay = Math.max(longestPlay, steps * dt - playStart);
          const title = sim.resultTitle === '' ? '(plain)' : sim.resultTitle;
          titles.set(title, (titles.get(title) ?? 0) + 1);
        }
        lastPhase = sim.phase;
      }

      // Sanity: nothing may go missing or hang.
      const pos = sim.ball.pos;
      let bad = !Number.isFinite(pos.x) || !Number.isFinite(pos.y) || !Number.isFinite(pos.z) || sim.phaseTime > 90 || steps - afterWhistleSteps > 60 * 60 * 40;
      for (const p of sim.players) {
        bad ||= !Number.isFinite(p.p.x) || !Number.isFinite(p.p.y) || !Number.isFinite(p.yaw);
      }
      if (bad) {
        console.error(`SIMTEST game ${game} ABORTED: phase=${sim.phase} phaseTime=${f(sim.phaseTime, 1)} playType=${sim.playType} ball=${sim.ball.state} steps=${steps} ${sim.downText()} ${sim.spotText()}`);
        ++stuck;
        aborted = true;
        break;
      }
    }
    if (aborted) {
      continue;
    }
    for (let i = 0; i < 12; ++i) { tally[i] += sim.tally[i]; }
    const a = sim.teams[0].score, b = sim.teams[1].score;
    points += a + b;
    highScore = Math.max(highScore, a, b);
    lowScore = Math.min(lowScore, a, b);
    plays += sim.playCount;
    simSeconds += steps * dt;
    overtimes += sim.overtime ? 1 : 0;
    ties += a === b ? 1 : 0;
    for (let team = 0; team < 2; ++team) {
      attempts += sim.teams[team].attempts;
      completions += sim.teams[team].completions;
      passYards += sim.teams[team].passYards;
      rushYards += sim.teams[team].rushYards;
    }
    if (verbose || game < 12) {
      log(`game ${d(game, 2)}: ${sim.teamInfo(0).name} ${a} - ${b} ${sim.teamInfo(1).name}${sim.overtime ? ' (OT)' : ''}  plays=${sim.playCount}  simtime=${f(steps * dt, 0)}s`);
    }
  }

  const g = Math.max(1, games - stuck);
  log(`===== ${games} games (skill ${f(skill, 2)}, ${bots} scripted humans), ${stuck} aborted =====`);
  log(`points/team/game ${f(points / (2 * g), 1)}  (low ${lowScore}, high ${highScore})  plays/game ${f(plays / g, 1)}  minutes/game ${f(simSeconds / g / 60, 1)}  longest play ${f(longestPlay, 1)}s  overtime ${overtimes}  ties ${ties}`);
  log(`passing ${completions}/${attempts} (${f(attempts > 0 ? (100 * completions) / attempts : 0, 0)}%)  ${f(attempts > 0 ? passYards / attempts : 0, 1)} yds/attempt  pass yds/team/game ${f(passYards / (2 * g), 0)}  rush yds/team/game ${f(rushYards / (2 * g), 0)}`);
  for (let i = 0; i < numEvents; ++i) {
    if (totals[i] > 0) {
      log(`  ${sl(eventName(i), 16)} ${d(totals[i], 7)}  (${f(totals[i] / g, 2)} per game)`);
    }
  }
  log(`catch contests: open ${tally[0]} | contested ${tally[1]} (picks ${tally[4]}) | defender alone at catch ${tally[2]} (picks ${tally[5]}) | defender in lane ${tally[3]} (picks ${tally[6]}) | on tipped balls ${tally[7]}`);
  log(`kick returns ${kickReturns}  avg ${f(kickReturns > 0 ? kickReturnYards / kickReturns : 0, 1)} yds  touchdowns ${kickReturnScores}`);
  for (let pass = 0; pass < 2; ++pass) {
    log(`  ${sl(pass === 0 ? 'OFFENSE' : 'DEFENSE', 16)} calls  yds/play  TD%   throw%  comp%  air   catchAt  throwT  pick%  sack%  fum%`);
    for (const [key, st] of pass === 0 ? byPlay : byDefense) {
      const c = Math.max(st.calls, 1), t = Math.max(st.throws, 1), k = Math.max(st.catches, 1);
      log(`  ${sl(key, 16)} ${d(st.calls, 5)}  ${f(st.yards / c, 1, 7)}  ${f((100 * st.scores) / c, 0, 4)}  ${f((100 * st.throws) / c, 0, 5)}  ${f((100 * st.catches) / t, 0, 5)}  ${f(st.airYards / t, 1, 5)}  ${f(st.catchYards / k, 1, 6)}  ${f(st.throwTime / t, 2, 6)}  ${f((100 * st.picks) / t, 1, 5)}  ${f((100 * st.sacks) / c, 1, 5)}  ${f((100 * st.fumbles) / c, 1, 4)}`);
    }
  }
  const sorted = [...titles].sort((x, y) => y[1] - x[1]);
  for (const [key, value] of sorted) {
    log(`  result ${sl(key, 18)} ${d(value, 6)}`);
  }
}

// CLI entry point: npx tsx src/sim/simtest.ts [games] [skill] [bots] [verbose]
const argv = typeof process !== 'undefined' ? process.argv.slice(2) : [];
const games = argv[0] !== undefined ? parseInt(argv[0], 10) : 10;
const skill = argv[1] !== undefined ? parseFloat(argv[1]) : 0.5;
const bots = argv[2] !== undefined ? parseInt(argv[2], 10) : 0;
const verbose = argv[3] !== undefined && argv[3] !== '0' && argv[3] !== 'false';
runSimTest(games, skill, bots, verbose);
