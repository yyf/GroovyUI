"""Compliance report aggregation and PDF export (UX-7 handoff deliverable)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF

from groovy.registry.agent.license_scanner import scan_workflow_licenses
from groovy.schema.models import Workflow

_DISCLAIMER = (
    "This report is informational only and does not constitute legal advice. "
    "Commercial use of AI model outputs depends on each model's license and your jurisdiction. "
    "Verify all licenses before shipping client work."
)


def build_compliance_report(
    workflow: Workflow,
    registry: Any,
    *,
    provenance: dict[str, Any] | None = None,
    authenticity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    license_scan = scan_workflow_licenses(workflow, registry)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_id": workflow.id,
        "workflow_title": license_scan.get("workflow_title") or workflow.id,
        "license": license_scan,
        "provenance": provenance,
        "authenticity": authenticity,
        "summary": {
            "commercial_ok": license_scan.get("commercial_ok", True),
            "scan_ok": license_scan.get("scan_ok", True),
            "contains_ai": bool(provenance and provenance.get("contains_ai")),
            "warning_count": len(license_scan.get("warnings", [])),
            "flag_count": len(license_scan.get("flags", [])),
        },
    }


def render_compliance_pdf(report: dict[str, Any]) -> bytes:
    pdf = _CompliancePdf()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    title = str(report.get("workflow_title") or "Untitled workflow")
    pdf.section_title("GroovyUI Compliance Report")
    pdf.body_text(f"Workflow: {title}")
    pdf.body_text(f"Workflow ID: {report.get('workflow_id', '')}")
    pdf.body_text(f"Generated: {report.get('generated_at', '')}")

    summary = report.get("summary") or {}
    pdf.section_title("Executive summary")
    pdf.bullet(f"Commercial use cleared: {'Yes' if summary.get('commercial_ok') else 'No'}")
    pdf.bullet(f"License scan passed: {'Yes' if summary.get('scan_ok') else 'No'}")
    pdf.bullet(f"Chain contains AI output: {'Yes' if summary.get('contains_ai') else 'No'}")
    pdf.bullet(f"Warnings: {summary.get('warning_count', 0)}")
    pdf.bullet(f"Flags: {summary.get('flag_count', 0)}")

    license_data = report.get("license") or {}
    warnings = license_data.get("warnings") or []
    flags = license_data.get("flags") or []
    if warnings or flags:
        pdf.section_title("Warnings and flags")
        for warning in warnings:
            pdf.bullet(str(warning))
        for flag in flags:
            pdf.bullet(f"{flag.get('node_id')} ({flag.get('code')}): {flag.get('message')}")

    rows = license_data.get("license_rows") or []
    if rows:
        pdf.section_title("License summary")
        pdf.table(
            ["Component", "Kind", "License", "Commercial"],
            [
                [
                    str(row.get("component", "")),
                    str(row.get("kind", "")),
                    str(row.get("license_spdx", "")),
                    "Yes" if row.get("commercial_ok") else "No",
                ]
                for row in rows
            ],
        )

    swaps = license_data.get("swap_suggestions") or []
    if swaps:
        pdf.section_title("Commercial-safe alternatives")
        for swap in swaps:
            pdf.body_text(
                f"{swap.get('node_id')} ({swap.get('node_type')}): "
                f"{swap.get('current_model_id')} ({swap.get('current_license')})"
            )
            for alt in swap.get("alternatives") or []:
                pdf.bullet(f"{alt.get('name')} — {alt.get('license_spdx')} ({alt.get('model_id')})")

    provenance = report.get("provenance")
    if provenance:
        pdf.section_title("Provenance")
        disclosure = provenance.get("focus_disclosure")
        if disclosure:
            pdf.body_text(str(disclosure))
        entries = provenance.get("entries") or []
        for entry in entries:
            pdf.body_text(f"Output node: {entry.get('node_id')} (cache {str(entry.get('cache_id', ''))[:8]}…)")
            for step in entry.get("chain") or []:
                node = step.get("node") or {}
                contrib = step.get("contribution") or {}
                pdf.bullet(
                    f"{node.get('node_type', 'unknown')} — {contrib.get('class', 'unknown')}"
                )
    else:
        pdf.section_title("Provenance")
        pdf.body_text("No render outputs supplied. Run the workflow to include provenance lineage.")

    authenticity = report.get("authenticity")
    if authenticity:
        pdf.section_title("Authenticity")
        overall = authenticity.get("overall") or {}
        pdf.body_text(f"Label: {overall.get('label', 'unknown')}")
        if overall.get("confidence") is not None:
            pdf.body_text(f"Confidence: {round(float(overall['confidence']) * 100)}%")
        if overall.get("summary"):
            pdf.body_text(str(overall["summary"]))
        prov_check = authenticity.get("provenance_check")
        if prov_check:
            pdf.body_text(
                f"Provenance check: {prov_check.get('status')} "
                f"(sidecar {'found' if prov_check.get('sidecar_found') else 'missing'})"
            )
        ml_det = authenticity.get("ml_detection")
        if ml_det:
            pdf.body_text(
                f"ML detection ({ml_det.get('model_id')}): "
                f"spoof {round(float(ml_det.get('spoof_score', 0)) * 100)}%"
            )
        pdf.body_text("Indicators only — not legal proof.")
    else:
        pdf.section_title("Authenticity")
        pdf.body_text("No authenticity report available for this workflow.")

    pdf.section_title("Disclaimer")
    pdf.body_text(_DISCLAIMER)
    return bytes(pdf.output())


class _CompliancePdf(FPDF):
    def __init__(self) -> None:
        super().__init__()
        self.set_margins(18, 18, 18)

    def _content_width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def section_title(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.ln(4)
        self.set_font("Helvetica", "B", 12)
        self.multi_cell(self._content_width(), 7, _safe_text(text))
        self.set_font("Helvetica", "", 10)
        self.ln(2)

    def body_text(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.multi_cell(self._content_width(), 5, _safe_text(text))
        self.ln(1)

    def bullet(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.multi_cell(self._content_width(), 5, _safe_text(f"- {text}"))

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        col_count = len(headers)
        width = self._content_width() / col_count
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 9)
        for header in headers:
            self.cell(width, 6, _safe_text(header), border=1)
        self.ln()
        self.set_font("Helvetica", "", 9)
        for row in rows:
            self.set_x(self.l_margin)
            for cell in row:
                self.cell(width, 6, _safe_text(cell)[:48], border=1)
            self.ln()
        self.ln(2)


def _safe_text(value: str) -> str:
    return value.encode("latin-1", errors="replace").decode("latin-1")
