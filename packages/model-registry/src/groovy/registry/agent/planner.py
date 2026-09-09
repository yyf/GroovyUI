"""Deterministic agent plan orchestrator — fan-in recommend + workflow (+ optional license peek).

No LLM. Returns explicit action cards; never installs or patches the graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from groovy.registry.agent.license_scanner import scan_workflow_licenses
from groovy.registry.agent.recommender import recommend_models
from groovy.registry.agent.workflow_suggester import suggest_workflows
from groovy.registry.catalog import ModelCatalog
from groovy.registry.store import InstallStore
from groovy.schema.models import Workflow


def plan_agent_request(
    catalog: ModelCatalog,
    store: InstallStore,
    registry: Any,
    *,
    prompt: str,
    templates_dir: Path,
    commercial_ok: bool | None = None,
    node_type: str | None = None,
    task_type: str | None = None,
    max_models: int = 3,
    max_workflows: int = 2,
) -> dict[str, Any]:
    prompt = prompt.strip()
    if not prompt:
        return {
            "prompt": prompt,
            "actions": [],
            "notes": "Enter a task description to build a plan.",
            "agent": "plan_v1",
            "mode": "empty",
            "planner": "deterministic",
            "deterministic": True,
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
    workflows = suggest_workflows(prompt, templates_dir)

    actions: list[dict[str, Any]] = []
    tools_used = ["recommend_models", "suggest_workflows"]

    for index, item in enumerate(recommend.get("results") or []):
        model = item["model"]
        actions.append(
            {
                "type": "install_model",
                "id": f"install:{model['id']}",
                "title": f"Install {model['name']}",
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
                        "rationale": f"Pre-wire a {node} node using this model (canvas change only on click).",
                        "model_id": model["id"],
                        "node_type": node,
                        "model": model,
                        "priority": 9,
                    }
                )

    for index, item in enumerate((workflows.get("results") or [])[:max_workflows]):
        actions.append(
            {
                "type": "apply_template",
                "id": f"apply:{item['template_id']}",
                "title": f"Apply “{item['title']}”",
                "rationale": item.get("rationale") or item.get("description") or item["template_id"],
                "template_id": item["template_id"],
                "description": item.get("description") or "",
                "workflow": item["workflow"],
                "priority": 8 - index,
            }
        )

    license_preview: dict[str, Any] | None = None
    top_workflows = workflows.get("results") or []
    if top_workflows:
        try:
            wf = Workflow.model_validate(top_workflows[0]["workflow"])
            license_preview = scan_workflow_licenses(wf, registry)
            tools_used.append("license_scan")
            if not license_preview.get("scan_ok", True):
                flag_count = len(
                    [f for f in license_preview.get("flags", []) if f.get("severity") in {"error", "warning"}]
                )
                actions.append(
                    {
                        "type": "open_compliance",
                        "id": f"compliance:{top_workflows[0]['template_id']}",
                        "title": "Review licenses on suggested template",
                        "rationale": (
                            f"{flag_count} license flag(s) on “{top_workflows[0]['title']}”. "
                            "Apply the template first (or keep your graph), then open Compliance — nothing auto-swaps."
                        ),
                        "template_id": top_workflows[0]["template_id"],
                        "scan_ok": False,
                        "priority": 5,
                    }
                )
        except Exception:
            license_preview = None

    actions.sort(key=lambda a: (-int(a.get("priority", 0)), str(a.get("title", ""))))

    notes_parts = [
        "Deterministic plan (no LLM): recommend_models + suggest_workflows"
        + (" + license_scan" if "license_scan" in tools_used else "")
        + ".",
        "Install / Drop / Apply / Compliance stay explicit clicks.",
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
        "workflow_count": len(top_workflows),
        "license_preview": {
            "scan_ok": license_preview.get("scan_ok"),
            "flag_count": len(license_preview.get("flags") or []),
            "template_id": top_workflows[0]["template_id"] if top_workflows else None,
        }
        if license_preview
        else None,
        "notes": " ".join(notes_parts),
        "agent": "plan_v1",
        "mode": "plan",
        "planner": "deterministic",
        "deterministic": True,
    }
