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
