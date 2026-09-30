from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[2]
from template_fixtures import require_template
TEMPLATE = require_template("midi-automation-demo")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "dialogue_48k.wav", tone, sr)
    (assets / "automation_cc7.mid").write_bytes(b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60MTrk\x00\x00\x00\x04\x00\xff\x2f\x00")
    return tmp_path


def test_midi_automation_demo(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"
        if node.type == "LoadMIDI":
            node.widgets["path"] = "assets/samples/automation_cc7.mid"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n5"])
    assert result.status == "completed", result.error
    assert result.outputs["n3"]["type"] == "AUTOMATION"
    assert result.outputs["n5"]["type"] == "AUDIO"
    automation = executor.cache.load_automation(result.outputs["n3"]["automation_id"])
    # Empty SMF still yields a short duration buffer; CC curve falls back to default_value.
    assert automation.frame_count >= 1
    assert automation.values[0] == pytest.approx(0.75)
