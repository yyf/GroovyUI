"""Optional VoxCPM2 TTS backend (OpenBMB / openbmb/VoxCPM2)."""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

HF_MODEL_ID = "openbmb/VoxCPM2"
NATIVE_SAMPLE_RATE = 48_000


@lru_cache(maxsize=1)
def _load_model():
    try:
        from voxcpm import VoxCPM  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "voxcpm is not installed. Install voxcpm2 from Model Browser (Cmd+K)."
        ) from exc
    # Denoiser off keeps first-load lighter; callers can still pass clean reference clips.
    return VoxCPM.from_pretrained(HF_MODEL_ID, load_denoiser=False)


def synthesize_pcm(
    text: str,
    *,
    sample_rate: int = 48000,
    reference_pcm: np.ndarray | None = None,
    reference_sample_rate: int | None = None,
    reference_text: str = "",
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
) -> np.ndarray:
    """Synthesize mono speech with VoxCPM2 (voice design / TTS / optional clone).

    Voice design: put a parenthetical description at the start of ``text``, e.g.
    ``(A calm narrator, warm tone)Hello from GroovyUI.``
    """
    source = (text or "").strip()
    if not source:
        raise RuntimeError("VoxCPM2 requires non-empty text")

    model = _load_model()
    gen_kwargs: dict = {
        "text": source,
        "cfg_value": float(cfg_value),
        "inference_timesteps": int(inference_timesteps),
    }

    with tempfile.TemporaryDirectory(prefix="groovy-voxcpm2-") as tmp:
        if reference_pcm is not None and reference_pcm.size:
            mono = reference_pcm.astype(np.float64)
            if mono.ndim > 1:
                mono = mono.mean(axis=0)
            peak = float(np.max(np.abs(mono))) if mono.size else 0.0
            if peak > 1e-8:
                mono = mono / peak * 0.9
            ref_path = Path(tmp) / "reference.wav"
            ref_sr = int(reference_sample_rate or sample_rate or NATIVE_SAMPLE_RATE)
            sf.write(str(ref_path), mono, ref_sr)
            gen_kwargs["reference_wav_path"] = str(ref_path)
            prompt = (reference_text or "").strip()
            if prompt:
                # Ultimate cloning: same clip as prompt + reference with transcript.
                gen_kwargs["prompt_wav_path"] = str(ref_path)
                gen_kwargs["prompt_text"] = prompt

        wav = model.generate(**gen_kwargs)

    mono_out = np.asarray(wav, dtype=np.float64)
    if mono_out.ndim > 1:
        mono_out = mono_out.mean(axis=0)
    try:
        native_sr = int(getattr(model.tts_model, "sample_rate", NATIVE_SAMPLE_RATE))
    except Exception:
        native_sr = NATIVE_SAMPLE_RATE
    if sample_rate != native_sr:
        from scipy import signal

        mono_out = signal.resample(mono_out, int(len(mono_out) * sample_rate / native_sr))
    peak_out = float(np.max(np.abs(mono_out))) if mono_out.size else 0.0
    if peak_out > 1e-8:
        mono_out = mono_out / peak_out * 0.9
    return mono_out.reshape(1, -1)
