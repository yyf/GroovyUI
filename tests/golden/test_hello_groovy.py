from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.core import register_all
from groovy.schema.models import Workflow

register_all()

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "hello-groovy.groovy.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "dialogue_48k.wav", tone, sr)
    return tmp_path


def test_hello_groovy_golden(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    # Point LoadAudio at fixture path relative to project
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n3"])
    assert result.status == "completed", result.error
    assert "n3" in result.outputs
    cache_id = result.outputs["n3"]["cache_id"]
    meta = executor.cache.read_meta(cache_id)
    assert meta["sample_rate"] == 48000
    assert meta["frame_count"] == 48000
    prov_path = project_dir / ".groovy" / "cache" / f"{cache_id}.provenance.json"
    assert prov_path.exists()


def test_workflow_template_validates() -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    assert workflow.metadata.title == "Hello Groovy"
    assert len(workflow.nodes) == 3
