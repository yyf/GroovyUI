from __future__ import annotations

import numpy as np
from scipy import signal


def denoise_audio(
    pcm: np.ndarray,
    *,
    model_id: str,
    strength: float,
    sample_rate: int,
) -> np.ndarray:
    """Phase 1 dev inference — spectral gate placeholder until DeepFilterNet weights ship."""
    _ = model_id, sample_rate
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0:
        return pcm.copy()

    out = pcm.copy()
    for ch in range(out.shape[0]):
        channel = out[ch]
        f, t, stft = signal.stft(channel, nperseg=1024)
        mag = np.abs(stft)
        noise_floor = np.percentile(mag, 20, axis=1, keepdims=True)
        mask = np.clip((mag - noise_floor) / (noise_floor + 1e-8), 0.0, 1.0)
        mask = 1.0 - strength * (1.0 - mask)
        cleaned = signal.istft(stft * mask, nperseg=1024)[1]
        if cleaned.shape[0] > channel.shape[0]:
            cleaned = cleaned[: channel.shape[0]]
        elif cleaned.shape[0] < channel.shape[0]:
            cleaned = np.pad(cleaned, (0, channel.shape[0] - cleaned.shape[0]))
        out[ch] = cleaned
    return out
