"""TTS with Emotion Editing template + TTS/VoiceConvert model wiring."""

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


def test_voice_convert_lists_step_audio_editx() -> None:
    assert "step-audio-editx" in NODE_REGISTRY["VoiceConvert"].COMPATIBLE_MODELS
    inputs = NODE_REGISTRY["VoiceConvert"].describe()["inputs"]
    assert any(s["name"] == "transcript" and s["type"] == "TEXT" for s in inputs)
    widgets = {w["name"] for w in NODE_REGISTRY["VoiceConvert"].describe()["widgets"]}
    assert {"edit_type", "edit_info", "prompt_text"}.issubset(widgets)


def test_tts_emotion_edit_template_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("tts-emotion-edit")
    data = json.loads(path.read_text())
    assert data["metadata"]["title"] == "TTS with Emotion Editing"
    assert "starter" in data["metadata"]["tags"]
    assert any(n["id"] == "note-voiceconvert-edits" for n in data["nodes"])

    tts = next(node for node in data["nodes"] if node["type"] == "TTS")
    assert tts["widgets"]["model"] == "kokoro-82m"
    convert = next(node for node in data["nodes"] if node["type"] == "VoiceConvert")
    assert convert["widgets"]["model"] == "step-audio-editx"
    assert convert["widgets"]["edit_type"] == "style"
    assert convert["widgets"]["edit_info"] == "whisper"
    assert convert["widgets"]["prompt_text"]

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    registry.installer.install("kokoro-82m")
    registry.installer.install("step-audio-editx")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n5", "n6"])
    assert out.status == "completed", out.error
    assert out.outputs["n5"]["type"] == "AUDIO"
