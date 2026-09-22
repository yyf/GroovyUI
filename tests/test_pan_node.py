"""Tests for layout-agnostic Pan DSP + node."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from groovy.executor import Executor
from groovy.node import NODE_REGISTRY
from groovy.nodes.core import register_all as register_core
from groovy.nodes.core.pan import pan_pcm, resolve_output_layout
from groovy.schema.models import Workflow

register_core()


def test_pan_node_registered() -> None:
    assert "Pan" in NODE_REGISTRY
    defaults = NODE_REGISTRY["Pan"].INPUT_TYPES()
    assert "audio" in defaults["required"]
    assert defaults["optional"]["pan"][1]["default"] == 0.0


def test_resolve_output_layout_promotes_mono() -> None:
    assert resolve_output_layout(input_layout="mono", input_channels=1, output_layout="auto") == "stereo"
    assert resolve_output_layout(input_layout="stereo", input_channels=2, output_layout="auto") == "stereo"
    assert resolve_output_layout(input_layout="mono", input_channels=1, output_layout="5.1") == "5.1"


def test_mono_to_stereo_equal_power_center() -> None:
    frames = 1000
    mono = np.ones((1, frames), dtype=np.float64) * 0.5
    out = pan_pcm(mono, pan=0.0, input_layout="mono", output_layout="stereo")
    assert out.shape == (2, frames)
    assert np.allclose(out[0], out[1], atol=1e-9)
    assert float(np.max(np.abs(out))) <= 1.0 + 1e-9


def test_mono_to_stereo_hard_left() -> None:
    mono = np.ones((1, 500), dtype=np.float64) * 0.4
    out = pan_pcm(mono, pan=-1.0, input_layout="mono", output_layout="stereo")
    assert float(np.max(np.abs(out[1]))) < 1e-9
    assert float(np.max(np.abs(out[0]))) > 0.3


def test_mono_to_51_has_twelve_or_six_channels() -> None:
    mono = np.ones((1, 200), dtype=np.float64) * 0.2
    out = pan_pcm(mono, pan=0.5, input_layout="mono", output_layout="5.1")
    assert out.shape == (6, 200)
    # LFE silent for mono drive
    assert float(np.max(np.abs(out[3]))) < 1e-12


def test_mono_to_stereo_pan_template(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    wav = project / "stereo.wav"
    t = np.linspace(0, 0.25, 12000, endpoint=False)
    tone = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(wav, np.column_stack([tone, tone * 0.5]), 48000)

    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "pan-unit",
            "metadata": {"title": "pan"},
            "nodes": [
                {"id": "n1", "type": "LoadAudio", "pos": {"x": 0, "y": 0}, "widgets": {"path": "stereo.wav"}},
                {"id": "n2", "type": "ChannelConvert", "pos": {"x": 200, "y": 0}, "widgets": {"layout": "mono"}},
                {
                    "id": "n3",
                    "type": "ControlCurve",
                    "pos": {"x": 200, "y": 120},
                    "widgets": {
                        "start_value": -1.0,
                        "end_value": 1.0,
                        "frame_count": 12000,
                        "sample_rate": 48000,
                        "points": '[{"t":0,"v":-1},{"t":1,"v":1}]',
                    },
                },
                {
                    "id": "n4",
                    "type": "Pan",
                    "pos": {"x": 400, "y": 0},
                    "widgets": {"pan": 0.0, "output_layout": "stereo"},
                },
                {"id": "n5", "type": "Preview", "pos": {"x": 600, "y": 0}, "widgets": {}},
            ],
            "links": [
                {"id": "l1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"},
                {"id": "l2", "from": ["n2", 0], "to": ["n4", 0], "type": "AUDIO"},
                {"id": "l3", "from": ["n3", 0], "to": ["n4", 1], "type": "AUTOMATION"},
                {"id": "l4", "from": ["n4", 0], "to": ["n5", 0], "type": "AUDIO"},
            ],
            "groups": [],
            "view": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
        }
    )
    out = Executor(project).execute(workflow, target_nodes=["n4", "n5"])
    assert out.status == "completed", out.error
    meta = Executor(project).cache.read_meta(out.outputs["n4"]["cache_id"])
    assert meta.get("channels") == 2
    assert meta.get("channel_layout") == "stereo"
