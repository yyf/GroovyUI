from __future__ import annotations

import numpy as np
import pytest

from groovy.executor.audio import AudioBuffer
from groovy.executor.cache import CacheStore


def test_spectrogram_tiles_shape_and_db_range(tmp_path) -> None:
    cache = CacheStore(tmp_path / "cache")
    sr = 48_000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    tone = 0.4 * np.sin(2 * np.pi * 880 * t)
    pcm = tone.reshape(1, -1)
    buffer = AudioBuffer.from_planar(pcm, sr, source_node_type="Test")
    cache.write_audio(buffer, pcm)

    spec = cache.spectrogram_tiles(buffer.id, width=64, height=24)
    assert spec["width"] == 64
    assert spec["height"] == 24
    assert len(spec["values"]) == 64 * 24
    assert spec["duration"] == pytest.approx(0.5, abs=0.02)
    assert spec["max_db"] == 0.0
    assert spec["min_db"] == -72.0
    assert max(spec["values"]) <= 0.0
    assert min(spec["values"]) >= -72.0


def test_spectrogram_duration_matches_waveform(tmp_path) -> None:
    cache = CacheStore(tmp_path / "cache")
    sr = 48_000
    t = np.linspace(0, 0.75, int(sr * 0.75), endpoint=False)
    tone = 0.4 * np.sin(2 * np.pi * 440 * t)
    pcm = tone.reshape(1, -1)
    buffer = AudioBuffer.from_planar(pcm, sr, source_node_type="Test")
    cache.write_audio(buffer, pcm)

    width = 128
    wave = cache.waveform_peaks(buffer.id, width=width)
    spec = cache.spectrogram_tiles(buffer.id, width=width, height=32)
    assert wave["duration"] == pytest.approx(spec["duration"], abs=1e-6)


def test_spectrogram_time_axis_aligns_with_signal(tmp_path) -> None:
    cache = CacheStore(tmp_path / "cache")
    sr = 48_000
    duration = 1.0
    frames = int(sr * duration)
    mono = np.zeros(frames, dtype=np.float64)
    start = int(frames * 0.75)
    t = np.linspace(0, 0.2, frames - start, endpoint=False)
    mono[start:] = 0.5 * np.sin(2 * np.pi * 440 * t)
    pcm = mono.reshape(1, -1)
    buffer = AudioBuffer.from_planar(pcm, sr, source_node_type="Test")
    cache.write_audio(buffer, pcm)

    width = 128
    spec = cache.spectrogram_tiles(buffer.id, width=width, height=32)
    grid = np.asarray(spec["values"], dtype=np.float64).reshape(spec["height"], spec["width"])
    col_energy = np.power(10.0, grid.mean(axis=0) / 20.0)
    peak_col = int(np.argmax(col_energy))
    assert peak_col >= int(width * 0.65)
