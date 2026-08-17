from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.audio import AudioBuffer
from groovy.executor.authenticity import AuthenticityReport
from groovy.executor.engine import JobContext
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.ai.nodes import DeepfakeDetect
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import NodeInstance, Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "authenticity-check.groovy.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "dialogue_48k.wav", tone, sr)
    registry = ModelRegistry(tmp_path)
    registry.installer.install("rawnet2-asvspoof")
    return tmp_path


def test_authenticity_check_workflow(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4", "n5", "n6"])
    assert result.status == "completed", result.error
    assert result.outputs["n2"]["type"] == "AUTHENTICITY"
    assert result.outputs["n2"].get("authenticity_id")
    assert result.outputs["n4"]["type"] == "AUTHENTICITY"
    deepfake = result.outputs["n3"]
    assert deepfake["type"] == "MULTI"
    slot_types = [slot.get("type") for slot in deepfake.get("outputs") or []]
    assert slot_types[:2] == ["AUTHENTICITY", "AUDIO"]
    report_id = result.outputs["n4"]["authenticity_id"]
    report = executor.cache.load_authenticity(report_id)
    assert report.record["overall"]["label"]
    assert "ml_detection" in report.record or "provenance_check" in report.record
    assert result.outputs["n5"]["type"] == "AUDIO"
    assert result.outputs["n6"]["type"] == "AUDIO"


def test_deepfake_mixed_outputs_cached_as_multi(tmp_path: Path) -> None:
    executor = Executor(tmp_path)
    pcm = np.zeros((1, 16), dtype=np.float64)
    audio = AudioBuffer.from_planar(pcm, 48000, source_node_type="Test", channel_layout="mono")
    executor.cache.write_audio(audio, pcm)
    report = AuthenticityReport.create({"overall": {"label": "unknown"}})
    executor.cache.write_authenticity(report)

    node = NodeInstance(id="n3", type="DeepfakeDetect", widgets={"model": "rawnet2-asvspoof"})
    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "test-deepfake-multi",
            "metadata": {"title": "test"},
            "nodes": [node.model_dump(mode="json")],
            "links": [],
            "groups": [],
            "view": {"zoom": 1.0, "pan": {"x": 0.0, "y": 0.0}},
        }
    )
    ctx = JobContext(project_dir=tmp_path, cache=executor.cache, job_id="job")
    meta = executor._output_meta_from_result(
        (report, audio),
        node=node,
        node_cls=DeepfakeDetect,
        ctx=ctx,
        workflow=workflow,
        kwargs={"audio": audio},
    )
    assert meta is not None
    assert meta["type"] == "MULTI"
    assert [slot["type"] for slot in meta["outputs"]] == ["AUTHENTICITY", "AUDIO"]
    assert meta["outputs"][0]["authenticity_id"] == report.id
    assert meta["outputs"][1]["cache_id"] == audio.id

    assert executor._normalize_output_meta(DeepfakeDetect, meta) == meta
    stale = {"type": "AUTHENTICITY", "authenticity_id": report.id}
    assert executor._normalize_output_meta(DeepfakeDetect, stale) is None
