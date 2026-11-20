/**
 * The HUD's typefaces (EFuryFace) and the metrics the canvas needs to place text where Slate does.
 *
 * Slate puts a canvas text item's baseline at Y + round(height) + round(descender), where height
 * and descender are the font's hhea line height and descender at the rendered size, and the text
 * box is `height` tall. The values below come from the TTFs in FourthAndFury/Content/Fonts.
 */

export enum Face { Medium, SemiBold, Bold, ExtraBold, Black, BoldItalic, ExtraBoldItalic, BlackItalic, Anton, Graduate, Count }
export enum Align { Left, Center, Right }

interface FaceInfo { file: string; family: string; height: number; descender: number }

const barlow = (file: string, family: string): FaceInfo => ({ file, family, height: 1.2, descender: -0.2 });

export const Faces: FaceInfo[] = [
  barlow('BarlowCondensed-Medium', 'FuryBarlowMedium'),
  barlow('BarlowCondensed-SemiBold', 'FuryBarlowSemiBold'),
  barlow('BarlowCondensed-Bold', 'FuryBarlowBold'),
  barlow('BarlowCondensed-ExtraBold', 'FuryBarlowExtraBold'),
  barlow('BarlowCondensed-Black', 'FuryBarlowBlack'),
  barlow('BarlowCondensed-BoldItalic', 'FuryBarlowBoldItalic'),
  barlow('BarlowCondensed-ExtraBoldItalic', 'FuryBarlowExtraBoldItalic'),
  barlow('BarlowCondensed-BlackItalic', 'FuryBarlowBlackItalic'),
  // Anton: unitsPerEm 2048, hhea ascent 2409, descent -674, lineGap 0.
  { file: 'Anton-Regular', family: 'FuryAnton', height: (2409 + 674) / 2048, descender: -674 / 2048 },
  // Graduate: unitsPerEm 1000, hhea ascent 953, descent -186, lineGap 0.
  { file: 'Graduate-Regular', family: 'FuryGraduate', height: (953 + 186) / 1000, descender: -186 / 1000 },
];

let loading: Promise<void> | null = null;

/** Registers the HUD fonts with the document (FontFace API). Safe to call more than once. */
export function loadHudFonts(): Promise<void> {
  if (loading) return loading;
  const base = import.meta.env.BASE_URL;
  loading = Promise.all(Faces.map(async (f) => {
    const face = new FontFace(f.family, `url(${base}assets/fonts/hud/${f.file}.woff2) format("woff2")`);
    await face.load();
    document.fonts.add(face);
  })).then(() => undefined);
  return loading;
}
