"""ACE-Step GenerateAudio reference_audio → identity-preserving cover."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np


def _stub_torch_free_cover(monkeypatch, runner) -> None:
    """CI has no torch; cover only needs a shape-bearing src_audio stand-in."""
    monkeypatch.setattr(
        runner,
        "_to_torch_audio",
        lambda pcm, *, device: np.asarray(pcm, dtype=np.float32),
    )


def test_ace_step_cover_keeps_source_identity_and_length(monkeypatch) -> None:
    from groovy.nodes.ai.backends import ace_step_runner as runner

    pipe = MagicMock()
    pipe.sample_rate = 48_000
    pipe.return_value = SimpleNamespace(
        audios=[np.zeros((2, 24_000), dtype=np.float32)]
    )
    monkeypatch.setattr(runner, "_load_pipeline", lambda _hf: (pipe, "cpu"))
    monkeypatch.setattr(runner, "_load_lora", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_unload_lora", lambda *_: None)
    _stub_torch_free_cover(monkeypatch, runner)

    ref = np.random.randn(2, 24_000).astype(np.float32) * 0.1  # 0.5s @ 48k
    out = runner.generate_from_text(
        "Cyberpunk ambient score with heavier drone presence",
        sample_rate=48_000,
        model_id="ace-step-1.5-2b-turbo",
        seconds_total=0.5,  # match source — do not force 10s bed
        num_inference_steps=8,
        guidance_scale=1.0,
        reference_pcm=ref,
        reference_sample_rate=48_000,
        audio_cover_strength=0.85,
    )
    assert out.ndim == 2
    assert out.shape[-1] == 24_000
    kwargs = pipe.call_args.kwargs
    assert kwargs["task_type"] == "cover"
    assert "src_audio" in kwargs
    # Timbre must not lock to the source clip — leave Diffusers reference_audio unset
    # so the prompt can restyle.
    assert "reference_audio" not in kwargs
    assert tuple(kwargs["src_audio"].shape) == (2, 24_000)
    assert kwargs["audio_duration"] == 0.5
    assert kwargs["audio_cover_strength"] == 0.85


def test_ace_step_cover_strength_default(monkeypatch) -> None:
    from groovy.nodes.ai.backends import ace_step_runner as runner

    pipe = MagicMock()
    pipe.sample_rate = 48_000
    pipe.return_value = SimpleNamespace(
        audios=[np.zeros((1, 48_000), dtype=np.float32)]
    )
    monkeypatch.setattr(runner, "_load_pipeline", lambda _hf: (pipe, "cpu"))
    _stub_torch_free_cover(monkeypatch, runner)
    ref = np.random.randn(1, 48_000).astype(np.float32) * 0.05
    runner.generate_from_text(
        "pad",
        sample_rate=48_000,
        model_id="ace-step-1.5-2b-turbo",
        seconds_total=1.0,
        reference_pcm=ref,
        reference_sample_rate=48_000,
    )
    assert pipe.call_args.kwargs["audio_cover_strength"] == 0.92


def test_ace_step_generate_text2music_without_reference(monkeypatch) -> None:
    from groovy.nodes.ai.backends import ace_step_runner as runner

    pipe = MagicMock()
    pipe.sample_rate = 48_000
    pipe.return_value = SimpleNamespace(
        audios=[np.zeros((1, 48_000), dtype=np.float32)]
    )
    monkeypatch.setattr(runner, "_load_pipeline", lambda _hf: (pipe, "cpu"))

    runner.generate_from_text(
        "beat",
        sample_rate=48_000,
        model_id="ace-step-1.5-2b-turbo",
        seconds_total=10.0,
        reference_pcm=np.zeros((1, 0), dtype=np.float32),
        reference_sample_rate=48_000,
    )
    kwargs = pipe.call_args.kwargs
    assert kwargs["task_type"] == "text2music"
    assert "src_audio" not in kwargs
    assert "reference_audio" not in kwargs
