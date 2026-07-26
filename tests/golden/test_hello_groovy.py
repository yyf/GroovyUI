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
        "TTS",
        "Normalize",
        "ControlCurve",
        "ControlCurve",
        "ControlCurve",
        "ControlCurve",
        "ControlCurve",
        "Granulate",
        "Preview",
        "SaveAudio",
    ]
    assert "Granulate" in NODE_REGISTRY
    granulate = next(n for n in workflow.nodes if n.type == "Granulate")
    assert granulate.widgets.get("window") == "exp"
    assert int(granulate.widgets.get("spray", 0)) >= 2
    curve_links = [l for l in workflow.links if l.to[0] == granulate.id and l.type == "AUTOMATION"]
    assert len(curve_links) == 5
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]


def test_hello_groovy_stub_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    from groovy.registry import ModelRegistry

    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    ModelRegistry(tmp_path).installer.install("kokoro-82m")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n4", "n5"])
    assert out.status == "completed", out.error
    assert out.outputs["n4"]["type"] == "AUDIO"
