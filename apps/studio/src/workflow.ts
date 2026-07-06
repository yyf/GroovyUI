import type { Edge, Node } from "@xyflow/react";
import type { NodeRenderStatus, Workflow, WorkflowLink, WorkflowNode } from "./types";
import type { GroovyNodeData } from "./components/GroovyFlowNode";

export function workflowToFlow(
  workflow: Workflow,
  nodeStatus: Record<string, NodeRenderStatus>,
): { nodes: Node<GroovyNodeData>[]; edges: Edge[] } {
  const nodes: Node<GroovyNodeData>[] = workflow.nodes.map((n: WorkflowNode) => ({
    id: n.id,
    type: "groovy",
    position: n.pos ?? { x: 0, y: 0 },
    data: {
      label: n.type,
      status: nodeStatus[n.id] ?? "idle",
    },
  }));
  const edges: Edge[] = workflow.links.map((l: WorkflowLink) => ({
    id: l.id,
    source: l.from[0],
    target: l.to[0],
    label: l.type,
  }));
  return { nodes, edges };
}

export function syncPositions(workflow: Workflow, nodes: Node[]): Workflow {
  const posById = new Map(nodes.map((n) => [n.id, n.position]));
  return {
    ...workflow,
    nodes: workflow.nodes.map((node: WorkflowNode) => {
      const pos = posById.get(node.id);
      return pos ? { ...node, pos: { x: pos.x, y: pos.y } } : node;
    }),
  };
}

export function resolveTargetNode(workflow: Workflow, selectedId: string | null): string {
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

export function formatJobError(error: string | null | undefined): string {
  if (!error) return "unknown error";
  const runtime = error.match(/RuntimeError:\s*(.+)/);
  if (runtime) return runtime[1].trim();
  const lines = error.trim().split("\n").filter(Boolean);
  return lines[lines.length - 1] ?? error;
}
