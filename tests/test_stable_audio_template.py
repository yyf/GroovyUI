"""Stable Audio hero template + GenerateAudio Stable Audio Open wiring."""

from __future__ import annotations

import json
from pathlib import Path

from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import NODE_REGISTRY
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]


def test_generate_audio_lists_stable_audio_model() -> None:
    assert "stable-audio-open-1.0" in NODE_REGISTRY["GenerateAudio"].COMPATIBLE_MODELS


def test_stable_audio_template_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = ROOT / "templates" / "stable-audio.groovy.json"
    data = json.loads(path.read_text())
    assert "featured" in data["metadata"]["tags"]
    assert data["nodes"][0]["widgets"]["model"] == "stable-audio-open-1.0"

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    registry.installer.install("stable-audio-open-1.0")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n3", "n4"])
    assert out.status == "completed", out.error
    assert out.outputs["n3"]["type"] == "AUDIO"
