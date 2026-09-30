from __future__ import annotations

import json
from pathlib import Path

from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.registry.compliance import summarize_compliance
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
from template_fixtures import require_template
TEMPLATE = require_template("podcast-denoise")


def test_compliance_summary_flags_nc_model(tmp_path: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    registry = ModelRegistry(tmp_path)
    summary = summarize_compliance(workflow, registry)
    assert summary["workflow_title"] == "Podcast Denoise"
    assert any(row["kind"] == "model" for row in summary["license_rows"])
    assert isinstance(summary["license_rows"], list)
