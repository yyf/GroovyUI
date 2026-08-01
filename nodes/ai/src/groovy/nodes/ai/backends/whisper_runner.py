from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy import signal

MODEL_ID_TO_WHISPER: dict[str, str] = {
    "whisper-large-v3-turbo": "large-v3-turbo",
    "whisper-small-en": "small.en",
}

WHISPER_SAMPLE_RATE = 16_000


@lru_cache(maxsize=2)
def _load_whisper(model_name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device="cpu", compute_type="int8")


def _to_mono_float32(pcm: np.ndarray) -> np.ndarray:
    if pcm.ndim == 1:
        return pcm.astype(np.float32)
    return pcm.mean(axis=0).astype(np.float32)


def _resample_mono(mono: np.ndarray, *, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return mono.astype(np.float32, copy=False)
    target_len = max(1, int(round(len(mono) * to_rate / from_rate)))
    return signal.resample(mono, target_len).astype(np.float32)


def transcribe_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    language: str = "en",
    temperature: float = 0.0,
) -> str:
    model_name = MODEL_ID_TO_WHISPER.get(model_id)
    if not model_name:
        raise RuntimeError(f"Unsupported whisper model: {model_id}")

    mono = _to_mono_float32(pcm)
    # faster-whisper assumes ndarray waveforms are already at 16 kHz (no resample).
    mono_16k = _resample_mono(mono, from_rate=int(sample_rate), to_rate=WHISPER_SAMPLE_RATE)

    model = _load_whisper(model_name)
    lang = None if language in {"", "auto"} else language
    segments, _ = model.transcribe(
        mono_16k,
        language=lang,
        temperature=float(temperature),
    )
    parts = [segment.text.strip() for segment in segments if segment.text.strip()]
    return " ".join(parts) if parts else ""
