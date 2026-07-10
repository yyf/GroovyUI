from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.nodes.core import register_all
from groovy.schema.models import Workflow

register_all()

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEMPLATE = ROOT / "templates" / "hello-groovy.groovy.json"
GOLDEN_WAV = FIXTURES / "dialogue_48k.wav"
GOLDEN_HASH_PATH = FIXTURES / "hello_groovy_pcm.sha256"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    shutil.copy(GOLDEN_WAV, assets / "dialogue_48k.wav")
    return tmp_path


def _prepare_hello_workflow(workflow: Workflow) -> None:
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"
        if node.type == "Normalize":
            # Peak mode is bit-stable cross-platform; pyloudnorm LUFS varies by OS/BLAS.
            node.widgets["mode"] = "peak"
            node.widgets["target_peak_db"] = -1.0


def _render_pcm_hash(project_dir: Path) -> str:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    _prepare_hello_workflow(workflow)

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
