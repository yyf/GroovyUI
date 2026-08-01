from __future__ import annotations

import numpy as np

from groovy.nodes.ai.backends.whisper_runner import WHISPER_SAMPLE_RATE, transcribe_pcm


class _FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeWhisper:
    def __init__(self) -> None:
        self.last_audio: np.ndarray | None = None
        self.last_kwargs: dict | None = None

    def transcribe(self, audio, **kwargs):
        self.last_audio = np.asarray(audio)
        self.last_kwargs = kwargs
        return [_FakeSegment("hello world")], None


def test_transcribe_pcm_resamples_ndarray_to_16k(monkeypatch):
    """faster-whisper treats ndarray input as 16 kHz; we must resample first."""
    fake = _FakeWhisper()
    monkeypatch.setattr(
        "groovy.nodes.ai.backends.whisper_runner._load_whisper",
        lambda _name: fake,
    )

    sample_rate = 44_100
    duration_s = 1.0
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    pcm = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    text = transcribe_pcm(
        pcm,
        sample_rate=sample_rate,
        model_id="whisper-large-v3-turbo",
        language="en",
    )

    assert text == "hello world"
    assert fake.last_audio is not None
    # 1s @ 44.1k → ~16k samples at Whisper rate
    assert abs(len(fake.last_audio) - WHISPER_SAMPLE_RATE) <= 2
    assert abs(len(fake.last_audio) / WHISPER_SAMPLE_RATE - duration_s) < 0.01


def test_transcribe_pcm_keeps_16k_length(monkeypatch):
    fake = _FakeWhisper()
    monkeypatch.setattr(
        "groovy.nodes.ai.backends.whisper_runner._load_whisper",
        lambda _name: fake,
    )

    pcm = np.zeros(WHISPER_SAMPLE_RATE, dtype=np.float32)
    transcribe_pcm(
        pcm,
        sample_rate=WHISPER_SAMPLE_RATE,
        model_id="whisper-small-en",
        language="en",
    )
    assert fake.last_audio is not None
    assert len(fake.last_audio) == WHISPER_SAMPLE_RATE
