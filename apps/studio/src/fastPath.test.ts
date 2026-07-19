import { describe, expect, it, vi } from "vitest";
import { applyModelSwaps, runFastPathSequence } from "./fastPath";
import type { ModelInstallState, Workflow } from "./types";

const workflow: Workflow = {
  schema_version: "1.0.0",
  groovy_version: "0.1.0",
  id: "fast-path-test",
  metadata: { title: "Fast path" },
  nodes: [
    { id: "n1", type: "Denoise", widgets: { model: "model-a" } },
    { id: "n2", type: "Preview", widgets: {} },
  ],
  links: [{ id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" }],
  groups: [],
};

const ready = (modelId: string): ModelInstallState => ({
  model_id: modelId,
  status: "ready",
  progress: 1,
});

describe("runFastPathSequence", () => {
  it("applies a confirmed optimizer plan atomically without mutating the source", () => {
    const optimized = applyModelSwaps(workflow, [
      { nodeId: "n1", modelId: "commercial-model" },
    ]);
    expect(optimized.nodes[0].widgets.model).toBe("commercial-model");
    expect(workflow.nodes[0].widgets.model).toBe("model-a");
    expect(optimized.nodes[1]).toEqual(workflow.nodes[1]);
  });

  it("installs the reviewed chain before rendering", async () => {
    const calls: string[] = [];
    let scan = 0;
    const result = await runFastPathSequence({
      workflow,
      findMissing: async () => {
        scan += 1;
        calls.push(`scan-${scan}`);
        return scan === 1
          ? [{ modelId: "model-a", name: "Model A", status: "missing", reason: "not_installed" }]
          : [];
      },
      installModel: async (modelId, onProgress) => {
        calls.push(`install-${modelId}`);
        onProgress(ready(modelId));
        return ready(modelId);
      },
      renderAll: async () => {
        calls.push("render-all");
        return true;
      },
      shouldStop: () => false,
    });

    expect(result).toBe("completed");
    expect(calls).toEqual(["scan-1", "install-model-a", "scan-2", "render-all"]);
  });

  it("stops after the active model without starting another install or render", async () => {
    let stopRequested = false;
    const installModel = vi.fn(async (modelId: string) => {
      stopRequested = true;
      return ready(modelId);
    });
    const renderAll = vi.fn(async () => true);

    const result = await runFastPathSequence({
      workflow,
      findMissing: async () => [
        { modelId: "model-a", name: "Model A", status: "missing", reason: "not_installed" },
        { modelId: "model-b", name: "Model B", status: "missing", reason: "not_installed" },
      ],
      installModel,
      renderAll,
      shouldStop: () => stopRequested,
    });

    expect(result).toBe("cancelled");
    expect(installModel).toHaveBeenCalledTimes(1);
    expect(renderAll).not.toHaveBeenCalled();
  });
});
