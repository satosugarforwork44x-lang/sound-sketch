// sketch/ui/sampler.js — 「音を作る」画面。短い音を録って（雑音を測る → 録る → 整える → 使う）、ドラムや鍵盤の音色にする
// ・録音と加工は api.py（mic.py・sampler.py）。ここは操作と表示だけ
// ・パネル（panel.js）とは host を通してだけつながる（音を鳴らす・割り当てる・閉じたあと描き直す）
import { selectBox } from "/ui/js/hub.js";

const EN = (document.documentElement.lang || navigator.language || "ja").startsWith("en");
export const SL = EN ? {
  title: "Make a sound", close: "Close",
  lead: "Record a short sound — tap a glass, clap, knock, say “pa” — and use it as a drum or as the instrument you play on the keys.",
  s1: "1  Measure the room", s1n: "Stay quiet for 2 seconds. It is remembered, so once is enough.",
  noise: "Measure noise (2 s)", measuring: "Measuring… stay quiet", noiseNone: "Not measured — noise is not removed",
  noiseOk: (db) => `Measured (${db} dB)`, noiseZero: "Measured — this mic is silent when quiet, nothing to remove", forget: "Forget",
  s2: "2  Record", s2n: "Press Record, make the sound, then Stop (8 s max). The mic and the PC's sound (a call, a video, …) are recorded separately — pick one in step 3. You can also drop a WAV here.",
  s2warn: "Music from your speakers also reaches the mic — use headphones. Using someone's voice or someone else's work? Ask them first, and mind copyright before sharing.",
  srcMic: "Mic", srcPc: "PC sound", srcBoth: "Both", src: "Use", srcNone: "(nothing)",
  rec: "Record", stop: "Stop", noMic: "Recording needs soundcard: run  py -m pip install soundcard  and restart Hub. You can still drop a WAV here.",
  from: (f) => `From ${f}`,
  s3: "3  Shape", trim: "Cut silence", norm: "Even volume", denoise: "Remove noise", length: "Length", play: "Listen",
  pitch: "Pitch", auto: (n, hz, how) => `auto: ${n} (${Math.round(hz)} Hz${how === "peak" ? ", strongest tone" : ""})`, noPitch: "auto: unknown (C4)",
  pitchHelp: "The note this sound is. Keys then play in tune. Change it if it sounds off",
  s4: "4  Use", name: "Name", to: "Use as", save: "Save and use",
  slots: { melody: "Melody", bass: "Bass", chords: "Chords", kick: "Kick", snare: "Snare", hat: "Hat", clap: "Clap" },
  current: "Sounds in this sketch", builtIn: "Built-in", empty: "Record or drop a WAV first",
  used: (slot, f) => `${slot} now uses “${f}”`,
} : {
  title: "音を作る", close: "閉じる",
  lead: "コップを叩く・手を叩く・机をノックする・「パッ」と言う などの短い音を録って、ドラムや鍵盤で弾く音にします。",
  s1: "1  部屋の雑音を測る", s1n: "2 秒だけ静かにしてください。覚えておくので、1 回で十分です。",
  noise: "雑音を測る（2 秒）", measuring: "測っています… 静かに", noiseNone: "まだ測っていません（雑音は消しません）",
  noiseOk: (db) => `測りました（${db} dB）`, noiseZero: "測りました（このマイクは静かなとき無音なので、消す雑音はありません）", forget: "忘れる",
  s2: "2  録る", s2n: "録音を押して音を出し、止めるを押します（最長 8 秒）。マイクと PC の音（通話・動画など）を別々に録るので、どちらを使うかは 3 で選べます。WAV をここに落としても使えます。",
  s2warn: "スピーカーで鳴らした音楽はマイクにも入るので、ヘッドホンを使ってください。人の声や他の人の作品を使うときは、相手の了解と著作権に気を付けてください。",
  srcMic: "マイク", srcPc: "PC の音", srcBoth: "両方", src: "使う音", srcNone: "（無音）",
  rec: "録音", stop: "止める", noMic: "録音には soundcard が必要です（py -m pip install soundcard を実行して Hub を再起動）。WAV を落として使うことはできます。",
  from: (f) => `${f} から`,
  s3: "3  整える", trim: "前後の無音を切る", norm: "音量をそろえる", denoise: "雑音を引く", length: "長さ", play: "試し聞き",
  pitch: "元の高さ", auto: (n, hz, how) => `自動: ${n}（${Math.round(hz)} Hz${how === "peak" ? "・いちばん強い音" : ""}）`, noPitch: "自動: 分からない（C4 とします）",
  pitchHelp: "この音が何の音か。合っていると、鍵盤で弾いたとき正しい高さで鳴ります。ずれて聞こえたら直してください",
  s4: "4  使う", name: "名前", to: "使う所", save: "保存して使う",
  slots: { melody: "メロディ", bass: "ベース", chords: "コード", kick: "キック", snare: "スネア", hat: "ハット", clap: "クラップ" },
  current: "このスケッチの音色", builtIn: "内蔵の音", empty: "先に録音するか、WAV を落としてください",
  used: (slot, f) => `${slot}の音を「${f}」にしました`,
};

const SLOTS = ["melody", "bass", "chords", "kick", "snare", "hat", "clap"];
const SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const FLAT = { "C#": 1, Db: 1, "D#": 3, Eb: 3, "F#": 6, Gb: 6, "G#": 8, Ab: 8, "A#": 10, Bb: 10 };
const PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
export const toMidi = (n) => {
  const m = /^([A-G])([#b]?)(-?\d)$/.exec(n || "");
  return m ? 12 * (Number(m[3]) + 1) + (m[2] ? FLAT[m[1] + m[2]] ?? PC[m[1]] : PC[m[1]]) : 60;
};
const toName = (m) => `${SHARP[m % 12]}${Math.floor(m / 12) - 1}`;
const svg = (d) => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const MIC_ICON = svg('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>');

/** host: { ctx, el（重ねる箱）, play(key), sketch(), samples(), setSamples(list), assign(slot, file|null, root), closed(slot|null) } */
export function createSampler(host) {
  const { ctx, el } = host;
  const opts = { source: "mic", trim: true, normalize: true, denoise: true, length: 1.5 };
  let ms = null;          // api.mic_state()
  let res = null;         // api.sample_process() の結果
  let root = 60, rootAuto = true, slot = "melody", nameVal = "";
  let poll = null, procTimer = null, wasRec = false, pending = null;

  async function call(fn, args) {
    try { return await ctx.call(fn, args); } catch (e) { ctx.toast(e.message, "error", 7000); return null; }
  }

  function open(target) {
    if (target) slot = target;
    el.hidden = false;
    build();
    refreshState();
  }
  function close(used = null) {
    stopPoll();
    el.hidden = true;
    host.closed(used);
  }
  const isOpen = () => !el.hidden;

  async function refreshState() {
    const s = await call("mic_state");
    if (!s) return;
    onState(s);
    if (s.phase === "idle" && s.raw && !res) process();
  }
  // 録音の様子を受け取る（ボタンの戻り値でも、0.1 秒ごとの見回りでも）。録り終わったら整える
  function onState(s) {
    ms = s;
    updateTop();
    if (s.phase !== "idle") return startPoll();
    stopPoll();
    if (s.error && pending) ctx.toast(s.error, "error", 9000);
    const was = pending;
    pending = null;
    if (was === "rec" && s.raw) { pickSource(s); wasRec = true; process(); }
    else if (was === "noise") { updateShape(); processSoon(); }
  }
  function startPoll() {
    if (poll) return;
    poll = setInterval(async () => {
      const s = await ctx.call("mic_state").catch(() => null);
      if (s && !el.hidden) onState(s);
    }, 100);
  }
  function stopPoll() { clearInterval(poll); poll = null; }

  async function process() {
    clearTimeout(procTimer);
    if (!ms?.raw) return;
    const r = await call("sample_process", { opts });
    if (!r) return;
    res = r;
    if (rootAuto) root = r.root ? toMidi(r.root) : 60;
    updateShape();
    if (wasRec) { wasRec = false; host.play(r.key); }   // 録った直後は 1 回聞かせる
  }
  // 録れた方を選んでおく。マイクがほぼ無音で PC の音があれば PC の音（電話越しの声・動画の音を録ったとき）
  function pickSource(s) {
    const src = s.sources || {}, loud = (v) => v != null && v > -45;
    opts.source = src.mic == null || (!loud(src.mic) && loud(src.pc)) ? "pc" : "mic";
    if (src.pc == null) opts.source = "mic";
  }
  const processSoon = () => { clearTimeout(procTimer); procTimer = setTimeout(process, 150); };

  async function loadFile(path) {
    const s = await call("sample_load", { path });
    if (!s) return;
    ms = s; res = null; rootAuto = true; opts.source = "mic";
    nameVal = path.split(/[\\/]/).pop().replace(/\.wav$/i, "");
    build(); updateTop();
    wasRec = true; process();
  }

  // ---------- 描く ----------
  function build() {
    el.innerHTML = `<div class="sk-keys-in sk-smp">
      <div class="sk-keys-head"><h2></h2><span class="sk-grow"></span><button type="button" class="btn primary sk-s-close"></button></div>
      <p class="sk-smp-lead"></p>
      <div class="sk-smp-grid">
        <section class="sk-step" data-s="1"><h3></h3><p class="sk-step-n"></p>
          <div class="sk-step-row"><button type="button" class="btn sk-s-noise"></button><span class="sk-s-nstat"></span><button type="button" class="sk-link sk-s-forget"></button></div></section>
        <section class="sk-step" data-s="2"><h3></h3><p class="sk-step-n"></p>
          <div class="sk-step-row"><button type="button" class="btn sk-s-rec"></button>
            <span class="sk-meters"><span class="sk-mrow" data-s="mic"><small></small><span class="sk-meter"><i></i></span></span>
              <span class="sk-mrow" data-s="pc"><small></small><span class="sk-meter"><i></i></span></span></span>
            <span class="sk-s-sec"></span></div>
          <p class="sk-s-from"></p><p class="sk-step-n sk-s-warn"></p></section>
        <section class="sk-step sk-step-wide" data-s="3"><h3></h3>
          <div class="sk-step-row sk-s-srcrow"><span class="sk-f"></span><div class="seg seg-sm sk-s-src" role="radiogroup"></div></div>
          <canvas class="sk-s-wave"></canvas>
          <div class="sk-step-row sk-s-togs"></div>
          <div class="sk-step-row"><span class="sk-f"></span><input type="range" class="sk-s-len" min="0.1" max="4" step="0.05"><span class="sk-s-lenv"></span>
            <span class="sk-grow"></span><button type="button" class="btn sk-s-play"></button></div>
          <div class="sk-step-row sk-s-pitch"><span class="sk-f"></span>
            <button type="button" class="icon-btn sk-s-p" data-d="-12">«</button><button type="button" class="icon-btn sk-s-p" data-d="-1">‹</button>
            <b class="sk-s-root"></b>
            <button type="button" class="icon-btn sk-s-p" data-d="1">›</button><button type="button" class="icon-btn sk-s-p" data-d="12">»</button>
            <button type="button" class="sk-link sk-s-auto"></button></div></section>
        <section class="sk-step sk-step-wide" data-s="4"><h3></h3>
          <div class="sk-step-row"><label class="sk-f"><span></span><input class="input sk-s-name" maxlength="60"></label>
            <span class="sk-f sk-s-tol"></span><span class="sk-s-to"></span><span class="sk-grow"></span>
            <button type="button" class="btn primary sk-s-save"></button></div></section>
      </div>
      <section class="sk-smp-cur"><h3></h3><div class="sk-smp-slots"></div></section>
    </div>`;
    const $ = (q) => el.querySelector(q);
    $("h2").textContent = SL.title;
    $(".sk-s-close").textContent = SL.close;
    $(".sk-s-close").addEventListener("click", () => close());
    $(".sk-smp-lead").textContent = SL.lead;
    const st = (n, t, note) => { const s = el.querySelector(`.sk-step[data-s="${n}"]`); s.querySelector("h3").textContent = t; if (note) s.querySelector(".sk-step-n").textContent = note; };
    st(1, SL.s1, SL.s1n); st(2, SL.s2, SL.s2n); st(3, SL.s3); st(4, SL.s4);
    $(".sk-s-noise").textContent = SL.noise;
    $(".sk-s-noise").addEventListener("click", async () => { const s = await call("noise_start"); if (s) { pending = "noise"; onState(s); } });
    $(".sk-s-warn").textContent = SL.s2warn;
    el.querySelectorAll(".sk-mrow").forEach((r) => { r.querySelector("small").textContent = r.dataset.s === "mic" ? SL.srcMic : SL.srcPc; });
    $(".sk-s-srcrow .sk-f").textContent = SL.src;
    for (const [v, label] of [["mic", SL.srcMic], ["pc", SL.srcPc], ["both", SL.srcBoth]]) {
      const b = document.createElement("button");
      b.type = "button"; b.setAttribute("role", "radio"); b.dataset.v = v;
      b.innerHTML = "<span></span>"; b.firstChild.textContent = label;
      b.addEventListener("click", () => { if (opts.source === v) return; opts.source = v; rootAuto = true; updateShape(); processSoon(); });
      $(".sk-s-src").append(b);
    }
    $(".sk-s-forget").textContent = SL.forget;
    $(".sk-s-forget").addEventListener("click", async () => { const s = await call("noise_clear"); if (s) { ms = s; updateTop(); processSoon(); } });
    $(".sk-s-rec").addEventListener("click", async () => {
      if (ms?.phase === "rec") { const s = await call("rec_stop"); if (s) onState(s); return; }
      host.stopPlayback();                           // サウンドスケッチ自身の音を PC の音に入れない
      const s = await call("rec_start");
      if (s) { pending = "rec"; res = null; rootAuto = true; updateShape(); onState(s); }
    });
    const togs = $(".sk-s-togs");
    for (const [k, label] of [["trim", SL.trim], ["normalize", SL.norm], ["denoise", SL.denoise]]) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "sk-tog"; b.dataset.k = k; b.textContent = label;
      b.addEventListener("click", () => { opts[k] = !opts[k]; updateShape(); processSoon(); });
      togs.append(b);
    }
    $(".sk-s-len").previousElementSibling.textContent = SL.length;
    $(".sk-s-len").value = opts.length;
    $(".sk-s-len").addEventListener("input", (e) => { opts.length = Number(e.target.value); $(".sk-s-lenv").textContent = `${opts.length.toFixed(2)} s`; processSoon(); });
    $(".sk-s-lenv").textContent = `${opts.length.toFixed(2)} s`;
    $(".sk-s-play").innerHTML = `${svg('<path d="M7 5v14l11-7z" fill="currentColor"/>')}<span></span>`;
    $(".sk-s-play span").textContent = SL.play;
    $(".sk-s-play").addEventListener("click", () => res && host.play(res.key));
    $(".sk-s-pitch .sk-f").textContent = SL.pitch;
    $(".sk-s-pitch").title = SL.pitchHelp;
    el.querySelectorAll(".sk-s-p").forEach((b) => b.addEventListener("click", () => {
      root = Math.max(12, Math.min(108, root + Number(b.dataset.d))); rootAuto = false; updateShape();
    }));
    $(".sk-s-auto").addEventListener("click", () => { rootAuto = true; if (res) root = res.root ? toMidi(res.root) : 60; updateShape(); });
    $(".sk-s-name").previousElementSibling.textContent = SL.name;
    $(".sk-s-name").value = nameVal;
    $(".sk-s-name").placeholder = EN ? "glass" : "glass";
    $(".sk-s-name").addEventListener("input", (e) => { nameVal = e.target.value; });
    $(".sk-s-tol").textContent = SL.to;
    $(".sk-s-to").append(selectBox({ options: SLOTS.map((s) => ({ value: s, label: SL.slots[s] })), value: slot, onChange: (v) => { slot = v; } }));
    $(".sk-s-save").textContent = SL.save;
    $(".sk-s-save").addEventListener("click", save);
    $(".sk-smp-cur h3").textContent = SL.current;
    buildSlots();
    updateTop(); updateShape();
  }

  function buildSlots() {
    const box = el.querySelector(".sk-smp-slots");
    if (!box) return;
    box.innerHTML = "";
    const sk = host.sketch(), list = host.samples();
    for (const s of SLOTS) {
      const row = document.createElement("div");
      row.className = "sk-krow";
      row.innerHTML = `<span></span><span class="sk-s-slot"></span>`;
      row.firstElementChild.textContent = SL.slots[s];
      const cur = sk?.voices?.[s]?.sample || "";
      const opts2 = [{ value: "", label: SL.builtIn }, ...list.map((x) => ({ value: x.file, label: x.file.replace(/\.wav$/i, "") }))];
      if (cur && !list.some((x) => x.file === cur)) opts2.push({ value: cur, label: `${cur} (?)` });
      row.lastElementChild.append(selectBox({ options: opts2, value: cur, onChange: (v) => {
        const x = list.find((y) => y.file === v);
        host.assign(s, v || null, x?.root || "C4");
      } }));
      box.append(row);
    }
  }

  function updateTop() {
    if (el.hidden || !ms) return;
    const $ = (q) => el.querySelector(q);
    const busy = ms.phase !== "idle";
    const n = ms.noise;
    $(".sk-s-nstat").textContent = ms.phase === "noise" ? SL.measuring : n ? (n.zero ? SL.noiseZero : SL.noiseOk(n.db)) : SL.noiseNone;
    $(".sk-s-nstat").classList.toggle("ok", !!n);
    $(".sk-s-forget").hidden = !n || busy;
    $(".sk-s-noise").disabled = busy || !ms.available;
    const rb = $(".sk-s-rec");
    const recOn = ms.phase === "rec";
    rb.innerHTML = `${recOn ? svg('<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>') : svg('<circle cx="12" cy="12" r="6" fill="currentColor"/>')}<span></span>`;
    rb.querySelector("span").textContent = recOn ? SL.stop : SL.rec;
    rb.classList.toggle("on", recOn);
    rb.disabled = !ms.available || ms.phase === "noise";
    const lv = (v) => (v == null ? 0 : Math.max(0, Math.min(1, (v + 60) / 60)));
    el.querySelectorAll(".sk-mrow").forEach((r) => {
      const v = ms.levels?.[r.dataset.s];
      r.querySelector("i").style.width = `${busy && ms.phase === "rec" ? lv(v) * 100 : r.dataset.s === "mic" && ms.phase === "noise" ? lv(v) * 100 : 0}%`;
      r.classList.toggle("off", busy && ms.levels && v == null);
    });
    $(".sk-s-sec").textContent = busy ? `${ms.seconds.toFixed(1)} / ${ms.limit} s` : ms.raw ? `${ms.raw.toFixed(1)} s` : "";
    $(".sk-s-from").textContent = !ms.available ? SL.noMic : ms.rawFrom && ms.rawFrom !== "rec" ? SL.from(ms.rawFrom) : (ms.notes || []).join(" / ");
    $(".sk-s-from").classList.toggle("warn", !ms.available || (ms.rawFrom === "rec" && !!ms.notes?.length));
    el.querySelector('.sk-step[data-s="1"]').classList.toggle("done", !!n);
    el.querySelector('.sk-step[data-s="2"]').classList.toggle("done", !!ms.raw && !busy);
  }

  function updateShape() {
    if (el.hidden) return;
    const $ = (q) => el.querySelector(q);
    const has = !!res;
    const src = ms?.rawFrom === "rec" ? ms.sources || {} : null;
    $(".sk-s-srcrow").hidden = !src;
    el.querySelectorAll(".sk-s-src button").forEach((b) => {
      const v = b.dataset.v;
      b.setAttribute("aria-checked", String(opts.source === v));
      b.disabled = !src || (v === "both" ? src.mic == null || src.pc == null : src[v] == null);
      const db = src && v !== "both" ? src[v] : null;
      b.title = db == null ? "" : db <= -89 ? SL.srcNone : `${db} dB`;
    });
    el.querySelectorAll(".sk-tog").forEach((b) => {
      b.setAttribute("aria-pressed", String(!!opts[b.dataset.k]));
      if (b.dataset.k === "denoise") b.disabled = !ms?.noise || ms.noise.zero || opts.source === "pc";   // 雑音を引くのはマイクだけ
    });
    $(".sk-s-play").disabled = !has;
    $(".sk-s-save").disabled = !has;
    el.querySelectorAll(".sk-s-p").forEach((b) => { b.disabled = !has; });
    $(".sk-s-root").textContent = has ? toName(root) : "—";
    const a = $(".sk-s-auto");
    a.hidden = !has;
    a.textContent = res?.pitch ? SL.auto(res.root, res.pitch.hz, res.pitch.how) : SL.noPitch;
    a.classList.toggle("on", rootAuto);
    el.querySelectorAll('.sk-step[data-s="3"], .sk-step[data-s="4"]').forEach((s) => s.classList.toggle("off", !has));
    drawWave();
  }

  function drawWave() {
    const cv = el.querySelector(".sk-s-wave");
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1, w = cv.clientWidth || 600, h = 72;
    cv.width = w * dpr; cv.height = h * dpr; cv.style.height = `${h}px`;
    const g = cv.getContext("2d");
    g.scale(dpr, dpr);
    const css = getComputedStyle(el);
    g.fillStyle = css.getPropertyValue("--ink-2") || "#1b1e25";
    g.fillRect(0, 0, w, h);
    if (!res?.peaks?.length) {
      g.fillStyle = css.getPropertyValue("--faint") || "#888";
      g.font = "12px system-ui"; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText(SL.empty, w / 2, h / 2);
      return;
    }
    const c1 = css.getPropertyValue("--c1-rgb").trim() || "120,160,255", c3 = css.getPropertyValue("--c3-rgb").trim() || "200,120,255";
    const grad = g.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, `rgb(${c1})`); grad.addColorStop(1, `rgb(${c3})`);
    g.fillStyle = grad;
    const p = res.peaks, bw = w / p.length;
    for (let i = 0; i < p.length; i++) {
      const v = Math.max(1, p[i] * (h / 2 - 4));
      g.fillRect(i * bw, h / 2 - v, Math.max(1, bw - 0.5), v * 2);
    }
    g.fillStyle = css.getPropertyValue("--faint") || "#888";
    g.font = "10.5px system-ui"; g.textAlign = "right"; g.textBaseline = "top";
    g.fillText(`${res.duration.toFixed(2)} s`, w - 6, 5);
  }

  async function save() {
    const r = await call("sample_save", { name: nameVal.trim(), opts, root: toName(root) });
    if (!r) return;
    host.setSamples(r.samples);
    host.assign(slot, r.file, r.root);
    ctx.toast(SL.used(SL.slots[slot], r.file.replace(/\.wav$/i, "")));
    nameVal = "";
    close(slot);
  }

  return { open, close, isOpen, loadFile, refreshSlots: buildSlots };
}
