"""Deterministic model Plan for Model Browser — recommend models for a task.

No LLM. Returns install / drop-node action cards; never installs or patches the graph.
Full graph drafting lives in Generate (⌘G), not here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from groovy.registry.agent.recommender import recommend_models
from groovy.registry.catalog import ModelCatalog
from groovy.registry.store import InstallStore


def plan_agent_request(
    catalog: ModelCatalog,
    store: InstallStore,
    registry: Any,
    *,
    prompt: str,
    templates_dir: Path | None = None,
    commercial_ok: bool | None = None,
    node_type: str | None = None,
    task_type: str | None = None,
    max_models: int = 5,
    max_workflows: int = 0,
) -> dict[str, Any]:
    """Plan which local published models fit the task (deterministic).

    ``templates_dir`` / ``max_workflows`` are ignored — kept for call-site stability.
    Use Generate for workflow/template composition.
    """
    del registry, templates_dir, max_workflows
    prompt = prompt.strip()
    if not prompt:
        return {
            "prompt": prompt,
            "actions": [],
            "notes": "Enter a task description to plan which models to use.",
            "agent": "plan_models_v1",
            "mode": "empty",
            "planner": "deterministic",
            "deterministic": True,
            "scope": "models",
        }

    recommend = recommend_models(
        catalog,
        store,
        prompt=prompt,
        commercial_ok=commercial_ok,
        task_type=task_type,
        node_type=node_type,
        max_results=max_models,
    )

    actions: list[dict[str, Any]] = []
    tools_used = ["recommend_models"]

    for index, item in enumerate(recommend.get("results") or []):
        model = item["model"]
        actions.append(
            {
                "type": "install_model",
                "id": f"install:{model['id']}",
                "title": f"Install {model['name']}",
                "summary": model.get("name") or model["id"],
                "rationale": item.get("rationale") or model.get("description") or model["id"],
                "model_id": model["id"],
                "model": model,
                "priority": 10 - index,
            }
        )
        if index == 0:
            node = (model.get("compatible_nodes") or [None])[0]
            if node:
                actions.append(
                    {
                        "type": "drop_node",
                        "id": f"drop:{model['id']}:{node}",
                        "title": f"Drop {node} with {model['name']}",
                        "summary": f"Drop {node}",
                        "rationale": f"Pre-wire a {node} node using this model (canvas change only on click).",
                        "model_id": model["id"],
                        "node_type": node,
                        "model": model,
                        "priority": 9,
                    }
                )

    actions.sort(key=lambda a: (-int(a.get("priority", 0)), str(a.get("title", ""))))

    notes_parts = [
        "Model Plan (deterministic): recommend published registry models for this task.",
        "Install / Drop stay explicit clicks. For a full graph blueprint, use Generate (⌘G).",
    ]
    if recommend.get("inferred_task"):
        notes_parts.append(f"Inferred task: {recommend['inferred_task']}.")

    return {
        "prompt": prompt,
        "inferred_task": recommend.get("inferred_task"),
        "commercial_ok": recommend.get("commercial_ok"),
        "node_type": node_type,
        "tools_used": tools_used,
        "actions": actions,
        "recommend_count": len(recommend.get("results") or []),
        "workflow_count": 0,
        "license_preview": None,
        "notes": " ".join(notes_parts),
        "agent": "plan_models_v1",
        "mode": "plan",
        "planner": "deterministic",
        "deterministic": True,
        "scope": "models",
    }
