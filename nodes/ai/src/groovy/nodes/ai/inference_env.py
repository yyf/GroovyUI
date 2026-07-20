from __future__ import annotations

from collections.abc import Callable


def inference_stub_enabled() -> bool:
    """Return True when AI nodes should use stub inference.

    See ``groovy.registry.studio_settings.inference_stub_active`` for precedence.
    """
    from groovy.registry.studio_settings import inference_stub_active

    return inference_stub_active()


def basic_pitch_available() -> bool:
    try:
        import basic_pitch.note_creation  # noqa: F401
        import onnxruntime  # noqa: F401

        return True
    except ImportError:
        return False


def musicgen_available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401

        return True
    except ImportError:
        return False


def musicgen_melody_available() -> bool:
    try:
        import pretty_midi  # noqa: F401
        import torchaudio  # noqa: F401

        return musicgen_available()
    except ImportError:
        return False


def musicgen_small_available() -> bool:
    return musicgen_available()


def demucs_available() -> bool:
    try:
        import demucs.apply  # noqa: F401
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def deepfilternet_available() -> bool:
    from groovy.nodes.ai.deepfilter_compat import deepfilternet_available as _available

    return _available()


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def kokoro_available() -> bool:
    try:
        import kokoro  # noqa: F401

        return True
    except ImportError:
        return False


_MODEL_RUNTIME_CHECKS: dict[str, Callable[[], bool]] = {
    "deepfilternet-v3": deepfilternet_available,
    "basic-pitch": basic_pitch_available,
    "demucs-v4": demucs_available,
    "demucs-v4-ht": demucs_available,
    "musicgen-melody-small": musicgen_melody_available,
    "musicgen-small": musicgen_small_available,
    "whisper-large-v3-turbo": whisper_available,
    "whisper-small-en": whisper_available,
    "kokoro-82m": kokoro_available,
}


def model_inference_ready(model_id: str, *, dev_stub: bool = False) -> bool:
    if dev_stub or inference_stub_enabled():
        return True
    checker = _MODEL_RUNTIME_CHECKS.get(model_id)
    if checker is None:
        return True
    return checker()
