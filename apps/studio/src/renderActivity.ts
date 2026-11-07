import { isAiNodeType } from "./nodeKinds";
import type { NodeRenderStatus } from "./types";

/** Hub/weight fetch has no progress ticks — surface a download hint after this pause. */
export const AI_DOWNLOAD_HINT_MS = 5_000;

export function slowAiDownloadLabel(input: {
  running: boolean;
  nodeType?: string | null;
  category?: string | null;
  staleMs: number;
}): string | undefined {
  if (!input.running || !input.nodeType) return undefined;
  if (!isAiNodeType(input.nodeType, input.category)) return undefined;
  if (input.staleMs < AI_DOWNLOAD_HINT_MS) return undefined;
  return "Downloading model…";
}

/**
 * Minimal live phase for the active AI hop.
 * Hub weight fetches are silent — after {@link AI_DOWNLOAD_HINT_MS} we label downloading.
 */
export function aiNodePhaseLabel(input: {
  isCurrent: boolean;
  running: boolean;
  isAi: boolean;
  message?: string | null;
  staleMs: number;
}): string | undefined {
  if (!input.running || !input.isCurrent || !input.isAi) return undefined;
  const msg = (input.message || "").toLowerCase();
  if (msg.includes("install")) return "installing";
  if (input.staleMs >= AI_DOWNLOAD_HINT_MS || msg.includes("download")) return "downloading";
  if (msg.includes("cache hit")) return "cached";
  return "rendering";
}

/**
 * Bottleneck gauge for every timed node after a completed render.
 *
 * Denominator is the sum of those node timings (full pipeline account), so chips
 * sum to 100%. Wall-clock `totalMs` is only a fallback when the sum is empty.
 * Largest-remainder rounding keeps displayed integers exact.
 */
export function nodeTimingPercents(
  timings: Record<string, number> | undefined,
  totalMs: number | undefined,
  nodeIds: Iterable<string>,
): Record<string, string> {
  if (!timings) return {};
  const entries: Array<{ id: string; ms: number }> = [];
  for (const id of nodeIds) {
    const raw = timings[id];
    if (raw == null) continue;
    entries.push({ id, ms: Math.max(0, raw) });
  }
  if (entries.length === 0) return {};

  const timedSum = entries.reduce((sum, row) => sum + row.ms, 0);
  const denom = timedSum > 0 ? timedSum : totalMs != null && totalMs > 0 ? totalMs : 0;
  if (denom <= 0) return {};

  const exact = entries.map((row) => (100 * row.ms) / denom);
  const floors = exact.map((value) => Math.floor(value));
  let remainder = 100 - floors.reduce((sum, value) => sum + value, 0);
  const byFrac = exact
    .map((value, index) => ({ index, frac: value - floors[index]! }))
    .sort((a, b) => b.frac - a.frac);
  const percents = [...floors];
  for (let i = 0; i < remainder; i++) {
    const slot = byFrac[i]?.index;
    if (slot == null) break;
    percents[slot] = (percents[slot] ?? 0) + 1;
  }

  const out: Record<string, string> = {};
  entries.forEach((row, index) => {
    out[row.id] = `${percents[index] ?? 0}%`;
  });
  return out;
}

/** @deprecated Use {@link nodeTimingPercents} — kept for call-site compatibility. */
export function aiNodeTimingPercents(
  timings: Record<string, number> | undefined,
  totalMs: number | undefined,
  nodeIds: Iterable<string>,
): Record<string, string> {
  return nodeTimingPercents(timings, totalMs, nodeIds);
}

/** Only the active node stays `running`; the previous hop is marked cached. */
export function nodeStatusOnProgress(
  prev: Record<string, NodeRenderStatus>,
  currentNode: string,
  previousRunning?: string,
): Record<string, NodeRenderStatus> {
  const next = { ...prev };
  if (previousRunning && previousRunning !== currentNode && next[previousRunning] === "running") {
    next[previousRunning] = "cached";
  }
  next[currentNode] = "running";
  return next;
}
