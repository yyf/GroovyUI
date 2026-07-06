from __future__ import annotations

import numpy as np
from scipy import signal
from scipy.ndimage import median_filter

from groovy.executor.audio import AudioBuffer, StemsBuffer
from groovy.executor.cache import CacheStore


def require_model(project_dir, model_id: str) -> None:
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
    text = str(kwargs.get("text", "Hello from GroovyUI."))
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
    _ = pcm, sample_rate
    return f"[dev transcript via {model_id}] Sample dialogue placeholder."


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
