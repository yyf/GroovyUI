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

/** Share of total job time for AI nodes only (shown after render completes). */
export function aiNodeTimingPercents(
  timings: Record<string, number> | undefined,
  totalMs: number | undefined,
  aiNodeIds: Iterable<string>,
): Record<string, string> {
  if (!timings) return {};
  const denom =
    totalMs != null && totalMs > 0
      ? totalMs
      : Object.values(timings).reduce((sum, ms) => sum + Math.max(0, ms), 0);
  if (denom <= 0) return {};
  const out: Record<string, string> = {};
  for (const id of aiNodeIds) {
    const ms = timings[id];
    if (ms == null) continue;
    out[id] = `${Math.round((100 * Math.max(0, ms)) / denom)}%`;
  }
  return out;
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
