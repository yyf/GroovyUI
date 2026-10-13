import type { NodeSchema, Workflow } from "./types";
import { addNodeToWorkflow, connectNodes, removeNodesFromWorkflow } from "./workflow";

export type CreativeAgentAction =
  | {
      type: "add_node";
      node: {
        id?: string;
        type: string;
        widgets?: Record<string, unknown>;
        pos?: { x: number; y: number };
      };
    }
  | {
      type: "connect";
      from: [string, number];
      to: [string, number];
      link_type?: string;
    }
  | {
      type: "set_widgets";
      node_id: string;
      node_type?: string | null;
      widgets: Record<string, unknown>;
    }
  | { type: "remove_node"; node_id: string }
  | { type: "propose_note"; message: string }
  | { type: "suggest_render"; target_node_id: string };

export type CreativeApplyResult = {
  workflow: Workflow;
  selectedNodeId?: string | null;
  renderTargetId?: string | null;
  statusMessage: string;
  canvasChanged: boolean;
};

/** Apply one approved Creative Agent action. Caller owns history / Compliance. */
export function applyCreativeAgentAction(
  workflow: Workflow,
  action: CreativeAgentAction,
  nodeSchemas: Record<string, NodeSchema>,
  center?: { x: number; y: number },
): CreativeApplyResult {
  switch (action.type) {
    case "propose_note":
      return {
        workflow,
        canvasChanged: false,
        statusMessage: action.message || "Noted",
      };
    case "suggest_render":
      return {
        workflow,
        selectedNodeId: action.target_node_id,
        renderTargetId: action.target_node_id,
        canvasChanged: false,
        statusMessage: `Approved render suggestion for ${action.target_node_id} — press Render when ready`,
      };
    case "remove_node": {
      const next = removeNodesFromWorkflow(workflow, new Set([action.node_id]));
      return {
        workflow: next,
        canvasChanged: true,
        statusMessage: `Removed node ${action.node_id}`,
      };
    }
    case "set_widgets": {
      const next: Workflow = {
        ...workflow,
        nodes: workflow.nodes.map((node) =>
          node.id === action.node_id
            ? { ...node, widgets: { ...node.widgets, ...action.widgets } }
            : node,
        ),
      };
      return {
        workflow: next,
        selectedNodeId: action.node_id,
        canvasChanged: true,
        statusMessage: `Updated widgets on ${action.node_id}`,
      };
    }
    case "add_node": {
      const nodeType = action.node.type;
      const widgets = { ...(action.node.widgets ?? {}) };
      const exact = Boolean(action.node.pos);
      const { workflow: withNode, nodeId } = addNodeToWorkflow(
        workflow,
        nodeType,
        widgets,
        action.node.pos ?? center,
        exact ? { exactPosition: true } : undefined,
      );
      // Prefer LLM-suggested id when free; otherwise keep generated id.
      const preferred = (action.node.id || "").trim();
      if (preferred && preferred !== nodeId && !workflow.nodes.some((n) => n.id === preferred)) {
        const remapped: Workflow = {
          ...withNode,
          nodes: withNode.nodes.map((node) =>
            node.id === nodeId ? { ...node, id: preferred } : node,
          ),
        };
        return {
          workflow: remapped,
          selectedNodeId: preferred,
          canvasChanged: true,
          statusMessage: `Added ${nodeType} (${preferred})`,
        };
      }
      return {
        workflow: withNode,
        selectedNodeId: nodeId,
        canvasChanged: true,
        statusMessage: `Added ${nodeType} (${nodeId})`,
      };
    }
    case "connect": {
      const connection = {
        source: action.from[0],
        sourceHandle: String(action.from[1]),
        target: action.to[0],
        targetHandle: String(action.to[1]),
      };
      const next = connectNodes(workflow, connection, nodeSchemas);
      return {
        workflow: next,
        canvasChanged: true,
        statusMessage: `Connected ${action.from[0]} → ${action.to[0]}`,
      };
    }
    default:
      return {
        workflow,
        canvasChanged: false,
        statusMessage: "Unknown action — skipped",
      };
  }
}
