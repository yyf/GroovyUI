"""Optional pyannote.audio diarization backend."""

from __future__ import annotations

from typing import Any

import numpy as np


def diarize_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str = "pyannote-diarization-3.1",
) -> list[tuple[float, float, str]]:
    """Return (start_s, end_s, speaker_id). Raises if pyannote is unavailable."""
    _ = model_id
    try:
        from pyannote.audio import Pipeline  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pyannote.audio is not installed") from exc

    if pcm.ndim == 1:
        wave = pcm.astype(np.float32)
    else:
        wave = pcm.mean(axis=0).astype(np.float32)

    # Hub id alias → pipeline checkpoint commonly used on Hub.
    pipeline_name = "pyannote/speaker-diarization-3.1"
    pipeline: Any = Pipeline.from_pretrained(pipeline_name)
    annotation = pipeline({"waveform": wave[None, :], "sample_rate": sample_rate})
    turns: list[tuple[float, float, str]] = []
    for segment, _, speaker in annotation.itertracks(yield_label=True):
        label = str(speaker).replace(" ", "_")
        if not label.startswith("SPEAKER_"):
            label = f"SPEAKER_{label}"
        turns.append((float(segment.start), float(segment.end), label))
    if not turns:
        duration = len(wave) / max(sample_rate, 1)
        return [(0.0, duration, "SPEAKER_00")]
    return turns
