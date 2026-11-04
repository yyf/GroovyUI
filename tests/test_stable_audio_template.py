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
from template_fixtures import require_template


def test_generate_audio_lists_stable_audio_model() -> None:
    assert "stable-audio-open-1.0" in NODE_REGISTRY["GenerateAudio"].COMPATIBLE_MODELS
    assert "stable-audio-open-small" in NODE_REGISTRY["GenerateAudio"].COMPATIBLE_MODELS
    assert "stable-audio-3-small-music" in NODE_REGISTRY["GenerateAudio"].COMPATIBLE_MODELS
    assert "stable-audio-3-small-sfx" in NODE_REGISTRY["GenerateAudio"].COMPATIBLE_MODELS


def test_stable_audio_3_small_in_seed_catalog() -> None:
    from groovy.registry.catalog import ModelCatalog

    for model_id in ("stable-audio-3-small-music", "stable-audio-3-small-sfx"):
        manifest = ModelCatalog().get(model_id)
        assert manifest is not None, model_id
        assert manifest.install.dev_stub is False
        assert manifest.license.commercial_ok is False
        assert "GenerateAudio" in manifest.compatible_nodes
        steps = next(p for p in manifest.inference_params if p.name == "num_inference_steps")
        assert steps.default == 8
        assert any(
            "stable-audio-3" in str(dep.get("package", "")) and dep.get("no_deps") is True
            for dep in manifest.install.python_deps
        )


def test_stable_audio_template_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("stable-audio")
    data = json.loads(path.read_text())
    assert "featured" in data["metadata"]["tags"]
    gen = next(node for node in data["nodes"] if node["type"] == "GenerateAudio")
    prompt = next(node for node in data["nodes"] if node["type"] == "Prompt")
    assert gen["widgets"]["model"] == "stable-audio-open-1.0"
    assert prompt["widgets"]["text"]
    assert any(
        link["from"] == ["n0", 0] and link["to"] == ["n1", 0] and link["type"] == "TEXT"
        for link in data["links"]
    )

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    registry.installer.install("stable-audio-open-1.0")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n3", "n4"])
    assert out.status == "completed", out.error
    assert out.outputs["n3"]["type"] == "AUDIO"


