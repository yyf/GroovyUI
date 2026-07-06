from __future__ import annotations

from typing import Any

from groovy.executor.audio import AudioBuffer
from groovy.executor.cache import CacheStore

DISCLOSURE_LABELS = {
    "human_recorded": "Contains human-recorded audio",
    "human_edited": "Contains human-edited audio",
    "ai_transformed": "Contains AI-processed or AI-transformed audio",
    "ai_generated": "Contains AI-generated audio",
    "unknown": "Audio provenance is unknown",
}


def read_provenance(cache: CacheStore, cache_id: str) -> dict[str, Any] | None:
    path = cache.cache_dir / f"{cache_id}.provenance.json"
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text())


def parent_refs(kwargs: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for value in kwargs.values():
        if isinstance(value, AudioBuffer):
            refs.append(
                {
                    "cache_id": value.id,
                    "content_hash": value.content_hash or "",
                    "source_node": value.source_node or "",
                    "source_node_type": value.source_node_type or "",
                }
            )
    return refs


def contribution_class(node_cls: type, parent_records: list[dict[str, Any]]) -> str:
    if getattr(node_cls, "PROVENANCE_PASSTHROUGH", False) and len(parent_records) == 1:
        parent_class = parent_records[0].get("contribution", {}).get("class")
        if parent_class:
            return str(parent_class)
    return str(getattr(node_cls, "PROVENANCE_CLASS", "unknown"))


def build_record(
    *,
    cache_id: str,
    content_hash: str | None,
    node_id: str,
    node_type: str,
    widgets: dict[str, Any],
    node_cls: type,
    job_id: str,
    workflow_id: str,
    groovy_version: str,
    executor_version: str,
    parent_records: list[dict[str, Any]],
    parent_refs_list: list[dict[str, str]],
) -> dict[str, Any]:
    klass = contribution_class(node_cls, parent_records)
    models: list[dict[str, str]] = []
    model_id = widgets.get("model")
    if model_id:
        models.append({"registry_id": str(model_id)})

    parents = [
        {
            "cache_id": ref["cache_id"],
            "content_hash": ref["content_hash"],
            "node_id": rec.get("node", {}).get("node_id", ref.get("source_node", "")),
            "node_type": rec.get("node", {}).get("node_type", ref.get("source_node_type", "")),
        }
        for ref, rec in zip(parent_refs_list, parent_records, strict=False)
    ]
    if len(parents) < len(parent_refs_list):
        for ref in parent_refs_list[len(parents) :]:
            parents.append(
                {
                    "cache_id": ref["cache_id"],
                    "content_hash": ref["content_hash"],
                    "node_id": ref.get("source_node", ""),
                    "node_type": ref.get("source_node_type", ""),
                }
            )

    from datetime import UTC, datetime

    return {
        "schema_version": "1.0.0",
        "cache_id": cache_id,
        "content_hash": content_hash,
        "created_at": datetime.now(UTC).isoformat(),
        "contribution": {
            "class": klass,
            "disclosure_label": DISCLOSURE_LABELS.get(klass, DISCLOSURE_LABELS["unknown"]),
        },
        "origin": {
            "type": "render",
            "job_id": job_id,
            "workflow_id": workflow_id,
            "groovy_version": groovy_version,
            "executor_version": executor_version,
        },
        "node": {"node_id": node_id, "node_type": node_type, "widgets_redacted": widgets},
        "models": models,
        "parents": parents,
    }


def build_lineage_chain(cache: CacheStore, cache_id: str) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_id: str | None = cache_id
    while current_id and current_id not in seen:
        seen.add(current_id)
        record = read_provenance(cache, current_id)
        if not record:
            break
        chain.append(record)
        parents = record.get("parents") or []
        current_id = parents[0]["cache_id"] if parents else None
    return chain


def disclosure_summary(chain: list[dict[str, Any]]) -> str:
    if not chain:
        return "No provenance data available. Render the workflow first."
    classes = {item.get("contribution", {}).get("class", "unknown") for item in chain}
    models = []
    for item in chain:
        for model in item.get("models") or []:
            mid = model.get("registry_id") or model.get("id")
            if mid:
                models.append(str(mid))
    parts: list[str] = []
    if "ai_generated" in classes:
        parts.append("This output includes AI-generated audio")
    if "ai_transformed" in classes:
        parts.append("AI processing was applied to transform the source material")
    if "human_recorded" in classes:
        parts.append("Human-recorded source material is included")
    if "unknown" in classes:
        parts.append("Some upstream provenance is unknown")
    if models:
        parts.append(f"Models used: {', '.join(dict.fromkeys(models))}")
    return ". ".join(parts) + "." if parts else "Human-edited audio workflow."


def summarize_workflow_outputs(
    cache: CacheStore,
    outputs: dict[str, dict[str, Any]],
    *,
    target_node_id: str | None = None,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for node_id, output in outputs.items():
        cache_id = output.get("cache_id")
        if not cache_id:
            continue
        chain = build_lineage_chain(cache, str(cache_id))
        entries.append(
            {
                "node_id": node_id,
                "cache_id": cache_id,
                "chain": chain,
                "disclosure": disclosure_summary(chain),
            }
        )

    focus = target_node_id
    if not focus:
        focus = next((e["node_id"] for e in entries), None)
    focus_entry = next((e for e in entries if e["node_id"] == focus), None)
    return {
        "entries": entries,
        "focus_node_id": focus,
        "focus_disclosure": focus_entry["disclosure"] if focus_entry else disclosure_summary([]),
        "contains_ai": any(
            item.get("contribution", {}).get("class") in {"ai_transformed", "ai_generated"}
            for entry in entries
            for item in entry["chain"]
        ),
    }
