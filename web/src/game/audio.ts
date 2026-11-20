/**
 * Everything you hear (port of UFuryAudio, FuryAudio.cpp): one-shot effects, the crowd (two beds
 * cross-faded by how exciting things are), looping music, and the stadium announcer, who only says
 * one thing at a time.
 *
 * Web Audio graph: every clip -> its own GainNode -> channel GainNode (Music, Announcer, Field,
 * Ambience, Interface; the C++ sound classes) -> Master GainNode -> destination.
 *
 * Sounds are looked up by name under assets/audio/<Name>.mp3 and decoded lazily, so the game runs
 * (silently) before the audio exists. A missing file is looked for once and then remembered as
 * missing. assets/audio/manifest.json, when present, lists the files (only those are fetched), the
 * looping flags, durations and the announcer's words; without it the C++ name prefixes decide the
 * channel and the tables below supply loops and captions.
 *
 * Browsers start the AudioContext suspended until a user gesture: call unlock() from the first
 * keydown / pointerdown / gamepad press (FuryInput.onGesture). While suspended, one-shot effects are
 * skipped (they would all fire at once on resume), loops and music are started so they begin on
 * unlock, and announcer lines still show their captions.
 */
import { RandomStream } from '../sim/core';
import { Option, Options } from './options';

/** The announcer's words from Content/Data/audio_manifest.json, used when the web manifest has no text. */
const DefaultCaptions: Record<string, string> = {
  VO_Title: "Fourth and Fury!",
  VO_Welcome_1: "Welcome, football fans, to Fourth and Fury!",
  VO_Welcome_2: "It's game night under the lights!",
  VO_Team_sasquatch: "The Portland Sasquatch!",
  VO_Team_volcanoes: "The Honolulu Volcanoes!",
  VO_Team_icebreakers: "The Anchorage Icebreakers!",
  VO_Team_hellhounds: "The Memphis Hellhounds!",
  VO_Team_twisters: "The Omaha Twisters!",
  VO_Team_amps: "The Austin Amps!",
  VO_Team_scorpions: "The Tucson Scorpions!",
  VO_Team_gargoyles: "The Brooklyn Gargoyles!",
  VO_Kickoff_1: "Get ready for the kickoff!",
  VO_Kickoff_2: "The ball is on the tee. Here we go!",
  VO_Touchdown_1: "Touchdown!",
  VO_Touchdown_2: "He's in! Touchdown!",
  VO_Touchdown_3: "Six points on the board!",
  VO_Touchdown_4: "Into the end zone! Touchdown!",
  VO_FirstDown_1: "First down!",
  VO_FirstDown_2: "The chains are moving!",
  VO_FirstDown_3: "That's a fresh set of downs!",
  VO_Sack_1: "That's a sack!",
  VO_Sack_2: "The quarterback goes down!",
  VO_Sack_3: "Nowhere to hide! He's down!",
  VO_Interception_1: "Intercepted!",
  VO_Interception_2: "Picked off!",
  VO_Interception_3: "Stolen out of the sky!",
  VO_Fumble_1: "Fumble!",
  VO_Fumble_2: "The football is loose!",
  VO_BigHit_1: "What a hit!",
  VO_BigHit_2: "He got flattened!",
  VO_BigHit_3: "That hit shook the stadium!",
  VO_BigHit_4: "Check the field for a crater!",
  VO_Incomplete_1: "Incomplete!",
  VO_Incomplete_2: "He couldn't hang on!",
  VO_Incomplete_3: "Off the fingertips. Incomplete!",
  VO_BigGain_1: "Big gain on the play!",
  VO_BigGain_2: "He breaks loose!",
  VO_BigGain_3: "That's a huge pickup!",
  VO_Fury_1: "Fury mode!",
  VO_Fury_2: "The fury is unleashed!",
  VO_Fury_3: "They are unstoppable!",
  VO_Turnover: "Turnover on downs!",
  VO_Safety: "Safety! Two points!",
  VO_FieldGoalGood: "The kick is good!",
  VO_FieldGoalNoGood: "No good! The kick is wide!",
  VO_ExtraPointGood: "The extra point is good!",
  VO_TwoPointGood: "The two point try is good!",
  VO_TwoPointNoGood: "Two point try, no good!",
  VO_Punt: "They're punting it away!",
  VO_Quarter2: "Second quarter!",
  VO_Quarter3: "Third quarter!",
  VO_Quarter4: "Fourth quarter! This is it!",
  VO_Halftime: "That's the half!",
  VO_TwoMinute: "The clock is running out! Now or never!",
  VO_Overtime: "We're going to overtime!",
  VO_Final_1: "That's the game!",
  VO_Final_2: "Final whistle! It's all over!",
  VO_Win_Home: "Victory for the home team!",
  VO_Win_Away: "The visitors take the win!",
};

/** Looping assets per Content/Data/audio_manifest.json ("loops": true). */
const DefaultLoops = new Set([
  'SFX_BallAir', 'SFX_Steps', 'SFX_FuryLoop', 'AMB_CrowdLow', 'AMB_CrowdHigh', 'AMB_Chant', 'AMB_Night',
  'MUS_Menu', 'MUS_PlaySelect', 'MUS_Halftime',
]);

const FirstChannel = Option.Music;
const LastChannel = Option.Interface;

function channelFor(name: string): Option {
  if (name.startsWith('MUS_')) return Option.Music;
  if (name.startsWith('VO_')) return Option.Announcer;
  if (name.startsWith('AMB_')) return Option.Ambience;
  if (name.startsWith('SFX_UI')) return Option.Interface;
  return Option.Field;
}

/** FMath::FInterpConstantTo. */
function interpConstantTo(current: number, target: number, dt: number, speed: number): number {
  const dist = target - current;
  if (dist * dist < 1e-8) return target;
  const step = speed * dt;
  return current + Math.min(Math.max(dist, -step), step);
}

interface ManifestEntry { name: string; file: string; text?: string; loops?: boolean; duration?: number }

/** Plays one buffer through its own gain (the UAudioComponent). A stopped clip can play again. */
class Clip {
  private source: AudioBufferSourceNode | null = null;
  private readonly gain: GainNode;
  private playing = false;
  private fading = false;
  volume: number;
  pitch: number;

  constructor(
    private readonly ctx: AudioContext,
    private readonly buffer: AudioBuffer,
    out: AudioNode,
    volume: number,
    pitch: number,
    private readonly loop: boolean,
    private readonly loopEnd: number,
    private readonly autoDestroy: boolean,
  ) {
    this.volume = volume;
    this.pitch = pitch;
    this.gain = ctx.createGain();
    this.gain.gain.value = volume;
    this.gain.connect(out);
  }

  play(): void {
    this.stopSource();
    if (this.fading) {
      this.fading = false;
      this.gain.gain.cancelScheduledValues(this.ctx.currentTime);
      this.gain.gain.value = this.volume;
    }
    const s = this.ctx.createBufferSource();
    s.buffer = this.buffer;
    s.loop = this.loop;
    if (this.loop && this.loopEnd > 0) { s.loopStart = 0; s.loopEnd = this.loopEnd; }
    s.playbackRate.value = this.pitch;
    s.connect(this.gain);
    s.onended = () => {
      if (this.source !== s) return;
      this.source = null;
      this.playing = false;
      if (this.autoDestroy) this.gain.disconnect();
    };
    this.source = s;
    this.playing = true;
    s.start();
  }

  private stopSource(): void {
    const s = this.source;
    this.source = null;
    this.playing = false;
    if (s) {
      s.onended = null;
      try { s.stop(); } catch { /* never started */ }
      s.disconnect();
    }
  }

  stop(): void {
    this.stopSource();
    if (this.autoDestroy) this.gain.disconnect();
  }

  isPlaying(): boolean { return this.playing; }

  setVolume(v: number): void {
    if (v === this.volume && !this.fading) return;
    this.volume = v;
    this.fading = false;
    const p = this.gain.gain, now = this.ctx.currentTime;
    p.cancelScheduledValues(now);
    // A short glide instead of a per-frame step, so slow fades do not zipper.
    p.setTargetAtTime(v, now, 0.015);
  }

  setPitch(pitch: number): void {
    this.pitch = pitch;
    if (this.source) this.source.playbackRate.value = pitch;
  }

  /** UAudioComponent::FadeOut(Seconds, 0): ramp to silence, then stop. */
  fadeOut(seconds: number): void {
    const p = this.gain.gain, now = this.ctx.currentTime;
    this.fading = true;
    p.cancelScheduledValues(now);
    p.setValueAtTime(this.volume, now);
    p.linearRampToValueAtTime(0, now + seconds);
    const s = this.source;
    if (s) { try { s.stop(now + seconds); } catch { /* already stopped */ } }
  }
}

export class FuryAudio {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private channels = new Map<Option, GainNode>();
  private previewClip: Clip | null = null;

  private manifest: Map<string, ManifestEntry> | null = null;
  private buffers = new Map<string, AudioBuffer | null>();
  private loading = new Map<string, Promise<AudioBuffer | null>>();
  private base = '/';

  private loops = new Map<string, Clip>();
  private pendingLoops = new Map<string, { volume: number; pitch: number }>();
  private voice: Clip | null = null;
  private musicNow: Clip | null = null;
  private musicOld: Clip | null = null;
  private musicPending = false;

  private loopTarget = new Map<string, number>();
  private loopNow = new Map<string, number>();
  private musicName = '';
  private musicVolume = 0.6;
  private previousMusicGain = 0;
  private musicFade = 1;
  private announcerGain = 1;
  private bedGain = 1;
  private musicPreview = false;
  private musicBedGain = 1;
  private crowdLevel = 0.2;
  private voiceCooldown = 0;
  private voiceText = new Map<string, string>(Object.entries(DefaultCaptions));
  private activeCaption = '';
  private captionTime = 0;
  private crowd = true;
  private anySound = false;
  private random = new RandomStream(977);

  /** Creates the audio graph, reads the manifest and starts preloading effects and voice lines. */
  async init(options: Options): Promise<void> {
    this.random.initialize(977);
    try {
      const env = (import.meta as unknown as { env?: { BASE_URL?: string } }).env;
      this.base = env?.BASE_URL ?? '/';
    } catch { this.base = '/'; }
    try {
      const Ctor: typeof AudioContext | undefined =
        globalThis.AudioContext ?? (globalThis as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (Ctor) {
        this.ctx = new Ctor({ latencyHint: 'interactive' });
        this.master = this.ctx.createGain();
        this.master.connect(this.ctx.destination);
        for (let c = FirstChannel; c <= LastChannel; ++c) {
          const g = this.ctx.createGain();
          g.connect(this.master);
          this.channels.set(c, g);
        }
      }
    } catch {
      this.ctx = null;
      this.master = null;
      this.channels.clear();
    }
    this.updateMix(options, 0);

    await this.readManifest();
    if (!this.ctx || !this.manifest) return;
    // First-use decodes during tackles and catches would drop the sound: fetch everything except
    // the music up front (music is decoded when first asked for).
    const names = [...this.manifest.keys()];
    const first = names.filter((n) => !n.startsWith('MUS_')).map((n) => this.load(n));
    // Then the music, one track at a time, so the settings preview and the next screen have it ready.
    void Promise.allSettled(first).then(async () => {
      for (const n of names) if (n.startsWith('MUS_')) await this.load(n);
    });
  }

  private async readManifest(): Promise<void> {
    let data: unknown;
    try {
      const response = await fetch(`${this.base}assets/audio/manifest.json`);
      if (!response.ok) return;
      data = await response.json();
    } catch { return; }
    const list: unknown[] = Array.isArray(data) ? data
      : data && typeof data === 'object' && Array.isArray((data as { files?: unknown }).files) ? (data as { files: unknown[] }).files
      : data && typeof data === 'object' ? Object.entries(data as Record<string, unknown>).map(([k, v]) => (v && typeof v === 'object' ? { name: k, ...(v as object) } : null))
      : [];
    const map = new Map<string, ManifestEntry>();
    for (const raw of list) {
      if (!raw || typeof raw !== 'object') continue;
      const e = raw as Record<string, unknown>;
      const fileField = typeof e.file === 'string' ? e.file : typeof e.path === 'string' ? e.path : '';
      const fromFile = fileField.split('/').pop()?.replace(/\.[^.]+$/, '') ?? '';
      const name = typeof e.name === 'string' ? e.name : fromFile;
      if (!name) continue;
      const file = /\.(mp3|ogg|opus|m4a|aac|webm|wav|flac)$/i.test(fileField) ? fileField.split('/').pop()! : `${name}.mp3`;
      const loops = typeof e.loops === 'boolean' ? e.loops : typeof e.loop === 'boolean' ? e.loop : undefined;
      const entry: ManifestEntry = {
        name, file,
        text: typeof e.text === 'string' ? e.text : undefined,
        loops,
        duration: typeof e.duration === 'number' ? e.duration : undefined,
      };
      map.set(name, entry);
      if (entry.text && name.startsWith('VO_')) this.voiceText.set(name, entry.text);
    }
    if (map.size === 0) return;
    this.manifest = map;
    if (map.has('AMB_CrowdLow') || map.has('SFX_Whistle')) this.anySound = true;
  }

  private load(name: string): Promise<AudioBuffer | null> {
    const pending = this.loading.get(name);
    if (pending) return pending;
    const ctx = this.ctx;
    const entry = this.manifest?.get(name);
    if (!ctx || (this.manifest && !entry)) {
      this.buffers.set(name, null);
      return Promise.resolve(null);
    }
    const url = `${this.base}assets/audio/${entry ? entry.file : `${name}.mp3`}`;
    const promise = (async (): Promise<AudioBuffer | null> => {
      try {
        const response = await fetch(url);
        if (!response.ok) return null;
        const bytes = await response.arrayBuffer();
        return await new Promise<AudioBuffer>((resolve, reject) => {
          const result = ctx.decodeAudioData(bytes, resolve, reject);
          if (result && typeof result.then === 'function') result.then(resolve, reject);
        });
      } catch {
        return null;   // missing or undecodable (e.g. the dev server's index.html fallback)
      }
    })().then((buffer) => {
      this.buffers.set(name, buffer);   // remember misses too, so a missing file is only looked for once
      if (buffer && (name === 'AMB_CrowdLow' || name === 'SFX_Whistle')) this.anySound = true;
      return buffer;
    });
    this.loading.set(name, promise);
    return promise;
  }

  /** The decoded sound, or null if missing or still loading (loading starts on first request). */
  private find(name: string): AudioBuffer | null {
    const b = this.buffers.get(name);
    if (b !== undefined) return b;
    void this.load(name);
    return null;
  }

  /** Still being fetched or decoded: known to exist (manifest) or not yet known missing. */
  private isLoading(name: string): boolean {
    return !this.buffers.has(name) && this.loading.has(name);
  }

  private isLoop(name: string): boolean {
    const entry = this.manifest?.get(name);
    return entry?.loops ?? DefaultLoops.has(name);
  }

  private running(): boolean { return !!this.ctx && this.ctx.state === 'running'; }

  private startClip(name: string, buffer: AudioBuffer | null, volume: number, pitch: number, autoDestroy: boolean): Clip | null {
    const ctx = this.ctx;
    if (!buffer || !ctx) return null;
    const out = this.channels.get(channelFor(name));
    if (!out) return null;
    const loop = this.isLoop(name);
    // MP3 frames pad the end of a file; loop at the source length when the manifest knows it.
    const length = this.manifest?.get(name)?.duration ?? 0;
    const excess = buffer.duration - length;
    const loopEnd = loop && length > 0 && excess > 0.005 && excess < 0.15 ? length : 0;
    try {
      const clip = new Clip(ctx, buffer, out, volume, pitch, loop, loopEnd, autoDestroy);
      clip.play();
      return clip;
    } catch {
      return null;
    }
  }

  /** Resumes the AudioContext; call from a user gesture (keydown, pointerdown, gamepad press). */
  unlock(): void {
    const ctx = this.ctx;
    if (!ctx || ctx.state === 'running' || ctx.state === 'closed') return;
    try { void ctx.resume().catch(() => undefined); } catch { /* not allowed yet */ }
  }

  private ramp(node: GainNode | null | undefined, target: number, fadeTime: number): void {
    if (!node || !this.ctx) return;
    const p = node.gain, now = this.ctx.currentTime;
    p.cancelScheduledValues(now);
    if (fadeTime > 0) {
      p.setValueAtTime(p.value, now);
      p.linearRampToValueAtTime(target, now + fadeTime);
    } else {
      p.setValueAtTime(target, now);
      p.value = target;
    }
  }

  updateMix(options: Options, fadeTime = 0.04): void {
    const master = options.volume(Option.Master);
    this.announcerGain = master * options.volume(Option.Announcer);
    this.ramp(this.master, master, fadeTime);
    for (let c = FirstChannel; c <= LastChannel; ++c) this.ramp(this.channels.get(c), options.volume(c), fadeTime);
  }

  stopPreview(): void {
    this.previewClip?.stop();
    this.previewClip = null;
    this.musicPreview = false;
  }

  /** A sample of one channel for the sound settings (A on a volume row). */
  preview(channel: Option): void {
    this.stopPreview();
    let sample = 'SFX_Whistle';
    switch (channel) {
      case Option.Music: sample = 'MUS_Victory'; break;
      case Option.Announcer: sample = 'VO_FirstDown_1'; break;
      case Option.Ambience: sample = 'AMB_Cheer_1'; break;
      case Option.Interface: sample = 'SFX_UIReady'; break;
      case Option.Field: sample = 'SFX_BigHit_1'; break;
      default: break;
    }
    this.musicPreview = channel === Option.Music;
    this.previewClip = this.startClip(sample, this.find(sample), channel === Option.Music ? 0.6 : 1, 1, true);
    if (this.previewClip && channel === Option.Music) this.previewClip.fadeOut(3);
  }

  shutdown(): void {
    this.stopPreview();
    try { void this.ctx?.close(); } catch { /* already closed */ }
  }

  play(name: string, volume = 1, pitch = 1): void {
    const sound = this.find(name);
    if (sound && this.running()) this.startClip(name, sound, volume, pitch, true);
  }

  /** Picks one of name_1 .. name_count at random, with a little pitch variation. */
  playOneOf(name: string, count: number, volume = 1, pitchSpread = 0.06): void {
    const pick = `${name}_${this.random.randRange(1, Math.max(count, 1))}`;
    const sound = this.find(pick);
    const pitch = 1 + this.random.fRandRange(-pitchSpread, pitchSpread);
    if (sound && this.running()) this.startClip(pick, sound, volume, pitch, true);
  }

  /** Announcer line. A line already playing is not interrupted unless urgent. */
  say(name: string, urgent = false): void {
    const sound = this.find(name);
    // A line still decoding keeps its caption and timing (the C++ keeps them in sync with a muted device).
    const duration = sound ? sound.duration : this.isLoading(name) ? this.manifest?.get(name)?.duration : undefined;
    if (duration === undefined) return;
    const busy = (this.voice !== null && this.voice.isPlaying()) || this.voiceCooldown > 0;
    if (busy && !urgent) return;
    this.voice?.stop();
    this.voice = sound && this.running() ? this.startClip(name, sound, 1, 1, true) : null;
    this.activeCaption = this.voiceText.get(name) ?? '';
    this.voiceCooldown = Math.max(0.6, duration);
    this.captionTime = Math.max(1.45, this.voiceCooldown + 0.18);
  }

  sayOneOf(name: string, count: number, urgent = false): void {
    this.say(`${name}_${this.random.randRange(1, Math.max(count, 1))}`, urgent);
  }

  private loop(name: string, volume: number): Clip | null {
    const found = this.loops.get(name);
    if (found) return found;
    const sound = this.find(name);
    if (!sound) return null;
    const clip = this.startClip(name, sound, Math.max(volume, 0.001), 1, false);
    if (clip) this.loops.set(name, clip);
    return clip;
  }

  /** A looping sound that fades in and out as it is switched on and off. */
  setLoop(name: string, on: boolean, volume = 0.6, pitch = 1): void {
    if (!on) this.pendingLoops.delete(name);
    if (!on && !this.loops.has(name)) return;   // never started: nothing to fade out
    const clip = this.loop(name, 0.001);
    if (!clip) {
      // Still decoding: start it from tick() once it arrives.
      if (on && this.isLoading(name)) this.pendingLoops.set(name, { volume, pitch });
      return;
    }
    this.loopTarget.set(name, on ? volume : 0);
    if (!this.loopNow.has(name)) this.loopNow.set(name, 0);
    if (on && Math.abs(clip.pitch - pitch) > 0.01) clip.setPitch(pitch);
    if (on && !clip.isPlaying()) clip.play();
  }

  fadeFieldLoops(): void {
    this.setLoop('SFX_FuryLoop', false);
    this.setLoop('SFX_BallAir', false);
    this.setLoop('AMB_Chant', false);
  }

  /** Switches the looping music (empty name = silence), cross-fading. */
  music(name: string, volume = 0.6): void {
    if (name === this.musicName) {
      this.musicVolume = volume;
      return;
    }
    this.previousMusicGain = this.musicVolume * this.musicFade;
    this.musicVolume = volume;
    this.musicName = name;
    this.musicOld?.stop();
    this.musicOld = this.musicNow;
    this.musicNow = null;
    this.musicFade = 0;
    this.musicPending = false;
    if (name) {
      const sound = this.find(name);
      if (sound) this.musicNow = this.startClip(name, sound, 0.001, 1, true);
      else this.musicPending = this.isLoading(name);
    }
  }

  setCrowd(on: boolean): void { this.crowd = on; }
  /** The announcer's current words ('' when quiet); the HUD shows them when captions are on. */
  caption(): string { return this.activeCaption; }
  hasSounds(): boolean { return this.anySound; }

  tick(dt: number, excitement: number): void {
    this.voiceCooldown = Math.max(0, this.voiceCooldown - dt);
    if (this.captionTime > 0) {
      this.captionTime -= dt;
      if (this.captionTime <= 0) this.activeCaption = '';
    }
    if (!this.ctx) return;

    // Sounds that were still decoding when asked for.
    if (this.musicPending && !this.musicNow) {
      const sound = this.find(this.musicName);
      if (sound) {
        this.musicPending = false;
        if (!this.musicOld) this.musicFade = 0;
        this.musicNow = this.startClip(this.musicName, sound, 0.001, 1, true);
      } else if (!this.isLoading(this.musicName)) {
        this.musicPending = false;
      }
    }
    for (const [name, want] of [...this.pendingLoops]) {
      if (this.find(name)) {
        this.pendingLoops.delete(name);
        this.setLoop(name, true, want.volume, want.pitch);
      } else if (!this.isLoading(name)) {
        this.pendingLoops.delete(name);
      }
    }

    // Make room for the music sample without losing the position of the current track.
    const previewing = this.musicPreview && this.previewClip !== null && this.previewClip.isPlaying();
    this.musicBedGain = interpConstantTo(this.musicBedGain, previewing ? 0 : 1, dt, 8);
    // Leave space for the call, then bring the stands back up after the line.
    const speaking = this.voice !== null && this.voice.isPlaying();
    const bedTarget = speaking ? 1 - 0.35 * this.announcerGain : 1;
    this.bedGain = interpConstantTo(this.bedGain, bedTarget, dt, speaking ? 4 : 1.3);
    // Music cross-fade.
    this.musicFade = Math.min(1, this.musicFade + dt / 0.8);
    this.musicNow?.setVolume(Math.max(0.001, this.musicVolume * this.musicFade * this.musicBedGain * this.bedGain));
    if (this.musicOld) {
      const left = 1 - this.musicFade;
      if (left <= 0) {
        this.musicOld.stop();
        this.musicOld = null;
      } else {
        this.musicOld.setVolume(Math.max(0.001, this.previousMusicGain * left * this.musicBedGain * this.bedGain));
      }
    }

    // Switched loops glide to their volume instead of snapping.
    for (const [name, now] of this.loopNow) {
      const target = this.loopTarget.get(name) ?? 0;
      const value = interpConstantTo(now, target, dt, target > now ? 4 : 2.5);
      this.loopNow.set(name, value);
      const clip = this.loops.get(name);
      if (clip) {
        clip.setVolume(Math.max(0.001, value));
        if (value === 0 && target === 0 && clip.isPlaying()) clip.stop();
      }
    }

    // The crowd: a murmur that is always there, and a roar that swells with the action. The two
    // beds are different people, so they are mixed with an equal-power cross-fade.
    this.crowdLevel = this.crowdLevel + ((this.crowd ? excitement : 0) - this.crowdLevel) * Math.min(1, dt * 2.5);
    const presence = this.crowd ? this.bedGain : 0;
    const angle = Math.min(Math.max(this.crowdLevel, 0), 1) * (Math.PI / 2);
    this.loop('AMB_CrowdLow', 0.4)?.setVolume(Math.max(0.001, presence * (0.35 + 0.65 * Math.cos(angle))));
    this.loop('AMB_CrowdHigh', 0.001)?.setVolume(Math.max(0.001, presence * Math.sin(angle) * 0.9));
    this.loop('AMB_Night', 0.2)?.setVolume(0.25);
  }
}
