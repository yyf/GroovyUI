from __future__ import annotations

import json
from pathlib import Path

from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.registry.compliance_report import build_compliance_report, render_compliance_pdf
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "podcast-denoise.groovy.json"


def test_build_compliance_report_includes_license_scan(tmp_path: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    registry = ModelRegistry(tmp_path)
    report = build_compliance_report(workflow, registry)
    assert report["workflow_title"] == "Podcast Denoise"
    assert report["license"]["agent"] == "license_scanner_v1"
    assert report["summary"]["warning_count"] >= 0
    assert report["provenance"] is None


def test_render_compliance_pdf_produces_valid_pdf(tmp_path: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    registry = ModelRegistry(tmp_path)
    report = build_compliance_report(workflow, registry)
    pdf_bytes = render_compliance_pdf(report)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500
