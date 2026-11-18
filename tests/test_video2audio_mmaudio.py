"""Video2Audio MMAudio Foley registry wiring and video-to-audio template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.executor.media_io import ffmpeg_available
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import NODE_REGISTRY
from groovy.registry import ModelRegistry
from groovy.registry.catalog import ModelCatalog
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata
from groovy.schema.validate import validate_workflow
from template_fixtures import require_template

register_core()
register_ai()


def test_video2audio_lists_mmaudio() -> None:
    assert "Video2Audio" in NODE_REGISTRY
    models = NODE_REGISTRY["Video2Audio"].COMPATIBLE_MODELS
    assert models[0] == "mmaudio-large-44k-v2"
    assert "diff-foley" in models
    assert "vibe-v2m" not in models


def test_mmaudio_seed_entry() -> None:
    manifest = ModelCatalog().get("mmaudio-large-44k-v2")
    assert manifest is not None
    assert manifest.status == "published"
    assert manifest.install.dev_stub is False
    assert "Video2Audio" in manifest.compatible_nodes
    assert manifest.license.spdx == "CC-BY-NC-4.0"
    assert manifest.license.commercial_ok is False
    assert "video-to-audio" in manifest.task_types


def test_video2audio_stub_render_mmaudio(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    samples = tmp_path / "assets" / "samples"
    samples.mkdir(parents=True)
    (samples / "clip.mp4").write_bytes(b"ftypisom")

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="video2audio-mmaudio-stub",
        metadata=WorkflowMetadata(title="video2audio-mmaudio-stub"),
        nodes=[
            NodeInstance(
                id="n1",
                type="Video2Audio",
                pos={"x": 0, "y": 0},
                widgets={
                    "model": "mmaudio-large-44k-v2",
                    "path": "assets/samples/clip.mp4",
                    "prompt": "rain on pavement",
                    "duration": 2.0,
                    "seed": 7,
                },
            ),
            NodeInstance(id="n2", type="Preview", pos={"x": 280, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"}),
        ],
    )
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    state = registry.installer.install("mmaudio-large-44k-v2")
    assert state.status == "ready", state.error

    out = Executor(tmp_path).execute(workflow, target_nodes=["n2"])
    assert out.status == "completed", out.error
    assert out.outputs["n1"]["type"] == "AUDIO"


def test_video_to_audio_mmaudio_template_stub(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("video-to-audio")
    data = json.loads(path.read_text())
    assert "featured" in data["metadata"]["tags"]
    gen = next(node for node in data["nodes"] if node["type"] == "Video2Audio")
    assert gen["widgets"]["model"] == "mmaudio-large-44k-v2"
    assert gen["widgets"]["path"] == "assets/samples/video480p.mov"

    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH (MuxVideo / SaveVideo path)")

    sample = Path(__file__).resolve().parents[1] / "assets" / "samples" / "video480p.mov"
    dest = tmp_path / "assets" / "samples" / "video480p.mov"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if sample.is_file():
        dest.write_bytes(sample.read_bytes())
    else:
        pytest.skip("assets/samples/video480p.mov not present")

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    registry.installer.install("mmaudio-large-44k-v2")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n3", "n4", "n6", "n7"])
    assert out.status == "completed", out.error
    assert out.outputs["n3"]["type"] == "AUDIO"
    assert out.outputs["n6"]["type"] == "VIDEO"
    assert out.outputs["n7"]["type"] == "STRING"
