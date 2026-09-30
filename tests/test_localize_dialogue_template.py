"""Localize Dialogue (A→B) template + SpeechTranslate node."""

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
from template_fixtures import require_template


def test_speech_translate_node_schema() -> None:
    spec = NODE_REGISTRY["SpeechTranslate"].describe()
    assert any(s["name"] == "audio" and s["type"] == "AUDIO" for s in spec["inputs"])
    widgets = {w["name"]: w for w in spec.get("widgets", [])}
    assert widgets["model"]["type"] == "MODEL_REF"
    assert "src_lang" in widgets and "tgt_lang" in widgets
    assert widgets["speaker_id"]["type"] == "INT"
    assert widgets["speaker_id"]["min"] == 0 and widgets["speaker_id"]["max"] == 199
    assert spec["outputs"][0]["type"] == "AUDIO"


def test_seamless_lang_normalize() -> None:
    from groovy.nodes.ai.backends.seamless_runner import normalize_lang

    assert normalize_lang("en") == "eng"
    assert normalize_lang("ES") == "spa"
    assert normalize_lang("fra") == "fra"


def test_localize_dialogue_template_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("localize-dialogue-a-to-b")
    data = json.loads(path.read_text())
    assert "featured" in data["metadata"]["tags"]
    st = next(node for node in data["nodes"] if node["type"] == "SpeechTranslate")
    assert st["widgets"]["model"] == "seamless-m4t-v2-large"
    assert st["widgets"]["src_lang"] == "eng"
    assert st["widgets"]["tgt_lang"] == "spa"
    assert st["widgets"].get("speaker_id", 0) == 0

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    sample = tmp_path / "assets" / "samples" / "podcast_denoise_demo.wav"
    sample.parent.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    sf.write(sample, 0.2 * np.sin(2 * np.pi * 220 * t), sr)

    registry = ModelRegistry(tmp_path)
    registry.installer.install("deepfilternet-v3")
    registry.installer.install("seamless-m4t-v2-large")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n5", "n6"])
    assert out.status == "completed", out.error
    assert out.outputs["n5"]["type"] == "AUDIO"
    assert out.outputs["n6"]["type"] == "STRING"  # SaveAudio write path
