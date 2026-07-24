from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf

from groovy.executor.audio import AudioBuffer
from groovy.executor.cache import CacheStore


def test_preview_wav_stereo_duration_matches_waveform(tmp_path) -> None:
    """Stereo preview must stay multi-channel — flattening to mono doubles duration."""
    cache = CacheStore(tmp_path / "cache")
    sr = 44_100
    frames = sr * 2  # 2 seconds
    pcm = np.stack(
        [
            0.2 * np.sin(2 * np.pi * 440 * np.arange(frames) / sr),
            0.2 * np.sin(2 * np.pi * 660 * np.arange(frames) / sr),
        ]
    )
    buffer = AudioBuffer.from_planar(pcm, sr, source_node_type="Test")
    cache.write_audio(buffer, pcm)

    wave = cache.waveform_peaks(buffer.id, width=64)
    assert wave["duration"] == pytest.approx(2.0, abs=1e-3)

    wav_bytes = cache.preview_wav_bytes(buffer.id)
    data, file_sr = sf.read(io.BytesIO(wav_bytes), always_2d=True)
    assert file_sr == sr
    assert data.shape == (frames, 2)
    assert data.shape[0] / file_sr == pytest.approx(wave["duration"], abs=1e-3)
