// sketch/ui/panel.js — サウンドスケッチ。数小節のリズム・ベース・コード・メロディをキーボードで作り、WAV にして AI に渡す
// ・音は api.py（numpy）が 1 音ずつ WAV にして /blob/sketch/<key> で渡す。ここでは Web Audio で並べて鳴らすだけ
// ・スケッチは保存先フォルダの .sketch.json。外（Claude など）で書き換えられたら読み直す
import { TOKEN, selectBox } from "/ui/js/hub.js";
import { KEYS, VOICE, BASE_OCT, ROMAN, SOLFA, chordMidis, inScale, keyChord, keyMidi, midiName, noteMidi } from "./theory.js";
import { ACTIONS, PRESETS, assign, keyLabel, normalizeKeymap } from "./keys.js";

const EN = (document.documentElement.lang || navigator.language || "ja").startsWith("en");
const L = EN ? {
  dropFolder: "Drop a folder here to keep your sketches in",
  dropNote: "Tip: use a folder panel folder (e.g. registries\\Sketch) and share it with Claude as \"write\" in Hub settings. Claude can then edit the sketch.",
  numpy: "numpy is needed to make sounds. Run  py -m pip install numpy  and restart Hub.",
  newSketch: "New sketch", bpm: "BPM", key: "Key", major: "Major", minor: "Minor", bars: (n) => `${n} bar${n > 1 ? "s" : ""}`,
  penta: "5 in key", white: "Do-Re-Mi", play: "Play", stop: "Stop", rec: "Rec",
  parts: { drums: "Drums", bass: "Bass", chords: "Chords", melody: "Melody" },
  drums: { kick: "Kick", snare: "Snare", hat: "Hat", clap: "Clap" },
  mute: "Mute", repeat: (n) => `×${n}`, exportWav: "Export WAV", openFolder: "Open folder",
  exported: (f) => `Saved ${f}`, reloaded: "Reloaded (changed outside)", ime: "IME is on — keys may not play",
  hintPiano: "S D F J K L ; = Do Re Mi Fa So La Ti · hold Shift = ♯ · Z / X = octave · Space = play",
  hintDrums: "← ↓ ↑ → = drums · Space = play · R = record",
  hintChords: "S D F J K L ; = chords I–VII · hold Shift = 7th · click a chord to put it at the cursor",
  keymap: "Key assignments", preset: "Preset", presets: { default: "Default", numpad: "Drums on numpad", custom: "Custom" },
  reset: "Reset", exportKeys: "Export", importKeys: "Import", close: "Close", pressKey: "Press a key…",
  swapped: (a) => `Swapped with “${a}”`, groups: { drums: "Drums", piano: "Piano mode", ops: "Controls" },
  act: { kick: "Kick", snare: "Snare", hat: "Hat", clap: "Clap", w0: "Do (C)", w1: "Re (D)", w2: "Mi (E)", w3: "Fa (F)", w4: "So (G)", w5: "La (A)", w6: "Ti (B)",
    sharp: "♯ / 7th (hold)", play: "Play / stop", rec: "Record", mode: "Do-Re-Mi / 5 in key",
    octDown: "Octave down", octUp: "Octave up", partDrums: "Part: drums", partBass: "Part: bass", partChords: "Part: chords", partMelody: "Part: melody" },
  warn: "Some parts were skipped",
  padDrums: "Drum pads", padPiano: (p) => `Piano — ${p}`, sharpChip: "♯", sharpChord: "7th",
  stepRec: "Rec (stopped): keys write at the cursor and move it on", liveRec: "Rec: notes are written while playing", noRec: "Press R (record) to write what you play",
  triads: "Chords", sevenths: "7th chords", refLane: "Reference", refNone: "None",
  refEmpty: "Drop a WAV here or pick one on the left — it plays along with the sketch (a recording, an exported song, …)",
  refHelp: "Drag to line up the start · double-click = jump to where the sound begins", refRemove: "Remove the reference",
  refMissing: (f) => `${f} is not in the sketch folder`, refAdded: (f) => `Added ${f} as the reference`, clearPart: (p) => `Clear ${p}`, cleared: (p) => `Cleared ${p} (Ctrl+Z to undo)`, clickTip: "Click a key to put it at the cursor (▼)", rhythm: "Rhythm presets", rhythmSet: (n) => `Set “${n}” (Ctrl+Z to undo)`, del: "Delete", placeChord: "Pick a chord for this spot",
} : {
  dropFolder: "スケッチの保存先にするフォルダを、ここに落としてください",
  dropNote: "おすすめ: フォルダ窓のフォルダ（例: registries\\Sketch）を使い、Hub の設定で Claude に「読み書き」で共有すると、Claude がスケッチを直せます。",
  numpy: "音を作るには numpy が必要です。py -m pip install numpy を実行して、Hub を再起動してください。",
  newSketch: "新しいスケッチ", bpm: "BPM", key: "キー", major: "長調", minor: "短調", bars: (n) => `${n} 小節`,
  penta: "調の 5 音", white: "ドレミ", play: "再生", stop: "停止", rec: "録音",
  parts: { drums: "ドラム", bass: "ベース", chords: "コード", melody: "メロディ" },
  drums: { kick: "キック", snare: "スネア", hat: "ハット", clap: "クラップ" },
  mute: "ミュート", repeat: (n) => `×${n}`, exportWav: "WAV に書き出す", openFolder: "フォルダを開く",
  exported: (f) => `${f} を保存しました`, reloaded: "外で書き換えられたので読み直しました", ime: "日本語入力がオンです。キーが鳴らないことがあります",
  hintPiano: "S D F J K L ; = ドレミファソラシ ・ Shift を押しながら = ♯（半音上げ）・ Z / X = オクターブ ・ Space = 再生",
  hintDrums: "← ↓ ↑ → = ドラム ・ Space = 再生 ・ R = 録音",
  hintChords: "S D F J K L ; = コード I〜VII ・ Shift を押しながら = 7th ・ クリックでカーソルの位置に置く",
  keymap: "キーの割り当て", preset: "プリセット", presets: { default: "既定", numpad: "ドラムをテンキーに", custom: "カスタム" },
  reset: "既定に戻す", exportKeys: "書き出す", importKeys: "読み込む", close: "閉じる", pressKey: "キーを押してください…",
  swapped: (a) => `「${a}」と入れ替えました`, groups: { drums: "ドラム", piano: "ピアノモード", ops: "操作" },
  act: { kick: "キック", snare: "スネア", hat: "ハット", clap: "クラップ", w0: "ド", w1: "レ", w2: "ミ", w3: "ファ", w4: "ソ", w5: "ラ", w6: "シ",
    sharp: "♯ / 7th（押している間）", play: "再生 / 停止", rec: "録音", mode: "ドレミ / 調の 5 音",
    octDown: "オクターブ下", octUp: "オクターブ上", partDrums: "パート: ドラム", partBass: "パート: ベース", partChords: "パート: コード", partMelody: "パート: メロディ" },
  warn: "読み飛ばした所があります",
  padDrums: "ドラムパッド", padPiano: (p) => `ピアノ — ${p}`, sharpChip: "♯（半音上げ）", sharpChord: "7th",
  stepRec: "録音待機（停止中）: 押した音がカーソルの位置に入り、カーソルが進みます", liveRec: "録音中: 再生しながら押した音が入ります", noRec: "R（録音）を押すと、弾いた音が入ります",
  triads: "コード", sevenths: "7th のコード", refLane: "参考の音", refNone: "なし",
  refEmpty: "WAV をここに落とすか、左で選ぶと、スケッチと一緒に鳴ります（録音・書き出した曲など）",
  refHelp: "ドラッグで頭を合わせる ・ ダブルクリックで音の出だしに合わせる", refRemove: "参考の音を外す",
  refMissing: (f) => `${f} が保存先フォルダにありません`, refAdded: (f) => `${f} を参考の音にしました`, clearPart: (p) => `${p}を全部消す`, cleared: (p) => `${p}を消しました（Ctrl+Z で戻せます）`, clickTip: "クリックすると、カーソル（▼）の位置に入ります", rhythm: "リズムのプリセット", rhythmSet: (n) => `「${n}」にしました（Ctrl+Z で戻せます）`, del: "消す", placeChord: "ここに置くコードを選んでください",
};

const PARTS = ["drums", "bass", "chords", "melody"];
const SOLFA_EN = ["Do", "Re", "Mi", "Fa", "So", "La", "Ti"];
const SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const showName = (m) => `${SHARP_NAMES[m % 12]}${Math.floor(m / 12) - 1}`;   // 画面に出す音名（♯ で書く）
const DRUMS = ["kick", "snare", "hat", "clap"];
const DRUM_KEY = { kick: "kick", snare: "snare", hat: "hat", clap: "clap" };
// リズムのプリセット（1 小節 16 マス。小節の数だけ繰り返す）
const RHYTHMS = [
  { ja: "8 ビート", en: "8-beat", kick: "x.......x.x.....", snare: "....x.......x...", hat: "x.x.x.x.x.x.x.x." },
  { ja: "16 ビート", en: "16-beat", kick: "x.....x...x.....", snare: "....x.......x...", hat: "XxxxXxxxXxxxXxxx" },
  { ja: "4 つ打ち（ダンス）", en: "Four on the floor", kick: "x...x...x...x...", clap: "....x.......x...", hat: "..x...x...x...x." },
  { ja: "ロック", en: "Rock", kick: "x.....x.x.....x.", snare: "....x.......x...", hat: "x.x.x.x.x.x.x.x." },
  { ja: "ヒップホップ", en: "Hip-hop", kick: "x......x..x.....", snare: "....x.......x...", hat: "x.x.x.x.x.x.x.x." },
  { ja: "バラード", en: "Ballad", kick: "x.......x.......", snare: "....x.......x...", hat: "x...x...x...x..." },
  { ja: "レゲエ（ワンドロップ）", en: "Reggae (one drop)", kick: "........x.......", snare: "........x.......", hat: "..x...x...x...x." },
  { ja: "ボサノバ", en: "Bossa nova", kick: "x..xx..xx..xx..x", clap: "x..x..x...x..x..", hat: "x.x.x.x.x.x.x.x." },
  { ja: "ファンク", en: "Funk", kick: "x..x..x...x.....", snare: "....x..x.x..x...", hat: "xxxxxxxxxxxxxxxx" },
  { ja: "空にする", en: "Clear", kick: "", snare: "", hat: "", clap: "" },
];
const LANE = { head: 18, drums: 84, chords: 44, bass: 120, melody: 150, ref: 56, gap: 10 };
const LANES = ["drums", "bass", "chords", "melody", "ref"];        // ref = 参考の音（WAV）   // bass / melody は窓の高さに合わせて伸ばす
const svg = (d) => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const IC = {
  play: svg('<path d="M7 5v14l11-7z" fill="currentColor"/>'), stop: svg('<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>'),
  rec: svg('<circle cx="12" cy="12" r="6" fill="currentColor"/>'), plus: svg('<path d="M12 5v14M5 12h14"/>'),
  keys: svg('<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M8 14h8"/>'),
  folder: svg('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
  wave: svg('<path d="M3 12h2l2-6 3 12 3-9 2 6 2-3h4"/>'),
  trash: svg('<path d="M4 7h16M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13M9 7V4h6v3"/>'),
};

export async function mount(el, ctx) {
  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = new URL("./sketch.css", import.meta.url).href;
  document.head.append(css);

  // ---------- 状態 ----------
  let st = null;                 // api.state()
  let name = null;               // 開いているスケッチ
  let sk = null;                 // スケッチの中身（api.normalize 済み）
  let mtime = null;              // 自分が最後に保存／読み込んだ時の更新時刻
  let part = "drums";
  let mode = "white";            // white: ドレミ（ふつうの鍵盤）/ penta: 調の 5 音
  const octOff = { bass: 0, chords: 0, melody: 0 };
  let rec = false;
  let cursor = 0;                // 止まっているときに音を入れる位置（ステップ）
  const flashes = {};            // ドラムの行を一瞬光らせる（パート名 → 終わる時刻）
  let km = normalizeKeymap(await ctx.call("keymap_get").catch(() => null));
  const undo = [];
  const steps = () => 16 * sk.bars;
  const isPiano = () => part !== "drums";

  el.innerHTML = `<div class="sk"><div class="sk-empty" hidden></div><div class="sk-main" hidden></div></div>`;
  const root = el.querySelector(".sk");
  const empty = el.querySelector(".sk-empty");
  const main = el.querySelector(".sk-main");

  // ---------- 保存・読み込み ----------
  let saveTimer = null, saving = false;
  function changed(fn) {           // 変更の前に元に戻す用の写しを取り、描き直して、少し待ってから保存
    undo.push(JSON.stringify(sk));
    if (undo.length > 60) undo.shift();
    fn();
    draw();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 350);
  }
  async function save() {
    if (!name) return;
    clearTimeout(saveTimer);
    saveTimer = null;
    saving = true;
    try { mtime = (await ctx.call("save_sketch", { name, sketch: sk })).mtime; }
    catch (e) { ctx.toast(e.message, "error"); }
    finally { saving = false; }
  }
  async function open(n, quiet = false) {
    try {
      const r = await ctx.call("open_sketch", { name: n });
      name = r.name; sk = r.sketch; mtime = r.mtime;
      loadRef();
      if (r.warnings?.length) ctx.toast(`${L.warn}: ${r.warnings[0]}${r.warnings.length > 1 ? ` (+${r.warnings.length - 1})` : ""}`, "error", 6000);
      else if (quiet) ctx.toast(L.reloaded);
      render();
      preload();
    } catch (e) { ctx.toast(e.message, "error"); }
  }
  async function refresh() {
    st = await ctx.call("state");
    if (!st.folder) return showEmpty();
    if (!st.files.length) { const r = await ctx.call("new_sketch"); st = await ctx.call("state"); return open(r.name); }
    return open(st.current || st.files[st.files.length - 1]);
  }
  function showEmpty() {
    main.hidden = true; empty.hidden = false;
    empty.innerHTML = `<div class="sk-drop">${IC.folder}<p class="sk-drop-t"></p><p class="sk-drop-n"></p></div>`;
    empty.querySelector(".sk-drop-t").textContent = L.dropFolder;
    empty.querySelector(".sk-drop-n").textContent = L.dropNote;
  }
  ctx.onNativeDrop(async (paths) => {
    if (!paths?.length) return;
    try {
      if (/\.wav$/i.test(paths[0]) && st?.folder && sk) {      // WAV は参考の音に（保存先フォルダに写す）
        const r = await ctx.call("import_audio", { path: paths[0] });
        st.audio = (await ctx.call("state")).audio;
        await setRef(r.file);
        ctx.toast(L.refAdded(r.file));
        return;
      }
      await save(); await ctx.call("set_folder", { path: paths[0] }); await refresh();
    } catch (e) { ctx.toast(e.message, "error"); }
  });
  // 外（Claude・エディタ）で書き換えられたら読み直す
  setInterval(async () => {
    if (!name || saving || saveTimer || document.hidden) return;
    try {
      const r = await ctx.call("poll", { name });
      if (r.audio && JSON.stringify(r.audio) !== JSON.stringify(st.audio)) { st.audio = r.audio; buildLabels(); updateParts(); }
      if (r.mtime && mtime && Math.abs(r.mtime - mtime) > 1e-6 && !saving && !saveTimer) await open(name, true);
    } catch { /* フォルダが一時的に読めない等は次の回に */ }
  }, 1500);

  // ---------- 音 ----------
  let ac = null, master = null;
  const bufs = new Map(), loading = new Map();
  // 参考の音は <audio> で流す（長い録音でもメモリに全部は読まない）。Web Audio の音量につなぐ
  const refEl = new Audio();
  refEl.preload = "auto";
  let refGain = null, refInfo = null, refTimers = [];
  function applyRefGain() { if (refGain) refGain.gain.value = sk?.ref && !sk.ref.mute ? sk.ref.vol : 0; }
  async function loadRef() {
    refInfo = null;
    if (!sk?.ref) { refEl.removeAttribute("src"); refEl.load(); draw(); return; }
    try {
      refInfo = await ctx.call("ref_info", { file: sk.ref.file });
      refEl.src = `/blob/sketch/${refInfo.key}?t=${encodeURIComponent(TOKEN)}`;
    } catch (e) { ctx.toast(e.message, "error", 6000); }
    applyRefGain(); draw();
  }
  async function setRef(file) {
    changed(() => { sk.ref = file ? { file, offset: 0, vol: sk.ref?.vol ?? 0.8, mute: false } : null; });
    await loadRef();
    if (sk.ref && refInfo) { sk.ref.offset = refInfo.onset; draw(); }   // 頭の無音は飛ばして、音の出だしに合わせる
    buildLabels(); updateParts();
    if (playing) syncRef();
  }
  // 再生の頭（ループの頭）で、参考の音を offset 秒から鳴らし直す
  function refAt(when) {
    refTimers.push(setTimeout(() => {
      if (!playing || !sk.ref || !refInfo) return;
      try { refEl.currentTime = sk.ref.offset; refEl.play().catch(() => {}); } catch { /* 読み込み中 */ }
    }, Math.max(0, (when - ac.currentTime) * 1000)));
  }
  function syncRef() {   // 今の位置に合わせる（再生中に頭をずらしたとき）
    if (!playing || !sk.ref || !refInfo) return;
    try { refEl.currentTime = sk.ref.offset + position() * stepSec(); refEl.play().catch(() => {}); } catch { /* 読み込み中 */ }
  }
  function stopRef() { refTimers.forEach(clearTimeout); refTimers = []; refEl.pause(); }
  function audio() {
    if (!ac) {
      ac = new AudioContext(); master = ac.createGain(); master.gain.value = 0.9; master.connect(ac.destination);
      refGain = ac.createGain(); ac.createMediaElementSource(refEl).connect(refGain).connect(master); applyRefGain();
    }
    if (ac.state === "suspended") ac.resume();
    return ac;
  }
  function load(key) {
    if (bufs.has(key)) return Promise.resolve(bufs.get(key));
    if (!loading.has(key)) {
      loading.set(key, fetch(`/blob/sketch/${key}?t=${encodeURIComponent(TOKEN)}`)
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.arrayBuffer(); })
        .then((a) => audio().decodeAudioData(a))
        .then((b) => { bufs.set(key, b); return b; })
        .catch((e) => { loading.delete(key); throw e; }));
    }
    return loading.get(key);
  }
  const drumKey = (d) => `d-${d}.wav`;
  const voiceKey = (p, midi) => `v-${VOICE[p]}-${midi}.wav`;
  function preload() {
    if (!st?.numpy) return;
    const keys = new Set(DRUMS.map(drumKey));
    for (const p of ["bass", "melody"]) {
      for (const n of sk[p]) keys.add(voiceKey(p, noteMidi(n.note)));
      for (let i = 0; i < 7; i++) for (const sharp of [false, true]) {
        keys.add(voiceKey(p, keyMidi({ ...sk, mode, part: p, octOff: octOff[p], idx: i, sharp })));
      }
    }
    for (const c of sk.chords) for (const m of chordMidis(c.name, 3)) keys.add(voiceKey("chords", m));
    for (let i = 0; i < 7; i++) {                // コードのキー（I〜VII と 7th）
      for (const seventh of [false, true]) {
        const nm = keyChord({ ...sk, idx: i, seventh });
        for (const m of chordMidis(nm, 3 + octOff.chords)) keys.add(voiceKey("chords", m));
      }
    }
    for (const k of keys) load(k).catch(() => {});
  }
  // when に鳴らす。dur（秒）があれば、その長さで切る。無ければ stop() を呼ぶまで鳴る（押している間）
  function sound(key, when, dur, gain) {
    const b = bufs.get(key);
    if (!b) { load(key).catch(() => {}); return null; }
    const src = ac.createBufferSource();
    src.buffer = b;
    const g = ac.createGain();
    g.gain.value = gain;
    src.connect(g).connect(master);
    src.start(when);
    const stop = (at) => {
      try { g.gain.setValueAtTime(gain, at); g.gain.linearRampToValueAtTime(0, at + 0.06); src.stop(at + 0.08); } catch { /* 済み */ }
    };
    if (dur != null) stop(when + Math.min(dur, b.duration - 0.08));
    return { stop: () => stop(ac.currentTime) };
  }
  const vol = (p) => (sk.mix[p].mute ? 0 : sk.mix[p].vol);
  const drumGain = (ch) => vol("drums") * (ch === "X" ? 1 : 0.72);

  // ---------- 再生（先読みしながら少し先まで予約する） ----------
  let playing = false, timer = null, nextStep = 0, nextTime = 0;
  const stepSec = () => 60 / sk.bpm / 4;
  function position() {       // 今の位置（ステップ、小数）
    if (!playing) return 0;
    const s = steps();
    return (((nextStep - (nextTime - ac.currentTime) / stepSec()) % s) + s) % s;
  }
  function schedule(step, t) {
    const sd = stepSec();
    for (const d of DRUMS) { const ch = sk.drums[d][step]; if (ch === "x" || ch === "X") sound(drumKey(d), t, null, drumGain(ch)); }
    for (const p of ["bass", "melody"]) for (const n of sk[p]) if (n.at === step) sound(voiceKey(p, noteMidi(n.note)), t, n.len * sd, vol(p));
    for (const c of sk.chords) if (c.at === step) for (const m of chordMidis(c.name, 3)) sound(voiceKey("chords", m), t, c.len * sd, vol("chords") * 0.85);
  }
  function tick() {
    while (nextTime < ac.currentTime + 0.12) {
      if (nextStep === 0) { refTimers = refTimers.slice(-4); refAt(nextTime); }
      schedule(nextStep, nextTime);
      nextTime += stepSec();
      nextStep = (nextStep + 1) % steps();
    }
  }
  function setPlaying(on) {
    if (on === playing || !sk) return;
    if (on) {
      audio(); preload();
      nextStep = 0; nextTime = ac.currentTime + 0.06; playing = true;
      timer = setInterval(tick, 25); tick();
      requestAnimationFrame(frame);
      updatePad();
    } else {
      playing = false; clearInterval(timer); stopRef();
      for (const h of held.values()) h.voice?.forEach((v) => v?.stop());
    }
    updateTransport(); updatePad(); draw();
  }
  function frame() { if (!playing) return; draw(); requestAnimationFrame(frame); }

  // ---------- 叩いて入れる ----------
  const held = new Map();          // code → { voice, startPos, idx, part }
  function hitDrum(d, accent) {
    audio();
    flash(d);
    flashes[d] = performance.now() + 160;
    draw(); setTimeout(draw, 170);
    sound(drumKey(d), ac.currentTime, null, drumGain(accent ? "X" : "x"));
    if (!(rec && playing)) return;
    const s = Math.round(position()) % steps();
    changed(() => { const a = sk.drums[d].split(""); a[s] = accent ? "X" : (a[s] === "X" ? "X" : "x"); sk.drums[d] = a.join(""); });
  }
  function noteDown(code, idx, opt = {}) {
    audio();
    const sharp = opt.sharp ?? down.has(km.sharp);
    let voices, info;
    if (part === "chords") {
      const nm = keyChord({ ...sk, idx, seventh: sharp });      // コードでは Shift = 7th
      voices = chordMidis(nm, 3 + octOff.chords).map((m) => sound(voiceKey("chords", m), ac.currentTime, null, vol("chords") * 0.85));
      info = { chord: nm };
      ctx.setStatus(nm);
    } else {
      const midi = keyMidi({ ...sk, mode, part, octOff: octOff[part], idx, sharp });
      voices = [sound(voiceKey(part, midi), ac.currentTime, null, vol(part))];
      info = { midi };
      ctx.setStatus(showName(midi));
    }
    held.set(code, { voice: voices, part, startPos: position(), idx, sharp, mouse: !!opt.mouse, ...info });
    updatePad(); draw();
  }
  function noteUp(code) {
    const h = held.get(code);
    if (!h) return;
    held.delete(code);
    h.voice.forEach((v) => v?.stop());
    updatePad(); draw();
    if (h.part !== part) return;
    if (!playing && (rec || h.mouse)) return stepInput(h);     // 止まっているとき: マウスで押した音は、そのままカーソルの位置に入る
    if (!rec && !h.mouse) return;                               // 再生中: 録音中か、マウスで押した音だけ入れる
    const s = steps();
    let len = position() - h.startPos;
    if (len < 0) len += s;
    if (h.chord) {             // コードは半小節（8 マス）にそろえる
      const at = (Math.round(h.startPos / 8) * 8) % s;
      const ln = Math.min(Math.max(8, Math.round(len / 8) * 8), s - at);
      placeChord(at, ln, h.chord);
    } else {
      const at = Math.round(h.startPos) % s;
      const ln = Math.min(Math.max(1, Math.round(len)), s - at);
      changed(() => { sk[h.part].push({ at, note: midiName(h.midi), len: ln }); sk[h.part].sort((a, b) => a.at - b.at); });
    }
  }

  // 止まっているときの録音: カーソルの位置に置いて、カーソルを進める
  function stepInput(h) {
    const s = steps();
    if (h.chord) {
      const { at, ln } = chordSlot(cursor);
      placeChord(at, ln, h.chord);
      cursor = (at + ln) % s;
    } else {
      const at = cursor, ln = Math.min(2, s - at);
      changed(() => { sk[h.part].push({ at, note: midiName(h.midi), len: ln }); sk[h.part].sort((a, b) => a.at - b.at); });
      cursor = (at + ln) % s;
    }
    draw();
  }
  function placeChord(at, ln, name) {
    changed(() => {
      sk.chords = sk.chords.filter((c) => c.at < at || c.at >= at + ln)
        .map((c) => (c.at < at && c.at + c.len > at ? { ...c, len: at - c.at } : c));
      sk.chords.push({ at, name, len: ln });
      sk.chords.sort((a, b) => a.at - b.at);
    });
  }

  // ---------- キー ----------
  const down = new Set();
  let capture = null;              // キーの割り当て画面で、次に押されたキーを受け取る役目
  let imeTimer = null;
  const actionOf = (code) => Object.keys(km).find((a) => a !== "_v" && km[a] === code);
  function onKeyDown(e) {
    if (capture) { e.preventDefault(); e.stopPropagation(); return capture(e); }
    if (!sk || main.hidden) return;
    if (e.isComposing || e.key === "Process") { showIme(); return; }
    const tag = e.target?.tagName;
    if ((tag === "INPUT" && e.target.type !== "range") || tag === "TEXTAREA" || document.querySelector(".menu") || !overlay.hidden) return;
    // 直前に押したボタンにフォーカスが残っていると、Space / Enter でそのボタンまで押されてしまうので外す
    if (tag === "BUTTON" || tag === "INPUT") document.activeElement.blur();
    if ((e.ctrlKey || e.metaKey) && e.code === "KeyZ") { e.preventDefault(); return doUndo(); }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    down.add(e.code);
    if (e.code === km.sharp) updatePad();
    const a = actionOf(e.code);
    const key = a && /^([wb])(\d)$/.exec(a);
    if (key && isPiano()) {
      e.preventDefault();
      const idx = Number(key[2]), black = key[1] === "b";
      if (part === "chords" && (black || idx > 6)) return;     // コードは白鍵 7 つ（I〜VII）
      if (mode === "penta" && black) return;                    // 「調の 5 音」では黒鍵は使わない
      if (!e.repeat && !held.has(e.code)) noteDown(e.code, idx, black ? { sharp: true } : {});
      return;
    }
    if (a && DRUM_KEY[a]) { e.preventDefault(); if (!e.repeat) hitDrum(a, e.shiftKey); return; }
    if (e.repeat) { if (a || e.code === "Space") e.preventDefault(); return; }
    switch (a) {
      case "play": e.preventDefault(); return setPlaying(!playing);
      case "rec": e.preventDefault(); rec = !rec; updateTransport(); return updatePad();
      case "mode": e.preventDefault(); mode = mode === "white" ? "penta" : "white"; updateHead(); updatePad(); return preload();
      case "octDown": case "octUp":
        if (isPiano()) { e.preventDefault(); octOff[part] = Math.max(-2, Math.min(2, octOff[part] + (a === "octUp" ? 1 : -1))); updateParts(); updatePad(); preload(); }
        return;
      case "partDrums": case "partBass": case "partChords": case "partMelody":
        e.preventDefault(); return selectPart(a.slice(4).toLowerCase());
    }
    if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); }   // ピアノモード以外の Space は再生
  }
  function onKeyUp(e) {
    down.delete(e.code);
    if (e.code === km.sharp) updatePad();
    if (held.has(e.code)) noteUp(e.code);
  }
  function releaseAll() { down.clear(); for (const c of [...held.keys()]) noteUp(c); }
  function showIme() {
    root.querySelector(".sk-ime")?.removeAttribute("hidden");
    clearTimeout(imeTimer);
    imeTimer = setTimeout(() => root.querySelector(".sk-ime")?.setAttribute("hidden", ""), 4000);
  }
  window.addEventListener("keydown", onKeyDown, true);
  window.addEventListener("keyup", onKeyUp, true);
  window.addEventListener("blur", releaseAll);

  function doUndo() {
    const prev = undo.pop();
    if (!prev) return;
    sk = JSON.parse(prev);
    render(); loadRef();
    clearTimeout(saveTimer); saveTimer = setTimeout(save, 200);
  }
  function selectPart(p) {
    releaseAll();
    part = p;
    updateParts(); updateHint(); buildPad(); preload();
  }

  // ---------- 画面 ----------
  function render() {
    empty.hidden = true; main.hidden = false;
    main.innerHTML = `
      <div class="sk-head">
        <button type="button" class="btn primary sk-play"></button>
        <button type="button" class="btn sk-rec">${IC.rec}<span>${L.rec}</span></button>
        <span class="sk-sep"></span>
        <span class="sk-file"></span><button type="button" class="icon-btn sk-new">${IC.plus}</button>
        <span class="sk-sep"></span>
        <label class="sk-f"><span>${L.bpm}</span><input class="input sk-bpm" type="number" min="40" max="240" step="1" inputmode="numeric"></label>
        <span class="sk-key"></span><span class="sk-scale"></span><span class="sk-bars"></span>
        <span class="sk-ime" hidden></span>
      </div>
      <div class="sk-body">
        <div class="sk-labels"></div>
        <div class="sk-roll"><canvas class="sk-cv"></canvas></div>
      </div>
      <div class="sk-pad">
        <div class="sk-pad-head"><span class="sk-pad-title"></span>
          <div class="seg seg-sm sk-mode" role="radiogroup"><button type="button" role="radio" data-m="white"><span>${L.white}</span></button><button type="button" role="radio" data-m="penta"><span>${L.penta}</span></button></div>
          <span class="sk-rhythm"></span><span class="sk-pad-mods"></span><span class="sk-pad-rec"></span></div>
        <div class="sk-pad-keys"></div>
      </div>
      <div class="sk-foot">
        <span class="sk-hint"></span>
        <span class="sk-rep"></span>
        <button type="button" class="btn primary sk-export">${IC.wave}<span>${L.exportWav}</span></button>
        <button type="button" class="btn sk-folder">${IC.folder}<span>${L.openFolder}</span></button>
      </div>`;
    const $ = (q) => main.querySelector(q);
    $(".sk-ime").textContent = L.ime;
    $(".sk-new").title = L.newSketch;
    if (!st.numpy) { const w = document.createElement("div"); w.className = "sk-warn"; w.textContent = L.numpy; main.prepend(w); }

    $(".sk-file").append(selectBox({ options: st.files.map((f) => ({ value: f, label: f })), value: name,
      onChange: async (v) => { await save(); st.current = v; open(v); } }));
    $(".sk-new").addEventListener("click", async () => {
      try { await save(); const r = await ctx.call("new_sketch"); st = await ctx.call("state"); open(r.name); } catch (e) { ctx.toast(e.message, "error"); }
    });
    const bpm = $(".sk-bpm");
    bpm.value = sk.bpm;
    bpm.addEventListener("change", () => {
      const v = Math.max(40, Math.min(240, Math.round(Number(bpm.value) || sk.bpm)));
      bpm.value = v; changed(() => { sk.bpm = v; });
    });
    bpm.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === "Escape") bpm.blur(); });
    $(".sk-key").append(selectBox({ options: KEYS.map((k) => ({ value: k, label: `${L.key} ${k}` })), value: sk.key,
      onChange: (v) => { changed(() => { sk.key = v; }); preload(); } }));
    $(".sk-scale").append(selectBox({ options: [{ value: "major", label: L.major }, { value: "minor", label: L.minor }], value: sk.scale,
      onChange: (v) => { changed(() => { sk.scale = v; }); preload(); } }));
    $(".sk-bars").append(selectBox({ options: [1, 2, 4, 8].map((n) => ({ value: n, label: L.bars(n) })), value: sk.bars,
      onChange: (v) => changed(() => resizeBars(Number(v))) }));
    main.querySelectorAll(".sk-mode button").forEach((b) => b.addEventListener("click", () => { mode = b.dataset.m; updateHead(); updatePad(); preload(); }));
    $(".sk-play").addEventListener("click", () => setPlaying(!playing));
    $(".sk-rec").addEventListener("click", () => { rec = !rec; updateTransport(); updatePad(); });
    let repeat = 2;
    $(".sk-rep").append(selectBox({ options: [1, 2, 4, 8].map((n) => ({ value: n, label: L.repeat(n) })), value: repeat, onChange: (v) => { repeat = Number(v); } }));
    $(".sk-export").addEventListener("click", async (ev) => {
      const b = ev.currentTarget; b.disabled = true;
      try {
        await save();
        const r = await ctx.call("export_wav", { name, repeat });
        ctx.toast(L.exported(r.file));
        st.lastExport = r.path;
      } catch (e) { ctx.toast(e.message, "error", 6000); }
      finally { b.disabled = false; }
    });
    $(".sk-folder").addEventListener("click", () => ctx.host.revealPath(st.lastExport || st.folder).catch(() => ctx.host.openPath(st.folder)));

    $(".sk-rhythm").append(selectBox({ options: [{ value: "", label: L.rhythm }, ...RHYTHMS.map((r, i) => ({ value: String(i), label: EN ? r.en : r.ja }))],
      value: "", onChange: (v) => {
        if (v === "") return;
        const r = RHYTHMS[Number(v)];
        changed(() => { for (const d of DRUMS) sk.drums[d] = (r[d] || "................").repeat(sk.bars); });
        ctx.toast(L.rhythmSet(EN ? r.en : r.ja));
      } }));
    buildLabels();
    const cv = $(".sk-cv");
    cv.addEventListener("pointerdown", onCanvas);
    cv.addEventListener("contextmenu", eraseAt);
    cv.addEventListener("dblclick", (e) => {
      const y = e.clientY - cv.getBoundingClientRect().top, rt = laneTop("ref");
      if (y >= rt && y < rt + LANE.ref && sk.ref && refInfo) { changed(() => { sk.ref.offset = refInfo.onset; }); if (playing) syncRef(); }
    });
    new ResizeObserver(() => { if (layoutLanes()) { buildLabels(); updateParts(); } else draw(); }).observe($(".sk-body"));
    layoutLanes();
    updateHead(); updateTransport(); updateParts(); updateHint(); buildPad();
    ctx.setTitle(name);
    draw();
  }
  function resizeBars(n) {
    const s = 16 * n;
    sk.bars = n;
    for (const d of DRUMS) sk.drums[d] = (sk.drums[d] + ".".repeat(s)).slice(0, s);
    for (const p of ["bass", "melody", "chords"]) sk[p] = sk[p].filter((x) => x.at < s).map((x) => ({ ...x, len: Math.min(x.len, s - x.at) }));
  }
  function laneTop(p) {
    let y = LANE.head;
    for (const q of LANES) { if (q === p) return y; y += LANE[q] + LANE.gap; }
    return y;
  }
  const totalH = () => laneTop("ref") + LANE.ref + 4;
  function buildLabels() {
    const box = main.querySelector(".sk-labels");
    box.style.height = `${totalH()}px`;
    box.innerHTML = "";
    const hintKey = { drums: km.partDrums, bass: km.partBass, chords: km.partChords, melody: km.partMelody };
    for (const p of PARTS) {
      const row = document.createElement("div");
      row.className = "sk-lab";
      row.dataset.p = p;
      row.style.top = `${laneTop(p)}px`;
      row.style.height = `${LANE[p]}px`;
      row.innerHTML = `<div class="sk-lab-top"><button type="button" class="sk-lab-name"><span></span><kbd></kbd></button><span class="sk-lab-oct"></span></div>
        <div class="sk-lab-ctl"><button type="button" class="sk-mute" aria-pressed="false">M</button><input type="range" class="sk-vol" min="0" max="1" step="0.05"><button type="button" class="sk-clear">${IC.trash}</button></div>`;
      row.querySelector(".sk-lab-name span").textContent = L.parts[p];
      row.querySelector("kbd").textContent = keyLabel(hintKey[p]);
      row.querySelector(".sk-lab-name").addEventListener("click", () => selectPart(p));
      const mute = row.querySelector(".sk-mute");
      mute.title = L.mute;
      mute.addEventListener("click", () => changed(() => { sk.mix[p].mute = !sk.mix[p].mute; }) || updateParts());
      const clr = row.querySelector(".sk-clear");
      clr.title = L.clearPart(L.parts[p]);
      clr.addEventListener("click", () => {
        changed(() => { if (p === "drums") for (const d of DRUMS) sk.drums[d] = ".".repeat(steps()); else sk[p] = []; });
        ctx.toast(L.cleared(L.parts[p]));
      });
      const v = row.querySelector(".sk-vol");
      v.value = sk.mix[p].vol;
      v.addEventListener("input", () => { sk.mix[p].vol = Number(v.value); });
      v.addEventListener("change", () => changed(() => { sk.mix[p].vol = Number(v.value); }));
      if (p === "drums") {
        const names = document.createElement("div");
        names.className = "sk-drum-names";
        names.innerHTML = DRUMS.map((d) => `<span>${L.drums[d]} <kbd>${keyLabel(km[d])}</kbd></span>`).join("");
        row.append(names);
      }
      box.append(row);
    }
    box.append(refLabel());
  }
  // 参考の音の行: WAV を選ぶ・ミュート・音量・外す
  function refLabel() {
    const row = document.createElement("div");
    row.className = "sk-lab sk-lab-ref";
    row.style.top = `${laneTop("ref")}px`;
    row.style.height = `${LANE.ref}px`;
    row.innerHTML = `<div class="sk-lab-top"><span class="sk-lab-name"><span></span></span><span class="sk-ref-file"></span></div>
      <div class="sk-lab-ctl"><button type="button" class="sk-mute" aria-pressed="false">M</button><input type="range" class="sk-vol" min="0" max="1" step="0.05"><button type="button" class="sk-clear">${IC.trash}</button></div>`;
    row.querySelector(".sk-lab-name span").textContent = L.refLane;
    const r = sk.ref;
    row.querySelector(".sk-ref-file").append(selectBox({
      options: [{ value: "", label: L.refNone }, ...(st.audio || []).map((f) => ({ value: f, label: f }))],
      value: r?.file || "", onChange: (v) => setRef(v || null),
    }));
    const mute = row.querySelector(".sk-mute");
    mute.title = L.mute;
    mute.setAttribute("aria-pressed", String(!!r?.mute));
    mute.disabled = !r;
    mute.addEventListener("click", () => { changed(() => { sk.ref.mute = !sk.ref.mute; }); applyRefGain(); mute.setAttribute("aria-pressed", String(sk.ref.mute)); });
    const v = row.querySelector(".sk-vol");
    v.value = r?.vol ?? 0.8;
    v.disabled = !r;
    v.addEventListener("input", () => { sk.ref.vol = Number(v.value); applyRefGain(); });
    v.addEventListener("change", () => changed(() => { sk.ref.vol = Number(v.value); }));
    const clr = row.querySelector(".sk-clear");
    clr.title = L.refRemove;
    clr.disabled = !r;
    clr.addEventListener("click", () => setRef(null));
    return row;
  }
  function updateHead() {
    main.querySelectorAll(".sk-mode button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.m === mode)));
  }
  function updateTransport() {
    const p = main.querySelector(".sk-play"), r = main.querySelector(".sk-rec");
    if (!p) return;
    p.innerHTML = `${playing ? IC.stop : IC.play}<span>${playing ? L.stop : L.play}</span>`;
    r.classList.toggle("on", rec);
    r.setAttribute("aria-pressed", String(rec));
  }
  function updateParts() {
    main.querySelectorAll(".sk-lab:not(.sk-lab-ref)").forEach((row) => {
      const p = row.dataset.p;
      row.classList.toggle("sel", p === part);
      row.querySelector(".sk-mute").setAttribute("aria-pressed", String(sk.mix[p].mute));
      const o = row.querySelector(".sk-lab-oct");
      o.textContent = p === "drums" ? "" : `Oct ${BASE_OCT[p] + octOff[p]}`;
    });
    draw();
  }
  function updateHint() {
    const h = main.querySelector(".sk-hint");
    if (h) h.textContent = part === "drums" ? L.hintDrums : part === "chords" ? L.hintChords : L.hintPiano;
  }

  // ---------- 鍵盤・パッド（どのキーで何が鳴るかを見せる。マウスでも押せる） ----------
  // ベース・メロディ: 7 つの白鍵（ドレミファソラシ）と黒鍵（♯）。コード: その調の I〜VII。ドラム: 4 つのパッドとリズムのプリセット
  function capButton(cls, code, onDown) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.innerHTML = `<kbd></kbd><b></b><small></small>`;
    b.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      b.setPointerCapture(e.pointerId);
      onDown(e);
    });
    const up = () => { if (held.has(code)) noteUp(code); };
    b.addEventListener("pointerup", up);
    b.addEventListener("pointercancel", up);
    return b;
  }
  function buildPad() {
    const box = main.querySelector(".sk-pad-keys");
    if (!box) return;
    box.innerHTML = "";
    box.className = `sk-pad-keys ${part === "drums" ? "drums" : part === "chords" ? "chords" : "kb"}`;
    const presets = main.querySelector(".sk-rhythm");
    presets.hidden = part !== "drums";
    if (part === "drums") {
      for (const d of DRUMS) {
        const b = capButton("sk-cap", `pad-${d}`, (e) => hitDrum(d, e.shiftKey));
        b.dataset.k = d;
        box.append(b);
      }
    } else {
      const n = 7;
      for (let i = 0; i < n; i++) {
        const b = capButton(part === "chords" ? "sk-cap" : "sk-cap sk-white", `pad-${i}`, () => noteDown(`pad-${i}`, i, { mouse: true }));
        b.dataset.k = String(i);
        box.append(b);
      }
      if (part !== "chords") {            // 黒鍵（ド♯ レ♯ ファ♯ ソ♯ ラ♯ …）。白鍵の境目に重ねる
        for (const i of [0, 1, 3, 4, 5]) {
          const b = capButton("sk-black", `pad-b${i}`, () => noteDown(`pad-b${i}`, i, { mouse: true, sharp: true }));
          b.dataset.k = String(i);
          b.style.left = `calc(${(i + 1) / n * 100}% - 16px)`;
          box.append(b);
        }
      }
    }
    updatePad();
  }
  function updatePad() {
    const box = main.querySelector(".sk-pad-keys");
    if (!box || !sk) return;
    const sharp = down.has(km.sharp);
    const mods = main.querySelector(".sk-pad-mods");
    const rh = main.querySelector(".sk-pad-rec");
    main.querySelector(".sk-mode").hidden = part !== "bass" && part !== "melody";
    if (part === "drums") {
      main.querySelector(".sk-pad-title").textContent = L.padDrums;
      rh.textContent = ""; mods.innerHTML = "";
      box.querySelectorAll(".sk-cap").forEach((b) => {
        b.querySelector("kbd").textContent = keyLabel(km[b.dataset.k]);
        b.querySelector("b").textContent = L.drums[b.dataset.k];
      });
      return;
    }
    main.querySelector(".sk-pad-title").textContent = L.padPiano(`${L.parts[part]} · Oct ${BASE_OCT[part] + octOff[part]}`);
    rh.textContent = rec ? (playing ? L.liveRec : L.stepRec) : (playing ? L.noRec : L.clickTip);
    rh.classList.toggle("on", rec);
    mods.innerHTML = `<span class="sk-chip" data-on="${sharp}"><kbd></kbd></span>`;
    const c1 = mods.querySelector(".sk-chip");
    c1.querySelector("kbd").textContent = keyLabel(km.sharp); c1.append(` ${part === "chords" ? L.sharpChord : L.sharpChip}`);
    const on = new Set([...held.entries()].map(([code, h]) => (code.startsWith("pad-b") || (h.sharp && part !== "chords") ? `b${h.idx}` : `w${h.idx}`)));
    box.querySelectorAll(".sk-cap").forEach((b) => {
      const idx = Number(b.dataset.k);
      b.querySelector("kbd").textContent = keyLabel(km[`w${idx}`]);
      if (part === "chords") {
        b.querySelector("b").textContent = keyChord({ ...sk, idx, seventh: sharp });
        b.querySelector("small").textContent = ROMAN[sk.scale][idx];
      } else {
        const midi = keyMidi({ ...sk, mode, part, octOff: octOff[part], idx, sharp: false });
        b.querySelector("b").textContent = mode === "white" ? (EN ? SOLFA_EN : SOLFA)[idx % 7] : midiName(midi);
        b.querySelector("small").textContent = mode === "white" ? midiName(midi) : (inScale(midi, sk.key, sk.scale) ? "" : "");
        b.classList.toggle("in-key", inScale(midi, sk.key, sk.scale));
      }
      b.classList.toggle("on", on.has(`w${idx}`));
    });
    box.querySelectorAll(".sk-black").forEach((b) => {
      const idx = Number(b.dataset.k);
      const midi = keyMidi({ ...sk, mode, part, octOff: octOff[part], idx, sharp: true });
      b.hidden = mode !== "white";
      b.querySelector("kbd").textContent = `⇧${keyLabel(km[`w${idx}`])}`;
      b.querySelector("b").textContent = "";
      b.querySelector("small").textContent = SHARP_NAMES[midi % 12];       // 半音上げなので ♯ で書く（C# D# F# G# A#）
      b.classList.toggle("in-key", inScale(midi, sk.key, sk.scale));
      b.classList.toggle("on", on.has(`b${idx}`));
    });
  }
  function flash(d) {
    const b = main.querySelector(`.sk-pad-keys.drums .sk-cap[data-k="${d}"]`);
    if (!b) return;
    b.classList.add("on");
    setTimeout(() => b.classList.remove("on"), 120);
  }

  // ---------- 描画（1 枚の Canvas に全パート） ----------
  let colors = null, colorsAt = 0;
  function palette() {
    if (colors && performance.now() - colorsAt < 2000) return colors;
    const cs = getComputedStyle(document.documentElement);
    const v = (k, d) => cs.getPropertyValue(k).trim() || d;
    colorsAt = performance.now();
    return (colors = { text: v("--text", "#eee"), muted: v("--muted", "#aaa"), faint: v("--faint", "#777"), ink2: v("--ink-2", "#222"),
      ink3: v("--ink-3", "#2c2c2c"), ink4: v("--ink-4", "#383838"), line: v("--line", "#333"), signal: v("--signal", "#7cf"),
      c1: v("--c1-rgb", "120,160,255"), c2: v("--c2-rgb", "160,120,255"), c3: v("--c3-rgb", "255,140,180") });
  }
  function geom() {
    const cv = main.querySelector(".sk-cv");
    const w = main.querySelector(".sk-roll").clientWidth;
    return { cv, w, h: totalH(), sw: w / steps() };
  }
  // ピアノロールに出す音の範囲。鍵盤の今のオクターブ（ベースは 1 つ下から）2 オクターブ分を基本に、
  // 置いてある音符がはみ出すときは広げる（下の音が隠れないように）。C から B までのオクターブ単位、最大 4 オクターブ
  function pitchRange(p) {
    const base = 12 * (BASE_OCT[p] + octOff[p] + 1) - (p === "bass" ? 12 : 0);
    let lo = base, hi = base + 24;
    for (const n of sk[p]) { const m = noteMidi(n.note); if (m < lo) lo = m; if (m > hi) hi = m; }
    lo -= ((lo % 12) + 12) % 12;
    hi += 11 - (((hi % 12) + 12) % 12);
    if (hi - lo + 1 > 48) hi = lo + 47;
    return { lo, hi, span: hi - lo + 1 };
  }
  // 窓の高さに合わせて、ベースとメロディの行を広げる（押しやすく・消しやすく）
  function layoutLanes() {
    const body = main.querySelector(".sk-body");
    if (!body) return false;
    const fixed = LANE.head + LANE.drums + LANE.chords + LANE.ref + LANE.gap * 4 + 8;
    const rest = Math.max(216, body.clientHeight - 16 - fixed);
    const bass = Math.round(rest * 0.45), melody = rest - bass;
    if (bass === LANE.bass && melody === LANE.melody) return false;
    LANE.bass = bass; LANE.melody = melody;
    return true;
  }
  function draw() {
    if (!sk || main.hidden) return;
    const { cv, w, h, sw } = geom();
    if (!w) return;
    const dpr = devicePixelRatio || 1;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.height = `${h}px`;
    }
    const g = cv.getContext("2d");
    const c = palette();
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const S = steps();
    const grad = (a) => { const gr = g.createLinearGradient(0, 0, w, 0); gr.addColorStop(0, `rgba(${c.c1},${a})`); gr.addColorStop(0.5, `rgba(${c.c2},${a})`); gr.addColorStop(1, `rgba(${c.c3},${a})`); return gr; };

    // 小節番号と拍の線
    g.font = "10px system-ui, sans-serif";
    g.fillStyle = c.faint;
    for (let b = 0; b < sk.bars; b++) g.fillText(String(b + 1), b * 16 * sw + 4, 12);
    for (const p of PARTS) {
      const y = laneTop(p), lh = LANE[p];
      g.fillStyle = p === part ? c.ink3 : c.ink2;
      roundRect(g, 0, y, w, lh, 6); g.fill();
      if (p === "bass" || p === "melody") {          // 調の中の音の行を少し明るく
        const { lo, span } = pitchRange(p), rh = lh / span;
        g.fillStyle = c.ink4;
        g.globalAlpha = 0.45;
        for (let i = 0; i < span; i++) if (inScale(lo + i, sk.key, sk.scale)) g.fillRect(0, y + lh - (i + 1) * rh, w, rh - 0.5);
        g.globalAlpha = 1;
        g.globalAlpha = 0.5;
        for (let i = 0; i < span; i += 12) { g.fillStyle = c.line; g.fillRect(0, y + lh - (i + 1) * rh + rh - 1, w, 1); }
        g.globalAlpha = 1;
        g.fillStyle = c.faint; g.font = "10px system-ui, sans-serif";      // オクターブの目印（C2, C3 …）
        for (let i = 0; i < span; i += 12) g.fillText(`C${Math.floor((lo + i) / 12) - 1}`, w - 22, y + lh - i * rh - 2);
      }
      for (let s = 0; s <= S; s += 4) {
        g.fillStyle = s % 16 === 0 ? c.faint : c.line;
        g.globalAlpha = s % 16 === 0 ? 0.6 : 0.5;
        g.fillRect(Math.round(s * sw), y, 1, lh);
      }
      g.globalAlpha = 1;
    }
    drawRef(g, c, w, sw, grad);
    // ドラム
    const dy = laneTop("drums"), rh = LANE.drums / 4;
    DRUMS.forEach((d, r) => {
      for (let s = 0; s < S; s++) {
        const ch = sk.drums[d][s];
        const x = s * sw + 2, yy = dy + r * rh + 3, cw = Math.max(2, sw - 4), chh = rh - 6;
        if (ch === "x" || ch === "X") { g.fillStyle = grad(ch === "X" ? 1 : 0.7); roundRect(g, x, yy, cw, chh, 3); g.fill(); }
        else { g.fillStyle = c.ink4; g.globalAlpha = 0.55; roundRect(g, x, yy, cw, chh, 3); g.fill(); g.globalAlpha = 1; }
      }
    });
    // コード
    const cy = laneTop("chords");
    for (const ch of sk.chords) {
      const x = ch.at * sw + 1, cw = ch.len * sw - 2;
      g.fillStyle = grad(0.55); roundRect(g, x, cy + 6, cw, LANE.chords - 12, 5); g.fill();
      g.fillStyle = c.text; g.font = "600 12px system-ui, sans-serif";
      g.save(); g.beginPath(); g.rect(x, cy, cw, LANE.chords); g.clip(); g.fillText(ch.name, x + 7, cy + LANE.chords / 2 + 4); g.restore();
    }
    // ベース・メロディ
    for (const p of ["bass", "melody"]) {
      const y = laneTop(p), lh = LANE[p], { lo, hi, span } = pitchRange(p), ph = lh / span;
      for (const n of sk[p]) {
        const m = noteMidi(n.note);
        const i = Math.max(0, Math.min(span - 1, m - lo));
        g.fillStyle = grad(m < lo || m > hi ? 0.35 : 0.9);
        roundRect(g, n.at * sw + 1, y + lh - (i + 1) * ph, Math.max(3, n.len * sw - 2), Math.max(3, ph), 2); g.fill();
      }
    }
    // 今押している音: ベース・メロディはその音の行、コードはコードの行を光らせる
    const now = playing ? position() : -1;
    for (const h of held.values()) {
      if (h.chord) {
        const y = laneTop("chords");
        g.fillStyle = grad(0.28); roundRect(g, 0, y, w, LANE.chords, 6); g.fill();
        g.strokeStyle = c.signal; g.lineWidth = 1.5; roundRect(g, 0.75, y + 0.75, w - 1.5, LANE.chords - 1.5, 6); g.stroke();
        const x = (playing ? now : cursor) * sw;
        g.fillStyle = c.text; g.font = "600 13px system-ui, sans-serif"; g.fillText(h.chord, x + 8, y + LANE.chords / 2 + 5);
      } else if (h.midi != null && (h.part === "bass" || h.part === "melody")) {
        const y = laneTop(h.part), lh = LANE[h.part], { lo, span } = pitchRange(h.part), ph = lh / span;
        const i = h.midi - lo;
        if (i >= 0 && i < span) {
          g.fillStyle = grad(0.45); g.fillRect(0, y + lh - (i + 1) * ph, w, ph);
          g.fillStyle = c.text; g.font = "600 11px system-ui, sans-serif";
          g.fillText(showName(h.midi), 4, Math.max(y + 11, y + lh - (i + 1) * ph - 2));
        }
      }
    }
    // ドラムを叩いた行
    const tnow = performance.now();
    DRUMS.forEach((d, r) => {
      if ((flashes[d] || 0) > tnow) { g.fillStyle = grad(0.3); g.fillRect(0, dy + r * rh, w, rh); }
    });
    // 再生中に鳴っている音符・コードを縁取る
    if (playing) {
      g.strokeStyle = "rgba(255,255,255,.85)"; g.lineWidth = 1.5;
      for (const ch of sk.chords) if (now >= ch.at && now < ch.at + ch.len) { roundRect(g, ch.at * sw + 1, cy + 6, ch.len * sw - 2, LANE.chords - 12, 5); g.stroke(); }
      for (const p of ["bass", "melody"]) {
        const y = laneTop(p), lh = LANE[p], { lo, span } = pitchRange(p), ph = lh / span;
        for (const n of sk[p]) {
          if (now < n.at || now >= n.at + n.len) continue;
          const i = Math.max(0, Math.min(span - 1, noteMidi(n.note) - lo));
          roundRect(g, n.at * sw + 1, y + lh - (i + 1) * ph, Math.max(3, n.len * sw - 2), Math.max(3, ph), 2); g.stroke();
        }
      }
    } else {   // 止まっているときはカーソル（録音待機で音が入る位置）
      const x = Math.round(cursor * sw);
      g.fillStyle = rec ? "rgba(255,90,90,.9)" : c.signal;
      g.globalAlpha = rec ? 1 : 0.6;
      g.fillRect(x, LANE.head - 4, 2, h - LANE.head + 4);
      g.beginPath(); g.moveTo(x - 4, LANE.head - 8); g.lineTo(x + 6, LANE.head - 8); g.lineTo(x + 1, LANE.head - 2); g.closePath(); g.fill();
      g.globalAlpha = 1;
    }
    // 再生位置
    if (playing) {
      const x = position() * sw;
      g.fillStyle = rec ? "rgba(255,90,90,.9)" : c.signal;
      g.fillRect(x, LANE.head - 4, 2, h - LANE.head + 4);
    }
  }
  // 参考の音: スケッチの長さ分の波形（offset 秒から）。無いときは使い方を出す
  function drawRef(g, c, w, sw, grad) {
    const y = laneTop("ref"), lh = LANE.ref;
    g.fillStyle = c.ink2; roundRect(g, 0, y, w, lh, 6); g.fill();
    g.font = "11px system-ui, sans-serif";
    if (!sk.ref) { g.fillStyle = c.faint; g.fillText(L.refEmpty, 10, y + lh / 2 + 4); return; }
    if (!refInfo) { g.fillStyle = c.faint; g.fillText(sk.ref.file, 10, y + lh / 2 + 4); return; }
    const loop = steps() * stepSec(), mid = y + lh / 2, amp = lh / 2 - 6;
    g.fillStyle = grad(sk.ref.mute ? 0.25 : 0.75);
    for (let x = 0; x < w; x += 2) {
      const t0 = sk.ref.offset + (x / w) * loop, t1 = sk.ref.offset + ((x + 2) / w) * loop;
      let pk = 0;
      for (let i = Math.floor(t0 / refInfo.binSec); i < Math.ceil(t1 / refInfo.binSec) && i < refInfo.peaks.length; i++) pk = Math.max(pk, refInfo.peaks[i]);
      const hh = Math.max(1, pk * amp);
      g.fillRect(x, mid - hh, 1.6, hh * 2);
    }
    if (refInfo.duration - sk.ref.offset < loop) {     // 録音がスケッチより短いとき、終わりに線
      const xe = ((refInfo.duration - sk.ref.offset) / loop) * w;
      g.fillStyle = c.faint; g.fillRect(xe, y + 4, 1, lh - 8);
    }
    const label = (text, ty, color) => {      // 波形の上でも読めるよう、文字の後ろを暗くする
      const tw = g.measureText(text).width;
      g.fillStyle = "rgba(0,0,0,.55)"; roundRect(g, 4, ty - 11, tw + 8, 15, 4); g.fill();
      g.fillStyle = color; g.fillText(text, 8, ty);
    };
    label(`${sk.ref.file} · ${sk.ref.offset.toFixed(2)} s`, y + 14, c.text);
    if (!playing) label(L.refHelp, y + lh - 5, c.muted);
  }
  function roundRect(g, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
  }

  // マウス: ドラムのマスを点ける／消す（Shift でアクセント）、音符を足す／消す、コードを消す
  function onCanvas(e) {
    const { sw } = geom();
    const r = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const s = Math.floor(x / sw);
    if (s < 0 || s >= steps()) return;
    const rt = laneTop("ref");
    if (y >= rt && y < rt + LANE.ref) return refDrag(e, x);   // 参考の音は、ドラッグで頭を合わせる
    cursor = s;
    if (y < LANE.head) { draw(); return; }     // 小節番号の帯を押すとカーソルだけ動く
    for (const p of PARTS) {
      const top = laneTop(p), lh = LANE[p];
      if (y < top || y >= top + lh) continue;
      if (p !== part) selectPart(p);
      if (p === "drums") {
        const d = DRUMS[Math.min(3, Math.floor((y - top) / (lh / 4)))];
        changed(() => { const a = sk.drums[d].split(""); a[s] = a[s] === "." ? (e.shiftKey ? "X" : "x") : "."; sk.drums[d] = a.join(""); });
        audio(); if (sk.drums[d][s] !== ".") sound(drumKey(d), ac.currentTime, null, drumGain(sk.drums[d][s]));
      } else if (p === "chords") {
        // Hub のメニューは、前に開いたメニューの「外を押したら閉じる」がこの pointerdown の後で動くことがある。
        // 同じ操作の中で開くとすぐ閉じられてしまうので、一拍おいてから開く
        const cx = e.clientX, cy = e.clientY;
        setTimeout(() => chordMenu(s, cx, cy), 0);
      } else {
        const midi = midiAt(p, y);
        const hit = noteAt(p, s, midi);
        if (hit >= 0) changed(() => sk[p].splice(hit, 1));
        else {
          changed(() => { sk[p].push({ at: s, note: midiName(midi), len: Math.min(2, steps() - s) }); sk[p].sort((a, b) => a.at - b.at); });
          audio(); sound(voiceKey(p, midi), ac.currentTime, 2 * stepSec(), vol(p));
        }
      }
      return;
    }
  }

  function midiAt(p, y) {
    const top = laneTop(p), lh = LANE[p], { lo, span } = pitchRange(p);
    return lo + Math.max(0, Math.min(span - 1, Math.floor((top + lh - y) / (lh / span))));
  }
  // その位置の音符（上下 1 行のずれまでは当たりにする。細い音符でも消しやすく）
  function noteAt(p, s, midi) {
    let best = -1, dist = 2;
    sk[p].forEach((n, i) => {
      const d = Math.abs(noteMidi(n.note) - midi);
      if (s >= n.at && s < n.at + n.len && d < dist) { best = i; dist = d; }
    });
    return best;
  }
  // 右クリックで消す（ドラムのマス・音符・コード）
  function eraseAt(e) {
    e.preventDefault();
    const { sw } = geom();
    const r = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top, s = Math.floor(x / sw);
    if (s < 0 || s >= steps()) return;
    for (const p of PARTS) {
      const top = laneTop(p), lh = LANE[p];
      if (y < top || y >= top + lh) continue;
      if (p === "drums") {
        const d = DRUMS[Math.min(3, Math.floor((y - top) / (lh / 4)))];
        if (sk.drums[d][s] !== ".") changed(() => { const a = sk.drums[d].split(""); a[s] = "."; sk.drums[d] = a.join(""); });
      } else if (p === "chords") {
        const hit = sk.chords.find((c) => s >= c.at && s < c.at + c.len);
        if (hit) changed(() => { sk.chords = sk.chords.filter((c) => c !== hit); });
      } else {
        const hit = noteAt(p, s, midiAt(p, y));
        if (hit >= 0) changed(() => sk[p].splice(hit, 1));
      }
      return;
    }
  }
  // コードは半小節（8 マス）単位。小節の前半に置くと、後半にコードが無ければ小節の終わりまで伸ばす
  function chordSlot(s) {
    const at = Math.floor(s / 8) * 8;
    const half2 = at % 16 === 8 || sk.chords.some((c) => c.at === at + 8);
    return { at, ln: Math.min(half2 ? 8 : 16, steps() - at) };
  }
  function refDrag(e, x0) {
    if (!sk.ref || !refInfo) return;
    const cv = e.currentTarget, loop = steps() * stepSec(), w = geom().w;
    const start = sk.ref.offset, before = JSON.stringify(sk);
    let moved = false;
    cv.setPointerCapture(e.pointerId);
    const move = (ev) => {
      const dx = ev.clientX - cv.getBoundingClientRect().left - x0;
      if (Math.abs(dx) > 2) moved = true;
      sk.ref.offset = Math.round(Math.max(0, Math.min(refInfo.duration, start - (dx / w) * loop)) * 1000) / 1000;
      draw();
    };
    const up = () => {
      cv.removeEventListener("pointermove", move); cv.removeEventListener("pointerup", up);
      if (!moved) return;
      undo.push(before);
      clearTimeout(saveTimer); saveTimer = setTimeout(save, 350);
      if (playing) syncRef();
    };
    cv.addEventListener("pointermove", move);
    cv.addEventListener("pointerup", up);
  }
  // コードの行を押したとき: その調のコードから選ぶ（置いてあるコードなら差し替え・消す）
  function chordMenu(s, x, y) {
    const hit = sk.chords.find((c) => s >= c.at && s < c.at + c.len);
    const { at, ln } = chordSlot(s);
    cursor = at;
    const pick = (name) => () => {
      placeChord(at, ln, name);
      audio();
      for (const m of chordMidis(name, 3 + octOff.chords)) sound(voiceKey("chords", m), ac.currentTime, Math.min(1.2, ln * stepSec()), vol("chords") * 0.85);
    };
    const triads = [], sevenths = [];
    for (let d = 0; d < 7; d++) {
      const opt = { idx: d };
      triads.push(keyChord({ ...sk, ...opt }));
      sevenths.push(keyChord({ ...sk, ...opt, seventh: true }));
    }
    const items = [{ label: hit ? hit.name : L.placeChord, heading: true }, { label: L.triads, heading: true },
      ...triads.map((n) => ({ label: n, onClick: pick(n) })), "-", { label: L.sevenths, heading: true },
      ...sevenths.map((n) => ({ label: n, onClick: pick(n) }))];
    if (hit) items.push("-", { label: L.del, danger: true, onClick: () => changed(() => { sk.chords = sk.chords.filter((c) => c !== hit); }) });
    ctx.contextMenu(items, x, y);
    draw();
  }

  // ---------- キーの割り当て（見出しの鍵盤ボタン） ----------
  const overlay = document.createElement("div");
  overlay.className = "sk-keys";
  overlay.hidden = true;
  root.append(overlay);
  ctx.addTool(IC.keys, L.keymap, () => { overlay.hidden ? showKeys() : hideKeys(); });
  function hideKeys() { overlay.hidden = true; capture = null; if (sk) { buildLabels(); updateParts(); buildPad(); } }
  async function saveKeys(next, note) {
    km = next;
    await ctx.call("keymap_set", { keymap: km }).catch((e) => ctx.toast(e.message, "error"));
    if (note) ctx.toast(note);
    showKeys();
  }
  function showKeys() {
    overlay.hidden = false;
    releaseAll();
    overlay.innerHTML = `<div class="sk-keys-in">
      <div class="sk-keys-head"><h2></h2><span class="sk-grow"></span><span class="sk-plabel"></span><span class="sk-preset"></span>
        <button type="button" class="btn sk-k-reset"></button><button type="button" class="btn sk-k-exp"></button>
        <button type="button" class="btn sk-k-imp"></button><button type="button" class="btn primary sk-k-close"></button></div>
      <div class="sk-keys-grid"></div></div>`;
    const $ = (q) => overlay.querySelector(q);
    $("h2").textContent = L.keymap;
    $(".sk-plabel").textContent = L.preset;
    $(".sk-k-reset").textContent = L.reset;
    $(".sk-k-exp").textContent = L.exportKeys;
    $(".sk-k-imp").textContent = L.importKeys;
    $(".sk-k-close").textContent = L.close;
    const current = Object.keys(PRESETS).find((p) => Object.keys(PRESETS[p]).every((k) => PRESETS[p][k] === km[k])) || "custom";
    $(".sk-preset").append(selectBox({
      options: [...Object.keys(PRESETS).map((p) => ({ value: p, label: L.presets[p] })), ...(current === "custom" ? [{ value: "custom", label: L.presets.custom }] : [])],
      value: current, onChange: (v) => { if (PRESETS[v]) saveKeys({ ...PRESETS[v] }); },
    }));
    $(".sk-k-reset").addEventListener("click", () => saveKeys({ ...PRESETS.default }));
    $(".sk-k-exp").addEventListener("click", async () => { try { ctx.toast(L.exported((await ctx.call("keymap_export")).file)); } catch (e) { ctx.toast(e.message, "error"); } });
    $(".sk-k-imp").addEventListener("click", async () => { try { saveKeys(normalizeKeymap(await ctx.call("keymap_import"))); } catch (e) { ctx.toast(e.message, "error"); } });
    $(".sk-k-close").addEventListener("click", hideKeys);
    const grid = $(".sk-keys-grid");
    for (const { group, items } of ACTIONS) {
      const sec = document.createElement("section");
      sec.innerHTML = `<h3></h3>`;
      sec.querySelector("h3").textContent = L.groups[group];
      for (const a of items) {
        const row = document.createElement("div");
        row.className = "sk-krow";
        row.innerHTML = `<span></span><button type="button" class="sk-kbtn"></button>`;
        row.querySelector("span").textContent = L.act[a];
        const b = row.querySelector("button");
        b.textContent = keyLabel(km[a]);
        b.addEventListener("click", () => {
          overlay.querySelectorAll(".sk-kbtn.wait").forEach((x) => { x.classList.remove("wait"); });
          b.classList.add("wait"); b.textContent = L.pressKey;
          capture = (ev) => {
            capture = null;
            if (ev.code === "Escape") return showKeys();
            const r = assign(km, a, ev.code);
            saveKeys(r.keymap, r.swapped ? L.swapped(L.act[r.swapped]) : null);
          };
        });
        sec.append(row);
      }
      grid.append(sec);
    }
  }

  await refresh();
}
