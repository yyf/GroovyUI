"""Rutt/Etra Scan modular template — offline scan VIDEO + PreviewVideo scrub path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.executor.media_io import ffprobe_available, probe_video_duration_seconds
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow

register_core()

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "rutt-etra-scan.groovy.json"


@pytest.fixture(scope="module")
def workflow() -> Workflow:
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    return Workflow.model_validate(data)


def test_rutt_etra_file_and_tags(workflow: Workflow) -> None:
    assert TEMPLATE.is_file()
    assert workflow.metadata.title == "Rutt/Etra Scan Processor"
    tags = set(workflow.metadata.tags)
    assert "modular" in tags
    assert "rutt-etra" in tags
    by_type = {n.type for n in workflow.nodes}
    assert "ScanProcessor" in by_type
    assert "LoadVideo" in by_type
    assert "MuxVideo" in by_type
    assert "Oscillator" in by_type
    assert "LFO" in by_type
    assert "Amplifier" in by_type
    assert "EnvelopeFollower" in by_type
    previews = [n for n in workflow.nodes if n.type == "PreviewVideo"]
    assert len(previews) == 2
    ids = {n.id for n in previews}
    assert "preview-source" in ids and "preview-video" in ids
    scan = next(n for n in workflow.nodes if n.type == "ScanProcessor")
    assert scan.widgets.get("look") == "Scan Studies"
    assert float(scan.widgets.get("phosphor_sat", 1.0)) == 0.0
    # AM sine → EnvelopeFollower → z_push_cv (slot 3); soft osc → x/y audio.
    assert any(
        list(l.from_)[:1] == ["env-follow"] and list(l.to)[:2] == ["scan", 3]
        for l in workflow.links
    )
    assert any(list(l.from_)[:1] == ["osc-x"] and list(l.to)[:1] == ["scan"] for l in workflow.links)
    assert any(list(l.from_)[:1] == ["osc-y"] and list(l.to)[:1] == ["scan"] for l in workflow.links)
    assert any(list(l.from_)[:1] == ["amp-am"] and list(l.to)[:1] == ["env-follow"] for l in workflow.links)


def test_rutt_etra_validates(workflow: Workflow) -> None:
    result = validate_workflow(workflow)
    assert result.valid, result.errors


def test_rutt_etra_execute_preview_video(workflow: Workflow, tmp_path: Path) -> None:
    if not ffprobe_available():
        pytest.skip("ffprobe required")
    sample = ROOT / "assets" / "samples" / "video480p.mov"
    if not sample.is_file():
        pytest.skip("assets/samples/video480p.mov not present")
    dest = tmp_path / "assets" / "samples" / "video480p.mov"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(sample.read_bytes())
    # Shorter bake for CI — mutate ScanProcessor + oscillators in a copy.
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    for node in data["nodes"]:
        if node["type"] in {"Oscillator", "LFO", "ScanProcessor"}:
            node["widgets"]["duration_sec"] = 1.0
        if node["type"] == "ScanProcessor":
            node["widgets"].update(
                {
                    "width": 320,
                    "height": 180,
                    "fps": 12,
                    "scan_lines": 48,
                    "focus": 0.3,
                }
            )
    short = Workflow.model_validate(data)
    ex = Executor(tmp_path)
    result = ex.execute(short, target_nodes=["preview-video"])
    assert result.status == "completed", result.error
    out = result.outputs["preview-video"]
    assert out.get("type") == "VIDEO"
    path = tmp_path / out["path"]
    assert path.is_file()
    duration = probe_video_duration_seconds(path)
    assert duration is not None
    assert 0.7 <= duration <= 1.5
