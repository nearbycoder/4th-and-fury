/**
 * Animation for the athletes without an animation mixer (port of FuryAnim.h/.cpp).
 *
 * Every clip is sampled once at load into plain arrays of local bone transforms (30 per second).
 * Athletes then build each frame's pose themselves by sampling and blending those arrays, and
 * write the result straight into their bones. That keeps the whole animation state machine in
 * ordinary game code, exactly as in the Unreal build.
 */
import * as THREE from 'three';
import { Grip } from '../sim/core';
import manifest from './data/anims.json';

const BakeRate = 30;

export class Pose {
  rot: Float32Array;
  loc: Float32Array;
  constructor(readonly num: number) {
    this.rot = new Float32Array(num * 4);
    this.loc = new Float32Array(num * 3);
  }
  copy(o: Pose): this { this.rot.set(o.rot); this.loc.set(o.loc); return this; }
  clone(): Pose { return new Pose(this.num).copy(this); }

  /** this = lerp(this, other, alpha). */
  blendTo(other: Pose, alpha: number): void {
    if (alpha <= 0) return;
    if (alpha >= 1) { this.copy(other); return; }
    for (let i = 0; i < this.num; ++i) blendBone(this, other, i, alpha);
  }
  /** Same, with a per-bone weight multiplied into alpha. */
  blendToMasked(other: Pose, alpha: number, mask: Float32Array): void {
    if (alpha <= 0) return;
    for (let i = 0; i < this.num; ++i) {
      const w = alpha * mask[i];
      if (w > 0) blendBone(this, other, i, w);
    }
  }
}

function blendBone(a: Pose, b: Pose, i: number, t: number): void {
  // Shortest-arc normalized lerp: plenty accurate at 30 samples per second.
  const r = a.rot, o = b.rot, k = i * 4;
  const sign = r[k] * o[k] + r[k + 1] * o[k + 1] + r[k + 2] * o[k + 2] + r[k + 3] * o[k + 3] < 0 ? -1 : 1;
  let x = r[k] + (o[k] * sign - r[k]) * t;
  let y = r[k + 1] + (o[k + 1] * sign - r[k + 1]) * t;
  let z = r[k + 2] + (o[k + 2] * sign - r[k + 2]) * t;
  let w = r[k + 3] + (o[k + 3] * sign - r[k + 3]) * t;
  const n = 1 / (Math.hypot(x, y, z, w) || 1);
  r[k] = x * n; r[k + 1] = y * n; r[k + 2] = z * n; r[k + 3] = w * n;
  const l = a.loc, p = b.loc, j = i * 3;
  l[j] += (p[j] - l[j]) * t;
  l[j + 1] += (p[j + 1] - l[j + 1]) * t;
  l[j + 2] += (p[j + 2] - l[j + 2]) * t;
}

export class Clip {
  numFrames = 0;
  length = 0;           // seconds
  loop = false;
  speed = 0;            // ground speed (cm/s) at which a locomotion loop does not skate
  grip: Grip = Grip.None;
  events = new Map<string, number>();
  rot!: Float32Array;   // numFrames * numBones * 4
  loc!: Float32Array;
  constructor(readonly name: string, readonly numBones: number) {}

  sample(time: number, out: Pose): void {
    if (this.numFrames <= 0) return;
    let frame = time * BakeRate;
    const last = this.numFrames - 1;
    if (this.loop && last > 0) {
      frame = frame % last;
      if (frame < 0) frame += last;
    } else {
      frame = Math.min(Math.max(frame, 0), last);
    }
    const a = Math.min(Math.floor(frame), last);
    const b = Math.min(a + 1, last);
    const t = frame - a;
    const n = this.numBones;
    const ra = a * n * 4, rb = b * n * 4, la = a * n * 3, lb = b * n * 3;
    const R = this.rot, L = this.loc, or = out.rot, ol = out.loc;
    for (let i = 0; i < n; ++i) {
      const ka = ra + i * 4, kb = rb + i * 4, k = i * 4;
      const sign = R[ka] * R[kb] + R[ka + 1] * R[kb + 1] + R[ka + 2] * R[kb + 2] + R[ka + 3] * R[kb + 3] < 0 ? -1 : 1;
      const x = R[ka] + (R[kb] * sign - R[ka]) * t;
      const y = R[ka + 1] + (R[kb + 1] * sign - R[ka + 1]) * t;
      const z = R[ka + 2] + (R[kb + 2] * sign - R[ka + 2]) * t;
      const w = R[ka + 3] + (R[kb + 3] * sign - R[ka + 3]) * t;
      const m = 1 / (Math.hypot(x, y, z, w) || 1);
      or[k] = x * m; or[k + 1] = y * m; or[k + 2] = z * m; or[k + 3] = w * m;
      const ja = la + i * 3, jb = lb + i * 3, j = i * 3;
      ol[j] = L[ja] + (L[jb] - L[ja]) * t;
      ol[j + 1] = L[ja + 1] + (L[jb + 1] - L[ja + 1]) * t;
      ol[j + 2] = L[ja + 2] + (L[jb + 2] - L[ja + 2]) * t;
    }
  }
  event(name: string, fallback: number): number {
    const v = this.events.get(name);
    return v === undefined ? fallback : v;
  }
}

interface ManifestClip { name: string; frames: number; loop?: boolean; speed?: number; ball?: string; events?: Record<string, number> }

/** Every clip plus the skeleton they animate. One instance is shared by all athletes. */
export class AnimSet {
  numBones = 0;
  boneNames: string[] = [];
  parents: number[] = [];
  refPose!: Pose;
  clips = new Map<string, Clip>();
  upperBody!: Float32Array;
  leftArm!: Float32Array;
  carryArm!: Float32Array;
  pelvis = -1; spine1 = -1; spine2 = -1; spine3 = -1; head = -1;
  handR = -1; handL = -1; ballHand = -1; ballTuck = -1;
  footL = -1; footR = -1; toeL = -1; toeR = -1; towel = -1;
  upperArmL = -1; upperArmR = -1;

  /** Builds from the bones of one skinned mesh (any build: they share the rig) and the clip library. */
  build(bones: THREE.Bone[], animations: THREE.AnimationClip[]): void {
    this.numBones = bones.length;
    this.boneNames = bones.map((b) => b.name);
    this.parents = bones.map((b) => bones.indexOf(b.parent as THREE.Bone));
    this.refPose = new Pose(this.numBones);
    bones.forEach((b, i) => {
      b.quaternion.toArray(this.refPose.rot, i * 4);
      b.position.toArray(this.refPose.loc, i * 3);
    });
    const bone = (n: string) => this.boneNames.indexOf(n);
    this.pelvis = bone('pelvis'); this.spine1 = bone('spine_01'); this.spine2 = bone('spine_02'); this.spine3 = bone('spine_03');
    this.head = bone('head'); this.upperArmL = bone('upperarm_l'); this.upperArmR = bone('upperarm_r');
    this.handR = bone('hand_r'); this.handL = bone('hand_l'); this.ballHand = bone('ball_hand_r'); this.ballTuck = bone('ball_tuck_r');
    this.footL = bone('foot_l'); this.footR = bone('foot_r'); this.toeL = bone('ball_l'); this.toeR = bone('ball_r'); this.towel = bone('towel');

    // Masks: a bone inherits its parent's weight; the listed bones start a region.
    const buildMask = (roots: string[], softRootWeight: number) => {
      const mask = new Float32Array(this.numBones);
      for (let i = 0; i < this.numBones; ++i) {
        let w = this.parents[i] >= 0 ? mask[this.parents[i]] : 0;
        if (roots.includes(this.boneNames[i])) w = 1;
        mask[i] = w;
      }
      // Ease the region in over the bone just below it so the seam does not snap.
      const soft = bone('spine_02');
      if (softRootWeight > 0 && soft >= 0 && mask[soft] < softRootWeight) mask[soft] = softRootWeight;
      return mask;
    };
    this.upperBody = buildMask(['spine_03'], 0.5);
    this.leftArm = buildMask(['clavicle_l'], 0);
    this.carryArm = buildMask(['clavicle_r'], 0);

    const byName = new Map(animations.map((a) => [a.name.replace(/^A_/, ''), a]));
    for (const entry of (manifest as unknown as { clips: ManifestClip[] }).clips) {
      const anim = byName.get(entry.name);
      if (!anim) { console.warn(`Animation ${entry.name} is in the manifest but not in the library`); continue; }
      const clip = this.bake(anim, entry.name);
      clip.loop = !!entry.loop;
      if (entry.speed) clip.speed = entry.speed * 100;   // metres per second -> cm per second
      clip.grip = entry.ball === 'hand' ? Grip.Hand : entry.ball === 'tuck' ? Grip.Tuck : Grip.None;
      for (const [k, frame] of Object.entries(entry.events ?? {})) clip.events.set(k, frame / BakeRate);
      this.clips.set(entry.name, clip);
    }
  }

  private bake(anim: THREE.AnimationClip, name: string): Clip {
    const n = this.numBones;
    const clip = new Clip(name, n);
    clip.length = anim.duration;
    clip.numFrames = Math.max(1, Math.round(clip.length * BakeRate) + 1);
    clip.rot = new Float32Array(clip.numFrames * n * 4);
    clip.loc = new Float32Array(clip.numFrames * n * 3);
    const quat: (THREE.Interpolant | null)[] = new Array(n).fill(null);
    const pos: (THREE.Interpolant | null)[] = new Array(n).fill(null);
    for (const track of anim.tracks) {
      const dot = track.name.lastIndexOf('.');
      const boneName = track.name.slice(0, dot), prop = track.name.slice(dot + 1);
      const i = this.boneNames.indexOf(boneName);
      if (i < 0) continue;
      if (prop === 'quaternion') quat[i] = (track as unknown as { createInterpolant(): THREE.Interpolant }).createInterpolant();
      else if (prop === 'position') pos[i] = (track as unknown as { createInterpolant(): THREE.Interpolant }).createInterpolant();
    }
    const q = new THREE.Quaternion();
    for (let f = 0; f < clip.numFrames; ++f) {
      const time = Math.min(f / BakeRate, clip.length);
      for (let i = 0; i < n; ++i) {
        const kr = (f * n + i) * 4, kl = (f * n + i) * 3;
        const qi = quat[i];
        if (qi) {
          const v = qi.evaluate(time);
          q.set(v[0], v[1], v[2], v[3]).normalize();
          q.toArray(clip.rot, kr);
        } else clip.rot.set(this.refPose.rot.subarray(i * 4, i * 4 + 4), kr);
        const pi = pos[i];
        if (pi) {
          const v = pi.evaluate(time);
          clip.loc[kl] = v[0]; clip.loc[kl + 1] = v[1]; clip.loc[kl + 2] = v[2];
        } else clip.loc.set(this.refPose.loc.subarray(i * 3, i * 3 + 3), kl);
      }
    }
    return clip;
  }

  find(name: string): Clip | null { return this.clips.get(name) ?? null; }
  /** The first of the given clips that exists (for graceful fallbacks). */
  findFirst(...names: string[]): Clip | null {
    for (const n of names) { const c = this.clips.get(n); if (c) return c; }
    return null;
  }
}
