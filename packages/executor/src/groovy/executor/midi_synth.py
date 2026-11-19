"""Offline MIDI → PCM via pretty_midi.synthesize (PreviewMidi audition + SynthMidi)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from groovy.executor.midi import MidiBuffer


def synthesize_midi_pcm(
    midi: MidiBuffer,
    *,
    sample_rate: int = 48_000,
    mid_path: str | Path | None = None,
) -> np.ndarray:
    """Return planar float64 PCM ``(1, frames)`` from an SMF / MidiBuffer.

    Empty / missing SMF → short silence. Matches PreviewMidi transport audition.
    """
    sr = max(8_000, int(sample_rate))
    path = Path(mid_path) if mid_path else (Path(midi.path) if midi.path else None)
    duration = max(0.25, float(midi.frame_count) / max(int(midi.sample_rate or sr), 1))

    if path is None or not path.is_file() or int(midi.frame_count or 0) <= 0:
        return np.zeros((1, int(round(0.25 * sr))), dtype=np.float64)

    try:
        from pretty_midi import PrettyMIDI

        pm = PrettyMIDI(str(path))
        duration = max(duration, float(pm.get_end_time()))
        audio = pm.synthesize(fs=sr)
        if audio.size:
            target_frames = int(round(duration * sr))
            if audio.size < target_frames:
                padded = np.zeros(target_frames, dtype=np.float64)
                padded[: audio.size] = audio
                audio = padded
            elif audio.size > target_frames:
                audio = audio[:target_frames]
            return np.asarray(audio, dtype=np.float64).reshape(1, -1)
    except ImportError:
        pass

    return np.zeros((1, int(round(duration * sr))), dtype=np.float64)
