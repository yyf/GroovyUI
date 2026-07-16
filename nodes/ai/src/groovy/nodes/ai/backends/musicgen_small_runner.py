"""Text-conditioned MusicGen (facebook/musicgen-small)."""

from __future__ import annotations

import contextlib
import io
from functools import lru_cache

import numpy as np
import torch
from scipy import signal
from transformers import AutoProcessor, MusicgenForConditionalGeneration

NATIVE_SAMPLE_RATE = 32_000
HF_MODEL_ID = "facebook/musicgen-small"


@lru_cache(maxsize=1)
def _load_musicgen_small() -> tuple[AutoProcessor, MusicgenForConditionalGeneration, str]:
    processor = AutoProcessor.from_pretrained(HF_MODEL_ID)
    model = MusicgenForConditionalGeneration.from_pretrained(HF_MODEL_ID)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    return processor, model, device


def generate_from_text(
    prompt: str,
    *,
    sample_rate: int,
    max_new_tokens: int = 512,
    guidance_scale: float = 3.0,
    temperature: float = 1.0,
) -> np.ndarray:
    processor, model, device = _load_musicgen_small()
    inputs = processor(
        text=[prompt or "ambient music"],
        padding=True,
        return_tensors="pt",
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}

    with torch.no_grad():
        with contextlib.redirect_stdout(io.StringIO()):
            generate_kwargs: dict[str, object] = {
                "max_new_tokens": max(64, int(max_new_tokens)),
                "guidance_scale": float(guidance_scale),
            }
            if temperature > 0:
                generate_kwargs["do_sample"] = True
                generate_kwargs["temperature"] = float(temperature)
            generated = model.generate(**inputs, **generate_kwargs)

    waveform = generated[0, 0].detach().cpu().numpy().astype(np.float64)
    if sample_rate != NATIVE_SAMPLE_RATE:
        target_len = max(1, int(len(waveform) * sample_rate / NATIVE_SAMPLE_RATE))
        waveform = signal.resample(waveform, target_len).astype(np.float64)
    peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
    if peak > 1.0:
        waveform = waveform / peak
    return waveform.reshape(1, -1)
