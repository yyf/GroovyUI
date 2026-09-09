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
TEMPLATE = ROOT / "templates" / "podcast-denoise.groovy.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "podcast_denoise_demo.wav", tone, sr)
    registry = ModelRegistry(tmp_path)
    registry.installer.install("deepfilternet-v3")
    return tmp_path


def test_podcast_denoise_with_ai_node(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/podcast_denoise_demo.wav"

    registry = ModelRegistry(project_dir)
    install = registry.store.get("deepfilternet-v3")
    assert install.status == "ready", install.error

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4", "n5"])
    assert result.status == "completed", result.error
    assert "n4" in result.outputs
    assert "n2" in result.outputs
    assert "n5" in result.outputs
