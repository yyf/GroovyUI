import type { ProvenanceEntry, ProvenanceLineage, ProvenanceLineageNode } from "./types";

export type ProvenanceKind = "human" | "ai" | "mixed" | "unknown";

export type ProvenanceLayoutNode = {
  cacheId: string;
  nodeId: string;
  nodeType: string;
  contributionClass: string;
  kind: ProvenanceKind;
  kindLabel: string;
  models: Array<{ registry_id?: string; role?: string; lora_scale?: number }>;
  modelSummary: string | null;
  isRoot: boolean;
  isSource: boolean;
  rank: number;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type ProvenanceLayoutEdge = {
  id: string;
  fromCacheId: string;
  toCacheId: string;
  path: string;
};

export type ProvenanceGlance = {
  hopCount: number;
  human: number;
  ai: number;
  mixed: number;
  unknown: number;
  humanPercent: number;
  aiPercent: number;
  label: string;
  hasBranching: boolean;
};

export type ProvenanceLayout = {
  width: number;
  height: number;
  orientation: "vertical" | "horizontal";
  nodes: ProvenanceLayoutNode[];
  edges: ProvenanceLayoutEdge[];
  glance: ProvenanceGlance;
};

const NODE_W = 228;
const NODE_H = 64;
const COL_GAP = 28;
const ROW_GAP = 32;
const PAD_X = 16;
const PAD_Y = 20;

const HUMAN = new Set(["human_recorded", "human_edited"]);
const AI = new Set(["ai_generated", "ai_transformed"]);

export function contributionKind(klass: string | undefined | null): ProvenanceKind {
  const value = (klass ?? "").trim().toLowerCase();
  if (HUMAN.has(value)) return "human";
  if (AI.has(value)) return "ai";
  if (value === "mixed") return "mixed";
  return "unknown";
}

export function contributionKindLabel(klass: string | undefined | null): string {
  switch ((klass ?? "").trim().toLowerCase()) {
    case "human_recorded":
      return "Human source";
    case "human_edited":
      return "Human edit";
    case "ai_generated":
      return "AI generated";
    case "ai_transformed":
      return "AI transform";
    case "mixed":
      return "Mixed";
    default:
      return "Unknown";
  }
}

function modelSummary(
  models: Array<{ registry_id?: string; role?: string; lora_scale?: number }>,
): string | null {
  if (!models.length) return null;
  const parts = models.map((model) => {
    const id = model.registry_id ?? "model";
    if (model.role === "adapter") {
      const scale = typeof model.lora_scale === "number" ? `×${model.lora_scale}` : "LoRA";
      return `${id} ${scale}`;
    }
    return id;
  });
  return parts.join(" · ");
}

/** Prefer API lineage DAG; fall back to linear chain so the viz still works. */
export function lineageFromEntry(entry: ProvenanceEntry): ProvenanceLineage | null {
  if (entry.lineage && entry.lineage.nodes.length > 0) {
    return entry.lineage;
  }
  if (!entry.chain || entry.chain.length === 0) return null;
  const nodes: ProvenanceLineageNode[] = entry.chain.map((step, idx) => ({
    cache_id: step.cache_id || `${entry.cache_id}-chain-${idx}`,
    node: step.node,
    contribution: step.contribution,
    models: step.models,
  }));
  const edges: ProvenanceLineage["edges"] = [];
  for (let i = 0; i < nodes.length - 1; i++) {
    edges.push({
      from_cache_id: nodes[i + 1].cache_id,
      to_cache_id: nodes[i].cache_id,
    });
  }
  return {
    root_cache_id: nodes[0]?.cache_id || entry.cache_id,
    nodes,
    edges,
  };
}

export function glanceFromLineage(lineage: ProvenanceLineage): ProvenanceGlance {
  let human = 0;
  let ai = 0;
  let mixed = 0;
  let unknown = 0;
  for (const node of lineage.nodes) {
    const kind = contributionKind(node.contribution?.class);
    if (kind === "human") human += 1;
    else if (kind === "ai") ai += 1;
    else if (kind === "mixed") mixed += 1;
    else unknown += 1;
  }
  const humanWeight = human + mixed * 0.5;
  const aiWeight = ai + mixed * 0.5;
  const total = humanWeight + aiWeight;
  const humanPercent = total > 0 ? Math.round((humanWeight / total) * 100) : 0;
  const aiPercent = total > 0 ? 100 - humanPercent : 0;
  const incoming = new Map<string, number>();
  for (const node of lineage.nodes) incoming.set(node.cache_id, 0);
  for (const edge of lineage.edges) {
    incoming.set(edge.to_cache_id, (incoming.get(edge.to_cache_id) ?? 0) + 1);
  }
  const hasBranching = [...incoming.values()].some((count) => count > 1);
  const parts: string[] = [];
  if (human) parts.push(`${human} human`);
  if (ai) parts.push(`${ai} AI`);
  if (mixed) parts.push(`${mixed} mixed`);
  if (unknown) parts.push(`${unknown} unknown`);
  return {
    hopCount: lineage.nodes.length,
    human,
    ai,
    mixed,
    unknown,
    humanPercent,
    aiPercent,
    label: parts.length ? parts.join(" · ") : "No hops",
    hasBranching,
  };
}

function topologicalRanks(
  nodes: ProvenanceLineageNode[],
  edges: ProvenanceLineage["edges"],
  rootId: string,
): Map<string, number> {
  const ids = new Set(nodes.map((n) => n.cache_id));
  const incoming = new Map<string, string[]>();
  const outgoing = new Map<string, string[]>();
  for (const id of ids) {
    incoming.set(id, []);
    outgoing.set(id, []);
  }
  for (const edge of edges) {
    if (!ids.has(edge.from_cache_id) || !ids.has(edge.to_cache_id)) continue;
    incoming.get(edge.to_cache_id)!.push(edge.from_cache_id);
    outgoing.get(edge.from_cache_id)!.push(edge.to_cache_id);
  }

  const rank = new Map<string, number>();
  const sources = [...ids].filter((id) => (incoming.get(id) || []).length === 0);
  const seed = sources.length > 0 ? sources : [rootId];
  for (const id of seed) rank.set(id, 0);

  const queue = [...seed];
  while (queue.length) {
    const cur = queue.shift()!;
    const r = rank.get(cur) ?? 0;
    for (const next of outgoing.get(cur) || []) {
      const nextRank = Math.max(rank.get(next) ?? 0, r + 1);
      if (!rank.has(next) || nextRank > (rank.get(next) ?? 0)) {
        rank.set(next, nextRank);
        queue.push(next);
      }
    }
  }
  for (const id of ids) {
    if (!rank.has(id)) rank.set(id, 0);
  }
  return rank;
}

function edgePath(x1: number, y1: number, x2: number, y2: number, vertical: boolean): string {
  if (vertical) {
    const midY = (y1 + y2) / 2;
    return `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
  }
  const midX = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
}

function buildNode(
  node: ProvenanceLineageNode,
  opts: { isRoot: boolean; isSource: boolean; rank: number; x: number; y: number },
): ProvenanceLayoutNode {
  const contributionClass = node.contribution?.class ?? "unknown";
  const models = node.models ?? [];
  return {
    cacheId: node.cache_id,
    nodeId: node.node?.node_id ?? "—",
    nodeType: node.node?.node_type ?? "unknown",
    contributionClass,
    kind: contributionKind(contributionClass),
    kindLabel: contributionKindLabel(contributionClass),
    models,
    modelSummary: modelSummary(models),
    isRoot: opts.isRoot,
    isSource: opts.isSource,
    rank: opts.rank,
    x: opts.x,
    y: opts.y,
    width: NODE_W,
    height: NODE_H,
  };
}

/**
 * Vertical recipe layout (sources on top → output at bottom) — easier to glance
 * in the narrow Compliance drawer than a left→right DAG.
 */
export function layoutProvenanceGraph(lineage: ProvenanceLineage): ProvenanceLayout {
  const ranks = topologicalRanks(lineage.nodes, lineage.edges, lineage.root_cache_id);
  const byRank = new Map<number, ProvenanceLineageNode[]>();
  for (const node of lineage.nodes) {
    const r = ranks.get(node.cache_id) ?? 0;
    const bucket = byRank.get(r) ?? [];
    bucket.push(node);
    byRank.set(r, bucket);
  }
  const maxRank = Math.max(0, ...byRank.keys());
  const maxCols = Math.max(1, ...[...byRank.values()].map((row) => row.length));
  const glance = glanceFromLineage(lineage);
  const vertical = !glance.hasBranching || maxCols <= 2;

  const placed = new Map<string, ProvenanceLayoutNode>();
  const incomingCount = new Map<string, number>();
  for (const node of lineage.nodes) incomingCount.set(node.cache_id, 0);
  for (const edge of lineage.edges) {
    incomingCount.set(edge.to_cache_id, (incomingCount.get(edge.to_cache_id) ?? 0) + 1);
  }

  if (vertical) {
    for (let r = 0; r <= maxRank; r++) {
      const row = byRank.get(r) ?? [];
      const rowWidth = row.length * NODE_W + (row.length - 1) * COL_GAP;
      const startX = PAD_X + Math.max(0, (maxCols * NODE_W + (maxCols - 1) * COL_GAP - rowWidth) / 2);
      row.forEach((node, col) => {
        placed.set(
          node.cache_id,
          buildNode(node, {
            isRoot: node.cache_id === lineage.root_cache_id,
            isSource: (incomingCount.get(node.cache_id) ?? 0) === 0,
            rank: r,
            x: startX + col * (NODE_W + COL_GAP),
            y: PAD_Y + r * (NODE_H + ROW_GAP),
          }),
        );
      });
    }
  } else {
    for (let r = 0; r <= maxRank; r++) {
      const col = byRank.get(r) ?? [];
      col.forEach((node, row) => {
        placed.set(
          node.cache_id,
          buildNode(node, {
            isRoot: node.cache_id === lineage.root_cache_id,
            isSource: (incomingCount.get(node.cache_id) ?? 0) === 0,
            rank: r,
            x: PAD_X + r * (NODE_W + COL_GAP),
            y: PAD_Y + row * (NODE_H + ROW_GAP),
          }),
        );
      });
    }
  }

  const nodes = [...placed.values()];
  const edges: ProvenanceLayoutEdge[] = lineage.edges
    .map((edge, idx) => {
      const from = placed.get(edge.from_cache_id);
      const to = placed.get(edge.to_cache_id);
      if (!from || !to) return null;
      const x1 = vertical ? from.x + from.width / 2 : from.x + from.width;
      const y1 = vertical ? from.y + from.height : from.y + from.height / 2;
      const x2 = vertical ? to.x + to.width / 2 : to.x;
      const y2 = vertical ? to.y : to.y + to.height / 2;
      return {
        id: `${edge.from_cache_id}->${edge.to_cache_id}-${idx}`,
        fromCacheId: edge.from_cache_id,
        toCacheId: edge.to_cache_id,
        path: edgePath(x1, y1, x2, y2, vertical),
      };
    })
    .filter((e): e is ProvenanceLayoutEdge => e != null);

  const width = vertical
    ? PAD_X * 2 + maxCols * NODE_W + (maxCols - 1) * COL_GAP
    : PAD_X * 2 + (maxRank + 1) * NODE_W + maxRank * COL_GAP;
  const height = vertical
    ? PAD_Y * 2 + (maxRank + 1) * NODE_H + maxRank * ROW_GAP
    : PAD_Y * 2 + maxCols * NODE_H + (maxCols - 1) * ROW_GAP;

  return {
    width,
    height,
    orientation: vertical ? "vertical" : "horizontal",
    nodes,
    edges,
    glance,
  };
}
