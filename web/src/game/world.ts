/**
 * Everything three.js: renderer, scene, camera, the stadium, thirty dressed athletes (two rosters
 * of fifteen), the ball and tee, seat markers, the scrimmage and first-down lines, contact shadows
 * and particles. The director drives it; nothing here knows the rules.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { EndLineX, MaxSeats, NumPlayers, SidelineY, Vec2, Vec3 } from '../sim/core';
import { AnimSet } from './anim';
import { Athlete } from './athlete';
import { Director } from './director';
import { FuryFX } from './fx';
import { Option, type Options } from './options';
import { CM, toThree } from './space';
import { Stadium } from './stadium';

export const asset = (path: string) => `${import.meta.env.BASE_URL}assets/${path}`;

const RosterSize = 15;

/** UI images by their Unreal texture names, mapped to the converted files. */
function uiPath(name: string): string | null {
  if (name.startsWith('T_Logo_')) return asset(`textures/logo_${name.slice(7)}.webp`);
  if (name === 'T_Title') return asset('textures/title.webp');
  if (name === 'T_TitleSmall') return asset('textures/title_small.webp');
  if (name.startsWith('T_Icon_')) return asset(`textures/icons/${name.slice(7).toLowerCase()}.png`);
  if (name.startsWith('T_Down_')) return asset(`textures/down_${name.slice(7)}.png`);
  return null;
}

export class World {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(32, 16 / 9, 0.5, 900);
  readonly anims = new AnimSet();
  readonly athletes: Athlete[] = [];
  readonly fx = new FuryFX();
  stadium!: Stadium;
  ball!: THREE.Object3D;
  tee!: THREE.Object3D;
  readonly markers: THREE.Mesh[] = [];
  catchMarker!: THREE.Mesh;
  scrimmageLine!: THREE.Mesh;
  firstDownLine!: THREE.Mesh;
  private shadows!: THREE.InstancedMesh;
  private shadowOpacity!: THREE.InstancedBufferAttribute;
  private images = new Map<string, HTMLImageElement | null>();
  private logos = new Map<string, THREE.Texture>();
  private hFov = 32;
  private width = 1;
  private height = 1;
  private renderScale = 1;

  constructor(readonly canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.8;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.scene.background = new THREE.Color(0x05070c);
    this.scene.add(this.fx.mesh);
  }

  async load(onProgress: (fraction: number, label: string) => void): Promise<void> {
    const manager = new THREE.LoadingManager();
    manager.onProgress = (_url, loaded, total) => onProgress(loaded / Math.max(total, 1), 'Loading the stadium');
    const gltf = new GLTFLoader(manager);
    const tex = new THREE.TextureLoader(manager);
    const loadTex = (path: string, srgb: boolean, flipY = false) =>
      tex.loadAsync(asset(path)).then((t) => { t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace; t.flipY = flipY; t.anisotropy = 8; t.needsUpdate = true; return t; });

    const [lean, mid, big, anims, numbers, football, kicktee] = await Promise.all([
      gltf.loadAsync(asset('characters/lean.glb')),
      gltf.loadAsync(asset('characters/mid.glb')),
      gltf.loadAsync(asset('characters/big.glb')),
      gltf.loadAsync(asset('characters/anims.glb')),
      loadTex('textures/numbers.png', false),
      gltf.loadAsync(asset('stadium/football.glb')),
      gltf.loadAsync(asset('stadium/kicktee.glb')),
    ]);
    this.stadium = new Stadium(this.scene, gltf, loadTex);
    await this.stadium.load();

    // The animation set is built on the mid build's rig; every build shares it.
    let bones: THREE.Bone[] = [];
    mid.scene.traverse((o) => { const m = o as THREE.SkinnedMesh; if (m.isSkinnedMesh && bones.length === 0) bones = m.skeleton.bones; });
    this.anims.build(bones, anims.animations.length ? anims.animations : mid.animations);

    const bodies = [lean.scene, mid.scene, big.scene];
    for (let i = 0; i < 2 * RosterSize; ++i) {
      const a = new Athlete(this.anims, bodies, { numbers });
      this.athletes.push(a);
      this.scene.add(a.root);
    }

    // Load every team's logo now, for helmets.
    await Promise.all(['sasquatch', 'volcanoes', 'icebreakers', 'hellhounds', 'twisters', 'amps', 'scorpions', 'gargoyles'].map(async (id) => {
      const t = await loadTex(`textures/logo_${id}.webp`, true).catch(() => null);
      if (t) this.logos.set(id, t);
    }));

    this.ball = football.scene;
    this.ball.traverse((o) => { if ((o as THREE.Mesh).isMesh) o.castShadow = true; });
    this.ball.visible = false;
    this.scene.add(this.ball);
    this.tee = kicktee.scene;
    this.tee.visible = false;
    this.scene.add(this.tee);

    this.buildMarkers();
    this.buildLines();
    this.buildShadows();
  }

  logoTexture(id: string): THREE.Texture | null { return this.logos.get(id) ?? null; }

  uiImage(name: string): HTMLImageElement | null {
    if (this.images.has(name)) {
      const img = this.images.get(name)!;
      return img && img.complete && img.naturalWidth > 0 ? img : null;
    }
    const path = uiPath(name);
    if (!path) { this.images.set(name, null); return null; }
    const img = new Image();
    img.decoding = 'async';
    img.src = path;
    img.onerror = () => this.images.set(name, null);
    this.images.set(name, img);
    return null;
  }

  // --- Markers, lines, shadows -----------------------------------------------------------------

  private markerMaterial(color: THREE.Color, inner: number, fill: number): THREE.ShaderMaterial {
    return new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      uniforms: { uColor: { value: color }, uInner: { value: inner }, uFill: { value: fill }, uBrightness: { value: 2 }, uOpacity: { value: 0.9 } },
      vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: `
        varying vec2 vUv;
        uniform vec3 uColor; uniform float uInner; uniform float uFill; uniform float uBrightness; uniform float uOpacity;
        void main() {
          float r = length(vUv * 2.0 - 1.0);
          float ring = smoothstep(uInner - 0.04, uInner, r) * (1.0 - smoothstep(0.96, 1.0, r));
          float disc = (1.0 - smoothstep(uInner - 0.06, uInner - 0.02, r)) * uFill;
          float a = clamp(ring + disc, 0.0, 1.0) * uOpacity;
          gl_FragColor = vec4(min(uColor * uBrightness, vec3(1.0)), a);
        }`,
    });
  }

  private buildMarkers(): void {
    // A 1 m plane, like Unreal's basic plane, lying on the turf.
    const plane = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
    for (let i = 0; i < MaxSeats; ++i) {
      const c = Director.seatColor(i);
      const m = new THREE.Mesh(plane, this.markerMaterial(new THREE.Color(c.r, c.g, c.b), 0.72, 0.16));
      m.visible = false;
      m.renderOrder = 2;
      this.markers.push(m);
      this.scene.add(m);
    }
    this.catchMarker = new THREE.Mesh(plane, this.markerMaterial(new THREE.Color(1, 0.8, 0.13), 0.88, 0));
    this.catchMarker.visible = false;
    this.catchMarker.renderOrder = 2;
    this.scene.add(this.catchMarker);
  }

  setMarkerFill(i: number, fill: number): void {
    (this.markers[i].material as THREE.ShaderMaterial).uniforms.uFill.value = fill;
  }

  private buildLines(): void {
    // Glowing strips 14 cm wide across the whole field, the way television draws them.
    const geo = new THREE.BoxGeometry(0.14, 0.006, (SidelineY * 2) * CM);
    const make = (r: number, g: number, b: number, brightness: number) => {
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: new THREE.Color(r * brightness, g * brightness, b * brightness), toneMapped: false }));
      m.visible = false;
      this.scene.add(m);
      return m;
    };
    this.scrimmageLine = make(0.08, 0.35, 1, 1.6);
    this.firstDownLine = make(1, 0.8, 0.05, 1.8);
  }

  private buildShadows(): void {
    // Soft ground-contact blobs under every athlete: one under the body, one under each foot.
    const plane = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
    const geo = new THREE.InstancedBufferGeometry();
    geo.index = plane.index;
    geo.setAttribute('position', plane.getAttribute('position'));
    geo.setAttribute('uv', plane.getAttribute('uv'));
    const material = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      vertexShader: `
        attribute float aGain;
        varying vec2 vUv; varying float vGain;
        void main() { vUv = uv; vGain = aGain; gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0); }`,
      fragmentShader: `
        varying vec2 vUv; varying float vGain;
        void main() { vec2 p = vUv * 2.0 - 1.0; float f = clamp(1.0 - dot(p, p), 0.0, 1.0); gl_FragColor = vec4(0.0, 0.0, 0.0, f * f * vGain); }`,
    });
    this.shadows = new THREE.InstancedMesh(geo as unknown as THREE.BufferGeometry, material, NumPlayers * 3);
    this.shadowOpacity = new THREE.InstancedBufferAttribute(new Float32Array(NumPlayers * 3), 1);
    this.shadows.geometry.setAttribute('aGain', this.shadowOpacity);
    this.shadows.frustumCulled = false;
    this.shadows.renderOrder = 1;
    this.shadows.visible = false;
    this.scene.add(this.shadows);
  }

  showShadows(visible: boolean): void { if (this.shadows) this.shadows.visible = visible; }

  updateShadows(members: number[]): void {
    const a = this.anims;
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3();
    const chest = new THREE.Vector3(), footL = new THREE.Vector3(), footR = new THREE.Vector3();
    const up = new THREE.Vector3(0, 1, 0);
    members.forEach((member, i) => {
      const at = this.athletes[member];
      at.boneWorldPosition(a.spine3, chest);
      at.boneWorldPosition(a.toeL, footL);
      at.boneWorldPosition(a.toeR, footR);
      const midX = (footL.x + footR.x) / 2, midZ = (footL.z + footR.z) / 2;
      const layX = chest.x - midX, layZ = chest.z - midZ;
      const span = Math.min(1.8, Math.hypot(layX, layZ));
      const clearance = Math.max(0, Math.min(footL.y, footR.y, chest.y));
      const lift = Math.min(Math.max(clearance / 2.4, 0), 1);
      const facing = at.root.rotation.y - Math.PI / 2;     // three yaw of the character's forward (+X when 0)
      const heading = span > 0.35 ? Math.atan2(-layZ, layX) : facing;
      const base = 3 * i;
      q.setFromAxisAngle(up, heading);
      p.set((chest.x + midX) / 2, 0.016, (chest.z + midZ) / 2);
      s.set(1.04 + span + 0.35 * lift, 1, 0.9 + 0.35 * lift);
      this.shadows.setMatrixAt(base, m.compose(p, q, s));
      this.shadowOpacity.setX(base, at.visible ? 0.48 - 0.31 * lift : 0);
      [footL, footR].forEach((foot, j) => {
        q.setFromAxisAngle(up, facing);
        p.set(foot.x, 0.018, foot.z);
        s.set(0.53, 1, 0.36);
        this.shadows.setMatrixAt(base + j + 1, m.compose(p, q, s));
        this.shadowOpacity.setX(base + j + 1, at.visible ? 0.5 * Math.min(Math.max(1 - foot.y / 0.58, 0), 1) : 0);
      });
    });
    this.shadows.instanceMatrix.needsUpdate = true;
    this.shadowOpacity.needsUpdate = true;
  }

  // --- Camera and frame ------------------------------------------------------------------------

  /** Eye and target in field space (cm); FOV is horizontal degrees, as in Unreal. */
  setCamera(eye: THREE.Vector3, look: THREE.Vector3, hFovDeg: number): void {
    toThree(eye.x, eye.y, eye.z, this.camera.position);
    const target = toThree(look.x, look.y, look.z);
    this.camera.up.set(0, 1, 0);
    this.camera.lookAt(target);
    this.hFov = hFovDeg;
    this.updateProjection();
  }

  private updateProjection(): void {
    const aspect = this.width / Math.max(this.height, 1);
    this.camera.aspect = aspect;
    const h = (this.hFov * Math.PI) / 180;
    this.camera.fov = (2 * Math.atan(Math.tan(h / 2) / aspect) * 180) / Math.PI;
    this.camera.updateProjectionMatrix();
  }

  resize(width: number, height: number): void {
    this.width = width;
    this.height = height;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2) * this.renderScale);
    this.renderer.setSize(width, height, false);
    this.updateProjection();
  }

  applyOptions(options: Options): void {
    const scale = options.get(Option.RenderScale) === 0 ? 1 : options.screenPercent(this.height * devicePixelRatio) / 100;
    this.renderScale = Math.min(Math.max(scale, 0.5), 1.5);
    this.renderer.shadowMap.enabled = options.get(Option.Lighting) > 0;
    this.stadium?.setQuality(options.get(Option.Lighting), options.crowdDensity());
    this.resize(this.width, this.height);
  }

  /** Field-space point (cm) -> CSS pixels in the canvas, or null if behind the camera. */
  project(world: Vec3): Vec2 | null {
    const p = toThree(world.x, world.y, world.z);
    const view = p.clone().applyMatrix4(this.camera.matrixWorldInverse);
    if (view.z > -0.1) return null;
    p.project(this.camera);
    return new Vec2((p.x * 0.5 + 0.5) * this.width, (-p.y * 0.5 + 0.5) * this.height);
  }

  render(time: number): void {
    this.stadium?.tick(time);
    this.renderer.render(this.scene, this.camera);
  }
}

export { EndLineX };
