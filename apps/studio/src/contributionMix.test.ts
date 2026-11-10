import { describe, expect, it } from "vitest";
import {
  computeContributionMix,
  contributionBucket,
  formatContributionMixLabel,
  percentagesFromWeights,
} from "./contributionMix";
import type { NodeSchema, Workflow } from "./types";

function workflow(nodes: Array<{ id: string; type: string }>): Workflow {
  return {
    id: "wf",
    schema_version: "0.1.0",
    groovy_version: "0.1.0",
    nodes: nodes.map((node) => ({ ...node, widgets: {} })),
    links: [],
    groups: [],
    metadata: { title: "test" },
  };
}

const schemas: Record<string, NodeSchema> = {
  LoadAudio: {
    type: "LoadAudio",
    category: "GroovyUI/Core",
    provenance_class: "human_recorded",
    provenance_passthrough: false,
    inputs: [],
    outputs: [{ name: "audio", type: "AUDIO" }],
    widgets: [],
  },
  Denoise: {
    type: "Denoise",
    category: "GroovyUI/AI",
    provenance_class: "ai_transformed",
    provenance_passthrough: false,
    inputs: [],
    outputs: [{ name: "audio", type: "AUDIO" }],
    widgets: [],
  },
  GenerateAudio: {
    type: "GenerateAudio",
    category: "GroovyUI/AI",
    provenance_class: "ai_generated",
    provenance_passthrough: false,
    inputs: [],
    outputs: [{ name: "audio", type: "AUDIO" }],
    widgets: [],
  },
  Preview: {
    type: "Preview",
    category: "GroovyUI/Core",
    provenance_class: "human_edited",
    provenance_passthrough: true,
    inputs: [],
    outputs: [{ name: "audio", type: "AUDIO" }],
    widgets: [],
  },
  Mix: {
    type: "Mix",
    category: "GroovyUI/Core",
    provenance_class: "human_edited",
    provenance_passthrough: true,
    inputs: [],
    outputs: [{ name: "audio", type: "AUDIO" }],
    widgets: [],
  },
};

describe("contributionBucket", () => {
  it("maps provenance classes", () => {
    expect(contributionBucket("human_recorded")).toBe("human");
    expect(contributionBucket("ai_generated")).toBe("ai");
    expect(contributionBucket("mixed")).toBe("mixed");
    expect(contributionBucket("human_edited", { passthrough: true })).toBe("passthrough");
  });
});

describe("percentagesFromWeights", () => {
  it("rounds to a 100% pair", () => {
    expect(percentagesFromWeights(1, 1)).toEqual({ humanPercent: 50, aiPercent: 50 });
    expect(percentagesFromWeights(2, 3)).toEqual({ humanPercent: 40, aiPercent: 60 });
  });
});

describe("computeContributionMix", () => {
  it("formats Human / AI percentages and skips passthrough", () => {
    const mix = computeContributionMix(
      workflow([
        { id: "a", type: "LoadAudio" },
        { id: "b", type: "Denoise" },
        { id: "c", type: "GenerateAudio" },
        { id: "d", type: "Preview" },
        { id: "e", type: "Mix" },
      ]),
      schemas,
    );
    // 1 human + 2 AI → Human 33% · AI 67%
    expect(mix.counted).toBe(3);
    expect(mix.passthrough).toBe(2);
    expect(mix.label).toBe("Human 33% · AI 67%");
    expect(formatContributionMixLabel(38, 62)).toBe("Human 38% · AI 62%");
  });

  it("falls back to AI node kinds when schemas are missing", () => {
    const mix = computeContributionMix(
      workflow([
        { id: "a", type: "LoadAudio" },
        { id: "b", type: "Denoise" },
      ]),
      {},
    );
    expect(mix.label).toBe("Human 50% · AI 50%");
  });
});
