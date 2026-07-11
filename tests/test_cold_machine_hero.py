"""Hero cold-machine gate — real Model Browser install + podcast-denoise render (no inference stub)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.registry.catalog import ModelCatalog
from groovy.registry.installer import model_install_complete
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "podcast-denoise.groovy.json"


pytestmark = pytest.mark.integration


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    if os.environ.get("GROOVY_INFERENCE_STUB", "").lower() in ("1", "true", "yes"):
        pytest.skip("Set GROOVY_INFERENCE_STUB=0 to run cold-machine hero tests")
    if not shutil.which("uv"):
        pytest.skip("uv is required for Model Browser python_deps install")

    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48_000
    t = np.linspace(0, 1.0, int(sr), endpoint=False)
    sf.write(assets / "male-1.wav", 0.25 * np.sin(2 * np.pi * 440 * t), sr)
    return tmp_path


def test_deepfilternet_install_from_model_browser(project_dir: Path) -> None:
    registry = ModelRegistry(project_dir)
    state = registry.installer.install("deepfilternet-v3")
    assert state.status == "ready", state.error

    manifest = ModelCatalog().get("deepfilternet-v3")
    assert manifest is not None
    assert model_install_complete(manifest, state)

    marker = project_dir / ".groovy" / "models" / "deepfilternet-v3" / "installed.json"
    assert marker.exists()


def test_podcast_denoise_cold_machine_gate(project_dir: Path) -> None:
    registry = ModelRegistry(project_dir)
    install = registry.installer.install("deepfilternet-v3")
    assert install.status == "ready", install.error

    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/male-1.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4", "n5"])
    assert result.status == "completed", result.error
    assert "n2" in result.outputs
    assert "n5" in result.outputs

    saved = project_dir / "exports" / "podcast-denoised.wav"
    assert saved.exists()
    assert saved.stat().st_size > 1_000
