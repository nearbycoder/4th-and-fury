/**
 * The director runs the whole game: camera, athletes, stadium and the flow from title screen to
 * final whistle (port of AFuryDirector: FuryDirector.cpp, FuryDirectorMatch.cpp,
 * FuryDirectorOptions.cpp). The HUD reads its state to draw the interface.
 *
 * Field-space positions (sim, film, events) are Unreal centimetres: X goal to goal, Y sideline to
 * sideline (+Y is the broadcast camera side), Z up. The renderer maps them to three.js metres as
 * three = (X, Z, Y) / 100.
 *
 * Names follow the C++ in lowerCamelCase; bools lose the `b` prefix.
 */
import * as THREE from 'three';
import { FurySim } from '../sim/index';
import {
  Act, BallState, Dir, EndLineX, Ev, Grip, MaxSeats, MaxSeatsPerTeam, NONE, NumPlayers, OffenseSlot0, Phase, Pick, PlayType,
  RandomStream, SeatInput, SidelineY, Stance, TeamSize, Vec2, Vec3, Yard, YardLine, BuildFor, Pos, leagueTeams, kitFor, skinTones,
  makeSeatInput,
} from '../sim/index';
import { FuryBot } from '../sim/bot';
import { FuryAudio } from './audio';
import { FilmRecorder, type PlayFilm } from './film';
import { Button, FuryInput, PadKind, type Pad } from './input';
import { Option, Options } from './options';
import { AthleteState, type Look } from './athlete';
import type { World } from './world';
import { CM, hexColor, toThree, v3ToThree } from './space';

export enum Screen { Viewer, Title, Lobby, Teams, Match, Final }

/** An RGBA colour in linear 0..1 (FLinearColor). The HUD converts to CSS. */
export interface Color { r: number; g: number; b: number; a: number }
export const rgba = (r: number, g: number, b: number, a = 1): Color => ({ r, g, b, a });
const WhiteC = rgba(1, 1, 1);

/** A line of big type that slides in over the action. */
export class Banner {
  title = '';
  detail = '';
  color: Color = rgba(1, 1, 1);
  start = -100;      // real-time seconds (director.now())
  length = 2;
  big = false;
}

/** One of the eight places at the table. */
export class LobbySeat {
  joined = false;
  pad = NONE;        // index into FuryInput's pads
  side = NONE;       // -1 undecided, 0 home (left), 1 away (right)
  ready = false;
  bot = false;
}

export const QuarterOptions = [60, 90, 120, 180];
export const SkillOptions = [0.25, 0.5, 0.8];
const RosterSize = 15;
/** The football in a grip socket: long axis on the socket's Y, laces on its +Z (web/public/assets/README.md). */
const BallInSocket = new THREE.Quaternion(0.5, -0.5, -0.5, 0.5);

/** What the HUD needs to know about one athlete on the field (port of AFuryAthlete queries). */
export interface AthleteView {
  visible: boolean;
  /** Top of the helmet in field space (cm). */
  headWorld(): Vec3;
}

function colorOfHex(hex: string): Color {
  const c = hexColor(hex);
  return rgba(c.r, c.g, c.b);
}
const luminance = (c: Color) => 0.3 * c.r + 0.59 * c.g + 0.11 * c.b;
const smoothStep = (a: number, b: number, x: number) => { const t = Math.min(Math.max((x - a) / (b - a), 0), 1); return t * t * (3 - 2 * t); };

export class Director {
  // --- State the HUD draws from ---
  screen: Screen = Screen.Title;
  screenTime = 0;
  sim = new FurySim();
  film = new FilmRecorder();
  viewingFilm = false;
  filmRolling = false;
  filmTime = 0;
  seats: LobbySeat[] = Array.from({ length: MaxSeats }, () => new LobbySeat());
  teamPick: number[] = [0, 1];
  teamLocked: boolean[] = [false, false];
  optionRow: number[] = [0, 0];       // 0 team, 1 quarter length, 2 difficulty
  quarterChoice = 2;                  // index into QuarterOptions
  skillChoice = 1;                    // 0 rookie, 1 pro, 2 all-fury
  startCountdown = -1;
  paused = false;
  fieldGuide = false;
  pauseCursor = 0;
  confirmPauseAction = false;
  pauseSeat = NONE;
  options = new Options();
  settingsPad = NONE;
  /** The web build cannot quit, so this stays NONE; kept so HUD code ports 1:1. */
  quitPad = NONE;
  soundTab = false;
  settingsRow = 0;
  liveFPS = 0;
  renderPercent = 100;
  outputSize = { x: 0, y: 0 };
  demo = false;
  quickMatch = false;
  banner = new Banner();
  excitement = 0.2;                   // 0 murmur .. 1 bedlam
  audio = new FuryAudio();

  // --- Private ---
  private world: World | null = null;
  private bots: FuryBot[] = Array.from({ length: MaxSeats }, () => new FuryBot());
  private sparkle = new RandomStream(31337);
  private squadLeague = [-1, -1];
  private dressedLeague = [-1, -1];
  private states: AthleteState[] = Array.from({ length: NumPlayers }, () => new AthleteState());
  private showcase: AthleteState[] = [new AthleteState(), new AthleteState()];
  private trailDistance = 0;
  private lastTrailPoint: Vec3 | null = null;
  private fireworkTimer = 0;
  private fireworksLeft = 0;
  private fireworkTeam = 0;
  private flashTimer = 0;
  private camEye = new THREE.Vector3(0, 4500, 2400);   // field space, cm
  private camLook = new THREE.Vector3(0, 0, 0);
  private camFov = 36;
  private shake = 0;
  private orbit = 0;
  private hitStop = 0;
  private slowMo = 0;
  private timeScale = 1;
  private finalDelay = 0;
  private idleTime = 0;
  private heardPhase: Phase = Phase.GameOver;
  private heardPick: Pick[] = [new Pick(), new Pick()];
  private heardPat = 0;
  private heardSecond = 0;
  private heardMeter = 0;
  private heardMeterStep = 0;
  private saidWinner = false;
  private ballSpin = new THREE.Euler();
  private lastDrawnBall: BallState = BallState.Dead;
  private releaseOffset = new THREE.Vector3();
  private catchOffset = new THREE.Vector3();
  private catchBlend = 0;
  private meterStart = 0;
  private meterLast = 0;
  private meterFrames = 0;

  /** Real time in seconds (AFuryHUD::Now / GetRealTimeSeconds). */
  now(): number { return performance.now() / 1000; }

  selectedFilm(): PlayFilm {
    return this.screen === Screen.Final && this.film.longestTouchdown.ready() ? this.film.longestTouchdown : this.film.last;
  }
  isViewer(): boolean { return this.screen === Screen.Viewer; }

  static seatColor(seat: number): Color {
    const c = [
      rgba(1, 0.16, 0.14), rgba(0.12, 0.5, 1), rgba(1, 0.82, 0.08), rgba(0.2, 0.9, 0.3),
      rgba(1, 0.45, 0.05), rgba(0.72, 0.3, 1), rgba(0.1, 0.9, 0.9), rgba(1, 0.4, 0.75),
    ];
    return c[Math.min(Math.max(seat, 0), MaxSeats - 1)];
  }
  static skillName(choice: number): string { return ['ROOKIE', 'PRO', 'ALL-FURY'][Math.min(Math.max(choice, 0), 2)]; }
  quarterSeconds(): number { return QuarterOptions[Math.min(Math.max(this.quarterChoice, 0), 3)]; }
  skill(): number { return SkillOptions[Math.min(Math.max(this.skillChoice, 0), 2)]; }

  seatPad(seat: number): Pad | null {
    if (seat < 0 || seat >= MaxSeats) return null;
    const s = this.seats[seat];
    return s.joined && s.pad !== NONE ? FuryInput.get().pad(s.pad) : null;
  }
  numJoined(): number { return this.seats.filter((s) => s.joined).length; }
  numOnSide(side: number): number { return this.seats.filter((s) => s.joined && s.side === side).length; }
  picker(side: number): number {
    // The first human on a side picks its team; a computer side is picked by the first human at the table.
    for (let i = 0; i < MaxSeats; ++i) if (this.seats[i].joined && this.seats[i].side === side && !this.seats[i].bot) return i;
    for (let i = 0; i < MaxSeats; ++i) if (this.seats[i].joined && !this.seats[i].bot) return i;
    return NONE;
  }

  /** UI image by its Unreal texture name ("T_Title", "T_Icon_Flame", "T_Logo_amps"); null until loaded. */
  uiTexture(name: string): HTMLImageElement | null { return this.world?.uiImage(name) ?? null; }
  teamLogo(league: number): HTMLImageElement | null {
    const all = leagueTeams();
    return league >= 0 && league < all.length ? this.uiTexture('T_Logo_' + all[league].id) : null;
  }
  /** The athlete drawn for sim player index i (0..13), or null. */
  athlete(index: number): AthleteView | null {
    if (!this.world || index < 0 || index >= NumPlayers) return null;
    return this.world.athletes[this.memberOf(index)];
  }
  /** Projects a field-space point (cm) to CSS pixels in the game canvas, or null if behind the camera. */
  worldToScreen(world: Vec3): Vec2 | null { return this.world?.project(world) ?? null; }

  private memberOf(index: number): number {
    const p = this.sim.players[index];
    return p.team * RosterSize + Math.min(Math.max(p.roster, 0), RosterSize - 1);
  }

  private showBanner(title: string, detail: string, color: Color, length: number, big: boolean): void {
    const b = this.banner;
    b.title = title; b.detail = detail; b.color = color; b.start = this.now(); b.length = length; b.big = big;
  }

  // ---------------------------------------------------------------------------------------------
  // Startup
  // ---------------------------------------------------------------------------------------------

  async init(world: World): Promise<void> {
    this.world = world;
    this.options.load();
    await this.audio.init(this.options);
    this.applyGraphics();
    const params = new URLSearchParams(location.search);
    const league = leagueTeams();
    const home = params.get('home'), away = params.get('away');
    if (home) this.teamPick[0] = Math.max(0, league.findIndex((t) => t.id === home));
    if (away) this.teamPick[1] = Math.max(0, league.findIndex((t) => t.id === away));
    world.stadium.dress(league[this.teamPick[0]], league[this.teamPick[1]]);
    const speed = Number(params.get('speed'));
    if (speed > 0) this.timeScale = speed;
    if (params.has('match')) {
      // Test shortcut: a seated keyboard player on the home side.
      this.seats[0] = Object.assign(new LobbySeat(), { joined: true, ready: true, side: 0, pad: FuryInput.KeyboardA });
      this.startMatch();
    } else if (params.has('demo')) {
      this.demo = true;
      this.startMatch();
    } else this.goTo(Screen.Title);
  }

  // ---------------------------------------------------------------------------------------------
  // Frame
  // ---------------------------------------------------------------------------------------------

  tick(deltaTime: number): void {
    FuryInput.get().tick(deltaTime);
    this.screenTime += deltaTime;
    this.updateFrameMeter();
    if (this.settingsPad !== NONE) {
      if (this.paused) this.banner.start += deltaTime;
      else if (this.screen !== Screen.Match) this.tickBackdrop(deltaTime, 5200, 2300, 0.07);
      this.tickSettings();
    } else {
      switch (this.screen) {
        case Screen.Title: this.tickTitle(deltaTime); break;
        case Screen.Lobby: this.tickLobby(deltaTime); break;
        case Screen.Teams: this.tickTeams(deltaTime); break;
        case Screen.Match: this.tickMatch(deltaTime); break;
        case Screen.Final: this.tickFinal(deltaTime); break;
        default: break;
      }
    }
    this.audio.tick(deltaTime, this.paused ? 0 : this.excitement);
    if (!this.paused) this.world?.fx.tick(deltaTime);
    this.world?.setCamera(this.camEye, this.camLook, this.camFov);
  }

  private updateFrameMeter(): void {
    const now = performance.now() / 1000;
    if (this.meterLast === 0 || now - this.meterLast > 1) {
      this.meterStart = now; this.meterFrames = 0; this.liveFPS = 0;
    } else {
      ++this.meterFrames;
      const elapsed = now - this.meterStart;
      if (elapsed >= 0.5) { this.liveFPS = this.meterFrames / elapsed; this.meterStart = now; this.meterFrames = 0; }
    }
    this.meterLast = now;
  }

  private setCamera(eye: THREE.Vector3, target: THREE.Vector3, fov: number): void {
    this.camEye.copy(eye);
    this.camLook.copy(target);
    this.camFov = fov;
  }

  private goTo(newScreen: Screen): void {
    this.screen = newScreen;
    this.viewingFilm = false;
    if (newScreen !== Screen.Final) this.quickMatch = false;
    this.screenTime = 0;
    this.idleTime = 0;
    this.paused = false;
    this.startCountdown = -1;
    if (newScreen === Screen.Title) {
      this.demo = false;
      for (let i = 0; i < MaxSeats; ++i) if (!this.seats[i].bot) this.seats[i] = new LobbySeat();
    }
    if (newScreen === Screen.Lobby) for (const s of this.seats) s.ready = s.bot;
    if (newScreen === Screen.Teams) {
      this.teamLocked[0] = this.teamLocked[1] = false;
      this.optionRow[0] = this.optionRow[1] = 0;
    }
    // Menus get the theme; the match gets the crowd.
    const menu = newScreen === Screen.Title || newScreen === Screen.Lobby || newScreen === Screen.Teams || newScreen === Screen.Final;
    this.audio.music(menu ? 'MUS_Menu' : '', newScreen === Screen.Final ? 0.4 : 0.6);
    this.audio.setCrowd(true);
    this.audio.fadeFieldLoops();
    if (newScreen === Screen.Title) this.audio.say('VO_Title', true);
    const w = this.world;
    if (!w) return;
    w.fx.clear();
    w.showShadows(newScreen === Screen.Match);
    if (newScreen !== Screen.Match) {
      w.stadium.setChains(0, 0, 0, 0, false);
      for (const a of w.athletes) a.visible = false;
      w.ball.visible = false;
      w.tee.visible = false;
      w.catchMarker.visible = false;
      for (const m of w.markers) m.visible = false;
      w.scrimmageLine.visible = false;
      w.firstDownLine.visible = false;
    }
    this.showcaseAthletes(newScreen === Screen.Teams);
  }

  // ---------------------------------------------------------------------------------------------
  // Front end
  // ---------------------------------------------------------------------------------------------

  private tickBackdrop(dt: number, radius: number, height: number, speed: number): void {
    // A slow sweep around the bowl behind the menus.
    if (!this.options.get(Option.ReducedMotion)) this.orbit += dt * speed;
    const eye = new THREE.Vector3(Math.cos(this.orbit) * radius, Math.sin(this.orbit) * radius * 0.55 + 600, height + Math.sin(this.orbit * 0.7) * 250);
    this.setCamera(eye, new THREE.Vector3(0, -400, 500), 48);
    this.excitement = approach(this.excitement, 0.25, dt * 0.3);
    this.world?.stadium.setExcitement(this.excitement);
  }

  private tryJoinFromTitle(): boolean {
    const input = FuryInput.get();
    for (let i = 0; i < FuryInput.MaxPads; ++i) {
      const pad = input.pad(i);
      if (pad.kind === PadKind.Bot || !pad.connected) continue;
      if (pad.wasPressed(Button.X)) {
        this.demo = false;
        this.quickMatch = true;
        for (let s = 0; s < MaxSeats; ++s) this.seats[s] = new LobbySeat();
        Object.assign(this.seats[0], { joined: true, ready: true, side: 0, pad: i });
        this.audio.play('SFX_UIJoin');
        this.startMatch();
        return true;
      }
      if (pad.wasPressed(Button.Y)) {
        if (this.demo) this.goTo(Screen.Title);
        this.openSettings(i);
        return true;
      }
      if (pad.wasPressed(Button.A) || pad.wasPressed(Button.Start)) {
        // Whoever starts the game takes the first seat.
        this.demo = false;
        this.goTo(Screen.Lobby);
        for (const seat of this.seats) {
          if (!seat.joined) { seat.joined = true; seat.pad = i; break; }
        }
        this.audio.play('SFX_UIJoin');
        return true;
      }
    }
    return false;
  }

  private tickTitle(dt: number): void {
    this.tickBackdrop(dt, 5200, 2300, 0.07);
    if (this.tryJoinFromTitle()) return;
    // Left alone, the game plays itself.
    this.idleTime += dt;
    if (this.idleTime > 22) {
      this.demo = true;
      const random = new RandomStream(Math.floor(Math.random() * 0xffff));
      const count = leagueTeams().length;
      this.teamPick[0] = random.randRange(0, count - 1);
      this.teamPick[1] = (this.teamPick[0] + 1 + random.randRange(0, count - 2)) % count;
      this.startMatch();
    }
  }

  private tickLobby(dt: number): void {
    this.tickBackdrop(dt, 4300, 1700, 0.05);
    const input = FuryInput.get();

    // Anyone not yet at the table joins with A.
    for (let i = 0; i < FuryInput.MaxPads; ++i) {
      const pad = input.pad(i);
      if (pad.kind === PadKind.Bot || pad.kind === PadKind.None || !pad.connected || !pad.wasPressed(Button.A)) continue;
      if (this.seats.some((s) => s.joined && s.pad === i)) continue;
      const free = this.seats.findIndex((s) => !s.joined);
      if (free >= 0) {
        // Joining swallows this press so it does not also ready the player up.
        this.seats[free] = Object.assign(new LobbySeat(), { joined: true, pad: i, side: NONE });
        this.startCountdown = -1;
        this.audio.play('SFX_UIJoin');
      }
    }

    let allReady = this.numJoined() > 0;
    for (let i = 0; i < MaxSeats; ++i) {
      const seat = this.seats[i];
      if (!seat.joined || seat.bot) continue;
      const pad = input.pad(seat.pad);
      if (!pad.connected) {
        this.seats[i] = new LobbySeat();
        this.startCountdown = -1;
        allReady = false;
        continue;
      }
      if (!seat.ready && pad.navX !== 0) {
        // Step left toward the home side, right toward the away side.
        const wanted = Math.min(Math.max((seat.side === NONE ? 0 : seat.side === 0 ? -1 : 1) + pad.navX, -1), 1);
        const side = wanted < 0 ? 0 : wanted > 0 ? 1 : NONE;
        if (side === NONE || side === seat.side || this.numOnSide(side) < MaxSeatsPerTeam) {
          if (side !== seat.side) this.audio.play('SFX_UIMove');
          seat.side = side;
        } else this.audio.play('SFX_UIError');
      }
      if (pad.wasPressed(Button.A) && seat.side !== NONE && this.screenTime > 0.25 && !seat.ready) {
        seat.ready = true;
        this.audio.play('SFX_UIReady');
      }
      if (pad.wasPressed(Button.B)) {
        this.audio.play('SFX_UIBack');
        if (seat.ready) seat.ready = false;
        else {
          this.seats[i] = new LobbySeat();
          if (this.numJoined() === 0) { this.goTo(Screen.Title); return; }
        }
        this.startCountdown = -1;
      }
      allReady &&= this.seats[i].ready && this.seats[i].side !== NONE;
    }

    if (allReady) {
      if (this.tickCountdown(1.6, dt)) this.goTo(Screen.Teams);
    } else this.startCountdown = -1;
  }

  private tickCountdown(length: number, dt: number): boolean {
    // Counts down with a tick every beat; true on the frame it runs out.
    const beat = 0.6;
    if (this.startCountdown < 0) {
      this.startCountdown = length;
      this.audio.play('SFX_Countdown');
    }
    const before = this.startCountdown;
    this.startCountdown -= dt;
    if (this.startCountdown > 0 && Math.floor(before / beat) !== Math.floor(this.startCountdown / beat)) this.audio.play('SFX_Countdown');
    return this.startCountdown <= 0;
  }

  private showcaseAthletes(show: boolean): void {
    // Two athletes at midfield wearing the chosen kits, shown on the team-select screen.
    const w = this.world;
    if (!w) return;
    for (let side = 0; side < 2; ++side) {
      const athlete = w.athletes[side * RosterSize + OffenseSlot0];
      athlete.visible = show;
      if (show) {
        athlete.setLook(this.makeLook(side, OffenseSlot0));
        this.dressedLeague[side] = this.teamPick[side];
        this.squadLeague[side] = -1;     // the showcase look may differ from the dressed squad
      }
    }
  }

  private tickTeams(dt: number): void {
    const input = FuryInput.get();
    const count = leagueTeams().length;
    for (const s of this.seats) {
      if (s.joined && !s.bot && !input.pad(s.pad).connected) { this.goTo(Screen.Lobby); return; }
    }

    // Camera: close on the two athletes standing at midfield, facing us.
    if (!this.options.get(Option.ReducedMotion)) this.orbit += dt * 0.25;
    this.setCamera(new THREE.Vector3(Math.sin(this.orbit) * 45, 1010, 140), new THREE.Vector3(0, 0, 104), 30);
    const w = this.world;
    if (w) {
      for (let side = 0; side < 2; ++side) {
        const athlete = w.athletes[side * RosterSize + OffenseSlot0];
        if (this.dressedLeague[side] !== this.teamPick[side]) {
          athlete.setLook(this.makeLook(side, OffenseSlot0));
          this.dressedLeague[side] = this.teamPick[side];
          this.squadLeague[side] = -1;
        }
        const s = this.showcase[side];
        // Side by side in the gap between the two team cards, turned slightly toward each other.
        s.pos = new Vec2(side === 0 ? -50 : 50, 0);
        s.yaw = Math.PI / 2 + (side === 0 ? -0.3 : 0.3);
        s.vel = Vec2.Zero;
        s.act = this.teamLocked[side] ? Act.Celebrate : Act.Stand;
        s.variant = this.teamLocked[side] ? 2 : Stance.Idle;
        s.actTime = this.screenTime;
        s.actSerial = this.teamLocked[side] ? 1 : 0;
        s.actLength = 0;
        s.hasBall = false;
        athlete.advance(s, dt);
      }
      w.stadium.setExcitement(0.3);
    }

    const sharedPicker = this.picker(0) === this.picker(1);
    const sharedSide = this.teamLocked[0] ? 1 : 0;
    for (let side = 0; side < 2; ++side) {
      const seat = this.picker(side);
      if (seat === NONE) { this.teamLocked[side] = true; continue; }      // nobody at the table: bots or a demo
      // One human choosing for both sides picks the home side first.
      if (sharedPicker && side !== sharedSide) continue;
      const pad = input.pad(this.seats[seat].pad);
      if (this.teamLocked[side]) {
        if (pad.wasPressed(Button.B)) { this.teamLocked[side] = false; this.audio.play('SFX_UIBack'); }
        continue;
      }
      const rows = side === 0 ? 3 : 1;
      const newRow = Math.min(Math.max(this.optionRow[side] - pad.navY, 0), rows - 1);
      if (newRow !== this.optionRow[side] || pad.navX !== 0) this.audio.play('SFX_UIMove');
      this.optionRow[side] = newRow;
      if (pad.navX !== 0) {
        if (this.optionRow[side] === 0) {
          this.teamPick[side] = (this.teamPick[side] + pad.navX + count) % count;
          if (this.teamPick[side] === this.teamPick[1 - side]) this.teamPick[side] = (this.teamPick[side] + pad.navX + count) % count;      // no mirror matches
        } else if (this.optionRow[side] === 1) this.quarterChoice = Math.min(Math.max(this.quarterChoice + pad.navX, 0), 3);
        else this.skillChoice = Math.min(Math.max(this.skillChoice + pad.navX, 0), 2);
      }
      if (pad.wasPressed(Button.A) && this.screenTime > 0.3) {
        this.teamLocked[side] = true;
        this.audio.play('SFX_UISelect');
        this.audio.say('VO_Team_' + leagueTeams()[this.teamPick[side]].id, true);
      } else if (pad.wasPressed(Button.B)) {
        this.audio.play('SFX_UIBack');
        if (sharedPicker && side === 1) { this.teamLocked[0] = false; continue; }
        this.goTo(Screen.Lobby);
        return;
      }
    }

    if (this.teamLocked[0] && this.teamLocked[1]) {
      if (this.tickCountdown(1.8, dt)) {
        this.audio.play('SFX_CountdownGo');
        this.startMatch();
      }
    } else this.startCountdown = -1;
  }

  private tickFinal(dt: number): void {
    if (this.viewingFilm) {
      const pad = this.seatPad(this.pauseSeat);
      if (pad && pad.connected) this.tickFilm(pad, dt);
      else this.viewingFilm = false;
      return;
    }
    this.tickBackdrop(dt, 4600, 2000, 0.06);
    const input = FuryInput.get();
    for (let i = 0; i < MaxSeats; ++i) {
      const seat = this.seats[i];
      if (!seat.joined || seat.bot) continue;
      const pad = input.pad(seat.pad);
      if (this.screenTime > 1 && pad.wasPressed(Button.Y) && this.selectedFilm().ready()) { this.openFilm(i); return; }
      if (this.screenTime > 1 && pad.wasPressed(Button.A)) { this.startMatch(); return; }      // rematch, same sides and settings
      if (this.screenTime > 1 && (pad.wasPressed(Button.B) || pad.wasPressed(Button.Start))) { this.goTo(Screen.Teams); return; }
    }
    if (this.numJoined() === 0 && this.screenTime > 12) this.goTo(Screen.Title);
  }

  // ---------------------------------------------------------------------------------------------
  // Settings (FuryDirectorOptions.cpp)
  // ---------------------------------------------------------------------------------------------

  applyGraphics(): void {
    const density = [0.35, 0.65, 1, 1.5];
    if (this.world) {
      this.world.fx.particleDensity = density[this.options.get(Option.Effects)] ?? 1;
      this.world.applyOptions(this.options);
    }
  }

  private openSettings(pad: number): void {
    this.settingsPad = pad;
    this.soundTab = false;
    this.settingsRow = 0;
    this.idleTime = 0;
  }

  private tickSettings(): void {
    const pad = FuryInput.get().pad(this.settingsPad);
    if (!pad.connected || pad.wasPressed(Button.B) || pad.wasPressed(Button.Start) || pad.wasPressed(Button.Back)) {
      this.audio.stopPreview();
      this.settingsPad = NONE;
      this.audio.play('SFX_UIBack');
      return;
    }
    if (pad.wasPressed(Button.LB) || pad.wasPressed(Button.RB)) {
      this.soundTab = !this.soundTab;
      this.settingsRow = 0;
      this.audio.stopPreview();
      this.audio.play('SFX_UIPage');
      return;
    }
    const rows = Options.rows(this.soundTab);
    const newRow = Math.min(Math.max(this.settingsRow - pad.navY, 0), rows.length - 1);
    if (this.settingsRow !== newRow) this.audio.play('SFX_UIMove');
    this.settingsRow = newRow;
    const selected = rows[this.settingsRow];
    const isChannel = selected >= Option.Master && selected <= Option.Interface;
    if (pad.wasPressed(Button.X)) {
      this.options.reset(this.soundTab);
    } else if (isChannel && pad.wasPressed(Button.Y)) {
      this.options.toggleMute(selected);
    } else if (!pad.navX || !this.options.adjust(selected, pad.navX)) {
      if (isChannel && pad.wasPressed(Button.A)) this.audio.preview(selected);
      return;
    }
    if (this.soundTab) this.audio.updateMix(this.options);
    else this.applyGraphics();
    this.options.save();
    this.audio.play('SFX_UIMove');
  }

  // ---------------------------------------------------------------------------------------------
  // The match (FuryDirectorMatch.cpp)
  // ---------------------------------------------------------------------------------------------

  private makeLook(team: number, roster: number): Look {
    const info = leagueTeams()[this.teamPick[team]];
    const entry = info.roster[Math.min(Math.max(roster, 0), info.roster.length - 1)];
    const kit = kitFor(info, team === 0);
    let scale = 1;
    // Linemen stand a little taller and wider, skill players a little slighter.
    switch (entry.pos) {
      case Pos.OL: case Pos.DL: scale = 1.05; break;
      case Pos.WR: case Pos.CB: scale = 0.98; break;
      case Pos.K: scale = 0.95; break;
    }
    return {
      build: BuildFor(entry.pos),
      jersey: hexColor(kit.jersey), jerseyTrim: hexColor(kit.trim), numberFill: hexColor(kit.numberFill), numberEdge: hexColor(kit.numberEdge),
      pants: hexColor(kit.pants), pantsStripe: hexColor(kit.pantsStripe), helmet: hexColor(kit.helmet), helmetStripe: hexColor(kit.helmetStripe),
      facemask: hexColor(kit.facemask), socks: hexColor(kit.socks), shoes: hexColor(kit.shoes), gloves: hexColor(kit.gloves),
      skin: hexColor(skinTones()[entry.skinTone]),
      number: entry.number,
      visor: entry.visor,
      scale,
      logo: this.world?.logoTexture(info.id) ?? null,
    };
  }

  private dressTeams(): void {
    const league = leagueTeams();
    const w = this.world;
    if (!w) return;
    w.stadium.dress(league[this.teamPick[0]], league[this.teamPick[1]]);
    // Dress both rosters now, once, so nothing has to change while the game is being played.
    for (let side = 0; side < 2; ++side) {
      if (this.squadLeague[side] === this.teamPick[side]) continue;
      this.squadLeague[side] = this.teamPick[side];
      for (let roster = 0; roster < RosterSize; ++roster) w.athletes[side * RosterSize + roster].setLook(this.makeLook(side, roster));
    }
  }

  private startMatch(): void {
    this.screen = Screen.Match;
    this.film.reset();
    this.viewingFilm = false;
    this.screenTime = 0;
    this.paused = false;
    this.finalDelay = 0;
    this.hitStop = this.slowMo = this.shake = 0;

    const seed = Math.floor(Math.random() * 0x7fffffff);
    for (let i = 0; i < MaxSeats; ++i) {
      const plays = !this.demo && this.seats[i].joined && this.seats[i].side !== NONE;
      this.sim.setSeat(i, plays, Math.max(this.seats[i].side, 0));
      this.bots[i].reset(i, seed);
    }
    this.sim.startMatch(this.teamPick[0], this.teamPick[1], this.quickMatch ? 60 : this.quarterSeconds(), this.quickMatch ? 0.25 : this.skill(), seed);
    this.dressTeams();
    // The showcase athletes may still be in their team-select pose; everyone else hides until placed.
    const w = this.world;
    if (w) {
      w.ball.visible = true;
      w.showShadows(true);
    }
    this.updateAthletes(0);
    this.lastDrawnBall = BallState.Dead;
    this.catchBlend = 0;
    this.updateBall(0);
    this.updateCamera(0, true);
    const home = this.sim.teamInfo(0), away = this.sim.teamInfo(1);
    this.showBanner(`${home.name.toUpperCase()}  VS  ${away.name.toUpperCase()}`, 'KICKOFF', WhiteC, 3, false);
    w?.fx.clear();
    this.lastTrailPoint = null;
    this.trailDistance = 0;
    this.fireworksLeft = 0;
    this.audio.music('');
    this.audio.sayOneOf('VO_Welcome', 2, true);
    this.heardPhase = this.sim.phase;
    this.saidWinner = false;
  }

  private gatherInput(out: SeatInput[], dt: number): void {
    const input = FuryInput.get();
    for (let i = 0; i < MaxSeats; ++i) {
      out[i] = makeSeatInput();
      if (!this.sim.seats[i].active) continue;
      if (this.seats[i].bot || this.seats[i].pad === NONE || !input.pad(this.seats[i].pad).connected) {
        out[i] = this.bots[i].think(this.sim, dt * this.timeScale);
        continue;
      }
      const pad = input.pad(this.seats[i].pad);
      const o = out[i];
      o.stick = pad.stick;
      o.turbo = pad.turbo();
      o.A = pad.wasPressed(Button.A);
      o.B = pad.wasPressed(Button.B);
      o.X = pad.wasPressed(Button.X);
      o.Y = pad.wasPressed(Button.Y);
      o.LB = pad.wasPressed(Button.LB);
      o.RB = pad.wasPressed(Button.RB);
      o.navX = pad.navX;
      o.navY = pad.navY;
    }
  }

  private openFilm(seat: number): void {
    this.pauseSeat = seat;
    this.viewingFilm = true;
    this.filmRolling = true;
    this.filmTime = 0;
    this.audio.play('SFX_UIPage');
  }

  private tickFilm(pad: Pad, dt: number): void {
    if (pad.wasPressed(Button.B) || pad.wasPressed(Button.Y) || pad.wasPressed(Button.Start)) {
      this.viewingFilm = false;
      if (pad.wasPressed(Button.Start)) this.paused = false;
      this.audio.play('SFX_UIBack');
      return;
    }
    const end = this.selectedFilm().duration();
    if (pad.wasPressed(Button.A)) {
      if (this.filmTime >= end) this.filmTime = 0;
      this.filmRolling = !this.filmRolling;
    }
    if (pad.navX !== 0 || Math.abs(pad.stick.x) > 0.4) {
      this.filmRolling = false;
      this.filmTime += pad.navX * 0.2 + pad.stick.x * 2.8 * dt;
    } else if (this.filmRolling) this.filmTime += dt;
    this.filmTime = Math.min(Math.max(this.filmTime, 0), end);
    if (this.filmTime >= end) this.filmRolling = false;
  }

  private tickPause(dt: number): void {
    const pad = this.pauseSeat === NONE ? null : this.seatPad(this.pauseSeat);
    if (!pad || !pad.connected) {
      this.viewingFilm = false;
      this.confirmPauseAction = false;
      this.paused = false;
      return;
    }
    if (this.viewingFilm) { this.tickFilm(pad, dt); return; }
    if (this.fieldGuide && !pad.wasPressed(Button.Start)) {
      if (pad.wasPressed(Button.B) || pad.wasPressed(Button.X)) { this.fieldGuide = false; this.audio.play('SFX_UIBack'); }
      return;
    }
    if (!this.confirmPauseAction && pad.wasPressed(Button.X) && !pad.wasPressed(Button.Start)) {
      this.fieldGuide = true;
      this.audio.play('SFX_UIPage');
      return;
    }
    if (!this.confirmPauseAction && pad.wasPressed(Button.Y) && this.film.last.ready()) { this.openFilm(this.pauseSeat); return; }
    if (pad.wasPressed(Button.Start) || pad.wasPressed(Button.B)) {
      const back = this.confirmPauseAction && !pad.wasPressed(Button.Start);
      this.confirmPauseAction = false;
      this.paused = back;
      this.audio.play('SFX_UIBack');
      return;
    }
    if (!this.confirmPauseAction) {
      const next = Math.min(Math.max(this.pauseCursor - pad.navY, 0), 3);      // a browser game cannot quit
      if (next !== this.pauseCursor) this.audio.play('SFX_UIMove');
      this.pauseCursor = next;
    }
    if (pad.wasPressed(Button.A)) {
      this.audio.play('SFX_UISelect');
      if (this.pauseCursor === 0) this.paused = false;
      else if (this.pauseCursor === 1) this.openSettings(this.seats[this.pauseSeat].pad);
      else if (!this.confirmPauseAction) this.confirmPauseAction = true;
      else if (this.pauseCursor === 2) this.startMatch();
      else this.goTo(Screen.Title);
    }
  }

  private inputs: SeatInput[] = Array.from({ length: MaxSeats }, () => makeSeatInput());

  private tickMatch(deltaTime: number): void {
    const input = FuryInput.get();
    if (this.demo) {
      if (this.tryJoinFromTitle()) return;
    } else if (!this.paused) {
      for (let i = 0; i < MaxSeats; ++i) {
        if (this.seats[i].joined && !this.seats[i].bot && input.pad(this.seats[i].pad).wasPressed(Button.Start) && this.sim.phase !== Phase.GameOver) {
          this.paused = true;
          this.pauseSeat = i;
          this.fieldGuide = false;
          this.confirmPauseAction = false;
          this.audio.fadeFieldLoops();
          this.audio.play('SFX_UISelect');
          this.pauseCursor = 0;
          return;
        }
      }
    }
    if (this.paused) {
      this.banner.start += deltaTime;
      this.tickPause(deltaTime);
      return;
    }

    // Big hits freeze the frame for an instant, then play out in slow motion.
    let dt = Math.min(deltaTime, 0.05) * this.timeScale;
    if (this.hitStop > 0) { this.hitStop -= deltaTime; dt = 0; }
    else if (this.slowMo > 0) { this.slowMo -= deltaTime; dt *= 0.35; }

    const inputs = this.inputs;
    this.gatherInput(inputs, deltaTime);
    let remaining = dt;
    while (remaining > 1e-5) {
      const step = Math.min(remaining, 1 / 90);
      this.sim.step(step, inputs);
      if (!this.demo) this.film.record(this.sim);
      remaining -= step;
      // Button presses count once, however many steps the frame is split into.
      for (const s of inputs) { s.A = s.B = s.X = s.Y = s.LB = s.RB = false; s.navX = s.navY = 0; }
      this.handleEvents();
    }

    this.updateAthletes(dt);
    this.world?.updateShadows(this.visibleAthletes());
    this.updateBall(dt);
    this.updateMarkers();
    this.updateCamera(deltaTime, false);
    this.updateEffects(dt);
    this.tickMatchSounds(deltaTime);

    // The crowd settles between plays and stays loud while a team is in Fury.
    const sim = this.sim;
    let floor = sim.phase === Phase.Live ? 0.4 : 0.22;
    const runner = sim.carrierIndex();
    if (sim.phase === Phase.Live && runner !== NONE) {
      const p = sim.players[runner];
      const nearGoal = Math.min(Math.max((YardLine(p.team, p.p.x) - 70) / 30, 0), 1);
      floor += 0.45 * nearGoal;
    }
    if (sim.teams[0].inFury() || sim.teams[1].inFury()) floor = Math.max(floor, 0.7);
    this.excitement = Math.max(floor, this.excitement - deltaTime * 0.12);
    this.world?.stadium.setExcitement(this.excitement);

    if (sim.phase === Phase.GameOver) {
      this.finalDelay += deltaTime;
      if (this.finalDelay > 3.4 && !this.saidWinner) {
        this.saidWinner = true;
        if (sim.winner() !== NONE) this.audio.say(sim.winner() === 0 ? 'VO_Win_Home' : 'VO_Win_Away', true);
      }
      if (this.finalDelay > 7) this.goTo(this.demo ? Screen.Title : Screen.Final);
    }
  }

  private tickMatchSounds(_dt: number): void {
    // Sound that follows the state of play rather than single events.
    const sim = this.sim, audio = this.audio;
    const halftime = sim.phase === Phase.Break && sim.quarter === 3;
    const choosing = sim.phase === Phase.PlaySelect || sim.phase === Phase.PatSelect;
    audio.music(halftime ? 'MUS_Halftime' : choosing ? 'MUS_PlaySelect' : '', halftime ? 0.5 : 0.32);
    const live = sim.phase === Phase.Live;
    const ball = sim.ball;
    const airborne = ball.state === BallState.Pass || ball.state === BallState.Kick || ball.state === BallState.FieldGoal;
    const flight = Math.min(Math.max(ball.time / Math.max(ball.duration, 0.01), 0), 1);
    const appr = flight * flight;
    audio.setLoop('SFX_BallAir', airborne && live, 0.18 + 0.27 * appr, 0.94 + 0.28 * appr);
    audio.setLoop('SFX_FuryLoop', sim.teams[0].inFury() || sim.teams[1].inFury(), 0.45);

    // Cleats on turf under whoever has the ball.
    const carrier = sim.carrierIndex();
    const cp = carrier !== NONE ? sim.players[carrier] : null;
    const carrierSpeed = live && cp && cp.height < 5 && !cp.down ? cp.v.size() : 0;
    if (carrierSpeed > 260 && this.world && this.world.athletes[this.memberOf(carrier)].didStep()) {
      audio.playOneOf('SFX_Cleat', 6, Math.min(Math.max(carrierSpeed / 1800, 0.2), 0.6), 0.1);
    }

    // The crowd gets a chant going before the snaps that matter.
    const bigDown = sim.playType === PlayType.TwoPoint || (sim.playType === PlayType.Scrimmage && (sim.down >= 3 || sim.goalToGo()));
    audio.setLoop('AMB_Chant', bigDown && (sim.phase === Phase.Lineup || sim.phase === Phase.PreSnap), 0.42);

    // Play calling: the cursor ticks, the page turns, and the clock nags at the end.
    if (sim.phase !== this.heardPhase) {
      if (this.heardPhase === Phase.Break && sim.quarter === 3 && sim.phase !== Phase.GameOver) audio.say('VO_Quarter3', true);
      this.heardPhase = sim.phase;
      this.heardPick = [Object.assign(new Pick(), sim.picks[0]), Object.assign(new Pick(), sim.picks[1])];
      this.heardPat = sim.patChoice;
      this.heardSecond = Math.ceil(sim.selectTimer);
      this.heardMeter = sim.kickMeter;
      this.heardMeterStep = 0;
    }
    if (sim.phase === Phase.PlaySelect) {
      let waiting = false;
      for (let team = 0; team < 2; ++team) {
        const pick = sim.picks[team];
        if (sim.captain(team) === NONE) continue;
        waiting ||= !pick.locked;
        const heard = this.heardPick[team];
        if (pick.page !== heard.page) audio.play('SFX_UIPage');
        else if (pick.cursor !== heard.cursor) audio.play('SFX_UIMove', 0.7);
        else if (pick.flip !== heard.flip) audio.play('SFX_UIMove', 0.7, 1.3);
        this.heardPick[team] = Object.assign(new Pick(), pick);
      }
      const second = Math.ceil(sim.selectTimer);
      if (second !== this.heardSecond && second <= 3 && second >= 1 && waiting) audio.play('SFX_Countdown', 0.8);
      this.heardSecond = second;
    } else if (sim.phase === Phase.PatSelect && sim.patChoice !== this.heardPat) {
      this.heardPat = sim.patChoice;
      audio.play('SFX_UIMove', 0.7);
    }

    // The kick meter ticks through the sweet spot and knocks at each end.
    if (sim.kickMeterLive && !sim.kickLocked) {
      const step = sim.kickMeter - this.heardMeter;
      if ((sim.kickMeter > 0) !== (this.heardMeter > 0)) audio.play('SFX_MeterTick', 0.9, 1.25);
      else if (step * this.heardMeterStep < 0) audio.play('SFX_MeterTick', 0.6, 0.8);
      if (step !== 0) this.heardMeterStep = step;
    }
    this.heardMeter = sim.kickMeter;
  }

  private handleEvents(): void {
    const sim = this.sim, audio = this.audio, fx = this.world?.fx;
    const teamColor = (team: number) => (team === NONE ? WhiteC : colorOfHex(sim.teamInfo(team).primary));
    const teamName = (team: number) => (team === NONE ? '' : sim.teamInfo(team).name.toUpperCase());
    const grass = rgba(0.35, 0.5, 0.3);
    for (const ev of sim.events) {
      const at = { x: ev.pos.x, y: ev.pos.y, z: ev.other !== NONE && ev.pos.z > 0 ? ev.pos.z : 95 };
      const ground = (z: number) => ({ x: at.x, y: at.y, z });
      const up = (z: number) => ({ x: at.x, y: at.y, z: at.z + z });
      const flash = rgba(1, 0.93, 0.7);

      // What it sounds and looks like.
      switch (ev.type) {
        case Ev.Hut: audio.playOneOf('SFX_Hut', 3, 0.6); break;
        case Ev.Snap: audio.play('SFX_Snap', 0.8); break;
        case Ev.Throw: audio.playOneOf('SFX_Throw', 2, 0.8); break;
        case Ev.Catch:
          audio.playOneOf('SFX_Catch', 3, 0.9);
          fx?.burst(up(30), flash, 6, 180, 0.18, 26, 2, 200);
          if (ev.value >= 20) { audio.playOneOf('AMB_Cheer', 3, 0.7); audio.sayOneOf('VO_BigGain', 3); }
          break;
        case Ev.Drop: case Ev.Tip: audio.play('SFX_Drop', 0.8); break;
        case Ev.Incomplete: audio.play('SFX_Bounce', 0.6); audio.sayOneOf('VO_Incomplete', 3); break;
        case Ev.Intercept:
          audio.play('SFX_Turnover'); audio.playOneOf('AMB_Cheer', 3, 0.9); audio.sayOneOf('VO_Interception', 3, true);
          fx?.burst(up(60), rgba(0.5, 0.8, 1), 26, 420, 0.5, 34, 4);
          break;
        case Ev.Tackle:
          audio.playOneOf('SFX_Hit', 4, 0.55 + 0.45 * ev.value);
          if (this.sparkle.fRand() < 0.4) audio.playOneOf('SFX_Grunt', 4, 0.5);
          fx?.burst(at, flash, 8 + Math.round(10 * ev.value), 260 + 240 * ev.value, 0.3, 22, 2.2, 620);
          fx?.burst(ground(8), grass, 10, 200, 0.5, 16, 0.8, 700, 0.7);
          break;
        case Ev.BigHit:
          audio.playOneOf('SFX_BigHit', 3, 1); audio.playOneOf('AMB_Ooh', 2, 0.9);
          if (this.sparkle.fRand() < 0.45) audio.sayOneOf('VO_BigHit', 4);
          fx?.emit(at, { x: 0, y: 0, z: 0 }, WhiteC, 0.14, 260, 5, 0, 0, 1800);
          fx?.burst(at, rgba(1, 0.8, 0.35), 44, 760, 0.55, 30, 4.5, 700);
          fx?.burst(ground(8), grass, 22, 340, 0.7, 18, 0.9, 700, 0.7);
          break;
        case Ev.Sack: audio.play('SFX_Sack'); audio.playOneOf('AMB_Cheer', 3, 0.8); audio.sayOneOf('VO_Sack', 3, true); break;
        case Ev.Fumble:
          audio.play('SFX_Fumble'); audio.sayOneOf('VO_Fumble', 2, true);
          fx?.burst(at, rgba(1, 0.85, 0.1), 24, 420, 0.45, 28, 4);
          break;
        case Ev.Recover: audio.playOneOf('SFX_Catch', 3, 0.8); break;
        case Ev.BrokenTackle: audio.playOneOf('SFX_Hit', 4, 0.45); audio.playOneOf('SFX_Grunt', 4, 0.5); break;
        case Ev.StiffArm: case Ev.Shove: case Ev.Pancake:
          audio.play('SFX_StiffArm', 0.9);
          fx?.burst(at, flash, 12, 380, 0.28, 24, 2.6, 500);
          break;
        case Ev.Spin: audio.play('SFX_Spin', 0.7); break;
        case Ev.Juke: audio.play('SFX_Juke', 0.7); fx?.burst(ground(6), grass, 8, 220, 0.4, 14, 0.8, 600, 0.6); break;
        case Ev.Hurdle: audio.play('SFX_Spin', 0.6, 1.25); break;
        case Ev.Dive:
          audio.playOneOf('SFX_Dive', 2, 0.7);
          fx?.burst(ground(6), grass, 12, 260, 0.5, 16, 0.8, 600, 0.6);
          break;
        case Ev.LateHit: {
          const heavy = ev.value >= 0.85;
          if (heavy) audio.playOneOf('SFX_BigHit', 3, 0.85);
          else audio.playOneOf('SFX_Hit', 4, 0.75);
          audio.playOneOf('AMB_Ooh', 2, heavy ? 0.7 : 0.4);
          fx?.burst(at, heavy ? rgba(1, 0.72, 0.28) : flash, heavy ? 18 : 9, heavy ? 500 : 310, 0.23, 19, 2.4, 600);
          fx?.burst(ground(6), rgba(0.32, 0.46, 0.24), heavy ? 10 : 5, 220, 0.35, 14, 0.85, 660);
          this.shake = Math.max(this.shake, heavy ? 0.38 : 0.17);
          break;
        }
        case Ev.Touchdown:
          audio.play('SFX_Touchdown'); audio.play('SFX_Cannon', 0.8); audio.playOneOf('AMB_Cheer', 3, 1); audio.sayOneOf('VO_Touchdown', 4, true);
          this.fireworksLeft = 10;
          this.fireworkTimer = 0.2;
          this.fireworkTeam = ev.team;
          break;
        case Ev.FirstDown: audio.play('SFX_FirstDown', 0.8); audio.sayOneOf('VO_FirstDown', 3); break;
        case Ev.TurnoverOnDowns: audio.play('SFX_Turnover', 0.8); audio.say('VO_Turnover', true); break;
        case Ev.Safety: audio.play('SFX_Turnover'); audio.say('VO_Safety', true); break;
        case Ev.Whistle: audio.play('SFX_Whistle', 0.7); break;
        case Ev.Kickoff: audio.playOneOf('SFX_Kick', 2); audio.sayOneOf('VO_Kickoff', 2); fx?.burst(ground(8), grass, 14, 300, 0.5, 16, 0.8, 600, 0.6); break;
        case Ev.PuntKick: audio.playOneOf('SFX_Kick', 2); audio.say('VO_Punt'); break;
        case Ev.FieldGoalKick: audio.playOneOf('SFX_Kick', 2); break;
        case Ev.FieldGoalGood: audio.play('SFX_FieldGoalGood'); audio.playOneOf('AMB_Cheer', 3, 0.8); audio.say('VO_FieldGoalGood', true); break;
        case Ev.FieldGoalNoGood: audio.play('SFX_NoGood'); audio.play('AMB_Boo', 0.7); audio.say('VO_FieldGoalNoGood', true); break;
        case Ev.ExtraPointGood: audio.play('SFX_FieldGoalGood', 0.6); audio.say('VO_ExtraPointGood'); break;
        case Ev.ExtraPointNoGood: audio.play('SFX_NoGood'); audio.play('AMB_Boo', 0.7); break;
        case Ev.TwoPointGood: audio.play('SFX_FieldGoalGood'); audio.playOneOf('AMB_Cheer', 3, 0.9); audio.say('VO_TwoPointGood', true); break;
        case Ev.TwoPointNoGood: audio.play('SFX_NoGood'); audio.say('VO_TwoPointNoGood', true); break;
        case Ev.Doink: audio.play('SFX_Goalpost'); break;
        case Ev.FuryStart: audio.play('SFX_FuryIgnite'); audio.sayOneOf('VO_Fury', 3, true); break;
        case Ev.FuryEnd: audio.play('SFX_FuryEnd', 0.8); break;
        case Ev.PlayPicked: audio.play('SFX_PlayPicked', 0.7); break;
        case Ev.QuarterEnd:
          audio.play('SFX_Horn');
          audio.play('SFX_WhistleLong', 0.7);
          if (ev.value < 1.5) audio.say('VO_Quarter2', true);
          else if (ev.value > 2.5 && ev.value < 3.5) audio.say('VO_Quarter4', true);
          break;
        case Ev.Halftime: audio.say('VO_Halftime', true); break;
        case Ev.Overtime: audio.say('VO_Overtime', true); break;
        case Ev.TwoMinute: audio.say('VO_TwoMinute', true); break;
        case Ev.GameOver:
          audio.play('MUS_Victory', 0.7);
          audio.sayOneOf('VO_Final', 2, true);
          this.fireworksLeft = 14;
          this.fireworkTimer = 0.4;
          this.fireworkTeam = ev.team === NONE ? 0 : ev.team;
          break;
        default: break;
      }

      // What it says on screen.
      switch (ev.type) {
        case Ev.Touchdown:
          this.showBanner('TOUCHDOWN!', sim.resultDetail, teamColor(ev.team), 2.8, true);
          this.excitement = 1;
          this.shake = Math.max(this.shake, 0.5);
          break;
        case Ev.FirstDown:
          this.showBanner('FIRST DOWN', teamName(ev.team), teamColor(ev.team), 1.7, false);
          this.excitement = Math.max(this.excitement, 0.6);
          break;
        case Ev.Sack:
          this.showBanner('SACKED!', teamName(ev.team), teamColor(ev.team), 2.2, true);
          this.excitement = Math.max(this.excitement, 0.8);
          break;
        case Ev.Intercept:
          this.showBanner('PICKED OFF!', teamName(ev.team), teamColor(ev.team), 2.4, true);
          this.excitement = 0.95;
          break;
        case Ev.Fumble:
          this.showBanner('FUMBLE!', 'LOOSE BALL', rgba(1, 0.8, 0.1), 1.6, true);
          this.excitement = 0.9;
          break;
        case Ev.Recover: this.showBanner('RECOVERED', teamName(ev.team), teamColor(ev.team), 1.6, false); break;
        case Ev.Incomplete: this.showBanner('INCOMPLETE', '', rgba(0.7, 0.72, 0.75), 1.3, false); break;
        case Ev.BigHit:
          this.shake = Math.max(this.shake, 0.75);
          this.hitStop = 0.07;
          this.slowMo = 0.22;
          this.excitement = Math.max(this.excitement, 0.75);
          break;
        case Ev.Tackle: this.shake = Math.max(this.shake, 0.18 + 0.25 * ev.value); break;
        case Ev.StiffArm: case Ev.Pancake: case Ev.Shove: this.shake = Math.max(this.shake, 0.3); break;
        case Ev.FuryStart:
          this.showBanner('FURY!', teamName(ev.team) + ' UNLEASHED', rgba(1, 0.35, 0.05), 3, true);
          this.excitement = 1;
          this.shake = Math.max(this.shake, 0.6);
          break;
        case Ev.FieldGoalGood:
          this.showBanner("IT'S GOOD!", 'FIELD GOAL', teamColor(ev.team), 2.4, true);
          this.excitement = 0.85;
          break;
        case Ev.FieldGoalNoGood: case Ev.ExtraPointNoGood: this.showBanner('NO GOOD!', '', rgba(0.75, 0.2, 0.15), 2, true); break;
        case Ev.ExtraPointGood: this.showBanner('EXTRA POINT', 'GOOD', teamColor(ev.team), 1.6, false); break;
        case Ev.TwoPointGood:
          this.showBanner('TWO POINTS!', teamName(ev.team), teamColor(ev.team), 2.4, true);
          this.excitement = 0.95;
          break;
        case Ev.TwoPointNoGood: this.showBanner('DENIED!', 'NO CONVERSION', teamColor(ev.team), 2, true); break;
        case Ev.Safety:
          this.showBanner('SAFETY!', 'TWO POINTS', teamColor(ev.team), 2.6, true);
          this.excitement = 0.95;
          break;
        case Ev.TurnoverOnDowns: this.showBanner('TURNOVER ON DOWNS', teamName(ev.team) + ' BALL', teamColor(ev.team), 2.2, false); break;
        case Ev.Touchback: this.showBanner('TOUCHBACK', '', WhiteC, 1.5, false); break;
        case Ev.Halftime:
          this.showBanner('HALFTIME', `${sim.teamInfo(0).abbr} ${sim.teams[0].score}  -  ${sim.teamInfo(1).abbr} ${sim.teams[1].score}`, WhiteC, 5, true);
          break;
        case Ev.QuarterEnd:
          if (ev.value < 1.5 || (ev.value > 2.5 && ev.value < 3.5)) this.showBanner(`END OF QUARTER ${Math.round(ev.value)}`, '', WhiteC, 2.6, false);
          break;
        case Ev.Overtime: this.showBanner('SUDDEN DEATH', 'NEXT SCORE WINS', rgba(1, 0.3, 0.1), 3.4, true); break;
        case Ev.GameOver:
          this.showBanner('FINAL', ev.team === NONE ? 'TIE GAME' : teamName(ev.team) + ' WIN', teamColor(ev.team), 6, true);
          this.excitement = 1;
          break;
        case Ev.TwoMinute: this.showBanner('30 SECONDS', 'LAST CHANCE', rgba(1, 0.8, 0.1), 2, false); break;
        case Ev.Catch: if (ev.value >= 20) this.excitement = Math.max(this.excitement, 0.75); break;
        default: break;
      }
    }
    sim.events.length = 0;
  }

  private visibleAthletes(): number[] {
    const out: number[] = [];
    for (let i = 0; i < NumPlayers; ++i) out.push(this.memberOf(i));
    return out;
  }

  private updateAthletes(dt: number): void {
    // The unit on the field changes between offense, defense and the kicking game. Every roster
    // member already has a dressed body, so a change of unit is only a change of who is shown.
    const w = this.world;
    if (!w) return;
    const onField = new Set<number>();
    for (let i = 0; i < NumPlayers; ++i) {
      const p = this.sim.players[i];
      const member = this.memberOf(i);
      onField.add(member);
      const s = this.states[i];
      s.pos = p.p; s.height = p.height; s.yaw = p.yaw; s.vel = p.v;
      s.act = p.act; s.variant = p.variant; s.actSerial = p.actSerial; s.actTime = p.actTime;
      s.actLength = p.actLength; s.actKey = p.actKey; s.hasBall = p.hasBall;
      s.passer = this.sim.isPasser(i);
      s.fury = this.sim.teams[p.team].inFury();
      s.visible = true;
      w.athletes[member].advance(s, dt);
    }
    for (let m = 0; m < w.athletes.length; ++m) if (!onField.has(m)) w.athletes[m].visible = false;
  }

  private ballPos = new THREE.Vector3();
  private ballQuat = new THREE.Quaternion();

  private updateBall(dt: number): void {
    const w = this.world;
    if (!w) return;
    const sim = this.sim, ball = sim.ball;
    const location = v3ToThree(ball.pos, this.ballPos);
    const rotation = this.ballQuat.identity();
    const mesh = w.ball;
    const tmp = new THREE.Vector3();
    // The ball mesh is long along its own X; three's +X is the field's +X.
    const fromX = (dirField: THREE.Vector3) => {
      // dirField is a three-space direction. Rotate +X onto it, keeping "up" up.
      const m = new THREE.Matrix4();
      const x = dirField.clone().normalize();
      let z = new THREE.Vector3().crossVectors(x, new THREE.Vector3(0, 1, 0));
      if (z.lengthSq() < 1e-6) z = new THREE.Vector3(0, 0, 1);
      z.normalize();
      const y = new THREE.Vector3().crossVectors(z, x).normalize();
      m.makeBasis(x, y, z);
      return new THREE.Quaternion().setFromRotationMatrix(m);
    };
    const velThree = new THREE.Vector3(ball.vel.x, ball.vel.z, ball.vel.y);
    switch (ball.state) {
      case BallState.Held: {
        if (ball.holder >= 0 && ball.holder < NumPlayers) {
          const holder = w.athletes[this.memberOf(ball.holder)];
          const grip = holder.currentGrip() === Grip.None ? Grip.Hand : holder.currentGrip();
          holder.gripWorld(grip, location, rotation);
          // The socket's local Y is the ball's long axis; the ball mesh is long in X.
          rotation.multiply(BallInSocket);
          if (this.lastDrawnBall === BallState.Pass) {
            // Bridge the last flight sample to the receiver's animated hands.
            this.catchOffset.copy(mesh.position).sub(location);
            if (this.catchOffset.length() > 1) this.catchOffset.setLength(1);
            this.catchBlend = 0.09;
          }
          this.catchBlend = Math.max(0, this.catchBlend - dt);
          location.addScaledVector(this.catchOffset, smoothStep(0, 0.09, this.catchBlend));
        }
        break;
      }
      case BallState.Pass: {
        if (this.lastDrawnBall !== BallState.Pass) {
          this.releaseOffset.set(0, 0, 0);
          if (ball.thrower >= 0 && ball.thrower < NumPlayers) {
            w.athletes[this.memberOf(ball.thrower)].gripWorld(Grip.Hand, tmp, new THREE.Quaternion());
            this.releaseOffset.copy(tmp).sub(v3ToThree(ball.from));
            if (this.releaseOffset.length() > 1.1) this.releaseOffset.setLength(1.1);
          }
        }
        location.addScaledVector(this.releaseOffset, 1 - smoothStep(0, 0.14, ball.time));
        // A spiral: nose along the flight path, spinning about its long axis.
        const wobble = ball.tipped ? 6 : 0;
        rotation.copy(velThree.lengthSq() > 1e-6 ? fromX(velThree) : new THREE.Quaternion());
        rotation.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), ball.spin * 2.2));
        if (wobble) rotation.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), ball.spin * wobble));
        break;
      }
      case BallState.Kick:
      case BallState.FieldGoal: {
        // End over end.
        const flat = new THREE.Vector3(velThree.x, 0, velThree.z);
        rotation.copy(fromX(flat.lengthSq() > 1e-6 ? flat : new THREE.Vector3(1, 0, 0)));
        rotation.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), ball.spin * 0.9));
        break;
      }
      case BallState.Loose:
      case BallState.Dead: {
        const speed = ball.vel.size();
        this.ballSpin.z += speed * dt * 0.7 * (Math.PI / 180);
        this.ballSpin.y += speed * dt * 0.25 * (Math.PI / 180);
        rotation.setFromEuler(this.ballSpin);
        break;
      }
      case BallState.Snap:
        rotation.copy(fromX(new THREE.Vector3(sim.offenseDir(), 0, 0)));
        rotation.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), ball.spin * 2));
        break;
      case BallState.Tee:
        if (sim.playType === PlayType.Kickoff) {
          location.y = 22 * CM;      // propped up on the tee
          rotation.copy(fromX(new THREE.Vector3(Dir(sim.kickingTeam), 0, 0)));
          rotation.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), (72 * Math.PI) / 180));
        } else if (sim.playType === PlayType.FieldGoal || sim.playType === PlayType.ExtraPoint) {
          location.y = (sim.phase === Phase.Live ? 14 : 9) * CM;
          if (sim.phase === Phase.Live) rotation.setFromAxisAngle(new THREE.Vector3(0, 0, 1), (80 * Math.PI) / 180);
          else rotation.setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 2);
        } else {
          location.y = 9 * CM;
        }
        break;
    }
    this.lastDrawnBall = ball.state;
    mesh.position.copy(location);
    mesh.quaternion.copy(rotation);

    const tee = sim.playType === PlayType.Kickoff && (sim.phase === Phase.Lineup || sim.phase === Phase.PreSnap || ball.state === BallState.Tee);
    w.tee.visible = tee;
    if (tee) toThree(sim.losX, 0, 0, w.tee.position);
  }

  private updateMarkers(): void {
    const w = this.world;
    if (!w) return;
    const sim = this.sim;
    const time = this.now();
    for (let i = 0; i < w.markers.length; ++i) {
      const seat = sim.seats[i];
      const show = seat.active && seat.player !== NONE && sim.phase !== Phase.GameOver;
      const marker = w.markers[i];
      marker.visible = show;
      if (!show) continue;
      const p = sim.players[seat.player];
      const pulse = p.hasBall ? 1 + 0.12 * Math.sin(time * 9) : 1;
      toThree(p.p.x, p.p.y, 2.5, marker.position);
      const ring = sim.afterWhistle() ? 1.06 : 1.75 * pulse;
      marker.scale.set(ring, 1, ring);
      w.setMarkerFill(i, sim.afterWhistle() ? 0.035 : p.hasBall ? 0.4 : 0.16);
    }

    // A narrowing gold ring gives returners and receivers a catch point while the ball is aloft.
    const ball = sim.ball;
    const flight = ball.state === BallState.Kick || ball.state === BallState.Pass;
    const showCatch = sim.phase === Phase.Live && flight && !ball.tipped && ball.time < ball.duration;
    w.catchMarker.visible = showCatch;
    if (showCatch) {
      const remaining = 1 - ball.time / ball.duration;
      const diameter = 1.4 + 1.8 * remaining;
      toThree(ball.to.x, ball.to.y, 3.5, w.catchMarker.position);
      w.catchMarker.scale.set(diameter, 1, diameter);
    }

    // The line of scrimmage and the line to gain, the way television draws them.
    const scrimmage = sim.playType === PlayType.Scrimmage || sim.playType === PlayType.Punt || sim.playType === PlayType.FieldGoal;
    const lines = scrimmage && (sim.phase === Phase.PlaySelect || sim.phase === Phase.Lineup || sim.phase === Phase.PreSnap || sim.phase === Phase.Live);
    w.stadium.setChains(scrimmage ? sim.down : 0, sim.losX, sim.firstDownX, sim.offenseDir(), sim.goalToGo());
    w.scrimmageLine.visible = lines;
    toThree(sim.losX, 0, 0.7, w.scrimmageLine.position);
    w.firstDownLine.visible = lines && !sim.goalToGo();
    toThree(sim.firstDownX, 0, 0.7, w.firstDownLine.position);
  }

  private updateCamera(dt: number, snap: boolean): void {
    // A sideline broadcast camera on the +Y side. Each frame it works out which athletes matter,
    // then picks the tightest shot that still shows all of them: wide before the snap so the whole
    // formation is readable, close on a runner, stretched out along a long pass.
    const sim = this.sim, ball = sim.ball;
    const carrier = sim.carrierIndex();
    let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
    const include = (p: Vec2, pad: number) => {
      minX = Math.min(minX, p.x - pad); minY = Math.min(minY, p.y - pad);
      maxX = Math.max(maxX, p.x + pad); maxY = Math.max(maxY, p.y + pad);
    };
    const ballFlat = new Vec2(ball.pos.x, ball.pos.y);
    let close = false;
    let closeEye = new THREE.Vector3(), closeLook = new THREE.Vector3();
    let minDistance = 2700;
    let flightHeight = 0;

    switch (sim.phase) {
      case Phase.PlaySelect:
      case Phase.PatSelect:
        include(sim.ballSpot().add(new Vec2(sim.offenseDir() * 300, 0)), 1300);
        break;
      case Phase.Lineup:
      case Phase.PreSnap:
      case Phase.Break:
        if (sim.playType === PlayType.Kickoff) {
          // The kicking team and the first stretch of field in front of it.
          for (let slot = 0; slot < TeamSize; ++slot) include(sim.players[sim.kickingTeam * TeamSize + slot].home, 150);
          include(new Vec2(sim.losX + Dir(sim.kickingTeam) * 1200, 0), 100);
        } else {
          for (const p of sim.players) {
            // The deep safety (and a deep returner) can be left out of the pre-snap picture.
            if (Math.abs(p.home.x - sim.losX) < 16 * Yard) include(p.home, 170);
          }
        }
        break;
      case Phase.Live:
        if (ball.state === BallState.Kick || ball.state === BallState.FieldGoal || ball.state === BallState.Pass) {
          // Frame a moving stretch of the flight path. Converting height into depth at the
          // sideline camera angle keeps the ball and the approaching catch point in view.
          const lookAhead = ball.land().sub(ballFlat).clampedToMaxSize(1250);
          flightHeight = Math.max(0, ball.pos.z) * 0.48;
          const ballDepth = (ball.pos.z - flightHeight) * 1.48;
          include(ballFlat.sub(new Vec2(0, ballDepth)), 370);
          include(ballFlat.add(lookAhead).add(new Vec2(0, flightHeight * 1.48)), 560);
          minDistance = 3200;
        } else if (carrier !== NONE && sim.isPasser(carrier)) {
          // The pocket and everyone the quarterback could throw to.
          for (let slot = 0; slot < TeamSize; ++slot) {
            const p = sim.players[sim.offense * TeamSize + slot];
            include(p.p.add(p.v.mul(0.25)), slot >= 4 ? 260 : 200);
          }
        } else if (carrier !== NONE) {
          // A runner: him, the grass ahead of him, and the nearest men chasing.
          const c = sim.players[carrier];
          include(c.p, 520);
          include(c.p.add(new Vec2(Dir(c.team) * 700, 0)).add(c.v.mul(0.35)), 300);
          const nearest = [1e12, 1e12];
          const chasers = [c.p, c.p];
          for (const p of sim.players) {
            if (p.team === c.team || p.down) continue;
            const d = Vec2.distSquared(p.p, c.p);
            if (d < nearest[0]) { nearest[1] = nearest[0]; chasers[1] = chasers[0]; nearest[0] = d; chasers[0] = p.p; }
            else if (d < nearest[1]) { nearest[1] = d; chasers[1] = p.p; }
          }
          for (let i = 0; i < 2; ++i) if (nearest[i] < (18 * Yard) ** 2) include(chasers[i], 200);
        } else {
          include(ballFlat, 800);
        }
        // Nobody should be playing blind: keep every human-controlled athlete near the play in shot.
        for (const seat of sim.seats) {
          if (seat.active && seat.player !== NONE && Vec2.distSquared(sim.players[seat.player].p, ballFlat) < (30 * Yard) ** 2) {
            include(sim.players[seat.player].p, 220);
          }
        }
        break;
      case Phase.Dead:
      case Phase.Celebrate:
        if (sim.phase === Phase.Celebrate && sim.scorer !== NONE && sim.phaseTime < 1.6 && !this.options.get(Option.ReducedMotion)) {
          // Get in close on the celebration. The shot aims above his waist so he stands in the
          // lower half of the frame, clear of the banner.
          const s = sim.players[sim.scorer];
          const swing = sim.phaseTime * 0.45;
          close = true;
          closeLook = new THREE.Vector3(s.p.x, s.p.y, 172);
          closeEye = closeLook.clone().add(new THREE.Vector3(-Dir(s.team) * Math.cos(swing) * 740, 600 + Math.sin(swing) * 200, 40));
        } else {
          let focus = sim.whistleFocus;
          const primary = this.picker(0);
          if (primary !== NONE && sim.seats[primary].player !== NONE) focus = sim.players[sim.seats[primary].player].p;
          include(focus, 350);
          const humanView = primary !== NONE;
          for (let i = 0; i < MaxSeats; ++i) {
            const seat = sim.seats[i];
            if (!seat.active || seat.player === NONE) continue;
            const pos = sim.players[seat.player].p;
            if ((humanView && !this.seats[i].bot) || Vec2.distSquared(pos, focus) < (10 * Yard) ** 2) include(pos, 180);
          }
          minDistance = 1550;
        }
        break;
      case Phase.GameOver:
        include(new Vec2(ball.pos.x * 0.5, 0), 2200);
        break;
    }
    if (minX > maxX) include(ballFlat, 1200);

    // Turn the box into a shot. With a 32 degree lens tilted 34 degrees down, a camera at distance D
    // sees 0.287 D to either side, 0.378 D beyond its aim point and 0.233 D short of it.
    const Fov = 32, SinPitch = 0.559, CosPitch = 0.829;
    const cx = (minX + maxX) * 0.5, cy = (minY + maxY) * 0.5;
    const hx = (maxX - minX) * 0.5, hy = (maxY - minY) * 0.5;
    const needed = Math.max(hx / 0.287, (hy + 190) / 0.3055) * 1.06;      // extra depth clears the score bug
    const distance = Math.min(Math.max(needed, minDistance), 6200);
    const aimY = sim.afterWhistle() ? cy : Math.min(Math.max(cy + 0.0725 * distance, -SidelineY), SidelineY + 300);
    const aimX = Math.min(Math.max(cx, -EndLineX - 200), EndLineX + 200);

    let wantEye: THREE.Vector3, wantLook: THREE.Vector3;
    if (close) { wantEye = closeEye; wantLook = closeLook; }
    else {
      wantLook = new THREE.Vector3(aimX, aimY, sim.afterWhistle() ? 105 : flightHeight);
      wantEye = wantLook.clone().add(new THREE.Vector3(0, distance * CosPitch, distance * SinPitch));
    }

    // Cut rather than swoop when the shot changes completely (to and from the close-up, or a long way down the field).
    const eye = this.camEye, look = this.camLook;
    const wasClose = eye.z < 600;
    const cut = snap || wasClose !== close || Math.abs(look.x - wantLook.x) > 4500;
    if (cut) { eye.copy(wantEye); look.copy(wantLook); }
    else {
      // Pull back quickly when something needs to be seen; ease in gently so the picture does not pump.
      const widening = wantEye.z > eye.z;
      look.lerp(wantLook, 1 - Math.exp(-4.2 * dt));
      eye.x += (wantEye.x - eye.x) * (1 - Math.exp(-4.2 * dt));
      const zoomRate = widening ? 3.4 : 1.3;
      eye.y += (wantEye.y - eye.y) * (1 - Math.exp(-zoomRate * dt));
      eye.z += (wantEye.z - eye.z) * (1 - Math.exp(-zoomRate * dt));
    }
    this.camFov = close ? 38 : Fov;
    if (flightHeight > 0) {
      // Keep a rising ball clear of the score display while the tracking shot catches up.
      // Correct the pitch by only the amount needed to bring it below the upper fifth.
      const forward = look.clone().sub(eye).normalize();
      const right = new THREE.Vector3(0, 0, 1).cross(forward).normalize();      // UpVector x Forward, field space
      const upv = forward.clone().cross(right);
      const toBall = new THREE.Vector3(ball.pos.x, ball.pos.y, ball.pos.z).sub(eye);
      const depth = toBall.dot(forward);
      if (depth > 1) {
        const aspect = this.outputSize.y > 0 ? this.outputSize.x / this.outputSize.y : 16 / 9;
        const topAngle = Math.atan((0.58 * Math.tan(((Fov * 0.5) * Math.PI) / 180)) / aspect);
        const lift = Math.atan2(toBall.dot(upv), depth) - topAngle;
        if (lift > 0) {
          const pitch = Math.asin(Math.min(Math.max(forward.z, -1), 1));
          const yaw = Math.atan2(forward.y, forward.x);
          const newPitch = pitch + Math.min((14 * Math.PI) / 180, lift);
          const dir = new THREE.Vector3(Math.cos(newPitch) * Math.cos(yaw), Math.cos(newPitch) * Math.sin(yaw), Math.sin(newPitch));
          const reach = look.distanceTo(eye);
          look.copy(eye).addScaledVector(dir, reach);
        }
      }
    }

    if (this.options.get(Option.ReducedMotion)) this.shake = 0;
    let jx = 0, jy = 0, jz = 0;
    if (this.shake > 0.01) {
      const t = this.now();
      jx = Math.sin(t * 61) * this.shake * 22; jy = Math.sin(t * 47 + 1.3) * this.shake * 22; jz = Math.sin(t * 53 + 2.1) * this.shake * 22;
      this.shake = Math.max(0, this.shake - dt * 1.9);
    }
    this.shotEye.set(eye.x + jx, eye.y + jy, eye.z + jz);
    this.shotLook.set(look.x + jx * 0.4, look.y + jy * 0.4, look.z + jz * 0.4);
    this.camFovShot = this.camFov;
  }
  private shotEye = new THREE.Vector3();
  private shotLook = new THREE.Vector3();
  private camFovShot = 32;

  /** The camera the renderer should use this frame (field space, cm; horizontal FOV in degrees). */
  cameraShot(): { eye: THREE.Vector3; look: THREE.Vector3; fov: number } {
    if (this.screen === Screen.Match && !(this.viewingFilm)) return { eye: this.shotEye, look: this.shotLook, fov: this.camFovShot };
    return { eye: this.camEye, look: this.camLook, fov: this.camFov };
  }

  private updateEffects(dt: number): void {
    const w = this.world;
    if (!w) return;
    const sim = this.sim, fx = w.fx;
    // Athletes on a team in Fury burn: flames lick off them as they move.
    for (let i = 0; i < NumPlayers; ++i) {
      const p = sim.players[i];
      if (!sim.teams[p.team].inFury() || sim.phase === Phase.PlaySelect) continue;
      // The ball carrier blazes; everyone else smoulders, more the faster they move.
      const rate = p.hasBall ? 60 : 5 + 16 * Math.min(1, p.v.size() / 700);
      const expected = Math.min(6, rate * dt * fx.particleDensity);
      let flames = Math.floor(expected);
      if (this.sparkle.fRand() < expected - flames) ++flames;
      if (flames > 0) {
        const athlete = w.athletes[this.memberOf(i)];
        const chest = athlete.boneWorldPosition(w.anims.spine3 >= 0 ? w.anims.spine3 : 0);
        for (let j = 0; j < flames; ++j) {
          fx.flame({ x: chest.x / CM, y: chest.z / CM, z: chest.y / CM + this.sparkle.fRandRange(-60, 30) }, { x: p.v.x * 0.25, y: p.v.y * 0.25, z: 0 });
        }
      }
    }

    // A long ball leaves a faint streak.
    const ball = sim.ball;
    if (ball.state === BallState.Pass || ball.state === BallState.Kick || ball.state === BallState.FieldGoal) {
      const fury = ball.thrower !== NONE && sim.teams[sim.players[ball.thrower].team].inFury();
      const spacing = 40 / fx.particleDensity;
      const start = this.lastTrailPoint ?? ball.pos;
      const seg = ball.pos.sub(start);
      const length = seg.size();
      // Space particles along the flight rather than adding one per displayed frame.
      if (length > 1e-8 && length < 900) {
        let d = Math.max(0, spacing - this.trailDistance);
        for (; d <= length; d += spacing) {
          const at = start.add(seg.mul(d / length));
          fx.emit(at, { x: 0, y: 0, z: 0 }, fury ? rgba(1, 0.4, 0.05) : rgba(0.85, 0.9, 1), 0.22, fury ? 42 : 20, fury ? 2.2 : 0.7, 0, 0, -60);
        }
        this.trailDistance = length + spacing - d;
      }
      this.lastTrailPoint = ball.pos;
    } else {
      this.lastTrailPoint = null;
      this.trailDistance = 0;
    }

    // Fireworks over the far stands after a score.
    if (this.fireworksLeft > 0) {
      this.fireworkTimer -= dt;
      if (this.fireworkTimer <= 0) {
        this.fireworkTimer = this.sparkle.fRandRange(0.18, 0.5);
        --this.fireworksLeft;
        const team = sim.teamInfo(this.fireworkTeam);
        const primary = colorOfHex(team.primary), secondary = colorOfHex(team.secondary);
        const colors = [luminance(primary) < 0.04 ? secondary : primary, secondary, rgba(1, 0.85, 0.4)];
        const origin = { x: this.sparkle.fRandRange(-5500, 5500), y: this.sparkle.fRandRange(-9000, -6500), z: this.sparkle.fRandRange(4200, 6400) };
        const pick = colors[this.sparkle.randRange(0, 2)];
        const scale = this.sparkle.fRandRange(1, 1.7);
        if (!this.options.get(Option.ReducedMotion)) fx.firework(origin, pick, scale);
        this.audio.playOneOf('SFX_Fireworks', 3, 0.55, 0.1);
      }
    }

    // Camera flashes twinkle in the crowd, more of them the louder it gets.
    const seatsSample = w.stadium.seatSample();
    if (!this.options.get(Option.ReducedMotion) && seatsSample.length > 0) {
      this.flashTimer -= dt;
      const perSecond = 3 + (110 - 3) * this.excitement * this.excitement;
      while (this.flashTimer <= 0) {
        this.flashTimer += 1 / perSecond;
        const seat = seatsSample[this.sparkle.randRange(0, seatsSample.length - 1)];
        fx.emit(seat, { x: 0, y: 0, z: 0 }, rgba(0.9, 0.95, 1), 0.09, 150, 5, 0, 0, 0);
      }
    }
  }
}

function approach(value: number, target: number, step: number): number {
  return value < target ? Math.min(value + step, target) : Math.max(value - step, target);
}
