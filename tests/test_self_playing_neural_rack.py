"""Self-playing neural rack: AutomationToMIDI → ACE oscillator + RAVE filter."""

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

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "self-playing-neural-rack.groovy.json"


def test_automation_to_midi_registered() -> None:
    assert "AutomationToMIDI" in NODE_REGISTRY
    schema = NODE_REGISTRY["AutomationToMIDI"].describe()
    names = [item["name"] for item in schema["inputs"]]
    assert names[0] == "cv"
    assert schema["outputs"][0]["type"] == "MIDI"


def test_self_playing_neural_rack_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    data = json.loads(TEMPLATE.read_text())
    assert "featured" not in data["metadata"]["tags"]
    types = {node["type"] for node in data["nodes"]}
    assert {"Clock", "Quantizer", "AutomationToMIDI", "GenerateAudio", "TimbreTransfer", "ObjectMerge"} <= types
    gen = next(node for node in data["nodes"] if node["type"] == "GenerateAudio")
    assert gen["widgets"]["model"] == "ace-step-1.5"
    assert gen["widgets"]["seconds_total"] == 10.0
    rave = next(node for node in data["nodes"] if node["type"] == "TimbreTransfer")
    assert rave["widgets"]["model"] == "rave-v1"
    assert any(
        link["from"] == ["n7", 0] and link["to"] == ["n9", 1] and link["type"] == "MIDI"
        for link in data["links"]
    )

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [error.message for error in result.errors]

    for node in workflow.nodes:
        if node.type in {"Clock", "NoiseGenerator", "Oscillator"}:
            node.widgets["duration_sec"] = 0.4
        if node.type == "GenerateAudio":
            node.widgets["seconds_total"] = 0.4

    registry = ModelRegistry(tmp_path)
    for model_id in ("ace-step-1.5", "rave-v1", "rawnet2-asvspoof"):
        registry.store.mark_ready(model_id)

    out = Executor(tmp_path).execute(workflow, target_nodes=["n7", "n18", "n19", "n21"])
    assert out.status == "completed", out.error
    assert out.outputs["n7"]["type"] == "MIDI"
    assert out.outputs["n18"]["type"] == "AUDIO"
    assert out.outputs["n21"]["type"] == "AUTHENTICITY"


MODULAR_TEMPLATE = ROOT / "templates" / "neural-modular-rack.groovy.json"


def test_neural_modular_rack_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    data = json.loads(MODULAR_TEMPLATE.read_text())
    assert "featured" in data["metadata"]["tags"]
    types = {node["type"] for node in data["nodes"]}
    assert "AmbisonicEncode" not in types
    assert "AmbisonicDecode" not in types
    assert {"Clock", "Quantizer", "Logic", "Filter", "Reverb", "Granulate", "AutomationToMIDI", "GenerateAudio", "Mix"} <= types
    assert "TimbreTransfer" not in types
    assert "DeepfakeDetect" not in types
    drone_filter = next(
        node for node in data["nodes"] if node["type"] == "Filter" and node["widgets"].get("filter_type") == "bandpass"
    )
    assert drone_filter["widgets"]["q"] >= 5.0
    reverb = next(node for node in data["nodes"] if node["type"] == "Reverb")
    assert reverb["widgets"]["mix"] <= 0.1
    clocks = [node for node in data["nodes"] if node["type"] == "Clock"]
    assert {clock["widgets"]["bpm"] for clock in clocks} == {88.0, 44.0}
    gen = next(node for node in data["nodes"] if node["type"] == "GenerateAudio")
    assert gen["widgets"]["model"] == "ace-step-1.5"
    assert gen["widgets"]["seconds_total"] == 10.0

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [error.message for error in result.errors]

    for node in workflow.nodes:
        if node.type in {"Clock", "NoiseGenerator", "Oscillator", "LFO", "Envelope"}:
            node.widgets["duration_sec"] = 0.4
        if node.type == "ControlCurve":
            node.widgets["frame_count"] = 19200
        if node.type == "GenerateAudio":
            node.widgets["seconds_total"] = 0.4

    registry = ModelRegistry(tmp_path)
    registry.store.mark_ready("ace-step-1.5")

    out = Executor(tmp_path).execute(workflow, target_nodes=["n22", "n32", "n33"])
    assert out.status == "completed", out.error
    assert out.outputs["n22"]["type"] == "MIDI"
    assert out.outputs["n32"]["type"] == "AUDIO"
