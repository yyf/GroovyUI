"""ACE-Step 1.5 text-to-music via diffusers AceStepPipeline."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from scipy import signal

# XL hero pack (~11GB) vs smallest Diffusers 2B turbo (~6.3GB).
HF_BY_MODEL_ID: dict[str, str] = {
    "ace-step-1.5": "ACE-Step/acestep-v15-xl-turbo-diffusers",
    "ace-step-1.5-2b-turbo": "Runware/acestep-v15-turbo-diffusers",
}
NATIVE_SAMPLE_RATE = 48_000


def _prefer_classic_hf_download() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


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


def _hf_model_id(model_id: str) -> str:
    try:
        return HF_BY_MODEL_ID[model_id]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported ACE-Step model id: {model_id}") from exc


@lru_cache(maxsize=2)
def _load_pipeline(hf_model_id: str):
    _prefer_classic_hf_download()
    try:
        from diffusers import AceStepPipeline
    except ImportError as exc:
        raise RuntimeError(
            "diffusers AceStepPipeline is missing. "
            "Install ace-step-1.5 or ace-step-1.5-2b-turbo from Model Browser (Cmd+K) "
            "(requires diffusers >= 0.39 with AceStepPipeline)."
        ) from exc

    token = _resolve_hf_token()
    # Prefer CUDA; skip MPS — large DiT + Metal dtype bugs (same class as MusicGen/AF3).
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    else:
        dtype = torch.float32

    try:
        pipe = AceStepPipeline.from_pretrained(
            hf_model_id,
            torch_dtype=dtype,
            token=token,
        )
    except Exception as exc:
        message = str(exc)
        if "Background writer channel closed" in message or "File reconstruction error" in message:
            raise RuntimeError(
                f"Hugging Face download failed while fetching {hf_model_id} "
                "(often HF Xet on macOS, disk full, or interrupted transfer). "
                "Free disk space, set HF_HUB_DISABLE_XET=1, clear the partial HF cache, then retry."
            ) from exc
        if "restricted" in message.lower() or "401" in message or "403" in message:
            raise RuntimeError(
                f"Hugging Face denied access to {hf_model_id}. "
                "Confirm the repo is visible and any required token is valid."
            ) from exc
        raise

    pipe = pipe.to(device)
    # Bound VAE decode memory for longer clips.
    if hasattr(getattr(pipe, "vae", None), "enable_tiling"):
        pipe.vae.enable_tiling()
    return pipe, device


def generate_from_text(
    prompt: str,
    *,
    sample_rate: int,
    model_id: str = "ace-step-1.5",
    seconds_total: float = 15.0,
    num_inference_steps: int = 8,
    guidance_scale: float = 1.0,
    lyrics: str = "",
    seed: int | None = None,
) -> np.ndarray:
    pipe, device = _load_pipeline(_hf_model_id(model_id))
    # Model supports ~10s–10min; keep hero demos short.
    duration = float(np.clip(seconds_total, 10.0, 120.0))
    generator = None
    if seed is not None and seed >= 0:
        gen_device = "cuda" if device == "cuda" else "cpu"
        generator = torch.Generator(device=gen_device).manual_seed(int(seed) % (2**63 - 1))

    result = pipe(
        prompt or "upbeat instrumental lo-fi beat",
        lyrics=lyrics or "",
        audio_duration=duration,
        num_inference_steps=max(4, int(num_inference_steps)),
        guidance_scale=float(guidance_scale),
        generator=generator,
        task_type="text2music",
    )
    audio = result.audios[0]
    if hasattr(audio, "detach"):
        pcm = audio.detach().float().cpu().numpy()
    else:
        pcm = np.asarray(audio, dtype=np.float64)
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    native_sr = int(getattr(pipe, "sample_rate", None) or NATIVE_SAMPLE_RATE)
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
