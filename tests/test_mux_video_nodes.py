"""MuxVideo / PreviewVideo / SaveVideo — ffmpeg video+audio compose."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest
from groovy.executor import Executor
from groovy.executor.media_io import ffmpeg_available, mux_video_with_audio, probe_video_dimensions
from groovy.nodes.core import register_all
from groovy.node import NODE_REGISTRY
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata

register_all()

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not on PATH")


def _write_silent_mov(path: Path, *, seconds: float = 0.5, size: str = "160x120") -> None:
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
            f"color=c=black:s={size}:d={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=mono:d={seconds}",
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


def test_mux_video_with_audio_helper(tmp_path: Path) -> None:
    src = tmp_path / "src.mov"
    _write_silent_mov(src, size="160x120")
    pcm = (0.1 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.4, 17640, endpoint=False))).reshape(1, -1)
    dest = tmp_path / "out.mp4"
    mux_video_with_audio(src, pcm, 44100, dest)
    assert dest.is_file()
    assert dest.stat().st_size > 1000
    assert probe_video_dimensions(dest) == (160, 120)


def test_mux_preview_save_video_nodes(tmp_path: Path) -> None:
    samples = tmp_path / "assets" / "samples"
    video = samples / "clip.mov"
    _write_silent_mov(video)

    # Generate a short tone via SignalGenerator → Normalize isn't needed; use LoadAudio on a wav.
    import soundfile as sf

    wav = samples / "tone.wav"
    t = np.linspace(0, 0.4, 17640, endpoint=False)
    sf.write(wav, (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float64), 44100)

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="mux-video-chain",
        metadata=WorkflowMetadata(title="mux-video-chain"),
        nodes=[
            NodeInstance(
                id="n0",
                type="LoadAudio",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/tone.wav"},
            ),
            NodeInstance(
                id="n1",
                type="MuxVideo",
                pos={"x": 200, "y": 0},
                widgets={"path": "assets/samples/clip.mov"},
            ),
            NodeInstance(id="n2", type="PreviewVideo", pos={"x": 400, "y": 0}, widgets={}),
            NodeInstance(
                id="n3",
                type="SaveVideo",
                pos={"x": 400, "y": 120},
                widgets={"path": "exports", "filename": "composed.mp4"},
            ),
        ],
        links=[
            Link(id="l0", **{"from": ["n0", 0], "to": ["n1", 0], "type": "AUDIO"}),
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "VIDEO"}),
            Link(id="l2", **{"from": ["n2", 0], "to": ["n3", 0], "type": "VIDEO"}),
        ],
    )
    assert "MuxVideo" in NODE_REGISTRY
    assert "PreviewVideo" in NODE_REGISTRY
    assert "SaveVideo" in NODE_REGISTRY

    out = Executor(tmp_path).execute(workflow, target_nodes=["n2", "n3"])
    assert out.status == "completed", out.error
    assert out.outputs["n2"]["type"] == "VIDEO"
    assert out.outputs["n2"].get("path")
    assert out.outputs["n2"].get("width") == 160
    assert out.outputs["n2"].get("height") == 120
    assert out.outputs["n3"]["type"] == "STRING"
    rel = out.outputs["n3"]["path"]
    assert isinstance(rel, str)
    assert not Path(rel).is_absolute()
    assert rel.startswith("exports/")
    saved = tmp_path / rel
    assert saved.is_file()
    assert saved.suffix.lower() == ".mp4"
    provenance_rel = out.outputs["n3"].get("provenance_path")
    assert isinstance(provenance_rel, str)
    assert provenance_rel.endswith(".provenance.json")
    sidecar = tmp_path / provenance_rel
    assert sidecar.is_file()
    assert sidecar.name == f"{saved.stem}.provenance.json"
    # Mux must carry a playable audio stream for PreviewVideo / exports.
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(saved),
        ],
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr
    assert "audio" in probe.stdout.lower()


def test_mux_video_cache_busts_when_source_file_replaced(tmp_path: Path) -> None:
    """Replacing assets/.../clip.mov in place must remux — path string alone is not enough."""
    import soundfile as sf

    samples = tmp_path / "assets" / "samples"
    video = samples / "clip.mov"
    _write_silent_mov(video, size="160x120")

    wav = samples / "tone.wav"
    t = np.linspace(0, 0.4, 17640, endpoint=False)
    sf.write(wav, (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float64), 44100)

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="mux-video-cache-bust",
        metadata=WorkflowMetadata(title="mux-video-cache-bust"),
        nodes=[
            NodeInstance(
                id="n0",
                type="LoadAudio",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/tone.wav"},
            ),
            NodeInstance(
                id="n1",
                type="MuxVideo",
                pos={"x": 200, "y": 0},
                widgets={"path": "assets/samples/clip.mov"},
            ),
            NodeInstance(id="n2", type="PreviewVideo", pos={"x": 400, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l0", **{"from": ["n0", 0], "to": ["n1", 0], "type": "AUDIO"}),
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "VIDEO"}),
        ],
    )

    executor = Executor(tmp_path)
    first = executor.execute(workflow, target_nodes=["n2"])
    assert first.status == "completed", first.error
    first_path = first.outputs["n2"]["path"]
    assert first.outputs["n2"].get("width") == 160
    assert first.outputs["n2"].get("height") == 120

    # Replace source video dimensions; same project-relative path string.
    _write_silent_mov(video, size="320x240")

    second = executor.execute(workflow, target_nodes=["n2"])
    assert second.status == "completed", second.error
    assert second.outputs["n2"].get("width") == 320
    assert second.outputs["n2"].get("height") == 240
    # New mux artifact (cache miss), not the prior cached mp4 path.
    assert second.outputs["n2"]["path"] != first_path
