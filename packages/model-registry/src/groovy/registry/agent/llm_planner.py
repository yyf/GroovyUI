"""Non-deterministic Plan via Anthropic Claude (BYOK).

Composes audio-graph blueprints from the user prompt. Does **not** send the
local model/template catalog to Claude. Unknown node types are kept in the
draft and flagged for the UI. Apply stays an explicit user click.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from typing import Any

from groovy.schema.models import Workflow

DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
SOCKET_TYPES = frozenset({"AUDIO", "MIDI", "TEXT", "STRING", "FLOAT", "CONTROL", "OBA", "SAMPLE_CHECK", "AUTHENTICITY"})
# Shipped demo clip — same default as studio LoadAudio / sampleDefaults.ts
DEFAULT_PLAN_LOAD_AUDIO_PATH = "assets/samples/podcast_denoise_demo.wav"


def _normalize_model_token(value: str) -> str:
    text = value.strip().lower()
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    if text.endswith(".git"):
        text = text[:-4]
    return re.sub(r"[^a-z0-9]+", "", text)


def _catalog_published(catalog: Any) -> list[Any]:
    if catalog is None:
        return []
    try:
        models = list(catalog.all())
    except Exception:
        return []
    return [m for m in models if getattr(m, "status", "") == "published"]


def resolve_local_model_id(
    suggested: str,
    *,
    node_type: str,
    catalog: Any,
    node_model_defaults: dict[str, str] | None = None,
    commercial_ok: bool | None = None,
) -> tuple[str | None, str]:
    """Map a Claude/public model string to a published local registry id."""
    suggested = (suggested or "").strip()
    defaults = node_model_defaults or {}
    published = _catalog_published(catalog)

    def _ok(model: Any) -> bool:
        if commercial_ok and not getattr(getattr(model, "license", None), "commercial_ok", False):
            return False
        nodes = list(getattr(model, "compatible_nodes", None) or [])
        if node_type and nodes and node_type not in nodes:
            return False
        return True

    if not suggested:
        default = defaults.get(node_type)
        if default:
            return default, "node_default"
        for model in published:
            if _ok(model):
                return str(model.id), "compatible_fallback"
        return None, "unresolved"

    if catalog is not None:
        exact = catalog.get(suggested)
        if exact is not None and getattr(exact, "status", "") == "published":
            return str(exact.id), "exact_id"

    basename = suggested.rsplit("/", 1)[-1].strip()
    if basename and basename != suggested and catalog is not None:
        by_base = catalog.get(basename)
        if by_base is not None and getattr(by_base, "status", "") == "published":
            return str(by_base.id), "basename_id"

    needle = _normalize_model_token(suggested)
    basename_needle = _normalize_model_token(basename) if basename else needle
    best: tuple[int, str] | None = None
    for model in published:
        if not _ok(model):
            continue
        mid = str(model.id)
        score = 0
        mid_n = _normalize_model_token(mid)
        name_n = _normalize_model_token(str(getattr(model, "name", "") or ""))
        tags_n = _normalize_model_token(" ".join(getattr(model, "tags", None) or []))
        if mid_n == needle or mid_n == basename_needle:
            score = 100
        elif needle and needle in mid_n:
            score = 80
        elif basename_needle and basename_needle in mid_n:
            score = 75
        elif needle and (needle in name_n or needle in tags_n):
            score = 55
        elif basename_needle and (basename_needle in name_n or basename_needle in tags_n):
            score = 50
        # Common family aliases (public name → local wedge)
        aliases = {
            "xtts": "kokoro",
            "xttsv2": "kokoro",
            "coqui": "kokoro",
            "whisper": "whisper",
            "demucs": "demucs",
            "deepfilter": "deepfilter",
            "rvc": "rvc",
            "musicgen": "musicgen",
            "basicpitch": "basicpitch",
        }
        for key, local_hint in aliases.items():
            if key in needle and local_hint in mid_n:
                score = max(score, 70)
        if score <= 0:
            continue
        if node_type and node_type in list(getattr(model, "compatible_nodes", None) or []):
            score += 15
        if best is None or score > best[0]:
            best = (score, mid)
    if best and best[0] >= 50:
        return best[1], "fuzzy_match"

    default = defaults.get(node_type)
    if default:
        return default, "node_default"
    for model in published:
        if _ok(model):
            return str(model.id), "compatible_fallback"
    return None, "unresolved"


def remap_workflow_model_refs(
    workflow: dict[str, Any],
    catalog: Any,
    *,
    node_model_defaults: dict[str, str] | None = None,
    commercial_ok: bool | None = None,
) -> list[dict[str, str]]:
    """Rewrite widgets.model to local registry ids. Returns remap audit rows."""
    remaps: list[dict[str, str]] = []
    defaults = node_model_defaults or {}
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return remaps
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "")
        widgets = node.get("widgets")
        if not isinstance(widgets, dict):
            widgets = {}
            node["widgets"] = widgets
        raw = widgets.get("model")
        suggested = "" if raw is None else str(raw).strip()
        # Only touch nodes that already have a model widget or declare a MODEL_REF default.
        if not suggested and node_type not in defaults:
            continue
        resolved, reason = resolve_local_model_id(
            suggested,
            node_type=node_type,
            catalog=catalog,
            node_model_defaults=defaults,
            commercial_ok=commercial_ok,
        )
        if not resolved:
            if suggested:
                # Drop unknown public refs so Compliance does not hard-block on HF paths.
                widgets.pop("model", None)
                remaps.append(
                    {
                        "node_id": str(node.get("id") or ""),
                        "node_type": node_type,
                        "from": suggested,
                        "to": "",
                        "reason": "cleared_unknown",
                    }
                )
            continue
        if suggested == resolved:
            continue
        widgets["model"] = resolved
        remaps.append(
            {
                "node_id": str(node.get("id") or ""),
                "node_type": node_type,
                "from": suggested or "(empty)",
                "to": resolved,
                "reason": reason,
            }
        )
    return remaps


def fill_load_audio_paths(workflow: dict[str, Any]) -> list[dict[str, str]]:
    """Ensure LoadAudio nodes have a project-relative demo path when Claude left path empty."""
    fills: list[dict[str, str]] = []
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return fills
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("type") or "") != "LoadAudio":
            continue
        widgets = node.get("widgets")
        if not isinstance(widgets, dict):
            widgets = {}
            node["widgets"] = widgets
        raw = widgets.get("path")
        path = "" if raw is None else str(raw).strip()
        if path:
            continue
        widgets["path"] = DEFAULT_PLAN_LOAD_AUDIO_PATH
        fills.append(
            {
                "node_id": str(node.get("id") or ""),
                "from": "(empty)",
                "to": DEFAULT_PLAN_LOAD_AUDIO_PATH,
                "reason": "default_demo_sample",
            }
        )
    return fills


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1)
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    data = json.loads(stripped)
    if not isinstance(data, dict):
        raise ValueError("Claude response JSON must be an object")
    return data


def _call_claude(*, api_key: str, system: str, user: str, model: str) -> str:
    # Omit temperature/top_p — Claude Sonnet 5+ reject non-default sampling params.
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    request = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Anthropic API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Anthropic API unreachable: {exc.reason}") from exc

    chunks = body.get("content") or []
    texts = [str(chunk.get("text", "")) for chunk in chunks if chunk.get("type") == "text"]
    text = "\n".join(t for t in texts if t).strip()
    if not text:
        raise RuntimeError("Anthropic API returned no text content")
    return text


def _slot_endpoint(raw: Any, field: str) -> list[str | int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    node_id = str(raw[0]).strip()
    if not node_id:
        return None
    try:
        slot = int(raw[1])
    except (TypeError, ValueError):
        slot = 0
    return [node_id, max(0, slot)]


def _sanitize_node(raw: Any, *, index: int, used_ids: set[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    node_type = str(raw.get("type") or "").strip()
    if not node_type:
        return None
    node_id = str(raw.get("id") or f"n{index + 1}").strip() or f"n{index + 1}"
    base = node_id
    suffix = 2
    while node_id in used_ids:
        node_id = f"{base}_{suffix}"
        suffix += 1
    used_ids.add(node_id)

    widgets = raw.get("widgets") if isinstance(raw.get("widgets"), dict) else {}
    pos = raw.get("pos") if isinstance(raw.get("pos"), dict) else None
    node: dict[str, Any] = {
        "id": node_id,
        "type": node_type,
        "widgets": widgets,
    }
    if pos is not None:
        try:
            node["pos"] = {"x": float(pos.get("x", 0)), "y": float(pos.get("y", 0))}
        except (TypeError, ValueError):
            pass
    return node


def _sanitize_link(raw: Any, *, index: int, node_ids: set[str]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    src = _slot_endpoint(raw.get("from"), "from")
    dst = _slot_endpoint(raw.get("to"), "to")
    if src is None or dst is None:
        return None
    if src[0] not in node_ids or dst[0] not in node_ids:
        return None
    link_type = str(raw.get("type") or "AUDIO").strip().upper() or "AUDIO"
    if link_type not in SOCKET_TYPES:
        link_type = "AUDIO"
    link_id = str(raw.get("id") or f"e{index + 1}").strip() or f"e{index + 1}"
    return {
        "id": link_id,
        "from": src,
        "to": dst,
        "type": link_type,
    }


def hydrate_composed_workflow(
    draft: dict[str, Any],
    *,
    index: int,
    known_node_types: set[str] | None,
    catalog: Any = None,
    node_model_defaults: dict[str, str] | None = None,
    commercial_ok: bool | None = None,
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, str]], str]:
    """Build a Workflow dict from Claude draft nodes/links.

    Returns (workflow, unknown_types, model_remaps, skip_reason).
    """
    raw_nodes = draft.get("nodes")
    raw_links = draft.get("links")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return None, [], [], "workflow has no nodes"

    used_ids: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_nodes[:48]):
        node = _sanitize_node(raw, index=i, used_ids=used_ids)
        if node:
            nodes.append(node)
    if not nodes:
        return None, [], [], "no valid nodes"

    node_ids = {n["id"] for n in nodes}
    links: list[dict[str, Any]] = []
    if isinstance(raw_links, list):
        for i, raw in enumerate(raw_links[:96]):
            link = _sanitize_link(raw, index=i, node_ids=node_ids)
            if link:
                links.append(link)

    summary = str(draft.get("summary") or draft.get("title") or "").strip()
    rationale = str(draft.get("rationale") or draft.get("description") or "").strip()
    title = summary or f"Claude draft {index + 1}"

    unknown: list[str] = []
    if known_node_types is not None:
        seen: set[str] = set()
        for node in nodes:
            ntype = str(node["type"])
            if ntype not in known_node_types and ntype not in seen:
                seen.add(ntype)
                unknown.append(ntype)

    workflow = {
        "schema_version": "1.0.0",
        "groovy_version": "0.1.0",
        "id": str(uuid.uuid4()),
        "metadata": {
            "title": title[:120],
            "author": "claude-plan",
            "description": rationale[:400],
            "tags": ["plan", "experimental", "claude"],
        },
        "nodes": nodes,
        "links": links,
        "groups": [],
    }
    remaps = remap_workflow_model_refs(
        workflow,
        catalog,
        node_model_defaults=node_model_defaults,
        commercial_ok=commercial_ok,
    )
    path_fills = fill_load_audio_paths(workflow)
    for row in path_fills:
        remaps.append(
            {
                "node_id": row["node_id"],
                "node_type": "LoadAudio",
                "from": row["from"],
                "to": row["to"],
                "reason": row["reason"],
            }
        )
    try:
        Workflow.model_validate(workflow)
    except Exception as exc:
        return None, unknown, remaps, f"invalid workflow shape: {exc}"
    return workflow, unknown, remaps, ""


def _collect_workflow_drafts(parsed: dict[str, Any], *, max_workflows: int) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    workflows = parsed.get("workflows")
    if isinstance(workflows, list):
        for item in workflows:
            if isinstance(item, dict):
                drafts.append(item)
    single = parsed.get("workflow")
    if isinstance(single, dict) and single not in drafts:
        drafts.insert(0, single)
    # Legacy: actions with inline nodes/links
    actions = parsed.get("actions")
    if isinstance(actions, list):
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("type") in {"propose_workflow", "apply_template", "compose_workflow"}:
                if isinstance(action.get("nodes"), list):
                    drafts.append(action)
                elif isinstance(action.get("workflow"), dict):
                    nested = action["workflow"]
                    if isinstance(nested.get("nodes"), list):
                        drafts.append(
                            {
                                **nested,
                                "summary": action.get("summary") or nested.get("summary"),
                                "rationale": action.get("rationale") or nested.get("rationale"),
                            }
                        )
    return drafts[: max(1, max_workflows)]


def plan_agent_request_llm(
    catalog: Any = None,
    store: Any = None,
    registry: Any = None,
    *,
    prompt: str,
    templates_dir: Any = None,
    api_key: str | None,
    commercial_ok: bool | None = None,
    node_type: str | None = None,
    task_type: str | None = None,
    max_models: int = 3,
    max_workflows: int = 2,
    model: str = DEFAULT_CLAUDE_MODEL,
    known_node_types: set[str] | frozenset[str] | None = None,
    node_model_defaults: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compose blueprint workflow(s) from prompt via Claude.

    Catalog / node types are **not** sent to Claude. After the reply, model widget
    values are remapped onto the local published registry (or node defaults).
    """
    del store, registry, templates_dir, max_models  # keep call-site stable
    prompt = prompt.strip()
    base = {
        "prompt": prompt,
        "planner": "llm",
        "deterministic": False,
        "agent": "plan_llm_v5",
        "tools_used": ["claude_messages"],
        "experimental": True,
    }
    if not prompt:
        return {
            **base,
            "actions": [],
            "notes": "Enter a task description to draft a graph blueprint.",
            "mode": "empty",
        }
    if not api_key:
        return {
            **base,
            "actions": [],
            "notes": (
                "Plan needs an Anthropic API key. "
                "Set ANTHROPIC_API_KEY in the environment (preferred) or save one in "
                "Settings → Plan / Claude. Suggest workflow works without a key."
            ),
            "mode": "needs_api_key",
        }

    known = set(known_node_types) if known_node_types is not None else None

    system = (
        "You are GroovyUI experimental Plan mode.\n"
        "Product philosophy: a patch-bay for AI audio exploration — not a DAW. "
        "Users patch models, render offline with sample accuracy, and audition cached PCM. "
        "Agents suggest; the user Applies explicitly. Never claim to install or rewrite the canvas.\n"
        "\n"
        "How to build the graph (priority order):\n"
        "1. Mentally search well-known public AI audio models that fit the task "
        "(denoise, stems, STT, TTS, voice conversion, audio-to-MIDI, music gen, etc.). "
        "Mention those public names in rationale/notes.\n"
        "2. Prefer simple offline patch-bay hops. Use PascalCase node types "
        "(LoadAudio, Denoise, SeparateStems, WhisperSTT, TTS, Normalize, Preview, SaveAudio).\n"
        "3. Keep graphs minimal: LoadAudio/Prompt → one or two AI hops → Preview/SaveAudio.\n"
        "4. For widgets.model: omit it or use a short family token (e.g. denoise, tts, whisper). "
        "Do NOT put Hugging Face org/repo paths (like org/model-name) in widgets.model — "
        "the studio remaps to local registry ids after your reply.\n"
        "5. For LoadAudio: omit widgets.path or leave it empty — the studio assigns a demo sample. "
        "Do not invent absolute paths.\n"
        "6. Prefer commercial-friendly public models when filters.commercial_ok is true.\n"
        "\n"
        "Reply with ONLY a JSON object:\n"
        '{"inferred_task": string|null, "notes": string, "workflows": [ ... ]}\n'
        "Each workflow object:\n"
        '{"summary":"short outcome","rationale":"why these public models + hops",'
        '"nodes":[{"id":"n1","type":"LoadAudio","widgets":{},"pos":{"x":0,"y":0}}],'
        '"links":[{"id":"e1","from":["n1",0],"to":["n2",0],"type":"AUDIO"}]}\n'
        "Socket type on links must be one of: AUDIO, MIDI, TEXT, FLOAT, CONTROL, OBA. "
        f"Return at most {max_workflows} workflows."
    )
    user_payload: dict[str, Any] = {
        "task": prompt,
        "filters": {
            "commercial_ok": commercial_ok,
            "task_type": task_type,
            "node_type": node_type,
        },
        "constraints": {
            "max_workflows": max_workflows,
            "blueprint_only": True,
            "no_model_catalog": True,
            "no_template_catalog": True,
            "no_node_type_catalog": True,
            "prefer_public_ai_models": True,
            "keep_graphs_simple": True,
            "remap_models_locally": True,
        },
    }
    user = json.dumps(user_payload, indent=2)

    try:
        raw_text = _call_claude(api_key=api_key, system=system, user=user, model=model)
        parsed = _extract_json_object(raw_text)
    except Exception as exc:
        return {
            **base,
            "actions": [],
            "notes": f"Claude plan failed: {exc}",
            "mode": "error",
            "inferred_task": None,
        }

    drafts = _collect_workflow_drafts(parsed, max_workflows=max_workflows)
    actions: list[dict[str, Any]] = []
    skipped: list[str] = []
    all_remaps: list[dict[str, str]] = []
    for index, draft in enumerate(drafts):
        workflow, unknown, remaps, reason = hydrate_composed_workflow(
            draft,
            index=index,
            known_node_types=known,
            catalog=catalog,
            node_model_defaults=node_model_defaults,
            commercial_ok=commercial_ok,
        )
        if workflow is None:
            skipped.append(reason or f"workflow[{index}] rejected")
            continue
        all_remaps.extend(remaps)
        summary = str(draft.get("summary") or workflow["metadata"]["title"]).strip()
        rationale = str(draft.get("rationale") or workflow["metadata"].get("description") or "").strip()
        if remaps:
            mapped = "; ".join(
                f"{row['from']}→{row['to'] or '(cleared)'}" for row in remaps if row.get("from")
            )
            if mapped:
                rationale = (rationale + f" Local model map: {mapped}.").strip()
        actions.append(
            {
                "type": "propose_workflow",
                "id": f"propose:{workflow['id']}",
                "title": summary or f"Draft graph {index + 1}",
                "summary": summary or f"Draft graph {index + 1}",
                "rationale": rationale or "Composed by Claude from your prompt.",
                "description": rationale,
                "workflow": workflow,
                "unknown_node_types": unknown,
                "model_remaps": remaps,
                "priority": int(draft.get("priority") or (10 - index)),
            }
        )

    actions.sort(key=lambda a: (-int(a.get("priority", 0)), str(a.get("title", ""))))

    notes = str(parsed.get("notes") or "").strip()
    note_parts = [
        "Experimental Plan (Claude) — public-model ideas remapped to local registry ids; Apply stays explicit.",
        notes,
    ]
    if all_remaps:
        note_parts.append(f"Remapped {len(all_remaps)} model reference(s) to published registry ids.")
    if any(a.get("unknown_node_types") for a in actions):
        note_parts.append("Highlighted nodes are not available in this build yet.")
    if skipped:
        note_parts.append(f"Dropped {len(skipped)} invalid draft(s).")

    return {
        **base,
        "inferred_task": parsed.get("inferred_task"),
        "commercial_ok": commercial_ok,
        "node_type": node_type,
        "actions": actions,
        "recommend_count": 0,
        "workflow_count": len(actions),
        "license_preview": None,
        "notes": " ".join(part for part in note_parts if part),
        "mode": "plan",
        "skipped": skipped,
    }
