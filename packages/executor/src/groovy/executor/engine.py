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

from groovy.executor.audio import AudioBuffer, StemsBuffer
from groovy.executor.cache import CacheStore
from groovy.executor.provenance import build_record, parent_refs, read_provenance
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
    on_progress: Callable[[str, str, float, str], None] | None = None

    def emit_progress(self, node_id: str, fraction: float, message: str) -> None:
        if self.on_progress:
            self.on_progress(self.job_id, node_id, fraction, message)


@dataclass
class ExecutionResult:
    job_id: str
    status: str
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    manifest_path: str | None = None
    error: str | None = None


class Executor:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.cache = CacheStore(project_dir)

    def execute(
        self,
        workflow: Workflow,
        *,
        target_nodes: list[str] | None = None,
        force_rebuild: bool = False,
        on_progress: Callable[[str, str, float, str], None] | None = None,
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
            on_progress=on_progress,
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
            for node_id in order:
                node = node_by_id[node_id]
                ctx.emit_progress(node_id, 0.0, f"Running {node.type}...")
                node_cls = get_node_class(node.type)
                instance = node_cls()
                instance.bind_context(ctx)

                kwargs = dict(node.widgets)
                for input_idx, (src_id, src_out_idx) in sorted(inputs_map.get(node_id, {}).items()):
                    src_outputs = node_outputs.get(src_id)
                    if src_outputs is None:
                        raise RuntimeError(f"Missing upstream output for {node_id}")
                    kwargs[_input_name(node_cls, input_idx)] = src_outputs[src_out_idx]

                run_fn = getattr(instance, node_cls.FUNCTION)
                if node_cls.run_in_worker:
                    from groovy.executor.worker import run_ai_worker

                    raw_outputs = run_ai_worker(node.type, kwargs, self.project_dir)
                    result = self._result_from_worker(raw_outputs)
                else:
                    result = run_fn(**kwargs)
                if not isinstance(result, tuple):
                    result = (result,)

                node_outputs[node_id] = result
                ctx.emit_progress(node_id, 1.0, f"Completed {node.type}")

                cache_id = None
                output_meta: dict[str, Any] | None = None
                for item in result:
                    if isinstance(item, AudioBuffer):
                        cache_id = item.id
                        output_meta = {"cache_id": cache_id, "type": "AUDIO"}
                        outputs[node_id] = output_meta
                        if not (
                            getattr(node_cls, "PROVENANCE_PASSTHROUGH", False)
                            and ctx.cache.read_provenance(cache_id)
                        ):
                            self._write_provenance(ctx, workflow, node, item, kwargs, node_cls)
                        break
                    if isinstance(item, StemsBuffer):
                        output_meta = {
                            "type": "STEMS",
                            "stems_id": item.id,
                            "stems": {name: buf.id for name, buf in item.stems.items()},
                        }
                        outputs[node_id] = output_meta
                        break
                    if isinstance(item, str):
                        output_meta = {"type": "TEXT", "text": item}
                        outputs[node_id] = output_meta
                        break

                manifest_nodes.append(
                    {
                        "node_id": node_id,
                        "type": node.type,
                        "cache_hit": False,
                        "output": output_meta,
                    }
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
        except Exception as exc:
            return ExecutionResult(job_id=job_id, status="failed", error=str(exc))

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
        record = build_record(
            cache_id=buffer.id,
            content_hash=buffer.content_hash,
            node_id=node.id,
            node_type=node.type,
            widgets=dict(node.widgets),
            node_cls=node_cls,
            job_id=ctx.job_id,
            workflow_id=workflow.id,
            groovy_version=GROOVY_VERSION,
            executor_version=EXECUTOR_VERSION,
            parent_records=parent_records,
            parent_refs_list=refs,
        )
        ctx.cache.write_provenance(buffer.id, record)

    def _result_from_worker(self, raw_outputs: list[dict[str, Any]]) -> tuple[Any, ...]:
        result: list[Any] = []
        for item in raw_outputs:
            if item.get("type") == "AUDIO" and item.get("cache_id"):
                buffer, _ = self.cache.load_audio(item["cache_id"])
                result.append(buffer)
            elif item.get("type") == "STEMS" and item.get("stems_id"):
                result.append(self.cache.load_stems(item["stems_id"]))
            elif item.get("type") == "TEXT":
                result.append(str(item.get("text", "")))
        return tuple(result)


def _input_name(node_cls: type, index: int) -> str:
    inputs = node_cls.INPUT_TYPES()
    names: list[str] = []
    for section in ("required", "optional"):
        for name, spec in inputs.get(section, {}).items():
            if not isinstance(spec, tuple) or not spec:
                continue
            socket_type = spec[0]
            if socket_type in {"AUDIO", "STEMS", "MIDI", "AUTHENTICITY"}:
                names.append(name)
            elif socket_type == "FLOAT" and section == "optional" and name.startswith("gain_"):
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
