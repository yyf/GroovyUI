from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from groovy.executor.audio import AudioBuffer
from groovy.executor.cache import CacheStore

DISCLOSURE_LABELS = {
    "human_recorded": "Contains human-recorded audio",
    "human_edited": "Contains human-edited audio",
    "ai_transformed": "Contains AI-processed or AI-transformed audio",
    "ai_generated": "Contains AI-generated audio",
    "mixed": "Contains a mix of human and AI audio contributions",
    "unknown": "Audio provenance is unknown",
}

PROMPT_WIDGET_KEYS = {
    "prompt",
    "negative_prompt",
    "text",
    "lyrics",
    "style_prompt",
    "description_prompt",
}
SECRET_KEY_MARKERS = (
    "api_key",
    "apikey",
    "auth",
    "credential",
    "password",
    "secret",
    "token",
)


def read_provenance(cache: CacheStore, cache_id: str) -> dict[str, Any] | None:
    path = cache.cache_dir / f"{cache_id}.provenance.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _looks_absolute_path(value: str) -> bool:
    return Path(value).expanduser().is_absolute() or bool(
        re.match(r"^[A-Za-z]:[\\/]", value)
    )


def _sanitize_value(key: str, value: Any) -> Any:
    normalized = key.strip().lower()
    if any(marker in normalized for marker in SECRET_KEY_MARKERS):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _sanitize_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(key, item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(key, item) for item in value]
    if isinstance(value, str) and _looks_absolute_path(value):
        return {
            "path_redacted": True,
            "basename": Path(value).name,
        }
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def sanitize_widgets(
    widgets: dict[str, Any],
    *,
    prompt_policy: str = "redacted",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Remove secrets/absolute paths and apply the export prompt policy."""
    policy = prompt_policy.strip().lower()
    if policy not in {"full", "redacted", "omit"}:
        policy = "redacted"
    sanitized: dict[str, Any] = {}
    prompts: list[dict[str, Any]] = []
    for key, value in widgets.items():
        normalized = key.strip().lower()
        if normalized in PROMPT_WIDGET_KEYS and isinstance(value, str):
            prompt: dict[str, Any] = {"name": key, "policy": policy}
            if policy == "full":
                prompt["text"] = value
                sanitized[key] = value
            elif policy == "redacted":
                digest = _sha256_text(value)
                prompt["sha256"] = digest
                sanitized[key] = {"redacted": True, "sha256": digest}
            else:
                sanitized[key] = "[omitted]"
            prompts.append(prompt)
            continue
        sanitized[key] = _sanitize_value(key, value)
    return sanitized, {
        "prompt_policy": policy,
        "prompts_redacted": policy != "full",
        "prompts": prompts,
    }


def apply_record_integrity(record: dict[str, Any]) -> dict[str, Any]:
    """Attach a deterministic hash over the record, excluding integrity itself."""
    unsigned = {key: value for key, value in record.items() if key != "integrity"}
    canonical = json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    parent_hashes = [
        parent["provenance_hash"]
        for parent in record.get("parents", [])
        if parent.get("provenance_hash")
    ]
    result = dict(unsigned)
    result["integrity"] = {
        "algorithm": "sha256",
        "record_hash": _sha256_text(canonical),
        "parent_record_hashes": parent_hashes,
        "signed": False,
    }
    return result


def verify_record_integrity(record: dict[str, Any]) -> bool | None:
    expected = record.get("integrity", {}).get("record_hash")
    if not expected:
        return None
    return apply_record_integrity(record)["integrity"]["record_hash"] == expected


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
    workflow_title: str = "",
    workflow_hash: str = "",
    model_metadata: dict[str, Any] | None = None,
    prompt_policy: str = "redacted",
) -> dict[str, Any]:
    klass = contribution_class(node_cls, parent_records)
    models: list[dict[str, Any]] = []
    model_id = widgets.get("model")
    if model_id:
        model = {"registry_id": str(model_id)}
        if model_metadata:
            model.update(model_metadata)
            model["registry_id"] = str(model_id)
        models.append(model)

    parents = [
        {
            "cache_id": ref["cache_id"],
            "content_hash": ref["content_hash"],
            "node_id": rec.get("node", {}).get("node_id", ref.get("source_node", "")),
            "node_type": rec.get("node", {}).get("node_type", ref.get("source_node_type", "")),
            "provenance_hash": rec.get("integrity", {}).get("record_hash"),
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
                    "provenance_hash": None,
                }
            )

    from datetime import UTC, datetime

    sanitized_widgets, conditioning = sanitize_widgets(
        widgets, prompt_policy=prompt_policy
    )
    seed = widgets.get("seed")
    record = {
        "schema_version": "1.1.0",
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
            "workflow_title": workflow_title,
            "workflow_hash": workflow_hash,
            "groovy_version": groovy_version,
            "executor_version": executor_version,
        },
        "node": {
            "node_id": node_id,
            "node_type": node_type,
            "widgets_redacted": sanitized_widgets,
            "seed": seed,
            "deterministic": bool(getattr(node_cls, "DETERMINISTIC", True)),
        },
        "models": models,
        "conditioning": conditioning,
        "parents": parents,
    }
    return apply_record_integrity(record)


def build_lineage_graph(cache: CacheStore, cache_id: str) -> dict[str, Any]:
    """Build a compact, deduplicated DAG for a sidecar export."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    seen: set[str] = set()
    pending = [cache_id]
    while pending:
        current_id = pending.pop()
        if current_id in seen:
            continue
        seen.add(current_id)
        record = read_provenance(cache, current_id)
        if not record:
            continue
        nodes.append(
            {
                "cache_id": current_id,
                "content_hash": record.get("content_hash"),
                "node": record.get("node", {}),
                "contribution": record.get("contribution", {}),
                "models": record.get("models", []),
                "record_hash": record.get("integrity", {}).get("record_hash"),
            }
        )
        for parent in record.get("parents") or []:
            parent_id = str(parent.get("cache_id") or "")
            if not parent_id:
                continue
            edges.append({"from_cache_id": parent_id, "to_cache_id": current_id})
            pending.append(parent_id)
    return {"root_cache_id": cache_id, "nodes": nodes, "edges": edges}


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
