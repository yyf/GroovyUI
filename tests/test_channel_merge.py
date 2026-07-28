from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from groovy.executor import Executor
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Workflow

register_core()


def _write_stereo(path: Path, *, sr: int = 48000, duration_s: float = 0.05) -> None:
    frames = int(sr * duration_s)
    t = np.linspace(0, duration_s, frames, endpoint=False)
    left = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    right = 0.2 * np.sin(2 * np.pi * 880.0 * t)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.stack([left, right], axis=1), sr)


def test_channel_merge_stereo_from_loadaudio_outlets(tmp_path: Path) -> None:
    rel = "assets/samples/merge-stereo.wav"
    _write_stereo(tmp_path / rel)

    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "test-channel-merge",
            "metadata": {"title": "channel-merge", "description": ""},
            "nodes": [
                {"id": "load", "type": "LoadAudio", "widgets": {"path": rel}},
                {"id": "merge", "type": "ChannelMerge", "widgets": {"output_layout": "stereo"}},
                {
                    "id": "save",
                    "type": "SaveAudio",
                    "widgets": {"path": "exports", "filename": "merged.wav"},
                },
            ],
            "links": [
                {"id": "l1", "from": ["load", 0], "to": ["merge", 0], "type": "AUDIO"},
                {"id": "l2", "from": ["load", 1], "to": ["merge", 1], "type": "AUDIO"},
                {"id": "l3", "from": ["merge", 0], "to": ["save", 0], "type": "AUDIO"},
            ],
            "groups": [],
        }
    )

    result = Executor(tmp_path).execute(workflow, target_nodes=["save"])
    assert result.status == "completed", result.error

    merge_out = result.outputs["merge"]
    assert merge_out["type"] == "AUDIO"
    ex = Executor(tmp_path)
    buf, pcm = ex.cache.load_audio(merge_out["cache_id"])
    assert buf.channels == 2
    assert buf.channel_layout == "stereo"
    assert float(pcm[0].max()) > 0.05
    assert float(pcm[1].max()) > 0.05

    save_path = Path(result.outputs["save"]["path"])
    assert save_path.is_file()
    data, _ = sf.read(save_path, always_2d=True)
    assert data.shape[1] == 2
    assert float(np.abs(data[:, 0]).max()) > 0.05
    assert float(np.abs(data[:, 1]).max()) > 0.05


def test_channel_merge_layout_mismatch_errors(tmp_path: Path) -> None:
    rel = "assets/samples/merge-stereo.wav"
    _write_stereo(tmp_path / rel)
    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "test-channel-merge-mismatch",
            "metadata": {"title": "mismatch", "description": ""},
            "nodes": [
                {"id": "load", "type": "LoadAudio", "widgets": {"path": rel}},
                {"id": "merge", "type": "ChannelMerge", "widgets": {"output_layout": "5.1"}},
            ],
            "links": [
                {"id": "l1", "from": ["load", 0], "to": ["merge", 0], "type": "AUDIO"},
                {"id": "l2", "from": ["load", 1], "to": ["merge", 1], "type": "AUDIO"},
            ],
            "groups": [],
        }
    )
    result = Executor(tmp_path).execute(workflow, target_nodes=["merge"])
    assert result.status == "failed"
    assert result.error and "expects 6 inputs" in result.error
