/**
 * The settings screen: graphics and sound tabs (port of FuryHUDOptions.cpp). The web build lists
 * its rows through Options.rows(), which leaves out what a browser cannot change (VSync).
 */
import type { Director } from '../game/director';
import { NONE, Options } from './deps';
import { Align, Face, Kit } from './kit';
import { Blaze, Dim, Gold, rgba, Slate, UIButton, White } from './style';

const { A, B, X, Y, LB, RB, Stick } = UIButton;
const roundInt = (x: number) => Math.floor(x + 0.5);

export function drawSettings(k: Kit, d: Director): void {
  const options = d.options;
  const sound = d.soundTab;
  const Left = 54, Width = 820, RowY = 235, Step = 58;
  const rowIds = Options.rows(sound);
  const rows = rowIds.length;
  const bottom = RowY + rows * Step + 145;
  k.panel(Left, 62, Width, bottom - 62, Blaze, 0.97);
  k.text('SETTINGS', Left + 34, 73, Face.BlackItalic, 69, White);

  k.glyph(NONE, LB, Left + 38, 170, 32);
  k.text('GRAPHICS', Left + 138, 159, Face.ExtraBold, 36, sound ? Dim : White);
  k.text('SOUND', Left + 366, 159, Face.ExtraBold, 36, sound ? White : Dim);
  k.glyph(NONE, RB, Left + 525, 170, 32);
  k.rect(Left + 36, 215, Width - 72, 2, Slate);
  k.rect(Left + (sound ? 366 : 138), 213, sound ? 102 : 141, 5, Blaze);

  for (let i = 0; i < rows; ++i) {
    const id = rowIds[i];
    const selected = i === d.settingsRow;
    const yPos = RowY + Step * i;
    if (selected) {
      k.rect(Left + 23, yPos, Width - 46, Step - 3, rgba(0.135, 0.072, 0.042));
      k.rect(Left + 23, yPos, 5, Step - 3, Blaze);
    }
    k.text(Options.label(id), Left + 42, yPos + 7, Face.SemiBold, 32, selected ? White : Dim);
    if (Options.isChannel(id)) {
      k.meter(Left + 360, yPos + 24, 222, 11, options.volume(id), selected ? Gold : Dim, Slate);
    }
    k.text(options.display(id), Left + Width - 73, yPos + 6, Face.Bold, 33, selected ? Gold : White, Align.Right);
    if (selected) {
      k.text('<', Left + (Options.isChannel(id) ? 326 : 521), yPos + 7, Face.Bold, 30, Blaze);
      k.text('>', Left + Width - 52, yPos + 7, Face.Bold, 30, Blaze);
    }
  }
  const foot = RowY + rows * Step;
  const current = rowIds[Math.min(Math.max(d.settingsRow, 0), rows - 1)];
  k.rect(Left + 36, foot + 12, Width - 72, 2, Slate);
  k.text(Options.hint(current), Left + 42, foot + 24, Face.Medium, 27, White);
  if (Options.isChannel(current)) {
    k.prompts(NONE, [[Stick, 'ADJUST'], [A, 'LISTEN'], [Y, options.muted(current) ? 'UNMUTE' : 'MUTE'], [X, 'RESET SOUND'], [B, 'BACK']],
      Left + Width * 0.5, foot + 85, 23);
  } else {
    k.prompts(NONE, [[Stick, 'ADJUST'], [X, sound ? 'RESET SOUND' : 'RESET GRAPHICS'], [B, 'BACK']], Left + Width * 0.5, foot + 85, 24);
  }

  if (sound) return;
  const XPos = 1430, YPos = 62;
  k.panel(XPos, YPos, 436, 250, Blaze, 0.94);
  k.text('VISUAL QUALITY', XPos + 26, YPos + 17, Face.Bold, 25, Dim, Align.Left, 100);
  const bars = roundInt(options.detail(d.renderPercent) * 12);
  for (let i = 0; i < 12; ++i) k.slant(XPos + 26 + 32 * i, YPos + 59, 26, 11, 4, i < bars ? Gold : Slate);
  const fps = d.liveFPS > 0 ? `${d.liveFPS.toFixed(0)} FPS` : '-- FPS';
  k.text(fps, XPos + 25, YPos + 79, Face.ExtraBoldItalic, 61, White);
  if (d.liveFPS > 0) {
    k.text(`${(1000 / d.liveFPS).toFixed(1)} ms`, XPos + 409, YPos + 103, Face.SemiBold, 32, White, Align.Right);
  }
  k.text('Live frame time  /  120 FPS takes 8.3 ms', XPos + 27, YPos + 156, Face.Medium, 24, Dim);
  const size = d.outputSize;
  k.text(`Field   ${roundInt((size.x * d.renderPercent) / 100)} x ${roundInt((size.y * d.renderPercent) / 100)}   /   ${d.renderPercent.toFixed(0)}%`,
    XPos + 27, YPos + 197, Face.SemiBold, 25, White);
}
