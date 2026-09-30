from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow
from template_fixtures import require_template

register_core()
register_ai()

TEMPLATE = require_template("ambisonic-trajectory-demo")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "podcast_denoise_demo.wav", tone, sr)
    registry = ModelRegistry(tmp_path)
    registry.installer.install("helix-v0.7")
    registry.installer.install("dcase-seld-foa-multiaccdoa")
    return tmp_path


def test_ambisonic_trajectory_demo_template(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4", "n6", "n7", "n8", "n9"])
    assert result.status == "completed", result.error

    assert result.outputs["n2"]["type"] == "TRAJECTORY"
    assert result.outputs["n3"]["type"] == "AMBISONICS"
    assert result.outputs["n4"]["type"] == "TRAJECTORY"
    assert result.outputs["n6"]["type"] == "AUDIO"
    assert result.outputs["n7"]["type"] == "TRAJECTORY"
    assert result.outputs["n8"]["type"] == "TRAJECTORY"
    assert result.outputs["n9"]["type"] == "MULTI"
    meter_slots = result.outputs["n9"]["outputs"]
    assert meter_slots[0]["type"] == "AUDIO"
    assert meter_slots[1]["type"] == "TEXT"
    assert "§METER§" in meter_slots[1]["text"]
    assert "L" in meter_slots[1]["text"] and "R" in meter_slots[1]["text"]

    authored = executor.cache.load_trajectory(result.outputs["n2"]["trajectory_id"])
    assert authored.source == "authored"
    assert len(authored.points) >= 2

    input_mon = executor.cache.load_trajectory(result.outputs["n7"]["trajectory_id"])
    assert input_mon.spatial_meta.get("monitor_role") == "input"
    assert input_mon.points[0]["x"] == pytest.approx(authored.points[0]["x"], abs=1e-6)

    ambi, pcm = executor.cache.load_ambisonics(result.outputs["n3"]["ambisonics_id"])
    assert ambi.layout_order == 1
    assert pcm.shape[0] == 4
    assert pcm.shape[1] > 0

    extracted = executor.cache.load_trajectory(result.outputs["n4"]["trajectory_id"])
    assert extracted.source == "extracted"
    assert len(extracted.points) >= 1

    output_mon = executor.cache.load_trajectory(result.outputs["n8"]["trajectory_id"])
    assert output_mon.spatial_meta.get("monitor_role") == "output"

    # Shared timebase: authored duration matches audio / extracted span.
    authored_dur = authored.points[-1]["t_sec"]
    extracted_dur = extracted.points[-1]["t_sec"]
    assert abs(authored_dur - extracted_dur) < 0.05

    # Stub round-trip: mid-path X should agree (L→R sweep crosses ~0).
    mid_t = 0.5 * authored_dur
    ax, _ay, az = authored.sample_at(mid_t)
    ex, _ey, ez = extracted.sample_at(mid_t)
    assert abs(ax - ex) < 0.15
    assert abs(az - ez) < 0.15

    # Stereo Preview follows Multi-ACCDOA (+X left): start +X → left-dominant; end −X → right.
    preview_id = result.outputs["n6"]["cache_id"]
    _buf, stereo = executor.cache.load_audio(preview_id)
    assert stereo.shape[0] == 2
    head = max(1, stereo.shape[1] // 20)
    left_energy = float(np.mean(stereo[0, :head] ** 2))
    right_energy = float(np.mean(stereo[1, :head] ** 2))
    assert left_energy > right_energy
    tail = max(1, stereo.shape[1] // 20)
    left_tail = float(np.mean(stereo[0, -tail:] ** 2))
    right_tail = float(np.mean(stereo[1, -tail:] ** 2))
    assert right_tail > left_tail
