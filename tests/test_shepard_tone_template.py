"""Shepard Tone modular template — seamless Shepard–Risset (DSP only)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from groovy.executor import Executor
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow

register_core()

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "shepard-tone.groovy.json"


def _audio_id(output: dict) -> str:
    return str(output.get("audio_id") or output.get("cache_id"))


@pytest.fixture(scope="module")
def workflow() -> Workflow:
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    return Workflow.model_validate(data)


def test_shepard_tone_file_and_tags(workflow: Workflow) -> None:
    assert TEMPLATE.is_file()
    assert workflow.metadata.title == "Shepard Tone"
    tags = set(workflow.metadata.tags)
    assert "modular" in tags
    assert "shepard" in tags
    assert sum(1 for n in workflow.nodes if n.type == "Oscillator") >= 6


def test_shepard_tone_validates(workflow: Workflow) -> None:
    result = validate_workflow(workflow)
    assert result.valid, result.errors


def test_shepard_tone_freq_curves_never_drop(workflow: Workflow) -> None:
    """Continuous rise — no octave wrap jumps on frequency ControlCurves."""
    for node in workflow.nodes:
        if not str(node.id).startswith("freq-"):
            continue
        points = json.loads(str(node.widgets.get("points") or "[]"))
        assert len(points) >= 8
        vals = [float(p["v"]) for p in points]
        for a, b in zip(vals, vals[1:]):
            assert b >= a * 0.999, f"{node.id} frequency wrap/drop {a} → {b}"


def test_shepard_tone_execute_rising_seamless(workflow: Workflow, tmp_path: Path) -> None:
    ex = Executor(tmp_path)
    result = ex.execute(workflow, target_nodes=["preview"])
    assert result.status == "completed", result.error
    _, pcm = ex.cache.load_audio(_audio_id(result.outputs["preview"]))
    pcm = np.asarray(pcm, dtype=np.float64)
    mono = pcm[0] if pcm.ndim > 1 else pcm.reshape(-1)
    assert mono.shape[0] > 1000
    assert float(np.max(np.abs(mono))) > 1e-3
    sr = 48000

    def centroid(seg: np.ndarray) -> float:
        win = seg * np.hanning(len(seg))
        spec = np.abs(np.fft.rfft(win)) + 1e-12
        freqs = np.fft.rfftfreq(len(win), 1.0 / sr)
        return float(np.sum(freqs * spec) / np.sum(spec))

    # Within the first half-octave (~2.5s at 5s/oct), centroid should climb.
    early = centroid(mono[0 : sr])
    later = centroid(mono[sr * 2 : sr * 3])
    assert later > early

    # No impulsive artifacts at octave-cycle marks (5s with current template).
    cycle = 5 * sr
    for boundary in (cycle, 2 * cycle, 3 * cycle):
        if boundary + sr // 10 >= mono.size or boundary < sr // 10:
            continue
        window = mono[boundary - sr // 20 : boundary + sr // 20]
        neigh = mono[boundary - sr // 2 : boundary - sr // 4]
        peak = float(np.max(np.abs(window)))
        rms = float(np.sqrt(np.mean(np.square(neigh)))) + 1e-12
        assert peak / rms < 12.0, f"cycle artifact at sample {boundary}: peak/rms={peak / rms:.1f}"
