"""RAVE TorchScript timbre transfer (encode → latent → decode)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from scipy import signal

DEFAULT_MODEL_SR = 48000
# Streaming exports often use power-of-two hops; pad so encode/decode stay stable.
_PAD_MULTIPLE = 2048


def _device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _resample_pcm(pcm: np.ndarray, *, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return pcm
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    out = []
    for channel in pcm:
        target_len = max(1, int(round(len(channel) * to_rate / from_rate)))
        out.append(signal.resample(channel, target_len).astype(np.float64))
    return np.stack(out, axis=0)


def _read_sidecar_sr(model_path: Path) -> int | None:
    sidecar = model_path.with_suffix(".json")
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for key in ("sample_rate", "sr", "sampling_rate", "samplerate"):
        value = data.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def _model_sample_rate(model: torch.jit.ScriptModule, model_path: Path) -> int:
    for attr in ("sr", "sample_rate", "sampling_rate", "samplerate"):
        if hasattr(model, attr):
            try:
                return int(getattr(model, attr))
            except (TypeError, ValueError):
                continue
    sidecar_sr = _read_sidecar_sr(model_path)
    if sidecar_sr:
        return sidecar_sr
    return DEFAULT_MODEL_SR


@lru_cache(maxsize=2)
def _load_rave(model_path: str) -> tuple[torch.jit.ScriptModule, torch.device, int]:
    path = Path(model_path)
    if not path.is_file():
        raise RuntimeError(f"RAVE checkpoint not found: {path}")
    device = _device()
    model = torch.jit.load(str(path), map_location=device)
    model.eval()
    return model, device, _model_sample_rate(model, path)


def _pad_frames(frames: int) -> int:
    if frames % _PAD_MULTIPLE == 0:
        return frames
    return frames + (_PAD_MULTIPLE - frames % _PAD_MULTIPLE)


def _apply_fidelity(z: torch.Tensor, fidelity: float) -> torch.Tensor:
    fidelity = float(np.clip(fidelity, 0.0, 1.0))
    if fidelity >= 0.999:
        return z
    # Soften reconstruction: truncate high latent dims + light noise.
    out = z.clone()
    if out.ndim >= 2 and out.shape[1] > 1:
        keep = max(1, int(round(out.shape[1] * fidelity)))
        if keep < out.shape[1]:
            out[:, keep:, ...] = 0
    if fidelity < 1.0:
        noise_scale = 0.35 * (1.0 - fidelity)
        out = out + noise_scale * torch.randn_like(out)
    return out


def transfer_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_path: Path | str,
    fidelity: float = 1.0,
) -> np.ndarray:
    """Run RAVE encode/decode timbre transfer on planar PCM (channels, frames)."""
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    channel_count = int(pcm.shape[0])
    mono = pcm.mean(axis=0).astype(np.float64)

    model, device, model_sr = _load_rave(str(Path(model_path).resolve()))
    working = _resample_pcm(mono.reshape(1, -1), from_rate=sample_rate, to_rate=model_sr)[0]
    original_len = int(working.shape[0])
    padded_len = _pad_frames(original_len)
    if padded_len > original_len:
        working = np.pad(working, (0, padded_len - original_len))

    x = torch.from_numpy(working.astype(np.float32)).reshape(1, 1, -1).to(device)
    with torch.no_grad():
        if hasattr(model, "encode") and hasattr(model, "decode"):
            z = model.encode(x)
            z = _apply_fidelity(z, fidelity)
            y = model.decode(z)
        else:
            y = model(x)

    out = y.detach().float().cpu().numpy()
    if out.ndim == 3:
        out = out[0, 0]
    elif out.ndim == 2:
        out = out[0]
    out = np.asarray(out, dtype=np.float64).reshape(-1)
    out = out[:original_len]
    out = _resample_pcm(out.reshape(1, -1), from_rate=model_sr, to_rate=sample_rate)[0]

    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 1.0:
        out = out / peak * 0.99

    if channel_count == 1:
        return out.reshape(1, -1)
    return np.stack([out] * channel_count, axis=0)


def clear_rave_cache() -> None:
    _load_rave.cache_clear()
