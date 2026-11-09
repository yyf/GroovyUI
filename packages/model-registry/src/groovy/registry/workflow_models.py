from __future__ import annotations

from typing import Any, Iterable, Literal

from groovy.registry.installer import model_install_complete
from groovy.registry.models import ModelManifest
from groovy.registry.store import InstallStore
from groovy.schema.models import NodeInstance, Workflow

ModelRefRole = Literal["base", "adapter"]


def iter_node_model_refs(node: NodeInstance) -> list[dict[str, str]]:
    """Base ``model`` widget plus optional ``lora`` adapter widget on AI nodes."""
    refs: list[dict[str, str]] = []
    model_id = node.widgets.get("model")
    if isinstance(model_id, str) and model_id.strip():
        refs.append(
            {
                "node_id": node.id,
                "node_type": node.type,
                "widget": "model",
                "model_id": model_id.strip(),
                "role": "base",
            }
        )
    lora_id = node.widgets.get("lora")
    if isinstance(lora_id, str) and lora_id.strip():
        refs.append(
            {
                "node_id": node.id,
                "node_type": node.type,
                "widget": "lora",
                "model_id": lora_id.strip(),
                "role": "adapter",
            }
        )
    return refs


def iter_workflow_model_refs(workflow: Workflow) -> Iterable[dict[str, str]]:
    for node in workflow.nodes:
        yield from iter_node_model_refs(node)


def unique_workflow_model_ids(workflow: Workflow) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for ref in iter_workflow_model_refs(workflow):
        model_id = ref["model_id"]
        if model_id in seen:
            continue
        seen.add(model_id)
        ordered.append(model_id)
    return ordered


def _node_ids_for_model(workflow: Workflow, model_id: str) -> list[str]:
    ids: list[str] = []
    for ref in iter_workflow_model_refs(workflow):
        if ref["model_id"] == model_id and ref["node_id"] not in ids:
            ids.append(ref["node_id"])
    return ids


def missing_models_for_workflow(
    workflow: Workflow,
    catalog: Any,
    store: InstallStore,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    missing: list[dict[str, Any]] = []
    for ref in iter_workflow_model_refs(workflow):
        model_id = ref["model_id"]
        if model_id in seen:
            continue
        seen.add(model_id)

        manifest: ModelManifest | None = catalog.get(model_id)
        state = store.get(model_id)
        if manifest is None:
            # Hub org/name or local path adapters are still disclosed, but not installable
            # as catalog cards — skip install queue for non-registry ids with a slash/path.
            if ref["role"] == "adapter" and ("/" in model_id or model_id.startswith(".")):
                continue
            missing.append(
                {
                    "model_id": model_id,
                    "name": model_id,
                    "status": "unknown",
                    "reason": "unknown",
                    "role": ref["role"],
                    "node_ids": _node_ids_for_model(workflow, model_id),
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
                "role": ref["role"],
                "dev_stub": manifest.install.dev_stub,
                "node_ids": _node_ids_for_model(workflow, model_id),
                "compatible_nodes": manifest.compatible_nodes,
            }
        )
    return missing
