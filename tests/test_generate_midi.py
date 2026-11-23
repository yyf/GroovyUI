"""GenerateMidi + PreviewMidi smoke tests (stub path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.node import NODE_REGISTRY, known_node_types
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.registry.catalog import ModelCatalog
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata
from groovy.schema.validate import validate_workflow
from template_fixtures import require_template

register_core()
register_ai()


def test_generate_midi_registered() -> None:
    assert "GenerateMidi" in NODE_REGISTRY
    assert NODE_REGISTRY["GenerateMidi"].RETURN_TYPES == ("MIDI", "GENERATE_LOG")
    assert NODE_REGISTRY["GenerateMidi"].OUTPUT_NAMES == ("midi", "log")
    opt = NODE_REGISTRY["GenerateMidi"].INPUT_TYPES()["optional"]
    assert opt["text"][0] == "TEXT"
    assert NODE_REGISTRY["GenerateMidi"].COMPATIBLE_MODELS[0] == "midi-llm"


def test_preview_midi_registered() -> None:
    assert "PreviewMidi" in NODE_REGISTRY
    assert NODE_REGISTRY["PreviewMidi"].RETURN_TYPES == ("MIDI",)
    req = NODE_REGISTRY["PreviewMidi"].INPUT_TYPES()["required"]
    assert req["midi"][0] == "MIDI"


def test_synth_midi_registered() -> None:
    assert "SynthMidi" in NODE_REGISTRY
    assert NODE_REGISTRY["SynthMidi"].RETURN_TYPES == ("AUDIO",)
    req = NODE_REGISTRY["SynthMidi"].INPUT_TYPES()["required"]
    assert req["midi"][0] == "MIDI"
    opt = NODE_REGISTRY["SynthMidi"].INPUT_TYPES()["optional"]
    assert opt["sample_rate"][1]["default"] == 48000


def test_save_midi_registered() -> None:
    assert "SaveMidi" in NODE_REGISTRY
    assert NODE_REGISTRY["SaveMidi"].RETURN_TYPES == ("STRING",)
    req = NODE_REGISTRY["SaveMidi"].INPUT_TYPES()["required"]
    assert req["midi"][0] == "MIDI"


def test_midi_llm_and_midi_gen_seed_entries() -> None:
    llm = ModelCatalog().get("midi-llm")
    assert llm is not None
    assert llm.status == "published"
    assert llm.license.commercial_ok is True
    assert "GenerateMidi" in llm.compatible_nodes
    assert "text-to-midi" in llm.task_types

    stub = ModelCatalog().get("midi-gen")
    assert stub is not None
    assert stub.install.dev_stub is True
    assert stub.license.commercial_ok is True


def test_generate_midi_stub_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    ModelRegistry(tmp_path).installer.install("midi-gen")
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="generate-midi-stub",
        metadata=WorkflowMetadata(title="generate-midi-stub"),
        nodes=[
            NodeInstance(
                id="n0",
                type="Prompt",
                pos={"x": 0, "y": 0},
                widgets={"text": "cheerful piano melody"},
            ),
            NodeInstance(
                id="n1",
                type="GenerateMidi",
                pos={"x": 280, "y": 0},
                widgets={"model": "midi-gen", "duration": 4.0, "seed": 7},
            ),
            NodeInstance(id="n2", type="PreviewMidi", pos={"x": 560, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l0", **{"from": ["n0", 0], "to": ["n1", 0], "type": "TEXT"}),
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "MIDI"}),
        ],
    )
    assert validate_workflow(workflow, known_node_types=known_node_types()).valid
    out = Executor(tmp_path).execute(workflow, target_nodes=["n2"])
    assert out.status == "completed", out.error
    assert out.outputs["n1"]["type"] == "MULTI"
    assert out.outputs["n1"]["outputs"][0]["type"] == "MIDI"
    assert out.outputs["n1"]["outputs"][0].get("midi_id")
    assert out.outputs["n1"]["outputs"][1]["type"] == "GENERATE_LOG"
    assert out.outputs["n1"]["outputs"][1].get("generate_log_id")
    assert out.outputs["n2"]["type"] == "MIDI"
    assert out.outputs["n2"].get("midi_id") == out.outputs["n1"]["outputs"][0].get("midi_id")


def test_text_to_midi_template_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("text-to-midi")
    data = json.loads(path.read_text())
    assert "text-to-midi" in data["metadata"]["tags"]
    assert data["metadata"]["title"] == "Text to MIDI"
    assert path.as_posix().endswith("/templates/text-to-midi.groovy.json")
    prompt = next(node for node in data["nodes"] if node["id"] == "n-midi-prompt")
    assert "Bohlen-Pierce microtonality" in prompt["widgets"]["text"]
    assert "Notes 0-127 only" in prompt["widgets"]["text"]
    gen = next(node for node in data["nodes"] if node["type"] == "GenerateMidi")
    assert gen["widgets"]["model"] == "midi-llm"
    assert gen["widgets"]["duration"] == 30.0
    assert any(node["type"] == "PreviewMidi" for node in data["nodes"])
    assert any(node["type"] == "SaveMidi" for node in data["nodes"])
    assert any(node["type"] == "SaveGenerateLog" for node in data["nodes"])
    synth = next(node for node in data["nodes"] if node["type"] == "SynthMidi")
    assert synth["widgets"]["sample_rate"] == 48000
    assert any(node["type"] == "SaveAudio" for node in data["nodes"])
    assert not any(node["type"] == "GenerateAudio" for node in data["nodes"])
    assert not any(node["type"] == "MIDIToAudio" for node in data["nodes"])
    assert any(
        link["from"] == ["n-midi-prompt", 0] and link["to"] == ["n-gen-midi", 0] and link["type"] == "TEXT"
        for link in data["links"]
    )
    assert any(
        link["from"] == ["n-gen-midi", 0] and link["to"] == ["n-preview-midi", 0] and link["type"] == "MIDI"
        for link in data["links"]
    )
    assert any(
        link["from"] == ["n-preview-midi", 0] and link["to"] == ["n-save-midi", 0] and link["type"] == "MIDI"
        for link in data["links"]
    )
    assert any(
        link["from"] == ["n-gen-midi", 0] and link["to"] == ["n-synth-midi", 0] and link["type"] == "MIDI"
        for link in data["links"]
    ), "GenerateMidi must wire to SynthMidi"
    assert any(
        link["from"] == ["n-gen-midi", 1]
        and link["to"] == ["n-midi-log", 0]
        and link["type"] == "GENERATE_LOG"
        for link in data["links"]
    ), "GenerateMidi.log must wire to SaveGenerateLog"

    workflow = Workflow.model_validate(data)
    assert validate_workflow(workflow, known_node_types=known_node_types()).valid
    registry = ModelRegistry(tmp_path)
    registry.installer.install("midi-llm")
    out = Executor(tmp_path).execute(
        workflow,
        target_nodes=[
            "n-preview-midi",
            "n-save-midi",
            "n-midi-log",
            "n-preview-audio",
            "n-save-audio",
        ],
    )
    assert out.status == "completed", out.error
    assert out.outputs["n-gen-midi"]["type"] == "MULTI"
    assert out.outputs["n-gen-midi"]["outputs"][1]["type"] == "GENERATE_LOG"
    assert out.outputs["n-gen-midi"]["outputs"][1].get("generate_log_id")
    assert out.outputs["n-preview-midi"]["type"] == "MIDI"
    assert out.outputs["n-preview-midi"].get("midi_id")
    assert out.outputs["n-save-midi"]["type"] == "STRING"
    rel = out.outputs["n-save-midi"]["path"]
    assert isinstance(rel, str) and rel.startswith("exports/")
    assert (tmp_path / rel).is_file()
    assert out.outputs["n-midi-log"]["type"] == "STRING"
    log_rel = out.outputs["n-midi-log"]["path"]
    assert isinstance(log_rel, str) and log_rel.startswith("exports/")
    assert (tmp_path / log_rel).is_file()
    assert out.outputs["n-preview-audio"]["type"] == "AUDIO"
    assert out.outputs["n-save-audio"]["type"] == "STRING"
    audio_rel = out.outputs["n-save-audio"]["path"]
    assert isinstance(audio_rel, str) and "exports/" in audio_rel.replace("\\", "/")
    audio_path = Path(audio_rel)
    if not audio_path.is_absolute():
        audio_path = tmp_path / audio_rel
    assert audio_path.is_file()
