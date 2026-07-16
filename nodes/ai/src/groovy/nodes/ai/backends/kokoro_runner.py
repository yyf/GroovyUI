"""Optional Kokoro TTS backend (hexgrad/Kokoro-82M)."""

from __future__ import annotations

import numpy as np


def synthesize_pcm(text: str, *, sample_rate: int = 48000) -> np.ndarray:
    """Synthesize mono speech; raises if kokoro package is unavailable."""
    try:
        from kokoro import KPipeline  # type: ignore
    except ImportError as exc:
        raise RuntimeError("kokoro package is not installed") from exc

    pipeline = KPipeline(lang_code="a")
    chunks: list[np.ndarray] = []
    native_sr = 24000
    for _gs, _ps, audio in pipeline(text, voice="af_heart"):
        chunks.append(np.asarray(audio, dtype=np.float64))
    if not chunks:
        raise RuntimeError("Kokoro returned empty audio")
    mono = np.concatenate(chunks)
    if sample_rate != native_sr:
        from scipy import signal

        mono = signal.resample(mono, int(len(mono) * sample_rate / native_sr))
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    if peak > 1e-8:
        mono = mono / peak * 0.9
    return mono.reshape(1, -1)
