"""sketch/api.py — サウンドスケッチ。リズム・ベース・コード・メロディを数小節だけ作り、WAV にして AI に渡す。

・スケッチは「保存先フォルダ」の <名前>.sketch.json。Hub のフォルダ窓として Claude に「読み書き」で共有すれば、
  Claude は今ある folders_read_text / folders_write_text でスケッチを読み書きできる（Hub 本体の変更は不要）
・保存先フォルダには書き方の説明 SKETCH_FORMAT.md を置く（Claude が最初に読む）
・音は synth.py（numpy）。パネルで鳴らす 1 音ずつの WAV も、書き出しも同じ関数から作る
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import tempfile
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
    return {"folder": str(f) if f else None, "files": files, "current": cur if cur in files else None,
            "numpy": _synth is not None and _synth.np is not None, "numpyError": _synth_error}


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
    return {"mtime": p.stat().st_mtime if p.exists() else None}


def export_wav(name: str, repeat: int = 1) -> dict:
    s = _need_synth()
    if repeat not in (1, 2, 4, 8):
        raise SketchError("繰り返しは 1・2・4・8 のどれか")
    data = open_sketch(name)
    out = _unique(_need_folder() / f"{name}.wav")
    s.write_wav(out, s.render(data["sketch"], repeat))
    return {"path": str(out), "file": out.name}


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


def blob_path(key: str) -> Path:
    """パネルで鳴らす 1 音の WAV（/blob/sketch/<key>）。初めて頼まれたときに作って data_dir に置いておく。"""
    s = _need_synth()
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
