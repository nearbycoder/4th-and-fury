/**
 * Field space <-> three.js space.
 *
 * The simulation works in Unreal units: centimetres, X goal to goal, Y sideline to sideline (+Y is
 * the broadcast camera's side), Z up, left-handed. The art comes from Blender through glTF, where
 * Unreal (X, Y, Z) cm = Blender (X, -Y, Z) m = glTF (X, Z, Y) m. So three = (X, Z, Y) / 100.
 */
import * as THREE from 'three';
import type { Vec2, Vec3 } from '../sim/core';

export const CM = 0.01;

export function toThree(x: number, y: number, z: number, out = new THREE.Vector3()): THREE.Vector3 {
  return out.set(x * CM, z * CM, y * CM);
}
export const v3ToThree = (v: Vec3, out = new THREE.Vector3()) => toThree(v.x, v.y, v.z, out);
export const v2ToThree = (v: Vec2, z = 0, out = new THREE.Vector3()) => toThree(v.x, v.y, z, out);
/** three.js point -> field space (cm), as plain numbers. */
export function fromThree(p: THREE.Vector3): { x: number; y: number; z: number } {
  return { x: p.x / CM, y: p.z / CM, z: p.y / CM };
}

/**
 * The rotation about three's Y axis that turns a glTF character (facing +Z) to face the field yaw
 * (radians, 0 = +X, increasing toward +Y, as in the simulation).
 */
export const yawToThree = (yaw: number) => Math.PI / 2 - yaw;

/** sRGB hex ("#RRGGBB") -> THREE.Color (linear working space). */
export function hexColor(hex: string): THREE.Color {
  return new THREE.Color().setStyle(hex, THREE.SRGBColorSpace);
}
/** FLinearColor-style linear components -> THREE.Color. */
export const linearColor = (r: number, g: number, b: number) => new THREE.Color(r, g, b);
