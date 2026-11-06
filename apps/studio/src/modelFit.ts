/** Compare a model's published needs to free resources on this machine. */

export type HostResources = {
  ramAvailableGb: number | null;
  vramAvailableGb: number | null;
  diskFreeMb: number | null;
  cuda: boolean;
};

export type ModelNeeds = {
  vramGb?: number | null;
  downloadMb?: number | null;
  requiresCuda?: boolean;
  runtimes?: string[];
  /** Hugging Face weight-size guess, not a measured inference budget. */
  approximate?: boolean;
  /** Disk figure is the weight-size guess, not a published repo size. */
  downloadApproximate?: boolean;
};

export type ResourceFit = {
  key: "memory" | "disk";
  /** RAM, VRAM, or Disk. */
  label: string;
  needLabel: string;
  haveLabel: string;
  /** Share of currently free resource the model asks for. Over 100 means it does not fit. */
  percent: number | null;
  percentLabel: string | null;
  fits: boolean | null;
  summary: string;
  /** Weight-only estimate from a Hub safetensors listing. */
  approximate?: boolean;
  /** Hub did not publish a size. The row keeps the bar and shows N/A. */
  unavailable?: boolean;
};

function trimNumber(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function formatGb(value: number): string {
  return `${trimNumber(value)} GB`;
}

function formatBytesMb(mb: number): string {
  if (mb >= 1024) return formatGb(mb / 1024);
  return `${Math.round(mb)} MB`;
}

function percentOf(need: number, have: number): number | null {
  if (!Number.isFinite(need) || need <= 0) return null;
  if (!Number.isFinite(have) || have <= 0) return null;
  return Math.round((need / have) * 1000) / 10;
}

function memoryTarget(needs: ModelNeeds, host: HostResources): "vram" | "ram" {
  if (needs.requiresCuda) return "vram";
  const runtimes = new Set(needs.runtimes ?? []);
  const appleOrCpu = runtimes.has("mlx") || runtimes.has("mps") || runtimes.has("cpu");
  if (host.cuda && host.vramAvailableGb != null && runtimes.has("cuda") && !appleOrCpu) {
    return "vram";
  }
  return "ram";
}

export function unavailableResourceRows(): ResourceFit[] {
  const summary = "Weight size not listed on Hugging Face";
  return (["RAM", "Disk"] as const).map((label) => ({
    key: label === "RAM" ? "memory" : "disk",
    label,
    needLabel: "N/A",
    haveLabel: "N/A",
    percent: null,
    percentLabel: "N/A",
    fits: null,
    approximate: false,
    unavailable: true,
    summary,
  }));
}

export function modelResourceFit(needs: ModelNeeds, host: HostResources | null): ResourceFit[] {
  if (!host) return [];
  const rows: ResourceFit[] = [];
  const approximate = Boolean(needs.approximate);
  const needGb = Number(needs.vramGb ?? 0);
  if (needGb > 0) {
    const target = memoryTarget(needs, host);
    const have = target === "vram" ? host.vramAvailableGb : host.ramAvailableGb;
    const label = target === "vram" ? "VRAM" : "RAM";
    if (have == null && target === "vram" && host.ramAvailableGb != null) {
      const ram = host.ramAvailableGb;
      const percent = percentOf(needGb, ram);
      const fits = needGb <= ram + 0.05;
      rows.push({
        key: "memory",
        label: "RAM",
        needLabel: formatGb(needGb),
        haveLabel: `${formatGb(ram)} free`,
        percent,
        percentLabel: percent == null ? null : `${trimNumber(percent)}%`,
        fits,
        approximate,
        summary: `${formatGb(needGb)} ${approximate ? "est. weights" : "VRAM need"} · ${formatGb(ram)} RAM free${
          percent == null ? "" : ` · ${trimNumber(percent)}% of free`
        } · no GPU on this machine`,
      });
    } else if (have == null) {
      rows.push({
        key: "memory",
        label,
        needLabel: formatGb(needGb),
        haveLabel: "not measured",
        percent: null,
        percentLabel: null,
        fits: null,
        approximate,
        summary: `${formatGb(needGb)} ${approximate ? "est. weights" : "need"} · ${label} not measured on this machine`,
      });
    } else {
      const percent = percentOf(needGb, have);
      const fits = needGb <= have + 0.05;
      rows.push({
        key: "memory",
        label,
        needLabel: formatGb(needGb),
        haveLabel: `${formatGb(have)} free`,
        percent,
        percentLabel: percent == null ? null : `${trimNumber(percent)}%`,
        fits,
        approximate,
        summary: `${formatGb(needGb)} ${approximate ? "est. weights" : "need"} · ${formatGb(have)} free${
          percent == null ? "" : ` · ${trimNumber(percent)}% of free`
        }`,
      });
    }
  }

  const needMb = Number(needs.downloadMb ?? 0);
  if (needMb > 0) {
    const haveMb = host.diskFreeMb;
    if (haveMb == null) {
      rows.push({
        key: "disk",
        label: "Disk",
        needLabel: formatBytesMb(needMb),
        haveLabel: "not measured",
        percent: null,
        percentLabel: null,
        fits: null,
        approximate: Boolean(needs.downloadApproximate),
        summary: `${formatBytesMb(needMb)} download · disk not measured`,
      });
    } else {
      const percent = percentOf(needMb, haveMb);
      const fits = needMb <= haveMb;
      rows.push({
        key: "disk",
        label: "Disk",
        needLabel: formatBytesMb(needMb),
        haveLabel: `${formatBytesMb(haveMb)} free`,
        percent,
        percentLabel: percent == null ? null : `${trimNumber(percent)}%`,
        fits,
        approximate: Boolean(needs.downloadApproximate),
        summary: `${formatBytesMb(needMb)} download · ${formatBytesMb(haveMb)} free${
          percent == null ? "" : ` · ${trimNumber(percent)}% of free`
        }`,
      });
    }
  }
  return rows;
}

export function hostSnapshotLine(host: HostResources | null): string {
  if (!host) return "This machine · measuring free RAM, VRAM, and disk…";
  const parts: string[] = ["This machine"];
  if (host.cuda && host.vramAvailableGb != null) {
    parts.push(`${formatGb(host.vramAvailableGb)} VRAM free`);
  } else if (host.cuda) {
    parts.push("CUDA · VRAM not measured");
  }
  if (host.ramAvailableGb != null) {
    parts.push(`${formatGb(host.ramAvailableGb)} RAM free`);
  } else {
    parts.push("RAM not measured");
  }
  if (host.diskFreeMb != null) {
    parts.push(`${formatBytesMb(host.diskFreeMb)} disk free`);
  } else {
    parts.push("disk not measured");
  }
  return parts.join(" · ");
}
