from __future__ import annotations

from typing import Any

from groovy.registry.workflow_models import iter_node_model_refs
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
                # Built-in GroovyUI nodes ship under the app license (Apache-2.0), not
                # model/weights SPDX — those appear as separate kind=model rows.
                "license_spdx": "Apache-2.0",
                "commercial_ok": True,
                "attribution_required": False,
            }
        )

        for ref in iter_node_model_refs(node):
            model_id = ref["model_id"]
            if model_id in models_seen:
                continue
            models_seen.add(model_id)
            role = ref["role"]
            manifest = registry.catalog.get(model_id)
            if not manifest:
                label = "LoRA adapter" if role == "adapter" else "model"
                warnings.append(f"Unknown {label} reference: {model_id}")
                rows.append(
                    {
                        "component": model_id,
                        "component_id": model_id,
                        "kind": "model",
                        "role": role,
                        "license_spdx": "unknown",
                        "commercial_ok": False,
                        "attribution_required": True,
                    }
                )
                continue
            rows.append(
                {
                    "component": (
                        f"{manifest.name} (LoRA)" if role == "adapter" else manifest.name
                    ),
                    "component_id": manifest.id,
                    "kind": "model",
                    "role": role,
                    "license_spdx": manifest.license.spdx,
                    "commercial_ok": manifest.license.commercial_ok,
                    "attribution_required": manifest.license.attribution_required,
                    "task_types": manifest.task_types,
                }
            )
            if not manifest.license.commercial_ok:
                kind = "LoRA adapter" if role == "adapter" else "model"
                warnings.append(
                    f"{manifest.name} ({kind}) is not cleared for commercial use "
                    f"({manifest.license.spdx})."
                )

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
