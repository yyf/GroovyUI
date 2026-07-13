"""Unit tests for AI tolerance helpers (always run in CI)."""

from __future__ import annotations

import numpy as np
import pytest
from audio_tolerance import align_pair, correlation, duration_delta_sec, snr_db


def test_snr_identical_is_infinite() -> None:
    signal = np.sin(np.linspace(0, 6.28, 512))
    assert snr_db(signal, signal) == float("inf")


def test_snr_with_noise_is_finite() -> None:
    signal = np.sin(np.linspace(0, 6.28, 512))
    noisy = signal + 0.05 * np.ones_like(signal)
    value = snr_db(signal, noisy)
    assert 20 < value < 40


def test_correlation_perfect() -> None:
    signal = np.linspace(-1, 1, 100)
    assert correlation(signal, signal) == pytest.approx(1.0)


def test_align_pair_trims_to_shorter() -> None:
    a = np.ones(10)
    b = np.ones(6)
    left, right = align_pair(a, b)
    assert left.size == right.size == 6


def test_duration_delta() -> None:
    assert duration_delta_sec(48_000, 48_024, 48_000) == pytest.approx(0.0005)
