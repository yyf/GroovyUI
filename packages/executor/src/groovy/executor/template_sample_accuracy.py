"""L4 sample-accuracy audit — offline PCM hash integrity per template hop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from groovy.executor.cache import CacheStore
from groovy.executor.sample_integrity import verify_samples_for_audio
from groovy.executor.template_integrity_registry import TemplateIntegritySpec
from groovy.schema.models import Workflow

HopRole = Literal["input", "output", "ai", "hop"]

_AUDIO_TERMINAL_TYPES = frozenset({"AUDIO", "MULTI", "STEMS"})


@dataclass(frozen=True)
class SampleHopRecord:
    node_id: str
    node_type: str
    cache_id: str
    slot: str | None
    role: HopRole
    ok: bool
    hash_match: bool
    frame_count: int
    sample_rate: int
    deterministic: bool | None
    sample_accurate: bool | None


@dataclass(frozen=True)
class TemplateSampleAccuracyReport:
    template_id: str
    records: tuple[SampleHopRecord, ...]

    @property
    def input_records(self) -> tuple[SampleHopRecord, ...]:
        return tuple(record for record in self.records if record.role == "input")

    @property
    def output_records(self) -> tuple[SampleHopRecord, ...]:
        return tuple(record for record in self.records if record.role == "output")

    @property
    def ai_records(self) -> tuple[SampleHopRecord, ...]:
        return tuple(record for record in self.records if record.role == "ai")


def _manifest_outputs_by_node(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_node: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("nodes", []):
        output = entry.get("output")
        if output:
            by_node[entry["node_id"]] = output
    return by_node


def _iter_audio_caches(output: dict[str, Any]) -> list[tuple[str | None, str]]:
    output_type = output.get("type")
    if output_type == "AUDIO" and output.get("cache_id"):
        return [(None, str(output["cache_id"]))]
    if output_type == "MULTI":
        refs: list[tuple[str | None, str]] = []
        for index, slot in enumerate(output.get("outputs") or []):
            if slot.get("type") == "AUDIO" and slot.get("cache_id"):
                refs.append((slot.get("name") or f"slot_{index}", str(slot["cache_id"])))
        return refs
    if output_type == "STEMS":
        stems = output.get("stems") or {}
        return [(name, str(cache_id)) for name, cache_id in stems.items() if cache_id]
    return []


def _node_flags(
    node_type: str,
    node_registry: dict[str, Any],
) -> tuple[bool | None, bool | None]:
    node_cls = node_registry.get(node_type)
    if node_cls is None:
        return None, None
    return getattr(node_cls, "DETERMINISTIC", None), getattr(node_cls, "SAMPLE_ACCURATE", None)


def _node_emits_audio_cache(node_type: str, node_registry: dict[str, Any]) -> bool:
    node_cls = node_registry.get(node_type)
    if node_cls is None:
        return False
    for output in node_cls.describe().get("outputs", []):
        if output.get("type") in {"AUDIO", "MULTI", "STEMS"}:
            return True
    return False


def _assign_role(
    node_id: str,
    node_type: str,
    *,
    load_audio_ids: set[str],
    required_output_ids: set[str],
    node_registry: dict[str, Any],
) -> HopRole:
    if node_id in load_audio_ids:
        return "input"
    if node_id in required_output_ids:
        return "output"
    deterministic, _sample_accurate = _node_flags(node_type, node_registry)
    if deterministic is False and _node_emits_audio_cache(node_type, node_registry):
        return "ai"
    return "hop"


def audit_sample_accuracy(
    spec: TemplateIntegritySpec,
    manifest: dict[str, Any],
    workflow: Workflow,
    cache: CacheStore,
    *,
    node_registry: dict[str, Any],
) -> tuple[list[str], TemplateSampleAccuracyReport]:
    """L4 — verify PCM hash integrity for input, terminal, and AI hops.

    Proves the offline sample-accuracy claim (declared hash matches cached PCM).
    AI hops must remain ``DETERMINISTIC = False`` (not bit-identical across reruns).
    """
    errors: list[str] = []
    outputs_by_node = _manifest_outputs_by_node(manifest)
    load_audio_ids = {node.id for node in workflow.nodes if node.type == "LoadAudio"}
    required_output_ids = {
        node_id for node_id, output_type in spec.required_outputs if output_type in _AUDIO_TERMINAL_TYPES
    }
    workflow_ai_audio_ids = {
        node.id
        for node in workflow.nodes
        if _node_emits_audio_cache(node.type, node_registry)
        and _node_flags(node.type, node_registry)[0] is False
    }

    records: list[SampleHopRecord] = []
    seen: set[tuple[str, str | None, str]] = set()

    for entry in manifest.get("nodes", []):
        node_id = str(entry["node_id"])
        node_type = str(entry.get("type") or "")
        output = entry.get("output")
        if not output:
            continue
        deterministic, sample_accurate = _node_flags(node_type, node_registry)
        role = _assign_role(
            node_id,
            node_type,
            load_audio_ids=load_audio_ids,
            required_output_ids=required_output_ids,
            node_registry=node_registry,
        )
        for slot, cache_id in _iter_audio_caches(output):
            key = (node_id, slot, cache_id)
            if key in seen:
                continue
            seen.add(key)
            check = verify_samples_for_audio(cache, cache_id)
            record = SampleHopRecord(
                node_id=node_id,
                node_type=node_type,
                cache_id=cache_id,
                slot=slot,
                role=role,
                ok=bool(check["ok"]),
                hash_match=bool(check["hash_match"]),
                frame_count=int(check["frame_count"]),
                sample_rate=int(check["sample_rate"]),
                deterministic=deterministic,
                sample_accurate=sample_accurate,
            )
            records.append(record)
            slot_label = f" ({slot})" if slot else ""
            if not check["ok"]:
                errors.append(f"{node_id}{slot_label}: {check['summary']}")
            if role == "ai":
                if deterministic is not False:
                    errors.append(f"{node_id}{slot_label}: AI hop must be DETERMINISTIC=False")
                if sample_accurate is not True:
                    errors.append(f"{node_id}{slot_label}: AI audio hop must be SAMPLE_ACCURATE=True")

    report = TemplateSampleAccuracyReport(template_id=spec.template_id, records=tuple(records))

    if load_audio_ids:
        audited_inputs = {record.node_id for record in report.input_records}
        missing_inputs = load_audio_ids - audited_inputs
        if missing_inputs:
            errors.append(
                f"LoadAudio nodes missing verified PCM: {sorted(missing_inputs)}"
            )

    for node_id, expected_type in spec.required_outputs:
        if expected_type not in _AUDIO_TERMINAL_TYPES:
            continue
        output = outputs_by_node.get(node_id)
        if not output:
            errors.append(f"{node_id}: required {expected_type} output missing from manifest")
            continue
        expected_refs = _iter_audio_caches(output)
        if not expected_refs:
            errors.append(f"{node_id}: required {expected_type} output has no AUDIO cache refs")
            continue
        verified_outputs = {
            (record.node_id, record.slot, record.cache_id)
            for record in report.output_records
            if record.hash_match
        }
        for slot, cache_id in expected_refs:
            if (node_id, slot, cache_id) not in verified_outputs:
                slot_label = f" ({slot})" if slot else ""
                errors.append(f"{node_id}{slot_label}: terminal output PCM hash verify failed")

    for node_id in sorted(workflow_ai_audio_ids):
        output = outputs_by_node.get(node_id)
        if not output or not _iter_audio_caches(output):
            continue
        ai_records = [record for record in report.ai_records if record.node_id == node_id]
        if not ai_records:
            errors.append(f"{node_id}: AI audio node missing verified hop")
        elif not all(record.hash_match for record in ai_records):
            errors.append(f"{node_id}: AI audio hop PCM hash verify failed")

    return errors, report


__all__ = [
    "SampleHopRecord",
    "TemplateSampleAccuracyReport",
    "audit_sample_accuracy",
]
