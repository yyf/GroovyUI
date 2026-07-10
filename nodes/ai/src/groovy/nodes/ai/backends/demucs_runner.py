from __future__ import annotations

import contextlib
import io
from functools import lru_cache

import numpy as np
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model
from scipy import signal

MODEL_ID_TO_DEMUCS: dict[str, str] = {
    "demucs-v4": "htdemucs",
    "demucs-v4-ht": "htdemucs_ft",
}


@lru_cache(maxsize=2)
def _load_demucs(model_name: str) -> tuple[object, str]:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = get_model(model_name)
    model.to(device)
    model.eval()
    return model, device


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
    model_id: str,
    shifts: int = 1,
    overlap: float = 0.25,
    segment: float = 0.0,
    split: bool = True,
) -> dict[str, np.ndarray]:
    model_name = MODEL_ID_TO_DEMUCS.get(model_id)
    if not model_name:
        raise RuntimeError(f"Unsupported demucs model: {model_id}")

    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)

    model, device = _load_demucs(model_name)
    model_rate = int(getattr(model, "samplerate", 44100))
    working = _resample_pcm(pcm, from_rate=sample_rate, to_rate=model_rate)

    wav = torch.from_numpy(working.astype(np.float32))
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)

    apply_kwargs: dict[str, object] = {
        "shifts": max(0, int(shifts)),
        "overlap": float(np.clip(overlap, 0.0, 0.99)),
        "split": bool(split),
        "progress": False,
    }
    if segment > 0:
        apply_kwargs["segment"] = float(segment)

    with torch.no_grad():
        with contextlib.redirect_stdout(io.StringIO()):
            separated = apply_model(model, wav[None].to(device), **apply_kwargs)

    stem_pcm: dict[str, np.ndarray] = {}
    for index, name in enumerate(model.sources):
        channels = separated[0, index].detach().cpu().numpy()
        if pcm.shape[0] == 1:
            channels = channels.mean(axis=0, keepdims=True)
        elif channels.shape[0] > pcm.shape[0]:
            channels = channels[: pcm.shape[0]]
        elif channels.shape[0] < pcm.shape[0]:
            channels = np.tile(channels.mean(axis=0, keepdims=True), (pcm.shape[0], 1))
        stem_pcm[name] = _resample_pcm(channels, from_rate=model_rate, to_rate=sample_rate)

    return stem_pcm
