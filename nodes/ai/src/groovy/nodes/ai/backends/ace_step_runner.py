"""ACE-Step 1.5 text-to-music via diffusers AceStepPipeline."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import NoReturn

import numpy as np
from scipy import signal

# XL turbo (~11GB), 2B SFT (CFG, ~50 steps, ~6.3GB), 2B turbo (~6.3GB).
# Demo SFT uses the 2B pack — XL SFT (~5B / ~12GB) OOMs many Macs on CPU.
HF_BY_MODEL_ID: dict[str, str] = {
    "ace-step-1.5": "ACE-Step/acestep-v15-xl-turbo-diffusers",
    "ace-step-1.5-sft": "Runware/acestep-v15-sft-diffusers",
    "ace-step-1.5-2b-turbo": "Runware/acestep-v15-turbo-diffusers",
}
# Registry LoRA ids → Hub adapters (load via Diffusers PEFT; unload after generate).
LORA_HF_BY_ID: dict[str, str] = {
    "ace-step-cny-lora": "ACE-Step/ACE-Step-v1.5-chinese-new-year-LoRA",
    "ace-step-ambient-lora": "DisturbingTheField/ACE-Step-v1.5-ambient_dream1-LoRA",
}
_LORA_ADAPTER_NAME = "groovy"
# Turbo packs are guidance-distilled; SFT uses CFG / APG (guidance_scale matters).
ACE_STEP_SFT_MODEL_IDS = frozenset({"ace-step-1.5-sft"})
ACE_STEP_TURBO_MODEL_IDS = frozenset({"ace-step-1.5", "ace-step-1.5-2b-turbo"})
ACE_STEP_MODEL_IDS = frozenset(HF_BY_MODEL_ID)
NATIVE_SAMPLE_RATE = 48_000
# CPU float32 DiT + activations thrash Macs under this *available* (not total) RAM floor.
# Available = free + reclaimable; a 16 GB Mac often shows ~10–13 GB with Studio open.
# Override with GROOVY_ACE_STEP_MIN_RAM_GB=… or GROOVY_ACE_STEP_ALLOW_LOW_RAM=1.
_DEFAULT_CPU_MIN_AVAILABLE_RAM_GB = {
    "ACE-Step/acestep-v15-xl-turbo-diffusers": 16.0,
    "Runware/acestep-v15-sft-diffusers": 12.0,
    "Runware/acestep-v15-turbo-diffusers": 12.0,
}

_HF_TOKEN_RE = re.compile(r"hf_[A-Za-z0-9]+")
_ACCESS_NEEDLES = (
    "401 client error",
    "403 client error",
    "401 unauthorized",
    "403 forbidden",
    "access to model",
    "cannot access gated",
    "gated repo",
    "repository not found",
    "access denied",
)


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


def _hf_token_arg(token: str | None) -> str | bool:
    """False = anonymous. None would inherit a broken huggingface-cli login."""
    return token if token else False


def _sanitize_hf_error(message: str) -> str:
    cleaned = _HF_TOKEN_RE.sub("hf_[redacted]", message)
    return " ".join(cleaned.split())[:400]


def _http_status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _is_hf_access_denied(exc: BaseException) -> bool:
    if type(exc).__name__ in {"GatedRepoError", "RepositoryNotFoundError"}:
        return True
    if _http_status(exc) in {401, 403}:
        return True
    lowered = str(exc).lower()
    return any(needle in lowered for needle in _ACCESS_NEEDLES)


def _is_hf_xet_failure(message: str) -> bool:
    return "Background writer channel closed" in message or "File reconstruction error" in message


def _hf_model_id(model_id: str) -> str:
    try:
        return HF_BY_MODEL_ID[model_id]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported ACE-Step model id: {model_id}") from exc


def _available_ram_gb() -> float | None:
    try:
        import psutil

        return float(psutil.virtual_memory().available) / (1024**3)
    except Exception:
        return None


def _cpu_min_ram_gb(hf_model_id: str) -> float:
    raw = os.environ.get("GROOVY_ACE_STEP_MIN_RAM_GB", "").strip()
    if raw:
        try:
            return max(4.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_CPU_MIN_AVAILABLE_RAM_GB.get(hf_model_id, 12.0)


def _allow_low_ram() -> bool:
    return os.environ.get("GROOVY_ACE_STEP_ALLOW_LOW_RAM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _refuse_cpu_if_low_ram(hf_model_id: str) -> None:
    """Fail fast on Apple/CPU hosts instead of swapping the whole machine to death."""
    if _allow_low_ram():
        return
    available = _available_ram_gb()
    if available is None:
        return
    needed = _cpu_min_ram_gb(hf_model_id)
    if available + 0.05 >= needed:
        return
    raise RuntimeError(
        f"ACE-Step on CPU needs ~{needed:.0f} GB available RAM (have {available:.1f} GB "
        "free/reclaimable — not total installed). Loading would thrash the Mac. "
        "Use Settings → Inference → Stub to explore the patch, render on CUDA, free memory "
        "(Activity Monitor → Memory), or set GROOVY_ACE_STEP_ALLOW_LOW_RAM=1 to override "
        "(may still freeze the host)."
    )


def _apply_memory_slicing(pipe: object) -> None:
    # Bound peak activation / VAE decode memory (helps barely-passing Macs).
    if hasattr(pipe, "enable_attention_slicing"):
        try:
            pipe.enable_attention_slicing()  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(pipe, "enable_vae_slicing"):
        try:
            pipe.enable_vae_slicing()  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(getattr(pipe, "vae", None), "enable_tiling"):
        try:
            pipe.vae.enable_tiling()  # type: ignore[union-attr]
        except Exception:
            pass


def _from_pretrained(AceStepPipeline: type, hf_model_id: str, *, dtype: object, token: str | bool):
    kwargs = {"torch_dtype": dtype, "token": token}
    try:
        return AceStepPipeline.from_pretrained(hf_model_id, low_cpu_mem_usage=True, **kwargs)
    except TypeError:
        # Older diffusers without low_cpu_mem_usage on AceStepPipeline.
        return AceStepPipeline.from_pretrained(hf_model_id, **kwargs)


@lru_cache(maxsize=3)
def _load_pipeline(hf_model_id: str):
    # Lazy: keep module importable in CI (no torch) for Hub auth unit tests.
    import torch

    _prefer_classic_hf_download()
    try:
        from diffusers import AceStepPipeline
    except ImportError as exc:
        raise RuntimeError(
            "diffusers AceStepPipeline is missing. "
            "Install ace-step-1.5, ace-step-1.5-sft, or ace-step-1.5-2b-turbo "
            "from Model Browser (Cmd+K) (requires diffusers >= 0.39 with AceStepPipeline)."
        ) from exc

    token = _resolve_hf_token()
    # Prefer CUDA; skip MPS — large DiT + Metal dtype bugs (same class as MusicGen/AF3).
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    else:
        _refuse_cpu_if_low_ram(hf_model_id)
        dtype = torch.float32

    try:
        pipe = _from_pretrained(
            AceStepPipeline, hf_model_id, dtype=dtype, token=_hf_token_arg(token)
        )
    except Exception as first_exc:
        if _is_hf_access_denied(first_exc) and token:
            try:
                pipe = _from_pretrained(AceStepPipeline, hf_model_id, dtype=dtype, token=False)
            except Exception as retry_exc:
                _raise_hf_load_error(hf_model_id, retry_exc)
        else:
            _raise_hf_load_error(hf_model_id, first_exc)

    pipe = pipe.to(device)
    _apply_memory_slicing(pipe)
    return pipe, device


def _raise_hf_load_error(hf_model_id: str, exc: BaseException) -> NoReturn:
    message = str(exc)
    if _is_hf_xet_failure(message):
        raise RuntimeError(
            f"Hugging Face download failed while fetching {hf_model_id} "
            "(often HF Xet on macOS, disk full, or interrupted transfer). "
            "Free disk space, set HF_HUB_DISABLE_XET=1, clear the partial HF cache, then retry."
        ) from exc
    if _is_hf_access_denied(exc):
        detail = _sanitize_hf_error(message)
        raise RuntimeError(
            f"Hugging Face denied access to {hf_model_id}. "
            "This XL pack is public — a fine-grained or invalid token can still 401 it. "
            f"Clear Settings → HF token (or use a classic Read token) and retry. Hub: {detail}"
        ) from exc
    raise RuntimeError(
        f"Failed to load ACE-Step from {hf_model_id}. {_sanitize_hf_error(message)}"
    ) from exc


def _resolve_lora_repo(lora: str) -> str:
    """Map registry LoRA id (or org/name Hub id) to a Diffusers adapter repo."""
    key = lora.strip()
    if not key:
        raise RuntimeError("LoRA id is empty")
    if key in LORA_HF_BY_ID:
        return LORA_HF_BY_ID[key]
    if "/" in key and not key.startswith("/") and " " not in key:
        return key
    try:
        from groovy.registry.catalog import ModelCatalog

        manifest = ModelCatalog().get(key)
        hf_repo = getattr(manifest, "hf_repo", None) if manifest is not None else None
        if isinstance(hf_repo, str) and hf_repo.strip():
            return hf_repo.strip()
        adapter_for = list(getattr(manifest, "adapter_for", None) or []) if manifest else []
        if manifest is not None and not adapter_for and not hf_repo:
            raise RuntimeError(
                f"{key!r} is in the catalog but is not marked as an ACE-Step LoRA "
                "(missing adapter_for / hf_repo). Pick ace-step-cny-lora or a Hub org/name."
            )
    except RuntimeError:
        raise
    except Exception:
        pass
    known = ", ".join(sorted(LORA_HF_BY_ID))
    raise RuntimeError(
        f"Unknown ACE-Step LoRA {key!r}. Install a LoRA from Model Browser "
        f"(known ids: {known}) or paste a Hugging Face org/name adapter repo."
    )


def _load_lora(pipe: object, repo: str, *, scale: float) -> None:
    try:
        import peft  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "PEFT is required for ACE-Step LoRA. Install ace-step-cny-lora "
            "(or peft) from Model Browser (Cmd+K), then retry."
        ) from exc
    if not hasattr(pipe, "load_lora_weights"):
        raise RuntimeError(
            "This Diffusers AceStepPipeline build does not support load_lora_weights "
            "(needs AceStepLoraLoaderMixin, shipped in diffusers >= 0.42). "
            "Install/upgrade ace-step-cny-lora or ace-step-1.5-2b-turbo from Model Browser "
            "(Cmd+K), or: uv pip install 'diffusers>=0.42' 'transformers>=5.22', then retry."
        )
    token = _hf_token_arg(_resolve_hf_token())
    try:
        pipe.load_lora_weights(  # type: ignore[attr-defined]
            repo, adapter_name=_LORA_ADAPTER_NAME, token=token
        )
    except TypeError:
        pipe.load_lora_weights(repo, adapter_name=_LORA_ADAPTER_NAME)  # type: ignore[attr-defined]
    except Exception as exc:
        if _is_hf_access_denied(exc):
            raise RuntimeError(
                f"Hugging Face denied access to LoRA {repo}. "
                f"Hub: {_sanitize_hf_error(str(exc))}"
            ) from exc
        raise RuntimeError(
            f"Failed to load ACE-Step LoRA from {repo}. {_sanitize_hf_error(str(exc))}"
        ) from exc
    weight = float(np.clip(scale, 0.0, 1.5))
    if hasattr(pipe, "set_adapters"):
        try:
            pipe.set_adapters([_LORA_ADAPTER_NAME], adapter_weights=[weight])  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    if hasattr(pipe, "fuse_lora"):
        try:
            pipe.fuse_lora(lora_scale=weight)  # type: ignore[attr-defined]
        except TypeError:
            pipe.fuse_lora()  # type: ignore[attr-defined]


def _unload_lora(pipe: object) -> None:
    """Strip adapter from the cached pipeline so the next base render stays clean."""
    if hasattr(pipe, "unfuse_lora"):
        try:
            pipe.unfuse_lora()  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(pipe, "delete_adapters"):
        try:
            pipe.delete_adapters([_LORA_ADAPTER_NAME])  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(pipe, "unload_lora_weights"):
        try:
            pipe.unload_lora_weights()  # type: ignore[attr-defined]
        except Exception:
            pass


def generate_from_text(
    prompt: str,
    *,
    sample_rate: int,
    model_id: str = "ace-step-1.5",
    seconds_total: float = 15.0,
    num_inference_steps: int = 8,
    guidance_scale: float = 1.0,
    lyrics: str = "",
    lora: str = "",
    lora_scale: float = 1.0,
    seed: int | None = None,
) -> np.ndarray:
    pipe, device = _load_pipeline(_hf_model_id(model_id))
    # Model supports ~10s–10min; keep hero demos short.
    duration = float(np.clip(seconds_total, 10.0, 120.0))
    generator = None
    if seed is not None and seed >= 0:
        import torch

        gen_device = "cuda" if device == "cuda" else "cpu"
        generator = torch.Generator(device=gen_device).manual_seed(int(seed) % (2**63 - 1))

    lora_id = (lora or "").strip()
    lora_loaded = False
    try:
        if lora_id:
            _load_lora(pipe, _resolve_lora_repo(lora_id), scale=lora_scale)
            lora_loaded = True
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
    finally:
        if lora_loaded:
            _unload_lora(pipe)
