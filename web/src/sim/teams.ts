/**
 * The Fury Football League: eight teams, their colours, ratings and rosters (port of FuryTeams.cpp).
 *
 * Team colours are kept as sRGB "#RRGGBB" strings. Unreal parses them into linear FLinearColor
 * (Fury::Hex), and KitFor does its luma tests in linear space, so kitFor does the same and converts
 * the results back to sRGB hex. Keep the ids and colours in step with Art/teams.json.
 */
import { Hex, Pos, RandomStream, RosterEntry, Team } from './core';

// ---------------------------------------------------------------------------------------------
// Colour helpers (FColor <-> FLinearColor, sRGB)
// ---------------------------------------------------------------------------------------------

interface Linear { r: number; g: number; b: number }

/** FLinearColor(FColor): sRGB byte to linear, the same curve as Unreal's sRGBToLinearTable. */
function srgbToLinear(byte: number): number {
  const c = byte / 255;
  return c > 0.04045 ? Math.pow((c + 0.055) / 1.055, 2.4) : c / 12.92;
}

/** FLinearColor::ToFColorSRGB for one channel. */
function linearToSrgbByte(v: number): number {
  let c = Math.min(Math.max(v, 0), 1);
  c = c <= 0.0031308 ? c * 12.92 : Math.pow(c, 1 / 2.4) * 1.055 - 0.055;
  return Math.floor(c * 255.999);
}

/** Fury::Hex: parses "#RRGGBB" as an sRGB colour and returns it in linear space. */
function hexToLinear(code: string): Linear {
  const h = code.replace('#', '');
  return {
    r: srgbToLinear(parseInt(h.slice(0, 2), 16)),
    g: srgbToLinear(parseInt(h.slice(2, 4), 16)),
    b: srgbToLinear(parseInt(h.slice(4, 6), 16)),
  };
}

function linearToHex(c: Linear): Hex {
  const two = (v: number) => linearToSrgbByte(v).toString(16).toUpperCase().padStart(2, '0');
  return `#${two(c.r)}${two(c.g)}${two(c.b)}`;
}

// ---------------------------------------------------------------------------------------------
// Rosters
// ---------------------------------------------------------------------------------------------

interface Names { offense: string[]; defense: string[]; kicker: string }

const OffensePos: Pos[] = [Pos.QB, Pos.OL, Pos.OL, Pos.OL, Pos.WR, Pos.WR, Pos.RB];
const DefensePos: Pos[] = [Pos.DL, Pos.DL, Pos.DL, Pos.LB, Pos.CB, Pos.CB, Pos.S];
// Numbers by position group, the way real rosters hand them out.
const OffenseBase = [7, 52, 61, 74, 80, 11, 21];
const DefenseBase = [90, 95, 99, 50, 20, 30, 40];

function make(id: string, city: string, name: string, abbr: string,
  primary: string, secondary: string, accent: string, helmet: string,
  speed: number, power: number, passing: number, defense: number, motto: string, names: Names, seed: number): Team {
  const team: Team = {
    id, city, name, abbr,
    primary, secondary, accent, helmet,
    speed, power, passing, defense,
    motto,
    roster: [],
  };

  const random = new RandomStream(seed);
  const used = new Set<number>();
  const number = (base: number): number => {
    let n = base + random.randRange(0, 8);
    if (base >= 90) { n = 90 + (n - 90) % 10; }
    while (used.has(n)) {
      n = base >= 90 ? 90 + (n - 89) % 10 : n % 99 + 1;
    }
    used.add(n);
    return n;
  };
  const add = (playerName: string, pos: Pos, base: number): void => {
    const entry: RosterEntry = { name: playerName, pos, number: 0, skinTone: 0, visor: false };
    entry.number = number(base);
    entry.skinTone = random.randRange(0, skinTones().length - 1);
    entry.visor = pos !== Pos.OL && pos !== Pos.DL && pos !== Pos.K && random.fRand() < 0.45;
    team.roster.push(entry);
  };
  for (let i = 0; i < 7; ++i) { add(names.offense[i], OffensePos[i], OffenseBase[i]); }
  for (let i = 0; i < 7; ++i) { add(names.defense[i], DefensePos[i], DefenseBase[i]); }
  add(names.kicker, Pos.K, 2);
  return team;
}

let skinToneCache: string[] | null = null;
export function skinTones(): string[] {
  if (!skinToneCache) {
    skinToneCache = ['#F1C9A5', '#E0AC84', '#C68958', '#A0683F', '#7A4A2B', '#55321C'];
  }
  return skinToneCache;
}

let leagueCache: Team[] | null = null;
export function leagueTeams(): Team[] {
  if (leagueCache) { return leagueCache; }
  leagueCache = [
    make('sasquatch', 'Portland', 'Sasquatch', 'POR', '#1F6B3A', '#EFE6CC', '#6B4423', '#1F6B3A',
      2, 5, 3, 4, 'Big. Hairy. Impossible to tackle.',
      { offense: ['Hollis', 'Brannigan', 'Oyelaran', 'Tuck', 'Maddox', 'Sorrel', 'Bigfoot Dunn'],
        defense: ['Krull', 'Vandermeer', 'Okafor', 'Stonebridge', 'Pines', 'Ashdown', 'Larkspur'], kicker: 'Twiggs' }, 11),
    make('volcanoes', 'Honolulu', 'Volcanoes', 'HNL', '#1A1A1E', '#FF5A1F', '#FFC21A', '#1A1A1E',
      3, 3, 5, 2, 'Every drive ends in an eruption.',
      { offense: ['Kealoha', 'Tavita', 'Makoa', 'Brewer', 'Nakamura', 'Fontaine', 'Palakiko'],
        defense: ['Lolohea', 'Ashby', 'Kanoa', 'Ferreira', 'Soares', 'Wyndham', 'Ikaika'], kicker: 'Pua' }, 23),
    make('icebreakers', 'Anchorage', 'Icebreakers', 'ANC', '#0F3470', '#8FE3FF', '#FFFFFF', '#F4F8FB',
      3, 4, 2, 5, 'Nothing gets through the ice.',
      { offense: ['Lindqvist', 'Baranov', 'Tuttle', 'Halvorsen', 'Frost', 'Okpik', 'Mercer'],
        defense: ['Kowalczyk', 'Bjornson', 'Steele', 'Northrup', 'Winters', 'Aklaq', 'Glacier Reed'], kicker: 'Sorenson' }, 37),
    make('hellhounds', 'Memphis', 'Hellhounds', 'MEM', '#B01228', '#26262B', '#FF8A1F', '#26262B',
      4, 4, 3, 3, 'Off the leash since kickoff.',
      { offense: ['Beaumont', 'Calloway', 'Durand', 'Pickett', 'Delacroix', 'Rhodes', 'Tallchief'],
        defense: ['Graves', 'Montrose', 'Lockhart', 'Cerberus Hale', 'Ember', 'Voss', 'Kincaid'], kicker: 'Dupree' }, 41),
    make('twisters', 'Omaha', 'Twisters', 'OMA', '#F2B90F', '#2E3440', '#FFFFFF', '#2E3440',
      5, 2, 3, 3, 'You will not see them coming.',
      { offense: ['Whitlock', 'Dombrowski', 'Haskell', 'Yoder', 'Gale', 'Swift', 'Cyclone Banks'],
        defense: ['Rourke', 'Tillman', 'Abernathy', 'Funnel', 'Zephyr', 'Lund', 'Prairie'], kicker: 'Kessler' }, 59),
    make('amps', 'Austin', 'Amps', 'ATX', '#E6007E', '#15151A', '#19E6FF', '#15151A',
      4, 2, 4, 3, 'Turned all the way up.',
      { offense: ['Valentine', 'Ruiz', 'McAllister', 'Boone', 'Reverb Jones', 'Castillo', 'Fuzz'],
        defense: ['Riff Lawson', 'Trevino', 'Stack', 'Overdrive', 'Marquez', 'Ziegler', 'Feedback'], kicker: 'Tremolo' }, 67),
    make('scorpions', 'Tucson', 'Scorpions', 'TUC', '#12A594', '#EBCB8B', '#1B1B1F', '#EBCB8B',
      4, 3, 3, 4, 'Quiet in the sand. Then the sting.',
      { offense: ['Navarro', 'Begay', 'Ortega', 'Sandoval', 'Mesa', 'Quill', 'Dustin Vega'],
        defense: ['Stinger', 'Yazzie', 'Calderon', 'Saguaro', 'Rios', 'Tovar', 'Mirage'], kicker: 'Coronado' }, 73),
    make('gargoyles', 'Brooklyn', 'Gargoyles', 'BKN', '#6C3BD1', '#9AA1AB', '#F2F2F2', '#9AA1AB',
      3, 4, 3, 4, 'Stone cold. Always watching.',
      { offense: ['Castellano', 'Abramowitz', 'Okonkwo', 'Rizzo', 'Spire', 'Delancey', 'Granite'],
        defense: ['Morello', 'Flatbush', 'Wojcik', 'Gable', 'Cornice', 'Ledge', 'Nightwatch'], kicker: 'Finch' }, 89),
  ];
  return leagueCache;
}

// ---------------------------------------------------------------------------------------------
// Kits
// ---------------------------------------------------------------------------------------------

/** Uniform colours for a team wearing its home (coloured) or away (white) kit, as sRGB hex. */
export interface Kit {
  jersey: Hex; trim: Hex; numberFill: Hex; numberEdge: Hex; pants: Hex; pantsStripe: Hex;
  helmet: Hex; helmetStripe: Hex; facemask: Hex; socks: Hex; shoes: Hex; gloves: Hex;
}

/** Port of Fury::KitFor. Colour decisions are made in linear space, exactly like the C++. */
export function kitFor(team: Team, home: boolean): Kit {
  const White: Linear = { r: 0.93, g: 0.93, b: 0.93 };
  const Black: Linear = { r: 0.015, g: 0.015, b: 0.018 };
  const luma = (c: Linear) => 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
  const primary = hexToLinear(team.primary);
  const secondary = hexToLinear(team.secondary);
  const accent = hexToLinear(team.accent);
  const helmet = hexToLinear(team.helmet);
  const darkPrimary = luma(primary) < 0.03;

  let jersey: Linear, trim: Linear, numberFill: Linear, numberEdge: Linear, pants: Linear, pantsStripe: Linear;
  if (home) {
    jersey = primary;
    trim = secondary;
    // Numbers must stand off the jersey: light on dark, dark on light.
    numberFill = luma(primary) > 0.35 ? Black : (luma(secondary) > 0.3 ? secondary : White);
    numberEdge = luma(numberFill) > 0.3 ? (darkPrimary ? accent : Black) : White;
    pants = luma(secondary) > 0.25 ? secondary : White;
    pantsStripe = primary;
  } else {
    jersey = White;
    trim = primary;
    numberFill = darkPrimary ? secondary : primary;
    numberEdge = darkPrimary ? Black : secondary;
    if (luma(numberFill) > 0.5) {
      numberFill = Black;
      numberEdge = primary;
    }
    pants = darkPrimary ? primary : (luma(primary) > 0.3 ? secondary : primary);
    pantsStripe = White;
  }
  const helmetStripe = luma(helmet) > 0.5 ? primary : (luma(secondary) > luma(helmet) + 0.05 ? secondary : accent);
  const facemask = luma(helmet) > 0.5 ? primary : { r: 0.7, g: 0.7, b: 0.72 };
  const socks = home ? jersey : primary;
  const shoes = home ? Black : White;
  const gloves = home ? accent : primary;

  return {
    jersey: linearToHex(jersey), trim: linearToHex(trim), numberFill: linearToHex(numberFill), numberEdge: linearToHex(numberEdge),
    pants: linearToHex(pants), pantsStripe: linearToHex(pantsStripe), helmet: linearToHex(helmet), helmetStripe: linearToHex(helmetStripe),
    facemask: linearToHex(facemask), socks: linearToHex(socks), shoes: linearToHex(shoes), gloves: linearToHex(gloves),
  };
}
