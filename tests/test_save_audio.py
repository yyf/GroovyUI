from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.audio import AudioBuffer
from groovy.executor.engine import JobContext
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
    out_path = Path(out_meta["path"])
    provenance_path = Path(out_meta["provenance_path"])
    assert out_path.parent == project_dir / "exports" / "renders"
    assert out_path.name.startswith("saved-") and out_path.suffix == ".wav"
    assert provenance_path == out_path.with_name(
        f"{out_path.stem}.provenance.json"
    )
    assert out_path.exists()
    assert provenance_path.exists()


@pytest.mark.parametrize(
    ("bit_depth", "expected_subtype"),
    [
        ("16", "PCM_16"),
        ("24", "PCM_24"),
        ("32", "PCM_32"),
        ("float", "FLOAT"),
    ],
)
def test_save_audio_writes_selected_wav_bit_depth(
    project_dir: Path, bit_depth: str, expected_subtype: str
) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id=f"save-audio-{bit_depth}",
        metadata=WorkflowMetadata(title=f"save-audio-{bit_depth}"),
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
                widgets={
                    "path": "exports/bit-depth",
                    "filename": f"saved-{bit_depth}.wav",
                    "format": "wav",
                    "bit_depth": bit_depth,
                },
            ),
        ],
        links=[Link(id="l1", from_=["n1", 0], to=["n2", 0], type="AUDIO")],
    )

    result = Executor(project_dir).execute(workflow, target_nodes=["n2"])

    assert result.status == "completed", result.error
    info = sf.info(result.outputs["n2"]["path"])
    assert info.format == "WAV"
    assert info.subtype == expected_subtype


def test_save_audio_flac_selection_replaces_wav_extension(project_dir: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="save-audio-flac",
        metadata=WorkflowMetadata(title="save-audio-flac"),
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
                widgets={
                    "path": "exports/formats",
                    "filename": "saved.wav",
                    "format": "flac",
                    "bit_depth": "24",
                },
            ),
        ],
        links=[Link(id="l1", from_=["n1", 0], to=["n2", 0], type="AUDIO")],
    )

    result = Executor(project_dir).execute(workflow, target_nodes=["n2"])

    assert result.status == "completed", result.error
    out_path = Path(result.outputs["n2"]["path"])
    info = sf.info(out_path)
    assert out_path.suffix == ".flac"
    assert not list(out_path.parent.glob("saved-*.wav"))
    assert info.format == "FLAC"
    assert info.subtype == "PCM_24"


def test_save_audio_bypasses_node_cache_and_re_emits_provenance(project_dir: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="save-audio-nocache",
        metadata=WorkflowMetadata(title="save-audio-nocache"),
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
    first = executor.execute(workflow, target_nodes=["n2"])
    assert first.status == "completed", first.error

    # A second render must re-run SaveAudio (side-effecting sink) rather than
    # serving a cached result, so provenance_path is always present + written.
    second = executor.execute(workflow, target_nodes=["n2"])
    assert second.status == "completed", second.error
    second_meta = second.outputs["n2"]
    assert second_meta["type"] == "STRING"
    assert second_meta.get("provenance_path")
    assert Path(second_meta["path"]).exists()
    assert Path(second_meta["provenance_path"]).exists()


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
    assert Path(result.outputs["n2"]["path"]).name.startswith("legacy-")


def test_save_audio_resolve_output_relative() -> None:
    assert SaveAudio._resolve_output_relative("exports/podcast", "ep-01.wav") == "exports/podcast/ep-01.wav"
    assert SaveAudio._resolve_output_relative("exports", "exports/legacy.wav") == "exports/legacy.wav"
    assert SaveAudio._with_format_extension("exports/render.wav", "flac") == "exports/render.flac"
    stamped = SaveAudio._timestamped_relative(
        "exports/render.wav",
        datetime(2026, 7, 18, 4, 29, 30, 123000, tzinfo=UTC),
    )
    assert stamped == "exports/render-20260718T042930123Z.wav"


def test_save_audio_schema_exposes_path_and_filename_widgets() -> None:
    from groovy.node import NODE_REGISTRY

    schema = NODE_REGISTRY["SaveAudio"].describe()
    widget_names = {widget["name"] for widget in schema["widgets"]}
    assert {"path", "filename", "format", "bit_depth"} <= widget_names


def test_save_audio_fails_loudly_without_provenance(project_dir: Path) -> None:
    executor = Executor(project_dir)
    pcm = np.zeros((1, 64), dtype=np.float64)
    audio = AudioBuffer.from_planar(
        pcm, 48000, source_node_type="Test", channel_layout="mono"
    )
    executor.cache.write_audio(audio, pcm)
    node = SaveAudio()
    node.bind_context(
        JobContext(project_dir=project_dir, cache=executor.cache, job_id="missing-prov")
    )

    with pytest.raises(RuntimeError, match="could not write provenance sidecar"):
        node.run(audio=audio, path="exports", filename="incomplete.wav")

    assert not list((project_dir / "exports").glob("incomplete-*.wav"))
