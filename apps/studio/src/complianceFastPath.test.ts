import { describe, expect, it } from "vitest";
import { fastPathBlockReason } from "./components/ComplianceDrawer";
import type { LicenseScanSummary } from "./types";

function scan(
  overrides: Partial<LicenseScanSummary> = {},
): LicenseScanSummary {
  return {
    workflow_id: "wf",
    workflow_title: "Workflow",
    license_rows: [],
    warnings: [],
    commercial_ok: true,
    flags: [],
    swap_suggestions: [],
    scan_ok: true,
    agent: "license_scanner_v1",
    ...overrides,
  };
}

describe("compliance-first fast path", () => {
  it("blocks commercial use when a model is not commercial-safe", () => {
    expect(
      fastPathBlockReason(
        scan({
          commercial_ok: false,
          scan_ok: false,
          flags: [
            {
              node_id: "n1",
              node_type: "GenerateAudio",
              severity: "error",
              code: "NC_MODEL",
              message: "Non-commercial model",
            },
          ],
        }),
        "commercial",
      ),
    ).toContain("commercial-safe");
  });

  it("allows the same reviewed chain for evaluation use", () => {
    expect(
      fastPathBlockReason(
        scan({
          commercial_ok: false,
          scan_ok: false,
          flags: [
            {
              node_id: "n1",
              node_type: "GenerateAudio",
              severity: "error",
              code: "NC_MODEL",
              message: "Non-commercial model",
            },
          ],
        }),
        "evaluation",
      ),
    ).toBeNull();
  });

  it("always blocks unknown model references", () => {
    expect(
      fastPathBlockReason(
        scan({
          flags: [
            {
              node_id: "n1",
              node_type: "TTS",
              severity: "warning",
              code: "UNKNOWN_MODEL",
              message: "Unknown model",
            },
          ],
        }),
        "evaluation",
      ),
    ).toContain("unknown model");
  });

  it("blocks when machine preflight reports insufficient disk", () => {
    expect(
      fastPathBlockReason(
        scan({
          preflight: {
            download: { known_mb: 2000, unknown_models: [], already_installed: [] },
            peak_vram_gb: 1,
            render_time: {
              basis_audio_seconds: 60,
              low_seconds: 5,
              high_seconds: 30,
              confidence: "rough",
              note: "note",
            },
            models: [],
            nodes: [],
            checks: [
              {
                code: "DISK_SHORT",
                severity: "error",
                message: "Only 100 MB free; need about 3000 MB for ~2000 MB of model downloads.",
              },
            ],
          },
        }),
        "evaluation",
      ),
    ).toContain("Only 100 MB free");
  });
});
