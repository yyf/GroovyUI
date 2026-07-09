from __future__ import annotations

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


def resolve_model_id(model_id: str) -> str:
    aliases = {"demucs-v4-objects": "demucs-v4"}
    return aliases.get(model_id, model_id)


def run_separate_to_objects(cache: CacheStore, kwargs: dict) -> list[dict]:
    from groovy.executor.oba import ObjectScene

    model_id = str(kwargs.get("model", "demucs-v4-objects"))
    resolved = resolve_model_id(model_id)
    stem_result = run_separate_stems(cache, {**kwargs, "model": resolved})[0]
    stems = cache.load_stems(stem_result["stems_id"])
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
    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "demucs-v4"))
    buffer, pcm = cache.load_audio(audio_id)
    stem_pcm = separate_stems_audio(pcm, sample_rate=buffer.sample_rate, model_id=model_id)
    stems = StemsBuffer.from_stem_pcm(
        stem_pcm, buffer.sample_rate, channel_layout=buffer.channel_layout
    )
    cache.write_stems(stems, stem_pcm)
    return [
        {
            "type": "STEMS",
            "stems_id": stems.id,
            "stems": {name: {"cache_id": buf.id} for name, buf in stems.stems.items()},
        }
    ]


def run_whisper_stt(cache: CacheStore, kwargs: dict) -> list[dict]:
    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "whisper-large-v3-turbo"))
    buffer, pcm = cache.load_audio(audio_id)
    text = transcribe_audio(pcm, sample_rate=buffer.sample_rate, model_id=model_id)
    return [{"type": "TEXT", "text": text}]


def run_tts(cache: CacheStore, kwargs: dict) -> list[dict]:
    text = str(kwargs.get("transcript") or kwargs.get("text") or "Hello from GroovyUI.")
    model_id = str(kwargs.get("model", "f5-tts-base"))
    sample_rate = 48000
    pcm = synthesize_speech(text, sample_rate=sample_rate, model_id=model_id)
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
    _ = model_id, sample_rate
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0:
        return pcm.copy()

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
    pcm: np.ndarray, *, sample_rate: int, model_id: str
) -> dict[str, np.ndarray]:
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


def transcribe_audio(pcm: np.ndarray, *, sample_rate: int, model_id: str) -> str:
    if pcm.ndim == 1:
        mono = pcm.astype(np.float64)
    else:
        mono = pcm.mean(axis=0).astype(np.float64)
    duration = len(mono) / max(sample_rate, 1)
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
    fingerprint = int(np.sum((mono[: min(len(mono), 4096)] * 1_000_000).astype(np.int64)) % 1_000_000)
    return (
        f"[dev transcript via {model_id}] "
        f"dur={duration:.2f}s peak={peak:.3f} rms={rms:.3f} fp={fingerprint}"
    )


def synthesize_speech(text: str, *, sample_rate: int, model_id: str) -> np.ndarray:
    _ = model_id
    duration = min(3.0, max(0.5, len(text) * 0.05))
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    tone = 0.2 * np.sin(2 * np.pi * 220 * t)
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
    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "basic-pitch"))
    buffer, pcm = cache.load_audio(audio_id)
    midi = audio_to_midi(pcm, sample_rate=buffer.sample_rate, model_id=model_id)
    mid_path = cache.cache_dir / f"{midi.id}.mid"
    duration = buffer.frame_count / buffer.sample_rate
    write_minimal_smf(mid_path, duration_sec=min(4.0, max(0.5, duration)))
    cache.write_midi(midi)
    return [{"type": "MIDI", "midi_id": midi.id}]


def run_midi_to_audio(cache: CacheStore, kwargs: dict) -> list[dict]:
    midi_id = kwargs["midi_id"]
    model_id = str(kwargs.get("model", "musicgen-melody-small"))
    prompt = str(kwargs.get("text") or kwargs.get("prompt") or "regenerated melody")
    midi = cache.load_midi(midi_id)
    sample_rate = midi.sample_rate
    pcm = midi_to_audio_waveform(midi, sample_rate=sample_rate, model_id=model_id, prompt=prompt)
    out_buffer = AudioBuffer.from_planar(pcm, sample_rate, source_node_type="MIDIToAudio")
    cache.write_audio(out_buffer, pcm)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_generate_audio(cache: CacheStore, kwargs: dict) -> list[dict]:
    model_id = str(kwargs.get("model", "musicgen-small"))
    prompt = str(kwargs.get("prompt") or kwargs.get("text") or "ambient music")
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
    )
    out_buffer = AudioBuffer.from_planar(pcm, sample_rate, source_node_type="GenerateAudio")
    cache.write_audio(out_buffer, pcm)
    return [{"type": "AUDIO", "cache_id": out_buffer.id}]


def run_sing_from_midi(cache: CacheStore, kwargs: dict) -> list[dict]:
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


def audio_to_midi(pcm: np.ndarray, *, sample_rate: int, model_id: str) -> MidiBuffer:
    _ = model_id
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    mono = pcm.mean(axis=0)
    frame_count = len(mono)
    return MidiBuffer.create(
        sample_rate=sample_rate,
        frame_count=frame_count,
        source_node_type="AudioToMIDI",
        midi_kind="transcript",
    )


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
    midi: MidiBuffer, *, sample_rate: int, model_id: str, prompt: str
) -> np.ndarray:
    _ = model_id, prompt
    duration = max(0.5, midi.frame_count / sample_rate)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    # melody stub: two-tone pattern from midi id hash
    seed = sum(ord(c) for c in midi.id) % 7
    f1 = 220 + seed * 20
    f2 = 330 + seed * 15
    tone = 0.15 * (np.sin(2 * np.pi * f1 * t) + 0.7 * np.sin(2 * np.pi * f2 * t))
    return tone.reshape(1, -1)


def generate_audio_waveform(
    prompt: str,
    *,
    sample_rate: int,
    model_id: str,
    midi: MidiBuffer | None = None,
    reference_pcm: np.ndarray | None = None,
) -> np.ndarray:
    _ = model_id, reference_pcm
    seed = sum(ord(c) for c in prompt) % 11
    duration = 2.0
    if midi is not None:
        duration = max(1.0, midi.frame_count / sample_rate)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    f1 = 130 + seed * 12
    f2 = 196 + seed * 8
    tone = 0.12 * (np.sin(2 * np.pi * f1 * t) + 0.5 * np.sin(2 * np.pi * f2 * t))
    if midi is not None:
        melody = midi_to_audio_waveform(midi, sample_rate=sample_rate, model_id=model_id, prompt=prompt)
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
) -> np.ndarray:
    _ = model_id, reference_pcm
    duration = max(1.0, midi.frame_count / sample_rate)
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    seed = sum(ord(c) for c in lyrics) % 9
    carrier = 440 + seed * 10
    # vocal-like AM envelope from syllable count
    syllables = max(1, len(lyrics.split()))
    env = 0.5 + 0.5 * np.sin(2 * np.pi * syllables * t / duration)
    tone = 0.18 * env * np.sin(2 * np.pi * carrier * t)
    vibrato = 0.03 * np.sin(2 * np.pi * 5.5 * t)
    tone = tone * (1.0 + vibrato)
    return tone.reshape(1, -1)
