from __future__ import annotations

from groovy.executor.audio import AudioBuffer
from groovy.node import GroovyNode, register_node


def register_all() -> None:
    _ = (
        Denoise,
        SeparateStems,
        WhisperSTT,
        DiarizeTranscribe,
        TranslateText,
        TTS,
        VoiceConvert,
        SpeechTranslate,
        TimbreTransfer,
        AudioToMIDI,
        DeepfakeDetect,
        EmbedWatermark,
        DetectWatermark,
        MIDIToAudio,
        GenerateAudio,
        SingFromMIDI,
        Video2Audio,
        SeparateToObjects,
        AmbisonicUpmix,
        AmbisonicTrajectoryExtract,
        BinauralRender,
        SpatialUpmix,
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
            "optional": {},
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
    RETURN_TYPES = ("AUDIO", "AUDIO", "AUDIO", "AUDIO")
    OUTPUT_NAMES = ("vocals", "drums", "bass", "other")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "demucs-v4"}),
            },
            "optional": {},
        }

    @classmethod
    def describe(cls) -> dict:
        schema = super().describe()
        schema["outputs"] = [
            {"name": name, "type": "AUDIO"} for name in cls.OUTPUT_NAMES
        ]
        return schema

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
    RETURN_TYPES = ("TEXT",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "whisper-large-v3-turbo"}),
            },
            "optional": {},
        }

    def run(self, **kwargs):
        raise RuntimeError("WhisperSTT must run in AI worker subprocess")


@register_node
class TranslateText(GroovyNode):
    """Text machine translation (Whisper transcript → target language)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = [
        "m2m100-418m",
        "madlad400-3b-mt",
        "opus-mt-en-es",
        "opus-mt-en-fr",
    ]
    RETURN_TYPES = ("TEXT",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("TEXT",),
                "model": ("MODEL_REF", {"default": "m2m100-418m"}),
            },
            "optional": {
                "src_lang": (
                    "STRING",
                    {
                        "default": "en",
                        "description": "Source language (ISO 639-1 preferred: en, es, fr). Opus models ignore this (fixed pair).",
                    },
                ),
                "tgt_lang": (
                    "STRING",
                    {
                        "default": "zh",
                        "description": "Target language (ISO 639-1 preferred: zh, en, es, fr). Opus models ignore this (fixed pair).",
                    },
                ),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("TranslateText must run in AI worker subprocess")


@register_node
class DiarizeTranscribe(GroovyNode):
    """Speaker-labeled transcript for meetings/podcasts (Whisper + diarization)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["whisper-large-v3-turbo", "whisper-small-en"]
    RETURN_TYPES = ("TEXT",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "whisper-large-v3-turbo"}),
            },
            "optional": {
                "diarize_model": ("STRING", {"default": "pyannote-diarization-3.1"}),
                "language": ("STRING", {"default": "en"}),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("DiarizeTranscribe must run in AI worker subprocess")


@register_node
class TTS(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    DURATION_LOCKED = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_generated"
    COMPATIBLE_MODELS = ["kokoro-82m", "cosyvoice-300m", "f5-tts-base", "gpt-sovits-v2"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL_REF", {"default": "kokoro-82m"}),
            },
            "optional": {
                "transcript": ("TEXT",),
                "text": ("STRING", {"default": "Hello from GroovyUI."}),
                "language": (
                    "STRING",
                    {
                        "default": "en",
                        "description": "ISO 639-1 for Kokoro (en, zh, es, fr, ja, …). Mandarin needs misaki[zh].",
                    },
                ),
                "voice": (
                    "STRING",
                    {
                        "default": "",
                        "description": "Optional Kokoro voice id (e.g. zf_xiaobei). Empty = language default.",
                    },
                ),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
                # Zero-shot / few-shot clone models (F5-TTS, GPT-SoVITS) use this clip.
                "reference_audio": ("AUDIO",),
                "reference_text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
            },
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
class SpeechTranslate(GroovyNode):
    """Speech-to-speech translation for localization (source language → target language)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    DURATION_LOCKED = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["seamless-m4t-v2-large"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "seamless-m4t-v2-large"}),
            },
            "optional": {
                "src_lang": (
                    "STRING",
                    {
                        "default": "eng",
                        "description": "Source language (ISO 639-3 preferred: eng, spa, fra; 2-letter also ok).",
                    },
                ),
                "tgt_lang": (
                    "STRING",
                    {
                        "default": "spa",
                        "description": "Target language (ISO 639-3 preferred: eng, spa, fra; 2-letter also ok).",
                    },
                ),
                "speaker_id": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 199,
                        "description": "Seamless vocoder speaker (0–199). Not source-voice clone; try other IDs if gender/timbre is wrong. Some IDs work better per language.",
                    },
                ),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("SpeechTranslate must run in AI worker subprocess")


@register_node
class TimbreTransfer(GroovyNode):
    """Neural audio resynthesis / timbre transfer (RAVE and similar VAEs)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["rave-v1"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "rave-v1"}),
            },
            "optional": {
                "fidelity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0}),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("TimbreTransfer must run in AI worker subprocess")


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
            "optional": {},
        }

    def run(self, **kwargs):
        raise RuntimeError("DeepfakeDetect must run in AI worker subprocess")


@register_node
class EmbedWatermark(GroovyNode):
    """Embed an imperceptible AudioSeal watermark into audio (Meta, MIT)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["audioseal-16bit"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "audioseal-16bit"}),
            },
            "optional": {
                "message_id": ("INT", {"default": 42, "min": 0, "max": 65535}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0}),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("EmbedWatermark must run in AI worker subprocess")


@register_node
class DetectWatermark(GroovyNode):
    """Detect an AudioSeal watermark and decode its 16-bit payload (Meta, MIT)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "unknown"
    COMPATIBLE_MODELS = ["audioseal-16bit"]
    RETURN_TYPES = ("TEXT", "AUDIO")
    OUTPUT_NAMES = ("report", "audio")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "audioseal-16bit"}),
            },
            "optional": {
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0}),
            },
        }

    @classmethod
    def describe(cls) -> dict:
        schema = super().describe()
        schema["outputs"] = [{"name": name, "type": typ} for name, typ in zip(cls.OUTPUT_NAMES, cls.RETURN_TYPES)]
        return schema

    def run(self, **kwargs):
        raise RuntimeError("DetectWatermark must run in AI worker subprocess")


@register_node
class MIDIToAudio(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    DURATION_LOCKED = False
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
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
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
    DURATION_LOCKED = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_generated"
    COMPATIBLE_MODELS = [
        "musicgen-small",
        "stable-audio-open-1.0",
        "ace-step-1.5",
        "ace-step-1.5-2b-turbo",
    ]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL_REF", {"default": "musicgen-small"}),
            },
            "optional": {
                # TEXT wire (optional) supersedes local prompt widget — same dual path as MIDIToAudio.
                "text": ("TEXT",),
                "prompt": ("STRING", {"default": ""}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
                "midi": ("MIDI",),
                "reference_audio": ("AUDIO",),
                "lyrics": ("STRING", {"default": ""}),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("GenerateAudio must run in AI worker subprocess")


@register_node
class Video2Audio(GroovyNode):
    """Generic video→audio node — Diff-Foley is the example default; browse for alternatives.

    Model-agnostic: pick any registry model listed in ``COMPATIBLE_MODELS``
    (default ``diff-foley`` as a worked example). Additional backends plug in via
    the worker dispatch in ``inference.video2audio_waveform``.
    """

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    DURATION_LOCKED = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_generated"
    # Example default; browse Model Browser for other video-to-audio models.
    COMPATIBLE_MODELS = ["diff-foley"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (
                    "MODEL_REF",
                    {
                        "default": "diff-foley",
                        "description": (
                            "Generic Video to Audio node — Diff-Foley is the example default. "
                            "Open Model Browser (Cmd+K → Find models) to install and choose "
                            "alternative video-to-audio models."
                        ),
                    },
                ),
            },
            "optional": {
                # Project-relative video path (mp4/…). Empty = text-to-audio when the model allows.
                "path": (
                    "STRING",
                    {
                        "default": "",
                        "description": "Project-relative video file (e.g. assets/uploads/clip.mp4). Required for most models; leave empty only if the selected model supports text-to-audio.",
                    },
                ),
                "text": ("TEXT",),
                "prompt": ("STRING", {"default": ""}),
                "negative_prompt": ("STRING", {"default": ""}),
                "duration": ("FLOAT", {"default": 8.0, "min": 1.0, "max": 30.0}),
                "num_steps": ("INT", {"default": 25, "min": 4, "max": 50}),
                "cfg_strength": ("FLOAT", {"default": 4.5, "min": 0.0, "max": 15.0}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("Video2Audio must run in AI worker subprocess")


@register_node
class SingFromMIDI(GroovyNode):
    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    DURATION_LOCKED = False
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
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
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


@register_node
class AmbisonicUpmix(GroovyNode):
    """Neural mono/stereo → FOA Ambisonics (Helix stub / real)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["helix-v0.7"]
    RETURN_TYPES = ("AMBISONICS",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "helix-v0.7"}),
            },
            "optional": {
                "trajectory": ("TRAJECTORY",),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("AmbisonicUpmix must run in AI worker subprocess")


@register_node
class AmbisonicTrajectoryExtract(GroovyNode):
    """Extract XYZ DOA trajectory from FOA Ambisonics (SELD stub / real)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["dcase-seld-foa-multiaccdoa"]
    RETURN_TYPES = ("TRAJECTORY",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ambisonics": ("AMBISONICS",),
                "model": ("MODEL_REF", {"default": "dcase-seld-foa-multiaccdoa"}),
            },
            "optional": {},
        }

    def run(self, **kwargs):
        raise RuntimeError("AmbisonicTrajectoryExtract must run in AI worker subprocess")


@register_node
class BinauralRender(GroovyNode):
    """Stereo → binaural headphones (stereo2spatial-v2; stub = Bauer crossfeed)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["hrtf-binaural-v0", "stereo2spatial-v2-binaural"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "hrtf-binaural-v0"}),
            },
            "optional": {
                "strength": ("FLOAT", {"default": 0.45}),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("BinauralRender must run in AI worker subprocess")


@register_node
class SpatialUpmix(GroovyNode):
    """Stereo → multichannel bed (stereo2spatial-v1 → 7.1.4; stub mid/side bleed)."""

    CATEGORY = "GroovyUI/AI"
    EXPORT_TIER = "OFFLINE_RENDER"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = False
    run_in_worker = True
    PROVENANCE_CLASS = "ai_transformed"
    COMPATIBLE_MODELS = ["stereo-atmos-bed-v0", "stereo2spatial-v1"]
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "model": ("MODEL_REF", {"default": "stereo-atmos-bed-v0"}),
            },
            "optional": {
                "layout": ("STRING", {"default": "7.1.4", "choices": ["7.1.4", "5.1", "7.1"]}),
            },
        }

    def run(self, **kwargs):
        raise RuntimeError("SpatialUpmix must run in AI worker subprocess")
