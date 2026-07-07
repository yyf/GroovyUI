from __future__ import annotations

from groovy.executor.audio import AudioBuffer
from groovy.node import GroovyNode, register_node


def register_all() -> None:
    _ = (
        Denoise,
        SeparateStems,
        WhisperSTT,
        TTS,
        VoiceConvert,
        AudioToMIDI,
        DeepfakeDetect,
        MIDIToAudio,
        GenerateAudio,
        SingFromMIDI,
        SeparateToObjects,
    )


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


@register_node
class AudioToMIDI(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["basic-pitch"]
    RETURN_TYPES = ("MIDI",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "basic-pitch"}),
            },
            "optional": {},
        }

    def run(self, **kwargs):
        raise RuntimeError("AudioToMIDI must run in AI worker subprocess")


@register_node
class DeepfakeDetect(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "unknown"
    COMPATIBLE_MODELS = ["rawnet2-asvspoof"]
    RETURN_TYPES = ("AUTHENTICITY", "AUDIO")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "rawnet2-asvspoof"}),
            },
            "optional": {
                "threshold": ("FLOAT", {"default": 0.5}),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("DeepfakeDetect must run in AI worker subprocess")


@register_node
class MIDIToAudio(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_generated"
    COMPATIBLE_MODELS = ["musicgen-melody-small"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "midi": ("MIDI",),
                "model": ("MODEL_REF", {"default": "musicgen-melody-small"}),
            },
            "optional": {
                "text": ("TEXT",),
                "prompt": ("STRING", {"default": "regenerated melody"}),
                "reference_audio": ("AUDIO",),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("MIDIToAudio must run in AI worker subprocess")


@register_node
class GenerateAudio(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_generated"
    COMPATIBLE_MODELS = ["musicgen-small", "stable-audio-open-1.0"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("TEXT",),
                "model": ("MODEL_REF", {"default": "musicgen-small"}),
            },
            "optional": {
                "midi": ("MIDI",),
                "reference_audio": ("AUDIO",),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("GenerateAudio must run in AI worker subprocess")


@register_node
class SingFromMIDI(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_generated"
    COMPATIBLE_MODELS = ["diffsinger-opencpop"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "midi": ("MIDI",),
                "model": ("MODEL_REF", {"default": "diffsinger-opencpop"}),
            },
            "optional": {
                "lyrics": ("TEXT",),
                "text": ("STRING", {"default": "la la la"}),
                "reference_audio": ("AUDIO",),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("SingFromMIDI must run in AI worker subprocess")


@register_node
class SeparateToObjects(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["demucs-v4-objects", "demucs-v4"]
    RETURN_TYPES = ("OBA",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "demucs-v4-objects"}),
            },
            "optional": {},
        }

    def run(self, **kwargs):
        raise RuntimeError("SeparateToObjects must run in AI worker subprocess")
