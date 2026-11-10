import type { NodeSchema, Workflow } from "./types";
import { isAiNodeType } from "./nodeKinds";

export type ContributionBucket = "human" | "ai" | "mixed" | "unknown" | "passthrough";

export type ContributionMix = {
  human: number;
  ai: number;
  /** Classified contributing nodes (excludes passthrough / unknown). */
  counted: number;
  /** Nodes skipped as utility passthrough. */
  passthrough: number;
  /** Nodes with unknown / missing class. */
  unknown: number;
  /** human + ai percentages, each 0–100, summing to 100 when counted > 0. */
  humanPercent: number;
  aiPercent: number;
  /** e.g. "Human 38% · AI 62%" or null when nothing classified. */
  label: string | null;
};

const HUMAN_CLASSES = new Set(["human_recorded", "human_edited"]);
const AI_CLASSES = new Set(["ai_generated", "ai_transformed"]);

export function contributionBucket(
  provenanceClass: string | undefined | null,
  opts: {
    passthrough?: boolean;
    nodeType?: string;
    category?: string | null;
  } = {},
): ContributionBucket {
  if (opts.passthrough) return "passthrough";
  const klass = (provenanceClass ?? "").trim().toLowerCase();
  if (HUMAN_CLASSES.has(klass)) return "human";
  if (AI_CLASSES.has(klass)) return "ai";
  if (klass === "mixed") return "mixed";
  if (klass === "unknown" || !klass) {
    // Schema not loaded yet — coarse AI vs core fallback for live canvas.
    if (opts.nodeType && isAiNodeType(opts.nodeType, opts.category)) return "ai";
    if (opts.nodeType) return "human";
    return "unknown";
  }
  return "unknown";
}

function roundShare(part: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((part / total) * 100);
}

/** Normalize so human% + ai% === 100 when there is any classified weight. */
export function percentagesFromWeights(human: number, ai: number): {
  humanPercent: number;
  aiPercent: number;
} {
  const total = human + ai;
  if (total <= 0) return { humanPercent: 0, aiPercent: 0 };
  const humanPercent = roundShare(human, total);
  const aiPercent = 100 - humanPercent;
  return { humanPercent, aiPercent };
}

export function formatContributionMixLabel(humanPercent: number, aiPercent: number): string {
  return `Human ${humanPercent}% · AI ${aiPercent}%`;
}

/**
 * Contribution Mix from graph node types (provenance classes), not audio ML.
 * Passthrough / utility nodes are excluded; `mixed` counts half human / half AI.
 */
export function computeContributionMix(
  workflow: Workflow,
  nodeSchemas: Record<string, NodeSchema> = {},
): ContributionMix {
  let human = 0;
  let ai = 0;
  let passthrough = 0;
  let unknown = 0;

  for (const node of workflow.nodes) {
    const schema = nodeSchemas[node.type];
    const bucket = contributionBucket(schema?.provenance_class, {
      passthrough: Boolean(schema?.provenance_passthrough),
      nodeType: node.type,
      category: schema?.category,
    });
    if (bucket === "passthrough") {
      passthrough += 1;
      continue;
    }
    if (bucket === "human") {
      human += 1;
      continue;
    }
    if (bucket === "ai") {
      ai += 1;
      continue;
    }
    if (bucket === "mixed") {
      human += 0.5;
      ai += 0.5;
      continue;
    }
    unknown += 1;
  }

  const counted = human + ai;
  const { humanPercent, aiPercent } = percentagesFromWeights(human, ai);
  return {
    human,
    ai,
    counted,
    passthrough,
    unknown,
    humanPercent,
    aiPercent,
    label: counted > 0 ? formatContributionMixLabel(humanPercent, aiPercent) : null,
  };
}
