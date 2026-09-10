import type { NodeSchema, Workflow } from "./types";
import { DEFAULT_LOAD_AUDIO_PATH } from "./sampleDefaults";

/** Hugging Face-style org/repo or URL — not a local registry id. */
export function looksLikeExternalModelRef(modelId: string): boolean {
  const value = modelId.trim();
  if (!value) return false;
  if (value.includes("/") || value.includes("://")) return true;
  return false;
}

function fillEmptyLoadAudioPaths(workflow: Workflow): Workflow {
  let changed = false;
  const nodes = workflow.nodes.map((node) => {
    if (node.type !== "LoadAudio") return node;
    const raw = node.widgets?.path;
    const path = typeof raw === "string" ? raw.trim() : "";
    if (path) return node;
    changed = true;
    return { ...node, widgets: { ...node.widgets, path: DEFAULT_LOAD_AUDIO_PATH } };
  });
  return changed ? { ...workflow, nodes } : workflow;
}

/**
 * Safety net for Plan Apply: replace external/public model strings with the
 * node schema default, and fill empty LoadAudio paths with the demo sample.
 */
export function sanitizePlanWorkflowModels(
  workflow: Workflow,
  schemas: Record<string, NodeSchema>,
): Workflow {
  let changed = false;
  const nodes = workflow.nodes.map((node) => {
    const raw = node.widgets?.model;
    if (typeof raw !== "string" || !raw.trim()) return node;
    if (!looksLikeExternalModelRef(raw)) return node;
    const schema = schemas[node.type];
    const fallback = schema?.widgets?.find((widget) => widget.name === "model")?.default;
    if (typeof fallback !== "string" || !fallback.trim()) {
      changed = true;
      const { model: _drop, ...rest } = node.widgets;
      return { ...node, widgets: rest };
    }
    if (fallback === raw) return node;
    changed = true;
    return { ...node, widgets: { ...node.widgets, model: fallback } };
  });
  const withModels = changed ? { ...workflow, nodes } : workflow;
  return fillEmptyLoadAudioPaths(withModels);
}

/** Short canvas label — full detail stays on title tooltip + Inspector. */
export function shortCanvasIssueLabel(issue: string): string {
  const text = issue.replace(/\s+/g, " ").trim();
  const lower = text.toLowerCase();
  if (lower.includes("file_not_found") || lower.includes("empty path")) {
    return "Missing audio file";
  }
  if (lower.includes("unknown model")) return "Unknown model";
  if (lower.includes("unsupported_format")) return "Unsupported format";
  if (lower.startsWith("render failed")) {
    const rest = text.replace(/^render failed\s*/i, "").trim();
    if (rest.toLowerCase().includes("file_not_found") || rest.toLowerCase().includes("empty path")) {
      return "Missing audio file";
    }
  }
  if (text.length <= 28) return text;
  return `${text.slice(0, 25)}…`;
}
