/**
 * One athlete on the field (port of AFuryAthlete): a skinned body dressed in a team's kit, posed
 * every frame from the simulation's state by sampling and blending baked clips.
 */
import * as THREE from 'three';
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js';
import { Act, AngleDelta, Approach, Build, Fall, FromAngle, Grip, Stance, Vec2, Vec3 } from '../sim/core';
import { AnimSet, Clip, Pose } from './anim';
import { CM, fromThree, toThree, yawToThree } from './space';

/** How one athlete is dressed (FFuryLook). Colours are THREE.Color in linear space. */
export interface Look {
  build: Build;
  jersey: THREE.Color; jerseyTrim: THREE.Color; numberFill: THREE.Color; numberEdge: THREE.Color;
  pants: THREE.Color; pantsStripe: THREE.Color; helmet: THREE.Color; helmetStripe: THREE.Color;
  facemask: THREE.Color; socks: THREE.Color; shoes: THREE.Color; gloves: THREE.Color; skin: THREE.Color;
  number: number;
  visor: boolean;
  scale: number;
  logo: THREE.Texture | null;
}

/** What the simulation tells an athlete each frame (FFuryAthleteState). */
export class AthleteState {
  pos: Vec2 = Vec2.Zero;
  height = 0;          // extra lift from the simulation (being launched by a hit)
  yaw = 0;             // facing, radians, 0 = +X
  vel: Vec2 = Vec2.Zero;
  act: Act = Act.Stand;
  variant = 0;
  actSerial = 0;       // changes whenever a new action starts
  actTime = 0;         // seconds since the action started
  actLength = 0;       // how long the simulation gives the action (0 = open-ended)
  actKey = 0;          // when its key moment (release, contact) happens in the simulation
  hasBall = false;
  passer = false;      // holding the ball to throw
  fury = false;
  visible = true;
}

interface Layer { clip: Clip | null; upperOnly?: boolean; leftArmOnly?: boolean }

const smoothStep01 = (t: number) => { t = Math.min(Math.max(t, 0), 1); return t * t * (3 - 2 * t); };

// ---------------------------------------------------------------------------------------------
// Materials: one per slot per athlete, sharing three shader programs
// ---------------------------------------------------------------------------------------------

export interface AthleteTextures { numbers: THREE.Texture | null }

interface SlotUniforms {
  uNumber: { value: number }; uUseNumber: { value: number };
  uNumberFill: { value: THREE.Color }; uNumberEdge: { value: THREE.Color };
  uNumbers: { value: THREE.Texture | null };
  uLogo: { value: THREE.Texture | null }; uUseLogo: { value: number };
  uGlow: { value: number }; uGlowColor: { value: THREE.Color };
}

function makeSlotMaterial(slot: string, tex: AthleteTextures): THREE.MeshStandardMaterial {
  const mat = new THREE.MeshStandardMaterial({ name: slot });
  const u: SlotUniforms = {
    uNumber: { value: 7 }, uUseNumber: { value: 0 },
    uNumberFill: { value: new THREE.Color(1, 1, 1) }, uNumberEdge: { value: new THREE.Color(0, 0, 0) },
    uNumbers: { value: tex.numbers },
    uLogo: { value: null }, uUseLogo: { value: 0 },
    uGlow: { value: 0 }, uGlowColor: { value: new THREE.Color(1, 0.35, 0.05) },
  };
  mat.userData.u = u;
  const numbered = slot === 'Jersey' && !!tex.numbers;
  const logo = slot === 'HelmetLogo';
  mat.customProgramCacheKey = () => `fury-athlete-${numbered ? 'n' : ''}${logo ? 'l' : ''}`;
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, u);
    if (numbered) {
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nattribute vec2 uv1;\nvarying vec2 vNumUv;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvNumUv = uv1;');
    }
    if (logo) {
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec2 vLogoUv;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvLogoUv = uv;');
    }
    let header = '#include <common>\nuniform float uGlow;\nuniform vec3 uGlowColor;\n';
    let paint = '';
    if (numbered) {
      header += 'varying vec2 vNumUv;\nuniform sampler2D uNumbers;\nuniform float uNumber;\nuniform float uUseNumber;\nuniform vec3 uNumberFill;\nuniform vec3 uNumberEdge;\n';
      // Jersey number: NumberUV is 0..1 inside a number panel; T_Numbers is a 10 x 10 sheet with
      // number n in column n % 10, row n / 10, row 0 at the top. R = fill, G = outline.
      paint += `
        {
          float inside = step(0.0, vNumUv.x) * step(vNumUv.x, 1.0) * step(0.0, vNumUv.y) * step(vNumUv.y, 1.0);
          float n = floor(uNumber + 0.5);
          vec2 cell = vec2(mod(n, 10.0), floor(n / 10.0));
          vec4 digits = texture2D(uNumbers, (cell + clamp(vNumUv, 0.0, 1.0)) * 0.1);
          float gate = inside * uUseNumber;
          diffuseColor.rgb = mix(diffuseColor.rgb, uNumberEdge, digits.g * gate);
          diffuseColor.rgb = mix(diffuseColor.rgb, uNumberFill, digits.r * gate);
        }`;
    }
    if (logo) {
      header += 'varying vec2 vLogoUv;\nuniform sampler2D uLogo;\nuniform float uUseLogo;\n';
      paint += `
        {
          vec4 emblem = texture2D(uLogo, vLogoUv);
          diffuseColor.rgb = mix(diffuseColor.rgb, emblem.rgb, emblem.a * uUseLogo);
        }`;
    }
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', header)
      .replace('#include <map_fragment>', '#include <map_fragment>\n' + paint)
      // Fury: a hot rim around the silhouette, so the uniform still reads underneath.
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        if (uGlow > 0.0) {
          float fres = 0.025 + 0.975 * pow(1.0 - abs(dot(normalize(normal), normalize(vViewPosition))), 3.6);
          totalEmissiveRadiance += uGlowColor * uGlow * fres;
        }`);
  };
  return mat;
}

// ---------------------------------------------------------------------------------------------
// The athlete
// ---------------------------------------------------------------------------------------------

export class Athlete {
  readonly root = new THREE.Group();
  private bodies: (THREE.Object3D | null)[] = [null, null, null];
  private body: THREE.Object3D | null = null;
  private bones: THREE.Bone[] = [];
  private materials = new Map<string, THREE.MeshStandardMaterial>();
  private build = -1;
  private scale = 1;

  private current: Pose;
  private from: Pose;
  private scratch: Pose;
  private moving: Pose;
  private temp: Pose;
  private blendTime = 0;
  private blendLength = 0;
  private lastSerial = -1;
  private wasFullBody = false;
  private phase = 0;          // shared locomotion phase, 0..1
  private moveBlend = 0;      // 0 standing, 1 moving
  private gaitBlend = 0;      // 0 jog, 1 sprint
  private dirBlend = new Vec2(1, 0);
  private lean = 0;
  private lastYaw = 0;
  private posed = false;
  private glowing = false;
  private grip: Grip = Grip.None;
  private stepped = false;
  private rollAxis = new THREE.Vector3(0, 0, 1);

  constructor(private readonly anims: AnimSet, private readonly meshes: THREE.Object3D[], private readonly tex: AthleteTextures) {
    const n = anims.numBones;
    this.current = anims.refPose.clone();
    this.from = anims.refPose.clone();
    this.scratch = new Pose(n);
    this.moving = new Pose(n);
    this.temp = new Pose(n);
    this.root.visible = false;
  }

  get visible(): boolean { return this.root.visible; }
  set visible(v: boolean) { this.root.visible = v; }
  currentGrip(): Grip { return this.grip; }
  didStep(): boolean { return this.stepped; }

  private useBuild(build: number): void {
    if (this.build === build) return;
    if (this.body) this.root.remove(this.body);
    let body = this.bodies[build];
    if (!body) {
      body = cloneSkinned(this.meshes[build]);
      body.traverse((o) => {
        const m = o as THREE.SkinnedMesh;
        if (!m.isSkinnedMesh && !(o as THREE.Mesh).isMesh) return;
        m.castShadow = true;
        m.receiveShadow = true;
        m.frustumCulled = false;     // the pose can reach far from the bind pose (dives, flips)
        const slot = (m.material as THREE.Material).name;
        let mat = this.materials.get(slot);
        if (!mat) { mat = makeSlotMaterial(slot, this.tex); this.materials.set(slot, mat); }
        m.material = mat;
      });
      this.bodies[build] = body;
    }
    this.body = body;
    this.root.add(body);
    // Bones in the animation set's order, by name.
    const byName = new Map<string, THREE.Bone>();
    body.traverse((o) => { if ((o as THREE.Bone).isBone) byName.set(o.name, o as THREE.Bone); });
    this.bones = this.anims.boneNames.map((name) => byName.get(name)!);
    // The roll axis for leaning: the character's forward (+Z in glTF) in the pelvis' parent space.
    const pelvis = this.anims.pelvis;
    if (pelvis >= 0 && this.bones[pelvis]?.parent) {
      body.updateMatrixWorld(true);
      const parent = this.bones[pelvis].parent!;
      const q = new THREE.Quaternion();
      const rootQ = new THREE.Quaternion();
      parent.getWorldQuaternion(q);
      body.getWorldQuaternion(rootQ);
      q.premultiply(rootQ.invert());
      this.rollAxis.set(0, 0, 1).applyQuaternion(q.invert()).normalize();
    }
    this.build = build;
    this.posed = false;
  }

  setLook(look: Look): void {
    this.useBuild(look.build);
    this.scale = look.scale;
    this.body!.scale.setScalar(look.scale);
    this.glowing = false;
    type S = { color: THREE.Color; rough: number; metal: number; number?: boolean };
    const surface = (slot: string): S => {
      switch (slot) {
        case 'Helmet': return { color: look.helmet, rough: 0.16, metal: 0 };
        case 'HelmetStripe': return { color: look.helmetStripe, rough: 0.2, metal: 0 };
        case 'HelmetLogo': return { color: look.helmet, rough: 0.16, metal: 0 };      // the emblem's clear parts are helmet paint
        case 'Facemask': return { color: look.facemask, rough: 0.3, metal: 0.85 };
        case 'Visor': return { color: new THREE.Color(0.01, 0.012, 0.016), rough: 0.06, metal: 0.9 };
        case 'Strap': return { color: new THREE.Color(0.85, 0.85, 0.85), rough: 0.6, metal: 0 };
        case 'Skin': return { color: look.skin, rough: 0.55, metal: 0 };
        case 'Eyes': return { color: new THREE.Color(0.015, 0.012, 0.01), rough: 0.4, metal: 0 };
        case 'Jersey': return { color: look.jersey, rough: 0.72, metal: 0, number: true };
        case 'JerseyTrim': return { color: look.jerseyTrim, rough: 0.7, metal: 0 };
        case 'Pants': return { color: look.pants, rough: 0.62, metal: 0 };
        case 'PantsStripe': return { color: look.pantsStripe, rough: 0.62, metal: 0 };
        case 'Belt': return { color: new THREE.Color(0.03, 0.03, 0.03), rough: 0.5, metal: 0 };
        case 'Socks': return { color: look.socks, rough: 0.8, metal: 0 };
        case 'Shoes': return { color: look.shoes, rough: 0.35, metal: 0 };
        case 'ShoeSole': return { color: new THREE.Color(0.75, 0.75, 0.75), rough: 0.6, metal: 0 };
        case 'Gloves': return { color: look.gloves, rough: 0.55, metal: 0 };
        case 'Bands': return { color: look.jerseyTrim, rough: 0.75, metal: 0 };
        default: return { color: new THREE.Color(0.5, 0.5, 0.5), rough: 0.6, metal: 0 };
      }
    };
    for (const [slot, mat] of this.materials) {
      const s = surface(slot);
      mat.color.copy(s.color);
      mat.roughness = s.rough;
      mat.metalness = s.metal;
      // Metals need something to reflect; the night stadium gives them little, so keep them readable.
      if (s.metal > 0.5) mat.envMapIntensity = 1.5;
      const u = mat.userData.u as SlotUniforms;
      u.uNumber.value = Math.min(Math.max(look.number, 0), 99);
      u.uUseNumber.value = s.number ? 1 : 0;
      u.uNumberFill.value.copy(look.numberFill);
      u.uNumberEdge.value.copy(look.numberEdge);
      u.uGlow.value = 0;
      if (slot === 'HelmetLogo') { u.uLogo.value = look.logo; u.uUseLogo.value = look.logo ? 1 : 0; }
      if (slot === 'Visor') mat.visible = look.visor;
    }
  }

  // --- Pose building (FuryAthlete.cpp) ---

  private stanceFor(s: AthleteState): Clip | null {
    const a = this.anims;
    if (s.passer) return a.findFirst('QBSet', 'Idle');
    switch (s.variant as Stance) {
      case Stance.Ready: return a.findFirst('Ready', 'Idle');
      case Stance.ThreePoint: return a.findFirst('Stance3', 'Ready', 'Idle');
      case Stance.Center: return a.findFirst('StanceCenter', 'Stance3', 'Idle');
      case Stance.QB: return a.findFirst('StanceQB', 'Ready', 'Idle');
      case Stance.QBSet: return a.findFirst('QBSet', 'Idle');
      default: return a.findFirst('Idle');
    }
  }

  private actionFor(s: AthleteState): Layer {
    const a = this.anims;
    const moving = s.vel.sizeSquared() > 200 * 200;
    const v = s.variant;
    switch (s.act) {
      case Act.Snap: return { clip: a.findFirst('Snap') };
      case Act.CatchSnap: return { clip: a.findFirst('CatchSnap') };
      case Act.Throw: return { clip: a.findFirst('Throw'), upperOnly: moving };
      case Act.Handoff: return { clip: a.findFirst('Handoff'), upperOnly: true };
      case Act.Catch: return v === 1 ? { clip: a.findFirst('CatchHigh', 'CatchChest') } : { clip: a.findFirst('CatchChest'), upperOnly: true };
      case Act.Swat: return { clip: a.findFirst('Swat', 'CatchHigh') };
      case Act.Block: return { clip: a.findFirst('BlockLoop', 'Ready') };
      case Act.Dive: return { clip: a.findFirst('DiveTackle', 'HitFront') };
      case Act.Tackle: return { clip: a.findFirst('TackleWrap', 'DiveTackle') };
      case Act.BigHit: return { clip: a.findFirst('BigHit', 'Shove') };
      case Act.Shove: return { clip: a.findFirst('Shove', 'BigHit') };
      case Act.Hit:
        switch (v as Fall) {
          case Fall.Front: return { clip: a.findFirst('HitFront', 'HitBack') };
          case Fall.Flip: return { clip: a.findFirst('HitFlip', 'HitBack') };
          case Fall.Spin: return { clip: a.findFirst('HitSpin', 'HitFront', 'HitBack') };
          default: return { clip: a.findFirst('HitBack') };
        }
      case Act.GroundRecoil: return { clip: v === 0 ? a.findFirst('GroundHitBack', 'DownBack') : a.findFirst('GroundHitFront', 'DownFront') };
      case Act.Down: return { clip: v === 0 ? a.findFirst('DownBack') : a.findFirst('DownFront', 'DownBack') };
      case Act.GetUp: return { clip: v === 0 ? a.findFirst('GetUpBack') : a.findFirst('GetUpFront', 'GetUpBack') };
      case Act.Stumble: return { clip: a.findFirst('Stumble') };
      case Act.StiffArm: return { clip: a.findFirst('StiffArm'), leftArmOnly: true };
      case Act.Spin: return { clip: a.findFirst('Spin') };
      case Act.Juke: return { clip: v === 0 ? a.findFirst('JukeL') : a.findFirst('JukeR') };
      case Act.Hurdle: return { clip: a.findFirst('Hurdle') };
      case Act.DiveBall: return { clip: a.findFirst('DiveBall', 'DiveTackle') };
      case Act.Kick: return { clip: a.findFirst('Kick') };
      case Act.Punt: return { clip: a.findFirst('Punt', 'Kick') };
      case Act.PickUp: return { clip: a.findFirst('PickUp'), upperOnly: moving };
      case Act.Celebrate:
        return { clip: v === 0 ? a.findFirst('CelebSpike', 'CelebFlex') : v === 1 ? a.findFirst('CelebDance', 'CelebFlex') : a.findFirst('CelebFlex', 'CelebDance') };
      case Act.Dejected: return { clip: a.findFirst('Dejected', 'Idle') };
      case Act.Signal: return { clip: a.findFirst('Signal1st'), upperOnly: true };
      case Act.ElbowDrop: return { clip: a.findFirst('ElbowDrop', 'DiveTackle') };
      default: return { clip: null };
    }
  }

  /**
   * The simulation decides how long an action lasts and when its key moment falls (the release of
   * a throw, the contact of a kick). The clip is stretched so its own key moment lands on the
   * simulation's, which keeps the ball leaving the hand exactly when the pass is launched.
   */
  private clipTime(s: AthleteState, clip: Clip): number {
    if (clip.loop || s.actLength <= 0) return s.actTime;
    if (s.act === Act.Dive && s.actKey <= 0) {
      // Hold the outstretched silhouette while the collision is still open.
      const hit = clip.event('hit', clip.length / 3);
      if (s.actTime < 0.1) return (s.actTime / 0.1) * hit * 0.82;
      if (s.actTime <= 0.36) return hit * (0.82 + (1 - 0.82) * ((s.actTime - 0.1) / 0.26));
      return hit + ((clip.length - hit) * (s.actTime - 0.36)) / Math.max(s.actLength - 0.36, 0.05);
    }
    let key = -1;
    for (const name of ['release', 'catch', 'contact', 'hit', 'apex', 'grab', 'give', 'spike']) {
      key = clip.event(name, -1);
      if (key > 0) break;
    }
    if (key > 0 && s.actKey > 0) {
      if (s.actTime < s.actKey) return (s.actTime * key) / s.actKey;
      return key + ((s.actTime - s.actKey) * (clip.length - key)) / Math.max(s.actLength - s.actKey, 0.05);
    }
    return (s.actTime * clip.length) / s.actLength;
  }

  private locomotion(s: AthleteState, dt: number, out: Pose): void {
    const a = this.anims;
    const speed = s.vel.size();
    const facing = FromAngle(s.yaw);
    const right = new Vec2(-facing.y, facing.x);

    // How much we are moving at all, and in which direction relative to where we face.
    const moveTarget = s.act === Act.Stand ? 0 : Math.min(Math.max((speed - 25) / 140, 0), 1);
    this.moveBlend = Approach(this.moveBlend, moveTarget, dt * 7);
    if (speed > 30) {
      const local = new Vec2(Vec2.dot(s.vel, facing) / speed, Vec2.dot(s.vel, right) / speed);
      this.dirBlend = Vec2.lerp(this.dirBlend, local, Math.min(1, dt * 12));
    }

    const stance = this.stanceFor(s);
    const carry = s.hasBall && !s.passer;
    let jog = a.findFirst('Jog', 'Run');
    const run = carry ? a.findFirst('RunBall', 'Run') : a.findFirst('Run', 'Jog');
    const back = s.passer ? a.findFirst('QBDrop', 'Backpedal') : a.findFirst('Backpedal');
    const left = a.findFirst('ShuffleL');
    const rightClip = a.findFirst('ShuffleR');
    if (carry && run) jog = a.findFirst('JogBall', 'RunBall', 'Run');

    if (stance) stance.sample(s.actTime, out);
    else out.copy(a.refPose);
    this.grip = s.hasBall ? (s.passer ? Grip.Hand : Grip.Tuck) : Grip.None;
    if (this.moveBlend <= 0.001 || !run) return;

    // Direction weights (forward / back / left / right), sharpened so one gait dominates.
    let wf = Math.max(0, this.dirBlend.x), wb = Math.max(0, -this.dirBlend.x);
    let wr = Math.max(0, this.dirBlend.y), wl = Math.max(0, -this.dirBlend.y);
    if (!back) { wf += wb; wb = 0; }
    if (!left || !rightClip) { wf += wl + wr; wl = wr = 0; }
    wf *= wf; wb *= wb; wl *= wl; wr *= wr;
    const sum = Math.max(wf + wb + wl + wr, 1e-4);
    wf /= sum; wb /= sum; wl /= sum; wr /= sum;

    const jogSpeed = jog && jog.speed > 0 ? jog.speed : 450;
    const runSpeed = run.speed > 0 ? run.speed : 800;
    const gaitTarget = jog === run ? 1 : Math.min(Math.max((speed - jogSpeed) / Math.max(runSpeed - jogSpeed, 1), 0), 1);
    this.gaitBlend = Approach(this.gaitBlend, gaitTarget, dt * 5);

    // One phase drives every gait so they stay in step; its rate keeps the feet from skating.
    const stride = (c: Clip | null, fallback: number) => (c && c.speed > 0 ? c.speed * c.length : fallback);
    const forwardStride = stride(jog, 300) + (stride(run, 430) - stride(jog, 300)) * this.gaitBlend;
    const strideLength = wf * forwardStride + wb * stride(back, 270) + (wl + wr) * stride(left, 230);
    const nextPhase = this.phase + (dt * speed) / (Math.max(strideLength, 50) * this.scale);
    this.stepped = Math.floor(2 * nextPhase) !== Math.floor(2 * this.phase);
    this.phase = nextPhase - Math.floor(nextPhase);

    let have = false;
    let accumulated = 0;
    const add = (c: Clip | null, weight: number) => {
      if (!c || weight <= 0.001) return;
      c.sample(this.phase * c.length, this.temp);
      accumulated += weight;
      if (!have) { this.moving.copy(this.temp); have = true; }
      else this.moving.blendTo(this.temp, weight / accumulated);
    };
    add(jog, wf * (1 - this.gaitBlend));
    add(run, wf * this.gaitBlend);
    add(back, wb);
    add(left, wl);
    add(rightClip, wr);
    if (have) {
      // The backpedal and shuffle were authored for coverage. Keep the carrying
      // arm wrapped around the ball when a runner cuts across his body.
      if (carry && jog && wf < 0.99) {
        jog.sample(this.phase * jog.length, this.temp);
        this.moving.blendToMasked(this.temp, 1 - wf, a.carryArm);
      }
      out.blendTo(this.moving, this.moveBlend);
    }
  }

  private buildPose(s: AthleteState, dt: number, out: Pose): void {
    const action = this.actionFor(s);
    const fullBody = !!action.clip && !action.upperOnly && !action.leftArmOnly;

    if (fullBody) {
      const clip = action.clip!;
      clip.sample(this.clipTime(s, clip), out);
      this.grip = s.hasBall ? (clip.grip === Grip.None ? Grip.Hand : clip.grip) : Grip.None;
      // Keep the locomotion phase ticking so the feet do not restart from zero afterwards.
      const p = this.phase + dt * 1.6;
      this.phase = p - Math.floor(p);
    } else {
      this.locomotion(s, dt, out);
      if (action.clip) {
        const clip = action.clip;
        clip.sample(this.clipTime(s, clip), this.temp);
        const length = s.actLength > 0 ? s.actLength : clip.length;
        const envelope = Math.min(Math.max(s.actTime / 0.07, 0), 1) * Math.min(Math.max((length - s.actTime) / 0.12, 0), 1);
        out.blendToMasked(this.temp, envelope, action.leftArmOnly ? this.anims.leftArm : this.anims.upperBody);
        if (!action.leftArmOnly && s.hasBall && clip.grip !== Grip.None) this.grip = clip.grip;
      }
    }

    // Cross-fade from whatever was on screen whenever the full-body action changes.
    const changed = fullBody !== this.wasFullBody || (fullBody && s.actSerial !== this.lastSerial);
    if (changed && this.posed) {
      this.from.copy(this.current);
      this.blendTime = 0;
      switch (s.act) {
        case Act.GroundRecoil: this.blendLength = 0.015; break;
        case Act.Hit: this.blendLength = 0.032; break;
        case Act.Tackle: this.blendLength = 0.035; break;
        case Act.Dive: case Act.BigHit: case Act.Shove: case Act.Spin: case Act.Juke: this.blendLength = 0.07; break;
        case Act.GetUp: case Act.Down: this.blendLength = 0.1; break;
        default: this.blendLength = fullBody ? 0.12 : 0.2; break;
      }
    }
    this.wasFullBody = fullBody;
    this.lastSerial = s.actSerial;

    if (this.blendTime < this.blendLength) {
      this.blendTime += dt;
      const alpha = smoothStep01(this.blendTime / this.blendLength);
      this.scratch.copy(this.from);
      this.scratch.blendTo(out, alpha);
      out.copy(this.scratch);
    }
  }

  private pose = new Pose(1);
  private q = new THREE.Quaternion();
  private q2 = new THREE.Quaternion();

  /** Moves, poses and renders the athlete for this frame. */
  advance(s: AthleteState, dt: number): void {
    if (!this.body) return;
    this.root.visible = s.visible;
    toThree(s.pos.x, s.pos.y, s.height, this.root.position);
    this.root.rotation.set(0, yawToThree(s.yaw), 0);
    if (s.fury !== this.glowing) {
      // In Fury the whole athlete smoulders.
      this.glowing = s.fury;
      for (const mat of this.materials.values()) (mat.userData.u as SlotUniforms).uGlow.value = this.glowing ? 2.4 : 0;
    }

    if (this.pose.num !== this.anims.numBones) this.pose = new Pose(this.anims.numBones);
    const pose = this.pose;
    this.stepped = false;
    this.buildPose(s, dt, pose);

    // Lean into turns and accelerations: a small roll of the hips, strongest at a sprint.
    const yawRate = dt > 1e-4 ? AngleDelta(this.lastYaw, s.yaw) / dt : 0;
    this.lastYaw = s.yaw;
    const leanTarget = this.wasFullBody ? 0 : Math.min(Math.max(yawRate * 0.045, -0.3), 0.3) * Math.min(Math.max(s.vel.size() / 800, 0), 1);
    this.lean += (leanTarget - this.lean) * Math.min(1, dt * 8);
    const pelvis = this.anims.pelvis;
    if (pelvis >= 0 && Math.abs(this.lean) > 0.002) {
      // Roll about the character's forward axis, expressed in the pelvis' parent space. (Field yaw
      // grows toward +Y, which the mirror into three.js space turns around, hence the sign.)
      this.q.setFromAxisAngle(this.rollAxis, this.lean);
      this.q2.fromArray(pose.rot, pelvis * 4).premultiply(this.q).toArray(pose.rot, pelvis * 4);
    }
    this.apply(pose);
  }

  private apply(pose: Pose): void {
    const n = this.anims.numBones;
    for (let i = 0; i < n; ++i) {
      const b = this.bones[i];
      if (!b) continue;
      b.quaternion.fromArray(pose.rot, i * 4);
      b.position.fromArray(pose.loc, i * 3);
    }
    this.current.copy(pose);
    this.posed = true;
    this.root.updateMatrixWorld(true);
  }

  /** Poses a named clip directly (presentation use). */
  previewClip(name: string, time: number): void {
    const clip = this.anims.find(name);
    const pose = this.anims.refPose.clone();
    if (clip) { clip.sample(time, pose); this.grip = clip.grip; }
    this.apply(pose);
  }

  // --- Queries (three.js space unless noted) ---

  boneWorldPosition(bone: number, out = new THREE.Vector3()): THREE.Vector3 {
    const b = this.bones[bone];
    return b ? b.getWorldPosition(out) : this.root.getWorldPosition(out);
  }
  /** Where the ball sits for a grip: the socket bone's world transform. Its local Y is the ball's long axis. */
  gripWorld(grip: Grip, pos: THREE.Vector3, quat: THREE.Quaternion): void {
    const bone = grip === Grip.Tuck ? this.anims.ballTuck : this.anims.ballHand;
    const b = this.bones[bone >= 0 ? bone : this.anims.handR];
    if (!b) { this.root.getWorldPosition(pos); quat.identity(); return; }
    b.getWorldPosition(pos);
    b.getWorldQuaternion(quat);
  }
  /** Top of the helmet in field space (cm). */
  headWorld(): Vec3 {
    if (this.anims.head < 0 || !this.root.visible) {
      const p = fromThree(this.root.position);
      return new Vec3(p.x, p.y, p.z + 170);
    }
    const p = fromThree(this.boneWorldPosition(this.anims.head));
    return new Vec3(p.x, p.y, p.z);
  }
  /** World-space (three) height above the ground of a bone, in cm. */
  boneHeightCm(bone: number): number { return this.boneWorldPosition(bone).y / CM; }
}
