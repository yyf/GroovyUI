import { describe, expect, it } from "vitest";
import {
  compareByComputePreset,
  computeCardLabel,
  matchesComputePreset,
  type ComputeResolved,
} from "./modelCompute";

const apple: ComputeResolved = {
  runtimes: ["mlx", "cuda"],
  requires_cuda: false,
  presets: ["apple", "cuda"],
  label: "Apple Silicon (MLX) / CUDA · ~4 GB",
};

const cudaOnly: ComputeResolved = {
  runtimes: ["cuda"],
  requires_cuda: true,
  presets: ["cuda"],
  label: "CUDA required · ~8 GB VRAM",
};

const cpu: ComputeResolved = {
  runtimes: ["cpu"],
  requires_cuda: false,
  presets: ["apple", "cpu"],
  label: "CPU · ~1 GB",
};

describe("modelCompute", () => {
  it("matches hardware presets", () => {
    expect(matchesComputePreset(apple, "any")).toBe(true);
    expect(matchesComputePreset(apple, "apple")).toBe(true);
    expect(matchesComputePreset(cudaOnly, "apple")).toBe(false);
    expect(matchesComputePreset(cudaOnly, "cuda")).toBe(true);
    expect(matchesComputePreset(cpu, "cpu")).toBe(true);
  });

  it("formats card labels", () => {
    expect(computeCardLabel(apple, 4)).toContain("Apple Silicon");
    expect(computeCardLabel(undefined, 2)).toBe("~2 GB VRAM");
  });

  it("sorts apple-first under Apple Silicon preset", () => {
    const rows = [
      { compute_resolved: cudaOnly, vram_gb_estimate: 8, name: "Cuda Heavy" },
      { compute_resolved: apple, vram_gb_estimate: 4, name: "MLX" },
    ];
    rows.sort((a, b) => compareByComputePreset(a, b, "apple"));
    expect(rows[0].name).toBe("MLX");
  });
});
