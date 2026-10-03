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


def stable_audio_available() -> bool:
    try:
        import torchsde  # noqa: F401
        from diffusers import StableAudioPipeline  # noqa: F401

        return True
    except ImportError:
        return False


def ace_step_available() -> bool:
    try:
        import torch  # noqa: F401
        from diffusers import AceStepPipeline  # noqa: F401

        return True
    except ImportError:
        return False


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


def f5_tts_available() -> bool:
    try:
        import f5_tts  # noqa: F401

        return True
    except ImportError:
        return False


def audioseal_available() -> bool:
    try:
        import audioseal  # noqa: F401
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def rave_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def seamless_available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401

        return True
    except ImportError:
        return False


def diff_foley_available() -> bool:
    try:
        import librosa  # noqa: F401
        import omegaconf  # noqa: F401
        import soundfile  # noqa: F401
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def stereo2spatial_available() -> bool:
    try:
        import stereo2spatial  # noqa: F401
        import torch  # noqa: F401

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
    "stable-audio-open-1.0": stable_audio_available,
    "ace-step-1.5": ace_step_available,
    "ace-step-1.5-2b-turbo": ace_step_available,
    "whisper-large-v3-turbo": whisper_available,
    "whisper-small-en": whisper_available,
    "kokoro-82m": kokoro_available,
    "f5-tts-base": f5_tts_available,
    "audioseal-16bit": audioseal_available,
    "rave-v1": rave_available,
    "seamless-m4t-v2-large": seamless_available,
    "diff-foley": diff_foley_available,
    "stereo2spatial-v2-binaural": stereo2spatial_available,
    "stereo2spatial-v1": stereo2spatial_available,
}


def model_inference_ready(model_id: str, *, dev_stub: bool = False) -> bool:
    if dev_stub or inference_stub_enabled():
        return True
    checker = _MODEL_RUNTIME_CHECKS.get(model_id)
    if checker is None:
        return True
    return checker()
