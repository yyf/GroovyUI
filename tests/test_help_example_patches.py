"""QA Help-tab minimal examples that can run offline without AI workers."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.node import NODE_REGISTRY, known_node_types
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata
from groovy.schema.validate import validate_workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "assets" / "samples"


def _workflow(title: str, nodes: list[NodeInstance], links: list[Link]) -> Workflow:
    return Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id=f"help-{title}",
        metadata=WorkflowMetadata(title=title),
        nodes=nodes,
        links=links,
    )


def _project_with_samples(tmp_path: Path, name: str, files: list[str]) -> Path:
    project = tmp_path / name
    dest = project / "assets" / "samples"
    dest.mkdir(parents=True, exist_ok=True)
    for filename in files:
        src = SAMPLES / filename
        assert src.is_file(), f"missing bundled sample: {src}"
        shutil.copy2(src, dest / filename)
    return project


@pytest.mark.parametrize(
    "name,workflow,targets",
    [
        (
            "oscillator",
            _workflow(
                "oscillator",
                [
                    NodeInstance(
                        id="n1",
                        type="Oscillator",
                        pos={"x": 0, "y": 0},
                        widgets={
                            "waveform": "sine",
                            "frequency_hz": 220.0,
                            "amplitude_default": 0.35,
                            "duration_sec": 0.2,
                            "sample_rate": 48000,
                        },
                    ),
                    NodeInstance(id="n2", type="PreviewAudio", pos={"x": 260, "y": 0}, widgets={}),
                ],
                [Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"})],
            ),
            ["n2"],
        ),
        (
            "filter-noise",
            _workflow(
                "filter",
                [
                    NodeInstance(
                        id="n1",
                        type="NoiseGenerator",
                        pos={"x": 0, "y": 0},
                        widgets={
                            "color": "white",
                            "amplitude": 0.4,
                            "duration_sec": 0.2,
                            "sample_rate": 48000,
                            "seed": 2,
                        },
                    ),
                    NodeInstance(
                        id="n2",
                        type="Filter",
                        pos={"x": 260, "y": 0},
                        widgets={"filter_type": "lowpass", "cutoff_hz": 1200.0, "q": 0.7},
                    ),
                    NodeInstance(id="n3", type="PreviewAudio", pos={"x": 520, "y": 0}, widgets={}),
                ],
                [
                    Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"}),
                    Link(id="l2", **{"from": ["n2", 0], "to": ["n3", 0], "type": "AUDIO"}),
                ],
            ),
            ["n3"],
        ),
        (
            "amp-envelope",
            _workflow(
                "amplifier",
                [
                    NodeInstance(
                        id="n1",
                        type="Oscillator",
                        pos={"x": 0, "y": 0},
                        widgets={
                            "waveform": "saw",
                            "frequency_hz": 110.0,
                            "amplitude_default": 0.4,
                            "duration_sec": 0.25,
                            "sample_rate": 48000,
                        },
                    ),
                    NodeInstance(
                        id="n2",
                        type="Envelope",
                        pos={"x": 0, "y": 120},
                        widgets={
                            "attack_ms": 10,
                            "decay_ms": 40,
                            "sustain": 0.4,
                            "release_ms": 80,
                            "duration_sec": 0.25,
                            "sample_rate": 48000,
                        },
                    ),
                    NodeInstance(id="n3", type="Amplifier", pos={"x": 280, "y": 0}, widgets={"gain": 0.9}),
                    NodeInstance(id="n4", type="PreviewAudio", pos={"x": 540, "y": 0}, widgets={}),
                ],
                [
                    Link(id="l1", **{"from": ["n1", 0], "to": ["n3", 0], "type": "AUDIO"}),
                    Link(id="l2", **{"from": ["n2", 0], "to": ["n3", 1], "type": "AUTOMATION"}),
                    Link(id="l3", **{"from": ["n3", 0], "to": ["n4", 0], "type": "AUDIO"}),
                ],
            ),
            ["n4"],
        ),
        (
            "float-math",
            _workflow(
                "float",
                [
                    NodeInstance(
                        id="n1",
                        type="Float",
                        pos={"x": 0, "y": 0},
                        widgets={"value": 2.0, "duration_sec": 0.05, "sample_rate": 48000},
                    ),
                    NodeInstance(
                        id="n2",
                        type="Float",
                        pos={"x": 0, "y": 80},
                        widgets={"value": 3.0, "duration_sec": 0.05, "sample_rate": 48000},
                    ),
                    NodeInstance(
                        id="n3",
                        type="FloatMath",
                        pos={"x": 220, "y": 40},
                        widgets={"operation": "multiply"},
                    ),
                ],
                [
                    Link(id="l1", **{"from": ["n1", 0], "to": ["n3", 0], "type": "AUTOMATION"}),
                    Link(id="l2", **{"from": ["n2", 0], "to": ["n3", 1], "type": "AUTOMATION"}),
                ],
            ),
            ["n3"],
        ),
        (
            "benchmark-text",
            _workflow(
                "benchmark",
                [
                    NodeInstance(
                        id="n1",
                        type="Prompt",
                        pos={"x": 0, "y": 0},
                        widgets={"text": "hello groovy"},
                    ),
                    NodeInstance(
                        id="n2",
                        type="Prompt",
                        pos={"x": 0, "y": 100},
                        widgets={"text": "hello groovy"},
                    ),
                    NodeInstance(
                        id="n3",
                        type="Benchmark",
                        pos={"x": 260, "y": 40},
                        widgets={"metric": "wer_cer", "normalize": True},
                    ),
                    NodeInstance(id="n4", type="PreviewAudio", pos={"x": 520, "y": 40}, widgets={}),
                ],
                [
                    Link(id="l1", **{"from": ["n2", 0], "to": ["n3", 0], "type": "TEXT"}),
                    Link(id="l2", **{"from": ["n1", 0], "to": ["n3", 1], "type": "TEXT"}),
                    Link(id="l3", **{"from": ["n3", 0], "to": ["n4", 1], "type": "TEXT"}),
                ],
            ),
            ["n4"],
        ),
        (
            "prompt-preview",
            _workflow(
                "prompt",
                [
                    NodeInstance(
                        id="n1",
                        type="Prompt",
                        pos={"x": 0, "y": 0},
                        widgets={"text": "Hello from GroovyUI."},
                    ),
                    NodeInstance(id="n2", type="PreviewAudio", pos={"x": 260, "y": 0}, widgets={}),
                ],
                [Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 1], "type": "TEXT"})],
            ),
            ["n2"],
        ),
        (
            "channel-merge",
            _workflow(
                "channel-merge",
                [
                    NodeInstance(
                        id="n1",
                        type="Oscillator",
                        pos={"x": 0, "y": 0},
                        widgets={
                            "waveform": "sine",
                            "frequency_hz": 220.0,
                            "amplitude_default": 0.2,
                            "duration_sec": 0.15,
                            "sample_rate": 48000,
                        },
                    ),
                    NodeInstance(
                        id="n2",
                        type="Oscillator",
                        pos={"x": 0, "y": 120},
                        widgets={
                            "waveform": "sine",
                            "frequency_hz": 330.0,
                            "amplitude_default": 0.2,
                            "duration_sec": 0.15,
                            "sample_rate": 48000,
                        },
                    ),
                    NodeInstance(
                        id="n3",
                        type="ChannelMerge",
                        pos={"x": 280, "y": 40},
                        widgets={"output_layout": "stereo"},
                    ),
                    NodeInstance(id="n4", type="PreviewAudio", pos={"x": 540, "y": 40}, widgets={}),
                ],
                [
                    Link(id="l1", **{"from": ["n1", 0], "to": ["n3", 0], "type": "AUDIO"}),
                    Link(id="l2", **{"from": ["n2", 0], "to": ["n3", 1], "type": "AUDIO"}),
                    Link(id="l3", **{"from": ["n3", 0], "to": ["n4", 0], "type": "AUDIO"}),
                ],
            ),
            ["n4"],
        ),
        (
            "sample-and-hold",
            _workflow(
                "sample-and-hold",
                [
                    NodeInstance(
                        id="n1",
                        type="Clock",
                        pos={"x": 0, "y": 0},
                        widgets={"bpm": 200, "pulse_ms": 8, "duration_sec": 0.3, "sample_rate": 48000},
                    ),
                    NodeInstance(
                        id="n2",
                        type="NoiseGenerator",
                        pos={"x": 0, "y": 120},
                        widgets={
                            "color": "white",
                            "amplitude": 1,
                            "duration_sec": 0.3,
                            "sample_rate": 48000,
                            "seed": 9,
                        },
                    ),
                    NodeInstance(id="n3", type="SampleAndHold", pos={"x": 280, "y": 0}, widgets={"threshold": 0.5}),
                    NodeInstance(
                        id="n4",
                        type="Quantizer",
                        pos={"x": 540, "y": 0},
                        widgets={"scale": "minor", "root_hz": 220},
                    ),
                ],
                [
                    Link(id="l1", **{"from": ["n1", 0], "to": ["n3", 0], "type": "AUTOMATION"}),
                    Link(id="l2", **{"from": ["n2", 0], "to": ["n3", 2], "type": "AUDIO"}),
                    Link(id="l3", **{"from": ["n3", 0], "to": ["n4", 0], "type": "AUTOMATION"}),
                ],
            ),
            ["n4"],
        ),
        (
            "comparator-logic",
            _workflow(
                "comparator-logic",
                [
                    NodeInstance(
                        id="n1",
                        type="LFO",
                        pos={"x": 0, "y": 0},
                        widgets={"rate_hz": 4, "amplitude": 1, "duration_sec": 0.35, "sample_rate": 48000},
                    ),
                    NodeInstance(id="n2", type="Comparator", pos={"x": 260, "y": 0}, widgets={"threshold": 0}),
                    NodeInstance(
                        id="n3",
                        type="Clock",
                        pos={"x": 0, "y": 140},
                        widgets={"bpm": 240, "pulse_ms": 5, "duration_sec": 0.35, "sample_rate": 48000},
                    ),
                    NodeInstance(id="n4", type="Logic", pos={"x": 520, "y": 40}, widgets={"operation": "and"}),
                ],
                [
                    Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "AUTOMATION"}),
                    Link(id="l2", **{"from": ["n2", 0], "to": ["n4", 0], "type": "AUTOMATION"}),
                    Link(id="l3", **{"from": ["n3", 0], "to": ["n4", 1], "type": "AUTOMATION"}),
                ],
            ),
            ["n4"],
        ),
    ],
)
def test_help_example_offline_render(tmp_path: Path, name: str, workflow: Workflow, targets: list[str]) -> None:
    validation = validate_workflow(workflow, known_node_types=known_node_types())
    assert validation.valid, [e.message for e in validation.errors]
    result = Executor(tmp_path / name).execute(workflow, target_nodes=targets)
    assert result.status == "completed", f"{name}: {result.error}"


@pytest.mark.parametrize(
    "name,workflow,targets,samples",
    [
        (
            "midi-automation-apply",
            _workflow(
                "midi-automation-apply",
                [
                    NodeInstance(
                        id="n1",
                        type="LoadAudio",
                        pos={"x": 0, "y": 0},
                        widgets={"path": "assets/samples/podcast_denoise_demo.wav"},
                    ),
                    NodeInstance(
                        id="n2",
                        type="LoadMIDI",
                        pos={"x": 0, "y": 140},
                        widgets={"path": "assets/samples/automation_cc7.mid", "midi_kind": "control"},
                    ),
                    NodeInstance(
                        id="n3",
                        type="MIDIToFloat",
                        pos={"x": 260, "y": 140},
                        widgets={"cc": 7, "default_value": 0.5},
                    ),
                    NodeInstance(id="n4", type="AutomationApply", pos={"x": 520, "y": 0}, widgets={}),
                    NodeInstance(id="n5", type="PreviewAudio", pos={"x": 780, "y": 0}, widgets={}),
                ],
                [
                    Link(id="l1", **{"from": ["n1", 0], "to": ["n4", 0], "type": "AUDIO"}),
                    Link(id="l2", **{"from": ["n2", 0], "to": ["n3", 0], "type": "MIDI"}),
                    Link(id="l3", **{"from": ["n3", 0], "to": ["n4", 1], "type": "AUTOMATION"}),
                    Link(id="l4", **{"from": ["n4", 0], "to": ["n5", 0], "type": "AUDIO"}),
                ],
            ),
            ["n5"],
            ["podcast_denoise_demo.wav", "automation_cc7.mid"],
        ),
        (
            "midi-note-gate",
            _workflow(
                "midi-note-gate",
                [
                    NodeInstance(
                        id="n1",
                        type="LoadMIDI",
                        pos={"x": 0, "y": 0},
                        widgets={"path": "assets/samples/automation_cc7.mid", "midi_kind": "performance"},
                    ),
                    NodeInstance(
                        id="n2",
                        type="MIDINoteGate",
                        pos={"x": 260, "y": 0},
                        widgets={"note": 60, "channel": 1},
                    ),
                    NodeInstance(
                        id="n3",
                        type="Oscillator",
                        pos={"x": 0, "y": 140},
                        widgets={
                            "waveform": "saw",
                            "frequency_hz": 110.0,
                            "amplitude_default": 0.35,
                            "duration_sec": 0.5,
                            "sample_rate": 48000,
                        },
                    ),
                    NodeInstance(id="n4", type="Amplifier", pos={"x": 520, "y": 0}, widgets={"gain": 1}),
                    NodeInstance(id="n5", type="PreviewAudio", pos={"x": 780, "y": 0}, widgets={}),
                ],
                [
                    Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "MIDI"}),
                    Link(id="l2", **{"from": ["n3", 0], "to": ["n4", 0], "type": "AUDIO"}),
                    Link(id="l3", **{"from": ["n2", 0], "to": ["n4", 1], "type": "AUTOMATION"}),
                    Link(id="l4", **{"from": ["n4", 0], "to": ["n5", 0], "type": "AUDIO"}),
                ],
            ),
            ["n5"],
            ["automation_cc7.mid"],
        ),
        (
            "load-video-preview",
            _workflow(
                "load-video-preview",
                [
                    NodeInstance(
                        id="n1",
                        type="LoadVideo",
                        pos={"x": 0, "y": 0},
                        widgets={"path": "assets/samples/video480p.mov"},
                    ),
                    NodeInstance(id="n2", type="PreviewVideo", pos={"x": 280, "y": 0}, widgets={}),
                ],
                [Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "VIDEO"})],
            ),
            ["n2"],
            ["video480p.mov"],
        ),
        (
            "load-image",
            _workflow(
                "load-image",
                [
                    NodeInstance(
                        id="n1",
                        type="LoadImage",
                        pos={"x": 0, "y": 0},
                        widgets={"path": "assets/samples/Fort-Zeelandia.png"},
                    ),
                ],
                [],
            ),
            ["n1"],
            ["Fort-Zeelandia.png"],
        ),
    ],
)
def test_help_example_asset_backed_render(
    tmp_path: Path,
    name: str,
    workflow: Workflow,
    targets: list[str],
    samples: list[str],
) -> None:
    validation = validate_workflow(workflow, known_node_types=known_node_types())
    assert validation.valid, [e.message for e in validation.errors]
    project = _project_with_samples(tmp_path, name, samples)
    result = Executor(project).execute(workflow, target_nodes=targets)
    assert result.status == "completed", f"{name}: {result.error}"


def test_bundled_help_samples_exist() -> None:
    for name in (
        "podcast_denoise_demo.wav",
        "automation_cc7.mid",
        "video480p.mov",
        "Fort-Zeelandia.png",
    ):
        assert (SAMPLES / name).is_file(), name


def test_registry_covers_help_focus_types() -> None:
    # Every registered node should be selectable in Inspector Help (curated recipes cover all).
    assert len(NODE_REGISTRY) >= 90
    # TTS ↔ GenerateSpeech rename may be mid-flight across branches; either canonical name is fine.
    assert "TTS" in NODE_REGISTRY or "GenerateSpeech" in NODE_REGISTRY
    for node_type in (
        "Amplifier",
        "AutomationApply",
        "Benchmark",
        "ChannelMerge",
        "GenerateVideo",
        "GenerateImage",
        "GenerateMidi",
        "SwitchImage",
        "LoadImage",
        "PreviewImage",
        "PreviewMidi",
        "SynthMidi",
        "SaveMidi",
        "LoadMIDI",
        "MIDINoteGate",
        "MatrixMixer",
        "MuxVideo",
        "Oscillator",
        "Prompt",
        "SampleAndHold",
        "TranslateText",
    ):
        assert node_type in NODE_REGISTRY
