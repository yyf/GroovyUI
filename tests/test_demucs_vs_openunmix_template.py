from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

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


def test_demucs_vs_openunmix_template_shape_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("demucs-vs-openunmix")
    assert path.as_posix().endswith("/templates/demucs-vs-openunmix.groovy.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "Demucs vs Open-Unmix" in data["metadata"]["title"]
    nodes = {node["id"]: node for node in data["nodes"]}
    assert nodes["n2"]["type"] == "SeparateStems"
    assert nodes["n2"]["widgets"]["model"] == "demucs-v4"
    assert nodes["n3"]["type"] == "SeparateStems"
    assert nodes["n3"]["widgets"]["model"] == "openunmix-umx"
    assert nodes["n4"]["type"] == "Preview"
    assert nodes["n5"]["type"] == "Preview"

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [error.message for error in result.errors]

    sample = tmp_path / "assets" / "samples" / "stem_separation_demo.wav"
    sample.parent.mkdir(parents=True)
    sr = 44100
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    sf.write(sample, 0.2 * np.sin(2 * np.pi * 220 * t), sr)

    registry = ModelRegistry(tmp_path)
    registry.installer.install("demucs-v4")
    registry.installer.install("openunmix-umx")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n4", "n5"])
    assert out.status == "completed", out.error
    assert out.outputs["n4"]["type"] == "AUDIO"
    assert out.outputs["n5"]["type"] == "AUDIO"
