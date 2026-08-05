"""SeamlessM4T speech-to-speech translation (Meta)."""

from __future__ import annotations

from functools import lru_cache
from math import gcd

import numpy as np
from scipy import signal

HF_MODEL_ID = "facebook/seamless-m4t-v2-large"
SEAMLESS_SAMPLE_RATE = 16_000

# Accept ISO 639-1 and common aliases → Seamless ISO 639-3 style codes.
_LANG_ALIASES: dict[str, str] = {
    "en": "eng",
    "eng": "eng",
    "es": "spa",
    "spa": "spa",
    "fr": "fra",
    "fra": "fra",
    "de": "deu",
    "deu": "deu",
    "pt": "por",
    "por": "por",
    "it": "ita",
    "ita": "ita",
    "nl": "nld",
    "nld": "nld",
    "ru": "rus",
    "rus": "rus",
    "zh": "cmn",
    "cmn": "cmn",
    "ja": "jpn",
    "jpn": "jpn",
    "ko": "kor",
    "kor": "kor",
    "ar": "arb",
    "arb": "arb",
    "hi": "hin",
    "hin": "hin",
}


def normalize_lang(code: str, *, default: str = "eng") -> str:
    raw = (code or default).strip().lower().replace("_", "-")
    if not raw:
        return default
    # zh-cn → cmn; es-mx → spa
    primary = raw.split("-", 1)[0]
    return _LANG_ALIASES.get(primary, primary if len(primary) == 3 else default)


def _to_mono(pcm: np.ndarray) -> np.ndarray:
    if pcm.ndim == 1:
        return pcm.astype(np.float32)
    return pcm.mean(axis=0).astype(np.float32)


def _resample(mono: np.ndarray, *, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate or mono.size == 0:
        return mono.astype(np.float32, copy=False)
    g = gcd(int(to_rate), int(from_rate))
    return signal.resample_poly(mono.astype(np.float64), to_rate // g, from_rate // g).astype(
        np.float32
    )


@lru_cache(maxsize=1)
def _load_seamless() -> tuple[object, object, str]:
    import torch
    from transformers import AutoProcessor, SeamlessM4Tv2Model

    processor = AutoProcessor.from_pretrained(HF_MODEL_ID)
    model = SeamlessM4Tv2Model.from_pretrained(HF_MODEL_ID)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    return processor, model, device


def translate_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    src_lang: str = "eng",
    tgt_lang: str = "spa",
    speaker_id: int = 0,
) -> np.ndarray:
    """Speech-to-speech translate; returns planar AUDIO at the input sample rate."""
    import torch

    src = normalize_lang(src_lang, default="eng")
    tgt = normalize_lang(tgt_lang, default="spa")
    mono = _to_mono(pcm)
    mono_16k = _resample(mono, from_rate=int(sample_rate), to_rate=SEAMLESS_SAMPLE_RATE)

    processor, model, device = _load_seamless()
    inputs = processor(audio=mono_16k, sampling_rate=SEAMLESS_SAMPLE_RATE, return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}

    spk = max(0, min(199, int(speaker_id)))
    with torch.no_grad():
        # SeamlessM4Tv2.generate: tgt_lang + speaker_id (vocoder voice). No gender enum;
        # source language is inferred from speech. speaker_id does not clone the input speaker.
        _ = src
        generated = model.generate(**inputs, tgt_lang=tgt, speaker_id=spk)

    waveform = generated[0].detach().float().cpu().numpy().reshape(-1)
    out = _resample(waveform.astype(np.float32), from_rate=SEAMLESS_SAMPLE_RATE, to_rate=int(sample_rate))
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 0.95:
        out = out * (0.95 / peak)
    return out.reshape(1, -1)
