/**
 * Collects input from every device into pads (port of FFuryInput / FFuryPad, FuryInput.cpp and the
 * polling half of FuryInputMac.cpp).
 *
 * Sources: the keyboard (split into two pads), the Gamepad API (polled every tick, like the macOS
 * GameController path, so any number of pads work), and scripted bots. Stick.x is right-positive,
 * stick.y is up-positive.
 *
 * Usage: FuryInput.get().attach(window) once, then FuryInput.get().tick(dt) once per frame before
 * the game reads the pads. onGesture() lets the app resume audio on the first key / pointer press.
 */
import { NONE, Vec2 } from '../sim/core';

/** The buttons the game understands, named after an Xbox-style pad. */
export enum Button { A, B, X, Y, LB, RB, LT, RT, Start, Back, Up, Down, Left, Right, Count }

export enum PadKind { None, Keyboard, Gamepad, Bot }

export type FaceStyle = 'xbox' | 'playstation' | 'nintendo' | 'generic';

const ButtonCount = Button.Count as number;

const StickDeadZone = 0.22;
const NavThreshold = 0.55;
const NavFirstRepeat = 0.38;
const NavRepeat = 0.13;
const TriggerThreshold = 0.35;

/** One input device as the game sees it: a gamepad, one half of the keyboard, or a scripted bot. */
export class Pad {
  kind: PadKind = PadKind.None;
  connected = false;
  label = '';
  /** Which markings the face buttons carry (replaces the macOS SF Symbols FaceSymbols). */
  faceStyle: FaceStyle = 'generic';

  stick: Vec2 = Vec2.Zero;
  down: boolean[] = new Array(ButtonCount).fill(false);
  pressed: boolean[] = new Array(ButtonCount).fill(false);
  released: boolean[] = new Array(ButtonCount).fill(false);

  /** Menu navigation: one step per push, with auto-repeat while held. */
  navX = 0;
  navY = 0;

  isDown(b: Button): boolean { return this.down[b]; }
  wasPressed(b: Button): boolean { return this.pressed[b]; }
  wasReleased(b: Button): boolean { return this.released[b]; }
  anyPressed(): boolean { return this.pressed.some((p) => p); }
  turbo(): boolean { return this.isDown(Button.RT) || this.isDown(Button.LT); }

  // --- Internal to FuryInput (C++ private + friend) ---
  /** @internal */ pendingPress: boolean[] = new Array(ButtonCount).fill(false);
  /** @internal */ pendingRelease: boolean[] = new Array(ButtonCount).fill(false);
  /** @internal */ raw: boolean[] = new Array(ButtonCount).fill(false);
  /** @internal */ rawStick: Vec2 = Vec2.Zero;
  /** @internal */ navHold: number[] = [0, 0];
  /** @internal */ navDir: number[] = [0, 0];
  /** @internal Gamepad.index of the device in this slot. */ nativeId = NONE;
  /** @internal Gamepad.id of the device in this slot. */ nativeName = '';
  /** @internal */ seen = false;

  /** @internal */
  recordButton(button: Button, held: boolean): void {
    if (this.raw[button] === held) return;
    this.raw[button] = held;
    if (held) this.pendingPress[button] = true;
    else this.pendingRelease[button] = true;
  }
}

interface KeyBinding { key: string; pad: number; button: Button }
interface KeyDirection { key: string; pad: number; button: Button }

const KA = 0, KB = 1;

// Keyboard A: WASD to move, T/F/G/H as the Y/X/A/B diamond. Keyboard B: arrows, I/J/K/L.
const KeyButtons: KeyBinding[] = [
  { key: 'KeyG', pad: KA, button: Button.A }, { key: 'Space', pad: KA, button: Button.A },
  { key: 'KeyH', pad: KA, button: Button.B }, { key: 'KeyF', pad: KA, button: Button.X },
  { key: 'KeyT', pad: KA, button: Button.Y }, { key: 'ShiftLeft', pad: KA, button: Button.RT },
  { key: 'KeyQ', pad: KA, button: Button.LB }, { key: 'KeyE', pad: KA, button: Button.RB },
  { key: 'Escape', pad: KA, button: Button.Start }, { key: 'Tab', pad: KA, button: Button.Back },
  { key: 'KeyK', pad: KB, button: Button.A }, { key: 'KeyL', pad: KB, button: Button.B },
  { key: 'KeyJ', pad: KB, button: Button.X }, { key: 'KeyI', pad: KB, button: Button.Y },
  { key: 'ShiftRight', pad: KB, button: Button.RT }, { key: 'KeyU', pad: KB, button: Button.LB },
  { key: 'KeyO', pad: KB, button: Button.RB }, { key: 'Enter', pad: KB, button: Button.Start },
  { key: 'NumpadEnter', pad: KB, button: Button.Start }, { key: 'Backspace', pad: KB, button: Button.Back },
];

// Each direction key is tracked as a hidden d-pad button so opposite keys cancel cleanly.
const KeyDirections: KeyDirection[] = [
  { key: 'KeyW', pad: KA, button: Button.Up }, { key: 'KeyS', pad: KA, button: Button.Down },
  { key: 'KeyA', pad: KA, button: Button.Left }, { key: 'KeyD', pad: KA, button: Button.Right },
  { key: 'ArrowUp', pad: KB, button: Button.Up }, { key: 'ArrowDown', pad: KB, button: Button.Down },
  { key: 'ArrowLeft', pad: KB, button: Button.Left }, { key: 'ArrowRight', pad: KB, button: Button.Right },
];

const GameKeys = new Set<string>([...KeyButtons.map((b) => b.key), ...KeyDirections.map((b) => b.key)]);

/** Standard Gamepad mapping: button index -> game button. LT/RT (6, 7) are read as analog values. */
const StandardButtons: [number, Button][] = [
  [0, Button.A], [1, Button.B], [2, Button.X], [3, Button.Y], [4, Button.LB], [5, Button.RB],
  [8, Button.Back], [9, Button.Start], [12, Button.Up], [13, Button.Down], [14, Button.Left], [15, Button.Right],
];

/** Face-button markings from the Gamepad.id string (vendor id or product name). */
export function faceStyleFor(id: string): FaceStyle {
  const s = id.toLowerCase();
  if (/054c|dualsense|dualshock|playstation/.test(s)) return 'playstation';
  if (/057e|nintendo|pro controller|joy-con/.test(s)) return 'nintendo';
  if (/xbox|045e|xinput/.test(s)) return 'xbox';
  return 'generic';
}

function buttonValue(b: GamepadButton | undefined): number {
  return b ? (typeof b === 'object' ? b.value : (b as unknown as number)) : 0;
}
function buttonPressed(b: GamepadButton | undefined): boolean {
  return b ? (typeof b === 'object' ? b.pressed : (b as unknown as number) > 0.5) : false;
}

export class FuryInput {
  static readonly MaxPads = 16;
  static readonly KeyboardA = 0;
  static readonly KeyboardB = 1;
  static readonly FirstGamepad = 2;

  private static instance: FuryInput | null = null;
  static get(): FuryInput {
    if (!FuryInput.instance) FuryInput.instance = new FuryInput();
    return FuryInput.instance;
  }

  private pads: Pad[] = Array.from({ length: FuryInput.MaxPads }, () => new Pad());
  private heldKeys = new Set<string>();
  private attached: Window | null = null;
  private gestureCallbacks: (() => void)[] = [];

  constructor() {
    const a = this.pads[FuryInput.KeyboardA];
    a.kind = PadKind.Keyboard; a.connected = true; a.label = 'KEYS  WASD';
    const b = this.pads[FuryInput.KeyboardB];
    b.kind = PadKind.Keyboard; b.connected = true; b.label = 'KEYS  ARROWS';
  }

  pad(index: number): Pad { return this.pads[index]; }

  numConnectedGamepads(): number {
    let count = 0;
    for (const p of this.pads) count += p.kind === PadKind.Gamepad && p.connected ? 1 : 0;
    return count;
  }

  firstConnectedGamepad(): number {
    for (let i = FuryInput.FirstGamepad; i < FuryInput.MaxPads; ++i) {
      if (this.pads[i].kind === PadKind.Gamepad && this.pads[i].connected) return i;
    }
    return NONE;
  }

  /**
   * Called on every user gesture the browser counts for autoplay (key / pointer / touch), and on
   * gamepad presses. Use it to resume the AudioContext: audio.unlock().
   */
  onGesture(callback: () => void): void { this.gestureCallbacks.push(callback); }

  /** Hooks keyboard, focus and pointer events. Safe to call more than once. */
  attach(target: Window): void {
    if (this.attached === target) return;
    this.attached = target;
    target.addEventListener('keydown', (e) => this.onKey(e, true), { capture: true });
    target.addEventListener('keyup', (e) => this.onKey(e, false), { capture: true });
    target.addEventListener('blur', () => this.releaseKeyboard());
    target.document.addEventListener('visibilitychange', () => {
      if (target.document.visibilityState === 'hidden') this.releaseKeyboard();
    });
    const gesture = () => this.gesture();
    target.addEventListener('pointerdown', gesture, { capture: true });
    target.addEventListener('touchend', gesture, { capture: true });
  }

  private gesture(): void {
    for (const cb of this.gestureCallbacks) {
      try { cb(); } catch { /* never let a listener break input */ }
    }
  }

  private onKey(e: KeyboardEvent, down: boolean): void {
    if (down) {
      // Leave browser shortcuts (Cmd+R, Ctrl+W...) and text fields alone.
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      this.gesture();
    }
    if (!GameKeys.has(e.code)) return;
    e.preventDefault();
    if (down && e.repeat) return;
    this.handleKey(e.code, down);
  }

  /** Port of FFuryInput::HandleKey for keyboard keys (KeyboardEvent.code). Returns whether the key is bound. */
  handleKey(code: string, down: boolean): boolean {
    if (down) this.heldKeys.add(code);
    else this.heldKeys.delete(code);
    let handled = false;
    for (const binding of KeyButtons) {
      if (binding.key !== code) continue;
      const stillHeld = down || KeyButtons.some(
        (other) => other.pad === binding.pad && other.button === binding.button && this.heldKeys.has(other.key));
      this.pads[binding.pad].recordButton(binding.button, stillHeld);
      handled = true;
    }
    for (const binding of KeyDirections) {
      if (binding.key !== code) continue;
      this.pads[binding.pad].recordButton(binding.button, down);
      handled = true;
    }
    return handled;
  }

  releaseKeyboard(): void {
    this.heldKeys.clear();
    for (const i of [FuryInput.KeyboardA, FuryInput.KeyboardB]) {
      const p = this.pads[i];
      p.raw.fill(false);
      p.pendingPress.fill(false);
      p.pendingRelease.fill(false);
    }
  }

  /** Scripted input (tests, attract mode): claims a pad slot that the game treats like a device. */
  addBot(label: string): number {
    for (let i = FuryInput.FirstGamepad; i < FuryInput.MaxPads; ++i) {
      if (this.pads[i].kind === PadKind.None) {
        const p = new Pad();
        p.kind = PadKind.Bot;
        p.connected = true;
        p.label = label;
        this.pads[i] = p;
        return i;
      }
    }
    return NONE;
  }

  setBot(index: number, stick: Vec2, held: Button[]): void {
    if (index < 0 || index >= FuryInput.MaxPads || this.pads[index].kind !== PadKind.Bot) return;
    const p = this.pads[index];
    p.rawStick = stick;
    p.raw.fill(false);
    for (const b of held) p.raw[b] = true;
  }

  /**
   * Port of PadForNative: a controller keeps its slot across disconnect / reconnect. The browser may
   * hand a reconnected pad a different index, so a vacant slot of the same model is preferred.
   */
  padForNative(nativeId: number, name: string): number {
    let vacant = NONE;
    for (let i = FuryInput.FirstGamepad; i < FuryInput.MaxPads; ++i) {
      const p = this.pads[i];
      if (p.kind !== PadKind.Gamepad) continue;
      if (p.nativeId === nativeId && p.nativeName === name) return i;
      if (!p.connected && (vacant === NONE || (p.nativeName === name && this.pads[vacant].nativeName !== name))) vacant = i;
    }
    if (vacant !== NONE) {
      const p = this.pads[vacant];
      p.connected = true;
      p.nativeId = nativeId;
      p.nativeName = name;
      p.faceStyle = faceStyleFor(name);
      return vacant;
    }
    for (let i = FuryInput.FirstGamepad; i < FuryInput.MaxPads; ++i) {
      if (this.pads[i].kind === PadKind.None) {
        const p = new Pad();
        p.kind = PadKind.Gamepad;
        p.connected = true;
        p.nativeId = nativeId;
        p.nativeName = name;
        p.faceStyle = faceStyleFor(name);
        this.pads[i] = p;
        p.label = `PAD ${this.numConnectedGamepads()}`;
        return i;
      }
    }
    return NONE;
  }

  /** Port of PollNative over navigator.getGamepads(). */
  private pollGamepads(): void {
    for (let i = FuryInput.FirstGamepad; i < FuryInput.MaxPads; ++i) {
      if (this.pads[i].kind === PadKind.Gamepad) this.pads[i].seen = false;
    }
    let list: (Gamepad | null)[] = [];
    try {
      if (typeof navigator !== 'undefined' && navigator.getGamepads) list = Array.from(navigator.getGamepads());
    } catch { list = []; }
    for (const g of list) {
      if (!g || !g.connected) continue;
      const index = this.padForNative(g.index, g.id || 'Controller');
      if (index === NONE) continue;
      const p = this.pads[index];
      p.seen = true;
      p.connected = true;
      const ax = g.axes.length > 0 ? g.axes[0] : 0;
      const ay = g.axes.length > 1 ? g.axes[1] : 0;
      p.rawStick = new Vec2(Number.isFinite(ax) ? ax : 0, Number.isFinite(ay) ? -ay : 0);
      let anyNewPress = false;
      for (const [bi, button] of StandardButtons) {
        const held = buttonPressed(g.buttons[bi]);
        if (held && !p.raw[button]) anyNewPress = true;
        p.raw[button] = held;
      }
      p.raw[Button.LT] = buttonValue(g.buttons[6]) > TriggerThreshold;
      p.raw[Button.RT] = buttonValue(g.buttons[7]) > TriggerThreshold;
      if (anyNewPress) this.gesture();
    }
    // A pad that vanished releases everything; its slot stays reserved so a reconnect is painless.
    for (let i = FuryInput.FirstGamepad; i < FuryInput.MaxPads; ++i) {
      const p = this.pads[i];
      if (p.kind === PadKind.Gamepad && !p.seen && p.connected) {
        p.connected = false;
        p.rawStick = Vec2.Zero;
        p.raw.fill(false);
      }
    }
  }

  /** Called once per frame before the game logic reads the pads. */
  tick(dt: number): void {
    this.pollGamepads();

    for (const p of this.pads) {
      if (p.kind === PadKind.None) continue;
      for (let i = 0; i < ButtonCount; ++i) {
        p.pressed[i] = p.pendingPress[i] || (p.raw[i] && !p.down[i]);
        p.released[i] = p.pendingRelease[i] || (!p.raw[i] && p.down[i]);
        p.pendingPress[i] = p.pendingRelease[i] = false;
        p.down[i] = p.raw[i];
      }

      // Analog stick with a radial dead zone, plus the digital directions (d-pad / keys).
      let stick = p.rawStick;
      const size = stick.size();
      stick = size > StickDeadZone
        ? stick.div(size).mul(Math.min(1, (size - StickDeadZone) / (1 - StickDeadZone)))
        : Vec2.Zero;
      const digital = new Vec2(
        (p.down[Button.Right] ? 1 : 0) - (p.down[Button.Left] ? 1 : 0),
        (p.down[Button.Up] ? 1 : 0) - (p.down[Button.Down] ? 1 : 0));
      if (!digital.isNearlyZero()) stick = digital.safeNormal();
      p.stick = stick;

      // Menu steps with auto-repeat.
      const axis = [stick.x, stick.y];
      const tap = [
        Number(p.wasPressed(Button.Right)) - Number(p.wasPressed(Button.Left)),
        Number(p.wasPressed(Button.Up)) - Number(p.wasPressed(Button.Down)),
      ];
      const opposed = [
        p.isDown(Button.Right) && p.isDown(Button.Left),
        p.isDown(Button.Up) && p.isDown(Button.Down),
      ];
      const nav = [0, 0];
      for (let a = 0; a < 2; ++a) {
        const dir = axis[a] > NavThreshold ? 1 : axis[a] < -NavThreshold ? -1 : 0;
        nav[a] = dir === 0 && !opposed[a] ? tap[a] : 0;
        if (dir === 0) {
          p.navDir[a] = 0;
          p.navHold[a] = 0;
        } else if (dir !== p.navDir[a] || dir === tap[a]) {
          p.navDir[a] = dir;
          p.navHold[a] = NavFirstRepeat;
          nav[a] = dir;
        } else {
          p.navHold[a] -= dt;
          if (p.navHold[a] <= 0) {
            p.navHold[a] = NavRepeat;
            nav[a] = dir;
          }
        }
      }
      p.navX = nav[0];
      p.navY = nav[1];
    }
  }
}
