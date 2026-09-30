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
from template_fixtures import require_template
TEMPLATE = require_template("self-playing-neural-rack")


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


MODULAR_TEMPLATE = require_template("neural-modular-rack")


def test_neural_modular_rack_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    data = json.loads(MODULAR_TEMPLATE.read_text())
    assert "featured" in data["metadata"]["tags"]
    types = {node["type"] for node in data["nodes"]}
    assert "AmbisonicEncode" not in types
    assert "AmbisonicDecode" not in types
    assert {"Clock", "BeatTrack", "Quantizer", "Logic", "Filter", "Reverb", "AutomationToMIDI", "GenerateAudio", "Mix"} <= types
    assert "Granulate" in types
    grain = next(node for node in data["nodes"] if node["type"] == "Granulate")
    assert grain["widgets"]["wet_end"] <= 0.4
    assert grain["widgets"]["width"] >= 0.5
    assert "TimbreTransfer" not in types
    assert "DeepfakeDetect" not in types
    drone_filter = next(
        node for node in data["nodes"] if node["type"] == "Filter" and node["widgets"].get("filter_type") == "bandpass"
    )
    assert drone_filter["widgets"]["q"] >= 1.5
    reverb = next(node for node in data["nodes"] if node["id"] == "n30")
    assert reverb["widgets"]["mix"] <= 0.2
    sparkle = next(node for node in data["nodes"] if node["id"] == "n52")
    assert sparkle["type"] == "Reverb"
    assert sparkle["widgets"]["mix"] >= 0.5
    clocks = [node for node in data["nodes"] if node["type"] == "Clock"]
    assert {clock["widgets"]["bpm"] for clock in clocks} == {136.0, 68.0}
    gen = next(node for node in data["nodes"] if node["type"] == "GenerateAudio")
    assert gen["widgets"]["model"] == "ace-step-1.5"
    assert gen["widgets"]["seconds_total"] == 30.0
    assert "IDM" in gen["widgets"]["prompt"]
    bus = next(node for node in data["nodes"] if node["id"] == "n29")
    assert bus["widgets"]["gain_a"] == 0.5
    assert bus["widgets"]["gain_b"] == 0.5
    bass = next(node for node in data["nodes"] if node["id"] == "n14")
    assert bass["widgets"]["waveform"] == "sine"
    assert not any(link["from"] == ["n11", 0] and link["to"] == ["n14", 0] for link in data["links"])
    assert any(link["from"] == ["n3", 0] and link["to"] == ["n49", 0] for link in data["links"])
    assert any(link["from"] == ["n51", 0] and link["to"] == ["n25", 0] for link in data["links"])
    assert any(link["from"] == ["n18", 0] and link["to"] == ["n19", 1] for link in data["links"])
    assert any(link["from"] == ["n35", 0] and link["to"] == ["n20", 1] for link in data["links"])
    assert any(link["from"] == ["n23", 0] and link["to"] == ["n26", 0] for link in data["links"])
    assert any(link["from"] == ["n23", 0] and link["to"] == ["n48", 0] for link in data["links"])
    assert any(link["from"] == ["n1", 0] and link["to"] == ["n48", 1] for link in data["links"])
    assert any(link["from"] == ["n48", 0] and link["to"] == ["n18", 0] for link in data["links"])
    assert any(link["from"] == ["n48", 1] and link["to"] == ["n18", 1] for link in data["links"])
    xor_gate = next(node for node in data["nodes"] if node["id"] == "n18")
    assert xor_gate["widgets"]["operation"] == "xor"
    assert any(link["from"] == ["n1", 0] and link["to"] == ["n50", 1] for link in data["links"])
    assert any(link["from"] == ["n42", 0] and link["to"] == ["n52", 0] for link in data["links"])
    assert any(link["from"] == ["n52", 0] and link["to"] == ["n53", 0] for link in data["links"])
    assert any(link["from"] == ["n53", 0] and link["to"] == ["n51", 1] for link in data["links"])
    assert any(link["from"] == ["n48", 0] and link["to"] == ["n9", 0] for link in data["links"])
    assert any(link["from"] == ["n2", 0] and link["to"] == ["n10", 0] for link in data["links"])

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
