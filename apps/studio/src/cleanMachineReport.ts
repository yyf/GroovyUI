import type { ActivationDiagnosticsSummary } from "./types";

type CapabilitiesSnapshot = {
  inference_mode: "real" | "stub";
  inference_effective: "real" | "stub";
  inference_stub_active: boolean;
  machine: {
    disk_free_mb: number;
    models_used_mb?: number | null;
    ram_available_gb: number | null;
    vram_available_gb: number | null;
    vram_source: string;
    torch_cuda_available: boolean;
    uv_available: boolean;
  };
};

/** Privacy-safe export for clean-machine / user-run comparison. */
export function buildCleanMachineReport(input: {
  diagnostics: ActivationDiagnosticsSummary | null;
  capabilities: CapabilitiesSnapshot | null;
  capturedAt?: string;
}): {
  schema_version: "1.0";
  captured_at: string;
  purpose: "clean_machine_first_audition";
  session: ActivationDiagnosticsSummary["latest_session"];
  session_count: number;
  diagnostics_path: string | null;
  machine: CapabilitiesSnapshot["machine"] | null;
  inference: {
    mode: "real" | "stub" | null;
    effective: "real" | "stub" | null;
    stub_active: boolean | null;
  };
} {
  const caps = input.capabilities;
  return {
    schema_version: "1.0",
    captured_at: input.capturedAt ?? new Date().toISOString(),
    purpose: "clean_machine_first_audition",
    session: input.diagnostics?.latest_session ?? null,
    session_count: input.diagnostics?.session_count ?? 0,
    diagnostics_path: input.diagnostics?.path ?? null,
    machine: caps
      ? {
          disk_free_mb: caps.machine.disk_free_mb,
          models_used_mb: caps.machine.models_used_mb ?? null,
          ram_available_gb: caps.machine.ram_available_gb,
          vram_available_gb: caps.machine.vram_available_gb,
          vram_source: caps.machine.vram_source,
          torch_cuda_available: caps.machine.torch_cuda_available,
          uv_available: caps.machine.uv_available,
        }
      : null,
    inference: {
      mode: caps?.inference_mode ?? null,
      effective: caps?.inference_effective ?? null,
      stub_active: caps?.inference_stub_active ?? null,
    },
  };
}
