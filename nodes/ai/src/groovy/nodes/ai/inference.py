from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.ndimage import median_filter

from groovy.executor.audio import AudioBuffer, StemsBuffer
from groovy.executor.authenticity import AuthenticityReport, ml_detection_stub, write_minimal_smf
from groovy.executor.cache import CacheStore
from groovy.executor.midi import MidiBuffer


def require_model(project_dir, model_id: str) -> None:
    model_id = resolve_model_id(model_id)
    marker = project_dir / ".groovy" / "models" / model_id / "installed.json"
    if not marker.exists():
        raise RuntimeError(
            f"Model not installed: {model_id}. Install it from Model Browser (Cmd+K) first."
        )


def run_denoise(cache: CacheStore, kwargs: dict) -> list[dict]:
    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "deepfilternet-v3"))
    strength = float(kwargs.get("strength", 1.0))
    buffer, pcm = cache.load_audio(audio_id)
    out = denoise_audio(pcm, model_id=model_id, strength=strength, sample_rate=buffer.sample_rate)
    out_buffer = AudioBuffer.from_planar(
        out, buffer.sample_rate, source_node_type="Denoise", channel_layout=buffer.channel_layout
    )
    cache.write_audio(out_buffer, out)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


DEFAULT_STEM_AZIMUTH: dict[str, float] = {
    "vocals": 0.0,
    "drums": -35.0,
    "bass": 0.0,
    "other": 40.0,
}

STEM_OUTPUT_ORDER = ("vocals", "drums", "bass", "other")


def resolve_model_id(model_id: str) -> str:
    aliases = {"demucs-v4-objects": "demucs-v4"}
    return aliases.get(model_id, model_id)


def run_separate_to_objects(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.executor.oba import ObjectScene

    model_id = str(kwargs.get("model", "demucs-v4-objects"))
    resolved = resolve_model_id(model_id)
    audio_id = kwargs["audio_id"]
    buffer, pcm = cache.load_audio(audio_id)
    from groovy.nodes.ai.model_params import bool_param, float_param, int_param

    _, stems = _write_stems_bundle(
        cache,
        pcm,
        sample_rate=buffer.sample_rate,
        channel_layout=buffer.channel_layout,
        model_id=resolved,
        shifts=int_param(kwargs, "shifts", 1),
        overlap=float_param(kwargs, "overlap", 0.25),
        segment=float_param(kwargs, "segment", 0.0),
        split=bool_param(kwargs, "split", True),
    )
    scene = ObjectScene.create(
        sample_rate=stems.sample_rate,
        frame_count=stems.frame_count,
        source_node_type="SeparateToObjects",
    )
    for name, buffer in stems.stems.items():
        scene.objects.append(
            {
                "id": f"obj_{name}",
                "name": name,
                "audio_id": buffer.id,
                "channels": buffer.channels,
                "position": {
                    "azimuth": DEFAULT_STEM_AZIMUTH.get(name, 0.0),
                    "elevation": 0.0,
                    "distance": 1.0,
                },
                "size": {"width": 0.15, "height": 0.1},
                "gain_db": 0.0,
                "metadata": {"source_node_type": "SeparateToObjects", "model": model_id},
            }
        )
    cache.write_object_scene(scene)
    return [{"type": "OBA", "oba_id": scene.id}]


def run_separate_stems(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import bool_param, float_param, int_param

    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "demucs-v4"))
    buffer, pcm = cache.load_audio(audio_id)
    stem_pcm, stems = _write_stems_bundle(
        cache,
        pcm,
        sample_rate=buffer.sample_rate,
        channel_layout=buffer.channel_layout,
        model_id=model_id,
        shifts=int_param(kwargs, "shifts", 1),
        overlap=float_param(kwargs, "overlap", 0.25),
        segment=float_param(kwargs, "segment", 0.0),
        split=bool_param(kwargs, "split", True),
    )
    _ = stems
    outputs: list[dict] = []
    for name in STEM_OUTPUT_ORDER:
        if name not in stem_pcm:
            continue
        out_buffer = AudioBuffer.from_planar(
            stem_pcm[name],
            buffer.sample_rate,
            source_node_type="SeparateStems",
            channel_layout=buffer.channel_layout,
        )
        cache.write_audio(out_buffer, stem_pcm[name])
        outputs.append({"type": "AUDIO", "cache_id": out_buffer.id, "name": name})
    return outputs


def _write_stems_bundle(
    cache: CacheStore,
    pcm: np.ndarray,
    *,
    sample_rate: int,
    channel_layout: str,
    model_id: str,
    shifts: int,
    overlap: float,
    segment: float,
    split: bool,
) -> tuple[dict[str, np.ndarray], StemsBuffer]:
    stem_pcm = separate_stems_audio(
        pcm,
        sample_rate=sample_rate,
        model_id=model_id,
        shifts=shifts,
        overlap=overlap,
        segment=segment,
        split=split,
    )
    stems = StemsBuffer.from_stem_pcm(
        stem_pcm, sample_rate, channel_layout=channel_layout
    )
    cache.write_stems(stems, stem_pcm)
    return stem_pcm, stems


def run_whisper_stt(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import float_param

    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "whisper-large-v3-turbo"))
    language = str(kwargs.get("language", "en"))
    temperature = float_param(kwargs, "temperature", 0.0)
    buffer, pcm = cache.load_audio(audio_id)
    text = transcribe_audio(
        pcm,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        language=language,
        temperature=temperature,
    )
    return [{"type": "TEXT", "text": text}]


def run_diarize_transcribe(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import float_param

    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "whisper-large-v3-turbo"))
    diarize_model = str(kwargs.get("diarize_model", "pyannote-diarization-3.1"))
    language = str(kwargs.get("language", "en"))
    temperature = float_param(kwargs, "temperature", 0.0)
    buffer, pcm = cache.load_audio(audio_id)
    text = diarize_and_transcribe(
        pcm,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        diarize_model=diarize_model,
        language=language,
        temperature=temperature,
    )
    return [{"type": "TEXT", "text": text}]


def run_tts(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import optional_seed, seed_param

    text = str(kwargs.get("transcript") or kwargs.get("text") or "Hello from GroovyUI.")
    model_id = str(kwargs.get("model", "kokoro-82m"))
    sample_rate = 48000
    reference_pcm = None
    reference_sample_rate = sample_rate
    # Worker serializes optional reference_audio as audio_id (same path as melody conditioning).
    if kwargs.get("audio_id"):
        ref_buf, reference_pcm = cache.load_audio(str(kwargs["audio_id"]))
        reference_sample_rate = int(ref_buf.sample_rate) or sample_rate
        sample_rate = reference_sample_rate
    pcm = synthesize_speech(
        text,
        sample_rate=sample_rate,
        model_id=model_id,
        seed=optional_seed(kwargs),
        stub_seed=seed_param(kwargs, fallback=text),
        reference_pcm=reference_pcm,
        reference_sample_rate=reference_sample_rate,
        reference_text=str(kwargs.get("reference_text") or ""),
    )
    out_buffer = AudioBuffer.from_planar(pcm, sample_rate, source_node_type="TTS")
    cache.write_audio(out_buffer, pcm)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_voice_convert(cache: CacheStore, kwargs: dict) -> list[dict]:
    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "rvc-v2-base"))
    buffer, pcm = cache.load_audio(audio_id)
    out = voice_convert_audio(pcm, sample_rate=buffer.sample_rate, model_id=model_id)
    out_buffer = AudioBuffer.from_planar(
        out, buffer.sample_rate, source_node_type="VoiceConvert", channel_layout=buffer.channel_layout
    )
    cache.write_audio(out_buffer, out)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def denoise_audio(
    pcm: np.ndarray,
    *,
    model_id: str,
    strength: float,
    sample_rate: int,
) -> np.ndarray:
    from groovy.nodes.ai.inference_env import deepfilternet_available, inference_stub_enabled

    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0:
        return pcm.copy()

    if model_id == "deepfilternet-v3":
        if deepfilternet_available() and not inference_stub_enabled():
            from groovy.nodes.ai.backends.deepfilternet_runner import denoise_pcm

            return denoise_pcm(pcm, sample_rate=sample_rate, strength=strength)
        if inference_stub_enabled():
            return _denoise_audio_stub(pcm, strength=strength, sample_rate=sample_rate)
        raise RuntimeError(
            "DeepFilterNet inference is not installed. Install deepfilternet-v3 from Model Browser (Cmd+K)."
        )

    return _denoise_audio_stub(pcm, strength=strength, sample_rate=sample_rate)


def _denoise_audio_stub(pcm: np.ndarray, *, strength: float, sample_rate: int) -> np.ndarray:
    _ = sample_rate
    out = pcm.copy()
    for ch in range(out.shape[0]):
        channel = out[ch]
        _, _, stft = signal.stft(channel, nperseg=1024)
        mag = np.abs(stft)
        noise_floor = np.percentile(mag, 20, axis=1, keepdims=True)
        mask = np.clip((mag - noise_floor) / (noise_floor + 1e-8), 0.0, 1.0)
        mask = 1.0 - strength * (1.0 - mask)
        cleaned = signal.istft(stft * mask, nperseg=1024)[1]
        if cleaned.shape[0] > channel.shape[0]:
            cleaned = cleaned[: channel.shape[0]]
        elif cleaned.shape[0] < channel.shape[0]:
            cleaned = np.pad(cleaned, (0, channel.shape[0] - cleaned.shape[0]))
        out[ch] = cleaned
    return out


def separate_stems_audio(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    shifts: int = 1,
    overlap: float = 0.25,
    segment: float = 0.0,
    split: bool = True,
) -> dict[str, np.ndarray]:
    from groovy.nodes.ai.inference_env import demucs_available, inference_stub_enabled

    if model_id in MODEL_ID_TO_DEMUCS:
        if demucs_available() and not inference_stub_enabled():
            from groovy.nodes.ai.backends.demucs_runner import separate_pcm_to_stems

            return separate_pcm_to_stems(
                pcm,
                sample_rate=sample_rate,
                model_id=model_id,
                shifts=shifts,
                overlap=overlap,
                segment=segment,
                split=split,
            )
        if inference_stub_enabled():
            return _separate_stems_stub(pcm, model_id=model_id)
        raise RuntimeError(
            "Demucs inference is not installed. Run: uv sync --group inference "
            "then install demucs-v4 from Model Browser (Cmd+K)."
        )

    return _separate_stems_stub(pcm, model_id=model_id)


MODEL_ID_TO_DEMUCS = {"demucs-v4", "demucs-v4-ht"}


def _separate_stems_stub(pcm: np.ndarray, *, model_id: str) -> dict[str, np.ndarray]:
    _ = model_id
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    mono = pcm.mean(axis=0)
    harmonic = median_filter(mono, size=31)
    percussive = mono - harmonic
    stem_mono = {
        "vocals": harmonic * 0.85,
        "drums": percussive,
        "bass": harmonic * 0.35,
        "other": harmonic * 0.15,
    }
    return {
        name: np.tile(wave, (pcm.shape[0], 1)) for name, wave in stem_mono.items()
    }


def transcribe_audio(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    language: str = "en",
    temperature: float = 0.0,
) -> str:
    from groovy.nodes.ai.inference_env import inference_stub_enabled, whisper_available

    if model_id in {"whisper-large-v3-turbo", "whisper-small-en"}:
        if whisper_available() and not inference_stub_enabled():
            from groovy.nodes.ai.backends.whisper_runner import transcribe_pcm

            return transcribe_pcm(
                pcm,
                sample_rate=sample_rate,
                model_id=model_id,
                language=language,
                temperature=temperature,
            )
        if inference_stub_enabled():
            return _transcribe_audio_stub(
                pcm,
                sample_rate=sample_rate,
                model_id=model_id,
                language=language,
                temperature=temperature,
            )
        raise RuntimeError(
            "Whisper inference is not installed. Run: uv sync --group inference "
            f"then install {model_id} from Model Browser (Cmd+K)."
        )

    return _transcribe_audio_stub(
        pcm,
        sample_rate=sample_rate,
        model_id=model_id,
        language=language,
        temperature=temperature,
    )


def _transcribe_audio_stub(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    language: str = "en",
    temperature: float = 0.0,
) -> str:
    _ = language, temperature
    if pcm.ndim == 1:
        mono = pcm.astype(np.float64)
    else:
        mono = pcm.mean(axis=0).astype(np.float64)
    duration = len(mono) / max(sample_rate, 1)
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
    fingerprint = int(np.sum((mono[: min(len(mono), 4096)] * 1_000_000).astype(np.int64)) % 1_000_000)
    return (
        f"[dev transcript via {model_id} lang={language} temp={temperature:.2f}] "
        f"dur={duration:.2f}s peak={peak:.3f} rms={rms:.3f} fp={fingerprint}"
    )


def diarize_and_transcribe(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    diarize_model: str = "pyannote-diarization-3.1",
    language: str = "en",
    temperature: float = 0.0,
) -> str:
    """Return speaker-labeled transcript (pyannote when available; else energy turns + Whisper)."""
    transcript = transcribe_audio(
        pcm,
        sample_rate=sample_rate,
        model_id=model_id,
        language=language,
        temperature=temperature,
    )
    turns = _speaker_turns(pcm, sample_rate=sample_rate, diarize_model=diarize_model)
    return _format_diarized_transcript(transcript, turns, diarize_model=diarize_model)


def _speaker_turns(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    diarize_model: str,
) -> list[tuple[float, float, str]]:
    """Return (start_s, end_s, speaker_id) turns."""
    try:
        from groovy.nodes.ai.backends.pyannote_runner import diarize_pcm

        return diarize_pcm(pcm, sample_rate=sample_rate, model_id=diarize_model)
    except Exception:
        return _energy_speaker_turns(pcm, sample_rate=sample_rate)


def _energy_speaker_turns(pcm: np.ndarray, *, sample_rate: int) -> list[tuple[float, float, str]]:
    if pcm.ndim == 1:
        mono = pcm.astype(np.float64)
    else:
        mono = pcm.mean(axis=0).astype(np.float64)
    if mono.size == 0:
        return [(0.0, 0.0, "SPEAKER_00")]
    hop = max(1, int(sample_rate * 0.5))
    frame = max(hop, int(sample_rate * 1.0))
    energies: list[float] = []
    for start in range(0, len(mono), hop):
        chunk = mono[start : start + frame]
        if chunk.size == 0:
            break
        energies.append(float(np.sqrt(np.mean(np.square(chunk)))))
    if not energies:
        duration = len(mono) / max(sample_rate, 1)
        return [(0.0, duration, "SPEAKER_00")]
    median = float(np.median(energies))
    voiced = [e > median * 0.35 for e in energies]
    turns: list[tuple[float, float, str]] = []
    speaker = 0
    i = 0
    while i < len(voiced):
        if not voiced[i]:
            i += 1
            continue
        j = i
        while j < len(voiced) and voiced[j]:
            j += 1
        start_s = i * hop / sample_rate
        end_s = min(len(mono), j * hop) / sample_rate
        turns.append((start_s, end_s, f"SPEAKER_{speaker:02d}"))
        speaker = 1 - speaker
        i = j
    if not turns:
        duration = len(mono) / max(sample_rate, 1)
        return [(0.0, duration, "SPEAKER_00")]
    return turns


def _format_diarized_transcript(
    transcript: str,
    turns: list[tuple[float, float, str]],
    *,
    diarize_model: str,
) -> str:
    parts = [p.strip() for p in transcript.replace("\n", " ").split(".") if p.strip()]
    if not parts:
        parts = [transcript.strip() or "(empty transcript)"]
    lines: list[str] = [f"# diarize={diarize_model} turns={len(turns)}"]
    for index, part in enumerate(parts):
        turn = turns[min(index, len(turns) - 1)]
        start_s, end_s, speaker = turn
        lines.append(f"[{start_s:06.2f}-{end_s:06.2f}] {speaker}: {part}.")
    return "\n".join(lines)


def synthesize_speech(
    text: str,
    *,
    sample_rate: int,
    model_id: str,
    seed: int | None = None,
    stub_seed: int | None = None,
    reference_pcm: np.ndarray | None = None,
    reference_sample_rate: int | None = None,
    reference_text: str = "",
) -> np.ndarray:
    from groovy.nodes.ai.inference_env import f5_tts_available, inference_stub_enabled

    effective_stub = stub_seed if stub_seed is not None else (seed if seed is not None else 0)

    if model_id == "kokoro-82m":
        if not inference_stub_enabled():
            from groovy.nodes.ai.backends.kokoro_runner import synthesize_pcm

            return synthesize_pcm(text, sample_rate=sample_rate)
        return _synthesize_speech_stub(
            text,
            sample_rate=sample_rate,
            model_id=model_id,
            seed=effective_stub,
            reference_pcm=reference_pcm,
        )

    if model_id == "f5-tts-base":
        if inference_stub_enabled():
            return _synthesize_speech_stub(
                text,
                sample_rate=sample_rate,
                model_id=model_id,
                seed=effective_stub,
                reference_pcm=reference_pcm,
            )
        if reference_pcm is None:
            raise RuntimeError(
                "F5-TTS voice cloning requires reference_audio. "
                "Wire LoadAudio → TTS reference_audio (Voice Cloning template)."
            )
        if not f5_tts_available():
            raise RuntimeError(
                "f5-tts is not installed. Install f5-tts-base from Model Browser (Cmd+K)."
            )
        from groovy.nodes.ai.backends.f5_tts_runner import synthesize_pcm as f5_synthesize

        return f5_synthesize(
            text,
            sample_rate=sample_rate,
            reference_pcm=reference_pcm,
            reference_sample_rate=int(reference_sample_rate or sample_rate),
            reference_text=reference_text,
            seed=seed,
        )

    if inference_stub_enabled():
        return _synthesize_speech_stub(
            text,
            sample_rate=sample_rate,
            model_id=model_id,
            seed=effective_stub,
            reference_pcm=reference_pcm,
        )

    raise RuntimeError(
        f"Unsupported TTS model for real inference: {model_id}. "
        "Install a supported model from Model Browser (kokoro-82m or f5-tts-base)."
    )


def _synthesize_speech_stub(
    text: str,
    *,
    sample_rate: int,
    model_id: str,
    seed: int = 0,
    reference_pcm: np.ndarray | None = None,
) -> np.ndarray:
    duration = min(3.0, max(0.5, len(text) * 0.05))
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # Slight pitch difference per model so stub A/B is audible; seed nudges frequency.
    base = 196.0 if "kokoro" in model_id else 220.0
    if "f5" in model_id or "sovits" in model_id or "cosyvoice" in model_id:
        base = 180.0
    freq = base + (seed % 17) * 3.0
    if reference_pcm is not None:
        # Nudge timbre from reference energy so clone graphs sound distinct in stub mode.
        ref = reference_pcm.astype(np.float64)
        if ref.ndim > 1:
            ref = ref.mean(axis=0)
        rms = float(np.sqrt(np.mean(ref * ref))) if ref.size else 0.0
        freq += min(40.0, rms * 80.0)
    tone = 0.2 * np.sin(2 * np.pi * freq * t)
    return tone.reshape(1, -1)


def voice_convert_audio(pcm: np.ndarray, *, sample_rate: int, model_id: str) -> np.ndarray:
    _ = model_id
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    ratio = 1.05
    out_channels = []
    for ch in pcm:
        new_len = int(len(ch) / ratio)
        out_channels.append(signal.resample(ch, new_len))
    max_len = max(len(c) for c in out_channels)
    padded = [np.pad(c, (0, max_len - len(c))) for c in out_channels]
    return np.stack(padded, axis=0)


def run_audio_to_midi(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import (
        bool_param,
        float_param,
        optional_frequency,
    )

    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "basic-pitch"))
    buffer, pcm = cache.load_audio(audio_id)
    midi, midi_bytes = audio_to_midi(
        pcm,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        onset_threshold=float_param(kwargs, "onset_threshold", 0.5),
        frame_threshold=float_param(kwargs, "frame_threshold", 0.3),
        minimum_note_length=float_param(kwargs, "minimum_note_length", 127.7),
        minimum_frequency=optional_frequency(kwargs, "minimum_frequency"),
        maximum_frequency=optional_frequency(kwargs, "maximum_frequency"),
        melodia_trick=bool_param(kwargs, "melodia_trick", True),
    )
    cache.write_midi(midi, midi_bytes)
    return [{"type": "MIDI", "midi_id": midi.id}]


def run_midi_to_audio(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import float_param, int_param, optional_seed, seed_param

    midi_id = kwargs["midi_id"]
    model_id = str(kwargs.get("model", "musicgen-melody-small"))
    prompt = str(kwargs.get("text") or kwargs.get("prompt") or "regenerated melody")
    midi = cache.load_midi(midi_id)
    sample_rate = midi.sample_rate
    reference_pcm = None
    if kwargs.get("audio_id"):
        _, reference_pcm = cache.load_audio(str(kwargs["audio_id"]))
    pcm = midi_to_audio_waveform(
        midi,
        sample_rate=sample_rate,
        model_id=model_id,
        prompt=prompt,
        reference_pcm=reference_pcm,
        max_new_tokens=int_param(kwargs, "max_new_tokens", 512),
        melody_weight=float_param(kwargs, "melody_weight", 0.55),
        reference_weight=float_param(kwargs, "reference_weight", 0.45),
        guidance_scale=float_param(kwargs, "guidance_scale", 3.0),
        temperature=float_param(kwargs, "temperature", 1.0),
        seed=optional_seed(kwargs),
        stub_seed=seed_param(kwargs, fallback=prompt + midi.id),
    )
    out_buffer = AudioBuffer.from_planar(pcm, sample_rate, source_node_type="MIDIToAudio")
    cache.write_audio(out_buffer, pcm)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_generate_audio(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import float_param, int_param, optional_seed, seed_param

    model_id = str(kwargs.get("model", "musicgen-small"))
    prompt = str(kwargs.get("text") or kwargs.get("prompt") or "ambient music")
    sample_rate = 48000
    midi = None
    if kwargs.get("midi_id"):
        midi = cache.load_midi(str(kwargs["midi_id"]))
    ref_pcm = None
    if kwargs.get("audio_id"):
        _, ref_pcm = cache.load_audio(str(kwargs["audio_id"]))
    pcm = generate_audio_waveform(
        prompt,
        sample_rate=sample_rate,
        model_id=model_id,
        midi=midi,
        reference_pcm=ref_pcm,
        max_new_tokens=int_param(kwargs, "max_new_tokens", 512),
        guidance_scale=float_param(kwargs, "guidance_scale", 3.0),
        temperature=float_param(kwargs, "temperature", 1.0),
        seed=optional_seed(kwargs),
        stub_seed=seed_param(kwargs, fallback=prompt),
    )
    out_buffer = AudioBuffer.from_planar(pcm, sample_rate, source_node_type="GenerateAudio")
    cache.write_audio(out_buffer, pcm)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_sing_from_midi(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import seed_param

    midi_id = kwargs["midi_id"]
    model_id = str(kwargs.get("model", "diffsinger-opencpop"))
    lyrics = str(kwargs.get("lyrics") or kwargs.get("text") or "la la la")
    midi = cache.load_midi(midi_id)
    sample_rate = midi.sample_rate
    ref_pcm = None
    if kwargs.get("audio_id"):
        _, ref_pcm = cache.load_audio(str(kwargs["audio_id"]))
    pcm = sing_from_midi_waveform(
        midi,
        lyrics=lyrics,
        sample_rate=sample_rate,
        model_id=model_id,
        reference_pcm=ref_pcm,
        stub_seed=seed_param(kwargs, fallback=lyrics),
    )
    out_buffer = AudioBuffer.from_planar(pcm, sample_rate, source_node_type="SingFromMIDI")
    cache.write_audio(out_buffer, pcm)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_deepfake_detect(cache: CacheStore, kwargs: dict) -> list[dict]:
    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "rawnet2-asvspoof"))
    threshold = float(kwargs.get("threshold", 0.5))
    buffer, pcm = cache.load_audio(audio_id)
    spoof_score = deepfake_score(pcm, model_id=model_id)
    ml_det = ml_detection_stub(model_id=model_id, spoof_score=spoof_score)
    from groovy.executor.authenticity import overall_label

    label, confidence, summary = overall_label(
        {"status": "missing", "contribution_class": "unknown"},
        ml_det,
        spoof_threshold=threshold,
    )
    report = AuthenticityReport.create(
        {
            "overall": {"label": label, "confidence": confidence, "summary": summary},
            "provenance_check": {
                "status": "missing",
                "sidecar_found": False,
                "chain_intact": None,
                "contribution_class": "unknown",
                "groovy_origin": False,
            },
            "ml_detection": ml_det,
        }
    )
    cache.write_authenticity(report)
    return [
        {"type": "AUTHENTICITY", "authenticity_id": report.id},
        {"type": "AUDIO", "cache_id": audio_id},
    ]


def audio_to_midi(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    minimum_note_length: float = 127.7,
    minimum_frequency: float | None = None,
    maximum_frequency: float | None = None,
    melodia_trick: bool = True,
) -> tuple[MidiBuffer, bytes]:
    from groovy.nodes.ai.inference_env import basic_pitch_available, inference_stub_enabled

    if model_id != "basic-pitch":
        raise RuntimeError(f"Unsupported audio-to-midi model: {model_id}")

    if basic_pitch_available() and not inference_stub_enabled():
        from groovy.nodes.ai.backends.basic_pitch_runner import transcribe_pcm_to_midi

        return transcribe_pcm_to_midi(
            pcm,
            sample_rate=sample_rate,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=minimum_note_length,
            minimum_frequency=minimum_frequency,
            maximum_frequency=maximum_frequency,
            melodia_trick=melodia_trick,
        )

    if inference_stub_enabled():
        return _audio_to_midi_stub(pcm, sample_rate=sample_rate)

    raise RuntimeError(
        "Basic Pitch inference is not installed. Run: uv sync --group inference "
        "then install basic-pitch from Model Browser (Cmd+K)."
    )


def _audio_to_midi_stub(pcm: np.ndarray, *, sample_rate: int) -> tuple[MidiBuffer, bytes]:
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    mono = pcm.mean(axis=0)
    frame_count = len(mono)
    midi = MidiBuffer.create(
        sample_rate=sample_rate,
        frame_count=frame_count,
        source_node_type="AudioToMIDI",
        midi_kind="transcript",
    )
    duration = max(0.5, frame_count / max(sample_rate, 1))
    mid_path = Path(tempfile.gettempdir()) / f"{midi.id}.mid"
    write_minimal_smf(mid_path, duration_sec=min(4.0, duration))
    return midi, mid_path.read_bytes()


def deepfake_score(pcm: np.ndarray, *, model_id: str) -> float:
    _ = model_id
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    mono = pcm.mean(axis=0)
    if len(mono) == 0:
        return 0.5
    zcr = np.mean(np.abs(np.diff(np.sign(mono))))
    spectral_flatness = float(np.mean(median_filter(np.abs(np.fft.rfft(mono)), size=5)))
    score = min(0.95, max(0.05, 0.35 + zcr * 2.0 + spectral_flatness * 0.01))
    return score


def midi_to_audio_waveform(
    midi: MidiBuffer,
    *,
    sample_rate: int,
    model_id: str,
    prompt: str,
    reference_pcm: np.ndarray | None = None,
    max_new_tokens: int = 512,
    melody_weight: float = 0.55,
    reference_weight: float = 0.45,
    guidance_scale: float = 3.0,
    temperature: float = 1.0,
    seed: int | None = None,
    stub_seed: int | None = None,
) -> np.ndarray:
    from groovy.nodes.ai.inference_env import inference_stub_enabled, musicgen_melody_available

    if model_id != "musicgen-melody-small":
        raise RuntimeError(f"Unsupported midi-to-audio model: {model_id}")

    if musicgen_melody_available() and not inference_stub_enabled():
        from groovy.nodes.ai.backends.musicgen_melody_runner import regenerate_audio_from_midi

        return regenerate_audio_from_midi(
            midi,
            sample_rate=sample_rate,
            prompt=prompt,
            reference_pcm=reference_pcm,
            max_new_tokens=max_new_tokens,
            melody_weight=melody_weight,
            reference_weight=reference_weight,
            guidance_scale=guidance_scale,
            temperature=temperature,
            seed=seed,
        )

    if inference_stub_enabled():
        return _midi_to_audio_stub(
            midi,
            sample_rate=sample_rate,
            prompt=prompt,
            seed=stub_seed if stub_seed is not None else (seed if seed is not None else 0),
        )

    raise RuntimeError(
        "MusicGen Melody inference is not installed. Run: ./scripts/setup-inference.sh "
        "(requires torch, torchaudio, transformers) then install musicgen-melody-small from Model Browser."
    )


def _midi_to_audio_stub(
    midi: MidiBuffer, *, sample_rate: int, prompt: str, seed: int = 0
) -> np.ndarray:
    _ = prompt
    duration = max(0.5, midi.frame_count / sample_rate)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    nudge = seed % 7
    f1 = 220 + nudge * 20
    f2 = 330 + nudge * 15
    tone = 0.15 * (np.sin(2 * np.pi * f1 * t) + 0.7 * np.sin(2 * np.pi * f2 * t))
    return tone.reshape(1, -1)


def generate_audio_waveform(
    prompt: str,
    *,
    sample_rate: int,
    model_id: str,
    midi: MidiBuffer | None = None,
    reference_pcm: np.ndarray | None = None,
    max_new_tokens: int = 512,
    guidance_scale: float = 3.0,
    temperature: float = 1.0,
    seed: int | None = None,
    stub_seed: int | None = None,
) -> np.ndarray:
    from groovy.nodes.ai.inference_env import inference_stub_enabled, musicgen_small_available

    _ = reference_pcm
    effective_stub = stub_seed if stub_seed is not None else (seed if seed is not None else 0)
    if model_id == "musicgen-small":
        if musicgen_small_available() and not inference_stub_enabled():
            from groovy.nodes.ai.backends.musicgen_small_runner import generate_from_text

            return generate_from_text(
                prompt,
                sample_rate=sample_rate,
                max_new_tokens=max_new_tokens,
                guidance_scale=guidance_scale,
                temperature=temperature,
                seed=seed,
            )
        if inference_stub_enabled():
            return _generate_audio_stub(
                prompt, sample_rate=sample_rate, midi=midi, model_id=model_id, seed=effective_stub
            )
        raise RuntimeError(
            "MusicGen Small inference is not installed. Run: ./scripts/setup-inference.sh "
            "(requires torch, transformers) then install musicgen-small from Model Browser."
        )

    if inference_stub_enabled():
        return _generate_audio_stub(
            prompt, sample_rate=sample_rate, midi=midi, model_id=model_id, seed=effective_stub
        )

    raise RuntimeError(f"Unsupported text-to-music model for real inference: {model_id}")


def _generate_audio_stub(
    prompt: str,
    *,
    sample_rate: int,
    midi: MidiBuffer | None,
    model_id: str,
    seed: int = 0,
) -> np.ndarray:
    nudge = seed % 11
    duration = 2.0
    if midi is not None:
        duration = max(1.0, midi.frame_count / sample_rate)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    f1 = 130 + nudge * 12
    f2 = 196 + nudge * 8
    tone = 0.12 * (np.sin(2 * np.pi * f1 * t) + 0.5 * np.sin(2 * np.pi * f2 * t))
    if midi is not None and model_id == "musicgen-melody-small":
        melody = midi_to_audio_waveform(
            midi, sample_rate=sample_rate, model_id=model_id, prompt=prompt, stub_seed=seed
        )
        min_len = min(tone.shape[-1], melody.shape[-1])
        tone = tone[:min_len] + 0.5 * melody[0, :min_len]
        tone = tone.reshape(1, -1)
    else:
        tone = tone.reshape(1, -1)
    return tone


def sing_from_midi_waveform(
    midi: MidiBuffer,
    *,
    lyrics: str,
    sample_rate: int,
    model_id: str,
    reference_pcm: np.ndarray | None = None,
    stub_seed: int | None = None,
) -> np.ndarray:
    _ = model_id, reference_pcm
    duration = max(1.0, midi.frame_count / sample_rate)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    nudge = (stub_seed if stub_seed is not None else sum(ord(c) for c in lyrics)) % 9
    carrier = 440 + nudge * 10
    # vocal-like AM envelope from syllable count
    syllables = max(1, len(lyrics.split()))
    env = 0.5 + 0.5 * np.sin(2 * np.pi * syllables * t / duration)
    tone = 0.18 * env * np.sin(2 * np.pi * carrier * t)
    vibrato = 0.03 * np.sin(2 * np.pi * 5.5 * t)
    tone = tone * (1.0 + vibrato)
    return tone.reshape(1, -1)
