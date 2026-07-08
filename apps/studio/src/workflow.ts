import type { Edge, Node } from "@xyflow/react";
import type { JobOutput, NodeRenderStatus, NodeSchema, Workflow, WorkflowGroup, WorkflowLink, WorkflowModule, WorkflowNode } from "./types";
import type { GroovyGroupNodeData } from "./components/ModuleGroupNode";
import type { GroovyNodeData } from "./components/GroovyFlowNode";
import { edgeTypeClass, socketTypeColor } from "./socketTypes";

export function previewCacheId(output?: JobOutput): string | null {
  if (!output?.cache_id) return null;
  return output.cache_id;
}

/** Preserve React Flow interaction state when syncing derived nodes from workflow. */
export function mergeFlowNodes<T extends Node>(current: T[], next: T[]): T[] {
  if (next.length === 0 && current.length > 0) {
    return current;
  }
  const merged: T[] = [];
  for (const fresh of next) {
    const existing = current.find((node) => node.id === fresh.id);
    if (!existing) {
      merged.push(fresh);
      continue;
    }
    merged.push({
      ...existing,
      data: fresh.data,
      type: fresh.type,
      hidden: fresh.hidden,
      position: existing.dragging ? existing.position : fresh.position,
    });
  }
  return merged;
}

/** Preserve React Flow interaction state when syncing derived edges from workflow. */
export function mergeFlowEdges<T extends Edge>(current: T[], next: T[]): T[] {
  if (next.length === 0 && current.length > 0) {
    return current;
  }
  const merged: T[] = [];
  for (const fresh of next) {
    const existing = current.find((edge) => edge.id === fresh.id);
    if (!existing) {
      merged.push(fresh);
      continue;
    }
    merged.push({
      ...existing,
      source: fresh.source,
      target: fresh.target,
      label: fresh.label,
      className: fresh.className,
      animated: fresh.animated,
      hidden: fresh.hidden,
    });
  }
  return merged;
}

export function proxyNodeId(groupId: string): string {
  return `proxy_${groupId}`;
}

export function collapsedMemberIds(workflow: Workflow): Set<string> {
  const hidden = new Set<string>();
  for (const group of workflow.groups) {
    if (!group.collapsed) continue;
    for (const nodeId of group.node_ids) {
      hidden.add(nodeId);
    }
  }
  return hidden;
}

export function groupForNode(workflow: Workflow, nodeId: string): WorkflowGroup | null {
  return workflow.groups.find((group) => group.node_ids.includes(nodeId)) ?? null;
}

export function groupForSelection(workflow: Workflow, nodeIds: string[]): WorkflowGroup | null {
  if (nodeIds.length === 0) return null;
  const groups = nodeIds.map((id) => groupForNode(workflow, id)).filter(Boolean) as WorkflowGroup[];
  if (groups.length === 0) return null;
  const first = groups[0];
  return groups.every((group) => group.id === first.id) ? first : null;
}

function groupCentroid(workflow: Workflow, group: WorkflowGroup): { x: number; y: number } {
  const nodes = workflow.nodes.filter((node) => group.node_ids.includes(node.id));
  if (nodes.length === 0) {
    return group.proxy_pos ?? { x: 120, y: 120 };
  }
  const x = nodes.reduce((sum, node) => sum + (node.pos?.x ?? 0), 0) / nodes.length;
  const y = nodes.reduce((sum, node) => sum + (node.pos?.y ?? 0), 0) / nodes.length;
  return { x, y };
}

export function toggleGroupCollapsed(workflow: Workflow, groupId: string): Workflow {
  return {
    ...workflow,
    groups: workflow.groups.map((group) => {
      if (group.id !== groupId) return group;
      const collapsed = !group.collapsed;
      return {
        ...group,
        collapsed,
        proxy_pos: collapsed ? group.proxy_pos ?? groupCentroid(workflow, group) : group.proxy_pos,
      };
    }),
  };
}

export function rewriteLinksForCollapsedGroups(workflow: Workflow): WorkflowLink[] {
  const collapsedGroups = workflow.groups.filter((group) => group.collapsed);
  if (collapsedGroups.length === 0) return workflow.links;

  const memberToGroup = new Map<string, WorkflowGroup>();
  for (const group of collapsedGroups) {
    for (const nodeId of group.node_ids) {
      memberToGroup.set(nodeId, group);
    }
  }

  const rewritten: WorkflowLink[] = [];
  for (const link of workflow.links) {
    const fromId = String(link.from[0]);
    const toId = String(link.to[0]);
    const fromGroup = memberToGroup.get(fromId);
    const toGroup = memberToGroup.get(toId);
    if (fromGroup && toGroup && fromGroup.id === toGroup.id) {
      continue;
    }
    if (fromGroup && !toGroup) {
      rewritten.push({ ...link, from: [proxyNodeId(fromGroup.id), link.from[1]] });
    } else if (!fromGroup && toGroup) {
      rewritten.push({ ...link, to: [proxyNodeId(toGroup.id), link.to[1]] });
    } else if (fromGroup && toGroup && fromGroup.id !== toGroup.id) {
      rewritten.push({
        ...link,
        id: `proxy_${link.id}`,
        from: [proxyNodeId(fromGroup.id), 0],
        to: [proxyNodeId(toGroup.id), 0],
      });
    } else {
      rewritten.push(link);
    }
  }
  return rewritten;
}

export function workflowToFlowNodes(
  workflow: Workflow,
  nodeStatus: Record<string, NodeRenderStatus>,
  outputs?: Record<string, JobOutput>,
): Node<GroovyNodeData | GroovyGroupNodeData>[] {
  const hidden = collapsedMemberIds(workflow);
  const nodes: Node<GroovyNodeData | GroovyGroupNodeData>[] = workflow.nodes
    .filter((node) => !hidden.has(node.id))
    .map((n: WorkflowNode) => ({
      id: n.id,
      type: "groovy",
      position: n.pos ?? { x: 0, y: 0 },
      data: {
        label: n.type,
        status: nodeStatus[n.id] ?? "idle",
        nodeId: n.id,
        canAudition: !!previewCacheId(outputs?.[n.id]),
      },
    }));

  for (const group of workflow.groups) {
    if (!group.collapsed) continue;
    const position = group.proxy_pos ?? groupCentroid(workflow, group);
    nodes.push({
      id: proxyNodeId(group.id),
      type: "groovyGroup",
      position,
      data: {
        label: group.title,
        groupId: group.id,
        nodeCount: group.node_ids.length,
      },
    });
  }

  return nodes;
}

export function workflowToFlowEdges(workflow: Workflow, activeEdgeIds?: Set<string>): Edge[] {
  const links = rewriteLinksForCollapsedGroups(workflow);
  return links.map((l: WorkflowLink) => {
    const typeClass = edgeTypeClass(l.type);
    const active = activeEdgeIds?.has(l.id) ?? false;
    const color = socketTypeColor(l.type);
    return {
      id: l.id,
      source: l.from[0],
      target: l.to[0],
      label: l.type,
      className: [typeClass, active ? "groovy-edge--active" : ""].filter(Boolean).join(" "),
      animated: active,
      style: { stroke: color, strokeWidth: 2 },
      labelStyle: { fill: color, fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: "#151820", fillOpacity: 0.92 },
      labelBgPadding: [4, 3] as [number, number],
      labelBgBorderRadius: 3,
    };
  });
}

export type WiredInputRow = {
  index: number;
  name: string;
  type: string;
  optional?: boolean;
  description?: string;
  connected: boolean;
  sourceNode?: WorkflowNode;
  linkType?: string;
};

/** Map schema input sockets to workflow links by slot index. */
export function wiredInputsForNode(
  workflow: Workflow,
  nodeId: string,
  inputs: NodeSchema["inputs"],
): WiredInputRow[] {
  return inputs.map((spec, index) => {
    const link = workflow.links.find((item) => item.to[0] === nodeId && item.to[1] === index);
    const sourceNode = link ? workflow.nodes.find((node) => node.id === link.from[0]) : undefined;
    return {
      index,
      name: spec.name,
      type: spec.type,
      optional: spec.optional,
      description: spec.description,
      connected: Boolean(link),
      sourceNode,
      linkType: link?.type,
    };
  });
}

export function flowNodesSyncKey(nodes: Node[]): string {
  return nodes
    .map(
      (node) =>
        `${node.id}:${node.type}:${node.hidden ? 1 : 0}:${node.position.x},${node.position.y}:${JSON.stringify(node.data)}`,
    )
    .join("|");
}

export function flowEdgesSyncKey(edges: Edge[]): string {
  return edges
    .map((edge) => `${edge.id}:${edge.source}->${edge.target}:${edge.className ?? ""}:${edge.animated ? 1 : 0}`)
    .join("|");
}

export function workflowToFlow(
  workflow: Workflow,
  nodeStatus: Record<string, NodeRenderStatus>,
  outputs?: Record<string, JobOutput>,
  activeEdgeIds?: Set<string>,
): { nodes: Node<GroovyNodeData | GroovyGroupNodeData>[]; edges: Edge[] } {
  return {
    nodes: workflowToFlowNodes(workflow, nodeStatus, outputs),
    edges: workflowToFlowEdges(workflow, activeEdgeIds),
  };
}

export function syncPositions(workflow: Workflow, nodes: Node[]): Workflow {
  const hidden = collapsedMemberIds(workflow);
  const posById = new Map(nodes.map((n) => [n.id, n.position]));
  return {
    ...workflow,
    nodes: workflow.nodes.map((node: WorkflowNode) => {
      if (hidden.has(node.id)) return node;
      const pos = posById.get(node.id);
      return pos ? { ...node, pos: { x: pos.x, y: pos.y } } : node;
    }),
    groups: workflow.groups.map((group) => {
      if (!group.collapsed) return group;
      const proxyId = proxyNodeId(group.id);
      const pos = posById.get(proxyId);
      return pos ? { ...group, proxy_pos: { x: pos.x, y: pos.y } } : group;
    }),
  };
}

export function topologicalNodeOrder(workflow: Workflow): string[] {
  const indegree = new Map(workflow.nodes.map((node) => [node.id, 0]));
  const adjacency = new Map(workflow.nodes.map((node) => [node.id, [] as string[]]));
  for (const link of workflow.links) {
    const source = link.from[0];
    const target = link.to[0];
    indegree.set(target, (indegree.get(target) ?? 0) + 1);
    adjacency.get(source)?.push(target);
  }
  const queue = workflow.nodes
    .filter((node) => (indegree.get(node.id) ?? 0) === 0)
    .map((node) => node.id);
  const order: string[] = [];
  while (queue.length > 0) {
    const nodeId = queue.shift()!;
    order.push(nodeId);
    for (const nextId of adjacency.get(nodeId) ?? []) {
      indegree.set(nextId, (indegree.get(nextId) ?? 1) - 1);
      if (indegree.get(nextId) === 0) {
        queue.push(nextId);
      }
    }
  }
  return order;
}

function hopDiffers(
  nodeA: string,
  nodeB: string,
  outputs: Record<string, JobOutput>,
): [string, string] | null {
  const outputA = outputs[nodeA];
  const outputB = outputs[nodeB];
  if (outputA?.cache_id && outputB?.cache_id && outputA.cache_id !== outputB.cache_id) {
    return [nodeA, nodeB];
  }
  return null;
}

function findDistinctHop(
  order: string[],
  outputs: Record<string, JobOutput>,
  selectedA: string,
  selectedB: string,
): [string, string] | null {
  const indexA = order.indexOf(selectedA);
  const indexB = order.indexOf(selectedB);
  if (indexA < 0 || indexB < 0) return null;
  const lo = Math.min(indexA, indexB);
  const hi = Math.max(indexA, indexB);

  for (let index = hi - 1; index >= lo; index--) {
    const hop = hopDiffers(order[index], order[index + 1], outputs);
    if (hop) return hop;
  }
  for (let index = lo; index > 0; index--) {
    const hop = hopDiffers(order[index - 1], order[index], outputs);
    if (hop) return hop;
  }
  for (let index = order.length - 2; index >= 0; index--) {
    const left = order[index];
    const right = order[index + 1];
    if (
      (left === selectedA || left === selectedB || right === selectedA || right === selectedB) &&
      hopDiffers(left, right, outputs)
    ) {
      return hopDiffers(left, right, outputs);
    }
  }
  return null;
}

export type CompareHop = {
  a: string;
  b: string;
  label: string;
};

export type CompareResolution = {
  pair: Array<{ node: WorkflowNode; output: JobOutput }>;
  note: string | null;
  missingRender: boolean;
};

export function listDistinctChainHops(
  workflow: Workflow,
  outputs?: Record<string, JobOutput>,
): CompareHop[] {
  if (!outputs) return [];
  const order = topologicalNodeOrder(workflow);
  const hops: CompareHop[] = [];
  for (let index = 0; index < order.length - 1; index++) {
    const nodeA = order[index];
    const nodeB = order[index + 1];
    if (!hopDiffers(nodeA, nodeB, outputs)) continue;
    const left = workflow.nodes.find((node) => node.id === nodeA);
    const right = workflow.nodes.find((node) => node.id === nodeB);
    hops.push({
      a: nodeA,
      b: nodeB,
      label: `${left?.type ?? nodeA} → ${right?.type ?? nodeB}`,
    });
  }
  return hops;
}

export function resolveComparePair(
  workflow: Workflow,
  outputs: Record<string, JobOutput> | undefined,
  selectedIds: string[],
): CompareResolution | null {
  if (!outputs || selectedIds.length !== 2) return null;
  const [firstId, secondId] = selectedIds;
  const nodeA = workflow.nodes.find((node) => node.id === firstId);
  const nodeB = workflow.nodes.find((node) => node.id === secondId);
  if (!nodeA || !nodeB) return null;

  const outputA = outputs[firstId];
  const outputB = outputs[secondId];
  if (!outputA?.cache_id || !outputB?.cache_id) {
    return {
      pair: [],
      note: "Render the workflow first (Play or Shift+R) so both nodes have cached audio.",
      missingRender: true,
    };
  }

  if (outputA.cache_id !== outputB.cache_id) {
    return {
      pair: [
        { node: nodeA, output: outputA },
        { node: nodeB, output: outputB },
      ],
      note: null,
      missingRender: false,
    };
  }

  const order = topologicalNodeOrder(workflow);
  const hop = findDistinctHop(order, outputs, firstId, secondId);
  if (hop) {
    const [hopA, hopB] = hop;
    const hopNodeA = workflow.nodes.find((node) => node.id === hopA);
    const hopNodeB = workflow.nodes.find((node) => node.id === hopB);
    const hopOutputA = outputs[hopA];
    const hopOutputB = outputs[hopB];
    if (!hopNodeA || !hopNodeB || !hopOutputA?.cache_id || !hopOutputB?.cache_id) {
      return null;
    }
    return {
      pair: [
        { node: hopNodeA, output: hopOutputA },
        { node: hopNodeB, output: hopOutputB },
      ],
      note:
        `${nodeA.type} (${firstId}) and ${nodeB.type} (${secondId}) share the same cached audio. ` +
        `Comparing ${hopNodeA.type} (${hopA}) → ${hopNodeB.type} (${hopB}) instead.`,
      missingRender: false,
    };
  }

  return {
    pair: [
      { node: nodeA, output: outputA },
      { node: nodeB, output: outputB },
    ],
    note:
      "Both selections share the same cached audio. Use a chain hop below (e.g. LoadAudio → Denoise).",
    missingRender: false,
  };
}

export function resolveTargetNode(workflow: Workflow, selectedId: string | null): string {
  if (selectedId?.startsWith("proxy_")) {
    const groupId = selectedId.slice("proxy_".length);
    const group = workflow.groups.find((item) => item.id === groupId);
    if (group && group.node_ids.length > 0) {
      return group.node_ids[group.node_ids.length - 1];
    }
  }
  if (selectedId) {
    return selectedId;
  }
  const preview = workflow.nodes.find((n: WorkflowNode) => n.type === "Preview");
  if (preview) {
    return preview.id;
  }
  return workflow.nodes[workflow.nodes.length - 1]?.id ?? "";
}

export function downloadWorkflow(workflow: Workflow): void {
  const blob = new Blob([JSON.stringify(workflow, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${workflow.metadata.title.toLowerCase().replace(/\s+/g, "-")}.groovy.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function extractModule(workflow: Workflow, nodeIds: string[]): WorkflowModule {
  const selected = new Set(nodeIds);
  const nodes = workflow.nodes.filter((node) => selected.has(node.id));
  const links = workflow.links.filter(
    (link) => selected.has(link.from[0]) && selected.has(link.to[0]),
  );

  const explicitInlets = nodes
    .filter((node) => node.type === "ModuleInlet")
    .map((node, index) => ({
      id: `in_${node.id}`,
      name: String(node.widgets.name ?? `in${index + 1}`),
      type: String(node.widgets.socket_type ?? "AUDIO"),
      node_id: node.id,
      slot: 0,
      direction: "in" as const,
    }));
  const explicitOutlets = nodes
    .filter((node) => node.type === "ModuleOutlet")
    .map((node, index) => ({
      id: `out_${node.id}`,
      name: String(node.widgets.name ?? `out${index + 1}`),
      type: "AUDIO",
      node_id: node.id,
      slot: 0,
      direction: "out" as const,
    }));

  const boundaryInlets = workflow.links
    .filter((link) => selected.has(link.to[0]) && !selected.has(link.from[0]))
    .map((link, index) => ({
      id: `boundary_in_${link.id}`,
      name: `in${index + 1}`,
      type: link.type,
      node_id: String(link.to[0]),
      slot: Number(link.to[1]),
      direction: "in" as const,
    }));
  const boundaryOutlets = workflow.links
    .filter((link) => selected.has(link.from[0]) && !selected.has(link.to[0]))
    .map((link, index) => ({
      id: `boundary_out_${link.id}`,
      name: `out${index + 1}`,
      type: link.type,
      node_id: String(link.from[0]),
      slot: Number(link.from[1]),
      direction: "out" as const,
    }));

  const inlets = explicitInlets.length > 0 ? explicitInlets : boundaryInlets;
  const outlets = explicitOutlets.length > 0 ? explicitOutlets : boundaryOutlets;

  return {
    schema_version: workflow.schema_version,
    metadata: {
      title: `${workflow.metadata.title} module`,
      description: `Extracted module (${nodes.length} nodes; ${inlets.length} in, ${outlets.length} out)`,
    },
    nodes,
    links,
    inlets,
    outlets,
  };
}

export function downloadModule(module: WorkflowModule): void {
  const blob = new Blob([JSON.stringify(module, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${module.metadata.title.toLowerCase().replace(/\s+/g, "-")}.module.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function createGroup(workflow: Workflow, nodeIds: string[], title: string): Workflow {
  const group = {
    id: `g_${Date.now()}`,
    title,
    node_ids: [...nodeIds],
    color: "#3b82f6",
    collapsed: false,
  };
  return {
    ...workflow,
    groups: [...workflow.groups, group],
  };
}

export function importModule(
  workflow: Workflow,
  module: WorkflowModule,
  anchor: { x: number; y: number } = { x: 80, y: 80 },
): Workflow {
  const prefix = `m${Date.now()}`;
  const idMap = new Map(module.nodes.map((node) => [node.id, `${prefix}_${node.id}`]));
  const xs = module.nodes.map((node) => node.pos?.x ?? 0);
  const ys = module.nodes.map((node) => node.pos?.y ?? 0);
  const minX = xs.length ? Math.min(...xs) : 0;
  const minY = ys.length ? Math.min(...ys) : 0;
  const newNodes = module.nodes.map((node) => ({
    ...node,
    id: idMap.get(node.id)!,
    pos: {
      x: (node.pos?.x ?? 0) - minX + anchor.x,
      y: (node.pos?.y ?? 0) - minY + anchor.y,
    },
  }));
  const newLinks = module.links.map((link) => ({
    ...link,
    id: `${prefix}_${link.id}`,
    from: [idMap.get(String(link.from[0]))!, link.from[1]] as [string, number],
    to: [idMap.get(String(link.to[0]))!, link.to[1]] as [string, number],
  }));
  return {
    ...workflow,
    nodes: [...workflow.nodes, ...newNodes],
    links: [...workflow.links, ...newLinks],
  };
}

export function addLink(workflow: Workflow, sourceId: string, targetId: string, type = "AUDIO"): Workflow {
  const link: WorkflowLink = {
    id: `l_${sourceId}_${targetId}_${Date.now()}`,
    from: [sourceId, 0],
    to: [targetId, 0],
    type,
  };
  return { ...workflow, links: [...workflow.links, link] };
}

export function removeLinks(workflow: Workflow, linkIds: Set<string>): Workflow {
  return { ...workflow, links: workflow.links.filter((link) => !linkIds.has(link.id)) };
}

export type WorkflowClipboard = {
  nodes: WorkflowNode[];
  links: WorkflowLink[];
};

/** Collect workflow nodes + internal links for copy/paste (skips collapsed group proxies). */
export function extractSelection(workflow: Workflow, nodeIds: string[]): WorkflowClipboard {
  const selected = new Set(nodeIds.filter((id) => !id.startsWith("proxy_")));
  return {
    nodes: workflow.nodes.filter((node) => selected.has(node.id)).map((node) => structuredClone(node)),
    links: workflow.links
      .filter((link) => selected.has(String(link.from[0])) && selected.has(String(link.to[0])))
      .map((link) => structuredClone(link)),
  };
}

/** Paste a clipboard slice; returns new node ids for selection focus. */
export function pasteSelection(
  workflow: Workflow,
  clip: WorkflowClipboard,
  offset: { x: number; y: number } = { x: 48, y: 48 },
): { workflow: Workflow; newNodeIds: string[] } {
  if (clip.nodes.length === 0) {
    return { workflow, newNodeIds: [] };
  }
  const prefix = `p${Date.now()}`;
  const idMap = new Map(clip.nodes.map((node) => [node.id, `${prefix}_${node.id}`]));
  const newNodes = clip.nodes.map((node) => ({
    ...node,
    id: idMap.get(node.id)!,
    pos: {
      x: (node.pos?.x ?? 0) + offset.x,
      y: (node.pos?.y ?? 0) + offset.y,
    },
  }));
  const newLinks = clip.links.map((link) => ({
    ...link,
    id: `${prefix}_${link.id}`,
    from: [idMap.get(String(link.from[0]))!, link.from[1]] as [string, number],
    to: [idMap.get(String(link.to[0]))!, link.to[1]] as [string, number],
  }));
  return {
    workflow: {
      ...workflow,
      nodes: [...workflow.nodes, ...newNodes],
      links: [...workflow.links, ...newLinks],
    },
    newNodeIds: newNodes.map((node) => node.id),
  };
}

/** Duplicate an on-canvas selection in place (same as copy + paste once). */
export function duplicateSelection(
  workflow: Workflow,
  nodeIds: string[],
  offset: { x: number; y: number } = { x: 48, y: 48 },
): { workflow: Workflow; newNodeIds: string[] } {
  return pasteSelection(workflow, extractSelection(workflow, nodeIds), offset);
}

export function removeNodesFromWorkflow(workflow: Workflow, rawIds: Set<string>): Workflow {
  const nodeIds = new Set<string>();
  for (const id of rawIds) {
    if (id.startsWith("proxy_")) {
      const groupId = id.slice("proxy_".length);
      const group = workflow.groups.find((item) => item.id === groupId);
      if (group) {
        for (const memberId of group.node_ids) nodeIds.add(memberId);
      }
      continue;
    }
    nodeIds.add(id);
  }

  const groups = workflow.groups
    .filter((group) => !rawIds.has(proxyNodeId(group.id)))
    .map((group) => ({
      ...group,
      node_ids: group.node_ids.filter((id) => !nodeIds.has(id)),
    }))
    .filter((group) => group.node_ids.length > 0)
    .filter((group) => group.node_ids.length >= 2);

  return {
    ...workflow,
    nodes: workflow.nodes.filter((node) => !nodeIds.has(node.id)),
    links: workflow.links.filter(
      (link) => !nodeIds.has(String(link.from[0])) && !nodeIds.has(String(link.to[0])),
    ),
    groups,
  };
}

export function collectModelRefs(workflow: Workflow): string[] {
  const ids = new Set<string>();
  for (const node of workflow.nodes) {
    const model = node.widgets.model;
    if (typeof model === "string" && model) {
      ids.add(model);
    }
  }
  return [...ids];
}

export function addNodeToWorkflow(
  workflow: Workflow,
  nodeType: string,
  widgets: Record<string, unknown>,
): Workflow {
  const id = `n${workflow.nodes.length + 1}`;
  const maxX = workflow.nodes.reduce((acc, n) => Math.max(acc, n.pos?.x ?? 0), 0);
  return {
    ...workflow,
    nodes: [
      ...workflow.nodes,
      { id, type: nodeType, pos: { x: maxX + 220, y: 80 }, widgets },
    ],
  };
}

export function formatJobError(error: string | null | undefined): string {
  if (!error) return "unknown error";
  const runtime = error.match(/RuntimeError:\s*(.+)/);
  if (runtime) return runtime[1].trim();
  const lines = error.trim().split("\n").filter(Boolean);
  return lines[lines.length - 1] ?? error;
}

export function setLoadAudioPath(workflow: Workflow, nodeId: string, path: string): Workflow {
  return {
    ...workflow,
    nodes: workflow.nodes.map((node) =>
      node.id === nodeId ? { ...node, widgets: { ...node.widgets, path } } : node,
    ),
  };
}

export function applyDroppedAudio(workflow: Workflow, path: string): Workflow {
  const loadNode = workflow.nodes.find((node) => node.type === "LoadAudio");
  if (loadNode) {
    return setLoadAudioPath(workflow, loadNode.id, path);
  }
  const id = `n${workflow.nodes.length + 1}`;
  return {
    ...workflow,
    nodes: [
      { id, type: "LoadAudio", pos: { x: 40, y: 80 }, widgets: { path } },
      ...workflow.nodes,
    ],
  };
}

export function edgeIdsOnPathToNode(workflow: Workflow, targetNodeId: string): Set<string> {
  const upstream = new Map<string, string[]>();
  for (const link of rewriteLinksForCollapsedGroups(workflow)) {
    const dst = String(link.to[0]);
    const src = String(link.from[0]);
    const list = upstream.get(dst) ?? [];
    list.push(src);
    upstream.set(dst, list);
  }
  const onPath = new Set<string>([targetNodeId]);
  const queue = [targetNodeId];
  while (queue.length > 0) {
    const nodeId = queue.pop()!;
    for (const src of upstream.get(nodeId) ?? []) {
      if (!onPath.has(src)) {
        onPath.add(src);
        queue.push(src);
      }
    }
  }
  return new Set(
    rewriteLinksForCollapsedGroups(workflow)
      .filter((link) => onPath.has(String(link.from[0])) && onPath.has(String(link.to[0])))
      .map((link) => link.id),
  );
}

export function downloadTemplateJson(template: Workflow, filename: string): void {
  const blob = new Blob([JSON.stringify(template, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
