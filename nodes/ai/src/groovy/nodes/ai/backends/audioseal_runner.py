"""AudioSeal watermark embed/detect (Meta, MIT).

Stub helpers are torch-free so CI with ``GROOVY_INFERENCE_STUB=1`` works without torch.
Real inference imports torch lazily.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import torch


@lru_cache(maxsize=1)
def _load_generator():
    from audioseal import AudioSeal

    model = AudioSeal.load_generator("audioseal_wm_16bits")
    model.eval()
    return model


@lru_cache(maxsize=1)
def _load_detector():
    from audioseal import AudioSeal

    model = AudioSeal.load_detector("audioseal_detector_16bits")
    model.eval()
    return model


def _pcm_to_tensor(pcm: np.ndarray) -> torch.Tensor:
    import torch

    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    return torch.from_numpy(pcm.astype(np.float32)).unsqueeze(0)


def _tensor_to_pcm(tensor: torch.Tensor, *, channels: int) -> np.ndarray:
    arr = tensor.detach().cpu().numpy()
    if arr.ndim == 3:
        arr = arr[0]
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[0] != channels and arr.shape[1] == channels:
        arr = arr.T
    return arr.astype(np.float64)


def message_id_to_bits(message_id: int, *, nbits: int = 16) -> torch.Tensor:
    import torch

    message_id = int(message_id) & ((1 << nbits) - 1)
    bits = [(message_id >> bit) & 1 for bit in range(nbits - 1, -1, -1)]
    return torch.tensor([bits], dtype=torch.float32)


def _stub_watermark(message_id: int, shape: tuple[int, ...], *, sample_rate: int = 48_000) -> np.ndarray:
    _ = sample_rate
    channels, frame_count = shape[0], shape[1]
    tag = np.zeros((channels, frame_count), dtype=np.float64)
    if frame_count < 17:
        return tag
    start = frame_count - 17
    scale = 1e-4
    tag[:, start] = scale
    for bit_index in range(16):
        bit = (int(message_id) >> bit_index) & 1
        tag[:, start + 1 + bit_index] = scale * (0.25 + 0.5 * bit)
    return tag


def embed_watermark_stub(
    pcm: np.ndarray,
    *,
    message_id: int = 0,
    strength: float = 1.0,
    sample_rate: int = 48_000,
) -> np.ndarray:
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    strength = float(np.clip(strength, 0.0, 2.0))
    out = pcm.copy()
    tag = _stub_watermark(message_id, out.shape, sample_rate=sample_rate) * strength
    mask = tag != 0
    out[mask] = tag[mask]
    return out


def detect_watermark_stub(
    pcm: np.ndarray,
    *,
    threshold: float = 0.5,
    sample_rate: int = 48_000,
) -> tuple[float, int, list[int]]:
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    threshold = float(np.clip(threshold, 0.0, 1.0))
    if pcm.shape[1] < 17:
        return 0.01, 0, [0] * 16
    start = pcm.shape[1] - 17
    magic = float(np.mean(pcm[:, start]))
    if magic < 5e-5:
        return 0.01, 0, [0] * 16
    bits: list[int] = []
    message_id = 0
    pivot = magic * 0.5
    for bit_index in range(16):
        value = float(np.mean(pcm[:, start + 1 + bit_index]))
        bit = 1 if value > pivot else 0
        bits.append(bit)
        message_id |= bit << bit_index
    probability = min(1.0, magic / 1e-4)
    detected = probability >= threshold
    return probability if detected else probability * 0.5, message_id if detected else 0, bits


def embed_watermark_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    message_id: int = 0,
    strength: float = 1.0,
) -> np.ndarray:
    import torch

    _ = sample_rate
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    strength = float(np.clip(strength, 0.0, 2.0))
    model = _load_generator()
    wav = _pcm_to_tensor(pcm)
    message = message_id_to_bits(message_id).to(wav.device)
    with torch.no_grad():
        watermark = model.get_watermark(wav, message=message)
        watermarked = wav + strength * watermark
    return _tensor_to_pcm(watermarked, channels=pcm.shape[0])


def detect_watermark_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    threshold: float = 0.5,
) -> tuple[float, int, list[int]]:
    import torch

    _ = sample_rate
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    threshold = float(np.clip(threshold, 0.0, 1.0))
    detector = _load_detector()
    wav = _pcm_to_tensor(pcm)
    with torch.no_grad():
        probability_raw, message = detector.detect_watermark(wav)
    if isinstance(probability_raw, torch.Tensor):
        probability = float(probability_raw.detach().cpu().reshape(-1)[0].item())
    else:
        probability = float(probability_raw)
    if isinstance(message, torch.Tensor):
        bits = [int(round(float(bit))) for bit in message.detach().cpu().reshape(-1).tolist()]
    else:
        bits = [int(round(float(bit))) for bit in message]
    message_id = 0
    for bit in bits[:16]:
        message_id = (message_id << 1) | (1 if bit else 0)
    detected = probability >= threshold
    return probability if detected else min(probability, 1.0 - threshold), message_id, bits[:16]
