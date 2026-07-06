from __future__ import annotations

from collections import defaultdict, deque

from groovy.schema.models import Link, NodeInstance, ValidationError, ValidationResult, Workflow

MAX_NODES = 256
MAX_LINKS = 512
MAX_GRAPH_DEPTH = 64


def validate_workflow(
    workflow: Workflow,
    *,
    known_node_types: set[str] | None = None,
) -> ValidationResult:
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    if len(workflow.nodes) > MAX_NODES:
        errors.append(
            ValidationError(code="TOO_MANY_NODES", message=f"Max {MAX_NODES} nodes allowed")
        )
    if len(workflow.links) > MAX_LINKS:
        errors.append(
            ValidationError(code="TOO_MANY_LINKS", message=f"Max {MAX_LINKS} links allowed")
        )

    node_by_id: dict[str, NodeInstance] = {n.id: n for n in workflow.nodes}
    if len(node_by_id) != len(workflow.nodes):
        errors.append(ValidationError(code="DUPLICATE_NODE_ID", message="Duplicate node ids"))

    if known_node_types is not None:
        for node in workflow.nodes:
            if node.type not in known_node_types:
                errors.append(
                    ValidationError(
                        code="UNKNOWN_NODE_TYPE",
                        message=f"Unknown node type: {node.type}",
                        node_id=node.id,
                    )
                )

    inputs_per_slot: dict[tuple[str, int], str] = {}
    for link in workflow.links:
        src_id, src_idx = _parse_endpoint(link.from_, "from")
        dst_id, dst_idx = _parse_endpoint(link.to, "to")

        if src_id not in node_by_id:
            errors.append(
                ValidationError(
                    code="INVALID_LINK",
                    message=f"Unknown source node {src_id}",
                    link_id=link.id,
                )
            )
            continue
        if dst_id not in node_by_id:
            errors.append(
                ValidationError(
                    code="INVALID_LINK",
                    message=f"Unknown target node {dst_id}",
                    link_id=link.id,
                )
            )
            continue

        slot = (dst_id, dst_idx)
        if slot in inputs_per_slot:
            errors.append(
                ValidationError(
                    code="MULTIPLE_INPUTS",
                    message=f"Input slot {dst_id}[{dst_idx}] already connected",
                    link_id=link.id,
                )
            )
        else:
            inputs_per_slot[slot] = link.id

    cycle_nodes = _find_cycle_nodes(workflow.nodes, workflow.links)
    if cycle_nodes:
        errors.append(
            ValidationError(
                code="CYCLE_DETECTED",
                message=f"Graph contains cycle involving: {', '.join(sorted(cycle_nodes))}",
            )
        )

    depth = _graph_depth(workflow.nodes, workflow.links)
    if depth > MAX_GRAPH_DEPTH:
        errors.append(
            ValidationError(
                code="GRAPH_TOO_DEEP",
                message=f"Graph depth {depth} exceeds max {MAX_GRAPH_DEPTH}",
            )
        )

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def _parse_endpoint(endpoint: list[str | int], label: str) -> tuple[str, int]:
    if len(endpoint) != 2:
        raise ValueError(f"Invalid {label} endpoint: {endpoint}")
    node_id = str(endpoint[0])
    idx = int(endpoint[1])
    return node_id, idx


def _build_adjacency(links: list[Link]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = defaultdict(list)
    for link in links:
        src_id, _ = _parse_endpoint(link.from_, "from")
        dst_id, _ = _parse_endpoint(link.to, "to")
        adj[src_id].append(dst_id)
    return adj


def _find_cycle_nodes(nodes: list[NodeInstance], links: list[Link]) -> set[str]:
    adj = _build_adjacency(links)
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle: set[str] = set()

    def dfs(node_id: str) -> bool:
        if node_id in visiting:
            cycle.add(node_id)
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for nxt in adj.get(node_id, []):
            if dfs(nxt):
                cycle.add(node_id)
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    for node in nodes:
        dfs(node.id)
    return cycle


def _graph_depth(nodes: list[NodeInstance], links: list[Link]) -> int:
    indegree: dict[str, int] = {n.id: 0 for n in nodes}
    adj = _build_adjacency(links)
    for targets in adj.values():
        for t in targets:
            indegree[t] = indegree.get(t, 0) + 1

    queue = deque([nid for nid, deg in indegree.items() if deg == 0])
    depth = 0
    remaining = len(indegree)

    while queue:
        depth += 1
        for _ in range(len(queue)):
            node_id = queue.popleft()
            remaining -= 1
            for nxt in adj.get(node_id, []):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

    if remaining > 0:
        return MAX_GRAPH_DEPTH + 1
    return depth
