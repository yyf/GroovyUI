from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from groovy.executor import Executor
from groovy.executor.engine import JobContext
from groovy.executor.live_midi import LiveIoState, demo_control_events
from groovy.nodes.core import register_all
from groovy.node import NODE_REGISTRY
from groovy.schema.models import Workflow
from groovy.server.main import app

register_all()

SURROUND_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "surround-mix.groovy.json"
KEYBOARD_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "keyboard-to-music.groovy.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "dialogue_48k.wav", tone, sr)
    return tmp_path


def test_live_io_settings_roundtrip(project_dir: Path) -> None:
    state = LiveIoState(project_dir)
    state.settings.midi_input_enabled = True
    state.save_settings()
    reloaded = LiveIoState(project_dir)
    assert reloaded.settings.midi_input_enabled is True


def test_midi_in_device_demo_events(project_dir: Path) -> None:
    executor = Executor(project_dir)
    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="midi-live")
    node = NODE_REGISTRY["MIDIInDevice"]()
    node.bind_context(ctx)
    midi, = node.run(device_id="virtual:in-demo", frame_count=48000)
    assert midi.midi_kind == "control"
    events = demo_control_events(frame_count=48000, sample_rate=48000)
    assert len(events) >= 2


def test_audio_devices_api() -> None:
    client = TestClient(app)
    response = client.get("/api/audio/devices", params={"direction": "in"})
    assert response.status_code == 200
    devices = response.json()["devices"]
    assert any(device["id"] == "virtual:audio:in-demo" for device in devices)
    assert all(device["direction"] == "in" for device in devices)


def test_audio_settings_roundtrip(project_dir: Path) -> None:
    state = LiveIoState(project_dir)
    state.settings.audio_input_enabled = True
    state.settings.default_audio_output_id = "virtual:audio:out-demo"
    state.save_settings()
    reloaded = LiveIoState(project_dir)
    assert reloaded.settings.audio_input_enabled is True
    assert reloaded.settings.default_audio_output_id == "virtual:audio:out-demo"


def test_live_io_settings_api_includes_audio() -> None:
    client = TestClient(app)
    response = client.get("/api/settings/live-io")
    assert response.status_code == 200
    data = response.json()
    assert "audio_input_enabled" in data
    assert "default_audio_input_id" in data


def test_midi_devices_api() -> None:
    client = TestClient(app)
    response = client.get("/api/midi/devices", params={"direction": "in"})
    assert response.status_code == 200
    devices = response.json()["devices"]
    assert any(device["id"] == "virtual:in-demo" for device in devices)


def test_osc_in_rejected_when_disabled() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/osc/in",
        json={"address": "/groovy/node/n1/gain", "args": [0.5]},
    )
    assert response.status_code == 403


def test_surround_mix_template(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(SURROUND_TEMPLATE.read_text()))
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n8"])
    assert result.status == "completed", result.error
    meta = executor.cache.read_meta(result.outputs["n6"]["cache_id"])
    assert meta["channel_layout"] == "5.1"


def test_keyboard_to_music_template(project_dir: Path) -> None:
    from groovy.nodes.ai import register_all as register_ai
    from groovy.registry import ModelRegistry

    register_ai()
    registry = ModelRegistry(project_dir)
    registry.installer.install("musicgen-melody-small")
    workflow = Workflow.model_validate(json.loads(KEYBOARD_TEMPLATE.read_text()))
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n3"])
    assert result.status == "completed", result.error
