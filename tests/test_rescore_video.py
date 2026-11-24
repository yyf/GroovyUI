"""LoadVideo / SplitVideo / Rescore Video template."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.executor.media_io import ffmpeg_available
from groovy.node import NODE_REGISTRY, known_node_types
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all
from groovy.registry import ModelRegistry
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata
from groovy.schema.validate import validate_workflow
from template_fixtures import require_template

register_all()
register_ai()

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not on PATH")


def _write_av_mov(path: Path, *, seconds: float = 0.5, size: str = "160x120") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s={size}:d={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_load_split_mux_video_chain(tmp_path: Path) -> None:
    samples = tmp_path / "assets" / "samples"
    video = samples / "clip.mov"
    _write_av_mov(video)

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="load-split-mux",
        metadata=WorkflowMetadata(title="load-split-mux"),
        nodes=[
            NodeInstance(
                id="n0",
                type="LoadVideo",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/clip.mov"},
            ),
            NodeInstance(id="n1", type="SplitVideo", pos={"x": 200, "y": 0}, widgets={}),
            NodeInstance(
                id="n2",
                type="MuxVideo",
                pos={"x": 400, "y": 0},
                widgets={"path": ""},
            ),
            NodeInstance(id="n3", type="PreviewVideo", pos={"x": 600, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l0", **{"from": ["n0", 0], "to": ["n1", 0], "type": "VIDEO"}),
            # Split silent video → Mux video inlet; Split audio → Mux audio (identity remux)
            Link(id="l1", **{"from": ["n1", 1], "to": ["n2", 0], "type": "AUDIO"}),
            Link(id="l2", **{"from": ["n1", 0], "to": ["n2", 1], "type": "VIDEO"}),
            Link(id="l3", **{"from": ["n2", 0], "to": ["n3", 0], "type": "VIDEO"}),
        ],
    )
    assert "LoadVideo" in NODE_REGISTRY
    assert "SplitVideo" in NODE_REGISTRY
    assert NODE_REGISTRY["SplitVideo"].RETURN_TYPES == ("VIDEO", "AUDIO")
    mux_inputs = [s["name"] for s in NODE_REGISTRY["MuxVideo"].describe()["inputs"]]
    assert mux_inputs == ["audio", "video"]

    out = Executor(tmp_path).execute(workflow, target_nodes=["n3"])
    assert out.status == "completed", out.error
    assert out.outputs["n1"]["type"] == "MULTI"
    slots = out.outputs["n1"]["outputs"]
    assert slots[0]["type"] == "VIDEO"
    assert slots[1]["type"] == "AUDIO"
    assert out.outputs["n3"]["type"] == "VIDEO"
    assert out.outputs["n3"].get("width") == 160
    assert out.outputs["n3"].get("height") == 120


def test_rescore_video_template_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("rescore-video")
    data = json.loads(path.read_text())
    assert data["metadata"]["title"] == "Rescore Video"
    assert "premium" in data["metadata"]["tags"]
    assert "rescore" in data["metadata"]["tags"]
    assert "compare" in data["metadata"]["tags"]
    assert "starter" not in data["metadata"]["tags"]
    # Premium pack lives under docs/internal/templates/ (not public templates/).
    assert path.as_posix().endswith(
        "/docs/internal/templates/rescore-video.groovy.json"
    )

    by_id = {n["id"]: n for n in data["nodes"]}
    assert by_id["n0"]["widgets"]["path"] == "assets/samples/Cyberpunk-station.mp4"
    assert by_id["n3"]["widgets"]["model"] == "ace-step-1.5-sft"
    assert by_id["n3"]["widgets"]["num_inference_steps"] == 72
    assert by_id["n3"]["widgets"]["guidance_scale"] == 11.0
    assert by_id["n3"]["widgets"]["seconds_total"] == 2.0
    assert by_id["n2"]["widgets"]["text"] == (
        "immersive rainy cyberpunk transit soundscape, soft rain on umbrellas and wet asphalt, "
        "layered distant quadcopter drone whirrs, low industrial hum and steam vents, "
        "muffled multilingual crowd murmur, faint neon electrical buzz, sparse melancholic "
        "dark synth pads, slow attack long decay reverb, atmospheric documentary bed, "
        "instrumental, no vocals, no drums, no melody hook"
    )
    assert by_id["n3"]["widgets"]["prompt"] == by_id["n2"]["widgets"]["text"]
    assert by_id["n3"]["widgets"]["lyrics_text"] == ""
    assert by_id["n3"]["widgets"]["audio_cover_strength"] == 0.18
    note_a = by_id["note-a"]
    note_b = by_id["note-b"]
    n5 = by_id["n5"]
    n6 = by_id["n6"]
    assert abs(note_a["pos"]["x"] - n5["pos"]["x"]) <= 20
    assert abs(note_b["pos"]["x"] - n6["pos"]["x"]) <= 20
    assert note_a["pos"]["y"] < n5["pos"]["y"]
    assert note_b["pos"]["y"] < n6["pos"]["y"]
    assert by_id["n5"]["type"] == "PreviewVideo"
    assert by_id["n6"]["type"] == "PreviewVideo"
    assert by_id["n8"]["type"] == "PreviewAudio"
    assert by_id["n9"]["type"] == "PreviewAudio"
    assert by_id["n-log"]["type"] == "SaveGenerateLog"

    links = data["links"]
    # A = original LoadVideo → PreviewVideo; B = Mux → PreviewVideo
    assert any(
        link["from"] == ["n0", 0] and link["to"] == ["n5", 0] and link["type"] == "VIDEO"
        for link in links
    )
    assert any(
        link["from"] == ["n4", 0] and link["to"] == ["n6", 0] and link["type"] == "VIDEO"
        for link in links
    )
    # Audio Previews for Inspector A/B
    assert any(
        link["from"] == ["n1", 1] and link["to"] == ["n8", 0] and link["type"] == "AUDIO"
        for link in links
    )
    assert any(
        link["from"] == ["n3", 0] and link["to"] == ["n9", 0] and link["type"] == "AUDIO"
        for link in links
    )
    assert any(
        link["from"] == ["n1", 1] and link["to"] == ["n3", 2] and link["type"] == "AUDIO"
        for link in links
    )
    assert any(
        link["from"] == ["n2", 0] and link["to"] == ["n3", 0] and link["type"] == "TEXT"
        for link in links
    )
    assert any(
        link["from"] == ["n3", 1] and link["to"] == ["n-log", 0] and link["type"] == "GENERATE_LOG"
        for link in links
    )

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=known_node_types())
    assert result.valid, [e.message for e in result.errors]

    samples = tmp_path / "assets" / "samples"
    samples.mkdir(parents=True)
    src = Path(__file__).resolve().parents[1] / "assets" / "samples" / "Cyberpunk-station.mp4"
    if src.is_file():
        (samples / "Cyberpunk-station.mp4").write_bytes(src.read_bytes())
    else:
        _write_av_mov(samples / "Cyberpunk-station.mp4", seconds=1.0)

    registry = ModelRegistry(tmp_path)
    registry.installer.install("ace-step-1.5-sft")
    out = Executor(tmp_path).execute(
        workflow, target_nodes=["n3", "n5", "n6", "n7", "n8", "n9", "n-log"]
    )
    assert out.status == "completed", out.error
    assert out.outputs["n3"]["type"] == "MULTI"
    assert out.outputs["n3"]["outputs"][0]["type"] == "AUDIO"
    assert out.outputs["n3"]["outputs"][1]["type"] == "GENERATE_LOG"
    assert out.outputs["n5"]["type"] == "VIDEO"
    assert out.outputs["n6"]["type"] == "VIDEO"
    assert out.outputs["n7"]["type"] == "STRING"
    assert out.outputs["n8"]["type"] == "AUDIO"
    assert out.outputs["n9"]["type"] == "AUDIO"
    assert out.outputs["n-log"]["type"] == "STRING"
    saved = tmp_path / out.outputs["n7"]["path"]
    assert saved.is_file()
