from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.node_cache import compute_node_signature
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Workflow

register_core()

CACHE_WORKFLOW = {
    "schema_version": "1.0.0",
    "groovy_version": "0.1.0",
    "id": "cache-load-normalize-0001",
    "metadata": {
        "title": "Cache Load Normalize",
        "author": "groovy",
        "description": "Core cache-hit micrograph",
        "tags": ["test"],
        "created_at": "2026-07-26T00:00:00Z",
        "modified_at": "2026-07-26T00:00:00Z",
    },
    "nodes": [
        {
            "id": "n1",
            "type": "LoadAudio",
            "pos": {"x": 0, "y": 0},
            "widgets": {"path": "assets/samples/dialogue_48k.wav"},
        },
        {
            "id": "n2",
            "type": "Normalize",
            "pos": {"x": 240, "y": 0},
            "widgets": {"mode": "peak", "target_peak_db": -1.0},
        },
        {"id": "n3", "type": "Preview", "pos": {"x": 480, "y": 0}, "widgets": {}},
    ],
    "links": [
        {"id": "l1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"},
        {"id": "l2", "from": ["n2", 0], "to": ["n3", 0], "type": "AUDIO"},
    ],
    "groups": [],
    "view": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
}


def test_compute_node_signature_stable() -> None:
    sig_a = compute_node_signature("Normalize", {"target_lufs": -16.0}, {"audio": type("Buf", (), {"id": "abc"})()})
    sig_b = compute_node_signature("Normalize", {"target_lufs": -16.0}, {"audio": type("Buf", (), {"id": "abc"})()})
    sig_c = compute_node_signature("Normalize", {"target_lufs": -14.0}, {"audio": type("Buf", (), {"id": "abc"})()})
    assert sig_a == sig_b
    assert sig_a != sig_c


def test_executor_skips_unchanged_nodes(tmp_path: Path) -> None:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    tone = 0.25 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, int(sr * 0.5), endpoint=False))
    sf.write(assets / "dialogue_48k.wav", tone, sr)

    workflow = Workflow.model_validate(CACHE_WORKFLOW)
    executor = Executor(tmp_path)
    first = executor.execute(workflow, target_nodes=["n3"])
    assert first.status == "completed", first.error
    second = executor.execute(workflow, target_nodes=["n3"])
    assert second.status == "completed", second.error

    manifest = json.loads(Path(first.manifest_path).read_text())
    hits = [n for n in manifest["nodes"] if n.get("cache_hit")]
    assert len(hits) == 0

    manifest2 = json.loads(Path(second.manifest_path).read_text())
    hits2 = [n for n in manifest2["nodes"] if n.get("cache_hit")]
    assert len(hits2) >= 2


CONTROL_CURVE_WORKFLOW = {
    "schema_version": "1.0.0",
    "groovy_version": "0.1.0",
    "id": "cache-control-curve-0001",
    "metadata": {
        "title": "Cache ControlCurve",
        "author": "groovy",
        "description": "Stale automation artifact recovery",
        "tags": ["test"],
        "created_at": "2026-07-26T00:00:00Z",
        "modified_at": "2026-07-26T00:00:00Z",
    },
    "nodes": [
        {
            "id": "n1",
            "type": "ControlCurve",
            "pos": {"x": 0, "y": 0},
            "widgets": {
                "start_value": 0.0,
                "end_value": 1.0,
                "frame_count": 4800,
                "sample_rate": 48000,
                "points": '[{"t":0,"v":0},{"t":1,"v":1}]',
            },
        },
        {
            "id": "n2",
            "type": "LoadAudio",
            "pos": {"x": 0, "y": 120},
            "widgets": {"path": "assets/samples/dialogue_48k.wav"},
        },
        {
            "id": "n3",
            "type": "AutomationApply",
            "pos": {"x": 240, "y": 0},
            "widgets": {"gain": 1.0},
        },
        {"id": "n4", "type": "Preview", "pos": {"x": 480, "y": 0}, "widgets": {}},
    ],
    "links": [
        {"id": "l1", "from": ["n2", 0], "to": ["n3", 0], "type": "AUDIO"},
        {"id": "l2", "from": ["n1", 0], "to": ["n3", 1], "type": "AUTOMATION"},
        {"id": "l3", "from": ["n3", 0], "to": ["n4", 0], "type": "AUDIO"},
    ],
    "groups": [],
    "view": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
}


def test_stale_automation_artifact_forces_cache_miss(tmp_path: Path) -> None:
    """node_state without automation files must re-run ControlCurve, not fail the job."""
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    tone = 0.25 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.25, int(sr * 0.25), endpoint=False))
    sf.write(assets / "dialogue_48k.wav", tone, sr)

    workflow = Workflow.model_validate(CONTROL_CURVE_WORKFLOW)
    executor = Executor(tmp_path)
    first = executor.execute(workflow, target_nodes=["n4"])
    assert first.status == "completed", first.error

    auto_id = first.outputs["n1"]["automation_id"]
    for suffix in (".automation.f64", ".automation.meta.json"):
        path = tmp_path / ".groovy" / "cache" / f"{auto_id}{suffix}"
        assert path.exists()
        path.unlink()

    second = executor.execute(workflow, target_nodes=["n4"])
    assert second.status == "completed", second.error
    manifest2 = json.loads(Path(second.manifest_path).read_text())
    curve_node = next(n for n in manifest2["nodes"] if n["node_id"] == "n1")
    assert curve_node["cache_hit"] is False
