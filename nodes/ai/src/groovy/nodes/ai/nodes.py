from __future__ import annotations

from groovy.executor.audio import AudioBuffer
from groovy.node import GroovyNode, register_node


def register_all() -> None:
    _ = (Denoise, SeparateStems, WhisperSTT, TTS, VoiceConvert)


@register_node
class Denoise(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["deepfilternet-v3"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "deepfilternet-v3"}),
            },
            "optional": {
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0}),
            },
        }

    def run(self, **kwargs) -> tuple[AudioBuffer]:
        raise RuntimeError("Denoise must run in AI worker subprocess")


@register_node
class SeparateStems(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["demucs-v4", "demucs-v4-ht"]
    RETURN_TYPES = ("STEMS",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "demucs-v4"}),
            },
            "optional": {},
        }

    def run(self, **kwargs):
        raise RuntimeError("SeparateStems must run in AI worker subprocess")


@register_node
class WhisperSTT(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["whisper-large-v3-turbo", "whisper-small-en"]
    RETURN_TYPES = ("STRING",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "whisper-large-v3-turbo"}),
            },
            "optional": {"language": ("STRING", {"default": "en"})},
        }

    def run(self, **kwargs):
        raise RuntimeError("WhisperSTT must run in AI worker subprocess")


@register_node
class TTS(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_generated"
    COMPATIBLE_MODELS = ["f5-tts-base", "cosyvoice-300m", "gpt-sovits-v2"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"default": "Hello from GroovyUI."}),
                "model": ("MODEL_REF", {"default": "f5-tts-base"}),
            },
            "optional": {},
        }

    def run(self, **kwargs):
        raise RuntimeError("TTS must run in AI worker subprocess")


@register_node
class VoiceConvert(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["rvc-v2-base", "openvoice-v2"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "rvc-v2-base"}),
            },
            "optional": {},
        }

    def run(self, **kwargs):
        raise RuntimeError("VoiceConvert must run in AI worker subprocess")
