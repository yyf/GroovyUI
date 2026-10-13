"""Creative Agent — multi-step canvas proposals with human approval gates.

Studio vehicle: Tab on the canvas (ghost preview → Tab approve each hop).
Not a Workflow-bar button — Patch Generation (⌘G) and Model Browser cover
prompt drafts / discovery; this agent grows the current patch in place.

Mirrors Patch Generation / Plan security:
- BYOK Anthropic key (server-side only)
- Never send model/template/node catalogs to Claude
- Canvas snapshot may include the user's current graph (ids/types/links only)
- Agents propose; each step requires explicit Tab approval (or skip / Esc)
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

from groovy.registry.agent.llm_planner import (
    DEFAULT_CLAUDE_MODEL,
    SOCKET_TYPES,
    _call_claude,
    _extract_json_object,
    _sanitize_link,
    _sanitize_node,
    resolve_local_model_id,
)

ALLOWED_ACTION_TYPES = frozenset(
    {
        "add_node",
        "connect",
        "set_widgets",
        "remove_node",
        "propose_note",
        "suggest_render",
    }
)
MAX_STEPS = 8

# Fixed public type names (not the live registry) — bias Claude + local remap.
PUBLIC_NODE_TYPE_HINTS = (
    "LoadAudio, SaveAudio, Preview, Normalize, Denoise, SeparateStems, "
    "WhisperSTT, TTS, Mix, Trim, Resample, ChannelConvert, Video2Audio, "
    "Prompt, Note, ControlCurve, AutomationApply"
)

# Public / hallucinated labels → GroovyUI node types (local remap; never sent as a catalog).
_NODE_TYPE_ALIASES: dict[str, str] = {
    "deepfilternet": "Denoise",
    "deepfilter": "Denoise",
    "deepfilternetv3": "Denoise",
    "noisereduction": "Denoise",
    "noisereduce": "Denoise",
    "audiocleanup": "Denoise",
    "denoiseaudio": "Denoise",
    "demucs": "SeparateStems",
    "htdemucs": "SeparateStems",
    "stemseparator": "SeparateStems",
    "separatestem": "SeparateStems",
    "source separation": "SeparateStems",
    "sourceseparation": "SeparateStems",
    "whisper": "WhisperSTT",
    "whisperstt": "WhisperSTT",
    "speech to text": "WhisperSTT",
    "speechtotext": "WhisperSTT",
    "asr": "WhisperSTT",
    "stt": "WhisperSTT",
    "kokoro": "TTS",
    "texttospeech": "TTS",
    "ttsnode": "TTS",
    "audioload": "LoadAudio",
    "loadaudiofile": "LoadAudio",
    "audioinput": "LoadAudio",
    "audiopreview": "Preview",
    "previewaudio": "Preview",
    "audionormalize": "Normalize",
    "loudnorm": "Normalize",
    "lufsnormalize": "Normalize",
    "audiomix": "Mix",
    "mixer": "Mix",
    "savewav": "SaveAudio",
    "exportaudio": "SaveAudio",
    "writeaudio": "SaveAudio",
    "videotoaudio": "Video2Audio",
    "v2a": "Video2Audio",
    "audioclip": "Trim",
    "resampleaudio": "Resample",
}


def _norm_type_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def resolve_local_node_type(
    proposed: str,
    *,
    known_node_types: set[str] | None,
) -> tuple[str | None, str | None]:
    """Map a Claude-invented type onto a local node type. Returns (resolved, reason)."""
    text = (proposed or "").strip()
    if not text:
        return None, None
    if known_node_types is not None and text in known_node_types:
        return text, None

    key = _norm_type_key(text)
    alias = _NODE_TYPE_ALIASES.get(key)
    if alias and (known_node_types is None or alias in known_node_types):
        return alias, "alias"

    if known_node_types:
        # Case-insensitive exact
        for known in known_node_types:
            if known.lower() == text.lower():
                return known, "casefold"
        # Fuzzy against known types (threshold keeps wild hallucinations out)
        best: tuple[float, str] | None = None
        for known in known_node_types:
            score = SequenceMatcher(None, key, _norm_type_key(known)).ratio()
            if best is None or score > best[0]:
                best = (score, known)
        if best and best[0] >= 0.72:
            return best[1], "fuzzy"

    if alias:
        return alias, "alias_unchecked"
    return None, None


def _canvas_summary(canvas: dict[str, Any] | None) -> dict[str, Any]:
    """Strip canvas to ids/types/links — never attach catalogs or secrets."""
    if not isinstance(canvas, dict):
        return {"nodes": [], "links": []}
    nodes_out: list[dict[str, Any]] = []
    for raw in canvas.get("nodes") or []:
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("id") or "").strip()
        node_type = str(raw.get("type") or "").strip()
        if not node_id or not node_type:
            continue
        widgets = raw.get("widgets") if isinstance(raw.get("widgets"), dict) else {}
        # Only pass widget *keys* + non-secret scalar hints (no HF tokens / paths beyond basename).
        safe_widgets: dict[str, Any] = {}
        for key, value in list(widgets.items())[:24]:
            k = str(key)
            if k.lower() in {"token", "api_key", "password", "secret", "hf_token"}:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                text = "" if value is None else str(value)
                if len(text) > 120:
                    text = text[:117] + "..."
                safe_widgets[k] = text if isinstance(value, str) else value
        entry: dict[str, Any] = {"id": node_id, "type": node_type}
        if safe_widgets:
            entry["widgets"] = safe_widgets
        nodes_out.append(entry)
        if len(nodes_out) >= 64:
            break
    links_out: list[dict[str, Any]] = []
    node_ids = {n["id"] for n in nodes_out}
    for i, raw in enumerate((canvas.get("links") or [])[:96]):
        link = _sanitize_link(raw, index=i, node_ids=node_ids)
        if link is not None:
            links_out.append(
                {
                    "id": link["id"],
                    "from": link["from"],
                    "to": link["to"],
                    "type": link["type"],
                }
            )
    return {"nodes": nodes_out, "links": links_out}


def _sanitize_action(
    raw: Any,
    *,
    known_node_types: set[str] | None,
    catalog: Any,
    node_model_defaults: dict[str, str] | None,
) -> tuple[dict[str, Any] | None, list[str], str]:
    """Return (action, unknown_node_types, skip_reason)."""
    if not isinstance(raw, dict):
        return None, [], "action must be an object"
    action_type = str(raw.get("type") or "").strip()
    if action_type not in ALLOWED_ACTION_TYPES:
        return None, [], f"unsupported action type {action_type!r}"

    unknown: list[str] = []

    if action_type == "propose_note":
        message = str(raw.get("message") or raw.get("text") or "").strip()
        if not message:
            return None, [], "propose_note needs message"
        return {"type": action_type, "message": message[:2000]}, [], ""

    if action_type == "suggest_render":
        target = str(raw.get("target_node_id") or raw.get("node_id") or "").strip()
        if not target:
            return None, [], "suggest_render needs target_node_id"
        return {"type": action_type, "target_node_id": target}, [], ""

    if action_type == "remove_node":
        node_id = str(raw.get("node_id") or "").strip()
        if not node_id:
            return None, [], "remove_node needs node_id"
        return {"type": action_type, "node_id": node_id}, [], ""

    if action_type == "set_widgets":
        node_id = str(raw.get("node_id") or "").strip()
        widgets = raw.get("widgets") if isinstance(raw.get("widgets"), dict) else None
        if not node_id or widgets is None:
            return None, [], "set_widgets needs node_id and widgets"
        cleaned: dict[str, Any] = {}
        for key, value in list(widgets.items())[:32]:
            k = str(key)
            if k.lower() in {"token", "api_key", "password", "secret", "hf_token"}:
                continue
            cleaned[k] = value
        node_type = str(raw.get("node_type") or "").strip()
        if "model" in cleaned and node_type:
            mapped, _reason = resolve_local_model_id(
                str(cleaned.get("model") or ""),
                node_type=node_type,
                catalog=catalog,
                node_model_defaults=node_model_defaults,
            )
            if mapped:
                cleaned["model"] = mapped
            else:
                cleaned.pop("model", None)
        return {
            "type": action_type,
            "node_id": node_id,
            "node_type": node_type or None,
            "widgets": cleaned,
        }, [], ""

    if action_type == "connect":
        src = raw.get("from")
        dst = raw.get("to")
        if not isinstance(src, (list, tuple)) or not isinstance(dst, (list, tuple)):
            return None, [], "connect needs from/to endpoints"
        try:
            src_id, src_slot = str(src[0]).strip(), int(src[1])
            dst_id, dst_slot = str(dst[0]).strip(), int(dst[1])
        except (IndexError, TypeError, ValueError):
            return None, [], "connect endpoints invalid"
        if not src_id or not dst_id:
            return None, [], "connect endpoints missing ids"
        link_type = str(raw.get("link_type") or raw.get("socket_type") or "AUDIO").strip().upper()
        if link_type in {"CONNECT", "LINK"}:
            link_type = "AUDIO"
        if link_type not in SOCKET_TYPES:
            link_type = "AUDIO"
        return {
            "type": "connect",
            "from": [src_id, max(0, src_slot)],
            "to": [dst_id, max(0, dst_slot)],
            "link_type": link_type,
        }, [], ""

    if action_type == "add_node":
        node_raw = raw.get("node") if isinstance(raw.get("node"), dict) else raw
        used_ids: set[str] = set()
        node = _sanitize_node(node_raw, index=0, used_ids=used_ids)
        if node is None:
            return None, [], "add_node needs a valid node"
        proposed_type = str(node["type"])
        resolved, remap_reason = resolve_local_node_type(
            proposed_type, known_node_types=known_node_types
        )
        if resolved:
            if resolved != proposed_type:
                node["type"] = resolved
                node["_remapped_from"] = proposed_type
                node["_remap_reason"] = remap_reason
            node_type = resolved
        else:
            # Degrade to a note instead of a locked dead-end — Tab can still advance.
            return {
                "type": "propose_note",
                "message": (
                    f"Claude suggested “{proposed_type}”, which isn’t in this build. "
                    "Try Denoise / SeparateStems / WhisperSTT / Preview, or open Model Browser (⌘K)."
                ),
                "_degraded_from": proposed_type,
            }, [proposed_type], ""
        widgets = node.get("widgets") if isinstance(node.get("widgets"), dict) else {}
        if "model" in widgets:
            mapped, _reason = resolve_local_model_id(
                str(widgets.get("model") or ""),
                node_type=node_type,
                catalog=catalog,
                node_model_defaults=node_model_defaults,
            )
            if mapped:
                widgets["model"] = mapped
            else:
                widgets.pop("model", None)
            node["widgets"] = widgets
        return {"type": "add_node", "node": node}, unknown, ""

    return None, [], f"unhandled action {action_type!r}"


def sanitize_creative_steps(
    drafts: list[Any],
    *,
    known_node_types: set[str] | None = None,
    catalog: Any = None,
    node_model_defaults: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    steps: list[dict[str, Any]] = []
    skipped: list[str] = []
    for index, raw in enumerate(drafts[:MAX_STEPS]):
        if not isinstance(raw, dict):
            skipped.append(f"step[{index}] not an object")
            continue
        action, unknown, reason = _sanitize_action(
            raw.get("action") if isinstance(raw.get("action"), dict) else raw,
            known_node_types=known_node_types,
            catalog=catalog,
            node_model_defaults=node_model_defaults,
        )
        if action is None:
            skipped.append(reason or f"step[{index}] rejected")
            continue
        step_id = str(raw.get("id") or f"step-{index + 1}").strip() or f"step-{index + 1}"
        title = str(raw.get("title") or action["type"]).strip()[:160]
        rationale = str(raw.get("rationale") or raw.get("reason") or "").strip()[:2000]
        # Remapped / degraded notes are approvable; only true add_node unknowns lock (rare now).
        locked = bool(unknown) and action["type"] == "add_node"
        remapped_from = None
        if action.get("type") == "add_node":
            node = action.get("node") if isinstance(action.get("node"), dict) else {}
            remapped_from = node.pop("_remapped_from", None) if isinstance(node, dict) else None
            if isinstance(node, dict):
                node.pop("_remap_reason", None)
        if action.get("type") == "propose_note" and action.get("_degraded_from"):
            remapped_from = action.pop("_degraded_from", None)
            if not title or title == "propose_note":
                title = f"Note: {remapped_from} unavailable"
            if rationale == "Proposed canvas action." or not rationale:
                rationale = action.get("message") or rationale
        steps.append(
            {
                "id": step_id,
                "index": len(steps),
                "title": title,
                "rationale": rationale or "Proposed canvas action.",
                "action": action,
                "unknown_node_types": unknown,
                "remapped_from": remapped_from,
                "requires_approval": True,
                "apply_locked": locked,
                "status": "pending",
            }
        )
    return steps, skipped


def plan_creative_agent(
    *,
    prompt: str,
    api_key: str | None,
    canvas: dict[str, Any] | None = None,
    revision: str | None = None,
    revise_step_id: str | None = None,
    prior_steps: list[Any] | None = None,
    model: str = DEFAULT_CLAUDE_MODEL,
    known_node_types: set[str] | frozenset[str] | None = None,
    catalog: Any = None,
    node_model_defaults: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Propose an ordered multi-step creative plan. Never mutates the canvas."""
    prompt = (prompt or "").strip()
    revision = (revision or "").strip()
    base = {
        "prompt": prompt,
        "planner": "llm",
        "deterministic": False,
        "agent": "creative_agent_v1",
        "tools_used": ["claude_messages"],
        "experimental": True,
        "human_in_the_loop": True,
    }
    if not prompt and not revision:
        return {
            **base,
            "steps": [],
            "notes": "Describe a creative goal — the agent proposes steps; you approve each one.",
            "mode": "empty",
        }
    if not api_key:
        return {
            **base,
            "steps": [],
            "notes": (
                "Creative Agent needs an Anthropic API key. "
                "Set ANTHROPIC_API_KEY or Settings → Plan / Claude."
            ),
            "mode": "needs_api_key",
        }

    known = set(known_node_types) if known_node_types is not None else None
    canvas_view = _canvas_summary(canvas)

    system = (
        "You are GroovyUI Creative Agent (experimental).\n"
        "Product philosophy: a patch-bay for AI audio exploration — not a DAW. "
        "Users patch models, render offline with sample accuracy, and audition cached PCM. "
        "You suggest actions and multi-step workflows; the human approves each step "
        "(thumbs-up or need-revision). Never claim to install models, rewrite the canvas, "
        "or auto-apply anything.\n"
        "\n"
        "Privacy / catalog policy (mandatory):\n"
        "- You are NOT given GroovyUI's private node-type registry, model registry, or templates.\n"
        "- You may see a summary of the user's current canvas (node ids/types/links only).\n"
        "- Invent hops from public AI-audio knowledge; the studio remaps model refs locally.\n"
        "\n"
        "Plan style:\n"
        "1. Reason briefly over canvas state, then propose 2–6 atomic steps.\n"
        "2. Each step is one canvas action the human can approve independently.\n"
        "3. Prefer additive exploration (add/connect/set widgets) over destructive remove.\n"
        "4. Keep graphs minimal. Offline render hops only — no live DAW transport fantasies.\n"
        "5. Layout: classic node-graph L→R signal flow (sources left, sinks right). "
        "Each node’s inputs are on the left, outputs on the right — place new hops to the "
        "right of their audio source (or left if inserting upstream).\n"
        "6. For widgets.model use short family tokens, not Hugging Face org/repo paths.\n"
        "7. For LoadAudio leave path empty (studio fills a demo sample).\n"
        "8. Prefer these public node type names when they fit: "
        f"{PUBLIC_NODE_TYPE_HINTS}. "
        "The studio remaps close aliases locally; avoid inventing product names.\n"
        "\n"
        "Allowed action.type values:\n"
        "- add_node: {type:'add_node', node:{id,type,widgets,pos}}\n"
        "- connect: {type:'connect', from:[id,slot], to:[id,slot], link_type:'AUDIO'}\n"
        "- set_widgets: {type:'set_widgets', node_id, node_type?, widgets:{}}\n"
        "- remove_node: {type:'remove_node', node_id}  (use sparingly)\n"
        "- propose_note: {type:'propose_note', message}  (no canvas mutation)\n"
        "- suggest_render: {type:'suggest_render', target_node_id}  (user must still press Render)\n"
        "\n"
        "Reply with ONLY a JSON object (no markdown fences):\n"
        '{"goal":string,"notes":string,"steps":['
        '{"id":"step-1","title":"...","rationale":"why",'
        '"action":{...}}]}\n'
        "Strict JSON only: double quotes, escape quotes inside strings, "
        "no trailing commas, no comments.\n"
        f"Return at most {MAX_STEPS} steps."
    )

    user_payload: dict[str, Any] = {
        "task": prompt or "(revision of prior plan)",
        "canvas": canvas_view,
        "constraints": {
            "max_steps": MAX_STEPS,
            "human_approves_each_step": True,
            "blueprint_proposals_only": True,
            "no_model_catalog": True,
            "no_template_catalog": True,
            "no_node_type_catalog": True,
            "patch_bay_not_daw": True,
        },
    }
    if revision:
        user_payload["revision"] = {
            "step_id": revise_step_id,
            "feedback": revision,
            "prior_steps": prior_steps or [],
            "instruction": (
                "Revise the plan from the named step onward using the human feedback. "
                "Keep already-approved steps out of the new steps list when possible; "
                "return replacement pending steps only."
            ),
        }
    for banned in (
        "models",
        "templates",
        "template_ids",
        "allowed_node_types",
        "known_node_types",
        "node_types",
        "node_catalog",
        "model_catalog",
        "registry",
        "node_model_defaults",
    ):
        user_payload.pop(banned, None)

    try:
        raw_text = _call_claude(
            api_key=api_key,
            system=system,
            user=json.dumps(user_payload, indent=2),
            model=model or DEFAULT_CLAUDE_MODEL,
        )
        parsed = _extract_json_object(raw_text)
    except Exception as exc:
        detail = str(exc)
        mode = "error"
        if "401" in detail or "authentication_error" in detail or "invalid x-api-key" in detail:
            mode = "auth_error"
            detail = (
                "Anthropic rejected the API key (401). "
                "Refresh ANTHROPIC_API_KEY or Settings → Plan / Claude."
            )
        elif isinstance(exc, json.JSONDecodeError) or "Expecting" in detail or "JSON" in detail:
            detail = (
                "Claude returned invalid JSON for the plan. "
                "Retry — or shorten the creative goal and try again."
            )
        return {
            **base,
            "steps": [],
            "notes": detail if mode == "auth_error" else f"Creative Agent failed: {detail}",
            "mode": mode,
            "goal": None,
        }

    drafts = parsed.get("steps")
    if not isinstance(drafts, list):
        drafts = []
    steps, skipped = sanitize_creative_steps(
        drafts,
        known_node_types=known,
        catalog=catalog,
        node_model_defaults=node_model_defaults,
    )
    notes = str(parsed.get("notes") or "").strip()
    goal = str(parsed.get("goal") or prompt).strip()
    note_parts = [
        "Creative Agent — proposes steps only; each step needs thumbs-up or need-revision.",
        notes,
    ]
    remapped = [s for s in steps if s.get("remapped_from")]
    if remapped:
        note_parts.append(
            f"Remapped {len(remapped)} node type(s) to local hops "
            "(unavailable suggestions become notes you can still Tab through)."
        )
    if any(s.get("apply_locked") for s in steps):
        note_parts.append("Some add_node steps still reference unavailable types.")
    if skipped:
        note_parts.append(f"Dropped {len(skipped)} invalid step(s).")

    return {
        **base,
        "goal": goal or None,
        "steps": steps,
        "notes": " ".join(part for part in note_parts if part),
        "mode": "plan" if steps else "empty_plan",
        "skipped": skipped,
        "revise_step_id": revise_step_id,
    }
