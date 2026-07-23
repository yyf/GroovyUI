import { describe, expect, it } from "vitest";
import { buildCleanMachineReport } from "./cleanMachineReport";
import type { ActivationDiagnosticsSummary } from "./types";

const diagnostics: ActivationDiagnosticsSummary = {
  path: "/tmp/workspace/.groovy/diagnostics/activation.jsonl",
  stored_locally: true,
  session_count: 1,
  event_count: 3,
  latest_session: {
    session_id: "session_abcdefgh",
    started_at: "2026-07-22T00:00:00+00:00",
    outcome: "audible",
    elapsed_ms: 8600,
    time_to_first_audible_ms: 8600,
    context: { source: "generate" },
    milestones: [
      { event: "task_started", elapsed_ms: 0, context: { source: "generate" } },
      { event: "playback_started", elapsed_ms: 8600, context: {} },
    ],
  },
};

describe("buildCleanMachineReport", () => {
  it("merges activation timing with a privacy-safe machine snapshot", () => {
    const report = buildCleanMachineReport({
      diagnostics,
      capabilities: {
        inference_mode: "real",
        inference_effective: "real",
        inference_stub_active: false,
        machine: {
          disk_free_mb: 12000,
          ram_available_gb: 16,
          vram_available_gb: 8,
          vram_source: "cuda:Test",
          torch_cuda_available: true,
          uv_available: true,
        },
      },
      capturedAt: "2026-07-22T12:00:00.000Z",
    });

    expect(report.purpose).toBe("clean_machine_first_audition");
    expect(report.session?.time_to_first_audible_ms).toBe(8600);
    expect(report.machine?.disk_free_mb).toBe(12000);
    expect(report.inference.effective).toBe("real");
    expect(JSON.stringify(report)).not.toContain("python_executable");
  });
});
