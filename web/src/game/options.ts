/**
 * Player settings: graphics, sound and accessibility (port of FFuryOptions / FFuryAutoScale,
 * FuryOptions.cpp). Values are small integers per row; the settings screen steps them with
 * adjust(). Saved to localStorage instead of GameUserSettings.ini.
 *
 * Web differences:
 *  - Render scale is a percentage of the canvas's device pixels (CSS size x devicePixelRatio).
 *    Auto picks 108000 / device-pixel height, clamped to 50..100, like the C++ (1080p native).
 *  - VSync stays in the enum (so indices match the C++) but is not shown: browsers always sync.
 *  - Frame limit "Unlimited" means the display's refresh rate (requestAnimationFrame), and it is
 *    the default, because skipping vsyncs to hit a 144 cap judders on faster displays.
 *  - AutoScale samples frame time (see AutoScale.sampleFrame) because WebGL has no portable GPU timer.
 */
import { NONE } from '../sim/core';

export enum Option {
  Preset, RenderScale, Lighting, Antialiasing, Textures, Crowd, Effects,
  FrameLimit, VSync, ShowFPS, ReducedMotion, Master, Music, Announcer, Field, Ambience, Interface, Captions, Count,
}

interface OptionInfo { key: string; label: string; hint: string; max: number }

const Info: OptionInfo[] = [
  { key: 'Preset', label: 'Quality preset', hint: 'Change the field, lighting and stadium detail together.', max: 3 },
  { key: 'RenderScale', label: 'Render scale', hint: 'Auto aims for 120 FPS or your lower cap. Fixed scales are a share of your display’s pixels.', max: 6 },
  { key: 'Lighting', label: 'Stadium lighting', hint: 'Add floodlight shadows and, on Ultra, illuminated haze.', max: 3 },
  { key: 'Antialiasing', label: 'Anti-aliasing', hint: 'Smooth helmet edges, bleachers and distant yard lines.', max: 3 },
  { key: 'Textures', label: 'Texture detail', hint: 'Keep turf and uniform textures sharper at a distance.', max: 3 },
  { key: 'Crowd', label: 'Crowd density', hint: 'Choose how many spectators fill the stands.', max: 3 },
  { key: 'Effects', label: 'Particle effects', hint: 'Set the number of sparks, impact particles and fireworks.', max: 3 },
  { key: 'FrameLimit', label: 'Frame-rate limit', hint: 'Cap the frame rate below your display’s refresh rate to save power.', max: 5 },
  { key: 'VSync', label: 'Vertical sync', hint: 'Synchronize frame presentation with your display.', max: 1 },
  { key: 'ShowFPS', label: 'Match FPS display', hint: 'Keep the live frame rate and frame time visible during play.', max: 1 },
  { key: 'ReducedMotion', label: 'Reduced motion', hint: 'Steady menu camera. Disable impact shake and stadium flashes.', max: 1 },
  { key: 'Master', label: 'Master volume', hint: 'Adjust the entire mix, including menus and previews.', max: 20 },
  { key: 'Music', label: 'Music', hint: 'Adjust the theme, play selection and victory music.', max: 20 },
  { key: 'Announcer', label: 'Announcer', hint: 'Adjust commentary and stadium announcements.', max: 20 },
  { key: 'Field', label: 'Field effects', hint: 'Adjust tackles, whistles, cleats and ball sounds.', max: 20 },
  { key: 'Ambience', label: 'Crowd and stadium', hint: 'Adjust crowd beds, chants, cheers and night ambience.', max: 20 },
  { key: 'Interface', label: 'Menu sounds', hint: 'Adjust feedback while navigating and choosing options.', max: 20 },
  { key: 'Captions', label: 'Announcer captions', hint: 'Show the announcer’s words, even when the sound is muted.', max: 1 },
];

export const PresetNames = ['Performance', 'Balanced', 'High', 'Ultra'];
export const Levels = ['Low', 'Medium', 'High', 'Ultra'];
/** Web anti-aliasing levels: see Options.antialiasing() for what each means to the renderer. */
export const AntiAliasingNames = ['Off', 'FXAA', 'MSAA 4×', 'MSAA 8×'];
const Percents = [0, 60, 75, 85, 100, 125, 150];
const FrameCaps = [30, 60, 90, 120, 144, 0];
// Render scale, lighting, anti-aliasing, textures, crowd, effects.
const Presets = [[2, 0, 1, 1, 0, 0], [0, 1, 3, 2, 3, 2], [4, 2, 3, 3, 3, 2], [6, 3, 3, 3, 3, 3]];
const StorageKey = 'FourthAndFury.Options';

const GraphicsRowsWeb: Option[] = [
  Option.Preset, Option.RenderScale, Option.Lighting, Option.Antialiasing, Option.Textures, Option.Crowd,
  Option.Effects, Option.FrameLimit, Option.ShowFPS, Option.ReducedMotion,
];
const SoundRowsWeb: Option[] = [
  Option.Master, Option.Music, Option.Announcer, Option.Field, Option.Ambience, Option.Interface, Option.Captions,
];

export class Options {
  static readonly Count = Option.Count as number;
  static readonly GraphicsRows = Option.Master as number;
  static readonly SoundRows = Options.Count - Options.GraphicsRows;
  static readonly ChannelCount = (Option.Captions as number) - Options.GraphicsRows;
  static isChannel(id: Option): boolean { return id >= Option.Master && id <= Option.Interface; }

  /** The rows the web settings screen shows, in order (VSync is dropped). Index with settingsRow. */
  static rows(soundTab: boolean): Option[] { return soundTab ? SoundRowsWeb : GraphicsRowsWeb; }

  private values: number[] = new Array(Options.Count).fill(0);
  private mutedChannels = 0;

  constructor() {
    this.reset(false);
    this.reset(true);
  }

  get(id: Option): number { return this.values[id]; }
  static label(id: Option): string { return Info[id].label; }
  static hint(id: Option): string { return Info[id].hint; }
  static max(id: Option): number { return Info[id].max; }

  private setPreset(index: number): void {
    this.values[Option.Preset] = index;
    for (let i = 0; i < Presets[0].length; ++i) this.values[Option.RenderScale + i] = Presets[index][i];
  }

  private matchingPreset(): number {
    for (let i = 0; i < Presets.length; ++i) {
      if (Presets[i].every((v, j) => this.values[Option.RenderScale + j] === v)) return i;
    }
    return NONE;
  }

  reset(sound: boolean): void {
    if (sound) {
      this.mutedChannels = 0;
      for (let i = Options.GraphicsRows; i < Options.GraphicsRows + Options.ChannelCount; ++i) this.values[i] = Info[i].max;
      this.values[Option.Captions] = 0;
      return;
    }
    this.setPreset(1);
    this.values[Option.FrameLimit] = 5;   // C++: 4 (144 FPS). The browser default is the display rate.
    this.values[Option.VSync] = 0;
    this.values[Option.ShowFPS] = 0;
    this.values[Option.ReducedMotion] = 0;
  }

  /** Steps a row. Returns whether anything changed (the caller then applies and saves). */
  adjust(id: Option, step: number): boolean {
    if (id === Option.Preset) {
      const current = this.matchingPreset();
      const base = current === NONE ? this.get(Option.Preset) : current;
      const next = Math.min(Math.max(base + step, 0), 3);
      if (next === current) return false;
      this.setPreset(next);
      return true;
    }
    const next = Math.min(Math.max(this.values[id] + step, 0), Info[id].max);
    if (Options.isChannel(id) && this.muted(id)) this.toggleMute(id);
    else if (next === this.values[id]) return false;
    this.values[id] = next;
    return true;
  }

  muted(channel: Option): boolean {
    return Options.isChannel(channel) && (this.mutedChannels & (1 << (channel - Options.GraphicsRows))) !== 0;
  }

  toggleMute(channel: Option): void {
    if (Options.isChannel(channel)) this.mutedChannels ^= 1 << (channel - Options.GraphicsRows);
  }

  /** 0..1 for a sound channel (0 when muted). */
  volume(channel: Option): number {
    return this.muted(channel) ? 0 : this.get(channel) / 20;
  }

  display(id: Option): string {
    const value = this.get(id);
    switch (id) {
      case Option.Preset: { const m = this.matchingPreset(); return m === NONE ? 'Custom' : PresetNames[m]; }
      case Option.RenderScale: return value ? `${Percents[value]}%` : 'Auto';
      case Option.Antialiasing: return AntiAliasingNames[value];
      case Option.FrameLimit: return this.frameCap() ? `${this.frameCap()} FPS` : 'Unlimited';
      case Option.VSync: case Option.ShowFPS: case Option.ReducedMotion: case Option.Captions: return value ? 'On' : 'Off';
      case Option.Crowd: return `${(value + 1) * 25}%`;
      case Option.Lighting: case Option.Textures: case Option.Effects: return Levels[value];
      default: return this.muted(id) ? 'Muted' : `${value * 5}%`;
    }
  }

  /** Frames per second to cap at; 0 = the display's refresh rate. */
  frameCap(): number { return FrameCaps[this.get(Option.FrameLimit)]; }

  /**
   * Render percentage of the canvas's device pixels. `height` is the canvas height in device
   * pixels (CSS height x devicePixelRatio). Renderer pixel ratio = devicePixelRatio * percent / 100.
   */
  screenPercent(height: number): number {
    const fixed = Percents[this.get(Option.RenderScale)];
    return fixed ? fixed : Math.min(Math.max(108000 / Math.max(height, 1), 50), 100);
  }

  /** 0..1 overall visual quality, for the HUD's twelve-bar meter. */
  detail(effectivePercent: number): number {
    let sum = Math.min(Math.max((effectivePercent - 50) / 100, 0), 1) * 3;
    for (let i = Option.Lighting; i <= Option.Effects; ++i) sum += this.values[i] / 3;
    return sum / 8;
  }

  // --- What ApplyGraphics did with the values (FuryDirectorOptions.cpp), as numbers for the renderer ---
  /** Anti-aliasing for the renderer: MSAA sample count for the scene target, and an FXAA pass. */
  antialiasing(): { msaa: number; fxaa: boolean } {
    return [{ msaa: 0, fxaa: false }, { msaa: 0, fxaa: true }, { msaa: 4, fxaa: false }, { msaa: 8, fxaa: false }][this.get(Option.Antialiasing)];
  }
  /** Texture anisotropy (r.MaxAnisotropy); clamp to renderer.capabilities.getMaxAnisotropy(). */
  anisotropy(): number { return [1, 4, 8, 16][this.get(Option.Textures)]; }
  /** Mip LOD bias (r.MipMapLODBias). */
  mipBias(): number { return [1, 0.5, 0, -0.5][this.get(Option.Textures)]; }
  /** Fraction of the spectators drawn (foliage.DensityScale). */
  crowdDensity(): number { return 0.25 * (this.get(Option.Crowd) + 1); }
  /** Particle count multiplier (Effects.ParticleDensity). */
  particleDensity(): number { return [0.35, 0.65, 1, 1.5][this.get(Option.Effects)]; }

  load(): void {
    let data: Record<string, unknown> | null = null;
    try {
      const text = globalThis.localStorage?.getItem(StorageKey);
      if (text) data = JSON.parse(text) as Record<string, unknown>;
    } catch { data = null; }
    if (!data || typeof data !== 'object') return;
    const muted = data['MutedChannels'];
    if (typeof muted === 'number' && Number.isFinite(muted)) this.mutedChannels = (muted | 0) & ((1 << Options.ChannelCount) - 1);
    for (let i = 0; i < Options.Count; ++i) {
      const v = data[Info[i].key];
      if (typeof v === 'number' && Number.isFinite(v)) this.values[i] = Math.min(Math.max(Math.trunc(v), 0), Info[i].max);
    }
  }

  save(): void {
    const data: Record<string, number> = { MutedChannels: this.mutedChannels };
    for (let i = 0; i < Options.Count; ++i) data[Info[i].key] = this.values[i];
    try { globalThis.localStorage?.setItem(StorageKey, JSON.stringify(data)); } catch { /* private mode, quota */ }
  }
}

/**
 * Adjusts the field render scale from measured cost (port of FFuryAutoScale). The HUD stays native.
 *
 * sample() is the C++ controller unchanged: feed it a per-frame cost in ms (GPU time from
 * EXT_disjoint_timer_query_webgl2 when the renderer has it). sampleFrame() is the web fallback that
 * feeds it the requestAnimationFrame interval instead.
 *
 * Director usage (only while a play is live, unpaused, and Render scale is Auto, like the C++):
 *   const cap = options.frameCap();
 *   const budgetMs = 1000 / (cap > 0 ? Math.min(cap, 120) : 120);
 *   renderPercent = autoScale.sampleFrame(dt, budgetMs, renderPercent, options.screenPercent(heightPx));
 * Call reset() when the canvas size or the options change.
 */
export class AutoScale {
  private window = 0;
  private totalMs = 0;
  private headroom = 0;
  private count = 0;
  // sampleFrame state
  private refreshMs = 0;
  private refreshProbe = Infinity;
  private refreshProbeTime = 0;
  private metFor = 0;
  private blockedAbove = Infinity;
  private blockedFor = 0;

  reset(): void {
    this.window = this.totalMs = this.headroom = 0;
    this.count = 0;
    this.metFor = 0;
    this.blockedAbove = Infinity;
    this.blockedFor = 0;
  }

  /** Port of FFuryAutoScale::Sample. Returns the new render percentage. */
  sample(dt: number, costMs: number, budgetMs: number, current: number, ceiling: number): number {
    if (dt <= 0 || dt > 0.15 || costMs <= 0 || costMs > 100) return current;
    this.window += dt;
    this.totalMs += costMs;
    ++this.count;
    if (this.window < 0.65) return current;
    const cost = this.totalMs / this.count;
    this.headroom = cost < budgetMs * 0.76 ? this.headroom + this.window : 0;
    this.window = this.totalMs = 0;
    this.count = 0;
    const floor = Math.min(ceiling, Math.max(50, ceiling * 0.62));
    if (cost > budgetMs * 1.03) {
      const wanted = current * Math.sqrt((budgetMs * 0.95) / cost);
      return Math.min(Math.max(Math.round(wanted), Math.max(floor, current - 10)), current);
    }
    if (this.headroom >= 2.4) {
      this.headroom = 0;
      return Math.min(ceiling, current + 3);
    }
    return current;
  }

  /**
   * Web fallback: the cost is the frame interval. Frames quantize to the display's refresh, so
   * the budget can never be shorter than one refresh, and spare time is invisible: instead of the
   * C++ "under 76% of budget for 2.4 s" rule, the scale steps up after 8 s of meeting the budget,
   * and a step that immediately misses blocks that level for 30 s so it does not oscillate.
   */
  sampleFrame(dt: number, budgetMs: number, current: number, ceiling: number): number {
    if (dt <= 0 || dt > 0.15) return current;
    const ms = dt * 1000;
    // Refresh period: the shortest interval seen over each 2 s window.
    this.refreshProbe = Math.min(this.refreshProbe, ms);
    this.refreshProbeTime += dt;
    if (this.refreshProbeTime >= 2) {
      this.refreshMs = this.refreshMs > 0 ? Math.min(this.refreshProbe, this.refreshMs * 0.8 + this.refreshProbe * 0.2) : this.refreshProbe;
      this.refreshProbe = Infinity;
      this.refreshProbeTime = 0;
    }
    const budget = Math.max(budgetMs, this.refreshMs * 1.02);
    if (this.blockedFor > 0) {
      this.blockedFor -= dt;
      if (this.blockedFor <= 0) this.blockedAbove = Infinity;
    }
    const before = this.window;
    const next = this.sample(dt, ms, budget, current, ceiling);
    if (this.window >= before) return next;   // window still filling
    // A window just closed.
    if (next < current) {
      this.metFor = 0;
      this.blockedAbove = Math.min(this.blockedAbove, current);
      this.blockedFor = 30;
      return next;
    }
    if (next > current) { this.metFor = 0; return next < this.blockedAbove ? next : current; }
    this.metFor += before + dt;
    if (this.metFor >= 8) {
      this.metFor = 0;
      const up = Math.min(ceiling, current + 3);
      if (up < this.blockedAbove) return up;
    }
    return current;
  }
}
