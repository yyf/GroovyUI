"""Voice cloning template + TTS reference_audio socket."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
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


def test_tts_exposes_optional_reference_audio_socket() -> None:
    inputs = NODE_REGISTRY["TTS"].describe()["inputs"]
    assert any(s["name"] == "reference_audio" and s["type"] == "AUDIO" for s in inputs)


def test_voice_cloning_template_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = ROOT / "templates" / "voice-cloning.groovy.json"
    data = json.loads(path.read_text())
    assert "featured" in data["metadata"]["tags"]
    tts = next(node for node in data["nodes"] if node["type"] == "TTS")
    assert tts["widgets"]["model"] == "f5-tts-base"
    # LoadAudio → TTS reference_audio (socket index 1)
    assert ["n1", 0] == data["links"][0]["from"]
    assert ["n2", 1] == data["links"][0]["to"]

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    sample = tmp_path / "assets" / "samples" / "male-1.wav"
    sample.parent.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    sf.write(sample, 0.2 * np.sin(2 * np.pi * 220 * t), sr)

    registry = ModelRegistry(tmp_path)
    registry.installer.install("f5-tts-base")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n4", "n5"])
    assert out.status == "completed", out.error
    assert out.outputs["n4"]["type"] == "AUDIO"
