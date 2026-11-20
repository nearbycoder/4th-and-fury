/**
 * The drawing kit (port of the AFuryHUD kit and shared widgets in FuryHUD.h / FuryHUD.cpp).
 *
 * Layout is authored on a 1920 x 1080 board; the kit scales it to the canvas and letterboxes when
 * the canvas is not 16:9 (S, OX, OY exactly as DrawHUD computes them). Kit functions take board
 * coordinates; the canvas is drawn in device pixels.
 */
import { Director } from '../game/director';
import { FuryInput } from '../game/input';
import { MaxSeats, NONE, Vec2, Vec3 } from '../sim/index';
import { Align, Face, Faces } from './fonts';
import { css, fade, inkOn, Ink, Slate, UIButton, White, rgba, type Color } from './style';

export { Align, Face };

const BoardW = 1920, BoardH = 1080;
const v = (x: number, y: number) => new Vec2(x, y);
/** FMath::RoundToFloat (round half up). */
const round = (x: number) => Math.floor(x + 0.5);

interface FontSetup { font: string; px: number; baseline: number; height: number }

export class Kit {
  readonly ctx: CanvasRenderingContext2D;
  S = 1; OX = 0; OY = 0;
  /** Device pixels per CSS pixel, to map Director.worldToScreen (CSS px) onto the board. */
  dpr = 1;
  /** The director being drawn this frame (AFuryHUD::Hud). */
  hud: Director | null = null;
  sharedPromptPad = NONE;

  /** Whole-pixel glyph advances per font ("font|char"). */
  private readonly advanceCache = new Map<string, number>();
  private scratch: HTMLCanvasElement | null = null;

  constructor(ctx: CanvasRenderingContext2D) {
    this.ctx = ctx;
  }

  /** Points the kit at a canvas of the given device size (DrawHUD's S / OX / OY). */
  layout(width: number, height: number): void {
    this.S = Math.min(width / BoardW, height / BoardH);
    this.OX = (width - BoardW * this.S) * 0.5;
    this.OY = (height - BoardH * this.S) * 0.5;
  }

  now(): number { return this.hud ? this.hud.now() : performance.now() / 1000; }
  boardScale(): number { return this.S; }
  toScreen(p: Vec2): Vec2 { return v(this.OX + p.x * this.S, this.OY + p.y * this.S); }
  private sx(x: number): number { return this.OX + x * this.S; }
  private sy(y: number): number { return this.OY + y * this.S; }

  // -------------------------------------------------------------------------------------------
  // Type
  // -------------------------------------------------------------------------------------------

  /**
   * AFuryHUD::Font. Size is the em height in board pixels; Slate sizes are points at 96 DPI and
   * whole points only.
   *
   * Unreal's FCanvasTextItem (and FSlateFontMeasure) lay text out with the legacy per-character
   * list: every glyph advances by its own whole-pixel advance, kerning comes only from an old-style
   * 'kern' table (these fonts have none, only GPOS) and FSlateFontInfo::LetterSpacing is never
   * applied. The kit does the same, so `spacing` arguments are accepted for 1:1 call sites but have
   * no effect, exactly as in the shipped game (verified against Docs/title.jpg).
   */
  font(face: Face, size: number, _spacing = 0): FontSetup {
    const pt = Math.max(1, round(size * this.S * 0.75));
    const px = (pt * 96) / 72;
    const info = Faces[face];
    return {
      font: `${px}px ${info.family}`,
      px,
      baseline: round(info.height * px) + round(info.descender * px),
      height: round(info.height * px),
    };
  }

  private advance(ch: string, f: FontSetup): number {
    const key = f.font + '|' + ch;
    let a = this.advanceCache.get(key);
    if (a === undefined) {
      this.ctx.font = f.font;
      a = round(this.ctx.measureText(ch).width);
      if (this.advanceCache.size > 20000) this.advanceCache.clear();
      this.advanceCache.set(key, a);
    }
    return a;
  }

  private rawWidth(str: string, f: FontSetup): number {
    let w = 0;
    for (const ch of str) w += this.advance(ch, f);
    return w;
  }

  /** AFuryHUD::Measure: size of the text box in board pixels. */
  measure(str: string, face: Face, size: number, spacing = 0): Vec2 {
    const f = this.font(face, size, spacing);
    if (!str) return v(0, f.height / this.S);
    return v(this.rawWidth(str, f) / this.S, f.height / this.S);
  }

  /** Draws text with its top-left at a screen position (AFuryHUD::Stamp), one glyph at a time. */
  private stamp(str: string, screenX: number, screenY: number, f: FontSetup, color: Color): void {
    if (color.a <= 0 || !str) return;
    const ctx = this.ctx;
    ctx.font = f.font;
    ctx.fillStyle = css(color);
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    const y = screenY + f.baseline;
    let x = screenX;
    for (const ch of str) {
      if (ch !== ' ') ctx.fillText(ch, x, y);
      x += this.advance(ch, f);
    }
  }

  /** Draws text with its top-left / top-centre / top-right at (x, y). Returns the width. */
  text(str: string, x: number, y: number, face: Face, size: number, color: Color, align = Align.Left, spacing = 0): number {
    const width = this.measure(str, face, size, spacing).x;
    const left = align === Align.Center ? x - width * 0.5 : align === Align.Right ? x - width : x;
    this.stamp(str, round(this.sx(left)), round(this.sy(y)), this.font(face, size, spacing), color);
    return width;
  }

  /** Text with a dark offset shadow. */
  textShadow(str: string, x: number, y: number, face: Face, size: number, color: Color, align = Align.Left, spacing = 0, offset = 3): number {
    this.text(str, x + offset, y + offset, face, size, rgba(0, 0, 0, 0.75 * color.a), align, spacing);
    return this.text(str, x, y, face, size, color, align, spacing);
  }

  /** Text with a solid outline (stamped copies), for titles over busy backgrounds. */
  textOutline(str: string, x: number, y: number, face: Face, size: number, color: Color, outline: Color, thickness: number, align = Align.Left, spacing = 0): number {
    const width = this.measure(str, face, size, spacing).x;
    const left = align === Align.Center ? x - width * 0.5 : align === Align.Right ? x - width : x;
    const px = this.sx(left), py = this.sy(y);
    const f = this.font(face, size, spacing);
    const r = Math.max(1, thickness * this.S);
    const edge = rgba(outline.r, outline.g, outline.b, outline.a * color.a);
    const copies = 12;
    for (let i = 0; i < copies; ++i) {
      const angle = (2 * Math.PI * i) / copies;
      this.stamp(str, round(px + Math.cos(angle) * r), round(py + Math.sin(angle) * r), f, edge);
    }
    this.stamp(str, round(px), round(py), f, color);
    return width;
  }

  // -------------------------------------------------------------------------------------------
  // Shapes
  // -------------------------------------------------------------------------------------------

  rect(x: number, y: number, w: number, h: number, color: Color): void {
    const x0 = round(this.sx(x)), y0 = round(this.sy(y)), x1 = round(this.sx(x + w)), y1 = round(this.sy(y + h));
    if (x1 <= x0 || y1 <= y0 || color.a <= 0) return;
    this.ctx.fillStyle = css(color);
    this.ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
  }

  frame(x: number, y: number, w: number, h: number, thickness: number, color: Color): void {
    this.rect(x, y, w, thickness, color);
    this.rect(x, y + h - thickness, w, thickness, color);
    this.rect(x, y + thickness, thickness, h - 2 * thickness, color);
    this.rect(x + w - thickness, y + thickness, thickness, h - 2 * thickness, color);
  }

  private path(points: Vec2[]): void {
    const ctx = this.ctx;
    ctx.beginPath();
    for (let i = 0; i < points.length; ++i) {
      const p = points[i];
      if (i === 0) ctx.moveTo(this.sx(p.x), this.sy(p.y)); else ctx.lineTo(this.sx(p.x), this.sy(p.y));
    }
    ctx.closePath();
  }

  /**
   * A gradient between two board points. Unreal interpolates vertex colours in linear space and
   * gamma-corrects per pixel, so intermediate stops are added to follow that curve.
   */
  private gradient(a: Vec2, b: Vec2, from: Color, to: Color): CanvasGradient {
    const g = this.ctx.createLinearGradient(this.sx(a.x), this.sy(a.y), this.sx(b.x), this.sy(b.y));
    const steps = 6;
    for (let i = 0; i <= steps; ++i) {
      const t = i / steps;
      g.addColorStop(t, css({ r: from.r + (to.r - from.r) * t, g: from.g + (to.g - from.g) * t, b: from.b + (to.b - from.b) * t, a: from.a + (to.a - from.a) * t }));
    }
    return g;
  }

  quad(a: Vec2, b: Vec2, c: Vec2, d: Vec2, color: Color): void {
    if (color.a <= 0) return;
    this.path([a, b, c, d]);
    this.ctx.fillStyle = css(color);
    this.ctx.fill();
  }

  /**
   * AFuryHUD::QuadGradient for the two layouts the HUD uses: top pair / bottom pair (CA = CB,
   * CC = CD) and left / right (CA = CD, CB = CC). Anything else falls back to a vertical blend.
   */
  quadGradient(a: Vec2, b: Vec2, c: Vec2, d: Vec2, ca: Color, cb: Color, cc: Color, cd: Color): void {
    if (ca.a <= 0 && cb.a <= 0 && cc.a <= 0 && cd.a <= 0) return;
    this.path([a, b, c, d]);
    let fill: CanvasGradient;
    if (ca === cd && cb === cc && ca !== cb) {
      const top = Math.min(a.y, b.y);
      fill = this.gradient(v(Math.min(a.x, d.x), top), v(Math.max(b.x, c.x), top), ca, cb);
    } else {
      const left = Math.min(a.x, d.x);
      fill = this.gradient(v(left, Math.min(a.y, b.y)), v(left, Math.max(c.y, d.y)), ca, cc);
    }
    this.ctx.fillStyle = fill;
    this.ctx.fill();
  }

  /** A parallelogram: the top edge is shifted right by lean. */
  slant(x: number, y: number, w: number, h: number, lean: number, color: Color): void {
    this.quad(v(x + lean, y), v(x + w + lean, y), v(x + w, y + h), v(x, y + h), color);
  }

  slantGradient(x: number, y: number, w: number, h: number, lean: number, top: Color, bottom: Color): void {
    this.quadGradient(v(x + lean, y), v(x + w + lean, y), v(x + w, y + h), v(x, y + h), top, top, bottom, bottom);
  }

  gradientV(x: number, y: number, w: number, h: number, top: Color, bottom: Color): void {
    this.quadGradient(v(x, y), v(x + w, y), v(x + w, y + h), v(x, y + h), top, top, bottom, bottom);
  }

  gradientH(x: number, y: number, w: number, h: number, left: Color, right: Color): void {
    this.quadGradient(v(x, y), v(x + w, y), v(x + w, y + h), v(x, y + h), left, right, right, left);
  }

  /** Shades the whole canvas, letterbox included. */
  screenShade(top: Color, bottom: Color = top): void {
    const left = -this.OX / this.S, above = -this.OY / this.S;
    this.gradientV(left, above, BoardW - 2 * left, BoardH - 2 * above, top, bottom);
  }

  line(a: Vec2, b: Vec2, thickness: number, color: Color): void {
    const dir = b.sub(a).safeNormal();
    const side = v(-dir.y, dir.x).mul(thickness * 0.5);
    this.quad(a.add(side), b.add(side), b.sub(side), a.sub(side), color);
  }

  triangle(a: Vec2, b: Vec2, c: Vec2, color: Color): void {
    if (color.a <= 0) return;
    this.path([a, b, c]);
    this.ctx.fillStyle = css(color);
    this.ctx.fill();
  }

  circle(center: Vec2, radius: number, color: Color, _segments = 28): void {
    if (color.a <= 0 || radius <= 0) return;
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.arc(this.sx(center.x), this.sy(center.y), radius * this.S, 0, Math.PI * 2);
    ctx.fillStyle = css(color);
    ctx.fill();
  }

  /** A ring; fraction 0 is straight up and fractions run clockwise. */
  ring(center: Vec2, radius: number, thickness: number, color: Color, _segments = 32, startFraction = 0, endFraction = 1): void {
    if (color.a <= 0 || endFraction <= startFraction) return;
    const ctx = this.ctx;
    const cx = this.sx(center.x), cy = this.sy(center.y);
    const r0 = Math.max(0, (radius - thickness * 0.5) * this.S), r1 = (radius + thickness * 0.5) * this.S;
    const a0 = 2 * Math.PI * startFraction - Math.PI / 2, a1 = 2 * Math.PI * endFraction - Math.PI / 2;
    ctx.beginPath();
    ctx.arc(cx, cy, r1, a0, a1, false);
    ctx.arc(cx, cy, r0, a1, a0, true);
    ctx.closePath();
    ctx.fillStyle = css(color);
    ctx.fill();
  }

  image(img: CanvasImageSource | null | undefined, x: number, y: number, w: number, h: number, tint: Color = White, uv0 = v(0, 0), uv1 = v(1, 1)): void {
    if (!img || tint.a <= 0) return;
    const iw = (img as HTMLImageElement).naturalWidth || (img as HTMLCanvasElement).width || 0;
    const ih = (img as HTMLImageElement).naturalHeight || (img as HTMLCanvasElement).height || 0;
    if (!iw || !ih || ((img as HTMLImageElement).complete === false)) return;
    const ctx = this.ctx;
    const dx = this.sx(x), dy = this.sy(y), dw = w * this.S, dh = h * this.S;
    const srcX = uv0.x * iw, srcY = uv0.y * ih, srcW = (uv1.x - uv0.x) * iw, srcH = (uv1.y - uv0.y) * ih;
    const plain = tint.r >= 0.999 && tint.g >= 0.999 && tint.b >= 0.999;
    ctx.save();
    ctx.globalAlpha = Math.min(1, tint.a);
    if (plain) {
      ctx.drawImage(img, srcX, srcY, srcW, srcH, dx, dy, dw, dh);
    } else {
      // Multiply the texture by the tint on a scratch canvas, keeping its alpha.
      const cw = Math.max(1, Math.ceil(dw)), ch = Math.max(1, Math.ceil(dh));
      const s = this.scratch ?? (this.scratch = document.createElement('canvas'));
      if (s.width < cw) s.width = cw;
      if (s.height < ch) s.height = ch;
      const sc = s.getContext('2d')!;
      sc.clearRect(0, 0, s.width, s.height);
      sc.globalCompositeOperation = 'source-over';
      sc.drawImage(img, srcX, srcY, srcW, srcH, 0, 0, cw, ch);
      sc.globalCompositeOperation = 'multiply';
      sc.fillStyle = css(rgba(tint.r, tint.g, tint.b, 1));
      sc.fillRect(0, 0, cw, ch);
      sc.globalCompositeOperation = 'destination-in';
      sc.drawImage(img, srcX, srcY, srcW, srcH, 0, 0, cw, ch);
      sc.globalCompositeOperation = 'source-over';
      ctx.drawImage(s, 0, 0, cw, ch, dx, dy, dw, dh);
    }
    ctx.restore();
  }

  // -------------------------------------------------------------------------------------------
  // Widgets shared by every screen
  // -------------------------------------------------------------------------------------------

  /** Where a point in the world lands on the board, or null if it is behind the camera. */
  worldToBoard(world: Vec3): Vec2 | null {
    const screen = this.hud?.worldToScreen(world);
    if (!screen) return null;
    return v((screen.x * this.dpr - this.OX) / this.S, (screen.y * this.dpr - this.OY) / this.S);
  }

  /** A dark glass panel with a coloured edge. */
  panel(x: number, y: number, w: number, h: number, accent: Color, alpha = 0.86): void {
    this.gradientV(x, y, w, h, fade(Slate, alpha), fade(Ink, alpha));
    this.rect(x, y, w, 5, accent);
    this.frame(x, y, w, h, 1.5, fade(White, 0.08));
  }

  meter(x: number, y: number, w: number, h: number, fraction: number, fill: Color, back: Color): void {
    const lean = h * 0.45;
    this.slant(x, y, w, h, lean, back);
    const amount = Math.min(Math.max(fraction, 0), 1);
    if (amount > 0.005) this.slant(x, y, w * amount, h, lean, fill);
  }

  /** "P3" in the seat's colour. Returns its width. */
  seatChip(seat: number, x: number, y: number, height: number, cpu = false): number {
    const color = cpu ? rgba(0.35, 0.37, 0.42) : Director.seatColor(seat);
    const label = cpu ? 'CPU' : `P${seat + 1}`;
    const size = height * 0.74;
    const width = this.measure(label, Face.BlackItalic, size).x + height * 0.7;
    this.slant(x, y, width, height, height * 0.28, color);
    this.text(label, x + width * 0.5 + height * 0.14, y + height * 0.06, Face.BlackItalic, size, inkOn(color), Align.Center);
    return width + height * 0.28;
  }

  /** A round controller-button glyph (or the matching key cap for keyboard players). Returns its width. */
  glyph(seat: number, button: UIButton, x: number, y: number, size: number, measureOnly = false): number {
    const hud = this.hud;
    let pad = hud ? (hud.quitPad !== NONE ? hud.quitPad : hud.settingsPad) : NONE;
    if (pad === NONE && hud && seat >= 0 && seat < MaxSeats && hud.seats[seat].joined && !hud.seats[seat].bot) {
      pad = hud.seats[seat].pad;
    }
    if (pad === NONE && seat === NONE) pad = this.sharedPromptPad;
    const keyboard = pad === FuryInput.KeyboardA || pad === FuryInput.KeyboardB ? pad : NONE;
    const index = Math.min(button, UIButton.Turbo);
    const label = keyboard !== NONE ? Keys[keyboard][index] : Pads[index];
    const isRound = keyboard === NONE && index < 4;
    if (isRound) {
      if (measureOnly) return size;
      const centre = v(x + size * 0.5, y + size * 0.5);
      this.circle(centre, size * 0.5, Ink, 24);
      const style = pad >= FuryInput.FirstGamepad ? FuryInput.get().pad(pad)?.faceStyle : undefined;
      if (style === 'playstation' || style === 'nintendo') {
        // The pad's own face symbols, drawn white like the system glyphs the C++ uses.
        this.ring(centre, size * 0.39, size * 0.07, White, 24);
        if (style === 'nintendo') {
          this.text(NintendoFace[index], centre.x, y + size * 0.19, Face.Bold, size * 0.5, White, Align.Center);
        } else {
          this.playStationShape(index, centre, size);
        }
        return size;
      }
      this.circle(centre, size * 0.43, FaceColors[index], 24);
      this.text(label, centre.x, y + size * 0.1, Face.Black, size * 0.66, Ink, Align.Center);
      return size;
    }
    const textSize = size * 0.6;
    const width = Math.max(size, this.measure(label, Face.Bold, textSize).x + size * 0.5);
    if (measureOnly) return width;
    this.rect(x, y, width, size, Ink);
    this.rect(x + 2, y + 2, width - 4, size - 6, rgba(0.86, 0.88, 0.9));
    this.text(label, x + width * 0.5, y + size * 0.1, Face.Bold, textSize, Ink, Align.Center);
    return width;
  }

  /** ✕ ○ □ △ for PlayStation pads, in the order A (south), B (east), X (west), Y (north). */
  private playStationShape(index: number, c: Vec2, size: number): void {
    const r = size * 0.17, t = size * 0.075;
    if (index === 0) {
      this.line(c.add(v(-r, -r)), c.add(v(r, r)), t, White);
      this.line(c.add(v(-r, r)), c.add(v(r, -r)), t, White);
    } else if (index === 1) {
      this.ring(c, r * 1.05, t, White, 20);
    } else if (index === 2) {
      const h = r * 0.95;
      this.frame(c.x - h, c.y - h, 2 * h, 2 * h, t, White);
    } else {
      const top = c.add(v(0, -r * 1.15)), left = c.add(v(-r * 1.1, r * 0.75)), right = c.add(v(r * 1.1, r * 0.75));
      this.line(top, left, t, White);
      this.line(left, right, t, White);
      this.line(right, top, t, White);
      // Fill the corners the thick lines leave notched.
      for (const p of [top, left, right]) this.circle(p, t * 0.5, White, 8);
    }
  }

  /** A row of prompts: glyph + label pairs, centred on centerX. */
  prompts(seat: number, items: [UIButton, string][], centerX: number, y: number, size = 26): void {
    // Measure first so the whole row can be centred.
    const gap = size * 1.1, pad = size * 0.3;
    let total = 0;
    for (const [button, label] of items) {
      total += this.glyph(seat, button, 0, 0, size, true) + pad + this.measure(label, Face.SemiBold, size * 0.86, 60).x + gap;
    }
    let x = centerX - (total - gap) * 0.5;
    for (const [button, label] of items) {
      x += this.glyph(seat, button, x, y, size) + pad;
      x += this.textShadow(label, x, y + size * 0.04, Face.SemiBold, size * 0.86, White, Align.Left, 60, 2) + gap;
    }
  }
}


const Keys: string[][] = [
  ['G', 'H', 'F', 'T', 'Q', 'E', 'ESC', 'WASD', 'L SHIFT'],
  ['K', 'L', 'J', 'I', 'U', 'O', 'ENTER', 'ARROWS', 'R SHIFT'],
];
const Pads = ['A', 'B', 'X', 'Y', 'LB', 'RB', 'START', 'STICK', 'LT / RT'];
const NintendoFace = ['B', 'A', 'Y', 'X'];
const FaceColors: Color[] = [rgba(0.2, 0.82, 0.3), rgba(0.92, 0.2, 0.17), rgba(0.16, 0.46, 1), rgba(1, 0.78, 0.08)];
