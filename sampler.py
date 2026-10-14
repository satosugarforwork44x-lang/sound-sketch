"""sampler.py — 録った短い音を「楽器の音」に整える（numpy だけ）。

流れ: 雑音を引く → 前後の無音を切る → 長さをそろえる（終わりをフェード）→ 音量をそろえる → 元の高さを調べる
高さが分かれば、鍵盤で弾いたときに正しい高さで鳴る（synth.sample_voice が速さを変えてずらす）。
"""
from __future__ import annotations

import math

import numpy as np

SR = 44100
N_FFT = 2048
HOP = 512
PEAK = 0.89                       # 音量をそろえるときの山の高さ（-1 dBFS）
_WIN = np.hanning(N_FFT + 1)[:-1]  # 端が 0 で、重ねると平らになる窓


def resample(x: np.ndarray, rate: int, to: int = SR) -> np.ndarray:
    if rate == to or not len(x):
        return np.asarray(x, dtype=np.float64)
    t = np.arange(int(len(x) * to / rate)) * (rate / to)
    return np.interp(t, np.arange(len(x)), x)


# ---------- 雑音 ----------
def _stft(x: np.ndarray) -> np.ndarray:
    x = np.concatenate([np.zeros(N_FFT // 2), x, np.zeros(N_FFT)])
    n = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    return np.fft.rfft(x[idx] * _WIN, axis=1)


def _istft(spec: np.ndarray, length: int) -> np.ndarray:
    frames = np.fft.irfft(spec, n=N_FFT, axis=1) * _WIN
    out = np.zeros(HOP * (len(frames) - 1) + N_FFT)
    norm = np.zeros_like(out)
    for i, f in enumerate(frames):
        out[i * HOP: i * HOP + N_FFT] += f
        norm[i * HOP: i * HOP + N_FFT] += _WIN ** 2
    out /= np.maximum(norm, 1e-8)
    return out[N_FFT // 2: N_FFT // 2 + length]


def noise_profile(x: np.ndarray) -> np.ndarray:
    """部屋の雑音の「周波数ごとの大きさ」の平均。"""
    if len(x) < N_FFT:
        raise ValueError("雑音が短すぎます")
    return np.abs(_stft(x)).mean(axis=0)


def denoise(x: np.ndarray, profile: np.ndarray, strength: float = 2.0, floor: float = 0.06) -> np.ndarray:
    """雑音の大きさを、周波数ごとに差し引く（スペクトル減算）。引きすぎで音が崩れないよう floor は残す。"""
    if not len(x) or not np.any(profile):
        return x
    spec = _stft(x)
    mag = np.abs(spec)
    gain = np.maximum(1 - strength * profile[None, :] / np.maximum(mag, 1e-12), floor)
    return _istft(spec * gain, len(x))


# ---------- 形を整える ----------
def trim(x: np.ndarray, thresh_db: float = -40.0, pre: float = 0.005, post: float = 0.03) -> np.ndarray:
    """前後の無音を切る。山の高さから thresh_db 下がった所までを音とみる。"""
    if not len(x):
        return x
    env = np.abs(x)
    top = env.max()
    if top <= 1e-9:
        return x[:0]
    on = np.nonzero(env > top * 10 ** (thresh_db / 20))[0]
    a = max(0, on[0] - int(pre * SR))
    b = min(len(x), on[-1] + int(post * SR))
    y = x[a:b].copy()
    n = min(len(y), int(0.002 * SR))          # 切り口の「プツッ」を消す
    if n:
        y[:n] *= np.linspace(0, 1, n)
    return y


def shape(x: np.ndarray, length: float) -> np.ndarray:
    """length 秒より長ければ切り、終わりを自然に消す（余韻の長さ）。"""
    n = int(max(0.05, length) * SR)
    y = x[:n].copy()
    fade = min(len(y), int(min(0.3, 0.5 * len(y) / SR) * SR))
    if fade > 1:
        y[-fade:] *= np.cos(np.linspace(0, np.pi / 2, fade)) ** 2
    return y


def normalize(x: np.ndarray, peak: float = PEAK) -> np.ndarray:
    top = float(np.max(np.abs(x))) if len(x) else 0.0
    return x * (peak / top) if top > 1e-9 else x


# ---------- 元の高さ ----------
def _yin_frame(w: np.ndarray, tau_min: int, tau_max: int, thr: float = 0.15):
    """YIN（倍音のある音の高さの求め方）。戻り値: (周期（サンプル）, 確かさ 0〜1) か None。"""
    half = len(w) // 2
    a = w[:half]
    e0 = float(np.dot(a, a))
    if e0 <= 1e-10:
        return None
    sq = np.concatenate([[0.0], np.cumsum(w * w)])
    e = sq[np.arange(half) + half] - sq[np.arange(half)]              # x[tau : tau+half] の大きさ
    nfft = 1 << (len(w) * 2 - 1).bit_length()
    r = np.fft.irfft(np.conj(np.fft.rfft(a, nfft)) * np.fft.rfft(w, nfft), nfft)[:half]
    d = np.maximum(e0 + e - 2 * r, 0)
    cm = np.ones_like(d)
    cs = np.cumsum(d[1:])
    cm[1:] = d[1:] * np.arange(1, half) / np.maximum(cs, 1e-12)
    hi = min(tau_max, half - 2)
    cand = np.nonzero(cm[tau_min:hi] < thr)[0]
    if len(cand):
        t = tau_min + cand[0]
        while t + 1 < hi and cm[t + 1] < cm[t]:
            t += 1
    else:
        t = tau_min + int(np.argmin(cm[tau_min:hi]))
        if cm[t] > 0.35:
            return None
    if 0 < t < len(cm) - 1:                  # となりの値で、周期を細かく求める
        y0, y1, y2 = cm[t - 1], cm[t], cm[t + 1]
        den = y0 - 2 * y1 + y2
        t = t + (0.5 * (y0 - y2) / den if abs(den) > 1e-12 else 0.0)
    return t, float(1 - min(1.0, cm[int(round(t))]))


def detect_pitch(x: np.ndarray, fmin: float = 40.0, fmax: float = 2000.0) -> dict | None:
    """元の高さ。{"midi": 69.02, "hz": 440.1, "how": "yin"|"peak", "sure": 0〜1}。分からなければ None。
    叩いた音（ガラス・金属）は倍音がそろわないので、YIN で決まらなければ、いちばん強い周波数を高さとみる。"""
    if len(x) < N_FFT:
        x = np.concatenate([x, np.zeros(N_FFT - len(x))])
    w_len = N_FFT
    start = min(len(x) - w_len, int(0.02 * SR))       # 叩いた瞬間の雑音は飛ばす
    seg = x[start: start + int(0.6 * SR)]
    frames = [seg[i: i + w_len] for i in range(0, max(1, len(seg) - w_len + 1), HOP)]
    rms = np.array([math.sqrt(float(np.mean(f * f))) for f in frames])
    if not len(rms) or rms.max() <= 1e-6:
        return None
    hz, sure = [], []
    for f, v in zip(frames, rms):
        if v < rms.max() * 0.15:
            continue
        res = _yin_frame(f, int(SR / fmax), int(SR / fmin))
        if res:
            hz.append(SR / res[0])
            sure.append(res[1])
    voiced = len(hz) / max(1, int(np.sum(rms >= rms.max() * 0.15)))
    peak = _strongest(seg, fmin)
    if hz and voiced >= 0.5:
        h = float(np.median(hz))
        # 倍音がそろった音なら、いちばん強い周波数は h の整数倍になる。ならなければ叩いた音とみて、強い周波数を使う
        if peak is None or any(abs(1200 * math.log2(peak / (k * h))) < 50 for k in range(1, 9)):
            return _pitch(h, "yin", float(np.median(sure)) * voiced)
    return _pitch(peak, "peak", 0.3) if peak else None


def _strongest(seg: np.ndarray, fmin: float) -> float | None:
    """いちばん強い周波数（叩いた音向け）。"""
    w = seg[: 1 << 15]
    if len(w) < 64:
        return None
    spec = np.abs(np.fft.rfft(w * np.hanning(len(w))))
    freqs = np.fft.rfftfreq(len(w), 1 / SR)
    spec[(freqs < fmin) | (freqs > 5000)] = 0
    k = int(np.argmax(spec))
    if spec[k] <= 0:
        return None
    if 0 < k < len(spec) - 1:                # となりの値で細かく
        a, b, c = np.log(spec[k - 1: k + 2] + 1e-12)
        den = a - 2 * b + c
        k = k + (0.5 * (a - c) / den if abs(den) > 1e-12 else 0.0)
    return float(k * SR / len(w))


def _pitch(h: float, how: str, sure: float) -> dict:
    return {"midi": round(69 + 12 * math.log2(h / 440), 2), "hz": round(h, 1), "how": how, "sure": round(sure, 2)}


# ---------- まとめて ----------
def process(raw: np.ndarray, noise: np.ndarray | None, opts: dict) -> tuple[np.ndarray, dict | None]:
    """opts: denoise / trim / normalize（真偽）、length（秒）。戻り値: (整えた音, 高さ)。"""
    x = np.asarray(raw, dtype=np.float64)
    if opts.get("denoise", True) and noise is not None:
        x = denoise(x, noise)
    if opts.get("trim", True):
        x = trim(x)
    pitch = detect_pitch(x) if len(x) else None
    x = shape(x, float(opts.get("length", 2.0)))
    if opts.get("normalize", True):
        x = normalize(x)
    return x, pitch


def peaks(x: np.ndarray, bins: int = 400) -> list[float]:
    """波形を描く用（区切りごとの最大値。そのままの大きさ、1 で頭打ち）。"""
    if not len(x):
        return []
    n = max(1, len(x) // bins)
    k = len(x) // n
    p = np.abs(x[: k * n]).reshape(k, n).max(axis=1)
    return [round(min(1.0, float(v)), 3) for v in p]
