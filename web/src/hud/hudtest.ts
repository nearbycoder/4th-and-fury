/**
 * Visual test page for the HUD (web/hud-test.html). Builds a Director in a chosen state and draws
 * the HUD over a dark field sketch. Pick the state with ?state=title|lobby|teams|playselect|live|
 * pat|final|pause|guide|settings|sound|film|banner (default: playselect). Add &freeze=1 to stop the
 * clock (stable screenshots), &style=playstation (etc.) to seat the players on gamepads.
 */
import * as THREE from 'three';
import { Director, Screen } from '../game/director';
import { FuryInput, PadKind, type FaceStyle } from '../game/input';
import { FuryBot } from '../sim/bot';
import { leagueTeams, makeSeatInput, MaxSeats, NONE, Phase, SeatInput, Vec2, Vec3 } from '../sim/index';
import { toThree } from '../game/space';
import { Hud, loadHudFonts } from './hud';
import { rgba } from './style';

const params = new URLSearchParams(location.search);
const state = params.get('state') ?? 'playselect';
const freeze = params.get('freeze') === '1';
/** &style=xbox|playstation|nintendo|generic seats everyone on (fake) gamepads with that face style. */
const style = params.get('style') as FaceStyle | null;

const images = new Map<string, HTMLImageElement>();
function image(file: string): HTMLImageElement {
  let img = images.get(file);
  if (!img) {
    img = new Image();
    img.src = `${import.meta.env.BASE_URL}assets/textures/${file}`;
    images.set(file, img);
  }
  return img;
}

/** A Director with the renderer's two hooks stubbed: UI textures and a fixed broadcast camera. */
class TestDirector extends Director {
  camera = new THREE.PerspectiveCamera(36, 16 / 9, 10, 100000);
  cssW = 1920; cssH = 1080;
  frozenNow = 1000;
  override now(): number { return freeze ? this.frozenNow : super.now(); }
  override uiTexture(name: string): HTMLImageElement | null {
    let file = '';
    if (name === 'T_Title') file = 'title.webp';
    else if (name === 'T_TitleSmall') file = 'title_small.webp';
    else if (name === 'T_Icon_Flame') file = 'icons/flame.png';
    else if (name.startsWith('T_Logo_')) file = `logo_${name.slice(7)}.webp`;
    if (!file) return null;
    const img = image(file);
    return img.complete && img.naturalWidth > 0 ? img : null;
  }
  aim(): void {
    const focus = this.sim.ball.pos;
    const eye = toThree(focus.x - 300, 3600, 1900);
    this.camera.aspect = this.cssW / this.cssH;
    this.camera.position.copy(eye);
    this.camera.lookAt(toThree(focus.x, focus.y * 0.5, 0));
    this.camera.updateMatrixWorld();
    this.camera.updateProjectionMatrix();
  }
  override worldToScreen(world: Vec3): Vec2 | null {
    const p = toThree(world.x, world.y, world.z).project(this.camera);
    if (p.z > 1) return null;
    return new Vec2((p.x * 0.5 + 0.5) * this.cssW, (0.5 - p.y * 0.5) * this.cssH);
  }
}

const d = new TestDirector();
const bots: FuryBot[] = Array.from({ length: MaxSeats }, () => new FuryBot());
const idle: SeatInput[] = Array.from({ length: MaxSeats }, () => makeSeatInput());
const dt = 1 / 60;

function joinSeats(count: number): void {
  for (let i = 0; i < count; ++i) {
    const seat = d.seats[i];
    seat.joined = true;
    seat.pad = i === 0 ? FuryInput.KeyboardA : FuryInput.KeyboardB;
    if (style) {
      seat.pad = FuryInput.FirstGamepad + i;
      const pad = FuryInput.get().pad(seat.pad);
      pad.kind = PadKind.Gamepad;
      pad.connected = true;
      pad.faceStyle = style;
      pad.label = style.toUpperCase() + ' PAD';
    }
    seat.side = i % 2;
  }
}

function startMatch(humans: number): void {
  joinSeats(humans);
  for (let i = 0; i < humans; ++i) {
    d.sim.setSeat(i, true, i % 2);
    bots[i].reset(i, 500 + i);
  }
  d.teamPick = [0, 3];
  d.sim.startMatch(0, 3, 120, 0.5, 1);
  d.screen = Screen.Match;
}

function step(humans: number, useBots: boolean): void {
  const inputs = idle.map((x, i) => (useBots && i < humans ? bots[i].think(d.sim, dt) : x));
  d.sim.step(dt, inputs);
}

function runUntil(humans: number, done: () => boolean, limit = 60 * 600): void {
  for (let n = 0; n < limit && !done(); ++n) step(humans, true);
}

function idleFor(humans: number, seconds: number): void {
  for (let n = 0; n < seconds / dt; ++n) step(humans, false);
}

function setup(): void {
  switch (state) {
    case 'title':
      d.screen = Screen.Title;
      d.screenTime = 3;
      break;
    case 'lobby':
      joinSeats(3);
      d.seats[2].side = NONE;
      d.seats[1].ready = true;
      d.screen = Screen.Lobby;
      d.screenTime = 2;
      break;
    case 'teams':
      joinSeats(2);
      d.teamPick = [1, 3];
      d.teamLocked = [true, false];
      d.optionRow = [0, 0];
      d.screen = Screen.Teams;
      d.screenTime = 2;
      break;
    case 'live':
    case 'banner':
      startMatch(2);
      runUntil(2, () => d.sim.phase === Phase.PlaySelect);
      runUntil(2, () => d.sim.phase === Phase.Live && d.sim.liveTime > 1.2);
      if (state === 'banner') {
        d.banner.title = 'TOUCHDOWN!';
        d.banner.detail = 'MEM  #21  J. RIVERA  /  34 YD RUN';
        d.banner.color = rgba(1, 0.3, 0.03);
        d.banner.big = true;
        d.banner.length = 3;
        d.banner.start = d.now() - 1;
      }
      break;
    case 'pat':
      startMatch(2);
      runUntil(2, () => d.sim.phase === Phase.PatSelect, 60 * 60 * 30);
      idleFor(2, 0.5);
      break;
    case 'final':
    case 'film': {
      startMatch(2);
      d.sim.quarterLength = 20;
      d.sim.clock = Math.min(d.sim.clock, 20);
      let guard = 0;
      while (d.sim.phase !== Phase.GameOver && guard++ < 60 * 60 * 60) {
        step(2, true);
        d.film.record(d.sim);
      }
      d.screen = Screen.Final;
      d.screenTime = 3;
      if (state === 'film') {
        d.viewingFilm = true;
        d.filmTime = Math.min(2, d.selectedFilm().duration() * 0.5);
      }
      break;
    }
    case 'pause':
    case 'guide':
    case 'settings':
    case 'sound':
      startMatch(2);
      runUntil(2, () => d.sim.phase === Phase.Live && d.sim.liveTime > 1.2);
      d.paused = true;
      d.pauseSeat = 0;
      d.pauseCursor = 1;
      d.fieldGuide = state === 'guide';
      if (state === 'settings' || state === 'sound') {
        d.settingsPad = style ? FuryInput.FirstGamepad : FuryInput.KeyboardA;
        d.soundTab = state === 'sound';
        d.settingsRow = 2;
        d.liveFPS = 118;
        d.outputSize = { x: 2560, y: 1440 };
        d.renderPercent = 75;
      }
      break;
    default:
      startMatch(2);
      runUntil(2, () => d.sim.phase === Phase.PlaySelect);
      idleFor(2, 0.4);
      d.sim.picks[1].cursor = 4;
      break;
  }
}

/** A rough field so the tags have something to sit on. */
function drawBackdrop(bg: HTMLCanvasElement): void {
  const ctx = bg.getContext('2d')!;
  const dpr = window.devicePixelRatio || 1;
  bg.width = Math.round(bg.clientWidth * dpr);
  bg.height = Math.round(bg.clientHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const g = ctx.createLinearGradient(0, 0, 0, bg.clientHeight);
  g.addColorStop(0, '#1d4a2a');
  g.addColorStop(1, '#2f6b39');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, bg.clientWidth, bg.clientHeight);
  if (d.screen !== Screen.Match) return;
  d.cssW = bg.clientWidth; d.cssH = bg.clientHeight;
  d.aim();
  ctx.strokeStyle = 'rgba(255,255,255,0.55)';
  ctx.lineWidth = 3;
  for (let yard = -50; yard <= 50; yard += 5) {
    const a = d.worldToScreen(new Vec3(yard * 91.44, -2438, 0)), b = d.worldToScreen(new Vec3(yard * 91.44, 2438, 0));
    if (!a || !b) continue;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  const teams = leagueTeams();
  for (const p of d.sim.players) {
    const foot = d.worldToScreen(new Vec3(p.p.x, p.p.y, 0)), head = d.worldToScreen(new Vec3(p.p.x, p.p.y, 190));
    if (!foot || !head) continue;
    const h = foot.y - head.y;
    ctx.fillStyle = teams[d.sim.teams[p.team].league].primary;
    ctx.fillRect(foot.x - h * 0.18, head.y, h * 0.36, h);
  }
  const ball = d.worldToScreen(d.sim.ball.pos);
  if (ball) { ctx.fillStyle = '#7a4a22'; ctx.beginPath(); ctx.ellipse(ball.x, ball.y, 9, 6, 0, 0, Math.PI * 2); ctx.fill(); }
}

async function main(): Promise<void> {
  await loadHudFonts();
  setup();
  // Preload the textures the HUD asks for, then draw.
  for (const name of ['T_Title', 'T_TitleSmall', 'T_Icon_Flame', ...leagueTeams().map((t) => 'T_Logo_' + t.id)]) d.uiTexture(name);
  await Promise.all([...images.values()].map((img) => img.decode().catch(() => undefined)));
  const bg = document.getElementById('field') as HTMLCanvasElement;
  const hud = new Hud(document.getElementById('hud') as HTMLCanvasElement);
  const frame = () => {
    drawBackdrop(bg);
    hud.draw(d);
    if (!freeze) requestAnimationFrame(frame);
  };
  frame();
  document.body.dataset.ready = '1';
}

main().catch((e) => { document.body.textContent = String(e?.stack ?? e); });
