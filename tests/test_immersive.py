from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.ambisonics import (
    decode_foa_to_stereo,
    encode_foa_from_audio,
    encode_foa_from_trajectory,
    foa_direction_xyz,
    rotate_foa_yaw,
)
from groovy.executor.engine import JobContext
from groovy.nodes.core import register_all
from groovy.node import NODE_REGISTRY
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata

register_all()

ROOT = Path(__file__).resolve().parents[1]
from template_fixtures import require_template
AMBISONIC_TEMPLATE = require_template("ambisonic-vr-preview")
OBJECT_TEMPLATE = require_template("object-spatial-demo")


def test_foa_encode_decode_roundtrip() -> None:
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    mono = 0.3 * np.sin(2 * np.pi * 440 * t)
    foa = encode_foa_from_audio(mono.reshape(1, -1))
    assert foa.shape[0] == 4
    stereo = decode_foa_to_stereo(foa)
    assert stereo.shape[0] == 2
    assert stereo.shape[1] == mono.shape[0]


def test_foa_rotate_changes_stereo() -> None:
    sr = 48000
    frames = 256
    mono = np.ones(frames) * 0.5
    foa = encode_foa_from_audio(mono.reshape(1, -1))
    before = decode_foa_to_stereo(foa)
    rotated = rotate_foa_yaw(foa, 90.0)
    after = decode_foa_to_stereo(rotated)
    assert not np.allclose(before, after)


def test_trajectory_encode_decode_lr_matches_accdoa_x() -> None:
    """Multi-ACCDOA left (+X) must decode louder in the left ear (AmbiY = +X)."""
    frames = 512
    mono = np.ones(frames) * 0.5
    # Multi-ACCDOA: x=left, y=up, z=front — hard left = +X.
    xyz = np.vstack(
        [
            np.ones(frames),
            np.zeros(frames),
            np.zeros(frames),
        ]
    )
    foa = encode_foa_from_trajectory(mono.reshape(1, -1), xyz=xyz)
    recovered = foa_direction_xyz(foa)
    assert recovered[0, frames // 2] == pytest.approx(1.0, abs=0.05)
    stereo = decode_foa_to_stereo(foa)
    assert float(np.mean(stereo[0] ** 2)) > float(np.mean(stereo[1] ** 2))

    # Hard right (−X) → right ear louder.
    xyz_r = np.vstack([-np.ones(frames), np.zeros(frames), np.zeros(frames)])
    foa_r = encode_foa_from_trajectory(mono.reshape(1, -1), xyz=xyz_r)
    stereo_r = decode_foa_to_stereo(foa_r)
    assert float(np.mean(stereo_r[1] ** 2)) > float(np.mean(stereo_r[0] ** 2))


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "dialogue_48k.wav", tone, sr)
    return tmp_path


def test_ambisonic_vr_preview_template(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(AMBISONIC_TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n5"])
    assert result.status == "completed", result.error
    assert result.outputs["n5"]["type"] == "AUDIO"


def test_object_spatial_demo_template(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(OBJECT_TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4"])
    assert result.status == "completed", result.error
    meta = executor.cache.read_meta(result.outputs["n4"]["cache_id"])
    assert meta["channel_layout"] == "stereo"


def test_object_from_audio_node(project_dir: Path) -> None:
    from groovy.executor.audio import AudioBuffer

    sr = 48000
    frames = 128
    pcm = np.full((1, frames), 0.2)
    source = AudioBuffer.from_planar(pcm, sr, source_node_type="Test", channel_layout="mono")
    executor = Executor(project_dir)
    executor.cache.write_audio(source, pcm)
    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="oba-test")
    node = NODE_REGISTRY["ObjectFromAudio"]()
    node.bind_context(ctx)
    scene, = node.run(audio=source, name="TestObj", azimuth=45.0)
    assert len(scene.objects) == 1
    assert scene.objects[0]["position"]["azimuth"] == 45.0
