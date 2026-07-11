from __future__ import annotations

from functools import lru_cache

import numpy as np
import torch
from scipy import signal

from groovy.nodes.ai.deepfilter_compat import ensure_deepfilter_importable

DF_SAMPLE_RATE = 48_000


@lru_cache(maxsize=1)
def _load_deepfilter():
    ensure_deepfilter_importable()
    from df.enhance import init_df

    loaded = init_df()
    if len(loaded) < 2:
        raise RuntimeError(f"Unexpected init_df() return arity: {len(loaded)}")
    model, df_state = loaded[0], loaded[1]
    return model, df_state


def _resample_pcm(pcm: np.ndarray, *, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return pcm
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    out_channels = []
    for channel in pcm:
        target_len = max(1, int(len(channel) * to_rate / from_rate))
        out_channels.append(signal.resample(channel, target_len).astype(np.float32))
    return np.stack(out_channels, axis=0)


def denoise_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    strength: float = 1.0,
) -> np.ndarray:
    ensure_deepfilter_importable()
    from df.enhance import enhance

    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)

    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0:
        return pcm.copy()

    model, df_state = _load_deepfilter()
    working = _resample_pcm(pcm, from_rate=sample_rate, to_rate=DF_SAMPLE_RATE)
    enhanced_channels = []
    with torch.no_grad():
        for channel in working:
            audio = torch.from_numpy(channel.astype(np.float32)[None, :])
            cleaned = enhance(model, df_state, audio).detach().cpu().numpy()[0]
            enhanced_channels.append(cleaned)

    enhanced = np.stack(enhanced_channels, axis=0)
    enhanced = _resample_pcm(enhanced, from_rate=DF_SAMPLE_RATE, to_rate=sample_rate)

    if enhanced.shape[1] > pcm.shape[1]:
        enhanced = enhanced[:, : pcm.shape[1]]
    elif enhanced.shape[1] < pcm.shape[1]:
        enhanced = np.pad(enhanced, ((0, 0), (0, pcm.shape[1] - enhanced.shape[1])))

    if strength >= 1.0:
        return enhanced
    return pcm * (1.0 - strength) + enhanced * strength
