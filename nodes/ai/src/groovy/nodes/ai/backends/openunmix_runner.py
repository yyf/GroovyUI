"""Open-Unmix (UMX) separation for SeparateStems — Mac-friendly PyTorch peer to Demucs."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import torch
from scipy import signal

MODEL_ID_TO_UMX: dict[str, str] = {
    "openunmix-umx": "umxhq",
}

UMX_RATE = 44100


@lru_cache(maxsize=1)
def _device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


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
    model_id: str = "openunmix-umx",
) -> dict[str, np.ndarray]:
    model_name = MODEL_ID_TO_UMX.get(model_id)
    if not model_name:
        raise RuntimeError(f"Unsupported Open-Unmix model: {model_id}")

    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)

    working = _resample_pcm(pcm, from_rate=sample_rate, to_rate=UMX_RATE)
    wav = torch.from_numpy(working.astype(np.float32))
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)

    from openunmix import predict

    # openunmix.predict.separate expects (channels, length) — not batched.
    with torch.no_grad():
        estimates = predict.separate(
            wav.to(_device()),
            rate=UMX_RATE,
            model_str_or_path=model_name,
            device=_device(),
        )

    stem_pcm: dict[str, np.ndarray] = {}
    for name in ("vocals", "drums", "bass", "other"):
        if name not in estimates:
            continue
        tensor = estimates[name]
        if tensor.dim() == 3:
            tensor = tensor[0]
        channels = tensor.detach().cpu().numpy().astype(np.float64)
        if channels.ndim == 1:
            channels = channels.reshape(1, -1)
        if channels.shape[0] != pcm.shape[0]:
            if pcm.shape[0] == 1:
                channels = channels.mean(axis=0, keepdims=True)
            elif channels.shape[0] == 1:
                channels = np.tile(channels, (pcm.shape[0], 1))
            else:
                channels = channels[: pcm.shape[0]]
        stem_pcm[name] = _resample_pcm(channels, from_rate=UMX_RATE, to_rate=sample_rate)

    for name in ("vocals", "drums", "bass", "other"):
        if name not in stem_pcm:
            stem_pcm[name] = np.zeros((pcm.shape[0], pcm.shape[1]), dtype=np.float64)
    return stem_pcm
