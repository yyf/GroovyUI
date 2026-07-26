"""Text-conditioned Stable Audio Open (stabilityai/stable-audio-open-1.0) via diffusers."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from scipy import signal

HF_MODEL_ID = "stabilityai/stable-audio-open-1.0"
NATIVE_SAMPLE_RATE = 44_100


def _resolve_hf_token() -> str | None:
    """Prefer env, then project Settings (same precedence as StudioSettingsStore)."""
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


def _use_stable_scheduler(pipe):
    """Replace CosineDPM (BrownianTree/torchsde) — can RecursionError on several backends.

    See huggingface/diffusers#13274. ODE DPMSolver++ avoids the SDE noise sampler.
    """
    from diffusers import DPMSolverMultistepScheduler

    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    return pipe


@lru_cache(maxsize=1)
def _load_pipeline():
    try:
        from diffusers import StableAudioPipeline
    except ImportError as exc:
        raise RuntimeError(
            "diffusers is not installed. Install stable-audio-open-1.0 from Model Browser (Cmd+K)."
        ) from exc

    token = _resolve_hf_token()
    if not token:
        raise RuntimeError(
            "Stable Audio Open is gated on Hugging Face. "
            "Save an HF token in Settings (or set HF_TOKEN), accept the model license, then retry."
        )

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    dtype = torch.float16 if device == "cuda" else torch.float32
    try:
        pipe = StableAudioPipeline.from_pretrained(
            HF_MODEL_ID,
            torch_dtype=dtype,
            token=token,
        )
    except Exception as exc:
        message = str(exc)
        if "restricted" in message.lower() or "401" in message or "403" in message:
            raise RuntimeError(
                "Hugging Face denied access to stabilityai/stable-audio-open-1.0. "
                "Confirm the license is accepted on the model page while logged into the same "
                "account as your token, and that the token has access to gated repos."
            ) from exc
        raise
    pipe = _use_stable_scheduler(pipe)
    pipe = pipe.to(device)
    return pipe, device


def generate_from_text(
    prompt: str,
    *,
    sample_rate: int,
    seconds_total: float = 10.0,
    num_inference_steps: int = 100,
    guidance_scale: float = 7.0,
    negative_prompt: str = "Low quality.",
    seed: int | None = None,
) -> np.ndarray:
    pipe, device = _load_pipeline()
    duration = float(np.clip(seconds_total, 1.0, 47.0))
    generator = None
    if seed is not None and seed >= 0:
        # Diffusers generators on MPS/CPU expect CPU; CUDA can use CUDA generator.
        gen_device = "cuda" if device == "cuda" else "cpu"
        generator = torch.Generator(device=gen_device).manual_seed(int(seed) % (2**63 - 1))

    try:
        result = pipe(
            prompt or "ambient music",
            negative_prompt=negative_prompt or None,
            audio_end_in_s=duration,
            num_inference_steps=max(8, int(num_inference_steps)),
            guidance_scale=float(guidance_scale),
            num_waveforms_per_prompt=1,
            generator=generator,
        )
    except RecursionError as exc:
        raise RuntimeError(
            "Stable Audio sampler hit a known CosineDPM/torchsde recursion bug. "
            "Retry after restarting the API (GroovyUI switches to DPMSolver++)."
        ) from exc
    audio = result.audios[0]
    # diffusers returns [channels, samples] float tensor/array
    if hasattr(audio, "detach"):
        pcm = audio.detach().float().cpu().numpy()
    else:
        pcm = np.asarray(audio, dtype=np.float64)
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    native_sr = int(getattr(getattr(pipe, "vae", None), "sampling_rate", None) or NATIVE_SAMPLE_RATE)
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
