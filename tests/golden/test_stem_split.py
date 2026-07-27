from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "stem-separation.groovy.json"


@pytest.fixture(autouse=True)
def _force_stub_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 1.0, int(sr), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "Knockout_41k_mono.wav", tone, sr)
    registry = ModelRegistry(tmp_path)
    registry.installer.install("demucs-v4")
    return tmp_path


def _load_workflow() -> Workflow:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/Knockout_41k_mono.wav"
    return workflow


def _find_stems_id(executor: Executor) -> str:
    for path in executor.cache.cache_dir.glob("*.stems.meta.json"):
        meta = json.loads(path.read_text())
        return str(meta["id"])
    raise AssertionError("expected stems bundle in cache")


def test_stem_split_vocals(project_dir: Path) -> None:
    workflow = _load_workflow()
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n3"])
    assert result.status == "completed", result.error
    assert result.outputs["n2"]["type"] == "MULTI"
    assert len(result.outputs["n2"]["outputs"]) == 4
    assert result.outputs["n3"]["type"] == "AUDIO"
    assert result.outputs["n3"]["cache_id"] == result.outputs["n2"]["outputs"][0]["cache_id"]


def test_legacy_stems_node_cache_feeds_four_preview_slots(project_dir: Path) -> None:
    workflow = _load_workflow()
    executor = Executor(project_dir)
    fresh = executor.execute(workflow, target_nodes=["n2"])
    assert fresh.status == "completed", fresh.error

    cached = executor.cache.read_node_cache(workflow.id, "n2")
    assert cached is not None
    stems_id = _find_stems_id(executor)

    executor.cache.write_node_cache(
        workflow.id,
        "n2",
        signature=cached["signature"],
        output_meta={"type": "STEMS", "stems_id": stems_id},
    )

    four_previews = Workflow.model_validate(
        {
            **workflow.model_dump(),
            "nodes": [
                *workflow.nodes,
                {"id": "p1", "type": "Preview", "pos": {"x": 520, "y": -60}, "widgets": {}},
                {"id": "p2", "type": "Preview", "pos": {"x": 520, "y": 0}, "widgets": {}},
                {"id": "p3", "type": "Preview", "pos": {"x": 520, "y": 60}, "widgets": {}},
                {"id": "p4", "type": "Preview", "pos": {"x": 520, "y": 120}, "widgets": {}},
            ],
            "links": [
                {"id": "l1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"},
                {"id": "l10", "from": ["n2", 0], "to": ["p1", 0], "type": "AUDIO"},
                {"id": "l11", "from": ["n2", 1], "to": ["p2", 0], "type": "AUDIO"},
                {"id": "l12", "from": ["n2", 2], "to": ["p3", 0], "type": "AUDIO"},
                {"id": "l13", "from": ["n2", 3], "to": ["p4", 0], "type": "AUDIO"},
            ],
        }
    )

    result = executor.execute(four_previews, target_nodes=["p1", "p2", "p3", "p4"])
    assert result.status == "completed", result.error
    assert result.outputs["n2"]["type"] == "MULTI"
    assert len(result.outputs["n2"]["outputs"]) == 4
    vocals_id = result.outputs["n2"]["outputs"][0]["cache_id"]
    for index, preview_id in enumerate(("p1", "p2", "p3", "p4")):
        assert result.outputs[preview_id]["type"] == "AUDIO"
        assert result.outputs[preview_id]["cache_id"] == result.outputs["n2"]["outputs"][index]["cache_id"]
    assert result.outputs["p1"]["cache_id"] == vocals_id
