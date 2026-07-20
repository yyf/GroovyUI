from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from groovy.executor import Executor
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata

register_core()


def _audio_id(output: dict) -> str:
    return str(output.get("audio_id") or output.get("cache_id"))


def test_signal_generator_sine_tone(tmp_path: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="sig-gen-test",
        metadata=WorkflowMetadata(title="SignalGenerator"),
        nodes=[
            NodeInstance(
                id="n1",
                type="SignalGenerator",
                pos={"x": 0, "y": 0},
                widgets={
                    "waveform": "sine",
                    "frequency_hz": 440.0,
                    "amplitude_default": 0.5,
                    "duration_sec": 0.25,
                    "sample_rate": 48000,
                },
            ),
            NodeInstance(id="n2", type="Preview", pos={"x": 200, "y": 0}, widgets={}),
        ],
        links=[Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"})],
    )
    executor = Executor(tmp_path)
    result = executor.execute(workflow, target_nodes=["n2"])
    assert result.status == "completed", result.error
    buffer, pcm = executor.cache.load_audio(_audio_id(result.outputs["n1"]))
    assert buffer.sample_rate == 48000
    assert buffer.frame_count == 12000
    assert float(np.max(np.abs(pcm))) == pytest.approx(0.5, abs=0.05)


def test_fm_from_oscillator_blocks(tmp_path: Path) -> None:
    """y = A_c sin(2π f_c t + I sin(2π f_m t)) patched from two SignalGenerators."""
    a_c, f_c, f_m, index = 0.5, 440.0, 220.0, 2.5
    sr, dur = 48000, 0.2
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="fm-blocks",
        metadata=WorkflowMetadata(title="FM blocks"),
        nodes=[
            NodeInstance(
                id="mod",
                type="SignalGenerator",
                pos={"x": 0, "y": 0},
                widgets={
                    "waveform": "sine",
                    "frequency_hz": f_m,
                    "amplitude_default": index,
                    "duration_sec": dur,
                    "sample_rate": sr,
                },
            ),
            NodeInstance(
                id="car",
                type="SignalGenerator",
                pos={"x": 200, "y": 0},
                widgets={
                    "waveform": "sine",
                    "frequency_hz": f_c,
                    "amplitude_default": a_c,
                    "duration_sec": dur,
                    "sample_rate": sr,
                },
            ),
            NodeInstance(id="out", type="Preview", pos={"x": 400, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["mod", 0], "to": ["car", 2], "type": "AUDIO"}),
            Link(id="l2", **{"from": ["car", 0], "to": ["out", 0], "type": "AUDIO"}),
        ],
    )
    executor = Executor(tmp_path)
    result = executor.execute(workflow, target_nodes=["out"])
    assert result.status == "completed", result.error
    _, pcm = executor.cache.load_audio(_audio_id(result.outputs["car"]))
    n = pcm.shape[1]
    t = np.arange(n, dtype=np.float64) / sr
    expected = a_c * np.sin(2 * np.pi * f_c * t + index * np.sin(2 * np.pi * f_m * t))
    assert np.allclose(pcm[0], expected, atol=1e-9)


def test_fm_index_via_floatmath_divide(tmp_path: Path) -> None:
    """I = Δf / f_m patched with FloatMath(divide) into modulator amplitude."""
    f_m, delta_f = 220.0, 660.0
    expected_i = delta_f / f_m
    sr, dur = 48000, 0.15
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="fm-div",
        metadata=WorkflowMetadata(title="FM divide"),
        nodes=[
            NodeInstance(
                id="delta",
                type="ControlCurve",
                pos={"x": 0, "y": 0},
                widgets={
                    "frame_count": int(sr * dur),
                    "sample_rate": sr,
                    "points": f'[{{"t":0,"v":{delta_f}}},{{"t":1,"v":{delta_f}}}]',
                },
            ),
            NodeInstance(
                id="fm",
                type="ControlCurve",
                pos={"x": 0, "y": 80},
                widgets={
                    "frame_count": int(sr * dur),
                    "sample_rate": sr,
                    "points": f'[{{"t":0,"v":{f_m}}},{{"t":1,"v":{f_m}}}]',
                },
            ),
            NodeInstance(
                id="div",
                type="FloatMath",
                pos={"x": 200, "y": 40},
                widgets={"operation": "divide"},
            ),
            NodeInstance(
                id="mod",
                type="SignalGenerator",
                pos={"x": 400, "y": 40},
                widgets={
                    "waveform": "sine",
                    "frequency_hz": f_m,
                    "amplitude_default": 1.0,
                    "duration_sec": dur,
                    "sample_rate": sr,
                },
            ),
            NodeInstance(
                id="car",
                type="SignalGenerator",
                pos={"x": 600, "y": 40},
                widgets={
                    "waveform": "sine",
                    "frequency_hz": 440.0,
                    "amplitude_default": 0.4,
                    "duration_sec": dur,
                    "sample_rate": sr,
                },
            ),
            NodeInstance(id="out", type="Preview", pos={"x": 800, "y": 40}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["delta", 0], "to": ["div", 0], "type": "AUTOMATION"}),
            Link(id="l2", **{"from": ["fm", 0], "to": ["div", 1], "type": "AUTOMATION"}),
            Link(id="l3", **{"from": ["fm", 0], "to": ["mod", 0], "type": "AUTOMATION"}),
            Link(id="l4", **{"from": ["div", 0], "to": ["mod", 1], "type": "AUTOMATION"}),
            Link(id="l5", **{"from": ["mod", 0], "to": ["car", 2], "type": "AUDIO"}),
            Link(id="l6", **{"from": ["car", 0], "to": ["out", 0], "type": "AUDIO"}),
        ],
    )
    executor = Executor(tmp_path)
    result = executor.execute(workflow, target_nodes=["out"])
    assert result.status == "completed", result.error
    _, pcm = executor.cache.load_audio(_audio_id(result.outputs["car"]))
    n = pcm.shape[1]
    t = np.arange(n, dtype=np.float64) / sr
    expected = 0.4 * np.sin(2 * np.pi * 440 * t + expected_i * np.sin(2 * np.pi * f_m * t))
    assert np.allclose(pcm[0], expected, atol=1e-6)
