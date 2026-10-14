"""確かめ用のマイク（soundcard の代わり）。
マイク: 部屋の小さな雑音と、0.3 秒後に「コン」と鳴るガラスの音。PC の音: pc_tone（Hz）の「声」（2ch）。"""
from __future__ import annotations

import contextlib
import time

import numpy as np


class _Rec:
    def __init__(self, rate: int, tone: float, speed: float, channels: int = 1, pc_tone: float = 0.0):
        self.rate, self.tone, self.speed, self.pos = rate, tone, speed, 0
        self.channels, self.pc_tone = channels, pc_tone
        self.rng = np.random.default_rng(3)

    def record(self, numframes: int):
        t = (self.pos + np.arange(numframes)) / self.rate
        self.pos += numframes
        if self.channels == 2:      # PC の音（雑音なし）。待ち時間はマイクの方だけで取る
            x = 0.5 * np.sin(2 * np.pi * self.pc_tone * t) * (t >= 0.2) if self.pc_tone else np.zeros(numframes)
            return np.stack([x, x], axis=1).astype(np.float32)
        x = 0.01 * self.rng.standard_normal(numframes)
        if self.tone:
            u = np.maximum(t - 0.3, 0)
            hit = t >= 0.3
            x += hit * 0.6 * np.exp(-u / 0.35) * (np.sin(2 * np.pi * self.tone * u) + 0.4 * np.sin(2 * np.pi * self.tone * 2.76 * u))
        time.sleep(numframes / self.rate / self.speed)
        return x.astype(np.float32).reshape(-1, 1)


class _Mic:
    def __init__(self, backend, loopback: bool = False):
        self.b, self.loopback = backend, loopback

    @contextlib.contextmanager
    def recorder(self, samplerate, channels=1, blocksize=None):
        yield _Rec(samplerate, self.b.tone, self.b.speed, channels, self.b.pc_tone if self.loopback else 0.0)


class _Speaker:
    id = "speaker-1"


class FakeSoundcard:
    """tone = ガラスの音の高さ（Hz）。0 なら雑音だけ。speed = 実際の何倍の速さで録れるか。"""

    def __init__(self, tone: float = 1200.0, speed: float = 1.0, pc_tone: float = 440.0, has_mic: bool = True):
        self.tone, self.speed, self.pc_tone, self.has_mic = tone, speed, pc_tone, has_mic

    def default_microphone(self):
        return _Mic(self) if self.has_mic else None

    def default_speaker(self):
        return _Speaker()

    def get_microphone(self, id, include_loopback=False):
        return _Mic(self, loopback=True)
