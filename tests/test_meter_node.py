"""Tests for Meter node / multi-channel level helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from groovy.executor.meter import (
    format_meter_summary,
    measure_channel_levels,
    resolve_meter_layout,
)
from groovy.node import NODE_REGISTRY
from groovy.nodes.core import register_all as register_core

register_core()


def test_meter_registered() -> None:
    assert "Meter" in NODE_REGISTRY
    schema = NODE_REGISTRY["Meter"].describe()
    assert schema["outputs"][0]["type"] == "AUDIO"
    assert schema["outputs"][1]["type"] == "TEXT"
    input_names = {s["name"] for s in schema["inputs"]}
    assert "audio" in input_names
    assert "ambisonics" in input_names
    widgets = {w["name"]: w for w in schema.get("widgets", [])}
    assert widgets["layout"]["default"] == "auto"


def test_measure_channel_levels_stereo_head_tail() -> None:
    # Left-dominant head, right-dominant tail (L→R pan debug case).
    frames = 1000
    pcm = np.zeros((2, frames), dtype=np.float64)
    pcm[0, :50] = 0.5
    pcm[1, -50:] = 0.5
    meter = measure_channel_levels(pcm, layout="stereo", edge_fraction=0.05)
    assert meter["channel_count"] == 2
    assert [c["name"] for c in meter["channels"]] == ["L", "R"]
    left, right = meter["channels"]
    assert left["peak_head"] > right["peak_head"]
    assert right["peak_tail"] > left["peak_tail"]
    summary = format_meter_summary(meter)
    assert "L" in summary and "R" in summary


def test_measure_auto_detects_stereo_from_channel_count() -> None:
    pcm = np.zeros((2, 100), dtype=np.float64)
    pcm[0] = 0.2
    meter = measure_channel_levels(pcm, layout="auto")
    assert meter["layout"] == "stereo"
    assert [c["name"] for c in meter["channels"]] == ["L", "R"]


def test_resolve_meter_layout_foa_from_order_meta() -> None:
    assert (
        resolve_meter_layout(
            layout_widget="auto",
            channel_count=4,
            channel_layout="ambisonics",
            layout_order=1,
        )
        == "foa"
    )
    assert (
        resolve_meter_layout(
            layout_widget="auto",
            channel_count=9,
            layout_order=2,
        )
        == "hoa2"
    )


def test_measure_foa_labels_from_ambi_meta() -> None:
    pcm = np.zeros((4, 200), dtype=np.float64)
    pcm[0] = 0.1
    pcm[1, :20] = 0.4
    meter = measure_channel_levels(
        pcm,
        layout="auto",
        channel_layout="ambisonics",
        layout_order=1,
        spatial_meta={"channel_ordering": "ACN"},
    )
    assert meter["layout"] == "foa"
    assert [c["name"] for c in meter["channels"]] == ["W", "Y", "Z", "X"]


def test_meter_node_via_executor(tmp_path: Path) -> None:
    from groovy.executor import Executor
    from groovy.schema.models import Workflow

    project = tmp_path / "project"
    project.mkdir()
    wav = project / "stereo.wav"
    frames = 4800
    pcm = np.zeros((frames, 2), dtype=np.float32)
    pcm[:240, 0] = 0.4
    pcm[-240:, 1] = 0.4
    sf.write(wav, pcm, 48000)
    data = {
        "schema_version": "1.0.0",
        "groovy_version": "0.1.0",
        "id": "meter-unit",
        "metadata": {"title": "Meter unit"},
        "nodes": [
            {"id": "n1", "type": "LoadAudio", "pos": {"x": 0, "y": 0}, "widgets": {"path": "stereo.wav"}},
            {
                "id": "n2",
                "type": "Meter",
                "pos": {"x": 200, "y": 0},
                "widgets": {"layout": "auto", "edge_fraction": 0.05},
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
    workflow = Workflow.model_validate(data)
    out = Executor(project).execute(workflow, target_nodes=["n2", "n3"])
    assert out.status == "completed", out.error
    payload = out.outputs["n2"]
    assert payload["type"] == "MULTI"
    slots = payload["outputs"]
    assert slots[0]["type"] == "AUDIO"
    assert slots[1]["type"] == "TEXT"
    text = slots[1]["text"]
    assert "§METER§" in text
    assert "L" in text and "R" in text
    assert out.outputs["n3"]["type"] == "AUDIO"


def test_meter_ambisonics_via_executor(tmp_path: Path) -> None:
    from groovy.executor import Executor
    from groovy.schema.models import Workflow

    project = tmp_path / "project"
    project.mkdir()
    wav = project / "mono.wav"
    sf.write(wav, np.full(2400, 0.25, dtype=np.float32), 48000)
    data = {
        "schema_version": "1.0.0",
        "groovy_version": "0.1.0",
        "id": "meter-ambi",
        "metadata": {"title": "Meter ambisonics"},
        "nodes": [
            {"id": "n1", "type": "LoadAudio", "pos": {"x": 0, "y": 0}, "widgets": {"path": "mono.wav"}},
            {"id": "n2", "type": "AmbisonicEncode", "pos": {"x": 200, "y": 0}, "widgets": {"order": 1}},
            {
                "id": "n3",
                "type": "Meter",
                "pos": {"x": 400, "y": 0},
                "widgets": {"layout": "auto", "edge_fraction": 0.05},
            },
        ],
        "links": [
            {"id": "l1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"},
            {"id": "l2", "from": ["n2", 0], "to": ["n3", 1], "type": "AMBISONICS"},
        ],
        "groups": [],
        "view": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
    }
    workflow = Workflow.model_validate(data)
    out = Executor(project).execute(workflow, target_nodes=["n3"])
    assert out.status == "completed", out.error
    payload = out.outputs["n3"]
    assert payload["type"] == "MULTI"
    slots = payload["outputs"]
    assert slots[0]["type"] == "AMBISONICS"
    assert slots[1]["type"] == "TEXT"
    text = slots[1]["text"]
    assert "§METER§" in text
    for name in ("W", "Y", "Z", "X"):
        assert name in text
