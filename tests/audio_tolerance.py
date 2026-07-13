"""Tolerance helpers for real AI-chain golden checks (not bit-identical)."""

from __future__ import annotations

import numpy as np


def mono(pcm: np.ndarray) -> np.ndarray:
    if pcm.ndim == 1:
        return pcm.astype(np.float64)
    return pcm.mean(axis=0).astype(np.float64)


def align_pair(reference: np.ndarray, estimate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ref = mono(reference)
    est = mono(estimate)
    n = min(ref.size, est.size)
    if n <= 0:
        return ref[:0], est[:0]
    return ref[:n], est[:n]


def snr_db(reference: np.ndarray, estimate: np.ndarray) -> float:
    """Signal-to-noise ratio treating ``estimate - reference`` as noise."""
    ref, est = align_pair(reference, estimate)
    if ref.size == 0:
        return float("-inf")
    noise = est - ref
    signal_power = float(np.mean(np.square(ref)))
    noise_power = float(np.mean(np.square(noise)))
    if signal_power <= 1e-18:
        return float("inf") if noise_power <= 1e-18 else float("-inf")
    if noise_power <= 1e-18:
        return float("inf")
    return 10.0 * float(np.log10(signal_power / noise_power))


def correlation(reference: np.ndarray, estimate: np.ndarray) -> float:
    ref, est = align_pair(reference, estimate)
    if ref.size < 2:
        return 1.0
    if float(np.std(ref)) < 1e-12 or float(np.std(est)) < 1e-12:
        return 0.0
    return float(np.corrcoef(ref, est)[0, 1])


def duration_delta_sec(frames_a: int, frames_b: int, sample_rate: int) -> float:
    return abs(frames_a - frames_b) / max(sample_rate, 1)


def assert_peak_sane(pcm: np.ndarray, *, label: str) -> None:
    peak = float(np.max(np.abs(pcm))) if pcm.size else 0.0
    assert peak > 1e-6, f"{label}: output is silent (peak={peak})"
    assert peak <= 4.0, f"{label}: output clipped hard (peak={peak})"
