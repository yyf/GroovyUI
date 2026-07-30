from __future__ import annotations

import contextlib
import io
from functools import lru_cache
from math import gcd
from pathlib import Path

import numpy as np
import torch
from pretty_midi import PrettyMIDI
from scipy import signal
from transformers import AutoProcessor, MusicgenMelodyForConditionalGeneration

from groovy.executor.midi import MidiBuffer

MELODY_SAMPLE_RATE = 32_000
HF_MODEL_ID = "facebook/musicgen-melody"
# MusicGen EnCodec frame rate ≈ 50 Hz → tokens ≈ seconds * 50
TOKENS_PER_SECOND = 50.0
MAX_NEW_TOKENS = 256  # HF docs default; also capped to melody length at runtime
# Chroma cares about pitch-class energy; sibilance / HF grit pollutes the conditioner.
MELODY_BANDPASS_HZ = (120.0, 3_500.0)


@lru_cache(maxsize=1)
def _load_musicgen_melody() -> tuple[AutoProcessor, MusicgenMelodyForConditionalGeneration, str]:
    processor = AutoProcessor.from_pretrained(HF_MODEL_ID)
    model = MusicgenMelodyForConditionalGeneration.from_pretrained(HF_MODEL_ID)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    return processor, model, device


def _peak_normalize(audio: np.ndarray, *, target: float = 0.8) -> np.ndarray:
    if audio.size == 0:
        return audio.astype(np.float32)
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-8:
        return audio.astype(np.float32)
    return (audio * (target / peak)).astype(np.float32)


def _resample_audio(audio: np.ndarray, *, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr or audio.size == 0:
        return audio.astype(np.float32, copy=False)
    g = gcd(int(target_sr), int(orig_sr))
    return signal.resample_poly(audio.astype(np.float64), target_sr // g, orig_sr // g).astype(np.float32)


def _bandpass_melody_band(mono: np.ndarray, *, sample_rate: int) -> np.ndarray:
    """Keep midband pitch energy; drop rumble + sibilance that skew chroma."""
    if mono.size < 32:
        return mono.astype(np.float32)
    low, high = MELODY_BANDPASS_HZ
    nyquist = sample_rate * 0.5
    high = min(high, nyquist * 0.95)
    low = max(20.0, min(low, high * 0.5))
    sos = signal.butter(2, [low / nyquist, high / nyquist], btype="band", output="sos")
    filtered = signal.sosfiltfilt(sos, mono.astype(np.float64))
    return filtered.astype(np.float32)


def _trim_leading_silence(mono: np.ndarray, *, sample_rate: int, threshold: float = 0.01) -> np.ndarray:
    if mono.size == 0:
        return mono
    window = max(1, int(sample_rate * 0.02))
    energy = np.convolve(np.abs(mono), np.ones(window) / window, mode="same")
    idx = np.argmax(energy >= threshold)
    if energy[idx] < threshold:
        return mono
    # Keep a 50ms pre-roll so attacks aren't clipped.
    start = max(0, int(idx) - int(sample_rate * 0.05))
    return mono[start:]


def _melody_audio_from_midi(midi: MidiBuffer) -> np.ndarray:
    if midi.path and Path(midi.path).exists():
        pm = PrettyMIDI(midi.path)
        audio = pm.synthesize(fs=MELODY_SAMPLE_RATE)
        if audio.size:
            cleaned = _bandpass_melody_band(audio.astype(np.float32), sample_rate=MELODY_SAMPLE_RATE)
            return _peak_normalize(cleaned, target=0.65)
    duration = max(0.5, midi.frame_count / max(midi.sample_rate, 1))
    return np.zeros(int(MELODY_SAMPLE_RATE * duration), dtype=np.float32)


def _melody_audio_from_reference(reference_pcm: np.ndarray, *, sample_rate: int) -> np.ndarray:
    """HF MusicGen Melody path: chroma from Demucs vocals / melody stem audio."""
    if reference_pcm.ndim == 1:
        mono = reference_pcm.astype(np.float32)
    else:
        mono = reference_pcm.mean(axis=0).astype(np.float32)
    mono = _resample_audio(mono, orig_sr=sample_rate, target_sr=MELODY_SAMPLE_RATE)
    mono = _trim_leading_silence(mono, sample_rate=MELODY_SAMPLE_RATE)
    mono = _bandpass_melody_band(mono, sample_rate=MELODY_SAMPLE_RATE)
    return _peak_normalize(mono, target=0.65)


def build_melody_conditioning(
    midi: MidiBuffer,
    *,
    sample_rate: int,
    reference_pcm: np.ndarray | None = None,
    melody_weight: float = 1.0,
    reference_weight: float = 0.0,
) -> np.ndarray:
    """
    Build MusicGen Melody conditioner audio.

    Prefer Demucs vocals / stem audio when ``reference_weight`` dominates (HF docs).
    MIDI→pretty_midi synth is a fallback when no reference is wired. Blending raw
    vocals into MIDI synth at ~50/50 makes generations noisy.
    """
    midi_audio = _melody_audio_from_midi(midi)
    if reference_pcm is None or reference_weight <= 0.0:
        return midi_audio

    ref = _melody_audio_from_reference(reference_pcm, sample_rate=sample_rate)
    if melody_weight <= 0.0 or reference_weight >= 0.99:
        return ref

    min_len = min(len(midi_audio), len(ref))
    if min_len <= 0:
        return ref if len(ref) else midi_audio

    total = max(melody_weight + reference_weight, 1e-6)
    blended = (melody_weight / total) * midi_audio[:min_len] + (reference_weight / total) * ref[:min_len]
    return _peak_normalize(blended.astype(np.float32), target=0.65)


def tokens_for_melody_duration(melody_audio: np.ndarray, *, requested: int) -> int:
    """Cap generation length to the conditioner so the model does not freerun into noise."""
    duration_s = len(melody_audio) / float(MELODY_SAMPLE_RATE)
    # Small pad (~0.5s) so the last note can ring; never exceed the user/widget request.
    matched = int(duration_s * TOKENS_PER_SECOND) + 25
    return max(64, min(int(requested), matched))


def regenerate_audio_from_midi(
    midi: MidiBuffer,
    *,
    sample_rate: int,
    prompt: str,
    reference_pcm: np.ndarray | None = None,
    max_new_tokens: int = 256,
    melody_weight: float = 1.0,
    reference_weight: float = 0.0,
    guidance_scale: float = 3.0,
    temperature: float = 0.7,
    seed: int | None = None,
) -> np.ndarray:
    melody_audio = build_melody_conditioning(
        midi,
        sample_rate=sample_rate,
        reference_pcm=reference_pcm,
        melody_weight=melody_weight,
        reference_weight=reference_weight,
    )
    token_budget = tokens_for_melody_duration(melody_audio, requested=max_new_tokens)

    processor, model, device = _load_musicgen_melody()
    inputs = processor(
        audio=melody_audio,
        sampling_rate=MELODY_SAMPLE_RATE,
        text=[prompt or "melodic music"],
        padding=True,
        return_tensors="pt",
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}

    generator = None
    if seed is not None and seed >= 0:
        generator = torch.Generator(device=device)
        generator.manual_seed(int(seed) % (2**63 - 1))

    with torch.no_grad():
        with contextlib.redirect_stdout(io.StringIO()):
            # HF: sampling >> greedy. Milder temperature + top_k reduces harsh freerun.
            generate_kwargs: dict[str, object] = {
                "max_new_tokens": token_budget,
                "guidance_scale": float(guidance_scale),
                "do_sample": True if temperature > 0 else False,
            }
            if temperature > 0:
                generate_kwargs["temperature"] = float(temperature)
                generate_kwargs["top_k"] = 250
                generate_kwargs["top_p"] = 0.95
            if generator is not None:
                generate_kwargs["generator"] = generator
            generated = model.generate(**inputs, **generate_kwargs)

    waveform = generated[0, 0].detach().cpu().numpy().astype(np.float64)
    if sample_rate != MELODY_SAMPLE_RATE:
        waveform = _resample_audio(waveform, orig_sr=MELODY_SAMPLE_RATE, target_sr=sample_rate).astype(
            np.float64
        )
    # Soft ceiling — avoid slamming peak to 1.0 which exaggerates grit.
    peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
    if peak > 0.95:
        waveform = waveform * (0.95 / peak)
    return waveform.reshape(1, -1)
