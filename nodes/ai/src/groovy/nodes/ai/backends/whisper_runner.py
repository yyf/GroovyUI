from __future__ import annotations

from functools import lru_cache

import numpy as np

MODEL_ID_TO_WHISPER: dict[str, str] = {
    "whisper-large-v3-turbo": "large-v3-turbo",
    "whisper-small-en": "small.en",
}


@lru_cache(maxsize=2)
def _load_whisper(model_name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device="cpu", compute_type="int8")


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

    if pcm.ndim == 1:
        mono = pcm.astype(np.float32)
    else:
        mono = pcm.mean(axis=0).astype(np.float32)

    model = _load_whisper(model_name)
    lang = None if language in {"", "auto"} else language
    segments, _ = model.transcribe(
        mono,
        language=lang,
        temperature=float(temperature),
    )
    parts = [segment.text.strip() for segment in segments if segment.text.strip()]
    return " ".join(parts) if parts else ""
