from __future__ import annotations

from typing import Any

from groovy.schema.models import Workflow


def summarize_compliance(workflow: Workflow, registry: Any) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    models_seen: set[str] = set()

    for node in workflow.nodes:
        rows.append(
            {
                "component": node.type,
                "component_id": node.id,
                "kind": "node",
                "license_spdx": "MIT",
                "commercial_ok": True,
                "attribution_required": False,
            }
        )

        model_id = node.widgets.get("model")
        if not model_id or model_id in models_seen:
            continue
        models_seen.add(str(model_id))
        manifest = registry.catalog.get(str(model_id))
        if not manifest:
            warnings.append(f"Unknown model reference: {model_id}")
            continue
        rows.append(
            {
                "component": manifest.name,
                "component_id": manifest.id,
                "kind": "model",
                "license_spdx": manifest.license.spdx,
                "commercial_ok": manifest.license.commercial_ok,
                "attribution_required": manifest.license.attribution_required,
                "task_types": manifest.task_types,
            }
        )
        if not manifest.license.commercial_ok:
            warnings.append(f"{manifest.name} is not cleared for commercial use ({manifest.license.spdx}).")

    path = workflow.metadata.title if workflow.metadata else workflow.id
    assets = [
        widget
        for node in workflow.nodes
        if node.type == "LoadAudio"
        for widget in [node.widgets.get("path")]
        if widget
    ]
    for asset in assets:
        rows.append(
            {
                "component": str(asset),
                "kind": "asset",
                "license_spdx": "user-owned",
                "commercial_ok": True,
                "attribution_required": False,
            }
        )

    return {
        "workflow_id": workflow.id,
        "workflow_title": path,
        "license_rows": rows,
        "warnings": warnings,
        "commercial_ok": all(row.get("commercial_ok", True) for row in rows if row["kind"] != "node"),
    }
