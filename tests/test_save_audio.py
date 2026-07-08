from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.core.nodes import SaveAudio
from groovy.nodes.core import register_all
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata

register_all()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.1, int(sr * 0.1), endpoint=False)
    sf.write(assets / "tone.wav", 0.25 * np.sin(2 * np.pi * 440 * t), sr)
    return tmp_path


def test_save_audio_writes_file_and_reports_string_path(project_dir: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="save-audio-test",
        metadata=WorkflowMetadata(title="save-audio-test"),
        nodes=[
            NodeInstance(
                id="n1",
                type="LoadAudio",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/tone.wav"},
            ),
            NodeInstance(
                id="n2",
                type="SaveAudio",
                pos={"x": 200, "y": 0},
                widgets={"path": "exports/renders", "filename": "saved.wav"},
            ),
        ],
        links=[Link(id="l1", from_=["n1", 0], to=["n2", 0], type="AUDIO")],
    )
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n2"])
    assert result.status == "completed", result.error
    out_meta = result.outputs["n2"]
    assert out_meta["type"] == "STRING"
    assert out_meta["path"].endswith("exports/renders/saved.wav")
    assert (project_dir / "exports" / "renders" / "saved.wav").exists()


def test_save_audio_legacy_filename_with_slashes(project_dir: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="save-audio-legacy",
        metadata=WorkflowMetadata(title="legacy"),
        nodes=[
            NodeInstance(
                id="n1",
                type="LoadAudio",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/tone.wav"},
            ),
            NodeInstance(
                id="n2",
                type="SaveAudio",
                pos={"x": 200, "y": 0},
                widgets={"filename": "exports/legacy.wav"},
            ),
        ],
        links=[Link(id="l1", from_=["n1", 0], to=["n2", 0], type="AUDIO")],
    )
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n2"])
    assert result.status == "completed", result.error
    assert (project_dir / "exports" / "legacy.wav").exists()


def test_save_audio_resolve_output_relative() -> None:
    assert SaveAudio._resolve_output_relative("exports/podcast", "ep-01.wav") == "exports/podcast/ep-01.wav"
    assert SaveAudio._resolve_output_relative("exports", "exports/legacy.wav") == "exports/legacy.wav"


def test_save_audio_schema_exposes_path_and_filename_widgets() -> None:
    from groovy.node import NODE_REGISTRY

    schema = NODE_REGISTRY["SaveAudio"].describe()
    widget_names = {widget["name"] for widget in schema["widgets"]}
    assert {"path", "filename", "format", "bit_depth"} <= widget_names
