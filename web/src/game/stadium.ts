/**
 * The arena (port of AFuryStadium): the bowl with its slot materials, the painted turf with both
 * end zones and the midfield emblem, the night sky, props from the art metadata, the chains and
 * down box, the crowd, and the floodlight banks.
 *
 * Art metadata is in Blender metres (Z up, +Y away from the camera side). Blender (x, y, z) is
 * three (x, z, -y).
 */
import * as THREE from 'three';
import type { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { SidelineY, Yard, type Team } from '../sim/core';
import meta from './data/stadium_meta.json';
import { CM, hexColor, toThree } from './space';
import { asset } from './world';

type LoadTex = (path: string, srgb: boolean, flipY?: boolean) => Promise<THREE.Texture>;
const fromBlender = (p: number[], out = new THREE.Vector3()) => out.set(p[0], p[2], -p[1]);

/** A lit surface with optional grime and detail normal (M_Surface). */
function surface(color: [number, number, number], roughness: number, metalness = 0): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color: new THREE.Color(...color), roughness, metalness });
}

export class Stadium {
  private group = new THREE.Group();
  private fieldMaterial!: THREE.MeshStandardMaterial;
  private fieldUniforms = {
    uField: { value: null as THREE.Texture | null },
    uEndLeft: { value: null as THREE.Texture | null },
    uEndRight: { value: null as THREE.Texture | null },
    uMidLogo: { value: null as THREE.Texture | null },
    uGrass: { value: null as THREE.Texture | null },
    uLines: { value: null as THREE.Texture | null },
  };
  private seatA = surface([0.2, 0.02, 0.03], 0.6);
  private seatB = surface([0.03, 0.04, 0.08], 0.6);
  private wallPad = surface([0.02, 0.05, 0.14], 0.55);
  private goalPad = surface([0.3, 0.02, 0.02], 0.6);
  private adsMaterial: THREE.Material | null = null;
  private screenMaterial = new THREE.MeshBasicMaterial({ color: new THREE.Color(0.01, 0.012, 0.02) });
  private chainPoles: THREE.Object3D[] = [];
  private downBox: THREE.Object3D | null = null;
  private downFace: THREE.MeshBasicMaterial | null = null;
  private downDigits: (THREE.Texture | null)[] = [];
  private crowdUniforms = {
    uHome: { value: new THREE.Color(0.8, 0.1, 0.1) },
    uAway: { value: new THREE.Color(0.1, 0.2, 0.8) },
    uExcitement: { value: 0.2 },
    uTime: { value: 0 },
  };
  private crowd: THREE.InstancedMesh[] = [];
  private seats: { x: number; y: number; z: number }[] = [];
  private lights: THREE.SpotLight[] = [];
  private shown = { down: -1, line: 0, target: 0, direction: 0, goal: false };
  private endZones = new Map<string, THREE.Texture>();
  private boardTexture: THREE.Texture | null = null;

  constructor(private scene: THREE.Scene, private gltf: GLTFLoader, private loadTex: LoadTex) {
    scene.add(this.group);
  }

  async load(): Promise<void> {
    const [bowl, field, grass, lines, sky, ads, ...props] = await Promise.all([
      this.gltf.loadAsync(asset('stadium/stadium.glb')),
      this.loadTex('textures/field.webp', true),
      this.loadTex('textures/detail/grass_m.webp', false).catch(() => null),
      this.loadTex('textures/field_lines.png', false).catch(() => null),
      this.loadTex('textures/night_sky.webp', true).catch(() => null),
      this.loadTex('textures/ads.webp', true).catch(() => null),
      ...['goalpost', 'pylon', 'bench', 'cooler', 'chainpole', 'downbox', 'camera'].map((n) => this.gltf.loadAsync(asset(`stadium/${n}.glb`))),
    ]);
    if (grass) { grass.wrapS = grass.wrapT = THREE.RepeatWrapping; }
    if (ads) { ads.wrapS = THREE.RepeatWrapping; this.adsMaterial = this.makeAds(ads); }
    this.downDigits = await Promise.all([1, 2, 3, 4].map((d) => this.loadTex(`textures/down_${d}.png`, true).catch(() => null)));

    // Turf: one plane, 128 m x 64 m, painted by the field material.
    this.fieldUniforms.uField.value = field;
    this.fieldUniforms.uGrass.value = grass;
    this.fieldUniforms.uLines.value = lines;
    this.fieldMaterial = this.makeField();
    const turf = new THREE.Mesh(new THREE.PlaneGeometry(128, 64).rotateX(-Math.PI / 2), this.fieldMaterial);
    turf.receiveShadow = true;
    this.group.add(turf);

    // The bowl.
    this.applySlotMaterials(bowl.scene);
    bowl.scene.traverse((o) => { if ((o as THREE.Mesh).isMesh) { o.receiveShadow = true; o.castShadow = false; } });
    this.group.add(bowl.scene);

    // Night sky: a huge inward-facing sphere.
    if (sky) {
      const dome = new THREE.Mesh(new THREE.SphereGeometry(450, 48, 24), new THREE.MeshBasicMaterial({ map: sky, side: THREE.BackSide, color: new THREE.Color(0.55, 0.55, 0.55), fog: false }));
      sky.flipY = true;
      sky.needsUpdate = true;
      this.group.add(dome);
    }

    // Props from the art metadata.
    const propScenes: Record<string, THREE.Object3D> = {
      SM_Goalpost: props[0].scene, SM_Pylon: props[1].scene, SM_Bench: props[2].scene, SM_Cooler: props[3].scene,
      SM_ChainPole: props[4].scene, SM_DownBox: props[5].scene, SM_Camera: props[6].scene,
    };
    for (const [name, entries] of Object.entries(meta.suggested_props as Record<string, { pos: number[]; yaw: number }[]>)) {
      const source = propScenes[name];
      if (!source) continue;      // the game places the tee itself
      for (const e of entries) {
        const prop = source.clone(true);
        fromBlender(e.pos, prop.position);
        prop.rotation.y = e.yaw;
        this.applySlotMaterials(prop);
        prop.traverse((o) => { if ((o as THREE.Mesh).isMesh) { o.castShadow = true; o.receiveShadow = true; } });
        this.group.add(prop);
        if (name === 'SM_ChainPole') { this.chainPoles.push(prop); prop.visible = false; }
        if (name === 'SM_DownBox') { this.downBox = prop; prop.visible = false; }
      }
    }

    await this.buildCrowd();
    this.buildLights();

    // A touch of haze for the floodlights to shine through.
    this.scene.fog = new THREE.FogExp2(new THREE.Color(0.035, 0.045, 0.07), 0.0028);
  }

  // --- Materials ---------------------------------------------------------------------------------

  private applySlotMaterials(root: THREE.Object3D): void {
    const orange: [number, number, number] = [1, 0.32, 0.02];
    root.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      const replaced = mats.map((m) => {
        switch (m.name) {
          case 'Concrete': return surface([0.36, 0.36, 0.37], 0.86);
          case 'ConcreteDark': return surface([0.045, 0.045, 0.05], 0.9);
          case 'SeatA': return this.seatA;
          case 'SeatB': return this.seatB;
          case 'Steel': return surface([0.3, 0.32, 0.35], 0.42, 0.9);
          case 'Glass': return surface([0.012, 0.02, 0.035], 0.08, 0.7);
          case 'WallPad': return this.wallPad;
          case 'LampHousing': return surface([0.04, 0.04, 0.045], 0.5, 0.7);
          case 'Apron': return surface([0.05, 0.075, 0.055], 0.92);
          case 'Roof': return surface([0.07, 0.075, 0.085], 0.5, 0.6);
          case 'GoalYellow': return surface([0.95, 0.72, 0.03], 0.35, 0.2);
          case 'GoalPad': return this.goalPad;
          case 'Leather': return surface([0.25, 0.095, 0.04], 0.5);
          case 'Laces': case 'BallStripe': return surface([0.9, 0.9, 0.88], 0.6);
          case 'Tee': case 'CoolerBody': case 'MarkerOrange': return surface(orange, 0.45);
          case 'Pylon': {
            const p = surface(orange, 0.5);
            p.emissive = new THREE.Color(...orange).multiplyScalar(0.6);
            return p;
          }
          case 'BenchSeat': return surface([0.07, 0.075, 0.09], 0.6);
          case 'DownFace': {
            this.downFace = new THREE.MeshBasicMaterial({ color: new THREE.Color(1.15, 1.15, 1.15), toneMapped: false });
            return this.downFace;
          }
          case 'CameraBody': return surface([0.03, 0.03, 0.035], 0.4, 0.3);
          case 'AdBoard': return this.adsMaterial ?? m;
          case 'Lamp': return new THREE.MeshBasicMaterial({ color: new THREE.Color(1, 0.97, 0.9).multiplyScalar(4), toneMapped: false, fog: false });
          case 'Screen': case 'ScreenSmall': return this.screenMaterial;
          default: return m;
        }
      });
      mesh.material = Array.isArray(mesh.material) ? replaced : replaced[0];
    });
  }

  /** The ad boards: eight boards in one strip; U counts boards along the wall (M_Ads). */
  private makeAds(tex: THREE.Texture): THREE.Material {
    const mat = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.55, emissive: new THREE.Color(1, 1, 1), emissiveMap: tex, emissiveIntensity: 0.6 });
    mat.onBeforeCompile = (shader) => {
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <map_fragment>', `
          vec2 adUv = vec2((mod(floor(vMapUv.x) + 8000.0, 8.0) + fract(vMapUv.x)) / 8.0, vMapUv.y);
          vec4 sampledDiffuseColor = texture2D(map, adUv);
          diffuseColor *= sampledDiffuseColor;`)
        .replace('#include <emissivemap_fragment>', 'totalEmissiveRadiance *= texture2D(emissiveMap, adUv).rgb;');
    };
    return mat;
  }

  /** The turf: painted field texture, team end zones and a midfield emblem, grass detail (M_Field). */
  private makeField(): THREE.MeshStandardMaterial {
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.9, metalness: 0 });
    const u = this.fieldUniforms;
    mat.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, u);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec2 vFieldM;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvFieldM = vec2(position.x, position.z);');
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>
          varying vec2 vFieldM;
          uniform sampler2D uField, uEndLeft, uEndRight, uMidLogo, uGrass, uLines;
          // The field texture covers 128 m x 64 m. End zones are 9.14 m deep and 48.77 m wide.
          vec3 zone(vec2 m, float side) {
            float depth = (54.86 - abs(m.x)) / 9.14;              // 0 at the end line, 1 at the goal line
            float across = (m.y * side + 24.385) / 48.77;         // reads left to right for someone standing on the field
            float inside = step(0.012, depth) * step(depth, 0.972) * step(0.004, across) * step(across, 0.996) * step(0.0, m.x * side);
            return vec3(across, depth, inside);
          }`)
        .replace('#include <map_fragment>', `
          vec2 m = vFieldM;                                       // metres from midfield; +x right, +y toward the camera
          vec2 fuv = m / vec2(128.0, 64.0) + 0.5;
          vec3 paint = texture2D(uField, fuv).rgb;
          vec3 l = zone(m, -1.0);
          paint = mix(paint, texture2D(uEndLeft, l.xy).rgb, l.z);
          vec3 r = zone(m, 1.0);
          paint = mix(paint, texture2D(uEndRight, r.xy).rgb, r.z);
          vec2 lp = m / 13.0 + 0.5;
          float li = step(0.0, lp.x) * step(lp.x, 1.0) * step(0.0, lp.y) * step(lp.y, 1.0);
          vec4 logo = texture2D(uMidLogo, lp);
          paint = mix(paint, logo.rgb, logo.a * li * 0.85);
          // Grass: clumpy brightness variation tiled across the turf.
          float clumps = texture2D(uGrass, fuv * 9.0).r;
          paint *= mix(0.82, 1.1, clumps);
          // Under floodlights the painted turf reads too neon; pull it toward a deeper, calmer green.
          float grey = dot(paint, vec3(0.3, 0.59, 0.11));
          paint = mix(vec3(grey), paint, 0.82) * vec3(0.62, 0.66, 0.62);
          diffuseColor.rgb = paint;`)
        .replace('#include <roughnessmap_fragment>', `
          float roughnessFactor = mix(0.93, 0.72, texture2D(uLines, vFieldM / vec2(128.0, 64.0) + 0.5).r);`);
    };
    return mat;
  }

  // --- Crowd ---------------------------------------------------------------------------------------

  private async buildCrowd(): Promise<void> {
    // crowd_instances.bin (web/tools/convert_crowd.py): "FCRD", version, count, record size, then per
    // spectator float32 x, y, z, yaw (three.js space, metres; yaw 0 faces +Z) and uint8 kind, flags,
    // scale, rand. The empty seats and the stand/sit/arms-up rolls of FuryStadium.cpp are already made.
    const [bin, ...meshes] = await Promise.all([
      fetch(asset('stadium/crowd_instances.bin')).then((r) => (r.ok ? r.arrayBuffer() : null)).catch(() => null),
      ...['crowdA', 'crowdB', 'crowdC'].map((n) => this.gltf.loadAsync(asset(`stadium/${n}.glb`))),
    ]);
    if (!bin || bin.byteLength < 16 || new TextDecoder().decode(new Uint8Array(bin, 0, 4)) !== 'FCRD') { console.warn('Stadium: no crowd data'); return; }
    const view = new DataView(bin);
    const count = view.getUint32(8, true), stride = view.getUint32(12, true);
    const kinds: { m: THREE.Matrix4; section: number; rand: number }[][] = [[], [], []];
    const q = new THREE.Quaternion(), p = new THREE.Vector3(), s = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
    for (let i = 0; i < count; ++i) {
      const o = 16 + i * stride;
      if (o + 20 > bin.byteLength) break;
      p.set(view.getFloat32(o, true), view.getFloat32(o + 4, true), view.getFloat32(o + 8, true));
      const yaw = view.getFloat32(o + 12, true);
      const kind = Math.min(view.getUint8(o + 16), 2), flags = view.getUint8(o + 17);
      s.setScalar(0.92 + (0.16 * view.getUint8(o + 18)) / 255);
      q.setFromAxisAngle(up, yaw);
      kinds[kind].push({ m: new THREE.Matrix4().compose(p, q, s), section: flags & 1, rand: view.getUint8(o + 19) / 255 });
      if (flags & 2) this.seats.push({ x: p.x / CM, y: p.z / CM, z: p.y / CM + 110 });
    }
    const material = this.makeCrowdMaterial();
    kinds.forEach((list, k) => {
      let geometry: THREE.BufferGeometry | null = null;
      meshes[k].scene.traverse((o) => { if ((o as THREE.Mesh).isMesh && !geometry) geometry = (o as THREE.Mesh).geometry; });
      if (!geometry || list.length === 0) return;
      const geo = geometry as THREE.BufferGeometry;
      const inst = new THREE.InstancedMesh(geo, material, list.length);
      const section = new Float32Array(list.length), rand = new Float32Array(list.length);
      list.forEach((e, i) => { inst.setMatrixAt(i, e.m); section[i] = e.section; rand[i] = e.rand; });
      geo.setAttribute('aSection', new THREE.InstancedBufferAttribute(section, 1));
      geo.setAttribute('aRand', new THREE.InstancedBufferAttribute(rand, 1));
      inst.frustumCulled = false;
      this.crowd.push(inst);
      this.group.add(inst);
    });
  }

  /** Instanced spectators: shirt colours picked per instance, and a bounce that grows with the noise (M_Crowd). */
  private makeCrowdMaterial(): THREE.MeshStandardMaterial {
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.85, vertexColors: false });
    const u = this.crowdUniforms;
    mat.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, u);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>
          attribute vec4 color;
          attribute float aSection;
          attribute float aRand;
          uniform vec3 uHome, uAway;
          uniform float uExcitement, uTime;
          varying vec3 vDress;`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>
          {
            float Rand = aRand;
            // Most of a section wears its team's colour; the rest wear whatever they like.
            float pick = fract(Rand * 7.31);
            vec3 team = aSection > 0.5 ? uAway : uHome;
            vec3 other = aSection > 0.5 ? uHome : uAway;
            vec3 neutral = mix(vec3(0.75, 0.75, 0.78), vec3(0.07, 0.08, 0.1), step(0.5, fract(Rand * 23.7)));
            vec3 shirt = pick < 0.62 ? team : (pick < 0.72 ? other : neutral);
            shirt *= mix(0.7, 1.1, fract(Rand * 91.7));
            vec3 skin = mix(vec3(0.75, 0.52, 0.38), vec3(0.2, 0.11, 0.06), fract(Rand * 3.77));
            vec3 hair = mix(vec3(0.03, 0.025, 0.02), vec3(0.3, 0.2, 0.1), fract(Rand * 13.1));
            vec3 legs = vec3(0.05, 0.06, 0.09);
            float sum = clamp(color.r + color.g + color.b, 0.0, 1.0);
            vDress = shirt * color.r + skin * color.g + hair * color.b + legs * (1.0 - sum);
            // Each fan hops on their own beat; louder moments mean bigger, faster hops and more people on their feet.
            float phase = Rand * 6.2832;
            float speed = mix(3.0, 9.0, uExcitement) * mix(0.8, 1.2, fract(Rand * 5.3));
            float hop = max(0.0, sin(uTime * speed + phase));
            float keen = step(1.0 - uExcitement * 0.9, fract(Rand * 41.3));
            transformed.y += color.a * hop * hop * mix(0.02, 0.26, uExcitement) * mix(0.25, 1.0, keen);
          }`);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vDress;')
        .replace('#include <color_fragment>', 'diffuseColor.rgb *= vDress;');
    };
    return mat;
  }

  // --- Lights --------------------------------------------------------------------------------------

  private buildLights(): void {
    for (let i = 0; i < meta.lights.length; ++i) {
      const bank = meta.lights[i];
      const light = new THREE.SpotLight(new THREE.Color(1, 0.97, 0.92), 11000, 260, (62 * Math.PI) / 180, 1 - 38 / 62, 2);
      fromBlender(bank.pos, light.position);
      fromBlender(bank.aim, light.target.position);
      // One key bank casts the long turf shadows. The other banks light the far side and uniforms.
      light.castShadow = i === 0;
      light.shadow.mapSize.set(2048, 2048);
      light.shadow.camera.near = 20;
      light.shadow.camera.far = 200;
      light.shadow.bias = -0.0004;
      light.shadow.normalBias = 0.02;
      this.group.add(light, light.target);
      this.lights.push(light);
    }
    // Ambient light from the sky dome.
    this.group.add(new THREE.HemisphereLight(new THREE.Color(0.16, 0.19, 0.27), new THREE.Color(0.05, 0.07, 0.05), 1.2));
  }

  setQuality(lighting: number, crowdDensity: number): void {
    const banks = [0, 1, 2, 4][lighting] ?? 1;
    this.lights.forEach((l, i) => { l.castShadow = i < banks; });
    for (const c of this.crowd) {
      const total = (c.instanceMatrix.array.length / 16) | 0;
      c.count = Math.max(1, Math.round(total * Math.min(Math.max(crowdDensity, 0.1), 1)));
    }
  }

  // --- Match dressing ------------------------------------------------------------------------------

  private async endZone(id: string): Promise<THREE.Texture | null> {
    let t = this.endZones.get(id);
    if (!t) {
      t = await this.loadTex(`textures/endzone_${id}.webp`, true).catch(() => undefined);
      if (t) this.endZones.set(id, t);
    }
    return t ?? null;
  }

  dress(home: Team, away: Team, homeLogo?: THREE.Texture | null): void {
    // The home side defends the left end zone; its emblem sits at midfield.
    void this.endZone(home.id).then((t) => { this.fieldUniforms.uEndLeft.value = t; });
    void this.endZone(away.id).then((t) => { this.fieldUniforms.uEndRight.value = t; });
    if (homeLogo !== undefined) this.fieldUniforms.uMidLogo.value = homeLogo;
    else void this.loadTex(`textures/logo_${home.id}.webp`, true).then((t) => { this.fieldUniforms.uMidLogo.value = t; }).catch(() => undefined);
    const dim = (hex: string, s: number) => hexColor(hex).multiplyScalar(s);
    this.seatA.color.copy(dim(home.primary, 0.45));
    this.seatB.color.copy(dim(home.secondary, 0.25));
    this.wallPad.color.copy(dim(home.primary, 0.6));
    this.goalPad.color.copy(dim(home.primary, 0.8));
    // A home crowd: both seat sections lean toward the home colours, the "away" blocks only partly.
    this.crowdUniforms.uHome.value.copy(dim(home.primary, 0.9));
    this.crowdUniforms.uAway.value.copy(dim(home.secondary, 0.8).lerp(dim(away.primary, 0.9), 0.35));
  }

  setExcitement(value: number): void { this.crowdUniforms.uExcitement.value = Math.min(Math.max(value, 0), 1); }

  setChains(down: number, line: number, target: number, direction: number, goalToGo: boolean): void {
    const s = this.shown;
    if (down === s.down && (down === 0 || (line === s.line && target === s.target && direction === s.direction && goalToGo === s.goal))) return;
    Object.assign(s, { down, line, target, direction, goal: goalToGo });
    if (this.downBox) {
      this.downBox.visible = down > 0;
      toThree(line, -SidelineY - 145, 0, this.downBox.position);
      const digit = this.downDigits[down - 1];
      if (this.downFace && digit) { this.downFace.map = digit; this.downFace.needsUpdate = true; }
    }
    this.chainPoles.forEach((pole, i) => {
      pole.visible = down > 0 && !goalToGo;
      toThree(i === 0 ? target - direction * 30 * Yard : target, -SidelineY - 88, 0, pole.position);
    });
  }

  /** Points in the stands (field space, cm) where camera flashes go off. */
  seatSample(): { x: number; y: number; z: number }[] { return this.seats; }

  /** The video board shows whatever the HUD draws into this canvas. */
  setBoard(canvas: HTMLCanvasElement): void {
    if (!this.boardTexture) {
      this.boardTexture = new THREE.CanvasTexture(canvas);
      this.boardTexture.colorSpace = THREE.SRGBColorSpace;
      this.boardTexture.flipY = false;      // glTF UVs put v = 0 at the top of the image
      this.screenMaterial.map = this.boardTexture;
      this.screenMaterial.color.setRGB(2.2, 2.2, 2.2);
      this.screenMaterial.toneMapped = false;
      this.screenMaterial.needsUpdate = true;
    }
    this.boardTexture.needsUpdate = true;
  }

  tick(time: number): void { this.crowdUniforms.uTime.value = time; }
}
