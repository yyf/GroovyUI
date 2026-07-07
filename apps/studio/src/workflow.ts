import type { Edge, Node } from "@xyflow/react";
import type { JobOutput, NodeRenderStatus, Workflow, WorkflowGroup, WorkflowLink, WorkflowModule, WorkflowNode } from "./types";
import type { GroovyGroupNodeData } from "./components/ModuleGroupNode";
import type { GroovyNodeData } from "./components/GroovyFlowNode";

export function previewCacheId(output?: JobOutput): string | null {
  if (!output?.cache_id) return null;
  return output.cache_id;
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

export function workflowToFlow(
  workflow: Workflow,
  nodeStatus: Record<string, NodeRenderStatus>,
  outputs?: Record<string, JobOutput>,
  activeEdgeIds?: Set<string>,
): { nodes: Node<GroovyNodeData | GroovyGroupNodeData>[]; edges: Edge[] } {
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

  const links = rewriteLinksForCollapsedGroups(workflow);
  const edges: Edge[] = links.map((l: WorkflowLink) => ({
    id: l.id,
    source: l.from[0],
    target: l.to[0],
    label: l.type,
    className: activeEdgeIds?.has(l.id) ? "groovy-edge--active" : undefined,
    animated: activeEdgeIds?.has(l.id) ?? false,
  }));
  return { nodes, edges };
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
