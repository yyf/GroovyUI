"""Cross-machine golden for core Load → Normalize(peak) → Granulate chain.

Hello Groovy itself is now TTS + Granulate (AI stub/real); bit-identical golden stays on this
deterministic core micrograph.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.nodes.core import register_all
from groovy.schema.models import Workflow

register_all()

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN_WAV = FIXTURES / "dialogue_48k.wav"
GOLDEN_HASH_PATH = FIXTURES / "hello_groovy_pcm.sha256"

# Deterministic micrograph (replaces old Load→Normalize Hello Groovy golden).
CORE_GOLDEN_WORKFLOW = {
    "schema_version": "1.0.0",
    "groovy_version": "0.1.0",
    "id": "golden-core-granulate-0001",
    "metadata": {
        "title": "Core Granulate Golden",
        "author": "groovy",
        "description": "Load → peak normalize → granulate (fixed seed) for SHA256 golden.",
        "tags": ["golden"],
        "created_at": "2026-07-26T00:00:00Z",
        "modified_at": "2026-07-26T00:00:00Z",
    },
    "nodes": [
        {
            "id": "n1",
            "type": "LoadAudio",
            "pos": {"x": 0, "y": 0},
            "widgets": {"path": "assets/samples/dialogue_48k.wav"},
        },
        {
            "id": "n2",
            "type": "Normalize",
            "pos": {"x": 240, "y": 0},
            "widgets": {"mode": "peak", "target_peak_db": -1.0},
        },
        {
            "id": "n3",
            "type": "Granulate",
            "pos": {"x": 480, "y": 0},
            "widgets": {
                "grain_ms": 45.0,
                "hop_ms": 18.0,
                "scatter_ms": 140.0,
                "wet_start": 0.0,
                "wet_end": 1.0,
                "seed": 7,
            },
        },
        {"id": "n4", "type": "Preview", "pos": {"x": 720, "y": 0}, "widgets": {}},
    ],
    "links": [
        {"id": "l1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"},
        {"id": "l2", "from": ["n2", 0], "to": ["n3", 0], "type": "AUDIO"},
        {"id": "l3", "from": ["n3", 0], "to": ["n4", 0], "type": "AUDIO"},
    ],
    "groups": [],
    "view": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
}


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    shutil.copy(GOLDEN_WAV, assets / "dialogue_48k.wav")
    return tmp_path


def _render_pcm_hash(project_dir: Path) -> str:
    workflow = Workflow.model_validate(CORE_GOLDEN_WORKFLOW)
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4"])
    assert result.status == "completed", result.error
    cache_id = result.outputs["n4"]["cache_id"]
    _, pcm = executor.cache.load_audio(cache_id)
    return hashlib.sha256(pcm.tobytes()).hexdigest()


def test_core_granulate_reproducible(project_dir: Path) -> None:
    first = _render_pcm_hash(project_dir)
    second = _render_pcm_hash(project_dir)
    assert first == second


def test_core_granulate_matches_golden_hash(project_dir: Path) -> None:
    digest = _render_pcm_hash(project_dir)
    expected = GOLDEN_HASH_PATH.read_text().strip()
    assert digest == expected
