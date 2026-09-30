from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.core import register_all
from groovy.schema.models import Workflow

register_all()

ROOT = Path(__file__).resolve().parents[2]
from template_fixtures import require_template
TEMPLATE = require_template("surround-downmix")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    return tmp_path


def test_surround_downmix_template(project_dir: Path) -> None:
    assets = project_dir / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    frames = 4800
    fl = np.sin(2 * np.pi * 220 * np.linspace(0, frames / sr, frames, endpoint=False))
    pcm = np.zeros((6, frames))
    pcm[0] = fl
    pcm[2] = 0.5 * fl
    pcm[4] = 0.3 * fl
    sf.write(assets / "surround_51.wav", pcm.T, sr)

    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/surround_51.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4"])
    assert result.status == "completed", result.error
    assert (project_dir / "assets" / "exports" / "surround_stereo.flac").exists()
    cache_id = result.outputs["n4"]["cache_id"]
    meta = executor.cache.read_meta(cache_id)
    assert meta["channel_layout"] == "stereo"
