"""mic.py — 短い音をマイクで録る（別スレッド・メモリの中だけ）。api.py から使う。

・soundcard（BSD-3-Clause）で Windows の WASAPI から、既定のマイクと PC の音（ループバック）を同時に・別々に録る
  （電話越しの声・動画の環境音など、PC で鳴っている音も楽器の元にできる。どちらを使うかは録ったあとで選ぶ）
・WASAPI は COM を使う。録るスレッドの中で COM を始める
  順番に注意: soundcard は読み込むときに自分で CoInitializeEx し、「もう始まっている（S_FALSE）」を
  エラー 0x100000001 として投げる。だから soundcard を先に読み込み、そのあとで com_thread() に入る
・Rec Sketch の recorder.py と同じ補い（float32 の形式を自分で作る・プライバシー設定の案内）を持つ。
  Rec Sketch を入れていない人でも、サウンドスケッチだけで録れるようにするため
"""
from __future__ import annotations

import contextlib
import math
import sys
import threading
from pathlib import Path

RATE = 48000
BLOCK = RATE // 10          # 1 回に読む長さ（0.1 秒）
BUFFER = RATE // 2          # WASAPI の受け皿（0.5 秒）。2 つの入口を順に読むので、待っている間にあふれない大きさにする
SOURCES = ("mic", "pc")
FLOOR_DB = -90.0


class MicError(Exception):
    pass


@contextlib.contextmanager
def com_thread():
    """このスレッドで COM を使えるようにする（Windows 以外では何もしない）。"""
    ok = False
    try:
        import ctypes
        ole32 = ctypes.windll.ole32          # type: ignore[attr-defined]
        ok = ole32.CoInitializeEx(None, 0) in (0, 1)   # S_OK / S_FALSE。0 = COINIT_MULTITHREADED
    except (ImportError, AttributeError, OSError):
        ole32 = None
    try:
        yield
    finally:
        if ok and ole32 is not None:
            ole32.CoUninitialize()


def load_backend():
    """soundcard。無ければ MicError（画面に入れ方を出す）。"""
    try:
        import soundcard
    except ImportError:
        raise MicError("録音には soundcard が必要です。コマンドプロンプトで py -m pip install soundcard を実行して、"
                       "Hub を再起動してください") from None
    except Exception as e:  # noqa: BLE001 — Windows 以外・音の仕組みが無い環境など
        raise MicError(f"録音の仕組み（soundcard）を使えません: {type(e).__name__}: {e}") from None
    _patch_mix_format()
    return soundcard


# ---------- soundcard の補い（Rec Sketch と同じ） ----------
# soundcard は機器の形式（GetMixFormat）が WAVEFORMATEXTENSIBLE・float32 であることを assert で確かめ、
# 違うと文の無い AssertionError で止まる（例: EMEET SmartCam C960 のマイク）。
# そのときだけ、こちらで float32 の形式を作って Windows に渡し、変換は Windows に任せる（AUTOCONVERTPCM）。
_IEEE_FLOAT = bytes.fromhex("0300000000001000800000aa00389b71")   # KSDATAFORMAT_SUBTYPE_IEEE_FLOAT（GUID のバイト列）


def _patch_mix_format() -> None:
    mf = sys.modules.get("soundcard.mediafoundation")
    cls = getattr(mf, "_AudioClient", None) if mf else None
    if cls is None or getattr(cls, "_rec_sketch_patched", False):   # Rec Sketch が先に補っていれば、そのまま使う
        return
    original = cls.__init__

    def __init__(self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode=False):
        try:
            original(self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode)
        except AssertionError:
            _init_float32(mf, self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode)

    cls.__init__ = __init__
    cls._rec_sketch_patched = True


def _init_float32(mf, self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode) -> None:
    """soundcard の _AudioClient.__init__ と同じことを、形式だけ自分で作って行う。"""
    import struct
    self._ptr = ptr
    self.channelmap = list(range(channels)) if isinstance(channels, int) else list(channels)
    if blocksize is None:
        blocksize = self.deviceperiod[0] * samplerate
    n = len(set(self.channelmap))
    sr = int(samplerate)
    mask = 0x4 if n == 1 else (1 << n) - 1
    raw = struct.pack("<HHIIHHHHI16s", 0xFFFE, n, sr, sr * n * 4, n * 4, 32, 22, 32, mask, _IEEE_FLOAT)
    self._rec_sketch_fmt = mf._ffi.new("char[]", raw)
    share = mf._ole32.AUDCLNT_SHAREMODE_EXCLUSIVE if exclusive_mode else mf._ole32.AUDCLNT_SHAREMODE_SHARED
    flags = 0x00100000 | 0x80000000 | 0x08000000 | 0x00080000
    if isloopback:
        flags |= 0x00020000
    duration = int(blocksize / samplerate * 10_000_000)
    hr = self._ptr[0][0].lpVtbl.Initialize(self._ptr[0], share, flags, duration, 0,
                                           mf._ffi.cast("WAVEFORMATEXTENSIBLE *", self._rec_sketch_fmt), mf._ffi.NULL)
    mf._com.check_error(hr)
    self.samplerate = samplerate
    self._idle_start_time = None


def describe(e: BaseException) -> str:
    """利用者に見せる 1 行。文が空のエラー（soundcard の assert など）でも、種類と止まった場所が分かるようにする。"""
    import traceback
    msg = str(e) or type(e).__name__
    tb = traceback.extract_tb(e.__traceback__)
    if tb:
        f = tb[-1]
        msg = f"{type(e).__name__}: {msg if str(e) else ''} [{Path(f.filename).name}:{f.lineno}]".replace(":  [", " [")
    return msg[:300]


PRIVACY_HINT = ("。Windows の 設定 → プライバシーとセキュリティ → マイク で「マイクへのアクセス」と"
                "「デスクトップ アプリがマイクにアクセスできるようにする」が オン か確かめてください")


def privacy_hint(e: BaseException) -> str:
    return PRIVACY_HINT if isinstance(e, AssertionError) or "0x80070005" in str(e).lower() else ""


def db(x) -> float:
    """ピークの dBFS。"""
    import numpy as np
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    return round(20 * math.log10(peak), 1) if peak > 1e-9 else FLOOR_DB


class Capture:
    """1 回分の短い録音。start() で別スレッドが動き、seconds 秒たつか stop() で止まる。音はメモリに持つ。
    マイク（mic）と PC の音（pc）を同じ長さで別々に持つ。片方が開けなければ、もう片方だけで録る。"""

    def __init__(self, seconds: float, backend=None, want_pc: bool = True):
        self.limit = float(seconds)
        self.want_pc = want_pc
        self.frames = 0
        self.levels = {s: FLOOR_DB for s in SOURCES}
        self.opened: dict[str, bool] = {s: False for s in SOURCES}
        self.notes: list[str] = []          # 片方だけ開けなかった理由（録音は続ける）
        self.error = ""
        self._chunks: dict[str, list] = {s: [] for s in SOURCES}
        self._backend = backend
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sketch-mic", daemon=True)

    def start(self, wait: float = 8.0) -> None:
        """録り始める。どちらも開けなかったときはここで MicError。"""
        self._thread.start()
        self._ready.wait(wait)
        if self.error and not self.frames:
            self._thread.join(2)
            raise MicError(self.error)

    def stop(self, wait: float = 3.0) -> None:
        self._stop.set()
        self._thread.join(wait)

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    @property
    def seconds(self) -> float:
        return self.frames / RATE

    def audio(self, source: str = "mic"):
        """録れた音（RATE の 1ch・float32）。開けなかった入口は None。"""
        import numpy as np
        if not self.opened.get(source):
            return None
        ch = self._chunks[source]
        return np.concatenate(ch) if ch else np.zeros(0, np.float32)

    def _open(self, sc, stack) -> dict:
        recs = {}
        try:
            mic = sc.default_microphone()
            if mic is None:
                raise MicError("マイクが見つかりません")
            recs["mic"] = stack.enter_context(mic.recorder(samplerate=RATE, channels=1, blocksize=BUFFER))
        except Exception as e:  # noqa: BLE001
            self.notes.append(f"マイク: {e if isinstance(e, MicError) else describe(e) + privacy_hint(e)}")
        if self.want_pc:
            try:
                spk = sc.default_speaker()
                if spk is None:
                    raise MicError("PC の音の出口（スピーカー・ヘッドホン）が見つかりません")
                loop = sc.get_microphone(str(spk.id), include_loopback=True)
                recs["pc"] = stack.enter_context(loop.recorder(samplerate=RATE, channels=2, blocksize=BUFFER))
            except Exception as e:  # noqa: BLE001
                self.notes.append(f"PC の音: {e if isinstance(e, MicError) else describe(e)}")
        if not recs:
            raise MicError("録れる入口がありません（" + " / ".join(self.notes) + "）")
        return recs

    def _run(self) -> None:
        import numpy as np
        try:
            sc = self._backend or load_backend()     # 先に読み込む（com_thread より後だと 0x100000001 になる）
            with com_thread(), contextlib.ExitStack() as stack:
                recs = self._open(sc, stack)
                for s in recs:
                    self.opened[s] = True
                self._ready.set()
                end = int(self.limit * RATE)
                while not self._stop.is_set() and self.frames < end:
                    got = {}
                    for s, r in recs.items():
                        x = np.asarray(r.record(numframes=BLOCK), dtype=np.float32)
                        got[s] = x.reshape(len(x), -1).mean(axis=1)        # PC の音（左右）は 1 本に
                    n = min(min(len(x) for x in got.values()), end - self.frames)
                    for s, x in got.items():
                        self._chunks[s].append(x[:n].copy())
                        self.levels[s] = db(x[:n])
                    self.frames += n
        except MicError as e:
            self.error = str(e)
        except Exception as e:  # noqa: BLE001
            self.error = f"録音が止まりました: {describe(e)}{privacy_hint(e)}"
        finally:
            self._ready.set()
