import type { Edge, Node } from "@xyflow/react";
import type { CreativeAgentStep } from "./api";
import type { GroovyNodeData } from "./components/GroovyFlowNode";
import type { CreativeAgentAction } from "./creativeAgentApply";
import { canvasNodeKind } from "./nodeKinds";
import { edgeTypeClass, resolveEdgeStroke } from "./socketTypes";
import type { NodeSchema, Workflow } from "./types";
import { estimateNodeSize } from "./workflow";

export type CreativeTabSession = {
  goal: string | null;
  notes: string | null;
  steps: CreativeAgentStep[];
  /** Index of the next step awaiting Tab approve. */
  cursor: number;
  planning: boolean;
  /** performance.now() when planning started (for elapsed / ETA). */
  planningStartedAt?: number | null;
  /** Ephemeral HUD notice (locked step, still planning, approved…). */
  notice?: string | null;
};

const PLAN_MS_STORAGE_KEY = "groovy-creative-plan-ms";
const DEFAULT_PLAN_ESTIMATE_MS = 14_000;
const PLAN_MS_SAMPLES = 8;

/** Vertical pitch between parallel branches (and chrome below the lane). */
export const FLOW_ROW = 130;

export function estimateCreativePlanMs(): number {
  try {
    const raw = localStorage.getItem(PLAN_MS_STORAGE_KEY);
    if (!raw) return DEFAULT_PLAN_ESTIMATE_MS;
    const samples = JSON.parse(raw) as number[];
    if (!Array.isArray(samples) || !samples.length) return DEFAULT_PLAN_ESTIMATE_MS;
    const nums = samples.filter((n) => typeof n === "number" && n > 1_000 && n < 120_000);
    if (!nums.length) return DEFAULT_PLAN_ESTIMATE_MS;
    return Math.round(nums.reduce((a, b) => a + b, 0) / nums.length);
  } catch {
    return DEFAULT_PLAN_ESTIMATE_MS;
  }
}

export function recordCreativePlanDuration(ms: number): void {
  if (!(ms > 1_000) || ms > 120_000) return;
  try {
    const raw = localStorage.getItem(PLAN_MS_STORAGE_KEY);
    const prev = raw ? (JSON.parse(raw) as number[]) : [];
    const next = [...(Array.isArray(prev) ? prev : []), Math.round(ms)].slice(-PLAN_MS_SAMPLES);
    localStorage.setItem(PLAN_MS_STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* ignore quota / private mode */
  }
}

/** Progress as % of typical plan time (not wall-clock seconds). */
export function formatCreativePlanTiming(elapsedMs: number, estimateMs: number): string {
  const denom = Math.max(estimateMs, 1);
  const pct = Math.min(99, Math.round((100 * elapsedMs) / denom));
  if (elapsedMs < estimateMs * 0.95) {
    return `AI agent · ${pct}%`;
  }
  return "AI agent · finishing…";
}

export function canvasSnapshotForCreative(workflow: Workflow | null): {
  nodes: Array<{ id: string; type: string; widgets?: Record<string, unknown> }>;
  links: Array<{ id: string; from: [string, number]; to: [string, number]; type: string }>;
} {
  if (!workflow) return { nodes: [], links: [] };
  return {
    nodes: workflow.nodes.slice(0, 64).map((node) => ({
      id: node.id,
      type: node.type,
      widgets: node.widgets,
    })),
    links: workflow.links.slice(0, 96).map((link) => ({
      id: link.id,
      from: link.from,
      to: link.to,
      type: link.type,
    })),
  };
}

export function creativeTabPrompt(args: {
  selectedNodeId: string | null;
  selectedNodeType: string | null;
  nodeCount: number;
}): string {
  const focus =
    args.selectedNodeId && args.selectedNodeType
      ? ` Focus on node ${args.selectedNodeId} (${args.selectedNodeType}).`
      : "";
  const layout =
    " Lay out hops left-to-right. Linear chain stays on one row. " +
    "When one node fans out to two sinks (e.g. Preview + SaveAudio), place them as parallel branches " +
    "(Preview above, SaveAudio below).";
  if (args.nodeCount <= 1) {
    return (
      "Hero grow: from LoadAudio, propose Denoise → Normalize, then Preview and SaveAudio in parallel " +
      "from Normalize (Preview above, SaveAudio below). Prefer those exact node type names." +
      layout +
      focus
    );
  }
  return (
    "Grow this patch: suggest the next useful hops from the current canvas." +
    " Prefer additive explore steps; keep the graph minimal." +
    " Prefer public type names: LoadAudio, Denoise, Normalize, Preview, SeparateStems, WhisperSTT, TTS, Mix, SaveAudio." +
    layout +
    focus
  );
}

/** Opacity ladder — next hop is nearly solid so Tab target is obvious. */
export function ghostOpacityForOffset(offset: number): number {
  if (offset <= 0) return 0.95;
  if (offset === 1) return 0.48;
  if (offset === 2) return 0.3;
  return 0.16;
}

export function ghostTierClass(offset: number): string {
  if (offset <= 0) return "groovy-node-ghost--next";
  if (offset === 1) return "groovy-node-ghost--near";
  return "groovy-node-ghost--far";
}

/** First non-Note node anchors the L→R grow lane. */
export function resolveCreativeAnchor(workflow: Workflow): {
  id: string | null;
  x: number;
  y: number;
  width: number;
  col: number;
  solidCount: number;
} {
  const signal = workflow.nodes.filter((node) => node.type !== "Note");
  const first = signal[0] ?? workflow.nodes[0];
  if (!first) {
    return { id: null, x: 80, y: 140, width: 200, col: 260, solidCount: 0 };
  }
  const width = estimateNodeSize(first).width;
  return {
    id: first.id,
    x: first.pos?.x ?? 0,
    y: first.pos?.y ?? 140,
    width,
    col: Math.max(260, width + 72),
    solidCount: signal.length,
  };
}

function schemaSockets(schema: NodeSchema | undefined): {
  inputs: GroovyNodeData["inputs"];
  outputs: GroovyNodeData["outputs"];
} {
  if (!schema) {
    return {
      inputs: [{ name: "in", type: "AUDIO", slot: 0 }],
      outputs: [{ name: "out", type: "AUDIO", slot: 0 }],
    };
  }
  return {
    inputs: schema.inputs.map((socket, slot) => ({
      name: socket.name,
      type: socket.type,
      optional: socket.optional,
      slot,
    })),
    outputs: schema.outputs.map((socket, slot) => ({
      name: socket.name,
      type: socket.type,
      slot,
    })),
  };
}

function addNodePreferredId(
  action: Extract<CreativeAgentAction, { type: "add_node" }>,
  stepId: string,
): string {
  return (action.node.id || "").trim() || `ghost-${stepId}`;
}

/** Branch ranks for n siblings: 1→[0], 2→[-1,1], 3→[-1,0,1], … */
export function parallelBranchRanks(count: number): number[] {
  if (count <= 0) return [];
  if (count === 1) return [0];
  const ranks: number[] = [];
  if (count % 2 === 1) ranks.push(0);
  for (let i = 1; ranks.length < count; i++) {
    ranks.push(-i);
    if (ranks.length < count) ranks.push(i);
  }
  return ranks.sort((a, b) => a - b);
}

/**
 * Soft rank for true parallel siblings (Preview above, Save below).
 * Extend this when new templates need named fork roles (e.g. stem lanes).
 * Score 0 = stay on the growing signal lane (Denoise, Normalize, Mix, …).
 */
function parallelSortScore(type: string): number {
  if (type === "Preview" || type === "PreviewVideo") return -1;
  if (type === "SaveAudio") return 1;
  return 0;
}

function isParallelForkType(type: string): boolean {
  return parallelSortScore(type) !== 0;
}

/** Directed reachability (detects chain links among siblings). */
function canReach(
  from: string,
  to: string,
  children: Map<string, string[]>,
  allowed: Set<string>,
): boolean {
  if (from === to) return true;
  const seen = new Set<string>();
  const stack = [from];
  while (stack.length) {
    const id = stack.pop()!;
    if (seen.has(id)) continue;
    seen.add(id);
    for (const kid of children.get(id) ?? []) {
      if (!allowed.has(kid)) continue;
      if (kid === to) return true;
      stack.push(kid);
    }
  }
  return false;
}

/**
 * Per parent: signal hops inherit the parent's lane and advance L→R.
 * Only alternate fork roles (Preview / SaveAudio today) get ±Y — and only when
 * there is no chain path between them. Claude double-wiring a chain off one
 * parent still serializes on the lane by step order.
 */
function assignLaneAndFanout(
  kids: string[],
  ghostMeta: Map<string, { type: string; order: number }>,
  children: Map<string, string[]>,
  branch: Map<string, number>,
  depth: Map<string, number>,
  parentBranch: number,
): void {
  if (kids.length === 0) return;

  const laneKids = kids.filter((id) => !isParallelForkType(ghostMeta.get(id)?.type ?? ""));
  const forkKids = kids.filter((id) => isParallelForkType(ghostMeta.get(id)?.type ?? ""));

  if (laneKids.length > 0) {
    const ordered = [...laneKids].sort(
      (a, b) => (ghostMeta.get(a)?.order ?? 0) - (ghostMeta.get(b)?.order ?? 0),
    );
    const baseDepth = Math.min(...ordered.map((id) => depth.get(id) ?? 1));
    ordered.forEach((id, i) => {
      branch.set(id, parentBranch);
      depth.set(id, baseDepth + i);
    });
  }

  if (forkKids.length === 0) return;

  const allowed = new Set(forkKids);
  const linked = forkKids.some((a, i) =>
    forkKids.slice(i + 1).some(
      (b) => canReach(a, b, children, allowed) || canReach(b, a, children, allowed),
    ),
  );

  if (forkKids.length === 1 || linked) {
    const ordered = [...forkKids].sort(
      (a, b) => (ghostMeta.get(a)?.order ?? 0) - (ghostMeta.get(b)?.order ?? 0),
    );
    const afterLane =
      laneKids.length > 0
        ? Math.max(...laneKids.map((id) => depth.get(id) ?? 0)) + 1
        : Math.min(...ordered.map((id) => depth.get(id) ?? 1));
    ordered.forEach((id, i) => {
      branch.set(id, parentBranch);
      depth.set(id, afterLane + i);
    });
    return;
  }

  const forkDepth =
    laneKids.length > 0
      ? Math.max(...laneKids.map((id) => depth.get(id) ?? 0)) + 1
      : Math.min(...forkKids.map((id) => depth.get(id) ?? 1));
  const sorted = [...forkKids].sort((a, b) => {
    const byScore =
      parallelSortScore(ghostMeta.get(a)?.type ?? "") -
      parallelSortScore(ghostMeta.get(b)?.type ?? "");
    if (byScore !== 0) return byScore;
    return (ghostMeta.get(a)?.order ?? 0) - (ghostMeta.get(b)?.order ?? 0);
  });
  const ranks = parallelBranchRanks(sorted.length);
  sorted.forEach((id, i) => {
    depth.set(id, forkDepth);
    branch.set(id, parentBranch + (ranks[i] ?? 0));
  });
}

/** Project remaining steps into non-interactive ghost React Flow nodes/edges. */
export function projectCreativeGhosts(
  session: CreativeTabSession,
  workflow: Workflow,
  nodeSchemas: Record<string, NodeSchema>,
  _anchor?: { x: number; y: number },
): { nodes: Node<GroovyNodeData>[]; edges: Edge[] } {
  const remaining = session.steps.slice(session.cursor);
  const solidIds = workflow.nodes.filter((n) => n.type !== "Note").map((n) => n.id);
  const solidIdSet = new Set(workflow.nodes.map((n) => n.id));

  const positions = new Map<string, { x: number; y: number }>();
  for (const node of workflow.nodes) {
    positions.set(node.id, { x: node.pos?.x ?? 0, y: node.pos?.y ?? 0 });
  }

  const flowIdFor = new Map<string, string>();
  for (const id of solidIdSet) flowIdFor.set(id, id);

  const addSteps = remaining.filter((s) => (s.action as CreativeAgentAction).type === "add_node");
  const ghostMeta = new Map<string, { type: string; order: number; step: CreativeAgentStep }>();
  addSteps.forEach((step, order) => {
    const action = step.action as Extract<CreativeAgentAction, { type: "add_node" }>;
    const logicalId = addNodePreferredId(action, step.id);
    ghostMeta.set(logicalId, { type: action.node.type, order, step });
  });
  const ghostIds = [...ghostMeta.keys()];

  const edgeList: Array<{ from: string; to: string }> = [];
  for (const link of workflow.links) {
    edgeList.push({ from: link.from[0], to: link.to[0] });
  }
  for (const step of remaining) {
    const action = step.action as CreativeAgentAction;
    if (action.type === "connect") {
      edgeList.push({ from: action.from[0], to: action.to[0] });
    }
  }

  const origin = resolveCreativeAnchor(workflow);
  const rootId = origin.id;
  const allIds = new Set([...solidIds, ...ghostIds]);

  const children = new Map<string, string[]>();
  for (const { from, to } of edgeList) {
    if (!allIds.has(from) || !allIds.has(to)) continue;
    const list = children.get(from) ?? [];
    if (!list.includes(to)) list.push(to);
    children.set(from, list);
  }

  const depth = new Map<string, number>();
  const queue: string[] = [];

  // Solids: depth from left-to-right X order (stable lane), then BFS can deepen ghosts.
  const solidsByX = [...workflow.nodes]
    .filter((n) => n.type !== "Note")
    .sort((a, b) => (a.pos?.x ?? 0) - (b.pos?.x ?? 0) || a.id.localeCompare(b.id));
  solidsByX.forEach((node, i) => {
    depth.set(node.id, i);
    queue.push(node.id);
  });
  if (rootId && allIds.has(rootId) && !depth.has(rootId)) {
    depth.set(rootId, 0);
    queue.push(rootId);
  }

  while (queue.length) {
    const id = queue.shift()!;
    const d = depth.get(id) ?? 0;
    for (const child of children.get(id) ?? []) {
      const next = d + 1;
      if (!depth.has(child) || next > (depth.get(child) ?? 0)) {
        depth.set(child, next);
        queue.push(child);
      }
    }
  }

  let fallback =
    Math.max(0, ...[...depth.values()], solidsByX.length - 1) + 1;
  for (const id of ghostIds) {
    if (!depth.has(id)) {
      depth.set(id, fallback);
      fallback += 1;
    }
  }

  const branch = new Map<string, number>();
  for (const id of solidIds) branch.set(id, 0);

  // Parents in depth order so child ranks inherit a stable parentBranch.
  const parentsOrdered = [...children.keys()].sort(
    (a, b) => (depth.get(a) ?? 0) - (depth.get(b) ?? 0),
  );
  for (const parentId of parentsOrdered) {
    const ghostKids = (children.get(parentId) ?? []).filter((id) => ghostMeta.has(id));
    if (ghostKids.length === 0) continue;
    const parentBranch = branch.get(parentId) ?? 0;
    assignLaneAndFanout(ghostKids, ghostMeta, children, branch, depth, parentBranch);
  }
  for (const id of ghostIds) {
    if (!branch.has(id)) branch.set(id, 0);
    // Lane hops never keep a parallel rank from a stale pass.
    if (!isParallelForkType(ghostMeta.get(id)?.type ?? "")) branch.set(id, 0);
  }

  const nodes: Node<GroovyNodeData>[] = [];
  const edges: Edge[] = [];
  // Lane Y follows the anchor solid; approved solids keep their own Y via positions.
  const laneY = origin.y;
  const slotPos = (logicalId: string) => {
    const d = depth.get(logicalId) ?? 1;
    const b = branch.get(logicalId) ?? 0;
    return {
      x: origin.x + d * origin.col,
      y: laneY + b * FLOW_ROW,
    };
  };

  let addOrdinal = 0;
  const orderedGhosts = [...ghostIds].sort((a, b) => {
    const da = depth.get(a) ?? 0;
    const db = depth.get(b) ?? 0;
    if (da !== db) return da - db;
    const ba = branch.get(a) ?? 0;
    const bb = branch.get(b) ?? 0;
    if (ba !== bb) return ba - bb;
    return (ghostMeta.get(a)?.order ?? 0) - (ghostMeta.get(b)?.order ?? 0);
  });

  for (const logicalId of orderedGhosts) {
    const meta = ghostMeta.get(logicalId)!;
    const step = meta.step;
    const action = step.action as Extract<CreativeAgentAction, { type: "add_node" }>;
    const opacity = ghostOpacityForOffset(addOrdinal);
    const tier = ghostTierClass(addOrdinal);
    const schema = nodeSchemas[action.node.type];
    const sockets = schemaSockets(schema);
    const pos = slotPos(logicalId);
    positions.set(logicalId, pos);
    const flowId = `__ghost__${step.id}`;
    flowIdFor.set(logicalId, flowId);
    nodes.push({
      id: flowId,
      type: "groovy",
      position: pos,
      draggable: false,
      selectable: false,
      connectable: false,
      focusable: false,
      className: `groovy-node-ghost ${tier}`,
      style: { opacity, pointerEvents: "none" },
      data: {
        label: action.node.type,
        kind: canvasNodeKind(action.node.type, schema?.category),
        status: "idle",
        nodeId: logicalId,
        ghost: true,
        ghostStep: step.index + 1,
        ghostTitle: step.title,
        ghostNext: addOrdinal === 0,
        inputs: sockets.inputs,
        outputs: sockets.outputs,
      },
    });
    addOrdinal += 1;
  }

  let chromeIndex = 0;
  for (const step of remaining) {
    const action = step.action as CreativeAgentAction;
    if (action.type === "connect") {
      const source = flowIdFor.get(action.from[0]);
      const target = flowIdFor.get(action.to[0]);
      if (!source || !target) continue;
      const linkType = action.link_type || "AUDIO";
      const stepOffset = Math.max(0, step.index - session.cursor);
      const isNext = step.index === session.cursor;
      edges.push({
        id: `__ghost_edge__${step.id}`,
        source,
        sourceHandle: String(action.from[1]),
        target,
        targetHandle: String(action.to[1]),
        selectable: false,
        focusable: false,
        className: `${edgeTypeClass(linkType)} groovy-edge-ghost${isNext ? " groovy-edge-ghost--next" : ""}`,
        style: {
          stroke: isNext ? "var(--accent)" : resolveEdgeStroke(linkType, null),
          strokeWidth: isNext ? 2.25 : 1.25,
          opacity: ghostOpacityForOffset(stepOffset),
          strokeDasharray: isNext ? "6 3" : "4 5",
        },
        data: { ghost: true },
      });
      continue;
    }

    if (
      action.type === "set_widgets" ||
      action.type === "remove_node" ||
      action.type === "suggest_render"
    ) {
      const targetId =
        action.type === "set_widgets" || action.type === "remove_node"
          ? action.node_id
          : action.target_node_id;
      const base = positions.get(targetId) ?? { x: origin.x + origin.col, y: laneY };
      nodes.push({
        id: `__ghost_marker__${step.id}`,
        type: "groovy",
        position: {
          x: base.x,
          y: laneY + FLOW_ROW * 2 + chromeIndex * 28,
        },
        draggable: false,
        selectable: false,
        connectable: false,
        focusable: false,
        className: "groovy-node-ghost groovy-node-ghost--marker groovy-node-ghost--far",
        style: { opacity: ghostOpacityForOffset(2), pointerEvents: "none", width: 168 },
        data: {
          label: step.title || action.type,
          kind: "core",
          status: "idle",
          nodeId: targetId,
          ghost: true,
          ghostStep: step.index + 1,
          ghostTitle: step.title,
          noteText: (step.rationale || action.type).slice(0, 96),
          inputs: [],
          outputs: [],
        },
      });
      chromeIndex += 1;
      continue;
    }

    if (action.type === "propose_note") {
      nodes.push({
        id: `__ghost_note__${step.id}`,
        type: "groovy",
        position: {
          x: origin.x + origin.col,
          y: laneY + FLOW_ROW * 2 + chromeIndex * 36,
        },
        draggable: false,
        selectable: false,
        connectable: false,
        focusable: false,
        className: "groovy-node-ghost groovy-node-ghost--note groovy-node-ghost--far",
        style: { opacity: ghostOpacityForOffset(2), pointerEvents: "none", width: 220 },
        data: {
          label: "Note",
          kind: "core",
          status: "idle",
          nodeId: `note-${step.id}`,
          ghost: true,
          ghostStep: step.index + 1,
          ghostTitle: step.title,
          noteText: action.message || step.rationale,
          inputs: [],
          outputs: [],
        },
      });
      chromeIndex += 1;
    }
  }

  return { nodes, edges };
}

export function creativeSessionStatus(session: CreativeTabSession): string {
  if (session.planning) {
    const started = session.planningStartedAt ?? performance.now();
    const timing = formatCreativePlanTiming(
      performance.now() - started,
      estimateCreativePlanMs(),
    );
    return `Creative · ${timing}`;
  }
  if (session.notice) return `Creative · ${session.notice}`;
  if (!session.steps.length) return "Creative · no steps";
  if (session.cursor >= session.steps.length) return "Creative · done — Esc to clear";
  const step = session.steps[session.cursor];
  const n = session.cursor + 1;
  const total = session.steps.length;
  const locked = step.apply_locked ? " · locked (Shift+Tab skip)" : "";
  return `Creative · ${n}/${total} ${step.title}${locked} · Tab approve · Esc dismiss`;
}
