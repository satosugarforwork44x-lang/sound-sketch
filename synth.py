"""synth.py — サウンドスケッチの音源（numpy だけで作る素朴な音）。

その場で鳴らす音（パネルが読み込む 1 音ずつの WAV）も、書き出す WAV も、ここの同じ関数から作る。
Suno などに渡して作り直してもらう前提なので、音質より「軽い・毎回同じ音」を優先している。
"""
from __future__ import annotations

import re
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:  # 音名・コードの読み取りは numpy なしでも使えるようにする（音を作る所だけ numpy が要る）
    np = None

SR = 44100
DRUMS = ("kick", "snare", "hat", "clap")
VOICES = ("bass", "pad", "lead")          # bass → ベース、pad → コード、lead → メロディ
PREVIEW_SEC = 2.0                          # その場で鳴らす用の 1 音の長さ（パネルが音符の長さで切る）
RELEASE = 0.06                             # 音の終わりのフェード（秒）

_NOISE = np.random.default_rng(7).uniform(-1.0, 1.0, SR * 2) if np is not None else None  # 雑音も毎回同じ（再現性）


def _t(sec: float) -> np.ndarray:
    return np.arange(int(SR * sec)) / SR


def _noise(n: int) -> np.ndarray:
    return _NOISE[:n].copy()


def _onepole_lp(x: np.ndarray, cutoff: float) -> np.ndarray:
    """1 次のローパス（ベクトル化のため、係数を使った差分方程式を lfilter 相当で回す）。"""
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    b = 1 - a
    for i, v in enumerate(x):       # 短い音（≦2 秒）にしか使わないので素直なループで十分
        acc = b * v + a * acc
        y[i] = acc
    return y


# ---------- ドラム ----------
def drum(name: str) -> np.ndarray:
    match name:
        case "kick":
            t = _t(0.45)
            freq = 45 + 110 * np.exp(-t / 0.035)
            phase = 2 * np.pi * np.cumsum(freq) / SR
            x = np.sin(phase) * np.exp(-t / 0.16)
            x[: int(SR * 0.003)] += 0.4 * _noise(int(SR * 0.003))       # 頭の「カチッ」
            return x * 0.95
        case "snare":
            t = _t(0.25)
            n = _noise(len(t))
            body = n - _onepole_lp(n, 1500)                              # 低い所を削った雑音
            tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05)
            return (0.65 * body * np.exp(-t / 0.07) + 0.45 * tone) * 0.9
        case "hat":
            t = _t(0.09)
            n = _noise(len(t))
            hp = np.diff(np.concatenate([[0.0], n]))                     # 差分＝高い所だけ残す
            return 0.5 * hp * np.exp(-t / 0.022)
        case "clap":
            t = _t(0.3)
            n = _noise(len(t))
            band = n - _onepole_lp(n, 900)
            env = np.zeros_like(t)
            for d in (0.0, 0.011, 0.022):                                 # 手拍子は数回に分かれて聞こえる
                m = t >= d
                env[m] += np.exp(-(t[m] - d) / 0.008)
            env += 0.5 * np.exp(-t / 0.09) * (t >= 0.022)
            return 0.55 * band * env
    raise ValueError(f"unknown drum: {name}")


# ---------- 音程のある音 ----------
def midi_hz(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _additive(f: float, t: np.ndarray, kind: str) -> np.ndarray:
    """倍音を足して作る（折り返し雑音が出ないように、ナイキストまでで止める）。"""
    nmax = max(1, min(40, int((SR / 2) / f)))
    x = np.zeros_like(t)
    for k in range(1, nmax + 1):
        match kind:
            case "saw":
                x += np.sin(2 * np.pi * k * f * t) / k
            case "tri":
                if k % 2:
                    x += ((-1) ** ((k - 1) // 2)) * np.sin(2 * np.pi * k * f * t) / (k * k)
            case "square":
                if k % 2:
                    x += np.sin(2 * np.pi * k * f * t) / k
    return x


def voice(kind: str, midi: int, sec: float) -> np.ndarray:
    """1 音を sec 秒鳴らした波形（最後に RELEASE のフェードが付く）。"""
    sec = max(0.03, float(sec))
    t = _t(sec + RELEASE)
    f = midi_hz(midi)
    match kind:
        case "bass":
            x = 0.55 * _additive(f, t, "saw") * (0.35 + 0.65 * np.exp(-t / 0.12))  # はじめだけ明るい
            x += 0.5 * np.sin(2 * np.pi * f * t)
            env = np.minimum(1, t / 0.004) * (0.75 + 0.25 * np.exp(-t / 0.2))
            amp = 0.5
        case "pad":
            x = _additive(f, t, "tri") + 0.6 * _additive(f * 1.004, t, "tri") + 0.12 * _additive(f, t, "saw")
            env = np.minimum(1, t / 0.03) * (0.8 + 0.2 * np.exp(-t / 0.4))
            amp = 0.22
        case "lead":
            x = _additive(f, t, "square") * 0.45 + _additive(f, t, "tri") * 0.8
            vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.4)
            x *= vib
            env = np.minimum(1, t / 0.006) * (0.65 + 0.35 * np.exp(-t / 0.15))
            amp = 0.32
        case _:
            raise ValueError(f"unknown voice: {kind}")
    rel_start = int(SR * sec)
    fade = np.ones_like(t)
    fade[rel_start:] = np.linspace(1, 0, len(t) - rel_start)
    return amp * x * env * fade


# ---------- 音名・コード ----------
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d)$")
_CHORD_RE = re.compile(r"^([A-G])([#b]?)(maj7|m7b5|m7|mmaj7|m6|m|dim7|dim|aug|sus2|sus4|7sus4|add9|maj|6|7|9)?(?:/[A-G][#b]?)?$")
CHORD_IV = {
    None: (0, 4, 7), "maj": (0, 4, 7), "m": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8),
    "sus2": (0, 2, 7), "sus4": (0, 5, 7), "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9), "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10), "mmaj7": (0, 3, 7, 11), "m7b5": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9), "7sus4": (0, 5, 7, 10), "add9": (0, 4, 7, 14), "9": (0, 4, 7, 10, 14),
}


def note_midi(name: str) -> int:
    """'C4' → 60, 'Eb2' → 39。読めなければ ValueError。"""
    m = _NOTE_RE.match(str(name).strip())
    if not m:
        raise ValueError(f"音名が読めない: {name}（例: C4, F#3, Bb2）")
    pc = PC[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return 12 * (int(m.group(3)) + 1) + pc


def midi_name(midi: int) -> str:
    return f"{NAMES[midi % 12]}{midi // 12 - 1}"


def chord_midis(name: str, octave: int = 3) -> list[int]:
    """'Cm7' → [48, 51, 55, 58]（根音を octave に置く）。読めなければ ValueError。"""
    m = _CHORD_RE.match(str(name).strip())
    if not m:
        raise ValueError(f"コード名が読めない: {name}（例: C, Am, F#m7, Bbmaj7）")
    root = PC[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    base = 12 * (octave + 1) + root % 12
    return [base + iv for iv in CHORD_IV[m.group(3)]]


# ---------- 録った音（サンプル）を楽器として鳴らす ----------
SLOTS = DRUMS + ("bass", "chords", "melody")
SAMPLE_GAIN = {"bass": 0.6, "chords": 0.35, "melody": 0.5, "kick": 1.0, "snare": 1.0, "hat": 1.0, "clap": 1.0}
MAX_SHIFT = 36                              # 半音で ±3 オクターブまで


def fold_shift(shift: int) -> int:
    """遠すぎる高さはオクターブ単位で近づける（それ以上は音が崩れるだけなので）。"""
    while shift > MAX_SHIFT:
        shift -= 12
    while shift < -MAX_SHIFT:
        shift += 12
    return shift


def sample_voice(x: np.ndarray, slot: str, shift: int = 0, sec: float | None = None) -> np.ndarray:
    """録った音を shift 半音ずらして鳴らす（昔のサンプラーと同じく、速さを変えて高さを変える）。
    sec があれば、その長さで切って RELEASE でフェード（シンセの音と同じ扱い）。"""
    shift = fold_shift(int(shift))
    if shift and len(x) > 1:
        ratio = 2 ** (shift / 12)
        t = np.arange(int(len(x) / ratio)) * ratio
        x = np.interp(t, np.arange(len(x)), x)
    y = np.asarray(x, dtype=np.float64) * SAMPLE_GAIN[slot]
    if sec is not None:
        cut = int(SR * max(0.03, sec))
        if len(y) > cut:
            n = min(len(y), cut + int(SR * RELEASE))
            y = y[:n].copy()
            y[cut:] *= np.linspace(1, 0, n - cut)
    return y


# ---------- ミックス・書き出し ----------
# ---------- 参考の音（録音などの WAV） ----------
def _pcm_to_float(raw: bytes, width: int, channels: int) -> np.ndarray:
    """PCM のバイト列を -1〜1 の 1ch にする（2ch 以上は平均）。"""
    match width:
        case 1:
            x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
        case 2:
            x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
        case 3:
            b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
            v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            x = (np.where(v & 0x800000, v - 0x1000000, v)).astype(np.float32) / 8388608
        case 4:
            x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
        case _:
            raise ValueError(f"{width * 8} bit の WAV は読めない")
    return x.reshape(-1, channels).mean(axis=1) if channels > 1 else x


def wav_info(path: Path, bin_sec: float = 0.01, max_bins: int = 20000) -> dict:
    """参考の音の長さ・音の出だし・波形の形（区切りごとの最大値）。長い録音でも少しずつ読む。"""
    with wave.open(str(path), "rb") as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        dur = n / rate if rate else 0.0
        bin_sec = max(bin_sec, dur / max_bins) if dur else bin_sec
        per = max(1, int(rate * bin_sec))
        peaks: list[float] = []
        while True:
            raw = w.readframes(per * 200)
            if not raw:
                break
            x = np.abs(_pcm_to_float(raw, width, ch))
            k = len(x) // per
            if k:
                peaks += x[: k * per].reshape(k, per).max(axis=1).tolist()
            if len(x) % per:
                peaks.append(float(x[k * per:].max()))
    top = max(peaks) if peaks else 0.0
    onset = next((i * bin_sec for i, v in enumerate(peaks) if top and v > top * 0.1), 0.0)
    return {"duration": round(dur, 3), "rate": rate, "onset": round(onset, 3), "binSec": bin_sec,
            "peaks": [round(v / top, 3) if top else 0.0 for v in peaks]}


def read_wav_mono(path: Path) -> np.ndarray:
    """WAV を SR（44.1 kHz）の 1ch にする（書き出しで混ぜるため）。"""
    with wave.open(str(path), "rb") as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        x = _pcm_to_float(w.readframes(w.getnframes()), width, ch)
    if rate != SR and len(x):
        t = np.arange(int(len(x) * SR / rate)) * (rate / SR)
        x = np.interp(t, np.arange(len(x)), x).astype(np.float32)
    return x


def render(sketch: dict, repeat: int = 1, ref: np.ndarray | None = None, samples: dict | None = None) -> np.ndarray:
    """正規化済みのスケッチ（api.normalize の結果）を、1 本の波形にする。
    ref（参考の音を SR の 1ch にしたもの）があれば、スケッチの頭から offset 秒の所を、繰り返しごとに重ねる。
    samples = {枠: (録った音, 元の高さの MIDI)}。枠（kick … / bass / chords / melody）は、内蔵の音の代わりにそれで鳴らす。"""
    samples = samples or {}
    steps = 16 * sketch["bars"]
    step_sec = 60.0 / sketch["bpm"] / 4
    total = steps * step_sec * repeat
    out = np.zeros(int(SR * (total + 2.0)))
    mix = sketch["mix"]

    def add(x: np.ndarray, at_sec: float, gain: float) -> None:
        i = int(round(at_sec * SR))
        j = min(len(out), i + len(x))
        if i < len(out):
            out[i:j] += gain * x[: j - i]

    cache: dict = {}

    def vcache(part: str, kind: str, midi: int, steps_len: int) -> np.ndarray:  # 繰り返しでは同じ音を作り直さない
        k = (part, midi, steps_len)
        if k not in cache:
            if part in samples:
                x, root = samples[part]
                cache[k] = sample_voice(x, part, midi - root, steps_len * step_sec)
            else:
                cache[k] = voice(kind, midi, steps_len * step_sec)
        return cache[k]

    def dcache(d: str) -> np.ndarray:
        if d not in cache:
            cache[d] = sample_voice(samples[d][0], d) if d in samples else drum(d)
        return cache[d]
    rinfo = sketch.get("ref")
    for r in range(repeat):
        off = r * steps * step_sec
        if ref is not None and rinfo and not rinfo["mute"]:
            i0 = int(rinfo["offset"] * SR)
            add(ref[i0: i0 + int(steps * step_sec * SR)], off, rinfo["vol"])
        if not mix["drums"]["mute"]:
            for d in DRUMS:
                pat = sketch["drums"][d]
                for s, ch in enumerate(pat):
                    if ch in "xX":
                        add(dcache(d), off + s * step_sec, mix["drums"]["vol"] * (1.0 if ch == "X" else 0.72))
        for part, kind in (("bass", "bass"), ("melody", "lead")):
            if mix[part]["mute"]:
                continue
            for n in sketch[part]:
                add(vcache(part, kind, note_midi(n["note"]), n["len"]), off + n["at"] * step_sec, mix[part]["vol"])
        if not mix["chords"]["mute"]:
            for c in sketch["chords"]:
                for midi in chord_midis(c["name"]):
                    add(vcache("chords", "pad", midi, c["len"]), off + c["at"] * step_sec, mix["chords"]["vol"])
    out = out[: int(SR * (total + 1.0))]                 # 余韻は 1 秒まで
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    if peak > 0.89:                                        # 割れないように -1 dBFS に収める
        out *= 0.89 / peak
    return out


def write_wav(path: Path, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
