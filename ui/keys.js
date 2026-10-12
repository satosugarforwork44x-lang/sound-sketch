// keys.js — キーの割り当て。キーは刻印ではなく物理的な位置（KeyboardEvent.code）で持つ（JIS と US で同じ位置になる）
// 既定: 中段の 7 キー S D F / J K L ; がドレミファソラシ。左手の小指は Shift（押しながら弾くと半音上げ）に空けておく
export const WHITE_KEYS = ["w0", "w1", "w2", "w3", "w4", "w5", "w6"];
export const ACTIONS = [
  { group: "drums", items: ["kick", "snare", "hat", "clap"] },
  { group: "piano", items: [...WHITE_KEYS, "sharp"] },
  { group: "ops", items: ["play", "rec", "mode", "octDown", "octUp", "partDrums", "partBass", "partChords", "partMelody"] },
];
export const KEYMAP_VERSION = "5";

const BASE = {
  kick: "ArrowDown", snare: "ArrowLeft", hat: "ArrowUp", clap: "ArrowRight",
  w0: "KeyS", w1: "KeyD", w2: "KeyF", w3: "KeyJ", w4: "KeyK", w5: "KeyL", w6: "Semicolon",
  sharp: "ShiftLeft",
  play: "Enter", rec: "KeyR", mode: "Tab", octDown: "KeyZ", octUp: "KeyX",
  partDrums: "Digit1", partBass: "Digit2", partChords: "Digit3", partMelody: "Digit4",
};

export const PRESETS = {
  default: BASE,
  // テンキーあり: ドラムをテンキーへ（矢印は空く）
  numpad: { ...BASE, kick: "Numpad1", snare: "Numpad2", hat: "Numpad5", clap: "Numpad3" },
};

// 保存されていた割り当てを読む。並びの考え方を変えた版（_v が違う）のものは捨てて既定にする
export function normalizeKeymap(saved) {
  const km = { ...BASE };
  if (saved && typeof saved === "object" && saved._v === KEYMAP_VERSION) {
    for (const k of Object.keys(BASE)) if (typeof saved[k] === "string") km[k] = saved[k];
  }
  km._v = KEYMAP_VERSION;
  return km;
}

// 同じキーが 2 つの役目に付いたら、元の役目と入れ替える（どれかが空になるのを防ぐ）
export function assign(km, action, code) {
  const out = { ...km };
  const other = Object.keys(out).find((k) => k !== action && k !== "_v" && out[k] === code);
  if (other) out[other] = km[action];
  out[action] = code;
  out._v = KEYMAP_VERSION;
  return { keymap: out, swapped: other || null };
}

const SPECIAL = {
  Space: "Space", Enter: "Enter", Tab: "Tab", Backspace: "BS", Escape: "Esc", Semicolon: ";", Quote: ":", Comma: ",",
  Period: ".", Slash: "/", Backslash: "]", IntlRo: "\\", IntlYen: "¥", BracketLeft: "@", BracketRight: "[", Minus: "-",
  Equal: "^", Backquote: "半/全", ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→",
  ShiftLeft: "左 Shift", ShiftRight: "右 Shift", ControlLeft: "左 Ctrl", ControlRight: "右 Ctrl", AltLeft: "左 Alt", AltRight: "右 Alt",
  NonConvert: "無変換", Convert: "変換", KanaMode: "かな", CapsLock: "Caps",
};
const EN = typeof document !== "undefined" && (document.documentElement.lang || navigator.language || "ja").startsWith("en");
const SPECIAL_EN = { ShiftLeft: "L Shift", ShiftRight: "R Shift", ControlLeft: "L Ctrl", ControlRight: "R Ctrl", AltLeft: "L Alt", AltRight: "R Alt",
  Backquote: "Zenkaku", NonConvert: "Muhenkan", Convert: "Henkan", KanaMode: "Kana" };
export function keyLabel(code) {
  if (!code) return "—";
  if (EN && SPECIAL_EN[code]) return SPECIAL_EN[code];
  if (SPECIAL[code]) return SPECIAL[code];
  let m;
  if ((m = /^Key([A-Z])$/.exec(code))) return m[1];
  if ((m = /^Digit(\d)$/.exec(code))) return m[1];
  if ((m = /^Numpad(.+)$/.exec(code))) return `Num ${m[1].replace("Decimal", ".")}`;
  return code;
}
