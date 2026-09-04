"""License scanner agent — commercial-use flags and model swap suggestions."""

from __future__ import annotations

from typing import Any

from groovy.registry.catalog import ModelCatalog
from groovy.registry.compliance import summarize_compliance
from groovy.registry.models import ModelManifest
from groovy.registry.preflight import estimate_workflow_preflight
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
                    "explain": (
                        f"Node {node.id} ({node.type}) points at `{model_id}`, which is not in the "
                        "local registry. Install or pick a published model before commercial review."
                    ),
                }
            )
            continue
        spdx_upper = manifest.license.spdx.upper()
        share_alike = "-SA-" in spdx_upper or spdx_upper.endswith("-SA")
        if manifest.license.attribution_required:
            flags.append(
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "severity": "info",
                    "code": "ATTRIBUTION_REQUIRED",
                    "message": f"{manifest.name} requires attribution ({manifest.license.spdx}).",
                    "explain": (
                        f"Keep {manifest.name} if you can credit the author in deliverables. "
                        "Apply a commercial-OK swap below only when you need attribution-free shipping."
                    ),
                    "model_id": manifest.id,
                }
            )
        if share_alike:
            flags.append(
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "severity": "warning",
                    "code": "SHARE_ALIKE",
                    "message": f"{manifest.name} has share-alike obligations ({manifest.license.spdx}).",
                    "explain": (
                        f"{manifest.name} may require sharing derivatives under similar terms. "
                        "Swap to a permissive commercial-OK model if that does not fit your release."
                    ),
                    "model_id": manifest.id,
                }
            )
        if not manifest.license.commercial_ok:
            flags.append(
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "severity": "error",
                    "code": "NC_MODEL",
                    "message": (
                        f"{manifest.name} ({manifest.license.spdx}) is not cleared for commercial use."
                    ),
                    "explain": (
                        f"`{manifest.id}` on {node.type} is fine for exploration, but not for paid/"
                        "client deliverables under the catalog license flag. Choose Apply on a "
                        "socket-compatible alternative (install still required), or browse Find models "
                        "with Commercial only."
                    ),
                    "model_id": manifest.id,
                }
            )
        needs_permissive_alternative = (
            not manifest.license.commercial_ok
            or manifest.license.attribution_required
            or share_alike
        )
        if not needs_permissive_alternative:
            continue
        alternatives = _commercial_alternatives(registry.catalog, manifest, node.type)
        task = manifest.task_types[0] if manifest.task_types else node.type
        if alternatives:
            swap_suggestions.append(
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "widget": "model",
                    "current_model_id": manifest.id,
                    "current_license": manifest.license.spdx,
                    "alternatives": alternatives,
                    "rationale": f"Commercial-friendly alternatives for {task}",
                    "explain": (
                        f"These models list `{node.type}` in compatible_nodes and are marked "
                        "commercial_ok. Apply only updates the widget — you still Install from "
                        "Model Browser before Render."
                    ),
                }
            )
        else:
            swap_suggestions.append(
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "widget": "model",
                    "current_model_id": manifest.id,
                    "current_license": manifest.license.spdx,
                    "alternatives": [],
                    "rationale": f"No socket-safe commercial peer for {node.type}",
                    "explain": (
                        f"No published commercial-OK model currently lists `{node.type}`. "
                        "Open Find models with Commercial only to search the catalog, or keep "
                        "this node for non-commercial exploration."
                    ),
                    "browse_hint": {
                        "node_type": node.type,
                        "commercial_only": True,
                        "query": task,
                        "mode": "recommend",
                    },
                }
            )

    optimization_swaps: list[dict[str, Any]] = []
    optimized_nodes = {
        swap["node_id"] for swap in swap_suggestions if swap.get("alternatives")
    }
    for swap in swap_suggestions:
        if not swap["alternatives"]:
            continue
        preferred = swap["alternatives"][0]
        optimization_swaps.append(
            {
                "node_id": swap["node_id"],
                "node_type": swap["node_type"],
                "from_model_id": swap["current_model_id"],
                "to_model_id": preferred["model_id"],
                "to_model_name": preferred["name"],
                "license_spdx": preferred["license_spdx"],
                "rationale": preferred["rationale"],
            }
        )
    unresolved = [
        {
            "node_id": flag["node_id"],
            "node_type": flag["node_type"],
            "model_id": flag.get("model_id"),
            "message": flag["message"],
            "explain": flag.get("explain"),
            "next_step": (
                "Open Model Browser → Find models with Commercial only, or keep for non-commercial use."
            ),
        }
        for flag in flags
        if flag["code"] in {"NC_MODEL", "UNKNOWN_MODEL", "SHARE_ALIKE"}
        and flag["node_id"] not in optimized_nodes
    ]

    return {
        **summary,
        "flags": flags,
        "swap_suggestions": swap_suggestions,
        "optimization_plan": {
            "intent": "commercial",
            "swaps": optimization_swaps,
            "unresolved": unresolved,
            "can_optimize": bool(optimization_swaps) and not unresolved,
        },
        "preflight": estimate_workflow_preflight(workflow, registry),
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
    """Return commercial-OK models that are socket-compatible with *node_type*.

    Never fall back to task-only peers that do not list the node type in
    ``compatible_nodes`` — those swaps would silently break the graph.
    """
    task = current.task_types[0] if current.task_types else None
    candidates = catalog.search("", task_type=task, commercial_ok=True, node_type=node_type)
    ranked: list[tuple[int, ModelManifest]] = []
    for model in candidates:
        if model.id == current.id:
            continue
        if node_type not in model.compatible_nodes:
            continue
        score = 0
        if set(model.task_types) & set(current.task_types):
            score += 3
        if model.vram_gb_estimate <= current.vram_gb_estimate:
            score += 1
        if not model.license.attribution_required:
            score += 3
        spdx_upper = model.license.spdx.upper()
        if "-SA-" not in spdx_upper and not spdx_upper.endswith("-SA"):
            score += 2
        if model.license.confidence >= 0.8:
            score += 1
        ranked.append((score, model))
    ranked.sort(key=lambda item: (-item[0], item[1].name.lower()))
    return [
        {
            "model_id": model.id,
            "name": model.name,
            "license_spdx": model.license.spdx,
            "attribution_required": model.license.attribution_required,
            "license_confidence": model.license.confidence,
            "vram_gb_estimate": model.vram_gb_estimate,
            "download_size_mb_estimate": model.download_size_mb_estimate,
            "task_types": model.task_types,
            "rationale": (
                f"{model.license.spdx} — commercial OK"
                + (f" · ~{model.vram_gb_estimate:g} GB VRAM" if model.vram_gb_estimate else "")
            ),
        }
        for _, model in ranked[:limit]
    ]
