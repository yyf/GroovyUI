from __future__ import annotations

import os


def inference_stub_enabled() -> bool:
    return os.environ.get("GROOVY_INFERENCE_STUB", "").lower() in ("1", "true", "yes")


def basic_pitch_available() -> bool:
    try:
        import basic_pitch.note_creation  # noqa: F401
        import onnxruntime  # noqa: F401

        return True
    except ImportError:
        return False


def musicgen_melody_available() -> bool:
    try:
        import pretty_midi  # noqa: F401
        import torch  # noqa: F401
        import torchaudio  # noqa: F401
        import transformers  # noqa: F401

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
