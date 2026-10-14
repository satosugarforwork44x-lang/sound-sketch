"""mic.py — 短い音をマイクで録る（別スレッド・メモリの中だけ）。api.py から使う。

・soundcard（BSD-3-Clause）で Windows の WASAPI から、既定のマイクを 1ch で録る
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
BLOCK = RATE // 20          # 1 回に読む長さ（0.05 秒。レベルの表示を細かくする）
BUFFER = RATE // 2          # WASAPI の受け皿（0.5 秒）
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
    """1 回分の短い録音。start() で別スレッドが動き、seconds 秒たつか stop() で止まる。音はメモリに持つ。"""

    def __init__(self, seconds: float, backend=None):
        self.limit = float(seconds)
        self.frames = 0
        self.level = FLOOR_DB
        self.error = ""
        self._chunks: list = []
        self._backend = backend
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sketch-mic", daemon=True)

    def start(self, wait: float = 8.0) -> None:
        """録り始める。マイクを開けなかったときはここで MicError。"""
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

    def audio(self):
        """録れた音（RATE の 1ch・float32）。"""
        import numpy as np
        return np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)

    def _run(self) -> None:
        import numpy as np
        try:
            sc = self._backend or load_backend()     # 先に読み込む（com_thread より後だと 0x100000001 になる）
            with com_thread():
                mic = sc.default_microphone()
                if mic is None:
                    raise MicError("マイクが見つかりません（Windows の設定 → サウンド → 入力 を確かめてください）")
                with mic.recorder(samplerate=RATE, channels=1, blocksize=BUFFER) as r:
                    self._ready.set()
                    end = int(self.limit * RATE)
                    while not self._stop.is_set() and self.frames < end:
                        x = np.asarray(r.record(numframes=BLOCK), dtype=np.float32)
                        x = x.reshape(len(x), -1)[:, 0][: end - self.frames]
                        self._chunks.append(x.copy())
                        self.level = db(x)
                        self.frames += len(x)
        except MicError as e:
            self.error = str(e)
        except Exception as e:  # noqa: BLE001
            self.error = f"録音が止まりました: {describe(e)}{privacy_hint(e)}"
        finally:
            self._ready.set()
