"""Unit tests for binaural / Atmos-bed stub upmix helpers + nodes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from groovy.node import NODE_REGISTRY
from groovy.nodes.ai.backends.spatial_upmix_runner import (
    stereo_to_atmos_bed_714,
    stereo_to_binaural_crossfeed,
)
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core

register_core()
register_ai()


def test_binaural_and_spatial_nodes_registered() -> None:
    assert "BinauralRender" in NODE_REGISTRY
    assert "SpatialUpmix" in NODE_REGISTRY
    assert NODE_REGISTRY["BinauralRender"].COMPATIBLE_MODELS == [
        "hrtf-binaural-v0",
        "stereo2spatial-v2-binaural",
    ]
    assert NODE_REGISTRY["SpatialUpmix"].COMPATIBLE_MODELS == [
        "stereo-atmos-bed-v0",
        "stereo2spatial-v1",
    ]


def test_stereo_to_binaural_crossfeed_shape() -> None:
    frames = 4800
    pcm = np.zeros((2, frames), dtype=np.float64)
    pcm[0, :100] = 0.5
    pcm[1, -100:] = 0.5
    out = stereo_to_binaural_crossfeed(pcm, sample_rate=48000)
    assert out.shape == (2, frames)
    assert float(np.max(np.abs(out))) > 0


def test_stereo_to_atmos_bed_714_channels() -> None:
    pcm = np.ones((2, 1000), dtype=np.float64) * 0.2
    bed = stereo_to_atmos_bed_714(pcm, sample_rate=48000)
    assert bed.shape == (12, 1000)


def test_binaural_and_atmos_templates_via_executor(tmp_path: Path) -> None:
    from groovy.executor import Executor
    from groovy.registry import ModelRegistry
    from groovy.schema.models import Workflow

    project = tmp_path / "project"
    project.mkdir()
    wav = project / "stereo.wav"
    sf.write(wav, np.column_stack([np.full(2400, 0.2), np.full(2400, -0.15)]).astype(np.float32), 48000)

    registry = ModelRegistry(project)
    registry.installer.install("hrtf-binaural-v0")
    registry.installer.install("stereo-atmos-bed-v0")

    binaural = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "binaural-unit",
            "metadata": {"title": "binaural"},
            "nodes": [
                {"id": "n1", "type": "LoadAudio", "pos": {"x": 0, "y": 0}, "widgets": {"path": "stereo.wav"}},
                {
                    "id": "n2",
                    "type": "BinauralRender",
                    "pos": {"x": 200, "y": 0},
                    "widgets": {"model": "hrtf-binaural-v0", "strength": 0.4},
                },
                {"id": "n3", "type": "Preview", "pos": {"x": 400, "y": 0}, "widgets": {}},
            ],
            "links": [
                {"id": "l1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"},
                {"id": "l2", "from": ["n2", 0], "to": ["n3", 0], "type": "AUDIO"},
            ],
            "groups": [],
            "view": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
        }
    )
    out = Executor(project).execute(binaural, target_nodes=["n2", "n3"])
    assert out.status == "completed", out.error
    assert out.outputs["n2"]["type"] == "AUDIO"

    atmos = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "atmos-unit",
            "metadata": {"title": "atmos"},
            "nodes": [
                {"id": "n1", "type": "LoadAudio", "pos": {"x": 0, "y": 0}, "widgets": {"path": "stereo.wav"}},
                {
                    "id": "n2",
                    "type": "SpatialUpmix",
                    "pos": {"x": 200, "y": 0},
                    "widgets": {"model": "stereo-atmos-bed-v0", "layout": "7.1.4"},
                },
                {
                    "id": "n3",
                    "type": "ChannelConvert",
                    "pos": {"x": 400, "y": 0},
                    "widgets": {"layout": "stereo"},
                },
                {"id": "n4", "type": "Preview", "pos": {"x": 600, "y": 0}, "widgets": {}},
            ],
            "links": [
                {"id": "l1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"},
                {"id": "l2", "from": ["n2", 0], "to": ["n3", 0], "type": "AUDIO"},
                {"id": "l3", "from": ["n3", 0], "to": ["n4", 0], "type": "AUDIO"},
            ],
            "groups": [],
            "view": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
        }
    )
    out2 = Executor(project).execute(atmos, target_nodes=["n2", "n3", "n4"])
    assert out2.status == "completed", out2.error
    meta = Executor(project).cache.read_meta(out2.outputs["n2"]["cache_id"])
    assert meta.get("channels") == 12
    assert meta.get("channel_layout") == "7.1.4"
