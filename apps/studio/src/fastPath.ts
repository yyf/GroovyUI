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

type FastPathDependencies = {
  workflow: Workflow;
  findMissing: (workflow: Workflow) => Promise<MissingFastPathModel[]>;
  installModel: (
    modelId: string,
    onProgress: (state: ModelInstallState) => void,
  ) => Promise<ModelInstallState>;
  renderAll: () => Promise<boolean>;
  shouldStop: () => boolean;
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
 * Cancellation is cooperative: it never interrupts an active package-manager
 * or weight write. It stops before the next model and guarantees render will
 * not start after a stop request.
 */
export async function runFastPathSequence({
  workflow,
  findMissing,
  installModel,
  renderAll,
  shouldStop,
  onInstallProgress,
}: FastPathDependencies): Promise<FastPathRunResult> {
  const missing = await findMissing(workflow);
  for (const [index, model] of missing.entries()) {
    if (shouldStop()) return "cancelled";
    if (model.reason === "unknown") {
      throw new Error(`Unknown model cannot be installed: ${model.modelId}`);
    }
    await installModel(model.modelId, (state) => {
      onInstallProgress?.(model, index, missing.length, state);
    });
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

  const completed = await renderAll();
  if (!completed) throw new Error("Render did not complete.");
  return "completed";
}
