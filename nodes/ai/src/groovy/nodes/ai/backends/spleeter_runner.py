"""Spleeter 2-stem separation for SeparateStems (vocals + accompaniment → other)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy import signal

SPLEETER_RATE = 44100


@lru_cache(maxsize=1)
def _load_separator() -> object:
    from spleeter.separator import Separator

    return Separator("spleeter:2stems")


def _resample_pcm(pcm: np.ndarray, *, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return pcm
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    out_channels = []
    for channel in pcm:
        target_len = max(1, int(len(channel) * to_rate / from_rate))
        out_channels.append(signal.resample(channel, target_len).astype(np.float64))
    return np.stack(out_channels, axis=0)


def separate_pcm_to_stems(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str = "spleeter-2stems",
) -> dict[str, np.ndarray]:
    """Return vocals/drums/bass/other — drums and bass are silence for 2-stem Spleeter."""
    _ = model_id
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)

    working = _resample_pcm(pcm, from_rate=sample_rate, to_rate=SPLEETER_RATE)
    # Spleeter expects (nb_frames, nb_channels).
    waveform = working.T.astype(np.float32)
    if waveform.shape[1] == 1:
        waveform = np.repeat(waveform, 2, axis=1)

    separator = _load_separator()
    prediction = separator.separate(waveform)
    vocals = np.asarray(prediction["vocals"], dtype=np.float64).T
    accompaniment = np.asarray(prediction["accompaniment"], dtype=np.float64).T

    def _match_channels(stem: np.ndarray) -> np.ndarray:
        if pcm.shape[0] == 1:
            return stem.mean(axis=0, keepdims=True)
        if stem.shape[0] > pcm.shape[0]:
            return stem[: pcm.shape[0]]
        if stem.shape[0] < pcm.shape[0]:
            return np.tile(stem.mean(axis=0, keepdims=True), (pcm.shape[0], 1))
        return stem

    vocals = _resample_pcm(_match_channels(vocals), from_rate=SPLEETER_RATE, to_rate=sample_rate)
    other = _resample_pcm(
        _match_channels(accompaniment), from_rate=SPLEETER_RATE, to_rate=sample_rate
    )
    silence = np.zeros_like(vocals)
    return {
        "vocals": vocals,
        "drums": silence,
        "bass": silence,
        "other": other,
    }
