/**
 * 4th & Fury in the browser: boot the renderer, load the art, and run the director every frame.
 */
import { Director } from './game/director';
import { FuryInput } from './game/input';
import { World } from './game/world';
import { Hud, loadHudFonts } from './hud/hud';

const boot = document.getElementById('boot')!;
const fill = boot.querySelector<HTMLElement>('.fill')!;
const label = boot.querySelector<HTMLElement>('.label')!;
const startButton = boot.querySelector<HTMLButtonElement>('.start')!;
const gameCanvas = document.getElementById('game') as HTMLCanvasElement;
const hudCanvas = document.getElementById('hud') as HTMLCanvasElement;

function progress(fraction: number, text: string): void {
  fill.style.width = `${Math.round(Math.min(Math.max(fraction, 0), 1) * 100)}%`;
  label.textContent = text;
}

async function main(): Promise<void> {
  let world: World;
  try {
    world = new World(gameCanvas);
  } catch (e) {
    label.innerHTML = '<span class="error">This browser could not start WebGL. Try a recent desktop Chrome, Edge, Firefox or Safari.</span>';
    throw e;
  }
  const director = new Director();
  const hud = new Hud(hudCanvas);
  const input = FuryInput.get();

  const resize = () => {
    const w = window.innerWidth, h = window.innerHeight;
    world.resize(w, h);
    director.outputSize = { x: w * devicePixelRatio, y: h * devicePixelRatio };
  };
  window.addEventListener('resize', resize);
  resize();

  await Promise.all([loadHudFonts().catch(() => undefined), world.load(progress)]);
  progress(1, 'Ready');
  await director.init(world);
  resize();

  // Browsers only start sound after a click or key press, so the first one also enters the game.
  boot.classList.add('ready');
  label.textContent = 'Ready';
  if (matchMedia('(pointer: coarse)').matches && !matchMedia('(any-pointer: fine)').matches) {
    // Touch-only devices: the game needs a keyboard or a gamepad.
    boot.querySelector<HTMLElement>('.hint')!.textContent = 'This game is played with a keyboard or a gamepad. Connect one, or come back on a computer.';
  }
  startButton.focus();
  let entered = false;
  const enter = (e?: Event) => {
    e?.preventDefault();
    if (entered) return;
    entered = true;
    director.audio.unlock();
    // Start listening only now, so the key that dismissed this screen does not also join a player.
    input.attach(window);
    input.onGesture(() => director.audio.unlock());
    boot.classList.add('done');
    document.body.classList.add('playing');
    window.removeEventListener('keydown', enterKey);
  };
  const enterKey = (e: KeyboardEvent) => { if (e.code === 'Enter' || e.code === 'Space') enter(e); };
  startButton.addEventListener('click', () => enter(), { once: true });
  window.addEventListener('keydown', enterKey);

  let last = performance.now();
  let boardVersion = -1;
  const frame = (now: number) => {
    const dt = Math.min((now - last) / 1000, 0.1);
    last = now;
    director.tick(dt);
    const shot = director.cameraShot();
    world.setCamera(shot.eye, shot.look, shot.fov);
    hud.draw(director);
    if (hud.board.version !== boardVersion) {
      boardVersion = hud.board.version;
      world.stadium.setBoard(hud.board.canvas);
    }
    world.render(now / 1000);
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

main().catch((e) => {
  console.error(e);
  label.innerHTML = `<span class="error">Something went wrong while loading: ${String(e?.message ?? e)}</span>`;
});
