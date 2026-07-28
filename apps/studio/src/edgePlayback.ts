import type { Workflow } from "./types";
import { edgeIdsOnPathToNode } from "./workflow";

/** Media / transport events that drive canvas edge dash animation. */
export type EdgePlaybackEvent =
  | "play"
  | "pause"
  | "ended"
  | "playback_failed"
  | "preview_cleared";

/**
 * Single source of truth for which workflow edges should animate.
 *
 * Animation turns ON only when audio actually starts (`play`).
 * Eager play requests must not set edges — failed autoplay would leave them stuck.
 * Pause / ended / failure / cleared preview always clear, even with no selection.
 */
export function nextActiveEdgeIds(args: {
  event: EdgePlaybackEvent;
  workflow: Workflow | null | undefined;
  /** Node whose upstream path should animate while playing. */
  targetNodeId: string | null | undefined;
}): Set<string> {
  const { event, workflow, targetNodeId } = args;
  if (event !== "play") {
    return new Set();
  }
  if (!workflow || !targetNodeId) {
    return new Set();
  }
  return edgeIdsOnPathToNode(workflow, targetNodeId);
}

/** Prefer the audition target set before play; fall back to current selection. */
export function resolveEdgePlaybackTarget(
  auditionTargetId: string | null | undefined,
  selectedNodeId: string | null | undefined,
): string | null {
  return auditionTargetId ?? selectedNodeId ?? null;
}
