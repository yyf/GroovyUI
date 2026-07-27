from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from groovy.executor import Executor
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Workflow


register_core()


def _write_wav(path: Path, *, channels: int, sr: int = 48000, duration_s: float = 0.1) -> None:
    frames = int(sr * duration_s)
    t = np.linspace(0, duration_s, frames, endpoint=False)

    # Distinct tones per channel so masking correctness is debuggable.
    waves = []
    for ch in range(channels):
        freq = 440.0 + 110.0 * ch
        waves.append(0.2 * np.sin(2 * np.pi * freq * t))

    # soundfile expects (frames, channels)
    pcm = np.stack(waves, axis=1) if channels > 1 else waves[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, pcm, sr)


def _loadaudio_workflow(*, rel_path: str, filename_stem: str) -> Workflow:
    return Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": f"test-loadaudio-multi-{filename_stem}",
            "metadata": {"title": "test-loadaudio-multi", "description": ""},
            "nodes": [
                {
                    "id": "n1",
                    "type": "LoadAudio",
                    "pos": {"x": 0, "y": 0},
                    "widgets": {"path": rel_path},
                }
            ],
            "links": [],
            "groups": [],
            "view": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
        }
    )


def test_load_audio_stereo_emits_two_outlets(tmp_path: Path) -> None:
    stereo_rel = "assets/samples/test-stereo.wav"
    stereo_abs = tmp_path / stereo_rel
    _write_wav(stereo_abs, channels=2)

    workflow = _loadaudio_workflow(rel_path=stereo_rel, filename_stem="stereo")
    result = Executor(tmp_path).execute(workflow, target_nodes=["n1"])
    assert result.status == "completed", result.error

    out = result.outputs["n1"]
    assert out["type"] == "MULTI"
    assert len(out["outputs"]) == 2


def test_load_audio_mono_emits_single_outlet(tmp_path: Path) -> None:
    mono_rel = "assets/samples/test-mono.wav"
    mono_abs = tmp_path / mono_rel
    _write_wav(mono_abs, channels=1)

    workflow = _loadaudio_workflow(rel_path=mono_rel, filename_stem="mono")
    result = Executor(tmp_path).execute(workflow, target_nodes=["n1"])
    assert result.status == "completed", result.error

    out = result.outputs["n1"]
    assert out["type"] == "AUDIO"

