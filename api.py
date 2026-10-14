"""sketch/api.py — サウンドスケッチ。リズム・ベース・コード・メロディを数小節だけ作り、WAV にして AI に渡す。

・スケッチは「保存先フォルダ」の <名前>.sketch.json。Hub のフォルダ窓として Claude に「読み書き」で共有すれば、
  Claude は今ある folders_read_text / folders_write_text でスケッチを読み書きできる（Hub 本体の変更は不要）
・保存先フォルダには書き方の説明 SKETCH_FORMAT.md を置く（Claude が最初に読む）
・音は synth.py（numpy）。パネルで鳴らす 1 音ずつの WAV も、書き出しも同じ関数から作る
・「音を作る」: マイクで短い音を録り（mic.py・soundcard）、整えて（sampler.py）、保存先フォルダの samples/ に WAV で置く。
  スケッチの voices でドラムの 1 つやベース・コード・メロディの音色にすると、鍵盤の高さに合わせて鳴る
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shutil
import os
import re
import tempfile
import threading
import time
from pathlib import Path

_ctx = None
_synth = None
_synth_error = ""

EXT = ".sketch.json"
FORMAT = "hub-sketch/1"
KEYS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
SCALES = ("major", "minor")
BARS = (1, 2, 4, 8)
PARTS = ("drums", "bass", "chords", "melody")
DRUM_NAMES = ("kick", "snare", "hat", "clap")
NAME_RE = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,80}$")
BLOB_RE = re.compile(r"^(?:d-(kick|snare|hat|clap)|v-(bass|pad|lead)-(\d{1,3}))\.wav$")
REF_RE = re.compile(r"^a-([A-Za-z0-9_-]{1,400})\.wav$")          # 参考の音: a-<名前を base64url にしたもの>.wav
SLOTS = DRUM_NAMES + ("bass", "chords", "melody")                # 録った音を割り当てられる枠
# 録った音: s-<枠>-<ずらす半音>-<更新時刻>-<名前を base64url にしたもの>.wav / 試し聞き: p-<番号>.wav
SAMPLE_RE = re.compile(r"^s-(kick|snare|hat|clap|bass|chords|melody)-(-?\d{1,2})-(\d{1,12})-([A-Za-z0-9_-]{1,400})\.wav$")
PREVIEW_RE = re.compile(r"^p-\d{1,9}\.wav$")
SAMPLE_DIR = "samples"
NOISE_SEC = 2.0
REC_MAX_SEC = 8.0


class SketchError(Exception):
    pass


def setup(ctx):
    global _ctx, _synth, _synth_error
    _ctx = ctx
    try:  # numpy が無くても、パネルは開いて理由を出せるようにする
        spec = importlib.util.spec_from_file_location("hubmod_sketch_synth", Path(__file__).with_name("synth.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _synth = mod
        _synth_error = "" if mod.np is not None else "numpy が入っていません"
    except Exception as e:
        _synth, _synth_error = None, str(e)


def _theory():
    """音名・コードの読み取り（numpy なしで動く）。"""
    if _synth is None:
        raise SketchError(f"synth.py を読み込めません: {_synth_error}")
    return _synth


def _need_synth():
    s = _theory()
    if s.np is None:
        raise SketchError("音を作るには numpy が必要です。コマンドプロンプトで py -m pip install numpy を実行して、Hub を再起動してください")
    return s


# ---------- 保存先 ----------
def _folder() -> Path | None:
    p = _ctx.store.get("sketch", "folder", None) or (_ctx.config or {}).get("folder")
    return Path(p) if p and Path(p).is_dir() else None


def _need_folder() -> Path:
    f = _folder()
    if not f:
        raise SketchError("保存先のフォルダが決まっていません。フォルダをこのパネルに落としてください")
    return f


def _path(name: str) -> Path:
    if not isinstance(name, str) or not NAME_RE.match(name) or name.strip() != name or name in (".", ".."):
        raise SketchError(f"スケッチの名前に使えない文字があります: {name}")
    return _need_folder() / f"{name}{EXT}"


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".sketch-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def _unique(path: Path) -> Path:
    """上書きしない: 'name.wav' があれば 'name (2).wav'。"""
    if not path.exists():
        return path
    stem, suf = path.name[: -len(path.suffix)], path.suffix
    for i in range(2, 1000):
        p = path.with_name(f"{stem} ({i}){suf}")
        if not p.exists():
            return p
    raise SketchError("同じ名前のファイルが多すぎます")


def set_folder(path: str) -> dict:
    """保存先を決める。.sketch.json を落とされたときは、その親フォルダを保存先にしてそのスケッチを開く。"""
    p = Path(str(path))
    if p.is_file() and p.name.endswith(EXT):
        _ctx.store.set("sketch", "current", p.name[: -len(EXT)])
        p = p.parent
    if not p.is_dir():
        raise SketchError(f"フォルダ（または .sketch.json）を落としてください: {p.name}")
    _ctx.store.set("sketch", "folder", str(p))
    guide = p / "SKETCH_FORMAT.md"
    if not guide.exists():
        _write_atomic(guide, (Path(__file__).with_name("SKETCH_FORMAT.md")).read_text(encoding="utf-8"))
    return state()


# ---------- スケッチの形をそろえる ----------
def default_sketch() -> dict:
    return {
        "format": FORMAT, "bpm": 96, "key": "C", "scale": "minor", "bars": 2,
        "drums": {"kick": "x...x...x...x..." * 2, "snare": "....x.......x..." * 2, "hat": "x.x.x.x.x.x.x.x." * 2, "clap": "." * 32},
        "bass": [], "chords": [], "melody": [],
        "mix": {p: {"vol": 0.8, "mute": False} for p in PARTS},
    }


def _num(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def normalize(raw: dict) -> tuple[dict, list[str]]:
    """読み込んだ JSON を、鳴らせる形に直す。直せなかった所は捨てて warnings に理由を残す。"""
    s = _theory()
    warn: list[str] = []
    if not isinstance(raw, dict):
        raise SketchError("スケッチの中身が JSON のオブジェクトではありません")
    d = default_sketch()
    out = {"format": FORMAT}
    out["bpm"] = int(round(_num(raw.get("bpm"), 40, 240, d["bpm"])))
    out["key"] = raw.get("key") if raw.get("key") in KEYS else d["key"]
    if raw.get("key") not in (None, *KEYS):
        warn.append(f"key は {', '.join(KEYS)} のどれか（{raw.get('key')} → {out['key']}）")
    out["scale"] = raw.get("scale") if raw.get("scale") in SCALES else d["scale"]
    out["bars"] = raw.get("bars") if raw.get("bars") in BARS else d["bars"]
    steps = 16 * out["bars"]

    drums = raw.get("drums") if isinstance(raw.get("drums"), dict) else {}
    out["drums"] = {}
    for name in DRUM_NAMES:
        pat = re.sub(r"[\s|]", "", str(drums.get(name, "") or ""))
        pat = "".join(ch if ch in "xX" else "." for ch in pat)
        out["drums"][name] = (pat + "." * steps)[:steps]

    def notes(key: str) -> list[dict]:
        res = []
        for i, n in enumerate(raw.get(key) or []):
            try:
                at, ln = int(n["at"]), int(n.get("len", 1))
                midi = s.note_midi(n["note"])
                if not (0 <= at < steps) or ln < 1 or not 12 <= midi <= 108:
                    raise ValueError("範囲外")
                res.append({"at": at, "note": s.midi_name(midi), "len": min(ln, steps - at)})
            except Exception as e:
                warn.append(f"{key}[{i}] を読み飛ばした: {e}")
        return sorted(res, key=lambda x: (x["at"], s.note_midi(x["note"])))

    out["bass"], out["melody"] = notes("bass"), notes("melody")
    chords = []
    for i, c in enumerate(raw.get("chords") or []):
        try:
            at, ln = int(c["at"]), int(c.get("len", 16))
            s.chord_midis(c["name"])
            if not 0 <= at < steps or ln < 1:
                raise ValueError("範囲外")
            chords.append({"at": at, "name": str(c["name"]).strip(), "len": min(ln, steps - at)})
        except Exception as e:
            warn.append(f"chords[{i}] を読み飛ばした: {e}")
    out["chords"] = sorted(chords, key=lambda x: x["at"])

    mix = raw.get("mix") if isinstance(raw.get("mix"), dict) else {}
    # 参考の音（保存先フォルダの WAV。任意）
    ref = raw.get("ref")
    out["ref"] = None
    if isinstance(ref, dict) and isinstance(ref.get("file"), str):
        f = ref["file"].strip()
        if f.lower().endswith(".wav") and NAME_RE.match(f):
            out["ref"] = {"file": f, "offset": round(_num(ref.get("offset"), 0, 3600, 0.0), 3),
                          "vol": round(_num(ref.get("vol"), 0, 1, 0.8), 3), "mute": bool(ref.get("mute", False))}
        else:
            warn.append(f"ref.file は保存先フォルダの .wav の名前だけ（{f}）")
    # 録った音の割り当て（任意）: {"melody": {"sample": "glass.wav", "root": "A5"}, "clap": {"sample": "knock.wav"}}
    voices = raw.get("voices") if isinstance(raw.get("voices"), dict) else {}
    out["voices"] = {}
    for slot, v in voices.items():
        try:
            if slot not in SLOTS:
                raise ValueError(f"枠は {', '.join(SLOTS)} のどれか")
            f = str((v or {}).get("sample", "")).strip()
            if not (f.lower().endswith(".wav") and NAME_RE.match(f)):
                raise ValueError("sample は samples フォルダの .wav の名前だけ")
            e = {"sample": f}
            if slot not in DRUM_NAMES:
                e["root"] = s.midi_name(s.note_midi(v.get("root") or "C4"))
            out["voices"][slot] = e
        except Exception as e:
            warn.append(f"voices.{slot} を読み飛ばした: {e}")
    out["mix"] = {}
    for p in PARTS:
        m = mix.get(p) if isinstance(mix.get(p), dict) else {}
        out["mix"][p] = {"vol": round(_num(m.get("vol"), 0, 1, 0.8), 3), "mute": bool(m.get("mute", False))}
    return out, warn


# ---------- 画面から呼ぶ ----------
def state() -> dict:
    f = _folder()
    files = sorted(p.name[: -len(EXT)] for p in f.glob(f"*{EXT}")) if f else []
    cur = _ctx.store.get("sketch", "current", None)
    return {"folder": str(f) if f else None, "files": files, "current": cur if cur in files else None, "audio": _audio(),
            "samples": samples(), "numpy": _synth is not None and _synth.np is not None, "numpyError": _synth_error}


def _audio() -> list[str]:
    """保存先フォルダの WAV（参考の音の候補）。新しい順。"""
    f = _folder()
    if not f:
        return []
    return [p.name for p in sorted(f.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)]


def _wav(name: str) -> Path:
    if not isinstance(name, str) or not NAME_RE.match(name) or not name.lower().endswith(".wav"):
        raise SketchError(f"WAV の名前が正しくありません: {name}")
    p = _need_folder() / name
    if not p.is_file():
        raise SketchError(f"保存先フォルダに {name} がありません")
    return p


def ref_info(file: str) -> dict:
    """参考の音の長さ・出だし・波形（画面に描く用）と、鳴らすための /blob のキー。"""
    s = _need_synth()
    try:
        info = s.wav_info(_wav(file))
    except Exception as e:   # wave.Error・ValueError（32 bit float など）
        raise SketchError(f"{file} を読めません（16 / 24 / 32 bit の PCM の WAV だけ）: {e}")
    info["key"] = "a-" + base64.urlsafe_b64encode(file.encode("utf-8")).decode("ascii").rstrip("=") + ".wav"
    return info


def import_audio(path: str) -> dict:
    """パネルに落とした WAV を、保存先フォルダに写す（上書きしない）。"""
    src = Path(str(path))
    if not src.is_file() or src.suffix.lower() != ".wav":
        raise SketchError("WAV ファイルを落としてください")
    folder = _need_folder()
    if src.parent.resolve() == folder.resolve():
        return {"file": src.name}
    out = _unique(folder / src.name)
    shutil.copy2(src, out)
    return {"file": out.name}


def open_sketch(name: str) -> dict:
    p = _path(name)
    if not p.exists():
        raise SketchError(f"スケッチが見つかりません: {name}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SketchError(f"{p.name} の JSON が壊れています（{e.lineno} 行目）")
    sketch, warn = normalize(raw)
    _ctx.store.set("sketch", "current", name)
    return {"name": name, "sketch": sketch, "warnings": warn, "mtime": p.stat().st_mtime}


def new_sketch(name: str | None = None) -> dict:
    name = name or time.strftime("sketch-%Y%m%d-%H%M%S")
    p = _path(name)
    if p.exists():
        raise SketchError(f"同じ名前のスケッチがあります: {name}")
    _write_atomic(p, _dump(default_sketch()))
    return open_sketch(name)


def _dump(sketch: dict) -> str:
    """人と Claude が読みやすい形（ドラムは 1 行 1 パート、音符は 1 行 1 音）。"""
    lines = ["{", f'  "format": "{FORMAT}",',
             f'  "bpm": {sketch["bpm"]}, "key": "{sketch["key"]}", "scale": "{sketch["scale"]}", "bars": {sketch["bars"]},',
             '  "drums": {']
    bar = lambda pat: "|".join(pat[i:i + 16] for i in range(0, len(pat), 16))
    lines += [f'    "{d}": "{bar(sketch["drums"][d])}"' + ("," if d != "clap" else "") for d in DRUM_NAMES]
    lines.append("  },")
    for key in ("bass", "chords", "melody"):
        items = [json.dumps(x, ensure_ascii=False) for x in sketch[key]]
        lines.append(f'  "{key}": [' + ("" if not items else "\n    " + ",\n    ".join(items) + "\n  ") + "],")
    if sketch.get("ref"):
        lines.append('  "ref": ' + json.dumps(sketch["ref"], ensure_ascii=False) + ",")
    if sketch.get("voices"):
        lines.append('  "voices": ' + json.dumps(sketch["voices"], ensure_ascii=False) + ",")
    lines.append('  "mix": ' + json.dumps(sketch["mix"]))
    lines.append("}")
    return "\n".join(lines) + "\n"


def save_sketch(name: str, sketch: dict) -> dict:
    clean, warn = normalize(sketch)
    p = _path(name)
    _write_atomic(p, _dump(clean))
    return {"mtime": p.stat().st_mtime, "warnings": warn}


def poll(name: str) -> dict:
    """外（Claude やエディタ）で書き換えられたかを見るための更新時刻。"""
    p = _path(name)
    return {"mtime": p.stat().st_mtime if p.exists() else None, "audio": _audio(), "samples": samples()}


def export_wav(name: str, repeat: int = 1) -> dict:
    s = _need_synth()
    if repeat not in (1, 2, 4, 8):
        raise SketchError("繰り返しは 1・2・4・8 のどれか")
    data = open_sketch(name)
    sk = data["sketch"]
    ref = None
    if sk.get("ref") and not sk["ref"]["mute"]:
        try:
            ref = s.read_wav_mono(_wav(sk["ref"]["file"]))
        except Exception as e:
            raise SketchError(f"参考の音 {sk['ref']['file']} を読めません: {e}（参考の音をミュートすれば書き出せます）")
    samples, warn = _load_voices(sk)
    out = _unique(_need_folder() / f"{name}.wav")
    s.write_wav(out, s.render(sk, repeat, ref, samples))
    return {"path": str(out), "file": out.name, "warnings": warn}


def keymap_get() -> dict | None:
    return _ctx.store.get("sketch", "keymap", None)


def keymap_set(keymap: dict) -> bool:
    if not isinstance(keymap, dict) or len(keymap) > 64:
        raise SketchError("キーの割り当ての形が違います")
    clean = {str(k)[:40]: str(v)[:40] for k, v in keymap.items() if isinstance(v, str)}
    _ctx.store.set("sketch", "keymap", clean)
    return True


def keymap_export() -> dict:
    km = keymap_get() or {}
    out = _unique(_need_folder() / "sketch-keymap.json")
    _write_atomic(out, json.dumps(km, ensure_ascii=False, indent=2))
    return {"path": str(out), "file": out.name}


def keymap_import(file: str = "sketch-keymap.json") -> dict:
    p = _need_folder() / Path(str(file)).name
    if not p.exists():
        raise SketchError(f"{p.name} が保存先フォルダにありません")
    try:
        km = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise SketchError(f"{p.name} の JSON が壊れています")
    keymap_set(km)
    return keymap_get()


# ---------- 音を作る（短い音を録る → 整える → 楽器の音として使う） ----------
_mods: dict = {}
_lock = threading.Lock()
_cap = None                 # 録っている途中（mic.Capture）
_cap_kind = ""              # "noise"（部屋の雑音を測る）/ "rec"（音を録る）
_cap_error = ""
_noise = None               # 部屋の雑音（周波数ごとの大きさ）。data_dir/noise.npy にも残す
_raw = None                 # 整える前の音（SR の 1ch）
_raw_from = ""              # "mic" か、読み込んだ WAV の名前
_preview_n = 0
mic_backend = None          # 確かめ用に、soundcard の代わりを差し込める


def _mod(name: str):
    """となりの mic.py / sampler.py を読み込む（Hub のモジュールは import の場所が決まっていないので、ファイルから）。"""
    if name not in _mods:
        spec = importlib.util.spec_from_file_location(f"hubmod_sketch_{name}", Path(__file__).with_name(f"{name}.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _mods[name] = mod
    return _mods[name]


def _sampler():
    _need_synth()
    return _mod("sampler")


def _noise_file() -> Path:
    return Path(_ctx.data_dir) / "noise.npy"


def _load_noise():
    global _noise
    if _noise is None and _noise_file().exists():
        try:
            _noise = _synth.np.load(_noise_file())
        except Exception:
            _noise = None
    return _noise


def _finish() -> None:
    """録り終わった音を受け取る（雑音なら周波数ごとの大きさにして残す）。"""
    global _cap, _cap_kind, _cap_error, _noise, _raw, _raw_from
    cap = _cap
    if cap is None or cap.running:
        return
    _cap = None
    kind, _cap_kind = _cap_kind, ""
    _cap_error = cap.error
    if cap.error and not cap.frames:
        return
    smp = _sampler()
    x = smp.resample(cap.audio(), _mod("mic").RATE)
    if kind == "noise":
        try:
            prof = smp.noise_profile(x)
        except ValueError as e:
            _cap_error = str(e)
            return
        _noise = prof
        Path(_ctx.data_dir).mkdir(parents=True, exist_ok=True)
        _synth.np.save(_noise_file(), prof)
        _ctx.store.set("sketch", "noise", {"db": _mod("mic").db(x), "zero": bool(not _synth.np.any(x)), "at": time.time()})
    else:
        _raw, _raw_from = x, "mic"


def mic_state() -> dict:
    """録音の様子（画面が 0.1 秒ごとに見る）。"""
    if _synth is None or _synth.np is None:
        return {"available": False, "phase": "idle", "error": _synth_error or "numpy が入っていません", "noise": None, "raw": None}
    with _lock:
        _finish()
        cap = _cap
        meta = _ctx.store.get("sketch", "noise", None) if _load_noise() is not None else None
        return {
            "available": mic_backend is not None or importlib.util.find_spec("soundcard") is not None,
            "phase": _cap_kind if cap else "idle",
            "seconds": round(cap.seconds, 2) if cap else 0.0,
            "limit": cap.limit if cap else REC_MAX_SEC,
            "level": cap.level if cap else None,
            "error": _cap_error,
            "noise": meta,
            "raw": round(len(_raw) / _synth.SR, 2) if _raw is not None and _synth else None,
            "rawFrom": _raw_from,
        }


def _start(kind: str, seconds: float) -> dict:
    global _cap, _cap_kind, _cap_error
    _need_synth()
    mic = _mod("mic")
    with _lock:
        _finish()
        if _cap is not None:
            raise SketchError("いま録っています")
        cap = mic.Capture(seconds, backend=mic_backend)
        try:
            cap.start()
        except mic.MicError as e:
            raise SketchError(str(e))
        _cap, _cap_kind, _cap_error = cap, kind, ""
    return mic_state()


def noise_start() -> dict:
    """部屋の雑音を 2 秒測る（音を出さずに待つ）。一度測れば覚えておく。"""
    return _start("noise", NOISE_SEC)


def noise_clear() -> dict:
    global _noise
    _noise = None
    _noise_file().unlink(missing_ok=True)
    _ctx.store.set("sketch", "noise", None)
    return mic_state()


def rec_start() -> dict:
    """短い音を録る（最長 8 秒。止めるまで）。"""
    return _start("rec", REC_MAX_SEC)


def rec_stop() -> dict:
    cap = _cap
    if cap is not None:
        cap.stop()
    return mic_state()


def sample_load(path: str) -> dict:
    """マイクの代わりに、WAV ファイルを整える元にする（最初の 8 秒まで）。"""
    global _raw, _raw_from
    s = _need_synth()
    src = Path(str(path))
    if not src.is_file() or src.suffix.lower() != ".wav":
        raise SketchError("WAV ファイルを落としてください")
    try:
        x = s.read_wav_mono(src)
    except Exception as e:
        raise SketchError(f"{src.name} を読めません（16 / 24 / 32 bit の PCM の WAV だけ）: {e}")
    _raw, _raw_from = x[: int(REC_MAX_SEC * s.SR)].astype(float), src.name
    return mic_state()


def _opts(opts: dict | None) -> dict:
    o = opts if isinstance(opts, dict) else {}
    return {"denoise": bool(o.get("denoise", True)), "trim": bool(o.get("trim", True)),
            "normalize": bool(o.get("normalize", True)), "length": _num(o.get("length"), 0.1, 4.0, 1.5)}


def _processed(opts: dict | None):
    if _raw is None:
        raise SketchError("まだ音がありません。録音するか、WAV を落としてください")
    x, pitch = _sampler().process(_raw, _load_noise(), _opts(opts))
    if not len(x):
        raise SketchError("音が小さすぎて、何も残りませんでした。もう少し近くで録ってみてください")
    return x, pitch


def sample_process(opts: dict | None = None) -> dict:
    """整えた結果（試し聞きの WAV・波形・元の高さ）。設定を変えるたびに呼ぶ。"""
    global _preview_n
    s = _need_synth()
    x, pitch = _processed(opts)
    out = Path(_ctx.data_dir) / "preview.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    s.write_wav(out, x)
    _preview_n += 1
    root = s.midi_name(max(12, min(108, int(round(pitch["midi"]))))) if pitch else None
    return {"key": f"p-{_preview_n}.wav", "duration": round(len(x) / s.SR, 3), "peaks": _sampler().peaks(x),
            "pitch": pitch, "root": root}


def _sample_dir() -> Path:
    return _need_folder() / SAMPLE_DIR


def _sample_index() -> dict:
    try:
        d = json.loads((_sample_dir() / "samples.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def sample_save(name: str, opts: dict | None = None, root: str = "C4") -> dict:
    """整えた音を samples/<名前>.wav に保存する（上書きしない）。元の高さ（root）も覚えておく。"""
    s = _need_synth()
    name = str(name or "").strip() or time.strftime("sound-%m%d-%H%M%S")
    if not NAME_RE.match(name + ".wav") or name in (".", ".."):
        raise SketchError(f"名前に使えない文字があります: {name}")
    root = s.midi_name(s.note_midi(root or "C4"))
    x, _ = _processed(opts)
    d = _sample_dir()
    d.mkdir(exist_ok=True)
    out = _unique(d / f"{name}.wav")
    tmp = out.with_name(out.name + ".tmp")
    s.write_wav(tmp, x)
    os.replace(tmp, out)
    idx = _sample_index()
    idx[out.name] = {"root": root}
    _write_atomic(d / "samples.json", json.dumps(idx, ensure_ascii=False, indent=2) + "\n")
    return {"file": out.name, "root": root, "samples": samples()}


def samples() -> list[dict]:
    """samples フォルダの音（新しい順）。鳴らすためのキーの材料（ver・b64）も付ける。"""
    f = _folder()
    if not f or not (f / SAMPLE_DIR).is_dir():
        return []
    idx = _sample_index()
    out = []
    for p in sorted((f / SAMPLE_DIR).glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True):
        r = idx.get(p.name, {}).get("root", "C4")
        out.append({"file": p.name, "root": r, "ver": int(p.stat().st_mtime),
                    "b64": base64.urlsafe_b64encode(p.name.encode("utf-8")).decode("ascii").rstrip("=")})
    return out


def _sample_wav(name: str) -> Path:
    if not isinstance(name, str) or not NAME_RE.match(name) or not name.lower().endswith(".wav"):
        raise SketchError(f"音の名前が正しくありません: {name}")
    p = _sample_dir() / name
    if not p.is_file():
        raise SketchError(f"samples フォルダに {name} がありません")
    return p


def _load_voices(sk: dict) -> tuple[dict, list[str]]:
    """書き出し用: 割り当てた録った音を読み込む。見つからない枠は内蔵の音に戻して、理由を返す。"""
    s = _need_synth()
    out, warn = {}, []
    for slot, v in (sk.get("voices") or {}).items():
        try:
            x = s.read_wav_mono(_sample_wav(v["sample"]))
            out[slot] = (x, s.note_midi(v.get("root", "C4")))
        except Exception as e:
            warn.append(f"{slot}: {e}（内蔵の音で書き出しました）")
    return out, warn


def _b64name(b: str) -> str:
    try:
        return base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8")
    except Exception:
        raise SketchError("その音はありません")


def blob_path(key: str) -> Path:
    """パネルで鳴らす 1 音の WAV（/blob/sketch/<key>）。初めて頼まれたときに作って data_dir に置いておく。"""
    s = _need_synth()
    r = REF_RE.match(str(key))
    if r:   # 参考の音は、保存先フォルダの WAV をそのまま渡す
        try:
            name = base64.urlsafe_b64decode(r.group(1) + "=" * (-len(r.group(1)) % 4)).decode("utf-8")
        except Exception:
            raise SketchError("その音はありません")
        return _wav(name)
    if PREVIEW_RE.match(str(key)):        # 試し聞き（いちばん新しい整えた音）
        out = Path(_ctx.data_dir) / "preview.wav"
        if not out.exists():
            raise SketchError("その音はありません")
        return out
    sm = SAMPLE_RE.match(str(key))
    if sm:   # 録った音を、枠の音量にして shift 半音ずらしたもの（名前が長くなるので、ためる名前はハッシュ）
        slot, shift = sm.group(1), int(sm.group(2))
        src = _sample_wav(_b64name(sm.group(4)))
        cache = Path(_ctx.data_dir) / "samples-cache"
        cache.mkdir(parents=True, exist_ok=True)
        out = cache / (hashlib.sha1(f"{key}|{src.stat().st_mtime_ns}".encode()).hexdigest()[:24] + ".wav")
        if not out.exists():
            tmp = out.with_suffix(".tmp")
            s.write_wav(tmp, s.sample_voice(s.read_wav_mono(src), slot, shift))
            os.replace(tmp, out)
        return out
    m = BLOB_RE.match(str(key))
    if not m:
        raise SketchError("その音はありません")
    cache = Path(_ctx.data_dir) / "voices"
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / key
    if not out.exists():
        if m.group(1):
            x = s.drum(m.group(1))
        else:
            midi = int(m.group(3))
            if not 12 <= midi <= 108:
                raise SketchError("その音はありません")
            x = s.voice(m.group(2), midi, s.PREVIEW_SEC)
        tmp = out.with_suffix(".tmp")
        s.write_wav(tmp, x)
        os.replace(tmp, out)
    return out
