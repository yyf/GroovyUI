from __future__ import annotations

from typing import Any

from groovy.registry.installer import model_install_complete
from groovy.registry.models import ModelManifest
from groovy.registry.store import InstallStore
from groovy.schema.models import Workflow


def missing_models_for_workflow(
    workflow: Workflow,
    catalog: Any,
    store: InstallStore,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    missing: list[dict[str, Any]] = []
    for node in workflow.nodes:
        model_id = node.widgets.get("model")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        model_id = model_id.strip()
        if model_id in seen:
            continue
        seen.add(model_id)

        manifest: ModelManifest | None = catalog.get(model_id)
        state = store.get(model_id)
        if manifest is None:
            missing.append(
                {
                    "model_id": model_id,
                    "name": model_id,
                    "status": "unknown",
                    "reason": "unknown",
                    "node_ids": [node.id],
                }
            )
            continue

        if model_install_complete(manifest, state):
            continue

        reason = "not_installed" if state.status != "ready" else "inference_not_ready"
        missing.append(
            {
                "model_id": model_id,
                "name": manifest.name,
                "status": state.status,
                "reason": reason,
                "dev_stub": manifest.install.dev_stub,
                "node_ids": [n.id for n in workflow.nodes if n.widgets.get("model") == model_id],
                "compatible_nodes": manifest.compatible_nodes,
            }
        )
    return missing
