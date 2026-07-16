from __future__ import annotations

import numpy as np

from groovy.nodes.ai.inference import (
    _energy_speaker_turns,
    _format_diarized_transcript,
    diarize_and_transcribe,
)


def test_energy_speaker_turns_alternates() -> None:
    sr = 16000
    # Two loud bursts separated by silence → two turns
    pcm = np.zeros(sr * 4, dtype=np.float64)
    pcm[0:sr] = 0.4 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, sr, endpoint=False))
    pcm[2 * sr : 3 * sr] = 0.4 * np.sin(2 * np.pi * 330 * np.linspace(0, 1, sr, endpoint=False))
    turns = _energy_speaker_turns(pcm, sample_rate=sr)
    assert len(turns) >= 2
    assert turns[0][2].startswith("SPEAKER_")
    assert turns[0][2] != turns[1][2]


def test_format_diarized_transcript_labels_sentences() -> None:
    text = _format_diarized_transcript(
        "Hello there. Second line here",
        [(0.0, 1.0, "SPEAKER_00"), (1.0, 2.0, "SPEAKER_01")],
        diarize_model="energy",
    )
    assert "SPEAKER_00" in text
    assert "SPEAKER_01" in text


def test_diarize_and_transcribe_stub_path(monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    sr = 16000
    pcm = 0.1 * np.sin(2 * np.pi * 440 * np.linspace(0, 1, sr, endpoint=False))
    text = diarize_and_transcribe(
        pcm.reshape(1, -1),
        sample_rate=sr,
        model_id="whisper-large-v3-turbo",
        diarize_model="pyannote-diarization-3.1",
    )
    assert "SPEAKER_" in text
    assert "whisper-large-v3-turbo" in text or "diarize=" in text
