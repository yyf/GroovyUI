"""Tests for VerifySamples / sample_integrity helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from groovy.executor.audio import AudioBuffer
from groovy.executor.cache import CacheStore
from groovy.executor.sample_integrity import pcm_content_hash, sample_pair_check, verify_samples_for_audio
from groovy.node import NODE_REGISTRY
from groovy.nodes.core import register_all as register_core


register_core()


def test_verify_samples_registered() -> None:
    assert "VerifySamples" in NODE_REGISTRY
    schema = NODE_REGISTRY["VerifySamples"].describe()
    assert schema["outputs"][0]["type"] == "SAMPLE_CHECK"
    assert schema["outputs"][1]["type"] == "AUDIO"
    assert schema.get("sample_accurate") is True


def test_verify_samples_hash_match(tmp_path: Path) -> None:
    cache = CacheStore(tmp_path)
    pcm = np.zeros((1, 4800), dtype=np.float64)
    pcm[0, ::100] = 0.25
    buffer = AudioBuffer.from_planar(pcm, 48000, source_node_type="LoadAudio")
    cache.write_audio(buffer, pcm)

    check = verify_samples_for_audio(cache, buffer.id)
    assert check["hash_match"] is True
    assert check["label"] == "match"
    assert check["ok"] is True
    assert check["frame_count"] == 4800
    assert check["sample_rate"] == 48000
    assert check["content_hash"] == pcm_content_hash(pcm)


def test_verify_samples_node_via_executor(tmp_path: Path) -> None:
    from groovy.executor import Executor
    from groovy.executor.engine import JobContext
    from groovy.schema.models import Workflow

    project = tmp_path / "project"
    project.mkdir()
    wav = project / "tone.wav"
    import soundfile as sf

    pcm = np.sin(2 * np.pi * 220 * np.arange(4800) / 48000).astype(np.float32)
    sf.write(wav, pcm, 48000)
    data = {
        "schema_version": "1.0.0",
        "groovy_version": "0.1.0",
        "id": "verify-samples-unit",
        "metadata": {"title": "VerifySamples unit"},
        "nodes": [
            {"id": "n1", "type": "LoadAudio", "pos": {"x": 0, "y": 0}, "widgets": {"path": "tone.wav"}},
            {"id": "n2", "type": "VerifySamples", "pos": {"x": 200, "y": 0}, "widgets": {}},
        ],
        "links": [{"id": "l1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"}],
        "groups": [],
        "view": {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
    }
    workflow = Workflow.model_validate(data)
    out = Executor(project).execute(workflow, target_nodes=["n2"])
    assert out.status == "completed", out.error
    payload = out.outputs["n2"]
    assert payload["type"] == "MULTI"
    slots = payload["outputs"]
    assert slots[0]["type"] == "SAMPLE_CHECK"
    assert slots[1]["type"] == "AUDIO"
    assert slots[0].get("sample_check_id")

    # Direct bind: hash match on the AUDIO outlet buffer
    executor = Executor(project)
    audio_id = slots[1]["cache_id"]
    buffer, _ = executor.cache.load_audio(audio_id)
    node = NODE_REGISTRY["VerifySamples"]()
    node.bind_context(JobContext(project_dir=project, cache=executor.cache, job_id="vs"))
    report, audio_out = node.run(audio=buffer)
    assert audio_out.id == buffer.id
    assert report.record["sample_check"]["hash_match"] is True
    assert report.record["sample_check"]["sample_count"] == report.record["sample_check"]["frame_count"]
    assert report.socket_type == "SAMPLE_CHECK"


def test_sample_pair_check_identical() -> None:
    meta = {
        "content_hash": "sha256:abc",
        "sample_rate": 48000,
        "frame_count": 100,
        "channel_layout": "mono",
    }
    result = sample_pair_check(meta, dict(meta))
    assert result["label"] == "identical"
    assert result["same_content_hash"] is True
