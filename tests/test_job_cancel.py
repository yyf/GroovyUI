from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.cancel import JobCancelled
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
from template_fixtures import require_template
TEMPLATE = require_template("transcribe-and-regenerate")


@pytest.fixture(autouse=True)
def _force_stub_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "podcast_denoise_demo.wav", tone, sr)
    registry = ModelRegistry(tmp_path)
    registry.installer.install("basic-pitch")
    registry.installer.install("musicgen-melody-small")
    return tmp_path


def test_executor_cancel_at_start(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/podcast_denoise_demo.wav"

    executor = Executor(project_dir)
    cancelled = executor.execute(workflow, target_nodes=["n5"], cancel_check=lambda: True)
    assert cancelled.status == "cancelled"


def test_worker_cancel_raises() -> None:
    from groovy.executor.worker import run_ai_worker

    with patch("groovy.executor.worker.subprocess.Popen") as popen:
        proc = popen.return_value
        proc.poll.side_effect = [None, None, 0]
        proc.stdout.read.return_value = '{"outputs": []}'
        proc.stderr.read.return_value = ""
        proc.returncode = 0

        with pytest.raises(JobCancelled):
            run_ai_worker("AudioToMIDI", {"audio_id": "x"}, Path("."), cancel_check=lambda: True)

        proc.terminate.assert_called_once()
