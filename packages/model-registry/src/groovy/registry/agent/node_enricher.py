from __future__ import annotations

import re
from typing import Any

NODE_HINTS: dict[str, dict[str, Any]] = {
    "LoadAudio": {
        "description": "Load a WAV or FLAC file from the project into the graph cache.",
        "inputs": {},
        "outputs": {"output_0": "Planar PCM audio buffer at native sample rate."},
        "widgets": {
            "path": "Project-relative path to the audio file (e.g. assets/samples/male-1.wav).",
        },
    },
    "Denoise": {
        "description": "Remove background noise from speech using a registry denoiser model.",
        "widgets": {
            "model": "Denoise model from the registry (e.g. DeepFilterNet).",
            "strength": "How aggressively to attenuate noise (0–1).",
        },
    },
    "SeparateStems": {
        "description": "Split music into stems (vocals, drums, bass, other) for remix workflows.",
        "widgets": {"model": "Stem separation model (e.g. Demucs)."},
    },
    "WhisperSTT": {
        "description": "Transcribe speech to text with a Whisper-class STT model.",
        "widgets": {"model": "Speech-to-text model from the registry."},
    },
    "DiarizeTranscribe": {
        "description": "Speaker-labeled transcript for meetings and podcasts (Whisper + diarization).",
        "widgets": {
            "model": "Whisper STT model for transcription.",
            "diarize_model": "Diarization model id (pyannote when installed; else energy-turn fallback).",
            "language": "ISO language code for Whisper.",
        },
    },
    "TTS": {
        "description": "Synthesize speech from a text prompt using a TTS model. Wire reference_audio for zero-shot voice cloning (F5-TTS / GPT-SoVITS).",
        "inputs": {
            "transcript": "Optional TEXT wire; overrides the local text widget when connected.",
            "reference_audio": "Optional speaker reference clip for clone models (F5-TTS, GPT-SoVITS).",
        },
        "widgets": {
            "model": "Text-to-speech model (Kokoro for plain TTS; F5-TTS / GPT-SoVITS for cloning).",
            "text": "Script or prompt to speak.",
            "seed": "Random seed (−1 = random).",
        },
    },
    "VoiceConvert": {
        "description": "Convert speaker timbre while preserving timing and intelligibility (RVC / OpenVoice).",
        "widgets": {"model": "Voice conversion / RVC model."},
    },
    "AudioToMIDI": {
        "description": "Transcribe pitched audio into a symbolic MIDI buffer (Basic Pitch class).",
        "widgets": {"model": "Audio-to-MIDI model (e.g. basic-pitch)."},
    },
    "MIDIToAudio": {
        "description": "Generate audio conditioned on MIDI melody and optional text prompt.",
        "widgets": {
            "model": "MIDI-to-audio model (e.g. MusicGen Melody).",
            "prompt": "Style or instrument description for generation.",
            "seed": "Random seed (−1 = random). Same seed + prompt → repeatable output.",
        },
    },
    "GenerateAudio": {
        "description": "Generate music or soundscapes from a text prompt (optional MIDI conditioning).",
        "inputs": {
            "text": "Optional TEXT wire; when connected, overrides the local prompt widget.",
            "midi": "Optional MIDI melody conditioning.",
            "reference_audio": "Optional timbre/style reference clip.",
        },
        "widgets": {
            "model": "Text-to-audio model (e.g. MusicGen Small).",
            "prompt": "Describe the sound you want to generate.",
            "seed": "Random seed (−1 = random). Same seed + prompt → repeatable output.",
        },
    },
    "SingFromMIDI": {
        "description": "Synthesize singing voice from MIDI notes and lyrics.",
        "inputs": {
            "midi": "Melody MIDI performance.",
            "lyrics": "Lyrics text from a Prompt node.",
            "reference_audio": "Optional vocal timbre reference.",
        },
        "widgets": {
            "model": "Singing synthesis model (e.g. DiffSinger).",
            "text": "Fallback lyrics when no TEXT wire is connected.",
            "seed": "Random seed (−1 = random).",
        },
    },
    "AutomationApply": {
        "description": "Multiply audio by a control-rate envelope curve (gain automation).",
        "inputs": {
            "audio": "Audio to modulate.",
            "curve": "Optional AUTOMATION envelope; falls back to scalar gain.",
        },
        "widgets": {"gain": "Scalar gain when no curve is wired."},
    },
    "MIDIToFloat": {
        "description": "Extract a control curve from MIDI CC data (stub: flat default in dev).",
        "widgets": {"cc": "MIDI CC number to follow.", "default_value": "Fallback value when CC is sparse."},
    },
    "Preview": {
        "description": "Terminal sink for cached audition (audio) and/or transcript inspection (text).",
        "inputs": {
            "audio": "Audio to audition in the transport bar (also enables SaveAudio chaining).",
            "text": "Text (e.g. Whisper transcript) shown on the node and in Node Helper.",
        },
    },
    "Note": {
        "description": "Sticky comment on the canvas — documentation only, not part of the render graph.",
        "widgets": {
            "text": "Your comment. Shown on the node; edit here or in the inspector.",
        },
    },
    "Normalize": {
        "description": "Adjust loudness to a target LUFS and peak ceiling.",
        "widgets": {
            "target_lufs": "Integrated loudness target (EBU R128 style).",
            "target_peak_db": "True-peak limit in dBFS.",
        },
    },
    "ChannelConvert": {
        "description": "Explicit upmix or downmix between channel layouts (ITU-R BS.775 for 5.1→stereo).",
        "widgets": {"layout": "Target layout: mono, stereo, 5.1, etc."},
    },
    "Transcode": {
        "description": "Export cached audio to FLAC or WAV while passing the buffer through.",
        "widgets": {"format": "Output codec.", "path": "Project-relative export path."},
    },
    "AmbisonicEncode": {
        "description": "Encode mono/stereo audio into first-order ambisonics (FOA AmbiX ACN/SN3D).",
        "widgets": {"order": "Ambisonics order (1 = FOA in Phase 2)."},
    },
    "AmbisonicDecode": {
        "description": "Decode FOA ambisonics to speaker or headphone layouts.",
        "widgets": {"layout": "Output layout (stereo in Phase 2)."},
    },
    "AmbisonicRotate": {
        "description": "Rotate the ambisonic soundfield — yaw for VR head-tracking preview.",
        "widgets": {"yaw": "Horizontal rotation in degrees."},
    },
    "ObjectFromAudio": {
        "description": "Wrap audio as a spatial object in an object-based scene (OBA).",
        "widgets": {
            "name": "Object label in the scene.",
            "azimuth": "Horizontal angle in degrees (0 = front).",
            "elevation": "Vertical angle in degrees.",
        },
    },
    "RenderObjectScene": {
        "description": "Render beds + objects to a channel layout for audition.",
        "widgets": {"output": "Target layout: stereo or binaural (stereo pan stub in Phase 2)."},
    },
    "ObjectPlacement": {
        "description": "Auto-spread spatial objects across the azimuth field.",
        "widgets": {
            "model": "Placement model (heuristic spread in Phase 2).",
            "spread_deg": "Total azimuth spread in degrees.",
        },
    },
    "SeparateToObjects": {
        "description": "Separate stems and map each to a spatial object in an OBA scene.",
        "widgets": {"model": "Stem separation model (demucs-v4-objects aliases demucs-v4)."},
    },
    "ObjectMerge": {
        "description": "Merge beds and objects from two object-based scenes.",
    },
    "ObjectAnimate": {
        "description": "Apply keyframed azimuth and gain animation to scene objects.",
        "widgets": {
            "object_id": "Target object id or name (empty = all objects).",
            "azimuth_start": "Start azimuth in degrees.",
            "azimuth_end": "End azimuth in degrees.",
            "gain_start_db": "Start gain in dB.",
            "gain_end_db": "End gain in dB.",
        },
    },
    "MIDIInDevice": {
        "description": "Hardware or virtual MIDI input → control or performance MIDI stream.",
        "widgets": {
            "device_id": "Selected MIDI input port.",
            "channel_filter": "MIDI channel 1–16 or all.",
            "mode": "control (CC automation) or performance (notes).",
            "record_arm": "Capture live input to cache during transport.",
        },
    },
    "MIDIOutDevice": {
        "description": "Forward MIDI stream or mirror a FLOAT as CC to hardware output.",
        "widgets": {
            "device_id": "Selected MIDI output port.",
            "channel": "MIDI channel 1–16.",
            "mode": "stream (forward MIDI) or cc_mirror (FLOAT → CC).",
            "cc_number": "CC number when mode is cc_mirror.",
        },
    },
    "OSCInLive": {
        "description": "Capture localhost OSC messages (/groovy/*) for widget tweaks and render.",
    },
    "MIDINoteGate": {
        "description": "Convert MIDI note on/off events into a 0/1 automation gate.",
        "widgets": {
            "note": "MIDI note number to track.",
            "channel": "MIDI channel 1–16.",
        },
    },
    "MultichannelNormalize": {
        "description": "EBU R128 / peak normalize multichannel audio without folding channels.",
        "widgets": {
            "target_lufs": "Integrated loudness target (default -23 LUFS for surround beds).",
            "target_peak_db": "Peak normalize target when mode is peak.",
            "mode": "lufs or peak.",
        },
    },
    "ModuleInlet": {
        "description": "Mark a subgraph input boundary when building reusable modules.",
        "inputs": {"signal": "External audio fed into the module."},
        "widgets": {"name": "Port label.", "socket_type": "Socket type label for export metadata."},
    },
    "ModuleOutlet": {
        "description": "Mark a subgraph output boundary when building reusable modules.",
        "inputs": {"signal": "Audio leaving the module."},
        "widgets": {"name": "Port label."},
    },
}


def _humanize(name: str) -> str:
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ").strip().lower()


def enrich_node_schema(node_type: str, schema: dict[str, Any]) -> dict[str, Any]:
    hints = NODE_HINTS.get(node_type, {})
    enriched = dict(schema)
    enriched["description"] = hints.get("description", f"{_humanize(node_type)} node.")
    enriched["inputs"] = [
        {
            **item,
            "description": hints.get("inputs", {}).get(item["name"])
            or f"{_humanize(item['name'])} ({item['type']} socket).",
        }
        for item in schema.get("inputs", [])
    ]
    enriched["outputs"] = [
        {
            **item,
            "description": hints.get("outputs", {}).get(item["name"])
            or f"{_humanize(item['name'])} ({item['type']} output).",
        }
        for item in schema.get("outputs", [])
    ]
    widget_hints = hints.get("widgets", {})
    enriched["widgets"] = [
        {
            **item,
            "description": widget_hints.get(item["name"])
            or f"Configure {_humanize(item['name'])} ({item['type']}).",
        }
        for item in schema.get("widgets", [])
    ]
    enriched["enriched"] = True
    return enriched
