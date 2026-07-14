"""Preview accepts optional AUDIO and/or TEXT."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Workflow

register_core()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48_000
    t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
    sf.write(assets / "tone.wav", 0.2 * np.sin(2 * np.pi * 440 * t), sr)
    return tmp_path


def test_preview_passthrough_audio(project_dir: Path) -> None:
    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "preview-audio",
            "metadata": {"title": "Preview audio"},
            "nodes": [
                {
                    "id": "n1",
                    "type": "LoadAudio",
                    "pos": {"x": 0, "y": 0},
                    "widgets": {"path": "assets/samples/tone.wav"},
                },
                {"id": "n2", "type": "Preview", "pos": {"x": 260, "y": 0}, "widgets": {}},
            ],
            "links": [{"id": "l1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"}],
            "groups": [],
        }
    )
    result = Executor(project_dir).execute(workflow, target_nodes=["n2"])
    assert result.status == "completed", result.error
    assert result.outputs["n2"]["type"] == "AUDIO"
    assert result.outputs["n2"]["cache_id"] == result.outputs["n1"]["cache_id"]


def test_preview_passthrough_text(project_dir: Path) -> None:
    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "preview-text",
            "metadata": {"title": "Preview text"},
            "nodes": [
                {
                    "id": "n1",
                    "type": "Prompt",
                    "pos": {"x": 0, "y": 0},
                    "widgets": {"text": "hello from prompt"},
                },
                {"id": "n2", "type": "Preview", "pos": {"x": 260, "y": 0}, "widgets": {}},
            ],
            "links": [{"id": "l1", "from": ["n1", 0], "to": ["n2", 1], "type": "TEXT"}],
            "groups": [],
        }
    )
    result = Executor(project_dir).execute(workflow, target_nodes=["n2"])
    assert result.status == "completed", result.error
    assert result.outputs["n2"]["type"] == "TEXT"
    assert result.outputs["n2"]["text"] == "hello from prompt"


def test_preview_audio_and_text_attaches_transcript(project_dir: Path) -> None:
    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "preview-both",
            "metadata": {"title": "Preview both"},
            "nodes": [
                {
                    "id": "n1",
                    "type": "LoadAudio",
                    "pos": {"x": 0, "y": 0},
                    "widgets": {"path": "assets/samples/tone.wav"},
                },
                {
                    "id": "n2",
                    "type": "Prompt",
                    "pos": {"x": 0, "y": 120},
                    "widgets": {"text": "side transcript"},
                },
                {"id": "n3", "type": "Preview", "pos": {"x": 280, "y": 40}, "widgets": {}},
                {
                    "id": "n4",
                    "type": "SaveAudio",
                    "pos": {"x": 520, "y": 40},
                    "widgets": {"path": "exports", "filename": "from-preview.wav", "format": "wav"},
                },
            ],
            "links": [
                {"id": "l1", "from": ["n1", 0], "to": ["n3", 0], "type": "AUDIO"},
                {"id": "l2", "from": ["n2", 0], "to": ["n3", 1], "type": "TEXT"},
                {"id": "l3", "from": ["n3", 0], "to": ["n4", 0], "type": "AUDIO"},
            ],
            "groups": [],
        }
    )
    result = Executor(project_dir).execute(workflow, target_nodes=["n3", "n4"])
    assert result.status == "completed", result.error
    preview = result.outputs["n3"]
    assert preview["type"] == "AUDIO"
    assert preview["cache_id"] == result.outputs["n1"]["cache_id"]
    assert preview.get("text") == "side transcript"
    saved = project_dir / "exports" / "from-preview.wav"
    assert saved.exists() and saved.stat().st_size > 100


def test_save_audio_rejects_text_preview(project_dir: Path) -> None:
    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "save-text",
            "metadata": {"title": "Save text preview"},
            "nodes": [
                {
                    "id": "n1",
                    "type": "Prompt",
                    "pos": {"x": 0, "y": 0},
                    "widgets": {"text": "not audio"},
                },
                {"id": "n2", "type": "Preview", "pos": {"x": 260, "y": 0}, "widgets": {}},
                {
                    "id": "n3",
                    "type": "SaveAudio",
                    "pos": {"x": 520, "y": 0},
                    "widgets": {"path": "exports", "filename": "bad.wav", "format": "wav"},
                },
            ],
            "links": [
                {"id": "l1", "from": ["n1", 0], "to": ["n2", 1], "type": "TEXT"},
                {"id": "l2", "from": ["n2", 0], "to": ["n3", 0], "type": "AUDIO"},
            ],
            "groups": [],
        }
    )
    result = Executor(project_dir).execute(workflow, target_nodes=["n3"])
    assert result.status == "failed"
    assert result.error and "AUDIO" in result.error
