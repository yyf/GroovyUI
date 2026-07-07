from __future__ import annotations

import json
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "sing-from-midi.groovy.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    (assets / "automation_cc7.mid").write_bytes(b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60MTrk\x00\x00\x00\x04\x00\xff\x2f\x00")
    registry = ModelRegistry(tmp_path)
    registry.installer.install("diffsinger-opencpop")
    return tmp_path


def test_sing_from_midi(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadMIDI":
            node.widgets["path"] = "assets/samples/automation_cc7.mid"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4"])
    assert result.status == "completed", result.error
    assert result.outputs["n4"]["cache_id"]
