from __future__ import annotations

import hashlib
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
GOLDEN_HASH_PATH = Path(__file__).resolve().parent / "fixtures" / "hello_groovy_pcm.sha256"


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


def _render_pcm_hash(project_dir: Path) -> str:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n3"])
    assert result.status == "completed", result.error
    cache_id = result.outputs["n3"]["cache_id"]
    _, pcm = executor.cache.load_audio(cache_id)
    return hashlib.sha256(pcm.tobytes()).hexdigest()


def test_hello_groovy_reproducible(project_dir: Path) -> None:
    first = _render_pcm_hash(project_dir)
    second = _render_pcm_hash(project_dir)
    assert first == second


def test_hello_groovy_matches_golden_hash(project_dir: Path) -> None:
    digest = _render_pcm_hash(project_dir)
    expected = GOLDEN_HASH_PATH.read_text().strip()
    assert digest == expected
