from __future__ import annotations

import re
from typing import Any

NODE_HINTS: dict[str, dict[str, Any]] = {
    "LoadAudio": {
        "description": "Load a WAV or FLAC file from the project into the graph cache.",
        "inputs": {},
        "outputs": {"output_0": "Planar PCM audio buffer at native sample rate."},
        "widgets": {
            "path": "Project-relative path to the audio file (e.g. assets/samples/podcast_denoise_demo.wav).",
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
    "SpeechTranslate": {
        "description": "Speech-to-speech translation for dialogue localization (source language → target language).",
        "widgets": {
            "model": "Speech translation model (e.g. SeamlessM4T).",
            "src_lang": "Source language (ISO 639-3 preferred: eng, spa, fra).",
            "tgt_lang": "Target language (ISO 639-3 preferred: eng, spa, fra).",
            "speaker_id": "Vocoder speaker 0–199 (timbre); not a gender control and not source cloning.",
        },
    },
    "TimbreTransfer": {
        "description": "Neural resynthesis / timbre transfer via RAVE-class VAEs (encode → latent → decode).",
        "widgets": {
            "model": "RAVE / timbre-transfer checkpoint (e.g. rave-v1).",
            "fidelity": "Reconstruction fidelity vs latent compactness (1 = faithful encode/decode).",
        },
    },
    "AudioToMIDI": {
        "description": "Transcribe pitched audio into a symbolic MIDI buffer (Basic Pitch class).",
        "widgets": {"model": "Audio-to-MIDI model (e.g. basic-pitch)."},
    },
    "MIDIToAudio": {
        "description": "Generate audio conditioned on MIDI melody and optional text prompt (MusicGen Melody).",
        "inputs": {
            "text": "Optional TEXT wire; when connected, overrides the local prompt widget.",
            "reference_audio": "Optional. Leave unwired — blending raw vocals into the melody conditioner makes output noisy.",
        },
        "widgets": {
            "model": "MIDI-to-audio model (e.g. MusicGen Melody).",
            "prompt": "Style or instrument description for generation.",
            "seed": "Random seed (−1 = random). Same seed + prompt → repeatable output.",
            "temperature": "Prefer ~0.7 for MusicGen Melody. 0 = greedy (often noisier); 1.0+ gets hissy.",
            "reference_weight": "Set 1.0 and wire Demucs vocals to reference_audio (HF path). Avoid ~0.5 blend with MIDI synth.",
            "max_new_tokens": "Length cap (~50 tok/s); runtime also caps to conditioner duration to avoid noisy freerun tails.",
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
            "model": "Text-to-audio model (MusicGen Small, Stable Audio Open, or ACE-Step 1.5 / 2B turbo).",
            "prompt": "Describe the sound you want to generate.",
            "seed": "Random seed (−1 = random). Same seed + prompt → repeatable output.",
            "lyrics": "ACE-Step: optional structured lyrics ([verse] / [chorus]); empty leans instrumental.",
            "seconds_total": "Stable Audio / ACE-Step: output length in seconds.",
            "num_inference_steps": "Diffusion / flow steps (ACE-Step turbo ≈ 8).",
            "guidance_scale": "Prompt adherence strength (ignored on ACE-Step turbo).",
            "negative_prompt": "Stable Audio: concepts to avoid.",
        },
    },
    "Video2Audio": {
        "description": (
            "Generic video→audio node — Diff-Foley is used as the example default. "
            "Browse Model Browser (Cmd+K → Find models) to install and switch to alternative "
            "video-to-audio models."
        ),
        "inputs": {
            "text": "Optional TEXT wire; when connected, overrides the local prompt widget (model-dependent).",
        },
        "widgets": {
            "model": (
                "Example default: Diff-Foley. This node is model-agnostic — open Model Browser "
                "to choose another video-to-audio model."
            ),
            "path": "Project-relative video (mp4/mov/…). Required for most models; some accept text-only.",
            "prompt": "Optional soundscape description (model-dependent; ignored by some backends).",
            "negative_prompt": "Concepts to avoid (model-dependent).",
            "duration": "Target length in seconds (default 8).",
            "num_steps": "Inference / diffusion steps (model-dependent).",
            "cfg_strength": "Classifier-free guidance strength (model-dependent).",
            "seed": "Random seed (−1 = random).",
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
    "AutomationToMIDI": {
        "description": "Read stepwise Hz CV (Quantizer / S&H) as MIDI notes for AI oscillators. Offline — not a live callback.",
        "inputs": {
            "cv": "AUTOMATION in Hz (typically Quantizer output).",
            "gate": "Optional AUTOMATION gate; notes only while the gate is high.",
        },
        "widgets": {
            "threshold": "Gate high when the curve is at or above this value.",
            "velocity": "Note-on velocity (0–1).",
            "midi_kind": "Usually score — generated from the rack, not a transcript.",
        },
    },
    "BeatTrack": {
        "description": "Find beats in audio and rebuild a Clock-style pulse train (plus half-time). Falls back to a wired Clock when the groove is too weak to track.",
        "inputs": {
            "audio": "Audio to analyze (typically GenerateAudio / a rendered hop).",
            "fallback_clock": "Pulse train used when onset/tempo confidence is low (stub audio, pads, silence).",
        },
        "widgets": {
            "fallback_bpm": "Metronome BPM when no fallback Clock is wired.",
            "pulse_ms": "Width of each emitted gate pulse.",
            "min_bpm": "Lowest tempo considered (helps avoid double-time).",
            "max_bpm": "Highest tempo considered (helps avoid half-time).",
            "tightness": "0 = regular grid at estimated BPM; 1 = snap each beat to a nearby onset.",
        },
    },
    "Preview": {
        "description": "Terminal sink for cached audition (audio) and/or transcript inspection (text).",
        "inputs": {
            "audio": "Audio to audition in the transport bar (also enables SaveAudio chaining).",
            "text": "Text (e.g. Whisper transcript) shown on the node and in Node Helper.",
        },
    },
    "MuxVideo": {
        "description": "Mux a source video file with generated AUDIO into a playable VIDEO clip (mp4).",
        "inputs": {
            "audio": "Generated or processed AUDIO to replace the source soundtrack.",
        },
        "widgets": {
            "path": "Project-relative source video (video stream copied; audio replaced).",
        },
    },
    "PreviewVideo": {
        "description": "Terminal sink for muxed VIDEO audition in Node Helper (HTML5 video player).",
        "inputs": {"video": "VIDEO clip from MuxVideo (or SaveVideo upstream passthrough)."},
    },
    "SaveVideo": {
        "description": "Copy a VIDEO clip into the project exports folder.",
        "inputs": {"video": "VIDEO clip to export (typically from PreviewVideo or MuxVideo)."},
        "widgets": {
            "path": "Folder under the project (e.g. exports).",
            "filename": "Base file name; a UTC timestamp is appended when written.",
        },
    },
    "Note": {
        "description": "Sticky comment on the canvas — documentation only, not part of the render graph.",
        "widgets": {
            "text": "Your comment. Shown on the node; edit here or in the inspector.",
        },
    },
    "VerifySamples": {
        "description": "Recompute PCM content hash and report sample count / rate / layout (SAMPLE_CHECK — not Authenticity).",
        "inputs": {"audio": "Any AUDIO cache from I/O, Processing, or AI hops."},
        "outputs": {
            "report": "SAMPLE_CHECK report with sample_check payload for Inspector.",
            "audio": "Passthrough of the verified AUDIO buffer.",
        },
    },
    "Meter": {
        "description": "Multi-channel peak/RMS meter. Auto-detects channel count and labels from AUDIO or AMBISONICS inlet metadata (FOA W/Y/Z/X, HOA ACN). Passthrough plus TEXT levels.",
        "inputs": {
            "audio": "AUDIO buffer to measure (optional if ambisonics is wired).",
            "ambisonics": "AMBISONICS (FOA/HOA) buffer to measure (optional if audio is wired).",
        },
        "outputs": {
            "audio": "Passthrough of the measured buffer (AUDIO or AMBISONICS at runtime).",
            "levels": "TEXT summary + §METER§ JSON (peak/RMS full + head/tail).",
        },
        "widgets": {
            "layout": "Channel labels: auto (default from inlet), stereo, mono, foa, hoa2, 5.1, …",
            "edge_fraction": "Fraction of clip used for head/tail peak windows (L/R debug).",
        },
    },
    "Normalize": {
        "description": "Adjust loudness to a target LUFS and peak ceiling.",
        "widgets": {
            "target_lufs": "Integrated loudness target (EBU R128 style).",
            "target_peak_db": "True-peak limit in dBFS.",
        },
    },
    "Granulate": {
        "description": "Offline granulator / grain cloud. Curves for size, hop, pitch spread, density, and stereo width; spray stacks overlaps; window shapes the grain envelope.",
        "inputs": {
            "audio": "Audio to granulate.",
            "grain_ms_curve": "AUTOMATION in ms — grain length over time (overrides grain_ms).",
            "hop_ms_curve": "AUTOMATION in ms — base onset spacing (overrides hop_ms).",
            "pitch_cents_curve": "AUTOMATION — ±cents random pitch per grain (overrides pitch_cents).",
            "density_curve": "AUTOMATION — extra grains/sec independent of hop (overrides density).",
            "width_curve": "AUTOMATION 0–1 — stereo bloom / pan spray (overrides width).",
        },
        "widgets": {
            "grain_ms": "Fallback grain length in ms when no grain curve is wired.",
            "hop_ms": "Fallback hop spacing in ms when no hop curve is wired.",
            "pitch_cents": "Fallback ±cents pitch scatter when no pitch curve is wired.",
            "density": "Fallback extra grains/sec when no density curve is wired (0 = hop only).",
            "spray": "Grains placed per onset (1 = single; higher = denser overlaps).",
            "width": "Fallback stereo width 0–1 when no width curve is wired.",
            "window": "Grain envelope: hann, tukey, exp (pointillist), or rect.",
            "window_alpha": "Tukey taper fraction (ignored for hann/exp).",
            "scatter_ms": "Max source/time jitter at full wet.",
            "wet_start": "Wet mix at the beginning (0 = dry/passthrough).",
            "wet_end": "Wet mix at the end (1 = fully granulated).",
            "seed": "RNG seed for scatter/pitch/pan (fixed seed → repeatable cloud).",
        },
    },
    "ChannelConvert": {
        "description": "Explicit upmix or downmix between channel layouts (ITU-R BS.775 for 5.1→stereo).",
        "widgets": {"layout": "Target layout: mono, stereo, 5.1, etc."},
    },
    "Pan": {
        "description": "Layout-agnostic equal-power panner (−1 left … +1 right). Collapses to mono drive, then images into the target layout (auto promotes mono → stereo).",
        "inputs": {
            "audio": "Any AUDIO (mono / stereo / surround).",
            "pan_curve": "Optional AUTOMATION pan (−1…+1) overriding the pan widget.",
        },
        "outputs": {"audio": "Panned AUDIO in output_layout."},
        "widgets": {
            "pan": "Static pan −1 (left) … +1 (right) when no curve is wired.",
            "output_layout": "Target bed: auto (mono→stereo), stereo, 5.1, 7.1, 7.1.4, …",
        },
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
    "TrajectoryAuthor": {
        "description": "Author a listener-relative XYZ path. Draw freehand on the pad or drag S/E (not live — Render to apply). Multi-ACCDOA: +X = left.",
        "widgets": {
            "start_x": "Start X (left+ / right−, Multi-ACCDOA).",
            "start_y": "Start Y (up).",
            "start_z": "Start Z (front).",
            "end_x": "End X (left+ / right−).",
            "end_y": "End Y.",
            "end_z": "End Z.",
            "duration_sec": "Path length in seconds. Locked to wired LoadAudio duration when audio is connected.",
            "sample_rate": "Sample rate. Locked to wired LoadAudio when audio is connected.",
            "points": "Drawn path as JSON [{t_sec,x,y,z},…] — overrides start/end when set (≥2 points). Times rescale to audio duration on render.",
            "object_id": "Label for the authored object.",
            "audio": "Optional audio — locks trajectory duration/sample_rate to the clip timebase.",
        },
    },
    "TrajectoryMonitor": {
        "description": "Passthrough XYZ monitor — wire authored trajectory (input) or extract (output) so both paths stay visible while Preview auditions stereo.",
        "widgets": {
            "role": "Monitor role: input (authored) or output (recovered).",
            "label": "Optional label shown in the trajectory panel.",
        },
    },
    "AmbisonicUpmix": {
        "description": "Neural mono/stereo → FOA Ambisonics (Helix). Optional TRAJECTORY conditions spatialization; stub encodes along XYZ.",
        "widgets": {"model": "Upmix model (helix-v0.7)."},
    },
    "BinauralRender": {
        "description": "Stereo → binaural headphones. Default stub (hrtf-binaural-v0); no applicable open neural model yet.",
        "inputs": {"audio": "Stereo (or mono) AUDIO to spatialize for headphones."},
        "outputs": {"audio": "2ch AUDIO with channel_layout=binaural."},
        "widgets": {
            "model": "Binaural model (hrtf-binaural-v0 stub default).",
            "strength": "Crossfeed amount (0–1) for the stub renderer.",
        },
    },
    "SpatialUpmix": {
        "description": "Stereo → multichannel bed (7.1.4). Default stub (stereo-atmos-bed-v0); no applicable open neural model yet.",
        "inputs": {"audio": "Mono/stereo AUDIO to expand into a channel bed."},
        "outputs": {"audio": "Multichannel AUDIO (7.1.4 / 7.1 / 5.1). Preview via ChannelConvert→stereo."},
        "widgets": {
            "model": "Upmix model (stereo-atmos-bed-v0 stub default).",
            "layout": "Target bed: 7.1.4 (Atmos), 7.1, or 5.1.",
        },
    },
    "AmbisonicTrajectoryExtract": {
        "description": "Extract XYZ DOA trajectory from FOA Ambisonics (SELD / intensity stub).",
        "widgets": {"model": "Trajectory extract model (dcase-seld-foa-multiaccdoa)."},
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
