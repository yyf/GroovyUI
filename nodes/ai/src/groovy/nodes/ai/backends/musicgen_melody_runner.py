from __future__ import annotations

import contextlib
import io
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from pretty_midi import PrettyMIDI
from scipy import signal
from transformers import AutoProcessor, MusicgenMelodyForConditionalGeneration

from groovy.executor.midi import MidiBuffer

MELODY_SAMPLE_RATE = 32_000
HF_MODEL_ID = "facebook/musicgen-melody"
MAX_NEW_TOKENS = 512  # default when model param not set

@lru_cache(maxsize=1)
def _load_musicgen_melody() -> tuple[AutoProcessor, MusicgenMelodyForConditionalGeneration, str]:
    processor = AutoProcessor.from_pretrained(HF_MODEL_ID)
    model = MusicgenMelodyForConditionalGeneration.from_pretrained(HF_MODEL_ID)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    return processor, model, device


def _melody_audio_from_midi(midi: MidiBuffer) -> np.ndarray:
    if midi.path and Path(midi.path).exists():
        pm = PrettyMIDI(midi.path)
        audio = pm.synthesize(fs=MELODY_SAMPLE_RATE)
        if audio.size:
            return audio.astype(np.float32)
    duration = max(0.5, midi.frame_count / max(midi.sample_rate, 1))
    return np.zeros(int(MELODY_SAMPLE_RATE * duration), dtype=np.float32)


def _melody_audio_from_reference(reference_pcm: np.ndarray, *, sample_rate: int) -> np.ndarray:
    if reference_pcm.ndim == 1:
        mono = reference_pcm.astype(np.float32)
    else:
        mono = reference_pcm.mean(axis=0).astype(np.float32)
    if sample_rate != MELODY_SAMPLE_RATE:
        target_len = max(1, int(len(mono) * MELODY_SAMPLE_RATE / sample_rate))
        mono = signal.resample(mono, target_len).astype(np.float32)
    return mono


def regenerate_audio_from_midi(
    midi: MidiBuffer,
    *,
    sample_rate: int,
    prompt: str,
    reference_pcm: np.ndarray | None = None,
    max_new_tokens: int = 512,
    melody_weight: float = 0.55,
    reference_weight: float = 0.45,
    guidance_scale: float = 3.0,
    temperature: float = 1.0,
) -> np.ndarray:
    melody_audio = _melody_audio_from_midi(midi)
    if reference_pcm is not None:
        ref = _melody_audio_from_reference(reference_pcm, sample_rate=sample_rate)
        min_len = min(len(melody_audio), len(ref))
        if min_len > 0:
            total = max(melody_weight + reference_weight, 1e-6)
            melody_audio = (
                (melody_weight / total) * melody_audio[:min_len]
                + (reference_weight / total) * ref[:min_len]
            )

    processor, model, device = _load_musicgen_melody()
    inputs = processor(
        audio=melody_audio,
        sampling_rate=MELODY_SAMPLE_RATE,
        text=[prompt or "melodic music"],
        padding=True,
        return_tensors="pt",
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}

    with torch.no_grad():
        with contextlib.redirect_stdout(io.StringIO()):
            generate_kwargs: dict[str, object] = {
                "max_new_tokens": max(64, int(max_new_tokens)),
                "guidance_scale": float(guidance_scale),
            }
            if temperature > 0:
                generate_kwargs["do_sample"] = True
                generate_kwargs["temperature"] = float(temperature)
            generated = model.generate(**inputs, **generate_kwargs)

    waveform = generated[0, 0].detach().cpu().numpy().astype(np.float64)
    if sample_rate != MELODY_SAMPLE_RATE:
        target_len = max(1, int(len(waveform) * sample_rate / MELODY_SAMPLE_RATE))
        waveform = signal.resample(waveform, target_len).astype(np.float64)
    peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
    if peak > 1.0:
        waveform = waveform / peak
    return waveform.reshape(1, -1)
