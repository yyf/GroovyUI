import { describe, expect, it } from "vitest";
import { applyNodeSchemaFallbacks } from "./nodeSchemaFallbacks";
import type { NodeSchema } from "./types";

const baseSaveAudio: NodeSchema = {
  type: "SaveAudio",
  category: "GroovyUI/Core",
  inputs: [{ name: "audio", type: "AUDIO" }],
  outputs: [{ name: "output_0", type: "STRING" }],
  widgets: [],
};

describe("applyNodeSchemaFallbacks", () => {
  it("adds SaveAudio widgets when API returns none", () => {
    const merged = applyNodeSchemaFallbacks(baseSaveAudio);
    const names = merged.widgets.map((w) => w.name);
    expect(names).toContain("path");
    expect(names).toContain("filename");
    expect(names).toContain("format");
    expect(names).toContain("bit_depth");
  });

  it("does not duplicate widgets already present from API", () => {
    const withPath: NodeSchema = {
      ...baseSaveAudio,
      widgets: [{ name: "path", type: "STRING", default: "custom" }],
    };
    const merged = applyNodeSchemaFallbacks(withPath);
    expect(merged.widgets.filter((w) => w.name === "path")).toHaveLength(1);
    expect(merged.widgets.find((w) => w.name === "path")?.default).toBe("custom");
  });
});
