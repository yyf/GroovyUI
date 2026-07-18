from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.provenance import build_lineage_chain, disclosure_summary, summarize_workflow_outputs
from groovy.nodes.core import register_all
from groovy.nodes.ai import register_all as register_ai
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow

register_all()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "podcast-denoise.groovy.json"


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
    registry.installer.install("deepfilternet-v3")
    return tmp_path


def test_provenance_chain_has_parents(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4"])
    assert result.status == "completed", result.error

    preview_id = result.outputs["n4"]["cache_id"]
    chain = build_lineage_chain(executor.cache, preview_id)
    assert len(chain) >= 2
    assert chain[0]["node"]["node_type"] in {"Normalize", "Preview"}
    disclosure = disclosure_summary(chain)
    assert "AI" in disclosure or "ai" in disclosure.lower()

    summary = summarize_workflow_outputs(executor.cache, result.outputs, target_node_id="n4")
    assert summary["contains_ai"] is True
    assert summary["focus_disclosure"]


def test_save_audio_writes_provenance_sidecar(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n2"])
    assert result.status == "completed"

    cache_id = result.outputs["n2"]["cache_id"]
    from groovy.nodes.core.nodes import SaveAudio

    node = SaveAudio()
    from groovy.executor.engine import JobContext

    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="test")
    node.bind_context(ctx)
    buffer, _ = executor.cache.load_audio(cache_id)
    written, = node.run(audio=buffer, filename="exports/test-out.wav")
    out = Path(written)
    sidecar = out.with_name(f"{out.stem}.provenance.json")
    assert out.name.startswith("test-out-")
    assert sidecar.exists()
