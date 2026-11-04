from __future__ import annotations

import json
from pathlib import Path

from groovy.executor import Executor
from groovy.node import NODE_REGISTRY
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow

register_core()
register_ai()

from template_fixtures import require_template

ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_node_registered() -> None:
    assert "Benchmark" in NODE_REGISTRY
    described = NODE_REGISTRY["Benchmark"].describe()
    input_names = {item["name"] for item in described["inputs"]}
    assert "hypothesis" in input_names
    assert "reference" in input_names


def test_asr_benchmark_template_shape_and_validate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("asr-benchmark-wer-cer")
    assert path.as_posix().endswith("/templates/asr-benchmark-wer-cer.groovy.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["metadata"]["title"].startswith("ASR Benchmark")
    nodes = {node["id"]: node for node in data["nodes"]}
    assert nodes["n2"]["type"] == "TTS"
    assert nodes["n2"]["widgets"]["model"] == "kokoro-82m"
    assert nodes["n4"]["widgets"]["model"] == "whisper-small-en"
    assert nodes["n5"]["widgets"]["model"] == "whisper-large-v3-turbo"
    assert nodes["n6"]["type"] == "Preview"
    assert nodes["n7"]["type"] == "Preview"
    assert nodes["n8"]["type"] == "Preview"
    assert "Benchmark" not in {node["type"] for node in data["nodes"]}

    ref_preview = [
        link
        for link in data["links"]
        if link["from"] == ["n1", 0] and link["to"] == ["n8", 1]
    ]
    assert len(ref_preview) == 1
    hyp_previews = [
        link
        for link in data["links"]
        if link["to"] in (["n6", 1], ["n7", 1]) and link["type"] == "TEXT"
    ]
    assert len(hyp_previews) == 2

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    for model_id in ("kokoro-82m", "whisper-small-en", "whisper-large-v3-turbo"):
        registry.installer.install(model_id)
    out = Executor(tmp_path).execute(workflow, target_nodes=["n6", "n7", "n8"])
    assert out.status == "completed", out.error
    assert out.outputs["n8"]["type"] == "TEXT"
    assert out.outputs["n6"]["type"] == "TEXT"
    assert out.outputs["n7"]["type"] == "TEXT"
    ref = out.outputs["n8"].get("text") or ""
    hyp_a = out.outputs["n6"].get("text") or ""
    hyp_b = out.outputs["n7"].get("text") or ""
    assert "Welcome to GroovyUI" in ref
    assert "WER" not in hyp_a and "CER" not in hyp_a
    assert "WER" not in hyp_b and "CER" not in hyp_b
