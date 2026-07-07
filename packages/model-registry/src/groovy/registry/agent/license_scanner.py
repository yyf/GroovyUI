"""License scanner agent — commercial-use flags and model swap suggestions (Phase 2)."""

from __future__ import annotations

from typing import Any

from groovy.registry.catalog import ModelCatalog
from groovy.registry.compliance import summarize_compliance
from groovy.registry.models import ModelManifest
from groovy.schema.models import Workflow


def scan_workflow_licenses(workflow: Workflow, registry: Any) -> dict[str, Any]:
    summary = summarize_compliance(workflow, registry)
    flags: list[dict[str, Any]] = []
    swap_suggestions: list[dict[str, Any]] = []

    for node in workflow.nodes:
        model_id = node.widgets.get("model")
        if not model_id:
            continue
        manifest = registry.catalog.get(str(model_id))
        if not manifest:
            flags.append(
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "severity": "warning",
                    "code": "UNKNOWN_MODEL",
                    "message": f"Unknown model reference: {model_id}",
                }
            )
            continue
        if manifest.license.commercial_ok:
            continue

        flags.append(
            {
                "node_id": node.id,
                "node_type": node.type,
                "severity": "error",
                "code": "NC_MODEL",
                "message": (
                    f"{manifest.name} ({manifest.license.spdx}) is not cleared for commercial use."
                ),
                "model_id": manifest.id,
            }
        )
        alternatives = _commercial_alternatives(registry.catalog, manifest, node.type)
        if alternatives:
            swap_suggestions.append(
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "widget": "model",
                    "current_model_id": manifest.id,
                    "current_license": manifest.license.spdx,
                    "alternatives": alternatives,
                    "rationale": f"Commercial-friendly alternatives for {manifest.task_types[0]}",
                }
            )

    return {
        **summary,
        "flags": flags,
        "swap_suggestions": swap_suggestions,
        "scan_ok": len([f for f in flags if f["severity"] == "error"]) == 0,
        "agent": "license_scanner_v1",
    }


def _commercial_alternatives(
    catalog: ModelCatalog,
    current: ModelManifest,
    node_type: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    task = current.task_types[0] if current.task_types else None
    candidates = catalog.search("", task_type=task, commercial_ok=True, node_type=node_type)
    if not candidates and task:
        candidates = catalog.search("", task_type=task, commercial_ok=True)
    ranked: list[tuple[int, ModelManifest]] = []
    for model in candidates:
        if model.id == current.id:
            continue
        score = 0
        if node_type in model.compatible_nodes:
            score += 4
        if set(model.task_types) & set(current.task_types):
            score += 3
        if model.vram_gb_estimate <= current.vram_gb_estimate:
            score += 1
        ranked.append((score, model))
    ranked.sort(key=lambda item: (-item[0], item[1].name.lower()))
    return [
        {
            "model_id": model.id,
            "name": model.name,
            "license_spdx": model.license.spdx,
            "task_types": model.task_types,
            "rationale": f"{model.license.spdx} — commercial OK",
        }
        for _, model in ranked[:limit]
    ]
