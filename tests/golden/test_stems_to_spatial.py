from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.engine import JobContext
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import NODE_REGISTRY
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow

register_core()
register_ai()

STEMS_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "stems-to-spatial.groovy.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "noisy_speech_1214.wav", tone, sr)
    registry = ModelRegistry(tmp_path)
    registry.installer.install("demucs-v4")
    return tmp_path


def test_stems_to_spatial_template(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(STEMS_TEMPLATE.read_text()))
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n5"])
    assert result.status == "completed", result.error
    assert result.outputs["n2"]["type"] == "OBA"
    assert result.outputs["n5"]["type"] == "AUDIO"
    scene = executor.cache.load_object_scene(result.outputs["n2"]["oba_id"])
    assert len(scene.objects) == 4
