from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.media_io import (
    ffmpeg_available,
    read_audio_pcm,
    write_audio_ffmpeg,
)
from groovy.nodes.core import register_all
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata

register_all()

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not on PATH")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    samples = tmp_path / "assets" / "samples"
    samples.mkdir(parents=True)
    sr = 44100
    t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
    tone = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float64)
    stereo = np.column_stack([tone, tone * 0.8])
    wav_path = samples / "tone.wav"
    sf.write(wav_path, stereo, sr)

    mp4_path = samples / "tone.mp4"
    write_audio_ffmpeg(
        mp4_path,
        stereo.T,
        sr,
        format_name="mp4",
    )

    # Two-stream stand-in for OpenSTEM: stream 0 = mix, stream 1 = quieter alt.
    stem_path = samples / "demo.stem.mp4"
    mix_wav = samples / "_mix.wav"
    alt_wav = samples / "_alt.wav"
    sf.write(mix_wav, stereo, sr)
    sf.write(alt_wav, stereo * 0.25, sr)
    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mix_wav),
            "-i",
            str(alt_wav),
            "-map",
            "0:a:0",
            "-map",
            "1:a:0",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(stem_path),
        ],
        check=True,
        capture_output=True,
    )
    mix_wav.unlink(missing_ok=True)
    alt_wav.unlink(missing_ok=True)
    return tmp_path


def test_read_mp4_via_ffmpeg(project_dir: Path) -> None:
    pcm, sr = read_audio_pcm(project_dir / "assets/samples/tone.mp4")
    assert sr == 44100
    assert pcm.ndim == 2
    assert pcm.shape[0] == 2
    assert pcm.shape[1] > 1000


def test_read_stem_mp4_defaults_to_stream_zero(project_dir: Path) -> None:
    mix, _ = read_audio_pcm(project_dir / "assets/samples/demo.stem.mp4", stream_index=0)
    alt, _ = read_audio_pcm(project_dir / "assets/samples/demo.stem.mp4", stream_index=1)
    assert float(np.sqrt(np.mean(np.square(mix)))) > float(
        np.sqrt(np.mean(np.square(alt)))
    )


def test_load_audio_node_accepts_mp4(project_dir: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="load-mp4",
        metadata=WorkflowMetadata(title="load-mp4"),
        nodes=[
            NodeInstance(
                id="n1",
                type="LoadAudio",
                widgets={"path": "assets/samples/tone.mp4", "audio_stream": 0},
            ),
            NodeInstance(id="n2", type="Preview", widgets={}),
        ],
        links=[Link(id="l1", from_=["n1", 0], to=["n2", 0], type="AUDIO")],
    )
    result = Executor(project_dir).execute(workflow, target_nodes=["n2"])
    assert result.status == "completed", result.error
    # Stereo LoadAudio emits per-channel AUDIO outlets as MULTI (outlet 0 → Preview).
    load_out = result.outputs["n1"]
    assert load_out["type"] == "MULTI"
    assert len(load_out["outputs"]) == 2
    assert all(slot.get("type") == "AUDIO" and slot.get("cache_id") for slot in load_out["outputs"])
    assert result.outputs["n2"]["type"] == "AUDIO"
    assert result.outputs["n2"].get("cache_id")

def test_save_audio_writes_mp4(project_dir: Path) -> None:
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="save-mp4",
        metadata=WorkflowMetadata(title="save-mp4"),
        nodes=[
            NodeInstance(
                id="n1",
                type="LoadAudio",
                widgets={"path": "assets/samples/tone.wav"},
            ),
            NodeInstance(
                id="n2",
                type="SaveAudio",
                widgets={
                    "path": "exports",
                    "filename": "out.mp4",
                    "format": "mp4",
                    "bit_depth": "16",
                },
            ),
        ],
        links=[Link(id="l1", from_=["n1", 0], to=["n2", 0], type="AUDIO")],
    )
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n2"])
    assert result.status == "completed", result.error
    exported = Path(result.outputs["n2"]["path"])
    assert exported.exists()
    assert exported.suffix.lower() == ".mp4"
    assert exported.stat().st_size > 500


def test_stem_split_template_path_is_stem_demo() -> None:
    from template_fixtures import require_template

    data = json.loads(require_template("stem-separation").read_text())
    load = next(node for node in data["nodes"] if node["type"] == "LoadAudio")
    assert load["widgets"]["path"] == "assets/samples/stem_separation_demo.wav"
