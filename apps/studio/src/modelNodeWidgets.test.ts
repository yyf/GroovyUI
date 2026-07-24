import { describe, expect, it } from "vitest";
import {
  mergeSpecWithModelParam,
  paramDefault,
  resolveInferenceParams,
  widgetsAfterModelSwap,
  widgetsForDroppedModel,
} from "./modelNodeWidgets";

describe("widgetsForDroppedModel", () => {
  it("applies schema defaults plus model inference defaults", () => {
    const widgets = widgetsForDroppedModel({
      schemaDefaults: { model: "placeholder", prompt: "", seed: -1 },
      modelId: "musicgen-small",
      params: [
        { name: "max_new_tokens", type: "INT", default: 512, min: 64, max: 2048 },
        { name: "guidance_scale", type: "FLOAT", default: 3, min: 0, max: 15 },
        { name: "temperature", type: "FLOAT", default: 1, min: 0, max: 2 },
      ],
    });
    expect(widgets).toEqual({
      model: "musicgen-small",
      prompt: "",
      seed: -1,
      max_new_tokens: 512,
      guidance_scale: 3,
      temperature: 1,
    });
  });
});

describe("widgetsAfterModelSwap", () => {
  it("resets model params and removes stale model-only keys", () => {
    const widgets = widgetsAfterModelSwap({
      existing: {
        model: "demucs-v4",
        prompt: "keep me",
        shifts: 3,
        overlap: 0.5,
        segment: 10,
        split: false,
      },
      modelId: "deepfilternet-v3",
      schemaWidgetNames: ["model", "prompt"],
      previousParams: [
        { name: "shifts", type: "INT", default: 1 },
        { name: "overlap", type: "FLOAT", default: 0.25 },
        { name: "segment", type: "FLOAT", default: 0 },
        { name: "split", type: "BOOLEAN", default: true },
      ],
      nextParams: [{ name: "strength", type: "FLOAT", default: 1, min: 0, max: 1 }],
    });
    expect(widgets).toEqual({
      model: "deepfilternet-v3",
      prompt: "keep me",
      strength: 1,
    });
  });
});

describe("mergeSpecWithModelParam", () => {
  it("overlays model ranges onto a schema widget", () => {
    const merged = mergeSpecWithModelParam(
      { name: "strength", type: "FLOAT", default: 0.5, min: 0, max: 2 },
      { name: "strength", type: "FLOAT", default: 1, min: 0, max: 1, description: "blend" },
    );
    expect(merged.default).toBe(1);
    expect(merged.min).toBe(0);
    expect(merged.max).toBe(1);
    expect(merged.description).toBe("blend");
  });
});

describe("paramDefault / resolveInferenceParams", () => {
  it("falls back by type when default is missing", () => {
    expect(paramDefault({ name: "x", type: "BOOLEAN" })).toBe(false);
    expect(paramDefault({ name: "x", type: "INT", min: 2 })).toBe(2);
  });

  it("uses client demucs mirror when card params are empty", () => {
    const params = resolveInferenceParams("demucs-v4", []);
    expect(params.some((param) => param.name === "shifts")).toBe(true);
  });
});
