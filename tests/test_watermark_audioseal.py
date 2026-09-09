from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.ai.inference import (
    detect_watermark_audio,
    embed_watermark_audio,
)
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "watermark-embed-detect.groovy.json"


@pytest.fixture(autouse=True)
def stub_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")


def test_embed_then_detect_stub_round_trip() -> None:
    sr = 48_000
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    pcm = np.stack([0.2 * np.sin(2 * np.pi * 440 * t)], axis=0)
    message_id = 42

    watermarked = embed_watermark_audio(
        pcm,
        sample_rate=sr,
        model_id="audioseal-16bit",
        message_id=message_id,
        strength=1.0,
    )
    report = detect_watermark_audio(
        watermarked,
        sample_rate=sr,
        model_id="audioseal-16bit",
        threshold=0.5,
    )

    assert report["watermark_detected"] is True
    assert report["message_id"] == message_id
    assert report["backend"] == "stub"


def test_detect_stub_on_clean_audio_is_negative() -> None:
    sr = 48_000
    pcm = np.zeros((1, sr // 2), dtype=np.float64)
    report = detect_watermark_audio(
        pcm,
        sample_rate=sr,
        model_id="audioseal-16bit",
        threshold=0.5,
    )
    assert report["watermark_detected"] is False


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48_000
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "podcast_denoise_demo.wav", tone, sr)
    registry = ModelRegistry(tmp_path)
    registry.installer.install("audioseal-16bit")
    return tmp_path


def test_watermark_embed_detect_template(project_dir: Path) -> None:
    from groovy.schema.models import Workflow

    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n2", "n3", "n4", "n5", "n6"])
    assert result.status == "completed", result.error

    detect = result.outputs["n3"]
    assert detect["type"] == "MULTI"
    slot_types = [slot.get("type") for slot in detect.get("outputs") or []]
    assert slot_types == ["TEXT", "AUDIO"]

    report = json.loads(next(slot["text"] for slot in detect["outputs"] if slot["type"] == "TEXT"))
    assert report["watermark_detected"] is True
    assert report["message_id"] == 42
    assert result.outputs["n5"]["type"] == "AUDIO"
