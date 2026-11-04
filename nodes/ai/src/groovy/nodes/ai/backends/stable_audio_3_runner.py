"""Stable Audio 3 Small Music / SFX via the official stable-audio-3 package."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import signal

# Short names accepted by StableAudioModel.from_pretrained.
MODEL_NAME_BY_ID: dict[str, str] = {
    "stable-audio-3-small-music": "small-music",
    "stable-audio-3-small-sfx": "small-sfx",
}
NATIVE_SAMPLE_RATE = 44_100
MAX_SECONDS = 120.0


def _resolve_hf_token() -> str | None:
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        env = os.environ.get(key, "").strip()
        if env:
            return env
    project = os.environ.get("GROOVY_PROJECT_DIR", "").strip()
    if not project:
        return None
    try:
        from groovy.registry.studio_settings import StudioSettingsStore

        return StudioSettingsStore(Path(project)).hf_token()
    except Exception:
        return None


def _ensure_hf_token() -> None:
    token = _resolve_hf_token()
    if not token:
        raise RuntimeError(
            "Stable Audio 3 is gated on Hugging Face. "
            "Save an HF token in Settings (or set HF_TOKEN), accept the model license "
            "(and Gemma Terms of Use), then retry."
        )
    os.environ.setdefault("HF_TOKEN", token)
    os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)


@lru_cache(maxsize=2)
def _load_model(sa3_name: str):
    _ensure_hf_token()
    try:
        from stable_audio_3 import StableAudioModel
    except ImportError as exc:
        raise RuntimeError(
            "stable-audio-3 is not installed. "
            "Install stable-audio-3-small-music or stable-audio-3-small-sfx "
            "from Model Browser (Cmd+K)."
        ) from exc

    try:
        # from_pretrained picks cuda → mps → cpu; model_half=False on non-CUDA.
        return StableAudioModel.from_pretrained(sa3_name)
    except Exception as exc:
        message = str(exc)
        if "401" in message or "403" in message or "gated" in message.lower():
            raise RuntimeError(
                f"Hugging Face denied access to Stable Audio 3 ({sa3_name}). "
                "Accept the Community license on the model page with the same account "
                "as your token, then retry."
            ) from exc
        raise


def generate_from_text(
    prompt: str,
    *,
    sample_rate: int,
    model_id: str = "stable-audio-3-small-music",
    seconds_total: float = 8.0,
    num_inference_steps: int = 8,
    guidance_scale: float = 1.0,
    negative_prompt: str = "",
    seed: int | None = None,
) -> np.ndarray:
    try:
        sa3_name = MODEL_NAME_BY_ID[model_id]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported Stable Audio 3 model id: {model_id}") from exc

    wrapper = _load_model(sa3_name)
    duration = float(np.clip(seconds_total, 1.0, MAX_SECONDS))
    seed_val = int(seed) if seed is not None and seed >= 0 else -1

    audio = wrapper.generate(
        prompt=prompt or ("soft ambient bed" if "music" in sa3_name else "subtle whoosh"),
        negative_prompt=negative_prompt or None,
        duration=duration,
        steps=max(4, int(num_inference_steps)),
        cfg_scale=float(guidance_scale),
        seed=seed_val,
        truncate_output_to_duration=True,
    )

    # (batch, channels, samples)
    if hasattr(audio, "detach"):
        pcm = audio.detach().float().cpu().numpy()
    else:
        pcm = np.asarray(audio, dtype=np.float64)
    if pcm.ndim == 3:
        pcm = pcm[0]
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)

    native_sr = int(getattr(wrapper.model, "sample_rate", None) or NATIVE_SAMPLE_RATE)
    if sample_rate != native_sr:
        target_len = max(1, int(pcm.shape[-1] * sample_rate / native_sr))
        pcm = np.stack(
            [signal.resample(ch, target_len).astype(np.float64) for ch in pcm],
            axis=0,
        )

    peak = float(np.max(np.abs(pcm))) if pcm.size else 0.0
    if peak > 1.0:
        pcm = pcm / peak
    return pcm.astype(np.float64)
