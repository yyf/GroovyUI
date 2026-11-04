/** Hardware presets for Model Browser (Apple Silicon / CUDA / CPU). */

export type ComputePreset = "any" | "apple" | "cuda" | "cpu";

export type ComputeResolved = {
  runtimes: string[];
  requires_cuda: boolean;
  presets: string[];
  label: string;
  vram_gb_estimate?: number;
  memory_note?: string | null;
};

export const COMPUTE_PRESETS: Array<{
  value: ComputePreset;
  label: string;
  hint: string;
}> = [
  {
    value: "any",
    label: "Any",
    hint: "No hardware filter — default catalog sort",
  },
  {
    value: "apple",
    label: "Apple Silicon",
    hint: "MLX / MPS Mac path, or CPU-friendly on Mac (no CUDA required)",
  },
  {
    value: "cuda",
    label: "CUDA",
    hint: "NVIDIA GPU preferred or required",
  },
  {
    value: "cpu",
    label: "CPU",
    hint: "Runs without a discrete GPU",
  },
];

export function matchesComputePreset(
  resolved: ComputeResolved | null | undefined,
  preset: ComputePreset,
): boolean {
  if (!preset || preset === "any") return true;
  if (!resolved?.presets?.length) {
    // Unresolved cards: keep visible under Any only.
    return false;
  }
  return resolved.presets.includes(preset);
}

export function computeCardLabel(
  resolved: ComputeResolved | null | undefined,
  vramGb: number | undefined,
): string {
  if (resolved?.label?.trim()) return resolved.label.trim();
  if (vramGb != null && vramGb > 0) return `~${vramGb} GB VRAM`;
  return "Compute unknown";
}

export function computePillClass(resolved: ComputeResolved | null | undefined): string {
  if (resolved?.requires_cuda) return "pill pill--warning";
  if (resolved?.runtimes?.includes("mlx") || resolved?.runtimes?.includes("mps")) {
    return "pill pill--ready";
  }
  if (resolved?.runtimes?.includes("cpu") && !resolved?.runtimes?.includes("cuda")) {
    return "pill pill--neutral";
  }
  return "pill pill--neutral";
}

/** Stable sort for an active hardware preset (lower rank first). */
export function compareByComputePreset(
  a: { compute_resolved?: ComputeResolved | null; vram_gb_estimate?: number; name?: string },
  b: { compute_resolved?: ComputeResolved | null; vram_gb_estimate?: number; name?: string },
  preset: ComputePreset,
): number {
  if (!preset || preset === "any") return 0;
  const rank = (model: typeof a): number => {
    const runtimes = new Set(model.compute_resolved?.runtimes ?? []);
    const requires = Boolean(model.compute_resolved?.requires_cuda);
    if (preset === "apple") {
      if (runtimes.has("mlx") || runtimes.has("mps")) return 0;
      return 1;
    }
    if (preset === "cuda") {
      return requires ? 0 : 1;
    }
    if (preset === "cpu") {
      return runtimes.has("cpu") && !requires ? 0 : 1;
    }
    return 0;
  };
  const ra = rank(a);
  const rb = rank(b);
  if (ra !== rb) return ra - rb;
  const va = Number(a.vram_gb_estimate ?? 0);
  const vb = Number(b.vram_gb_estimate ?? 0);
  if (preset === "cuda" && va !== vb) return vb - va;
  if (va !== vb) return va - vb;
  return String(a.name ?? "").localeCompare(String(b.name ?? ""));
}
