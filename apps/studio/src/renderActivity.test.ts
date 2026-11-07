import { describe, expect, it } from "vitest";
import {
  AI_DOWNLOAD_HINT_MS,
  aiNodePhaseLabel,
  nodeTimingPercents,
  nodeStatusOnProgress,
  slowAiDownloadLabel,
} from "./renderActivity";

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

describe("aiNodePhaseLabel", () => {
  it("is silent when idle or not the current AI hop", () => {
    expect(
      aiNodePhaseLabel({
        isCurrent: false,
        running: true,
        isAi: true,
        staleMs: 0,
      }),
    ).toBeUndefined();
    expect(
      aiNodePhaseLabel({
        isCurrent: true,
        running: false,
        isAi: true,
        staleMs: 0,
      }),
    ).toBeUndefined();
    expect(
      aiNodePhaseLabel({
        isCurrent: true,
        running: true,
        isAi: false,
        staleMs: 0,
      }),
    ).toBeUndefined();
  });

  it("labels rendering, then downloading after a quiet pause", () => {
    expect(
      aiNodePhaseLabel({
        isCurrent: true,
        running: true,
        isAi: true,
        message: "Running TranslateText...",
        staleMs: 100,
      }),
    ).toBe("rendering");
    expect(
      aiNodePhaseLabel({
        isCurrent: true,
        running: true,
        isAi: true,
        message: "Running TranslateText...",
        staleMs: AI_DOWNLOAD_HINT_MS,
      }),
    ).toBe("downloading");
  });

  it("labels installing from the progress message", () => {
    expect(
      aiNodePhaseLabel({
        isCurrent: true,
        running: true,
        isAi: true,
        message: "Installing model weights…",
        staleMs: 0,
      }),
    ).toBe("installing");
  });
});

describe("nodeTimingPercents", () => {
  it("shares all timed node time so chips sum to 100%", () => {
    // Include core + AI hops; ignore wall-clock padding in total_ms.
    expect(
      nodeTimingPercents({ n1: 250, n2: 750, n3: 1000 }, 2500, ["n1", "n2", "n3"]),
    ).toEqual({ n1: "13%", n2: "37%", n3: "50%" });
  });

  it("falls back to summing timings when total is missing", () => {
    expect(nodeTimingPercents({ a: 1, b: 3 }, undefined, ["a", "b"])).toEqual({
      a: "25%",
      b: "75%",
    });
  });

  it("rounds with largest remainder so percents sum to 100", () => {
    const labels = nodeTimingPercents({ a: 1, b: 1, c: 1 }, undefined, ["a", "b", "c"]);
    const sum = Object.values(labels).reduce((acc, label) => acc + Number.parseInt(label, 10), 0);
    expect(sum).toBe(100);
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
