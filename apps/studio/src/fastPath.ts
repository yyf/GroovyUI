import { InstallCancelledError } from "./api";
import type { ModelInstallState, Workflow } from "./types";

export type MissingFastPathModel = {
  modelId: string;
  status: string;
  name: string;
  reason: string;
};

export type FastPathRunResult = "completed" | "cancelled";

export function applyModelSwaps(
  workflow: Workflow,
  swaps: Array<{ nodeId: string; modelId: string }>,
): Workflow {
  const replacements = new Map(swaps.map((swap) => [swap.nodeId, swap.modelId]));
  return {
    ...workflow,
    nodes: workflow.nodes.map((node) => {
      const modelId = replacements.get(node.id);
      return modelId
        ? { ...node, widgets: { ...node.widgets, model: modelId } }
        : node;
    }),
  };
}

/** Select one listenable Preview sink so first audition does not render unrelated exports. */
export function resolveFastPathPreviewTarget(workflow: Workflow): string | null {
  const previews = workflow.nodes.filter((node) => node.type === "Preview");
  const audioPreview = previews.find((preview) =>
    workflow.links.some(
      (link) => link.to[0] === preview.id && link.type === "AUDIO",
    ),
  );
  return audioPreview?.id ?? null;
}

type FastPathDependencies = {
  workflow: Workflow;
  findMissing: (workflow: Workflow) => Promise<MissingFastPathModel[]>;
  installModel: (
    modelId: string,
    onProgress: (state: ModelInstallState) => void,
    options?: { shouldStop?: () => boolean },
  ) => Promise<ModelInstallState>;
  renderPreview: () => Promise<boolean>;
  shouldStop: () => boolean;
  onInstallStart?: (model: MissingFastPathModel, index: number, total: number) => void;
  onInstallComplete?: (model: MissingFastPathModel, index: number, total: number) => void;
  onInstallProgress?: (
    model: MissingFastPathModel,
    index: number,
    total: number,
    state: ModelInstallState,
  ) => void;
};

/**
 * Explicitly committed compliance-first sequence.
 *
 * Stop requests cancel the active model install via the install API, then
 * prevent later models and render from starting.
 */
export async function runFastPathSequence({
  workflow,
  findMissing,
  installModel,
  renderPreview,
  shouldStop,
  onInstallStart,
  onInstallComplete,
  onInstallProgress,
}: FastPathDependencies): Promise<FastPathRunResult> {
  const missing = await findMissing(workflow);
  for (const [index, model] of missing.entries()) {
    if (shouldStop()) return "cancelled";
    if (model.reason === "unknown") {
      throw new Error(`Unknown model cannot be installed: ${model.modelId}`);
    }
    onInstallStart?.(model, index, missing.length);
    try {
      await installModel(
        model.modelId,
        (state) => {
          onInstallProgress?.(model, index, missing.length, state);
        },
        { shouldStop },
      );
    } catch (error) {
      if (error instanceof InstallCancelledError || shouldStop()) {
        return "cancelled";
      }
      throw error;
    }
    onInstallComplete?.(model, index, missing.length);
    if (shouldStop()) return "cancelled";
  }

  const unresolved = await findMissing(workflow);
  if (unresolved.length > 0) {
    throw new Error(
      `Inference setup is still required for ${unresolved
        .map((model) => model.name || model.modelId)
        .join(", ")}. Open Model Browser for recovery steps.`,
    );
  }
  if (shouldStop()) return "cancelled";

  const completed = await renderPreview();
  if (!completed) throw new Error("Render did not complete.");
  return "completed";
}
