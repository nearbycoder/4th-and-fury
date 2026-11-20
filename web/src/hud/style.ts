/**
 * Colours and button ids shared by the interface code (port of FuryHUDStyle.h), plus the colour
 * helpers the C++ gets from FLinearColor.
 *
 * Every Color is LINEAR RGBA, exactly like the FLinearColor values in the C++. Unreal's canvas
 * gamma-corrects vertex colours in the pixel shader and blends in gamma space, so the browser
 * equivalent is: convert rgb to sRGB, keep alpha as-is (see css()).
 */
import { rgba, type Color } from '../game/director';

export type { Color };
export { rgba };

export const Ink = rgba(0.012, 0.014, 0.02);
export const Slate = rgba(0.045, 0.05, 0.065);
export const White = rgba(1, 1, 1);
export const Dim = rgba(0.6, 0.63, 0.68);
export const Blaze = rgba(1, 0.3, 0.03);     // the game's own orange
export const Gold = rgba(1, 0.76, 0.07);
export const Good = rgba(0.2, 0.88, 0.34);
export const Bad = rgba(0.93, 0.18, 0.14);

/** FuryUI::EButton: the prompts the HUD can show. */
export enum UIButton { A, B, X, Y, LB, RB, Start, Stick, Turbo }

// ---------------------------------------------------------------------------------------------
// FLinearColor helpers
// ---------------------------------------------------------------------------------------------

export const fade = (c: Color, alpha: number): Color => ({ r: c.r, g: c.g, b: c.b, a: c.a * alpha });

/** AFuryHUD::InkOn: dark type on light backgrounds. Returns the shared constants, so callers may compare with ===. */
export function inkOn(background: Color): Color {
  const luma = 0.2126 * background.r + 0.7152 * background.g + 0.0722 * background.b;
  return luma > 0.45 ? Ink : White;
}

/** FLinearColor::GetLuminance. */
export const luminance = (c: Color) => c.r * 0.3 + c.g * 0.59 + c.b * 0.11;

/** FMath::Lerp on FLinearColor. */
export const lerpColor = (a: Color, b: Color, t: number): Color =>
  ({ r: a.r + (b.r - a.r) * t, g: a.g + (b.g - a.g) * t, b: a.b + (b.b - a.b) * t, a: a.a + (b.a - a.a) * t });

/** AFuryHUD::Ease: ease-out cubic on 0..1. */
export function ease(t: number): number {
  t = Math.min(Math.max(t, 0), 1);
  return 1 - Math.pow(1 - t, 3);
}

export const sameColor = (a: Color, b: Color) => a === b || (a.r === b.r && a.g === b.g && a.b === b.b && a.a === b.a);

function toSrgb(v: number): number {
  const c = v <= 0 ? 0 : v >= 1 ? 1 : v;
  const s = c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
  return Math.round(s * 255);
}
function fromSrgb(byte: number): number {
  const c = byte / 255;
  return c > 0.04045 ? Math.pow((c + 0.055) / 1.055, 2.4) : c / 12.92;
}

/** A linear colour as a CSS colour string (sRGB channels, alpha unchanged). */
export function css(c: Color): string {
  const a = c.a <= 0 ? 0 : c.a >= 1 ? 1 : c.a;
  return `rgba(${toSrgb(c.r)},${toSrgb(c.g)},${toSrgb(c.b)},${a.toFixed(4)})`;
}

const hexCache = new Map<string, Color>();
/** Fury::Hex: an sRGB "#RRGGBB" team colour as a linear Color (what FFuryTeam holds in the C++). */
export function hex(code: string): Color {
  let c = hexCache.get(code);
  if (!c) {
    const h = code.replace('#', '');
    c = rgba(fromSrgb(parseInt(h.slice(0, 2), 16)), fromSrgb(parseInt(h.slice(2, 4), 16)), fromSrgb(parseInt(h.slice(4, 6), 16)));
    hexCache.set(code, c);
  }
  return c;
}
