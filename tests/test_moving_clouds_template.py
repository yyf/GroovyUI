"""Moving Clouds — standard Modular Synth template (Spiegel-inspired grain stereo)."""

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
TEMPLATE = ROOT / "templates" / "moving-clouds.groovy.json"


def _audio_id(output: dict) -> str:
    return str(output.get("audio_id") or output.get("cache_id"))


@pytest.fixture(scope="module")
def workflow() -> Workflow:
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    return Workflow.model_validate(data)


def test_moving_clouds_file_and_tags(workflow: Workflow) -> None:
    assert TEMPLATE.is_file()
    assert workflow.metadata.title == "Moving Clouds"
    tags = set(workflow.metadata.tags)
    assert "modular" in tags
    assert "granular" in tags
    assert "experimental" not in tags
    assert not any(n.type == "Note" for n in workflow.nodes)


def test_moving_clouds_validates(workflow: Workflow) -> None:
    result = validate_workflow(workflow)
    assert result.valid, result.errors


def test_moving_clouds_granulates_high_resonators(workflow: Workflow) -> None:
    by_id = {n.id: n for n in workflow.nodes}
    assert by_id["grain-c"].type == "Granulate"
    assert by_id["grain-d"].type == "Granulate"
    assert by_id["pan-c"].type == "Pan"
    assert by_id["pan-d"].type == "Pan"
    assert by_id["pan-lfo-c"].type == "LFO"
    assert by_id["pan-lfo-d"].type == "FloatMath"


def test_moving_clouds_stereo_imaging(workflow: Workflow, tmp_path: Path) -> None:
    ex = Executor(tmp_path)
    result = ex.execute(workflow, target_nodes=["preview"])
    assert result.status == "completed", result.error
    _, pcm = ex.cache.load_audio(_audio_id(result.outputs["preview"]))
    pcm = np.asarray(pcm, dtype=np.float64)
    assert pcm.shape[0] == 2
    assert pcm.shape[1] > 1000
    assert float(np.max(np.abs(pcm))) > 1e-4
    left, right = pcm[0], pcm[1]
    sr = 48000
    win = sr * 2
    balances: list[float] = []
    for start in range(0, left.shape[0] - win, win):
        a = left[start : start + win]
        b = right[start : start + win]
        balances.append(float(np.sqrt(np.mean(a**2)) - np.sqrt(np.mean(b**2))))
    assert float(np.std(balances)) > 1e-4
