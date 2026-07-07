from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from groovy.executor import Executor
from groovy.executor.audio import AudioBuffer
from groovy.executor.engine import JobContext
from groovy.nodes.core import register_all
from groovy.node import NODE_REGISTRY
from groovy.registry.agent.registry_freshness import scan_registry_freshness
from groovy.registry.agent.template_generator import generate_template_from_workflow
from groovy.registry import ModelRegistry
from groovy.registry.pack_installer import PackInstaller
from groovy.schema.models import Workflow
from groovy.server.main import app

register_all()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "dialogue_48k.wav", tone, sr)
    pcm51 = np.vstack([tone, tone * 0.8, tone * 0.5, tone * 0.2, tone * 0.6, tone * 0.6])
    sf.write(assets / "surround_51.wav", pcm51.T, sr)
    return tmp_path


def test_multichannel_normalize_node(project_dir: Path) -> None:
    sr = 48000
    pcm = np.vstack([np.full(48000, 0.1), np.full(48000, 0.2)])
    source = AudioBuffer.from_planar(pcm, sr, source_node_type="Test", channel_layout="stereo")
    executor = Executor(project_dir)
    executor.cache.write_audio(source, pcm)
    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="mc-norm")
    node = NODE_REGISTRY["MultichannelNormalize"]()
    node.bind_context(ctx)
    out, = node.run(audio=source, target_lufs=-23.0)
    assert out.channel_layout == "stereo"


def test_channel_convert_71_downmix(project_dir: Path) -> None:
    sr = 48000
    pcm = np.random.default_rng(0).normal(0, 0.1, (8, 256))
    source = AudioBuffer.from_planar(pcm, sr, source_node_type="Test", channel_layout="7.1")
    executor = Executor(project_dir)
    executor.cache.write_audio(source, pcm)
    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="71")
    node = NODE_REGISTRY["ChannelConvert"]()
    node.bind_context(ctx)
    out, = node.run(audio=source, layout="stereo")
    assert out.channel_layout == "stereo"
    _, rendered = executor.cache.load_audio(out.id)
    assert rendered.shape[0] == 2


def test_template_generator_agent() -> None:
    workflow = {
        "schema_version": "1.0.0",
        "groovy_version": "0.1.0",
        "id": "test",
        "metadata": {"title": "Demo"},
        "nodes": [{"id": "n1", "type": "Preview", "widgets": {}}],
        "links": [],
        "groups": [],
    }
    result = generate_template_from_workflow(
        workflow,
        title="Generated Demo",
        known_node_types=set(NODE_REGISTRY.keys()),
    )
    assert result["template_id"] == "generated-demo"
    assert result["validation"]["valid"] is True


def test_registry_freshness_scan(project_dir: Path) -> None:
    registry = ModelRegistry(project_dir)
    report = scan_registry_freshness(registry.catalog, registry.store)
    assert "flags" in report
    assert report["agent"] == "registry_freshness"


def test_community_pack_install(project_dir: Path) -> None:
    installer = PackInstaller(project_dir)
    state = installer.install("groovy-modular-control", consent=True)
    assert state.status == "installed"
    installed = installer.list_installed()
    assert any(item["id"] == "groovy-modular-control" for item in installed)


def test_pack_and_template_api() -> None:
    client = TestClient(app)
    packs = client.get("/api/packs")
    assert packs.status_code == 200
    assert any(item["id"] == "groovy-immersive-stubs" for item in packs.json()["packs"])
    install = client.post("/api/packs/groovy-immersive-stubs/install")
    assert install.status_code == 200
    freshness = client.get("/api/registry/freshness")
    assert freshness.status_code == 200
    template = client.post(
        "/api/workflow/generate-template",
        json={
            "workflow": {
                "schema_version": "1.0.0",
                "groovy_version": "0.1.0",
                "id": "x",
                "metadata": {"title": "API Demo"},
                "nodes": [{"id": "n1", "type": "Preview", "widgets": {}}],
                "links": [],
                "groups": [],
            },
            "title": "API Generated",
        },
    )
    assert template.status_code == 200
    assert template.json()["agent"] == "template_generator"
