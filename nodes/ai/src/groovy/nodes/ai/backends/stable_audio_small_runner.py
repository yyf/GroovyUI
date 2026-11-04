"""Stable Audio Open Small (stabilityai/stable-audio-open-small) via stable-audio-tools."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import signal

HF_MODEL_ID = "stabilityai/stable-audio-open-small"
NATIVE_SAMPLE_RATE = 44_100
# Model card: variable length up to ~11s; keep demos short.
MAX_SECONDS = 11.0


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


@lru_cache(maxsize=1)
def _load_model():
    token = _resolve_hf_token()
    if not token:
        raise RuntimeError(
            "Stable Audio Open Small is gated on Hugging Face. "
            "Save an HF token in Settings (or set HF_TOKEN), accept the model license, then retry."
        )
    # stable-audio-tools / huggingface_hub read HF_TOKEN from the environment.
    os.environ.setdefault("HF_TOKEN", token)
    os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)

    try:
        import torch
        from stable_audio_tools import get_pretrained_model
    except ImportError as exc:
        raise RuntimeError(
            "stable-audio-tools is not installed. "
            "Install stable-audio-open-small from Model Browser (Cmd+K)."
        ) from exc

    try:
        model, model_config = get_pretrained_model(HF_MODEL_ID)
    except Exception as exc:
        message = str(exc)
        if "restricted" in message.lower() or "401" in message or "403" in message:
            raise RuntimeError(
                f"Hugging Face denied access to {HF_MODEL_ID}. "
                "Confirm the license is accepted on the model page while logged into the same "
                "account as your token, and that the token has access to gated repos."
            ) from exc
        raise

    device = "cuda" if torch.cuda.is_available() else "cpu"
    # float16 VAE decode is painfully slow on CPU; keep fp32 off CUDA.
    if device == "cpu":
        model = model.to(device).float()
    else:
        model = model.to(device)
    model.eval()
    return model, model_config, device


def generate_from_text(
    prompt: str,
    *,
    sample_rate: int,
    seconds_total: float = 8.0,
    num_inference_steps: int = 8,
    guidance_scale: float = 1.0,
    seed: int | None = None,
) -> np.ndarray:
    import torch
    from einops import rearrange
    from stable_audio_tools.inference.generation import generate_diffusion_cond

    model, model_config, device = _load_model()
    native_sr = int(model_config.get("sample_rate") or NATIVE_SAMPLE_RATE)
    sample_size = int(model_config["sample_size"])
    duration = float(np.clip(seconds_total, 1.0, MAX_SECONDS))

    conditioning = [
        {
            "prompt": prompt or "soft ambient texture",
            "seconds_total": duration,
        }
    ]

    seed_kw: dict = {}
    if seed is not None and seed >= 0:
        seed_kw["seed"] = int(seed) % (2**31 - 1)

    with torch.inference_mode():
        output = generate_diffusion_cond(
            model,
            steps=max(4, int(num_inference_steps)),
            cfg_scale=float(guidance_scale),
            conditioning=conditioning,
            sample_size=sample_size,
            sampler_type="pingpong",
            device=device,
            **seed_kw,
        )

    # (batch, channels, samples) → (channels, samples)
    output = rearrange(output, "b d n -> d (b n)")
    pcm = output.detach().float().cpu().numpy().astype(np.float64)
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)

    # Trim to requested duration (model may allocate full sample_size).
    target_frames = max(1, int(round(duration * native_sr)))
    if pcm.shape[-1] > target_frames:
        pcm = pcm[:, :target_frames]

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
