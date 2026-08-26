"""Signal integrity helpers for render manifests and template regression suites."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from groovy.executor.cache import CacheStore
from groovy.executor.template_integrity_registry import (
    ALL_TEMPLATE_INTEGRITY_SPECS,
    SIGNAL_INTEGRITY_V1_TEMPLATES,
    TemplateIntegritySpec,
    load_template_workflow,
    prepare_template_project,
)

# Nodes allowed to change sample rate on an AUDIO edge.
SR_CONVERT_NODES = frozenset({"Resample", "LoadAudio"})

# Nodes allowed to change channel layout on an AUDIO edge.
LAYOUT_CONVERT_NODES = frozenset({"ChannelConvert", "ChannelMerge", "Granulate", "LoadAudio"})

REQUIRED_AUDIO_SIGNAL_FIELDS = (
    "sample_rate",
    "channel_layout",
    "frame_count",
    "content_hash",
)


def attach_signal_metadata(cache: CacheStore, output_meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """Enrich manifest output entries with per-hop signal fields from cache meta."""
    if not output_meta:
        return output_meta

    output_type = output_meta.get("type")
    if output_type == "AUDIO" and output_meta.get("cache_id"):
        meta = cache.read_meta(output_meta["cache_id"])
        return {
            **output_meta,
            "sample_rate": meta.get("sample_rate"),
            "channel_layout": meta.get("channel_layout"),
            "frame_count": meta.get("frame_count"),
            "content_hash": meta.get("content_hash"),
        }

    if output_type == "MULTI" and output_meta.get("outputs"):
        enriched_slots: list[dict[str, Any]] = []
        for slot in output_meta["outputs"]:
            if slot.get("type") == "AUDIO" and slot.get("cache_id"):
                meta = cache.read_meta(slot["cache_id"])
                enriched_slots.append(
                    {
                        **slot,
                        "sample_rate": meta.get("sample_rate"),
                        "channel_layout": meta.get("channel_layout"),
                        "frame_count": meta.get("frame_count"),
                        "content_hash": meta.get("content_hash"),
                    }
                )
            else:
                enriched_slots.append(slot)
        return {**output_meta, "outputs": enriched_slots}

    if output_type == "STEMS" and output_meta.get("stems_id"):
        stems_meta_path = cache.cache_dir / f"{output_meta['stems_id']}.stems.meta.json"
        if stems_meta_path.exists():
            stems_meta = json.loads(stems_meta_path.read_text())
            return {
                **output_meta,
                "sample_rate": stems_meta.get("sample_rate"),
                "channel_layout": stems_meta.get("channel_layout"),
                "frame_count": stems_meta.get("frame_count"),
            }
    return output_meta


def load_manifest(manifest_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(manifest_path).read_text())


def _manifest_outputs_by_node(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_node: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("nodes", []):
        output = entry.get("output")
        if output:
            by_node[entry["node_id"]] = output
    return by_node


def audit_manifest(
    manifest: dict[str, Any],
    workflow: Workflow,
    cache: CacheStore,
) -> list[str]:
    """L2 — per-hop signal metadata and SR/layout continuity along AUDIO edges."""
    errors: list[str] = []
    outputs_by_node = _manifest_outputs_by_node(manifest)
    nodes_by_id = {node.id: node for node in workflow.nodes}

    for entry in manifest.get("nodes", []):
        output = entry.get("output")
        if not output:
            continue
        if output.get("type") == "AUDIO":
            missing = [field for field in REQUIRED_AUDIO_SIGNAL_FIELDS if not output.get(field)]
            if missing:
                errors.append(
                    f"{entry['node_id']} ({entry.get('type')}): manifest missing {', '.join(missing)}"
                )
            frame_count = output.get("frame_count")
            if frame_count is not None and int(frame_count) <= 0:
                errors.append(f"{entry['node_id']}: zero-length PCM (frame_count={frame_count})")

    for link in workflow.links:
        if link.type != "AUDIO":
            continue
        from_id = link.from_[0]
        to_id = link.to[0]
        to_node = nodes_by_id.get(to_id)
        from_out = outputs_by_node.get(from_id)
        to_out = outputs_by_node.get(to_id)
        if not from_out or not to_out or from_out.get("type") != "AUDIO" or to_out.get("type") != "AUDIO":
            continue
        if not to_node:
            continue

        from_sr = from_out.get("sample_rate")
        to_sr = to_out.get("sample_rate")
        if from_sr is not None and to_sr is not None and from_sr != to_sr:
            if to_node.type not in SR_CONVERT_NODES:
                errors.append(
                    f"{from_id} → {to_id}: sample rate changed {from_sr} → {to_sr} "
                    f"without {', '.join(sorted(SR_CONVERT_NODES))}"
                )

        from_layout = from_out.get("channel_layout")
        to_layout = to_out.get("channel_layout")
        if from_layout and to_layout and from_layout != to_layout:
            if to_node.type not in LAYOUT_CONVERT_NODES:
                errors.append(
                    f"{from_id} → {to_id}: layout changed {from_layout} → {to_layout} "
                    f"without {', '.join(sorted(LAYOUT_CONVERT_NODES))}"
                )

    _ = cache
    return errors


def _validate_required_output(
    node_id: str,
    expected_type: str,
    output: dict[str, Any] | None,
    cache: CacheStore,
) -> list[str]:
    errors: list[str] = []
    if not output:
        return [f"{node_id}: missing output (expected {expected_type})"]
    if output.get("type") != expected_type:
        return [f"{node_id}: expected {expected_type}, got {output.get('type')}"]
    if expected_type == "AUDIO":
        if int(output.get("frame_count") or 0) <= 0:
            errors.append(f"{node_id}: zero-length PCM")
    elif expected_type == "MIDI":
        if not output.get("midi_id"):
            errors.append(f"{node_id}: missing midi_id")
    elif expected_type == "TEXT":
        text = output.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{node_id}: empty TEXT output")
    elif expected_type == "AUTHENTICITY":
        if not output.get("authenticity_id"):
            errors.append(f"{node_id}: missing authenticity_id")
    elif expected_type == "MULTI":
        slots = output.get("outputs") or []
        if not slots:
            errors.append(f"{node_id}: empty MULTI outputs")
        else:
            auth = next((slot for slot in slots if slot.get("type") == "AUTHENTICITY"), None)
            sample = next((slot for slot in slots if slot.get("type") == "SAMPLE_CHECK"), None)
            audio = next((slot for slot in slots if slot.get("type") == "AUDIO" and slot.get("cache_id")), None)
            if auth is not None and not auth.get("authenticity_id"):
                errors.append(f"{node_id}: MULTI AUTHENTICITY slot missing authenticity_id")
            if sample is not None and not sample.get("sample_check_id"):
                errors.append(f"{node_id}: MULTI SAMPLE_CHECK slot missing sample_check_id")
            if audio is not None and int(audio.get("frame_count") or 0) <= 0:
                # frame_count may only exist after enrichment; fall back to cache
                meta = cache.read_meta(audio["cache_id"])
                if int(meta.get("frame_count") or 0) <= 0:
                    errors.append(f"{node_id}: MULTI AUDIO slot zero-length PCM")
    elif expected_type == "STEMS":
        if not output.get("stems_id"):
            errors.append(f"{node_id}: missing stems_id")
    _ = cache
    return errors


def audit_output_contract(
    spec: TemplateIntegritySpec,
    workflow: Workflow,
    manifest: dict[str, Any],
    cache: CacheStore,
) -> list[str]:
    """L3 — terminal and required output contracts."""
    errors: list[str] = []
    outputs_by_node = _manifest_outputs_by_node(manifest)
    nodes_by_id = {node.id: node for node in workflow.nodes}

    required = spec.required_outputs or ((spec.terminal_node, spec.terminal_output_type),)
    for node_id, expected_type in required:
        if expected_type == "NONE":
            continue
        errors.extend(_validate_required_output(node_id, expected_type, outputs_by_node.get(node_id), cache))

    load_nodes = [node for node in workflow.nodes if node.type == "LoadAudio"]
    load_meta: dict[str, Any] | None = None
    if load_nodes:
        load_out = outputs_by_node.get(load_nodes[0].id)
        if load_out and load_out.get("type") == "AUDIO":
            load_meta = load_out

    audio_terminal = next(
        (node_id for node_id, output_type in required if output_type == "AUDIO"),
        None,
    )
    if audio_terminal and load_meta:
        terminal_out = outputs_by_node.get(audio_terminal)
        if terminal_out and terminal_out.get("type") == "AUDIO":
            if terminal_out.get("sample_rate") != load_meta.get("sample_rate"):
                errors.append(
                    f"terminal SR {terminal_out.get('sample_rate')} != load SR {load_meta.get('sample_rate')}"
                )

    if spec.expect_stems_node:
        stems_out = outputs_by_node.get(spec.expect_stems_node)
        if stems_out and stems_out.get("type") == "MULTI":
            names = {slot.get("name") for slot in stems_out.get("outputs", [])}
            if spec.expect_stem_keys:
                missing = spec.expect_stem_keys - names
                if missing:
                    errors.append(f"{spec.expect_stems_node}: missing stem outputs {sorted(missing)}")
            vocals = next(
                (slot for slot in stems_out.get("outputs", []) if slot.get("name") == "vocals"),
                None,
            )
            if vocals and vocals.get("cache_id") and load_meta:
                stem_meta = cache.read_meta(vocals["cache_id"])
                if stem_meta.get("sample_rate") != load_meta.get("sample_rate"):
                    errors.append(
                        f"vocals SR {stem_meta.get('sample_rate')} != load SR {load_meta.get('sample_rate')}"
                    )
        elif stems_out and stems_out.get("type") == "STEMS":
            if spec.expect_stem_keys:
                stem_keys = set(stems_out.get("stems", {}).keys())
                missing = spec.expect_stem_keys - stem_keys
                if missing:
                    errors.append(f"{spec.expect_stems_node}: missing stem keys {sorted(missing)}")
            if load_meta:
                vocals_id = stems_out.get("stems", {}).get("vocals")
                if vocals_id:
                    stem_meta = cache.read_meta(vocals_id)
                    if stem_meta.get("sample_rate") != load_meta.get("sample_rate"):
                        errors.append(
                            f"vocals SR {stem_meta.get('sample_rate')} != load SR {load_meta.get('sample_rate')}"
                        )
        elif spec.expect_stem_keys:
            errors.append(f"{spec.expect_stems_node}: expected MULTI or STEMS output")

    if spec.expect_terminal_layout and audio_terminal:
        terminal_out = outputs_by_node.get(audio_terminal)
        if terminal_out and terminal_out.get("channel_layout") != spec.expect_terminal_layout:
            errors.append(
                f"{audio_terminal}: expected layout {spec.expect_terminal_layout}, "
                f"got {terminal_out.get('channel_layout')}"
            )

    for node_id, layout in spec.expect_hop_layout.items():
        hop_out = outputs_by_node.get(node_id)
        if not hop_out or hop_out.get("type") != "AUDIO":
            errors.append(f"{node_id}: expected AUDIO hop for layout check")
        elif hop_out.get("channel_layout") != layout:
            errors.append(f"{node_id}: expected layout {layout}, got {hop_out.get('channel_layout')}")

    if load_meta and audio_terminal:
        terminal_out = outputs_by_node.get(audio_terminal)
        if terminal_out and terminal_out.get("type") == "AUDIO":
            load_layout = load_meta.get("channel_layout")
            terminal_layout = terminal_out.get("channel_layout")
            if load_layout and terminal_layout and load_layout != terminal_layout:
                if terminal_layout == "mono" and load_layout not in {"mono"}:
                    path_has_convert = any(
                        nodes_by_id.get(link.to[0], None)
                        and nodes_by_id[link.to[0]].type == "ChannelConvert"
                        for link in workflow.links
                        if link.type == "AUDIO"
                    )
                    if not path_has_convert:
                        errors.append(
                            f"silent fold suspected: load layout {load_layout} → terminal {terminal_layout} "
                            "without ChannelConvert"
                        )

from groovy.schema.models import Workflow

__all__ = [
    "ALL_TEMPLATE_INTEGRITY_SPECS",
    "SIGNAL_INTEGRITY_V1_TEMPLATES",
    "TemplateIntegritySpec",
    "attach_signal_metadata",
    "audit_manifest",
    "audit_output_contract",
    "load_manifest",
    "load_template_workflow",
    "prepare_template_project",
]
