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
from template_fixtures import require_template
TEMPLATE = require_template("podcast-denoise")


def test_build_compliance_report_includes_license_scan(tmp_path: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    registry = ModelRegistry(tmp_path)
    report = build_compliance_report(workflow, registry)
    assert report["workflow_title"] == "Podcast Denoise"
    assert report["license"]["agent"] == "license_scanner_v1"
    assert report["summary"]["warning_count"] >= 0
    assert report["provenance"] is None
    assert report["include_authenticity"] is True


def test_render_compliance_pdf_produces_valid_pdf(tmp_path: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    registry = ModelRegistry(tmp_path)
    report = build_compliance_report(workflow, registry)
    pdf_bytes = render_compliance_pdf(report)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_render_compliance_pdf_omits_authenticity_when_disabled(tmp_path: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    registry = ModelRegistry(tmp_path)
    with_auth = build_compliance_report(
        workflow,
        registry,
        include_authenticity=True,
        authenticity={
            "overall": {
                "label": "synthetic",
                "confidence": 0.91,
                "summary": "UNIQUE_AUTH_MARKER_XYZ",
            }
        },
    )
    without_auth = build_compliance_report(workflow, registry, include_authenticity=False)
    assert without_auth["include_authenticity"] is False
    assert without_auth["authenticity"] is None

    pdf_with = render_compliance_pdf(with_auth)
    pdf_without = render_compliance_pdf(without_auth)
    assert pdf_with.startswith(b"%PDF")
    assert pdf_without.startswith(b"%PDF")
    # Compressed streams may hide titles, but payload text still differs in length when
    # the authenticity section is present.
    assert len(pdf_with) > len(pdf_without)
