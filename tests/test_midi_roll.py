from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from groovy.executor.cache import CacheStore
from groovy.nodes.ai.inference import audio_to_midi


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def _force_stub_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")


def test_cache_midi_roll_returns_notes(project_dir: Path) -> None:
    cache = CacheStore(project_dir)
    sr = 48_000
    pcm = np.sin(2 * np.pi * 440 * np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)).reshape(1, -1)
    midi, midi_bytes = audio_to_midi(pcm, sample_rate=sr, model_id="basic-pitch")
    cache.write_midi(midi, midi_bytes)

    roll = cache.midi_roll(midi.id)
    assert roll["midi_id"] == midi.id
    assert roll["duration"] > 0
    assert roll["min_pitch"] <= roll["max_pitch"]
    assert isinstance(roll["notes"], list)


def test_cache_midi_preview_wav_bytes(project_dir: Path) -> None:
    cache = CacheStore(project_dir)
    sr = 48_000
    pcm = np.sin(2 * np.pi * 440 * np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)).reshape(1, -1)
    midi, midi_bytes = audio_to_midi(pcm, sample_rate=sr, model_id="basic-pitch")
    cache.write_midi(midi, midi_bytes)

    wav = cache.midi_preview_wav_bytes(midi.id)
    assert wav.startswith(b"RIFF")
    assert cache.is_midi_cache(midi.id)
