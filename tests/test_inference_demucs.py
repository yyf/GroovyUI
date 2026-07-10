from __future__ import annotations

import numpy as np
import pytest

from groovy.nodes.ai.inference import _separate_stems_stub, separate_stems_audio


@pytest.fixture(autouse=True)
def _force_stub_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")


def test_separate_stems_stub_returns_four_stems() -> None:
    pcm = np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, 24_000, endpoint=False)).reshape(1, -1)
    stems = separate_stems_audio(pcm, sample_rate=48_000, model_id="demucs-v4")
    assert set(stems.keys()) == {"vocals", "drums", "bass", "other"}
    for stem in stems.values():
        assert stem.shape[0] == pcm.shape[0]
        assert stem.shape[1] == pcm.shape[1]


def test_separate_stems_respects_shifts_param_in_stub_path() -> None:
    pcm = np.random.default_rng(0).normal(size=(1, 4096))
    stems = separate_stems_audio(
        pcm,
        sample_rate=48_000,
        model_id="demucs-v4",
        shifts=2,
        overlap=0.5,
    )
    assert _separate_stems_stub(pcm, model_id="demucs-v4")["vocals"].shape == stems["vocals"].shape
