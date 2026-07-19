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
});
