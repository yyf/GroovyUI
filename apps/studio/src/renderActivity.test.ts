import { describe, expect, it } from "vitest";
import { AI_DOWNLOAD_HINT_MS, nodeStatusOnProgress, slowAiDownloadLabel } from "./renderActivity";

describe("slowAiDownloadLabel", () => {
  it("is silent for DSP nodes and short AI waits", () => {
    expect(
      slowAiDownloadLabel({
        running: true,
        nodeType: "Granulate",
        staleMs: 30_000,
      }),
    ).toBeUndefined();
    expect(
      slowAiDownloadLabel({
        running: true,
        nodeType: "GenerateAudio",
        staleMs: AI_DOWNLOAD_HINT_MS - 1,
      }),
    ).toBeUndefined();
  });

  it("labels a slow AI hop as a model download", () => {
    expect(
      slowAiDownloadLabel({
        running: true,
        nodeType: "GenerateAudio",
        staleMs: AI_DOWNLOAD_HINT_MS,
      }),
    ).toBe("Downloading model…");
    expect(
      slowAiDownloadLabel({
        running: true,
        nodeType: "CustomInfer",
        category: "GroovyUI/AI",
        staleMs: 8_000,
      }),
    ).toBe("Downloading model…");
  });
});

describe("nodeStatusOnProgress", () => {
  it("highlights only the current node", () => {
    const first = nodeStatusOnProgress({}, "n1");
    expect(first).toEqual({ n1: "running" });
    const second = nodeStatusOnProgress(first, "n23", "n1");
    expect(second).toEqual({ n1: "cached", n23: "running" });
  });
});
