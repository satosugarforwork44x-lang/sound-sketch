// theory.js — 音名・調・コードの計算（synth.py と同じ決まり）。画面の外でも試せるよう DOM を使わない
export const KEYS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
export const NAMES = KEYS;
export const PENTA = { major: [0, 2, 4, 7, 9], minor: [0, 3, 5, 7, 10] };
export const SEVEN = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10] };
export const BASE_OCT = { bass: 2, chords: 3, melody: 4 };
export const VOICE = { bass: "bass", chords: "pad", melody: "lead" };

const PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const CHORD_IV = {
  "": [0, 4, 7], maj: [0, 4, 7], m: [0, 3, 7], dim: [0, 3, 6], aug: [0, 4, 8], sus2: [0, 2, 7], sus4: [0, 5, 7],
  6: [0, 4, 7, 9], m6: [0, 3, 7, 9], 7: [0, 4, 7, 10], maj7: [0, 4, 7, 11], m7: [0, 3, 7, 10], mmaj7: [0, 3, 7, 11],
  m7b5: [0, 3, 6, 10], dim7: [0, 3, 6, 9], "7sus4": [0, 5, 7, 10], add9: [0, 4, 7, 14], 9: [0, 4, 7, 10, 14],
};
const CHORD_RE = /^([A-G])([#b]?)(maj7|m7b5|m7|mmaj7|m6|m|dim7|dim|aug|sus2|sus4|7sus4|add9|maj|6|7|9)?(?:\/[A-G][#b]?)?$/;

export function noteMidi(name) {
  const m = /^([A-Ga-g])([#b]?)(-?\d)$/.exec(String(name).trim());
  if (!m) return null;
  return 12 * (Number(m[3]) + 1) + PC[m[1].toUpperCase()] + ({ "#": 1, b: -1 }[m[2]] || 0);
}
export const midiName = (midi) => `${NAMES[((midi % 12) + 12) % 12]}${Math.floor(midi / 12) - 1}`;

export function chordMidis(name, octave = 3) {
  const m = CHORD_RE.exec(String(name).trim());
  if (!m) return [];
  const root = (PC[m[1]] + ({ "#": 1, b: -1 }[m[2]] || 0) + 12) % 12;
  const base = 12 * (octave + 1) + root;
  return CHORD_IV[m[3] || ""].map((iv) => base + iv);
}

export const WHITE = [0, 2, 4, 5, 7, 9, 11];               // ドレミファソラシ
export const SOLFA = ["ド", "レ", "ミ", "ファ", "ソ", "ラ", "シ"];
export const ROMAN = { major: ["I", "ii", "iii", "IV", "V", "vi", "vii°"], minor: ["i", "ii°", "III", "iv", "v", "VI", "VII"] };

// 白鍵（idx 0〜9。7 から上のオクターブ）→ 音。
// mode "white": ふつうの鍵盤（ドレミファソラシ。調に関係なく白鍵）/ "penta": 調の 5 音だけ（どれを押しても外れない）
// upper: 1 オクターブ上、sharp: 半音上げ
export function keyMidi({ key, scale, mode, part, octOff = 0, idx, upper = false, sharp = false }) {
  const oct = BASE_OCT[part] + octOff + (upper ? 1 : 0);
  if (mode === "penta") {
    const sc = PENTA[scale];
    const base = 12 * (oct + 1) + KEYS.indexOf(key);
    return base + Math.floor(idx / 5) * 12 + sc[idx % 5] + (sharp ? 1 : 0);
  }
  return 12 * (oct + 1) + Math.floor(idx / 7) * 12 + WHITE[idx % 7] + (sharp ? 1 : 0);
}

// コードのパート: 7 つの鍵盤 → その調の和音 I〜VII。seventh なら 4 和音
export function keyChord({ key, scale, idx, seventh = false }) {
  const sc = SEVEN[scale];
  const d = idx % 7;
  const at = (k) => (sc[(d + k) % 7] - sc[d] + 12) % 12;
  const iv = [at(2), at(4)].concat(seventh ? [at(6)] : []).join(",");
  const q = { "4,7": "", "3,7": "m", "3,6": "dim", "4,8": "aug", "4,7,11": "maj7", "3,7,10": "m7", "4,7,10": "7",
    "3,6,10": "m7b5", "3,6,9": "dim7", "3,7,11": "mmaj7" }[iv] ?? "";
  return NAMES[(KEYS.indexOf(key) + sc[d]) % 12] + q;
}

// 調の中の音か（ピアノロールの行を明るくする）
export const inScale = (midi, key, scale) => SEVEN[scale].includes((((midi - KEYS.indexOf(key)) % 12) + 12) % 12);
