"""Hero cold-machine gate — real Model Browser install + hero template renders (no inference stub)."""

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
from groovy.nodes.ai.inference_env import whisper_available
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.registry.catalog import ModelCatalog
from groovy.registry.installer import model_install_complete
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
PODCAST = ROOT / "templates" / "podcast-denoise.groovy.json"
DIALOGUE = ROOT / "templates" / "transcribe-dialogue.groovy.json"
DIALOGUE_FIXTURE = ROOT / "assets" / "samples" / "dialogue_48k.wav"


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
    sf.write(assets / "podcast_denoise_demo.wav", 0.25 * np.sin(2 * np.pi * 440 * t), sr)
    if DIALOGUE_FIXTURE.is_file():
        shutil.copy(DIALOGUE_FIXTURE, assets / "dialogue_48k.wav")
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

    workflow = Workflow.model_validate(json.loads(PODCAST.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/podcast_denoise_demo.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4", "n5"])
    assert result.status == "completed", result.error
    assert "n2" in result.outputs
    assert "n5" in result.outputs

    saved = Path(result.outputs["n5"]["path"])
    assert saved.name.startswith("podcast-denoised-")
    assert saved.exists()
    assert saved.stat().st_size > 1_000


def test_whisper_install_from_model_browser(project_dir: Path) -> None:
    registry = ModelRegistry(project_dir)
    state = registry.installer.install("whisper-large-v3-turbo")
    assert state.status == "ready", state.error

    manifest = ModelCatalog().get("whisper-large-v3-turbo")
    assert manifest is not None
    assert model_install_complete(manifest, state)

    marker = project_dir / ".groovy" / "models" / "whisper-large-v3-turbo" / "installed.json"
    assert marker.exists()
    assert whisper_available(), "faster_whisper import failed after Model Browser install"


def test_transcribe_dialogue_cold_machine_gate(project_dir: Path) -> None:
    if not (project_dir / "assets" / "samples" / "dialogue_48k.wav").is_file():
        pytest.skip("dialogue_48k.wav fixture missing from assets/samples")

    registry = ModelRegistry(project_dir)
    install = registry.installer.install("whisper-large-v3-turbo")
    assert install.status == "ready", install.error
    if not whisper_available():
        pytest.skip("faster_whisper unavailable after install")

    workflow = Workflow.model_validate(json.loads(DIALOGUE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n2", "n3", "n4", "n5"], force_rebuild=True)
    assert result.status == "completed", result.error

    text_out = result.outputs["n2"]
    assert text_out["type"] == "TEXT"
    text = text_out.get("text") or ""
    assert isinstance(text, str) and text.strip(), "Whisper returned empty transcript on dialogue fixture"

    text_preview = result.outputs["n3"]
    assert text_preview["type"] == "TEXT"
    assert (text_preview.get("text") or "").strip() == text.strip()

    audio_preview = result.outputs["n4"]
    assert audio_preview["type"] == "AUDIO"
    assert audio_preview["cache_id"] == result.outputs["n1"]["cache_id"]

    saved = Path(result.outputs["n5"]["path"])
    assert saved.name.startswith("dialogue-source-")
    assert saved.exists()
    assert saved.stat().st_size > 1_000
