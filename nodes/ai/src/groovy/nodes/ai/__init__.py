from groovy.nodes.ai.nodes import (
    AudioToMIDI,
    DeepfakeDetect,
    Denoise,
    GenerateAudio,
    MIDIToAudio,
    SeparateStems,
    SeparateToObjects,
    SingFromMIDI,
    TTS,
    VoiceConvert,
    WhisperSTT,
    register_all,
)

__all__ = [
    "register_all",
    "Denoise",
    "SeparateStems",
    "SeparateToObjects",
    "WhisperSTT",
    "TTS",
    "VoiceConvert",
    "AudioToMIDI",
    "DeepfakeDetect",
    "MIDIToAudio",
    "GenerateAudio",
    "SingFromMIDI",
]
