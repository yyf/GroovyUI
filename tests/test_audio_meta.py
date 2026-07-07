from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor.audio_meta import (
    ambisonic_order,
    channel_layout_for_channels,
    channel_map_for_layout,
    probe_audio_file,
)


def test_channel_layout_for_surround() -> None:
    assert channel_layout_for_channels(6) == "5.1"
    assert channel_layout_for_channels(12) == "7.1.4"
    assert channel_map_for_layout("5.1", 6) == ["FL", "FR", "FC", "LFE", "BL", "BR"]


def test_ambisonic_order_detection() -> None:
    assert ambisonic_order(4) == 1
    assert ambisonic_order(9) == 2
    assert ambisonic_order(5) is None


def test_probe_51_wav(tmp_path: Path) -> None:
    sr = 48000
    frames = 256
    pcm = np.zeros((6, frames))
    pcm[0] = 1.0
    path = tmp_path / "surround_51.wav"
    sf.write(path, pcm.T, sr)

    meta = probe_audio_file(path)
    assert meta["channels"] == 6
    assert meta["channel_layout"] == "5.1"
    assert meta["encoding_scheme"] == "5.1 surround"
    assert meta["channel_map"] == ["FL", "FR", "FC", "LFE", "BL", "BR"]


def test_probe_atmos_bed(tmp_path: Path) -> None:
    sr = 48000
    frames = 128
    pcm = np.zeros((12, frames))
    path = tmp_path / "atmos_bed.wav"
    sf.write(path, pcm.T, sr)

    meta = probe_audio_file(path)
    assert meta["channel_layout"] == "7.1.4"
    assert "Atmos" in str(meta["encoding_scheme"])


def test_probe_foa_ambisonics(tmp_path: Path) -> None:
    sr = 48000
    frames = 64
    pcm = np.zeros((4, frames))
    path = tmp_path / "foa_ambisonic.wav"
    sf.write(path, pcm.T, sr, format="WAV", subtype="FLOAT")

    meta = probe_audio_file(path)
    assert meta["layout_order"] == 1
    assert meta["channel_layout"] in {"quad", "ambisonics"}
