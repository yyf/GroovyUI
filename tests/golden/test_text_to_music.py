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
from template_fixtures import require_template
TEMPLATE = require_template("text-to-music")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    registry = ModelRegistry(tmp_path)
    registry.installer.install("musicgen-small")
    return tmp_path


def test_text_to_music(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n3"])
    assert result.status == "completed", result.error
    assert result.outputs["n3"]["cache_id"]
