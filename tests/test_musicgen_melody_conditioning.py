from __future__ import annotations

from pathlib import Path

import numpy as np
import pretty_midi

from groovy.executor.midi import MidiBuffer
from groovy.nodes.ai.backends.musicgen_melody_runner import (
    MELODY_SAMPLE_RATE,
    build_melody_conditioning,
    tokens_for_melody_duration,
)


def _simple_midi(path: Path) -> MidiBuffer:
    pm = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)
    instrument.notes.append(pretty_midi.Note(velocity=100, pitch=60, start=0.0, end=0.5))
    pm.instruments.append(instrument)
    pm.write(str(path))
    return MidiBuffer(
        id="midi-test",
        sample_rate=48_000,
        frame_count=24_000,
        path=str(path),
        midi_kind="performance",
    )


def test_build_melody_conditioning_ignores_reference_when_weight_zero(tmp_path: Path) -> None:
    midi_path = tmp_path / "note.mid"
    midi = _simple_midi(midi_path)
    noisy = np.random.default_rng(0).normal(0.0, 0.4, size=MELODY_SAMPLE_RATE).astype(np.float32)

    midi_only = build_melody_conditioning(midi, sample_rate=48_000)
    with_ref_ignored = build_melody_conditioning(
        midi,
        sample_rate=48_000,
        reference_pcm=noisy,
        melody_weight=1.0,
        reference_weight=0.0,
    )

    assert midi_only.shape == with_ref_ignored.shape
    assert np.allclose(midi_only, with_ref_ignored)
    assert float(np.max(np.abs(midi_only))) > 0.1


def test_build_melody_conditioning_prefers_reference_when_weight_dominates(tmp_path: Path) -> None:
    midi_path = tmp_path / "note.mid"
    midi = _simple_midi(midi_path)
    # Pure 440 Hz tone as "vocals" reference
    t = np.linspace(0, 1.0, MELODY_SAMPLE_RATE, endpoint=False)
    ref = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    midi_only = build_melody_conditioning(midi, sample_rate=MELODY_SAMPLE_RATE)
    vocals_only = build_melody_conditioning(
        midi,
        sample_rate=MELODY_SAMPLE_RATE,
        reference_pcm=ref,
        melody_weight=0.0,
        reference_weight=1.0,
    )

    assert not np.allclose(
        midi_only[: min(len(midi_only), len(vocals_only))],
        vocals_only[: min(len(midi_only), len(vocals_only))],
    )
    assert float(np.max(np.abs(vocals_only))) > 0.4


def test_reference_conditioner_band_limits_sibilance() -> None:
    from groovy.nodes.ai.backends.musicgen_melody_runner import _melody_audio_from_reference

    sr = 48_000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    # Melody + loud 8 kHz hiss
    vocal = (0.25 * np.sin(2 * np.pi * 440 * t) + 0.35 * np.sin(2 * np.pi * 8000 * t)).astype(
        np.float32
    )
    cleaned = _melody_audio_from_reference(vocal, sample_rate=sr)
    spec = np.abs(np.fft.rfft(cleaned * np.hanning(len(cleaned))))
    freqs = np.fft.rfftfreq(len(cleaned), 1 / MELODY_SAMPLE_RATE)
    mid = float(np.mean(spec[(freqs > 300) & (freqs < 800)]))
    high = float(np.mean(spec[freqs > 6000]))
    assert mid > high


def test_tokens_capped_to_melody_duration() -> None:
    # 2 seconds of conditioner → ~100 tokens + pad, not the full 512 request
    melody = np.zeros(MELODY_SAMPLE_RATE * 2, dtype=np.float32)
    assert tokens_for_melody_duration(melody, requested=512) <= 150
    assert tokens_for_melody_duration(melody, requested=64) == 64
