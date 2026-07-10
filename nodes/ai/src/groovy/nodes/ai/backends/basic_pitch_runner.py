from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
from basic_pitch.inference import predict
from pretty_midi import PrettyMIDI

from groovy.executor.midi import MidiBuffer

BASIC_PITCH_ONNX = build_icassp_2022_model_path(FilenameSuffix.onnx)


def transcribe_pcm_to_midi(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    minimum_note_length: float = 127.7,
    minimum_frequency: float | None = None,
    maximum_frequency: float | None = None,
    melodia_trick: bool = True,
) -> tuple[MidiBuffer, bytes]:
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    mono = pcm.mean(axis=0).astype(np.float32)

    with tempfile.TemporaryDirectory() as tmp_dir:
        wav_path = Path(tmp_dir) / "input.wav"
        midi_path = Path(tmp_dir) / "output.mid"
        sf.write(wav_path, mono, sample_rate)
        # basic_pitch prints progress to stdout; keep the worker JSON protocol clean.
        with contextlib.redirect_stdout(io.StringIO()):
            _, midi_data, _ = predict(
                str(wav_path),
                BASIC_PITCH_ONNX,
                onset_threshold=onset_threshold,
                frame_threshold=frame_threshold,
                minimum_note_length=minimum_note_length,
                minimum_frequency=minimum_frequency,
                maximum_frequency=maximum_frequency,
                melodia_trick=melodia_trick,
            )
        midi_data.write(str(midi_path))
        midi_bytes = midi_path.read_bytes()

    pm = PrettyMIDI(io.BytesIO(midi_bytes))
    duration = max(pm.get_end_time(), 0.25)
    frame_count = max(1, int(duration * sample_rate))
    midi = MidiBuffer.create(
        sample_rate=sample_rate,
        frame_count=frame_count,
        source_node_type="AudioToMIDI",
        midi_kind="transcript",
    )
    return midi, midi_bytes
