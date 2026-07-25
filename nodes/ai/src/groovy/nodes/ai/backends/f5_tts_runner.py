"""Optional F5-TTS backend (SWivid/F5-TTS) for zero-shot voice cloning."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf


def _ensure_numba_cache() -> None:
    """Librosa/numba need a writable cache dir (site-packages is often read-only)."""
    if os.environ.get("NUMBA_CACHE_DIR"):
        return
    root = Path(os.environ.get("GROOVY_PROJECT_DIR") or Path.cwd()) / ".groovy" / "numba_cache"
    root.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(root)


@lru_cache(maxsize=1)
def _load_f5tts():
    _ensure_numba_cache()
    try:
        from f5_tts.api import F5TTS  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "f5-tts package is not installed. Install f5-tts-base from Model Browser (Cmd+K)."
        ) from exc

    # F5TTS_v1_Base is the current public checkpoint; downloads from Hugging Face on first use.
    return F5TTS(model="F5TTS_v1_Base")


def synthesize_pcm(
    text: str,
    *,
    sample_rate: int = 48000,
    reference_pcm: np.ndarray,
    reference_sample_rate: int,
    reference_text: str = "",
    seed: int | None = None,
) -> np.ndarray:
    """Clone voice from reference PCM and synthesize ``text``.

    ``reference_text`` may be empty — F5-TTS will ASR-transcribe the reference (uses extra VRAM).
    """
    if reference_pcm.size == 0:
        raise RuntimeError("F5-TTS requires a non-empty reference_audio clip")

    mono = reference_pcm.astype(np.float64)
    if mono.ndim > 1:
        mono = mono.mean(axis=0)
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    if peak > 1e-8:
        mono = mono / peak * 0.9

    with tempfile.TemporaryDirectory(prefix="groovy-f5-ref-") as tmp:
        ref_path = Path(tmp) / "reference.wav"
        sf.write(str(ref_path), mono, int(reference_sample_rate))

        model = _load_f5tts()
        wav, native_sr, _spec = model.infer(
            ref_file=str(ref_path),
            ref_text=reference_text or "",
            gen_text=text,
            seed=seed,
            show_info=lambda *_args, **_kwargs: None,
        )

    mono_out = np.asarray(wav, dtype=np.float64)
    if mono_out.ndim > 1:
        mono_out = mono_out.mean(axis=0)
    native_sr = int(native_sr) if native_sr else 24000
    if sample_rate != native_sr:
        from scipy import signal

        mono_out = signal.resample(mono_out, int(len(mono_out) * sample_rate / native_sr))
    peak_out = float(np.max(np.abs(mono_out))) if mono_out.size else 0.0
    if peak_out > 1e-8:
        mono_out = mono_out / peak_out * 0.9
    return mono_out.reshape(1, -1)
