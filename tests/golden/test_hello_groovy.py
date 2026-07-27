from __future__ import annotations

import json
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import NODE_REGISTRY
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "hello-groovy.groovy.json"


def test_hello_groovy_template_shape() -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    assert workflow.metadata.title == "Hello Groovy"
    types = [n.type for n in workflow.nodes]
    assert types == [
        "Prompt",
        "TTS",
        "ControlCurve",
        "AutomationApply",
        "Normalize",
        "Preview",
        "SaveAudio",
    ]
    assert "Prompt" in NODE_REGISTRY
    assert "AutomationApply" in NODE_REGISTRY
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]


def test_hello_groovy_stub_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    from groovy.registry import ModelRegistry

    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    ModelRegistry(tmp_path).installer.install("kokoro-82m")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n8", "n9"])
    assert out.status == "completed", out.error
    assert out.outputs["n8"]["type"] == "AUDIO"
