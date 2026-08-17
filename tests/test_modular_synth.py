from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from groovy.executor import Executor
from groovy.node import NODE_REGISTRY
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata

register_core()

MODULAR_TYPES = [
    "NoiseGenerator",
    "Oscillator",
    "MatrixMixer",
    "Filter",
    "Amplifier",
    "Envelope",
    "LFO",
    "Attenuator",
    "Reverb",
    "Logic",
    "Comparator",
    "SampleAndHold",
    "Quantizer",
    "Clock",
    "AutomationToMIDI",
]


def _audio_id(output: dict) -> str:
    return str(output.get("audio_id") or output.get("cache_id"))


def _auto_id(output: dict) -> str:
    return str(output.get("automation_id") or output.get("cache_id"))


def test_modular_nodes_registered() -> None:
    for name in MODULAR_TYPES:
        assert name in NODE_REGISTRY, name
    schema = NODE_REGISTRY["SignalGenerator"].describe()
    wave = next(w for w in schema["widgets"] if w["name"] == "waveform")
    assert wave.get("choices") == ["sine", "saw", "square", "triangle"]


def test_noise_oscillator_filter_amp_chain(tmp_path: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="mod-audio-chain",
        metadata=WorkflowMetadata(title="modular audio"),
        nodes=[
            NodeInstance(
                id="noise",
                type="NoiseGenerator",
                pos={"x": 0, "y": 0},
                widgets={"color": "white", "amplitude": 0.4, "duration_sec": 0.2, "sample_rate": 48000, "seed": 1},
            ),
            NodeInstance(
                id="filt",
                type="Filter",
                pos={"x": 200, "y": 0},
                widgets={"filter_type": "lowpass", "cutoff_hz": 800.0, "q": 0.7},
            ),
            NodeInstance(
                id="env",
                type="Envelope",
                pos={"x": 0, "y": 120},
                widgets={
                    "attack_ms": 5,
                    "decay_ms": 40,
                    "sustain": 0.5,
                    "release_ms": 80,
                    "duration_sec": 0.2,
                    "sample_rate": 48000,
                },
            ),
            NodeInstance(id="amp", type="Amplifier", pos={"x": 400, "y": 0}, widgets={"gain": 0.8}),
            NodeInstance(id="att", type="Attenuator", pos={"x": 600, "y": 0}, widgets={"amount": 0.5}),
            NodeInstance(id="prev", type="Preview", pos={"x": 800, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["noise", 0], "to": ["filt", 0], "type": "AUDIO"}),
            Link(id="l2", **{"from": ["filt", 0], "to": ["amp", 0], "type": "AUDIO"}),
            Link(id="l3", **{"from": ["env", 0], "to": ["amp", 1], "type": "AUTOMATION"}),
            Link(id="l4", **{"from": ["amp", 0], "to": ["att", 0], "type": "AUDIO"}),
            Link(id="l5", **{"from": ["att", 0], "to": ["prev", 0], "type": "AUDIO"}),
        ],
    )
    # amp inputs: audio=0, cv=1 — verify socket order from schema
    amp_schema = NODE_REGISTRY["Amplifier"].describe()
    amp_inputs = [s["name"] for s in amp_schema["inputs"]]
    assert amp_inputs[0] == "audio"
    assert amp_inputs[1] == "cv"

    result = Executor(tmp_path).execute(workflow, target_nodes=["prev"])
    assert result.status == "completed", result.error


def test_reverb_mix_and_passthrough(tmp_path: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="mod-reverb",
        metadata=WorkflowMetadata(title="reverb"),
        nodes=[
            NodeInstance(
                id="osc",
                type="Oscillator",
                pos={"x": 0, "y": 0},
                widgets={
                    "waveform": "square",
                    "frequency_hz": 110.0,
                    "amplitude_default": 0.4,
                    "duration_sec": 0.25,
                    "sample_rate": 48000,
                },
            ),
            NodeInstance(
                id="rev",
                type="Reverb",
                pos={"x": 200, "y": 0},
                widgets={"mix": 0.35, "room_sec": 0.8, "damping": 0.5},
            ),
            NodeInstance(id="prev", type="Preview", pos={"x": 400, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["osc", 0], "to": ["rev", 0], "type": "AUDIO"}),
            Link(id="l2", **{"from": ["rev", 0], "to": ["prev", 0], "type": "AUDIO"}),
        ],
    )
    schema = NODE_REGISTRY["Reverb"].describe()
    assert [s["name"] for s in schema["inputs"]][:2] == ["audio", "mix_cv"]
    ex = Executor(tmp_path)
    result = ex.execute(workflow, target_nodes=["prev"])
    assert result.status == "completed", result.error
    _, pcm = ex.cache.load_audio(_audio_id(result.outputs["prev"]))
    assert pcm.shape[1] > 1000
    assert float(np.max(np.abs(pcm))) > 0.01


def test_oscillator_and_matrix_mixer(tmp_path: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="mod-osc-mix",
        metadata=WorkflowMetadata(title="osc mix"),
        nodes=[
            NodeInstance(
                id="o1",
                type="Oscillator",
                pos={"x": 0, "y": 0},
                widgets={"waveform": "sine", "frequency_hz": 220.0, "amplitude_default": 0.3, "duration_sec": 0.15},
            ),
            NodeInstance(
                id="o2",
                type="Oscillator",
                pos={"x": 0, "y": 120},
                widgets={"waveform": "saw", "frequency_hz": 330.0, "amplitude_default": 0.2, "duration_sec": 0.15},
            ),
            NodeInstance(
                id="mix",
                type="MatrixMixer",
                pos={"x": 220, "y": 40},
                widgets={
                    "gain_0_0": 1.0,
                    "gain_1_0": 0.5,
                    "gain_0_1": 0.0,
                    "gain_1_1": 1.0,
                },
            ),
            NodeInstance(id="prev0", type="Preview", pos={"x": 420, "y": 0}, widgets={}),
            NodeInstance(id="prev1", type="Preview", pos={"x": 420, "y": 120}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["o1", 0], "to": ["mix", 0], "type": "AUDIO"}),
            Link(id="l2", **{"from": ["o2", 0], "to": ["mix", 1], "type": "AUDIO"}),
            Link(id="l3", **{"from": ["mix", 0], "to": ["prev0", 0], "type": "AUDIO"}),
            Link(id="l4", **{"from": ["mix", 1], "to": ["prev1", 0], "type": "AUDIO"}),
        ],
    )
    mix_schema = NODE_REGISTRY["MatrixMixer"].describe()
    names = [s["name"] for s in mix_schema["inputs"]]
    assert names[:2] == ["in_0", "in_1"]
    outs = [s["name"] for s in mix_schema["outputs"]]
    assert outs == ["out_0", "out_1", "out_2", "out_3"]
    assert any(w["name"] == "gain_1_1" for w in mix_schema["widgets"])
    executor = Executor(tmp_path)
    result = executor.execute(workflow, target_nodes=["prev0", "prev1"])
    assert result.status == "completed", result.error
    mix_out = result.outputs["mix"]
    assert mix_out.get("type") == "MULTI"
    assert len(mix_out.get("outputs") or []) == 4
    _, pcm0 = executor.cache.load_audio(_audio_id(mix_out["outputs"][0]))
    _, pcm1 = executor.cache.load_audio(_audio_id(mix_out["outputs"][1]))
    assert float(np.max(np.abs(pcm0))) > 0.05
    assert float(np.max(np.abs(pcm1))) > 0.05


def test_matrix_mixer_legacy_gain_widgets(tmp_path: Path) -> None:
    """Old gain_0..gain_3 map onto out_0 column."""
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="mod-mix-legacy",
        metadata=WorkflowMetadata(title="legacy gains"),
        nodes=[
            NodeInstance(
                id="o1",
                type="Oscillator",
                pos={"x": 0, "y": 0},
                widgets={"waveform": "sine", "frequency_hz": 200.0, "amplitude_default": 0.4, "duration_sec": 0.1},
            ),
            NodeInstance(id="mix", type="MatrixMixer", pos={"x": 200, "y": 0}, widgets={"gain_0": 0.8}),
            NodeInstance(id="prev", type="Preview", pos={"x": 400, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["o1", 0], "to": ["mix", 0], "type": "AUDIO"}),
            Link(id="l2", **{"from": ["mix", 0], "to": ["prev", 0], "type": "AUDIO"}),
        ],
    )
    ex = Executor(tmp_path / "legacy")
    result = ex.execute(workflow, target_nodes=["prev"])
    assert result.status == "completed", result.error


def test_control_modular_nodes(tmp_path: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="mod-control",
        metadata=WorkflowMetadata(title="control rack"),
        nodes=[
            NodeInstance(
                id="lfo",
                type="LFO",
                pos={"x": 0, "y": 0},
                widgets={"rate_hz": 4.0, "amplitude": 1.0, "duration_sec": 0.25, "sample_rate": 48000},
            ),
            NodeInstance(
                id="clk",
                type="Clock",
                pos={"x": 0, "y": 120},
                widgets={"bpm": 240.0, "pulse_ms": 5.0, "duration_sec": 0.25, "sample_rate": 48000},
            ),
            NodeInstance(id="cmp", type="Comparator", pos={"x": 220, "y": 0}, widgets={"threshold": 0.0}),
            NodeInstance(id="logic", type="Logic", pos={"x": 420, "y": 40}, widgets={"operation": "and"}),
            NodeInstance(id="sah", type="SampleAndHold", pos={"x": 220, "y": 120}, widgets={}),
            NodeInstance(
                id="quant",
                type="Quantizer",
                pos={"x": 420, "y": 120},
                widgets={"scale": "major", "root_hz": 220.0},
            ),
            NodeInstance(
                id="osc",
                type="Oscillator",
                pos={"x": 640, "y": 80},
                widgets={"waveform": "sine", "frequency_hz": 220.0, "amplitude_default": 0.3, "duration_sec": 0.25},
            ),
            NodeInstance(id="prev", type="Preview", pos={"x": 860, "y": 80}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["lfo", 0], "to": ["cmp", 0], "type": "AUTOMATION"}),
            Link(id="l2", **{"from": ["cmp", 0], "to": ["logic", 0], "type": "AUTOMATION"}),
            Link(id="l3", **{"from": ["clk", 0], "to": ["logic", 1], "type": "AUTOMATION"}),
            Link(id="l4", **{"from": ["lfo", 0], "to": ["sah", 1], "type": "AUTOMATION"}),
            Link(id="l5", **{"from": ["clk", 0], "to": ["sah", 0], "type": "AUTOMATION"}),
            Link(id="l6", **{"from": ["sah", 0], "to": ["quant", 0], "type": "AUTOMATION"}),
            Link(id="l7", **{"from": ["quant", 0], "to": ["osc", 0], "type": "AUTOMATION"}),
            Link(id="l8", **{"from": ["osc", 0], "to": ["prev", 0], "type": "AUDIO"}),
        ],
    )
    # SampleAndHold: required clock first, then optional signal
    sah = NODE_REGISTRY["SampleAndHold"].describe()
    assert [s["name"] for s in sah["inputs"]][0] == "clock"
    result = Executor(tmp_path).execute(workflow, target_nodes=["prev"])
    assert result.status == "completed", result.error
    auto = Executor(tmp_path)
    # re-run to inspect quantizer output range
    result2 = auto.execute(workflow, target_nodes=["quant", "prev"])
    assert result2.status == "completed", result2.error
    q = auto.cache.load_automation(_auto_id(result2.outputs["quant"]))
    assert float(np.min(q.values)) >= 20.0
    assert float(np.max(q.values)) < 5000.0


def test_pink_brown_noise_deterministic(tmp_path: Path) -> None:
    for color in ("pink", "brown"):
        workflow = Workflow(
            schema_version="1.0.0",
            groovy_version="0.1.0",
            id=f"noise-{color}",
            metadata=WorkflowMetadata(title=color),
            nodes=[
                NodeInstance(
                    id="n1",
                    type="NoiseGenerator",
                    pos={"x": 0, "y": 0},
                    widgets={"color": color, "duration_sec": 0.1, "seed": 42, "amplitude": 0.5},
                ),
                NodeInstance(id="n2", type="Preview", pos={"x": 200, "y": 0}, widgets={}),
            ],
            links=[Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"})],
        )
        ex = Executor(tmp_path / color)
        result = ex.execute(workflow, target_nodes=["n2"])
        assert result.status == "completed", result.error


def test_float_feeds_float_math(tmp_path: Path) -> None:
    assert "Float" in NODE_REGISTRY
    schema = NODE_REGISTRY["Float"].describe()
    assert schema["outputs"][0]["type"] == "AUTOMATION"
    assert any(w["name"] == "value" for w in schema["widgets"])
    assert not any(s["name"] == "value" for s in schema["inputs"])

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="float-math",
        metadata=WorkflowMetadata(title="Float → FloatMath"),
        nodes=[
            NodeInstance(
                id="a",
                type="Float",
                pos={"x": 0, "y": 0},
                widgets={"value": 2.0, "duration_sec": 0.05, "sample_rate": 48000},
            ),
            NodeInstance(
                id="b",
                type="Float",
                pos={"x": 0, "y": 80},
                widgets={"value": 3.0, "duration_sec": 0.05, "sample_rate": 48000},
            ),
            NodeInstance(
                id="math",
                type="FloatMath",
                pos={"x": 220, "y": 40},
                widgets={"operation": "multiply"},
            ),
        ],
        links=[
            Link(id="l1", **{"from": ["a", 0], "to": ["math", 0], "type": "AUTOMATION"}),
            Link(id="l2", **{"from": ["b", 0], "to": ["math", 1], "type": "AUTOMATION"}),
        ],
    )
    ex = Executor(tmp_path / "float")
    result = ex.execute(workflow, target_nodes=["math"])
    assert result.status == "completed", result.error
    curve = ex.cache.load_automation(_auto_id(result.outputs["math"]))
    assert float(np.mean(curve.values)) == pytest.approx(6.0, abs=1e-6)


def test_hz_to_midi_note_a4() -> None:
    from groovy.nodes.core.modular_synth import hz_to_midi_note

    assert int(hz_to_midi_note(440.0)[()]) == 69
    assert int(hz_to_midi_note(np.array([220.0, 440.0, 880.0]))[1]) == 69


def test_automation_to_midi_from_quantizer(tmp_path: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="cv-to-midi",
        metadata=WorkflowMetadata(title="automation to midi"),
        nodes=[
            NodeInstance(
                id="clk",
                type="Clock",
                pos={"x": 0, "y": 0},
                widgets={"bpm": 240.0, "pulse_ms": 40.0, "duration_sec": 0.5, "sample_rate": 48000},
            ),
            NodeInstance(
                id="noise",
                type="NoiseGenerator",
                pos={"x": 0, "y": 120},
                widgets={"color": "white", "amplitude": 1.0, "duration_sec": 0.5, "sample_rate": 48000, "seed": 3},
            ),
            NodeInstance(id="sah", type="SampleAndHold", pos={"x": 220, "y": 40}, widgets={"threshold": 0.5}),
            NodeInstance(
                id="quant",
                type="Quantizer",
                pos={"x": 440, "y": 40},
                widgets={"scale": "minor", "root_hz": 220.0},
            ),
            NodeInstance(
                id="midi",
                type="AutomationToMIDI",
                pos={"x": 660, "y": 40},
                widgets={"midi_kind": "score", "velocity": 0.8},
            ),
        ],
        links=[
            Link(id="l1", **{"from": ["clk", 0], "to": ["sah", 0], "type": "AUTOMATION"}),
            Link(id="l2", **{"from": ["noise", 0], "to": ["sah", 2], "type": "AUDIO"}),
            Link(id="l3", **{"from": ["sah", 0], "to": ["quant", 0], "type": "AUTOMATION"}),
            Link(id="l4", **{"from": ["quant", 0], "to": ["midi", 0], "type": "AUTOMATION"}),
        ],
    )
    ex = Executor(tmp_path / "cv-midi")
    result = ex.execute(workflow, target_nodes=["midi"])
    assert result.status == "completed", result.error
    assert result.outputs["midi"]["type"] == "MIDI"
    midi_id = result.outputs["midi"]["midi_id"]
    midi = ex.cache.load_midi(midi_id)
    assert midi.midi_kind == "score"
    assert midi.frame_count == 24000
    assert (tmp_path / "cv-midi" / ".groovy" / "cache" / f"{midi_id}.mid").exists()
    from groovy.executor.live_midi import load_midi_events

    events = load_midi_events(ex.cache, midi_id)
    ons = [e for e in events if e.get("type") == "note_on"]
    assert ons, "expected at least one note_on from quantized CV"