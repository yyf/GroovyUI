from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.audio import AudioBuffer
from groovy.executor.engine import JobContext
from groovy.nodes.core import register_all
from groovy.node import NODE_REGISTRY
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata

register_all()

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "tone.wav", tone, sr)
    stereo = np.vstack([tone, tone * 0.8])
    sf.write(assets / "stereo.wav", stereo.T, sr)
    return tmp_path


def _mini_workflow(nodes: list[NodeInstance], links: list[Link]) -> Workflow:
    return Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="signal-integrity-micro",
        metadata=WorkflowMetadata(title="signal-integrity-micro"),
        nodes=nodes,
        links=links,
    )


def test_mix_rejects_sample_rate_mismatch(project_dir: Path) -> None:
    executor = Executor(project_dir)
    sr_a, sr_b = 48000, 44100
    frames = 128
    pcm_a = np.full((1, frames), 0.1)
    pcm_b = np.full((1, frames), 0.2)
    buf_a = AudioBuffer.from_planar(pcm_a, sr_a, source_node_type="Test", channel_layout="mono")
    buf_b = AudioBuffer.from_planar(pcm_b, sr_b, source_node_type="Test", channel_layout="mono")
    executor.cache.write_audio(buf_a, pcm_a)
    executor.cache.write_audio(buf_b, pcm_b)

    workflow = _mini_workflow(
        [
            NodeInstance(id="a", type="Mix", pos={"x": 0, "y": 0}, widgets={}),
        ],
        [],
    )
    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="mix-sr")
    node = NODE_REGISTRY["Mix"]()
    node.bind_context(ctx)
    with pytest.raises(ValueError, match="Sample rate mismatch"):
        node.run(a=buf_a, b=buf_b)


def test_mix_rejects_channel_layout_mismatch(project_dir: Path) -> None:
    executor = Executor(project_dir)
    sr = 48000
    frames = 128
    mono = np.full((1, frames), 0.1)
    stereo = np.full((2, frames), 0.2)
    buf_mono = AudioBuffer.from_planar(mono, sr, source_node_type="Test", channel_layout="mono")
    buf_stereo = AudioBuffer.from_planar(stereo, sr, source_node_type="Test", channel_layout="stereo")
    executor.cache.write_audio(buf_mono, mono)
    executor.cache.write_audio(buf_stereo, stereo)

    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="mix-layout")
    node = NODE_REGISTRY["Mix"]()
    node.bind_context(ctx)
    with pytest.raises(ValueError, match="Channel layout mismatch"):
        node.run(a=buf_mono, b=buf_stereo)


def test_mix_fan_in_preserves_layout(project_dir: Path) -> None:
    workflow = _mini_workflow(
        [
            NodeInstance(
                id="n1",
                type="LoadAudio",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/tone.wav"},
            ),
            NodeInstance(
                id="n2",
                type="LoadAudio",
                pos={"x": 0, "y": 120},
                widgets={"path": "assets/samples/tone.wav"},
            ),
            NodeInstance(id="n3", type="Mix", pos={"x": 240, "y": 0}, widgets={}),
        ],
        [
            Link(id="l1", from_=["n1", 0], to=["n3", 0], type="AUDIO"),
            Link(id="l2", from_=["n2", 0], to=["n3", 1], type="AUDIO"),
        ],
    )
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n3"])
    assert result.status == "completed", result.error
    cache_id = result.outputs["n3"]["cache_id"]
    meta = executor.cache.read_meta(cache_id)
    assert meta["channel_layout"] == "mono"
    assert meta["sample_rate"] == 48000
    assert meta["frame_count"] > 0


def test_module_inlet_preserves_layout(project_dir: Path) -> None:
    sr = 48000
    frames = 64
    pcm = np.full((2, frames), 0.2)
    source = AudioBuffer.from_planar(pcm, sr, source_node_type="Test", channel_layout="stereo")
    executor = Executor(project_dir)
    executor.cache.write_audio(source, pcm)
    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="module-layout")
    inlet = NODE_REGISTRY["ModuleInlet"]()
    inlet.bind_context(ctx)
    outlet = NODE_REGISTRY["ModuleOutlet"]()
    outlet.bind_context(ctx)
    mid, = inlet.run(signal=source, name="audio_in")
    out, = outlet.run(signal=mid, name="audio_out")
    meta = executor.cache.read_meta(out.id)
    assert meta["channel_layout"] == "stereo"
    assert meta["sample_rate"] == sr


def test_save_audio_round_trip_lossless(project_dir: Path) -> None:
    load_save = _mini_workflow(
        [
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
                widgets={"path": "exports", "filename": "roundtrip.wav", "format": "wav"},
            ),
        ],
        [Link(id="l1", from_=["n1", 0], to=["n2", 0], type="AUDIO")],
    )
    reload = _mini_workflow(
        [
            NodeInstance(
                id="n3",
                type="LoadAudio",
                pos={"x": 0, "y": 0},
                widgets={"path": "exports/roundtrip.wav"},
            ),
        ],
        [],
    )
    executor = Executor(project_dir)
    save_result = executor.execute(load_save, target_nodes=["n2"])
    assert save_result.status == "completed", save_result.error
    reload_result = executor.execute(reload, target_nodes=["n3"])
    assert reload_result.status == "completed", reload_result.error

    src_id = save_result.outputs["n1"]["cache_id"]
    dst_id = reload_result.outputs["n3"]["cache_id"]
    _, src_pcm = executor.cache.load_audio(src_id)
    _, dst_pcm = executor.cache.load_audio(dst_id)

    min_frames = min(src_pcm.shape[1], dst_pcm.shape[1])
    src_trim = src_pcm[:, :min_frames]
    dst_trim = dst_pcm[:, :min_frames]
    assert hashlib.sha256(src_trim.tobytes()).hexdigest() == hashlib.sha256(dst_trim.tobytes()).hexdigest()

    prov_path = project_dir / ".groovy" / "cache" / f"{dst_id}.provenance.json"
    assert prov_path.exists()
    prov = json.loads(prov_path.read_text())
    assert prov.get("node", {}).get("node_type") == "LoadAudio"


def test_manifest_includes_per_hop_signal_fields(project_dir: Path) -> None:
    workflow = _mini_workflow(
        [
            NodeInstance(
                id="n1",
                type="LoadAudio",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/tone.wav"},
            ),
            NodeInstance(id="n2", type="Normalize", pos={"x": 200, "y": 0}, widgets={"mode": "lufs"}),
        ],
        [Link(id="l1", from_=["n1", 0], to=["n2", 0], type="AUDIO")],
    )
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n2"])
    assert result.status == "completed", result.error
    manifest = json.loads(Path(result.manifest_path).read_text())
    for node_id in ("n1", "n2"):
        entry = next(item for item in manifest["nodes"] if item["node_id"] == node_id)
        output = entry["output"]
        assert output["type"] == "AUDIO"
        for field in ("sample_rate", "channel_layout", "frame_count", "content_hash"):
            assert output.get(field), f"{node_id} missing {field}"
