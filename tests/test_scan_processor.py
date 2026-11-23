"""ScanProcessor — offline Rutt/Etra-style raster VIDEO bake (luma → Z)."""

from __future__ import annotations

from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.executor.media_io import ffprobe_available, probe_video_duration_seconds
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata
from groovy.schema.validate import validate_workflow

register_core()

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VIDEO = ROOT / "assets" / "samples" / "video480p.mov"


def _mini_workflow(**scan_widgets) -> Workflow:
    widgets = {
        "z_push": 1.4,
        "focus": 0.35,
        "intensity": 1.0,
        "h_size": 1.0,
        "v_size": 1.0,
        "aspect": 1.333,
        "rotation_deg": -18.0,
        "mirror_v": True,
        "width": 320,
        "height": 180,
        "fps": 12,
        "duration_sec": 1.0,
        "sample_rate": 48000,
        "scan_lines": 48,
    }
    widgets.update(scan_widgets)
    return Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="scan-proc-test",
        metadata=WorkflowMetadata(title="ScanProcessor test"),
        nodes=[
            NodeInstance(
                id="osc-x",
                type="Oscillator",
                pos={"x": 0, "y": 0},
                widgets={
                    "waveform": "saw",
                    "frequency_hz": 55.0,
                    "amplitude_default": 0.8,
                    "duration_sec": 1.0,
                    "sample_rate": 48000,
                },
            ),
            NodeInstance(
                id="osc-y",
                type="Oscillator",
                pos={"x": 0, "y": 80},
                widgets={
                    "waveform": "sine",
                    "frequency_hz": 110.0,
                    "amplitude_default": 0.8,
                    "duration_sec": 1.0,
                    "sample_rate": 48000,
                },
            ),
            NodeInstance(id="scan", type="ScanProcessor", pos={"x": 280, "y": 40}, widgets=widgets),
        ],
        links=[
            # x_audio=5, y_audio=6 (DCU slots 0–4 CV, 5–7 audio, 8 video, 9 image)
            Link(id="l1", **{"from": ["osc-x", 0], "to": ["scan", 5], "type": "AUDIO"}),
            Link(id="l2", **{"from": ["osc-y", 0], "to": ["scan", 6], "type": "AUDIO"}),
        ],
    )


def _video_luma_workflow(**scan_widgets) -> Workflow:
    widgets = {
        "z_push": 1.6,
        "focus": 0.4,
        "intensity": 1.05,
        "h_size": 1.0,
        "v_size": 1.0,
        "aspect": 1.333,
        "rotation_deg": -20.0,
        "mirror_v": True,
        "luma_contrast": 1.4,
        "width": 320,
        "height": 180,
        "fps": 12,
        "duration_sec": 1.0,
        "sample_rate": 48000,
        "scan_lines": 64,
    }
    widgets.update(scan_widgets)
    return Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="scan-proc-video-test",
        metadata=WorkflowMetadata(title="ScanProcessor video luma test"),
        nodes=[
            NodeInstance(
                id="load-video",
                type="LoadVideo",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/video480p.mov"},
            ),
            NodeInstance(id="scan", type="ScanProcessor", pos={"x": 280, "y": 40}, widgets=widgets),
        ],
        links=[
            Link(id="l-vid", **{"from": ["load-video", 0], "to": ["scan", 8], "type": "VIDEO"}),
        ],
    )


def test_scan_processor_look_choices() -> None:
    from groovy.node import NODE_REGISTRY

    looks = NODE_REGISTRY["ScanProcessor"].INPUT_TYPES()["optional"]["look"][1]["choices"]
    assert len(looks) == 11
    assert "Phosphor Green" in looks
    assert "Scan Studies" in looks
    assert "Noise Terrain" in looks
    assert "Display 90" in looks
    assert "Wireframe" in looks
    widgets = NODE_REGISTRY["ScanProcessor"].INPUT_TYPES()["optional"]
    assert "phosphor_sat" in widgets


def test_scan_processor_validates() -> None:
    result = validate_workflow(_mini_workflow())
    assert result.valid, result.errors


def test_scan_processor_video_luma_validates() -> None:
    result = validate_workflow(_video_luma_workflow())
    assert result.valid, result.errors


def test_scan_processor_bakes_video(tmp_path: Path) -> None:
    if not ffprobe_available():
        pytest.skip("ffprobe required")
    workflow = _mini_workflow()
    ex = Executor(tmp_path)
    result = ex.execute(workflow, target_nodes=["scan"])
    assert result.status == "completed", result.error
    out = result.outputs["scan"]
    assert out.get("type") == "VIDEO"
    path = tmp_path / out["path"]
    assert path.is_file()
    assert path.stat().st_size > 1000
    duration = probe_video_duration_seconds(path)
    assert duration is not None
    assert 0.7 <= duration <= 1.4


def test_scan_processor_video_luma_bakes(tmp_path: Path) -> None:
    if not ffprobe_available():
        pytest.skip("ffprobe required")
    if not SAMPLE_VIDEO.is_file():
        pytest.skip("sample video missing")
    # Copy sample into project so LoadVideo resolves under executor project_dir.
    dest = tmp_path / "assets" / "samples"
    dest.mkdir(parents=True)
    (dest / "video480p.mov").write_bytes(SAMPLE_VIDEO.read_bytes())
    workflow = _video_luma_workflow()
    ex = Executor(tmp_path)
    result = ex.execute(workflow, target_nodes=["scan"])
    assert result.status == "completed", result.error
    out = result.outputs["scan"]
    assert out.get("type") == "VIDEO"
    path = tmp_path / out["path"]
    assert path.is_file()
    assert path.stat().st_size > 1000
    duration = probe_video_duration_seconds(path)
    assert duration is not None
    assert 0.7 <= duration <= 1.4


def test_scan_processor_deterministic(tmp_path: Path) -> None:
    if not ffprobe_available():
        pytest.skip("ffprobe required")
    workflow = _mini_workflow()
    a = Executor(tmp_path / "a")
    b = Executor(tmp_path / "b")
    ra = a.execute(workflow, target_nodes=["scan"])
    rb = b.execute(workflow, target_nodes=["scan"])
    assert ra.status == "completed" and rb.status == "completed"
    pa = a.cache.resolve_project_path(ra.outputs["scan"]["path"])
    pb = b.cache.resolve_project_path(rb.outputs["scan"]["path"])
    assert pa.read_bytes() == pb.read_bytes()
