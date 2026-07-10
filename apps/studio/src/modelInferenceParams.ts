import type { InferenceParamSpec } from "./types";

const MODEL_INFERENCE_PARAMS: Record<string, InferenceParamSpec[]> = {
  "demucs-v4": [
    {
      name: "shifts",
      type: "INT",
      default: 1,
      min: 0,
      max: 5,
      description: "Random shift passes — higher improves quality but slows render.",
    },
    {
      name: "overlap",
      type: "FLOAT",
      default: 0.25,
      min: 0,
      max: 0.99,
      description: "Overlap between analysis segments.",
    },
    {
      name: "segment",
      type: "FLOAT",
      default: 0,
      min: 0,
      max: 60,
      description: "Segment length in seconds (0 = model default).",
    },
    {
      name: "split",
      type: "BOOLEAN",
      default: true,
      description: "Split long files into segments during separation.",
    },
  ],
  "demucs-v4-ht": [
    {
      name: "shifts",
      type: "INT",
      default: 1,
      min: 0,
      max: 5,
      description: "Random shift passes — higher improves quality but slows render.",
    },
    {
      name: "overlap",
      type: "FLOAT",
      default: 0.25,
      min: 0,
      max: 0.99,
      description: "Overlap between analysis segments.",
    },
    {
      name: "segment",
      type: "FLOAT",
      default: 0,
      min: 0,
      max: 60,
      description: "Segment length in seconds (0 = model default).",
    },
    {
      name: "split",
      type: "BOOLEAN",
      default: true,
      description: "Split long files into segments during separation.",
    },
  ],
};

export function inferenceParamsForModel(modelId: string): InferenceParamSpec[] {
  return MODEL_INFERENCE_PARAMS[modelId] ?? [];
}
