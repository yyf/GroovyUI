from __future__ import annotations

import json
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


def run_translate_text(cache: CacheStore, kwargs: dict) -> list[dict]:
    _ = cache
    text = str(kwargs.get("text") or kwargs.get("transcript") or "")
    model_id = str(kwargs.get("model", "m2m100-418m"))
    src_lang = str(kwargs.get("src_lang", "en"))
    tgt_lang = str(kwargs.get("tgt_lang", "zh"))
    translated = translate_text_content(
        text,
        model_id=model_id,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
    )
    return [{"type": "TEXT", "text": translated}]


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


def run_speech_translate(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import int_param

    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "seamless-m4t-v2-large"))
    src_lang = str(kwargs.get("src_lang", "eng"))
    tgt_lang = str(kwargs.get("tgt_lang", "spa"))
    speaker_id = int_param(kwargs, "speaker_id", 0)
    buffer, pcm = cache.load_audio(audio_id)
    out = speech_translate_audio(
        pcm,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        speaker_id=speaker_id,
    )
    out_buffer = AudioBuffer.from_planar(
        out,
        buffer.sample_rate,
        source_node_type="SpeechTranslate",
        channel_layout=buffer.channel_layout,
    )
    cache.write_audio(out_buffer, out)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_timbre_transfer(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import float_param

    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "rave-v1"))
    fidelity = float_param(kwargs, "fidelity", 1.0)
    buffer, pcm = cache.load_audio(audio_id)
    out = timbre_transfer_audio(
        pcm,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        fidelity=fidelity,
        project_dir=cache.project_dir,
    )
    out_buffer = AudioBuffer.from_planar(
        out, buffer.sample_rate, source_node_type="TimbreTransfer", channel_layout=buffer.channel_layout
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


def translate_text_content(
    text: str,
    *,
    model_id: str,
    src_lang: str = "en",
    tgt_lang: str = "zh",
) -> str:
    """Text MT (M2M100 / MADLAD / Opus when installed; stub otherwise)."""
    from groovy.nodes.ai.backends.text_mt_runner import HF_MODEL_IDS
    from groovy.nodes.ai.inference_env import inference_stub_enabled, text_mt_available

    if model_id not in HF_MODEL_IDS:
        raise RuntimeError(
            f"Unsupported TranslateText model {model_id!r}. "
            f"Supported: {', '.join(sorted(HF_MODEL_IDS))}."
        )
    if text_mt_available() and not inference_stub_enabled():
        from groovy.nodes.ai.backends.text_mt_runner import translate_text

        return translate_text(text, model_id=model_id, src_lang=src_lang, tgt_lang=tgt_lang)
    if inference_stub_enabled():
        return _translate_text_stub(text, model_id=model_id, src_lang=src_lang, tgt_lang=tgt_lang)
    raise RuntimeError(
        f"{model_id} needs torch + transformers (+ sentencepiece) for Real inference. "
        "Install the model from Model Browser, or switch Settings → Inference to Stub."
    )


def _translate_text_stub(
    text: str,
    *,
    model_id: str,
    src_lang: str,
    tgt_lang: str,
) -> str:
    from groovy.nodes.ai.backends.text_mt_runner import OPUS_FIXED_PAIR, normalize_lang_iso2

    source = (text or "").strip()
    src = normalize_lang_iso2(src_lang, default="en")
    tgt = normalize_lang_iso2(tgt_lang, default="zh")
    if model_id in OPUS_FIXED_PAIR:
        src, tgt = OPUS_FIXED_PAIR[model_id]
    if not source:
        return ""
    # Deterministic stub so Preview shows a distinct translated string in CI.
    return f"[{model_id}|{src}->{tgt}] {source}"


def speech_translate_audio(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    src_lang: str = "eng",
    tgt_lang: str = "spa",
    speaker_id: int = 0,
) -> np.ndarray:
    """Speech-to-speech localization (SeamlessM4T when installed; stub otherwise)."""
    from groovy.nodes.ai.inference_env import inference_stub_enabled, seamless_available

    if model_id == "seamless-m4t-v2-large":
        if seamless_available() and not inference_stub_enabled():
            from groovy.nodes.ai.backends.seamless_runner import translate_pcm

            return translate_pcm(
                pcm,
                sample_rate=sample_rate,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
                speaker_id=speaker_id,
            )
        if inference_stub_enabled():
            return _speech_translate_stub(
                pcm,
                sample_rate=sample_rate,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
                speaker_id=speaker_id,
            )
        raise RuntimeError(
            "seamless-m4t-v2-large needs torch + transformers for Real inference. "
            "Install the model from Model Browser, or switch Settings → Inference to Stub."
        )
    return _speech_translate_stub(
        pcm,
        sample_rate=sample_rate,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        speaker_id=speaker_id,
    )


def _speech_translate_stub(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    src_lang: str,
    tgt_lang: str,
    speaker_id: int = 0,
) -> np.ndarray:
    """Audible stand-in: mild retune + band emphasis keyed by language codes."""
    _ = sample_rate
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    # Different tgt codes nudge pitch so A/B eng→spa vs eng→fra is distinguishable in Stub.
    nudge = 1.0 + (sum(ord(c) for c in (tgt_lang or "spa")[:3]) % 7) * 0.01
    src_bias = 0.97 + (sum(ord(c) for c in (src_lang or "eng")[:3]) % 5) * 0.005
    # speaker_id shifts pitch so stub can stand in for “different vocoder voice”.
    spk = 1.0 + (int(speaker_id) % 20) * 0.004
    ratio = max(0.85, min(1.15, nudge * src_bias * spk))
    out_channels = []
    for ch in pcm:
        new_len = max(1, int(round(len(ch) / ratio)))
        resampled = signal.resample(ch.astype(np.float64), new_len).astype(np.float32)
        # Mild high-shelf attenuation — “re-voiced” not identical.
        if len(resampled) > 8:
            kernel = np.array([0.25, 0.5, 0.25], dtype=np.float32)
            pad = np.pad(resampled, (1, 1), mode="edge")
            smoothed = np.convolve(pad, kernel, mode="valid")
            resampled = 0.65 * resampled + 0.35 * smoothed
        out_channels.append(resampled)
    max_len = max(len(c) for c in out_channels)
    padded = [np.pad(c, (0, max_len - len(c))) for c in out_channels]
    return np.stack(padded, axis=0)


def timbre_transfer_audio(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    fidelity: float = 1.0,
    project_dir: Path | None = None,
) -> np.ndarray:
    """RAVE-class encode/decode timbre transfer (real TorchScript when installed)."""
    from groovy.nodes.ai.inference_env import inference_stub_enabled, rave_available

    fidelity = float(np.clip(fidelity, 0.0, 1.0))
    if model_id == "rave-v1":
        if rave_available() and not inference_stub_enabled():
            from groovy.nodes.ai.backends.rave_runner import transfer_pcm

            root = Path(project_dir) if project_dir else Path.cwd()
            model_path = root / ".groovy" / "models" / model_id / "sol_ordinario_fast.ts"
            return transfer_pcm(
                pcm,
                sample_rate=sample_rate,
                model_path=model_path,
                fidelity=fidelity,
            )
        if inference_stub_enabled():
            return _timbre_transfer_audio_stub(pcm, fidelity=fidelity)
        raise RuntimeError(
            "RAVE inference is not ready. Install rave-v1 from Model Browser (Cmd+K) "
            "(downloads TorchScript weights; requires torch)."
        )
    return _timbre_transfer_audio_stub(pcm, fidelity=fidelity)


def _timbre_transfer_audio_stub(pcm: np.ndarray, *, fidelity: float) -> np.ndarray:
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    # Stub: mild spectral blur + soft saturation so A/B is audible without real RAVE weights.
    out = pcm.astype(np.float64).copy()
    blur = max(3, int(round(5 + (1.0 - fidelity) * 40)))
    if blur % 2 == 0:
        blur += 1
    for ch in range(out.shape[0]):
        smoothed = median_filter(out[ch], size=blur)
        wet = fidelity * out[ch] + (1.0 - fidelity) * smoothed
        out[ch] = np.tanh(wet * (1.15 + 0.35 * (1.0 - fidelity)))
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * 0.9).astype(np.float64)


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
        max_new_tokens=int_param(kwargs, "max_new_tokens", 256),
        melody_weight=float_param(kwargs, "melody_weight", 1.0),
        reference_weight=float_param(kwargs, "reference_weight", 0.0),
        guidance_scale=float_param(kwargs, "guidance_scale", 3.0),
        temperature=float_param(kwargs, "temperature", 0.7),
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
        guidance_scale=float_param(
            kwargs,
            "guidance_scale",
            (
                7.0
                if model_id == "stable-audio-open-1.0"
                else 1.0
                if model_id in ("ace-step-1.5", "ace-step-1.5-2b-turbo")
                else 3.0
            ),
        ),
        temperature=float_param(kwargs, "temperature", 1.0),
        seconds_total=float_param(
            kwargs,
            "seconds_total",
            15.0 if model_id in ("ace-step-1.5", "ace-step-1.5-2b-turbo") else 10.0,
        ),
        num_inference_steps=int_param(
            kwargs,
            "num_inference_steps",
            8 if model_id in ("ace-step-1.5", "ace-step-1.5-2b-turbo") else 100,
        ),
        negative_prompt=str(kwargs.get("negative_prompt") or "Low quality."),
        lyrics=str(kwargs.get("lyrics") or ""),
        seed=optional_seed(kwargs),
        stub_seed=seed_param(kwargs, fallback=prompt),
    )
    out_buffer = AudioBuffer.from_planar(pcm, sample_rate, source_node_type="GenerateAudio")
    cache.write_audio(out_buffer, pcm)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_video2audio(cache: CacheStore, kwargs: dict) -> list[dict]:
    from pathlib import Path

    from groovy.executor.project_paths import resolve_project_media_path
    from groovy.nodes.ai.model_params import float_param, int_param, optional_seed, seed_param

    model_id = str(kwargs.get("model", "diff-foley"))
    prompt = str(kwargs.get("text") or kwargs.get("prompt") or "")
    path_raw = str(kwargs.get("path") or "").strip()
    video_path: Path | None = None
    if path_raw:
        video_path, _ = resolve_project_media_path(cache, path_raw)
    # Diff-Foley native 16 kHz (future backends may override).
    sample_rate = 16000 if model_id == "diff-foley" else 44100
    pcm = video2audio_waveform(
        prompt,
        video_path=video_path,
        sample_rate=sample_rate,
        model_id=model_id,
        duration=float_param(kwargs, "duration", 8.0),
        num_steps=int_param(kwargs, "num_steps", 25),
        cfg_strength=float_param(kwargs, "cfg_strength", 4.5),
        negative_prompt=str(kwargs.get("negative_prompt") or ""),
        seed=optional_seed(kwargs),
        stub_seed=seed_param(kwargs, fallback=prompt or path_raw or model_id),
    )
    out_buffer = AudioBuffer.from_planar(pcm, sample_rate, source_node_type="Video2Audio")
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
            "ml_detection": ml_det,
        }
    )
    cache.write_authenticity(report)
    return [
        {"type": "AUTHENTICITY", "authenticity_id": report.id},
        {"type": "AUDIO", "cache_id": audio_id},
    ]


def run_embed_watermark(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import float_param, int_param

    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "audioseal-16bit"))
    message_id = int_param(kwargs, "message_id", 42)
    strength = float_param(kwargs, "strength", 1.0)
    buffer, pcm = cache.load_audio(audio_id)
    out = embed_watermark_audio(
        pcm,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        message_id=message_id,
        strength=strength,
    )
    out_buffer = AudioBuffer.from_planar(
        out,
        buffer.sample_rate,
        source_node_type="EmbedWatermark",
        channel_layout=buffer.channel_layout,
    )
    cache.write_audio(out_buffer, out)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_detect_watermark(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.model_params import float_param

    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "audioseal-16bit"))
    threshold = float_param(kwargs, "threshold", 0.5)
    buffer, pcm = cache.load_audio(audio_id)
    report = detect_watermark_audio(
        pcm,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        threshold=threshold,
    )
    return [
        {"type": "TEXT", "text": json.dumps(report, indent=2)},
        {"type": "AUDIO", "cache_id": audio_id},
    ]


def embed_watermark_audio(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    message_id: int = 42,
    strength: float = 1.0,
) -> np.ndarray:
    from groovy.nodes.ai.inference_env import audioseal_available, inference_stub_enabled

    if model_id != "audioseal-16bit":
        raise RuntimeError(f"Unsupported watermark model: {model_id}")

    if audioseal_available() and not inference_stub_enabled():
        from groovy.nodes.ai.backends.audioseal_runner import embed_watermark_pcm

        return embed_watermark_pcm(
            pcm,
            sample_rate=sample_rate,
            message_id=message_id,
            strength=strength,
        )
    if inference_stub_enabled():
        from groovy.nodes.ai.backends.audioseal_runner import embed_watermark_stub

        return embed_watermark_stub(pcm, message_id=message_id, strength=strength, sample_rate=sample_rate)
    raise RuntimeError(
        "AudioSeal inference is not installed. Install audioseal-16bit from Model Browser (Cmd+K)."
    )


def detect_watermark_audio(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    threshold: float = 0.5,
) -> dict[str, object]:
    from groovy.nodes.ai.inference_env import audioseal_available, inference_stub_enabled

    if model_id != "audioseal-16bit":
        raise RuntimeError(f"Unsupported watermark model: {model_id}")

    if audioseal_available() and not inference_stub_enabled():
        from groovy.nodes.ai.backends.audioseal_runner import detect_watermark_pcm

        probability, message_id, bits = detect_watermark_pcm(
            pcm,
            sample_rate=sample_rate,
            threshold=threshold,
        )
        backend = "audioseal"
    elif inference_stub_enabled():
        from groovy.nodes.ai.backends.audioseal_runner import detect_watermark_stub

        probability, message_id, bits = detect_watermark_stub(
            pcm, threshold=threshold, sample_rate=sample_rate
        )
        backend = "stub"
    else:
        raise RuntimeError(
            "AudioSeal inference is not installed. Install audioseal-16bit from Model Browser (Cmd+K)."
        )

    detected = probability >= threshold
    return {
        "model": model_id,
        "backend": backend,
        "watermark_detected": detected,
        "detection_probability": round(probability, 4),
        "threshold": threshold,
        "message_id": message_id,
        "message_bits": bits,
    }


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
    max_new_tokens: int = 256,
    melody_weight: float = 1.0,
    reference_weight: float = 0.0,
    guidance_scale: float = 3.0,
    temperature: float = 0.7,
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
    seconds_total: float = 10.0,
    num_inference_steps: int = 100,
    negative_prompt: str = "Low quality.",
    lyrics: str = "",
    seed: int | None = None,
    stub_seed: int | None = None,
) -> np.ndarray:
    from groovy.nodes.ai.inference_env import (
        ace_step_available,
        inference_stub_enabled,
        musicgen_small_available,
        stable_audio_available,
    )

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

    if model_id == "stable-audio-open-1.0":
        if inference_stub_enabled():
            return _generate_audio_stub(
                prompt, sample_rate=sample_rate, midi=midi, model_id=model_id, seed=effective_stub
            )
        if not stable_audio_available():
            raise RuntimeError(
                "Stable Audio Open inference is not installed. "
                "Install stable-audio-open-1.0 from Model Browser (Cmd+K) "
                "(requires diffusers + torch; accept the HF model license and set a token)."
            )
        from groovy.nodes.ai.backends.stable_audio_runner import generate_from_text as sa_generate

        return sa_generate(
            prompt,
            sample_rate=sample_rate,
            seconds_total=seconds_total,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            negative_prompt=negative_prompt,
            seed=seed,
        )

    if model_id in ("ace-step-1.5", "ace-step-1.5-2b-turbo"):
        if inference_stub_enabled():
            return _generate_audio_stub(
                prompt, sample_rate=sample_rate, midi=midi, model_id=model_id, seed=effective_stub
            )
        if not ace_step_available():
            raise RuntimeError(
                "ACE-Step 1.5 inference is not installed. "
                f"Install {model_id} from Model Browser (Cmd+K) "
                "(requires diffusers with AceStepPipeline + torch)."
            )
        from groovy.nodes.ai.backends.ace_step_runner import generate_from_text as ace_generate

        return ace_generate(
            prompt,
            sample_rate=sample_rate,
            model_id=model_id,
            seconds_total=seconds_total,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            lyrics=lyrics,
            seed=seed,
        )

    if inference_stub_enabled():
        return _generate_audio_stub(
            prompt, sample_rate=sample_rate, midi=midi, model_id=model_id, seed=effective_stub
        )

    raise RuntimeError(f"Unsupported text-to-music model for real inference: {model_id}")


def video2audio_waveform(
    prompt: str,
    *,
    video_path,
    sample_rate: int,
    model_id: str,
    duration: float = 8.0,
    num_steps: int = 25,
    cfg_strength: float = 4.5,
    negative_prompt: str = "",
    seed: int | None = None,
    stub_seed: int | None = None,
) -> np.ndarray:
    """Model-agnostic video±text → audio. Dispatch by registry ``model_id``."""
    _ = negative_prompt  # Reserved for future text-conditioned V2A backends.
    from groovy.nodes.ai.inference_env import inference_stub_enabled

    effective_stub = stub_seed if stub_seed is not None else (seed if seed is not None else 0)
    if inference_stub_enabled():
        return _video2audio_stub(
            prompt,
            sample_rate=sample_rate,
            duration=duration,
            seed=effective_stub,
            has_video=video_path is not None,
        )

    if video_path is None and not prompt.strip():
        raise RuntimeError("Video2Audio needs a video path and/or a text prompt.")

    if model_id == "diff-foley":
        return _video2audio_diff_foley(
            prompt,
            video_path=video_path,
            sample_rate=sample_rate,
            duration=duration,
            num_steps=num_steps,
            cfg_strength=cfg_strength,
            seed=seed,
        )

    # Future backends (HunyuanVideo-Foley, FoleyCrafter, …) branch here.
    raise RuntimeError(
        f"Unsupported Video2Audio model for real inference: {model_id}. "
        "Install a published video-to-audio model from Model Browser (Cmd+K)."
    )


def _video2audio_diff_foley(
    prompt: str,
    *,
    video_path,
    sample_rate: int,
    duration: float,
    num_steps: int,
    cfg_strength: float,
    seed: int | None,
) -> np.ndarray:
    _ = prompt  # Diff-Foley is video-conditioned only.
    if video_path is None:
        raise RuntimeError(
            "Diff-Foley requires a video file path (text-only is not supported). "
            "Set the Video2Audio path widget, or pick a model that supports text±video."
        )
    from groovy.nodes.ai.inference_env import diff_foley_available

    if not diff_foley_available():
        raise RuntimeError(
            "Diff-Foley inference deps are not installed. Install diff-foley from "
            "Model Browser (Cmd+K) (requires torch, librosa, omegaconf)."
        )
    from groovy.nodes.ai.backends.diff_foley_runner import generate_from_video

    return generate_from_video(
        video_path=video_path,
        sample_rate=sample_rate,
        duration=duration,
        num_steps=num_steps,
        cfg_strength=cfg_strength,
        seed=seed,
    )


def _video2audio_stub(
    prompt: str,
    *,
    sample_rate: int,
    duration: float,
    seed: int = 0,
    has_video: bool = False,
) -> np.ndarray:
    """Deterministic placeholder for CI / Inference=Stub — not real V2A inference."""
    nudge = seed % 13
    seconds = max(1.0, min(float(duration), 30.0))
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    # Slightly different spectrum when a video path was provided vs text-only.
    f1 = (110 if has_video else 98) + nudge * 9
    f2 = (165 if has_video else 147) + nudge * 7
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * (0.25 + nudge * 0.02) * t)
    tone = 0.1 * envelope * (np.sin(2 * np.pi * f1 * t) + 0.4 * np.sin(2 * np.pi * f2 * t))
    if prompt:
        tone = tone * (0.85 + 0.15 * ((sum(ord(c) for c in prompt) % 7) / 7.0))
    return tone.astype(np.float64).reshape(1, -1)


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


def run_ambisonic_upmix(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.executor.ambisonics import AmbisonicBuffer
    from groovy.executor.trajectory import TrajectoryBuffer, azimuth_elevation_to_xyz
    from groovy.nodes.ai.backends.helix_runner import ambisonic_upmix_pcm

    audio_id = kwargs.get("audio_id") or (kwargs.get("audio") or {}).get("cache_id")
    if not audio_id:
        raise RuntimeError("AmbisonicUpmix requires audio input")
    model_id = str(kwargs.get("model", "helix-v0.7"))
    buffer, pcm = cache.load_audio(str(audio_id))

    trajectory: TrajectoryBuffer | None = None
    traj_id = kwargs.get("trajectory_id")
    if not traj_id and isinstance(kwargs.get("trajectory"), dict):
        traj_id = kwargs["trajectory"].get("trajectory_id")
    if traj_id:
        trajectory = cache.load_trajectory(str(traj_id))

    if trajectory is not None:
        xyz = trajectory.resample_xyz(pcm.shape[-1] if pcm.ndim > 1 else len(pcm))
    else:
        # Default front-left → front-right sweep when no authored trajectory.
        x0, y0, z0 = azimuth_elevation_to_xyz(45.0, 0.0)
        x1, y1, z1 = azimuth_elevation_to_xyz(-45.0, 0.0)
        frames = pcm.shape[-1] if pcm.ndim > 1 else len(pcm)
        alpha = np.linspace(0.0, 1.0, frames)
        xyz = np.vstack(
            [
                x0 + alpha * (x1 - x0),
                y0 + alpha * (y1 - y0),
                z0 + alpha * (z1 - z0),
            ]
        )

    foa = ambisonic_upmix_pcm(
        pcm,
        xyz=xyz,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        project_dir=cache.project_dir,
    )
    out = AmbisonicBuffer.from_pcm(
        foa,
        buffer.sample_rate,
        layout_order=1,
        source_node_type="AmbisonicUpmix",
        spatial_meta={
            "channel_ordering": "ACN",
            "normalization": "SN3D",
            "model": model_id,
            "trajectory_id": trajectory.id if trajectory else None,
        },
    )
    cache.write_ambisonics(out, foa)
    return [{"type": "AMBISONICS", "ambisonics_id": out.id}]


def run_ambisonic_trajectory_extract(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.backends.seld_runner import extract_trajectory_from_foa

    ambi_id = kwargs.get("ambisonics_id")
    if not ambi_id and isinstance(kwargs.get("ambisonics"), dict):
        ambi_id = kwargs["ambisonics"].get("ambisonics_id")
    if not ambi_id:
        raise RuntimeError("AmbisonicTrajectoryExtract requires ambisonics input")
    model_id = str(kwargs.get("model", "dcase-seld-foa-multiaccdoa"))
    buffer, pcm = cache.load_ambisonics(str(ambi_id))
    trajectory = extract_trajectory_from_foa(
        pcm,
        sample_rate=buffer.sample_rate,
        frame_count=buffer.frame_count,
        model_id=model_id,
        project_dir=cache.project_dir,
        spatial_meta={"source_ambisonics_id": buffer.id, "model": model_id},
    )
    cache.write_trajectory(trajectory)
    return [{"type": "TRAJECTORY", "trajectory_id": trajectory.id}]


def run_binaural_render(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.backends.spatial_upmix_runner import binaural_render_pcm

    audio_id = kwargs.get("audio_id") or (kwargs.get("audio") or {}).get("cache_id")
    if not audio_id:
        raise RuntimeError("BinauralRender requires audio input")
    model_id = str(kwargs.get("model", "hrtf-binaural-v0"))
    strength = float(kwargs.get("strength", 0.45))
    buffer, pcm = cache.load_audio(str(audio_id))
    out, renderer = binaural_render_pcm(
        pcm,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        project_dir=cache.project_dir,
        strength=strength,
    )
    out_buffer = AudioBuffer.from_planar(
        out,
        buffer.sample_rate,
        source_node_type="BinauralRender",
        channel_layout="binaural",
    )
    out_buffer.encoding_scheme = f"Binaural render ({model_id})"
    out_buffer.spatial_meta = {
        **dict(getattr(buffer, "spatial_meta", None) or {}),
        "model": model_id,
        "binaural_strength": strength,
        "renderer": renderer,
    }
    cache.write_audio(out_buffer, out)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_spatial_upmix(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.nodes.ai.backends.spatial_upmix_runner import spatial_upmix_pcm

    audio_id = kwargs.get("audio_id") or (kwargs.get("audio") or {}).get("cache_id")
    if not audio_id:
        raise RuntimeError("SpatialUpmix requires audio input")
    model_id = str(kwargs.get("model", "stereo-atmos-bed-v0"))
    layout = str(kwargs.get("layout", "7.1.4") or "7.1.4").strip().lower()
    buffer, pcm = cache.load_audio(str(audio_id))
    out, upmix = spatial_upmix_pcm(
        pcm,
        sample_rate=buffer.sample_rate,
        model_id=model_id,
        project_dir=cache.project_dir,
        layout=layout,
    )
    out_buffer = AudioBuffer.from_planar(
        out,
        buffer.sample_rate,
        source_node_type="SpatialUpmix",
        channel_layout=layout,
    )
    out_buffer.encoding_scheme = f"Spatial upmix ({layout}, {model_id})"
    out_buffer.spatial_meta = {
        **dict(getattr(buffer, "spatial_meta", None) or {}),
        "model": model_id,
        "target_layout": layout,
        "upmix": upmix,
    }
    cache.write_audio(out_buffer, out)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]
