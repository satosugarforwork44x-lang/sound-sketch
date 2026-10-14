"""確かめ用のマイク（soundcard の代わり）。部屋の小さな雑音と、0.3 秒後に「コン」と鳴るガラスの音を返す。"""
from __future__ import annotations

import contextlib
import time

import numpy as np


class _Rec:
    def __init__(self, rate: int, tone: float, speed: float):
        self.rate, self.tone, self.speed, self.pos = rate, tone, speed, 0
        self.rng = np.random.default_rng(3)

    def record(self, numframes: int):
        t = (self.pos + np.arange(numframes)) / self.rate
        self.pos += numframes
        x = 0.01 * self.rng.standard_normal(numframes)
        if self.tone:
            u = np.maximum(t - 0.3, 0)
            hit = t >= 0.3
            x += hit * 0.6 * np.exp(-u / 0.35) * (np.sin(2 * np.pi * self.tone * u) + 0.4 * np.sin(2 * np.pi * self.tone * 2.76 * u))
        time.sleep(numframes / self.rate / self.speed)
        return x.astype(np.float32).reshape(-1, 1)


class _Mic:
    def __init__(self, backend):
        self.b = backend

    @contextlib.contextmanager
    def recorder(self, samplerate, channels=1, blocksize=None):
        yield _Rec(samplerate, self.b.tone, self.b.speed)


class FakeSoundcard:
    """tone = ガラスの音の高さ（Hz）。0 なら雑音だけ。speed = 実際の何倍の速さで録れるか。"""

    def __init__(self, tone: float = 1200.0, speed: float = 1.0):
        self.tone, self.speed = tone, speed

    def default_microphone(self):
        return _Mic(self)
