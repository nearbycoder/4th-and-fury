/**
 * The whole in-game interface, drawn onto a 2D canvas over the game (port of AFuryHUD::DrawHUD).
 *
 * Usage: `await loadHudFonts(); const hud = new Hud(canvas); ... hud.draw(director)` every frame.
 * The canvas should overlay the game canvas at the same CSS size: Director.worldToScreen returns
 * CSS pixels in that canvas. The stadium video board is drawn into `hud.board.canvas`; re-upload
 * it as a texture whenever `hud.board.version` changes.
 */
import { Director, Screen } from '../game/director';
import { FuryInput } from '../game/input';
import { NONE, Option } from './deps';
import { Align, Face, Kit } from './kit';
import { BoardState, drawMatch } from './match';
import { drawFinal, drawLobby, drawTeams, drawTitle } from './menus';
import { drawSettings } from './options';
import { fade, Ink, White } from './style';

export { loadHudFonts } from './fonts';
export { BoardState } from './match';

export class Hud {
  readonly canvas: HTMLCanvasElement;
  readonly kit: Kit;
  /** The stadium's video board (AFuryStadium::BoardTarget). */
  readonly board = new BoardState();

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Hud: no 2D context');
    this.kit = new Kit(ctx);
  }

  /** Matches the canvas backing store to its CSS size at the device pixel ratio. */
  private resize(): void {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    const w = Math.max(1, Math.round(rect.width * dpr)), h = Math.max(1, Math.round(rect.height * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    this.kit.dpr = dpr;
  }

  draw(director: Director): void {
    this.resize();
    const k = this.kit;
    const ctx = k.ctx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    k.layout(this.canvas.width, this.canvas.height);
    k.hud = director;
    k.sharedPromptPad = FuryInput.get().firstConnectedGamepad();
    const d = director;

    // (The quit prompt is not ported: a browser tab cannot quit.)
    if (d.settingsPad !== NONE) {
      drawSettings(k, d);
      return;
    }
    switch (d.screen) {
      case Screen.Viewer: break;     // the animation viewer is not part of the web build
      case Screen.Title: drawTitle(k, d); break;
      case Screen.Lobby: drawLobby(k, d); break;
      case Screen.Teams: drawTeams(k, d); break;
      case Screen.Match:
        drawMatch(k, d, this.board);
        if (d.options.get(Option.ShowFPS) && d.liveFPS > 0) {
          k.rect(1610, 23, 260, 41, fade(Ink, 0.88));
          k.text(`${d.liveFPS.toFixed(0)} FPS   /   ${(1000 / d.liveFPS).toFixed(1)} ms`, 1854, 27, Face.SemiBold, 26, White, Align.Right);
        }
        break;
      case Screen.Final: drawFinal(k, d); break;
    }
    if (d.options.get(Option.Captions) && !d.paused && !d.viewingFilm && d.screen !== Screen.Viewer && d.audio) {
      const line = d.audio.caption();
      if (line) {
        let top = 1019;
        if (d.screen === Screen.Title) top = 42;
        else if (d.screen === Screen.Teams) top = 732;
        else if (d.screen === Screen.Final) top = 186;
        const width = k.measure(line, Face.SemiBold, 31).x + 46;
        k.rect(960 - width * 0.5, top, width, 44, fade(Ink, 0.96));
        k.text(line, 960, top + 2, Face.SemiBold, 31, White, Align.Center);
      }
    }
  }
}
