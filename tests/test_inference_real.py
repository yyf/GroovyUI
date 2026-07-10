from __future__ import annotations

import os

import numpy as np
import pytest

from groovy.nodes.ai.inference import _audio_to_midi_stub, _midi_to_audio_stub, audio_to_midi, midi_to_audio_waveform
from groovy.executor.midi import MidiBuffer


@pytest.fixture(autouse=True)
def _force_stub_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")


def test_audio_to_midi_stub_writes_smf_bytes() -> None:
    sr = 48_000
    pcm = np.sin(2 * np.pi * 440 * np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)).reshape(1, -1)
    midi, midi_bytes = audio_to_midi(pcm, sample_rate=sr, model_id="basic-pitch")
    assert midi.id
    assert midi_bytes.startswith(b"MThd")
    assert midi.frame_count > 0


def test_midi_to_audio_stub_returns_audio() -> None:
    midi = MidiBuffer.create(sample_rate=48_000, frame_count=24_000, source_node_type="AudioToMIDI")
    pcm = midi_to_audio_waveform(midi, sample_rate=48_000, model_id="musicgen-melody-small", prompt="test")
    assert pcm.shape[0] == 1
    assert pcm.shape[1] > 0


def test_unsupported_model_errors_without_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    from groovy.nodes.ai import inference_env

    monkeypatch.delenv("GROOVY_INFERENCE_STUB", raising=False)
    monkeypatch.setattr(inference_env, "basic_pitch_available", lambda: False)
    pcm = np.zeros((1, 100))
    with pytest.raises(RuntimeError, match="Basic Pitch inference is not installed"):
        audio_to_midi(pcm, sample_rate=48_000, model_id="basic-pitch")
