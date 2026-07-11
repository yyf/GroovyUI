"""Torchaudio compatibility shims for DeepFilterNet on newer torchaudio releases."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass


@dataclass
class _AudioMetaData:
    sample_rate: int
    num_frames: int = 0
    num_channels: int = 1


def ensure_deepfilter_importable() -> None:
    import torchaudio as ta

    if not hasattr(ta, "info"):

        def info(path: str, **kwargs: object) -> _AudioMetaData:
            wav, sr = ta.load(path)
            channels = wav.shape[0] if wav.ndim > 1 else 1
            return _AudioMetaData(sample_rate=sr, num_frames=wav.shape[-1], num_channels=channels)

        ta.info = info  # type: ignore[attr-defined]

    if "torchaudio.backend.common" not in sys.modules:
        common = types.ModuleType("torchaudio.backend.common")
        common.AudioMetaData = _AudioMetaData
        backend = types.ModuleType("torchaudio.backend")
        backend.common = common
        sys.modules["torchaudio.backend.common"] = common
        sys.modules["torchaudio.backend"] = backend


def deepfilternet_available() -> bool:
    try:
        ensure_deepfilter_importable()
        import df.enhance  # noqa: F401

        return True
    except ImportError:
        return False
