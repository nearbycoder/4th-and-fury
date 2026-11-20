/**
 * Sparks, dust, flames and fireworks (port of FFuryFX): a small CPU particle system drawn as
 * camera-facing additive quads through one instanced mesh. Positions are field space (cm).
 */
import * as THREE from 'three';
import { RandomStream } from '../sim/core';
import { CM } from './space';
import type { Color } from './director';

const MaxParticles = 5000;

interface Particle {
  px: number; py: number; pz: number;
  vx: number; vy: number; vz: number;
  r: number; g: number; b: number;
  life: number; maxLife: number; size: number; growth: number; brightness: number; gravity: number; drag: number;
}

export type V3 = { x: number; y: number; z: number };

export class FuryFX {
  particleDensity = 1;
  readonly mesh: THREE.Mesh;
  private particles: Particle[] = [];
  private random = new RandomStream(4242);
  private pos: Float32Array;
  private data: Float32Array;
  private geometry: THREE.InstancedBufferGeometry;

  constructor() {
    const quad = new THREE.PlaneGeometry(1, 1);
    this.geometry = new THREE.InstancedBufferGeometry();
    this.geometry.index = quad.index;
    this.geometry.setAttribute('position', quad.getAttribute('position'));
    this.geometry.setAttribute('uv', quad.getAttribute('uv'));
    this.pos = new Float32Array(MaxParticles * 4);
    this.data = new Float32Array(MaxParticles * 4);
    this.geometry.setAttribute('iPos', new THREE.InstancedBufferAttribute(this.pos, 4).setUsage(THREE.DynamicDrawUsage));
    this.geometry.setAttribute('iData', new THREE.InstancedBufferAttribute(this.data, 4).setUsage(THREE.DynamicDrawUsage));
    this.geometry.instanceCount = 0;
    const material = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: `
        attribute vec4 iPos;   // xyz (three space, metres), size (metres)
        attribute vec4 iData;  // rgb, strength
        varying vec2 vUv;
        varying vec4 vData;
        void main() {
          vUv = uv;
          vData = iData;
          vec4 mv = modelViewMatrix * vec4(iPos.xyz, 1.0);
          mv.xy += position.xy * iPos.w;
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        varying vec2 vUv;
        varying vec4 vData;
        void main() {
          float soft = pow(clamp(1.0 - length(vUv * 2.0 - 1.0), 0.0, 1.0), 1.8);
          gl_FragColor = vec4(vData.rgb * vData.a * soft, 1.0);
        }`,
    });
    this.mesh = new THREE.Mesh(this.geometry, material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 10;
  }

  clear(): void { this.particles.length = 0; }

  /** One particle with full control. */
  emit(o: V3, v: V3, c: Color, life: number, size: number, brightness: number, gravity = 0, drag = 1.5, growth = 0): void {
    if (this.particles.length >= MaxParticles) return;
    this.particles.push({ px: o.x, py: o.y, pz: o.z, vx: v.x, vy: v.y, vz: v.z, r: c.r, g: c.g, b: c.b, life, maxLife: life, size, growth, brightness, gravity, drag });
  }

  private vRand(): V3 {
    // Uniform direction on the unit sphere (FRandomStream::VRand).
    for (;;) {
      const x = this.random.fRand() * 2 - 1, y = this.random.fRand() * 2 - 1, z = this.random.fRand() * 2 - 1;
      const l = x * x + y * y + z * z;
      if (l > 1e-4 && l <= 1) { const s = 1 / Math.sqrt(l); return { x: x * s, y: y * s, z: z * s }; }
    }
  }

  /** A spray of particles flying out from a point. */
  burst(o: V3, c: Color, count: number, speed: number, life: number, size: number, brightness = 3, gravity = 500, upBias = 0.4): void {
    count = Math.round(count * this.particleDensity);
    for (let i = 0; i < count; ++i) {
      const d = this.vRand();
      d.z = Math.abs(d.z) * (1 - upBias) + upBias;
      const len = Math.hypot(d.x, d.y, d.z) || 1;
      const s = (speed * this.random.fRandRange(0.35, 1)) / len;
      this.emit(o, { x: d.x * s, y: d.y * s, z: d.z * s }, c, life * this.random.fRandRange(0.6, 1), size * this.random.fRandRange(0.6, 1.2), brightness, gravity, 1.6);
    }
  }

  /** A firework shell: a bright core and a sphere of falling embers. */
  firework(o: V3, c: Color, scale = 1): void {
    this.emit(o, { x: 0, y: 0, z: 0 }, { r: 1, g: 1, b: 1, a: 1 }, 0.25, 900 * scale, 6, 0, 0, 2500);
    const count = Math.round(90 * this.particleDensity);
    for (let i = 0; i < count; ++i) {
      const d = this.vRand();
      const t = this.random.fRandRange(0, 0.35);
      const tint = { r: c.r + (1 - c.r) * t, g: c.g + (1 - c.g) * t, b: c.b + (1 - c.b) * t, a: 1 };
      const s = 1500 * scale * this.random.fRandRange(0.6, 1);
      this.emit(o, { x: d.x * s, y: d.y * s, z: d.z * s }, tint, this.random.fRandRange(1.1, 1.9), 70 * scale, 5, 260, 1.3, -18);
    }
  }

  /** A lick of flame at a point (Fury mode). */
  flame(o: V3, drift: V3): void {
    const jx = this.random.fRandRange(-22, 22), jy = this.random.fRandRange(-22, 22), jz = this.random.fRandRange(0, 30);
    const t = this.random.fRand();
    const c = { r: 1, g: 0.55 + (0.16 - 0.55) * t, b: 0.08 + (0.02 - 0.08) * t, a: 1 };
    const vx = this.random.fRandRange(-30, 30), vy = this.random.fRandRange(-30, 30), vz = this.random.fRandRange(120, 260);
    const life = this.random.fRandRange(0.28, 0.5), size = this.random.fRandRange(34, 58);
    this.emit({ x: o.x + jx, y: o.y + jy, z: o.z + jz }, { x: drift.x + vx, y: drift.y + vy, z: drift.z + vz }, c, life, size, 2.4, -40, 1.2, -60);
  }

  tick(dt: number): void {
    const ps = this.particles;
    let used = 0;
    for (let i = ps.length - 1; i >= 0; --i) {
      const p = ps[i];
      p.life -= dt;
      if (p.life <= 0) { ps[i] = ps[ps.length - 1]; ps.pop(); continue; }
      p.vz -= p.gravity * dt;
      const k = Math.exp(-p.drag * dt);
      p.vx *= k; p.vy *= k; p.vz *= k;
      p.px += p.vx * dt; p.py += p.vy * dt; p.pz += p.vz * dt;
      if (p.pz < 4 && p.gravity > 0) {
        p.pz = 4;
        p.vx *= 0.5; p.vy *= 0.5; p.vz = Math.abs(p.vz) * 0.25;
      }
      p.size = Math.max(1, p.size + p.growth * dt);
      const age = p.life / p.maxLife;                      // 1 new .. 0 gone
      const fade = Math.min(1, age * 2.2);
      const j = used * 4;
      this.pos[j] = p.px * CM; this.pos[j + 1] = p.pz * CM; this.pos[j + 2] = p.py * CM; this.pos[j + 3] = p.size * CM;
      this.data[j] = p.r; this.data[j + 1] = p.g; this.data[j + 2] = p.b; this.data[j + 3] = p.brightness * fade;
      ++used;
    }
    this.geometry.instanceCount = used;
    (this.geometry.getAttribute('iPos') as THREE.InstancedBufferAttribute).needsUpdate = true;
    (this.geometry.getAttribute('iData') as THREE.InstancedBufferAttribute).needsUpdate = true;
  }
}
