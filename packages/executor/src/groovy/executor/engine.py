from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from groovy.executor.ambisonics import AmbisonicBuffer
from groovy.executor.audio import AudioBuffer, StemsBuffer
from groovy.executor.authenticity import AuthenticityReport
from groovy.executor.sample_integrity import SampleCheckReport
from groovy.executor.cache import CacheStore
from groovy.executor.cancel import JobCancelled
from groovy.executor.content_credentials import (
    ContentCredentialSigner,
    ContentCredentialsMode,
    NoOpContentCredentialSigner,
    normalize_content_credentials_mode,
)
from groovy.executor.control import AutomationBuffer
from groovy.executor.midi import MidiBuffer
from groovy.executor.node_cache import compute_node_signature
from groovy.executor.oba import ObjectScene
from groovy.executor.osc_live import OscBuffer
from groovy.executor.trajectory import TrajectoryBuffer
from groovy.executor.provenance import build_record, parent_refs, read_provenance
from groovy.executor.signal_integrity import attach_signal_metadata
from groovy.node import NODE_REGISTRY, get_node_class
from groovy.schema.models import Link, NodeInstance, Workflow
from groovy.schema.validate import validate_workflow

EXECUTOR_VERSION = "0.1.0"
GROOVY_VERSION = "0.1.0"


@dataclass
class JobContext:
    project_dir: Path
    cache: CacheStore
    job_id: str
    content_credential_signer: ContentCredentialSigner = field(
        default_factory=NoOpContentCredentialSigner
    )
    content_credentials_mode: ContentCredentialsMode = "off"
    on_progress: Callable[[str, str, float, str], None] | None = None
    cancel_check: Callable[[], bool] | None = None

    def emit_progress(self, node_id: str, fraction: float, message: str) -> None:
        if self.on_progress:
            self.on_progress(self.job_id, node_id, fraction, message)

    def check_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise JobCancelled()


@dataclass
class ExecutionResult:
    job_id: str
    status: str
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    manifest_path: str | None = None
    error: str | None = None


class Executor:
    def __init__(
        self,
        project_dir: Path,
        *,
        model_metadata_resolver: Callable[[str], dict[str, Any] | None] | None = None,
        provenance_prompt_policy: str = "redacted",
        content_credential_signer: ContentCredentialSigner | None = None,
        content_credentials_mode_resolver: Callable[[], str] | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.cache = CacheStore(project_dir)
        self.model_metadata_resolver = model_metadata_resolver
        self.provenance_prompt_policy = provenance_prompt_policy
        self.content_credential_signer = (
            content_credential_signer or NoOpContentCredentialSigner()
        )
        self.content_credentials_mode_resolver = content_credentials_mode_resolver

    def execute(
        self,
        workflow: Workflow,
        *,
        target_nodes: list[str] | None = None,
        force_rebuild: bool = False,
        on_progress: Callable[[str, str, float, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> ExecutionResult:
        validation = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
        if not validation.valid:
            msg = "; ".join(e.message for e in validation.errors)
            return ExecutionResult(job_id="", status="failed", error=msg)

        job_id = str(uuid.uuid4())
        ctx = JobContext(
            project_dir=self.project_dir,
            cache=self.cache,
            job_id=job_id,
            content_credential_signer=self.content_credential_signer,
            content_credentials_mode=normalize_content_credentials_mode(
                self.content_credentials_mode_resolver()
                if self.content_credentials_mode_resolver
                else "off"
            ),
            on_progress=on_progress,
            cancel_check=cancel_check,
        )

        node_by_id = {n.id: n for n in workflow.nodes}
        order = _topological_order(workflow.nodes, workflow.links)
        if target_nodes:
            required = _upstream_closure(target_nodes, workflow.links)
            order = [nid for nid in order if nid in required]

        inputs_map = _build_inputs_map(workflow.links)
        manifest_nodes: list[dict[str, Any]] = []
        outputs: dict[str, dict[str, Any]] = {}
        started_at = datetime.now(UTC).isoformat()

        try:
            node_outputs: dict[str, tuple[Any, ...]] = {}
            total_nodes = len(order)
            for node_index, node_id in enumerate(order):
                ctx.check_cancelled()
                node = node_by_id[node_id]

                def overall_fraction(local: float) -> float:
                    if total_nodes <= 0:
                        return 1.0
                    return min(1.0, (node_index + local) / total_nodes)

                ctx.emit_progress(node_id, overall_fraction(0.0), f"Running {node.type}...")
                node_cls = get_node_class(node.type)
                instance = node_cls()
                instance.bind_context(ctx)

                kwargs = dict(node.widgets)
                for input_idx, (src_id, src_out_idx) in sorted(inputs_map.get(node_id, {}).items()):
                    src_outputs = node_outputs.get(src_id)
                    if src_outputs is None:
                        raise RuntimeError(f"Missing upstream output for {node_id}")
                    if src_out_idx >= len(src_outputs):
                        src_type = node_by_id[src_id].type
                        raise RuntimeError(
                            f"{node.type} needs output slot {src_out_idx} from {src_type}, "
                            f"but only {len(src_outputs)} slot(s) are available. "
                            "Re-render the workflow (Shift+R) to refresh cached stems."
                        )
                    kwargs[_input_name(node_cls, input_idx)] = src_outputs[src_out_idx]

                signature = compute_node_signature(node.type, dict(node.widgets), kwargs)
                cacheable = getattr(node_cls, "CACHEABLE", True)
                cached_state = (
                    None
                    if force_rebuild or not cacheable
                    else ctx.cache.read_node_cache(workflow.id, node_id)
                )
                cache_hit = False
                cached_output_meta = (
                    self._normalize_output_meta(node_cls, cached_state.get("output"))
                    if cached_state
                    else None
                )
                if cached_state and cached_state.get("signature") == signature and cached_output_meta:
                    result = self._result_from_meta(cached_output_meta, node_cls=node_cls)
                    if result is not None:
                        node_outputs[node_id] = result
                        outputs[node_id] = cached_output_meta
                        cache_hit = True
                        ctx.emit_progress(node_id, overall_fraction(1.0), f"Cache hit {node.type}")
                        manifest_output = attach_signal_metadata(self.cache, cached_output_meta)
                        if cached_state.get("output", {}).get("type") == "STEMS":
                            ctx.cache.write_node_cache(
                                workflow.id,
                                node_id,
                                signature=signature,
                                output_meta=cached_output_meta,
                            )
                        manifest_nodes.append(
                            {
                                "node_id": node_id,
                                "type": node.type,
                                "cache_hit": True,
                                "output": manifest_output,
                            }
                        )
                        continue

                run_fn = getattr(instance, node_cls.FUNCTION)
                if node_cls.run_in_worker:
                    from groovy.executor.worker import run_ai_worker

                    raw_outputs = run_ai_worker(
                        node.type,
                        kwargs,
                        self.project_dir,
                        cancel_check=ctx.cancel_check,
                    )
                    result = self._result_from_worker(raw_outputs)
                else:
                    result = run_fn(**kwargs)
                if not isinstance(result, tuple):
                    result = (result,)

                node_outputs[node_id] = result
                ctx.emit_progress(node_id, overall_fraction(1.0), f"Completed {node.type}")

                output_meta = self._output_meta_from_result(
                    result,
                    node=node,
                    node_cls=node_cls,
                    ctx=ctx,
                    workflow=workflow,
                    kwargs=kwargs,
                )
                if output_meta:
                    outputs[node_id] = output_meta

                manifest_output = attach_signal_metadata(self.cache, output_meta) if output_meta else None
                manifest_nodes.append(
                    {
                        "node_id": node_id,
                        "type": node.type,
                        "cache_hit": cache_hit,
                        "output": manifest_output,
                    }
                )
                if output_meta and cacheable:
                    ctx.cache.write_node_cache(
                        workflow.id, node_id, signature=signature, output_meta=output_meta
                    )

            manifest = {
                "job_id": job_id,
                "workflow_id": workflow.id,
                "started_at": started_at,
                "completed_at": datetime.now(UTC).isoformat(),
                "executor_version": EXECUTOR_VERSION,
                "groovy_version": GROOVY_VERSION,
                "nodes": manifest_nodes,
                "outputs": outputs,
            }
            manifest_path = self.cache.write_manifest(job_id, manifest)
            return ExecutionResult(
                job_id=job_id,
                status="completed",
                outputs=outputs,
                manifest_path=str(manifest_path),
            )
        except JobCancelled as exc:
            return ExecutionResult(
                job_id=job_id,
                status="cancelled",
                outputs=outputs,
                error=exc.message,
            )
        except Exception as exc:
            return ExecutionResult(job_id=job_id, status="failed", error=str(exc), outputs=outputs)

    def _write_provenance(
        self,
        ctx: JobContext,
        workflow: Workflow,
        node: NodeInstance,
        buffer: AudioBuffer,
        kwargs: dict[str, Any],
        node_cls: type,
    ) -> None:
        refs = parent_refs(kwargs)
        parent_records = [read_provenance(ctx.cache, ref["cache_id"]) or {} for ref in refs]
        model_id = node.widgets.get("model")
        model_metadata = (
            self.model_metadata_resolver(str(model_id))
            if model_id and self.model_metadata_resolver
            else None
        )
        workflow_json = json.dumps(
            workflow.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
        )
        record = build_record(
            cache_id=buffer.id,
            content_hash=buffer.content_hash,
            node_id=node.id,
            node_type=node.type,
            widgets=dict(node.widgets),
            node_cls=node_cls,
            job_id=ctx.job_id,
            workflow_id=workflow.id,
            workflow_title=workflow.metadata.title,
            workflow_hash=f"sha256:{hashlib.sha256(workflow_json.encode('utf-8')).hexdigest()}",
            groovy_version=GROOVY_VERSION,
            executor_version=EXECUTOR_VERSION,
            parent_records=parent_records,
            parent_refs_list=refs,
            model_metadata=model_metadata,
            prompt_policy=self.provenance_prompt_policy,
        )
        ctx.cache.write_provenance(buffer.id, record)

    def _normalize_output_meta(
        self,
        node_cls: type,
        output_meta: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not output_meta:
            return None

        return_types = getattr(node_cls, "RETURN_TYPES", ())
        if len(return_types) <= 1:
            return output_meta

        if output_meta.get("type") == "MULTI":
            slots = output_meta.get("outputs") or []
            if len(slots) == len(return_types):
                return output_meta
            return None

        if output_meta.get("type") == "STEMS" and output_meta.get("stems_id"):
            stems = self.cache.load_stems(str(output_meta["stems_id"]))
            names = getattr(node_cls, "OUTPUT_NAMES", ()) or tuple(stems.stems.keys())
            slots: list[dict[str, Any]] = []
            for name in names:
                buf = stems.stems.get(name)
                if buf is not None:
                    slots.append({"type": "AUDIO", "cache_id": buf.id, "name": name})
            if len(slots) == len(return_types):
                return {"type": "MULTI", "outputs": slots}
            return None

        # Stale single-slot cache for a multi-outlet node (e.g. DeepfakeDetect
        # used to persist AUTHENTICITY only, dropping the AUDIO pass-through).
        return None

    def _result_from_worker(self, raw_outputs: list[dict[str, Any]]) -> tuple[Any, ...]:
        result: list[Any] = []
        for item in raw_outputs:
            if item.get("type") == "AUDIO" and item.get("cache_id"):
                buffer, _ = self.cache.load_audio(item["cache_id"])
                result.append(buffer)
            elif item.get("type") == "STEMS" and item.get("stems_id"):
                result.append(self.cache.load_stems(item["stems_id"]))
            elif item.get("type") == "MIDI" and item.get("midi_id"):
                result.append(self.cache.load_midi(item["midi_id"]))
            elif item.get("type") == "AUTHENTICITY" and item.get("authenticity_id"):
                result.append(self.cache.load_authenticity(item["authenticity_id"]))
            elif item.get("type") == "SAMPLE_CHECK" and item.get("sample_check_id"):
                result.append(self.cache.load_sample_check(item["sample_check_id"]))
            elif item.get("type") == "AUTOMATION" and item.get("automation_id"):
                result.append(self.cache.load_automation(item["automation_id"]))
            elif item.get("type") == "AMBISONICS" and item.get("ambisonics_id"):
                buffer, _ = self.cache.load_ambisonics(item["ambisonics_id"])
                result.append(buffer)
            elif item.get("type") == "OBA" and item.get("oba_id"):
                result.append(self.cache.load_object_scene(item["oba_id"]))
            elif item.get("type") == "TRAJECTORY" and item.get("trajectory_id"):
                result.append(self.cache.load_trajectory(item["trajectory_id"]))
            elif item.get("type") == "OSC" and item.get("osc_id"):
                result.append(self.cache.load_osc(item["osc_id"]))
            elif item.get("type") == "TEXT":
                result.append(str(item.get("text", "")))
            elif item.get("type") == "STRING" and item.get("path"):
                result.append(str(item["path"]))
        return tuple(result)

    def _result_from_meta(
        self,
        output_meta: dict[str, Any],
        *,
        node_cls: type | None = None,
    ) -> tuple[Any, ...] | None:
        meta = self._normalize_output_meta(node_cls, output_meta) if node_cls else output_meta
        if not meta:
            return None
        if meta.get("type") == "MULTI":
            slots: list[Any] = []
            for slot in meta.get("outputs", []):
                loaded = self._result_from_worker([slot])
                if not loaded:
                    return None
                slots.append(loaded[0])
            return tuple(slots) if slots else None
        result = self._result_from_worker([meta])
        return result if result else None

    def _slot_meta_from_item(
        self,
        item: Any,
        *,
        node: NodeInstance,
        node_cls: type,
        ctx: JobContext,
        workflow: Workflow,
        kwargs: dict[str, Any],
        name: str | None = None,
    ) -> dict[str, Any] | None:
        if isinstance(item, SampleCheckReport):
            meta = {"type": "SAMPLE_CHECK", "sample_check_id": item.id}
        elif isinstance(item, AuthenticityReport):
            meta = {"type": "AUTHENTICITY", "authenticity_id": item.id}
        elif isinstance(item, MidiBuffer):
            meta = {"type": "MIDI", "midi_id": item.id}
        elif isinstance(item, AutomationBuffer):
            meta = {"type": "AUTOMATION", "automation_id": item.id}
        elif isinstance(item, AmbisonicBuffer):
            meta = {"type": "AMBISONICS", "ambisonics_id": item.id}
        elif isinstance(item, ObjectScene):
            meta = {"type": "OBA", "oba_id": item.id}
        elif isinstance(item, TrajectoryBuffer):
            meta = {"type": "TRAJECTORY", "trajectory_id": item.id}
        elif isinstance(item, OscBuffer):
            meta = {"type": "OSC", "osc_id": item.id}
        elif isinstance(item, AudioBuffer):
            if not (
                getattr(node_cls, "PROVENANCE_PASSTHROUGH", False)
                and ctx.cache.read_provenance(item.id)
            ):
                self._write_provenance(ctx, workflow, node, item, kwargs, node_cls)
            meta = {"cache_id": item.id, "type": "AUDIO"}
            if node.type == "Preview" and kwargs.get("text") is not None:
                meta["text"] = str(kwargs["text"])
        elif isinstance(item, StemsBuffer):
            meta = {
                "type": "STEMS",
                "stems_id": item.id,
                "stems": {stem_name: buf.id for stem_name, buf in item.stems.items()},
            }
        elif isinstance(item, str):
            if node.type == "SaveAudio":
                output_path = Path(item)
                provenance_path = output_path.with_name(f"{output_path.stem}.provenance.json")
                if not provenance_path.is_file():
                    raise RuntimeError(
                        f"SaveAudio wrote audio but provenance sidecar is missing: "
                        f"{provenance_path}"
                    )
                sidecar = json.loads(provenance_path.read_text())
                meta = {
                    "type": "STRING",
                    "path": item,
                    "provenance_path": str(provenance_path),
                    "content_credentials": sidecar.get(
                        "content_credentials",
                        {"status": "off", "mode": "off", "verified": False},
                    ),
                }
            else:
                meta = {"type": "TEXT", "text": item}
        else:
            return None
        if name:
            meta["name"] = name
        return meta

    def _output_meta_from_result(
        self,
        result: tuple[Any, ...],
        *,
        node: NodeInstance,
        node_cls: type,
        ctx: JobContext,
        workflow: Workflow,
        kwargs: dict[str, Any],
    ) -> dict[str, Any] | None:
        names = getattr(node_cls, "OUTPUT_NAMES", None) or tuple(
            f"output_{index}" for index in range(len(result))
        )
        slots: list[dict[str, Any]] = []
        for index, item in enumerate(result):
            name = names[index] if index < len(names) else f"output_{index}"
            slot = self._slot_meta_from_item(
                item,
                node=node,
                node_cls=node_cls,
                ctx=ctx,
                workflow=workflow,
                kwargs=kwargs,
                name=name if len(result) > 1 else None,
            )
            if slot is None:
                continue
            slots.append(slot)

        if len(slots) > 1:
            return {"type": "MULTI", "outputs": slots}
        if len(slots) == 1:
            slot = dict(slots[0])
            slot.pop("name", None)
            return slot
        return None


def _input_name(node_cls: type, index: int) -> str:
    inputs = node_cls.INPUT_TYPES()
    names: list[str] = []
    for section in ("required", "optional"):
        for name, spec in inputs.get(section, {}).items():
            if not isinstance(spec, tuple) or not spec:
                continue
            socket_type = spec[0]
            if socket_type in {
                "AUDIO",
                "STEMS",
                "MIDI",
                "AUTHENTICITY",
                "SAMPLE_CHECK",
                "TEXT",
                "AUTOMATION",
                "AMBISONICS",
                "OBA",
                "OSC",
                "TRAJECTORY",
            }:
                names.append(name)
            elif socket_type == "FLOAT" and name in {"gain_a", "gain_b", "value"}:
                names.append(name)
    if index < len(names):
        return names[index]
    return f"input_{index}"


def _topological_order(nodes: list[NodeInstance], links: list[Link]) -> list[str]:
    indegree: dict[str, int] = {n.id: 0 for n in nodes}
    adj: dict[str, list[str]] = defaultdict(list)
    for link in links:
        src = str(link.from_[0])
        dst = str(link.to[0])
        adj[src].append(dst)
        indegree[dst] += 1
    queue = deque([nid for nid, deg in indegree.items() if deg == 0])
    order: list[str] = []
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for nxt in adj[node_id]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(nodes):
        raise ValueError("Graph has cycles")
    return order


def _build_inputs_map(links: list[Link]) -> dict[str, dict[int, tuple[str, int]]]:
    result: dict[str, dict[int, tuple[str, int]]] = defaultdict(dict)
    for link in links:
        src_id = str(link.from_[0])
        src_idx = int(link.from_[1])
        dst_id = str(link.to[0])
        dst_idx = int(link.to[1])
        result[dst_id][dst_idx] = (src_id, src_idx)
    return result


def _upstream_closure(target_nodes: list[str], links: list[Link]) -> set[str]:
    reverse: dict[str, list[str]] = defaultdict(list)
    for link in links:
        reverse[str(link.to[0])].append(str(link.from_[0]))

    needed: set[str] = set()
    stack = list(target_nodes)
    while stack:
        node_id = stack.pop()
        if node_id in needed:
            continue
        needed.add(node_id)
        stack.extend(reverse.get(node_id, []))
    return needed


def cache_key(node_type: str, widgets: dict, input_ids: list[str]) -> str:
    payload = json.dumps(
        {"type": node_type, "widgets": widgets, "inputs": input_ids, "executor": EXECUTOR_VERSION},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
