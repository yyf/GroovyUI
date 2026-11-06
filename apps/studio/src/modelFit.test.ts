import { describe, expect, it } from "vitest";
import { hostSnapshotLine, modelResourceFit, unavailableResourceRows, type HostResources } from "./modelFit";

const mac: HostResources = {
  ramAvailableGb: 14.2,
  vramAvailableGb: null,
  diskFreeMb: 80_000,
  cuda: false,
};

const cuda: HostResources = {
  ramAvailableGb: 32,
  vramAvailableGb: 11.2,
  diskFreeMb: 20_000,
  cuda: true,
};

describe("modelResourceFit", () => {
  it("compares Apple/CPU models to free RAM and disk, with percent of free", () => {
    const rows = modelResourceFit(
      { vramGb: 8, downloadMb: 6300, requiresCuda: false, runtimes: ["cpu", "mps"] },
      mac,
    );
    expect(rows[0]).toMatchObject({
      label: "RAM",
      needLabel: "8 GB",
      haveLabel: "14.2 GB free",
      percentLabel: "56.3%",
      fits: true,
    });
    expect(rows[1]?.label).toBe("Disk");
    expect(rows[1]?.fits).toBe(true);
    expect(rows[1]?.percentLabel).toBe("7.9%");
  });

  it("flags a model that asks for more free RAM than this machine has", () => {
    const rows = modelResourceFit({ vramGb: 16, runtimes: ["cpu"] }, mac);
    expect(rows[0]?.fits).toBe(false);
    expect(rows[0]?.percent).toBeGreaterThan(100);
  });

  it("compares CUDA-required models to free VRAM", () => {
    const rows = modelResourceFit(
      { vramGb: 8, requiresCuda: true, runtimes: ["cuda"] },
      cuda,
    );
    expect(rows[0]?.label).toBe("VRAM");
    expect(rows[0]?.haveLabel).toBe("11.2 GB free");
    expect(rows[0]?.fits).toBe(true);
  });

  it("marks a weight-derived disk figure as an estimate", () => {
    const rows = modelResourceFit(
      { vramGb: 1.5, downloadMb: 1536, approximate: true, downloadApproximate: true, runtimes: ["cpu"] },
      mac,
    );
    expect(rows.map((row) => row.label)).toEqual(["RAM", "Disk"]);
    expect(rows[1]?.approximate).toBe(true);
    expect(rows[1]?.needLabel).toBe("1.5 GB");
  });

  it("compares a CUDA model's memory need to free RAM when this machine has no GPU", () => {
    const rows = modelResourceFit({ vramGb: 8, requiresCuda: true, runtimes: ["cuda"] }, mac);
    expect(rows[0]?.label).toBe("RAM");
    expect(rows[0]?.haveLabel).toBe("14.2 GB free");
    expect(rows[0]?.fits).toBe(true);
    expect(rows[0]?.summary).toContain("no GPU");
  });
});

describe("unavailableResourceRows", () => {
  it("keeps RAM and Disk bars and marks both N/A", () => {
    const rows = unavailableResourceRows();
    expect(rows.map((row) => row.label)).toEqual(["RAM", "Disk"]);
    expect(rows.every((row) => row.unavailable && row.needLabel === "N/A" && row.percent == null)).toBe(true);
  });
});

describe("hostSnapshotLine", () => {
  it("lists free RAM and disk when there is no GPU", () => {
    expect(hostSnapshotLine(mac)).toBe("This machine · 14.2 GB RAM free · 78.1 GB disk free");
  });

  it("includes free VRAM on CUDA hosts", () => {
    expect(hostSnapshotLine(cuda)).toContain("11.2 GB VRAM free");
    expect(hostSnapshotLine(null)).toContain("measuring");
  });
});
