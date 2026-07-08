import type {
  BatchRenderResult,
  ComplianceSummary,
  JobState,
  LicenseScanSummary,
  ModelCard,
  NodeSchema,
  ProvenanceSummary,
  Workflow,
} from "./types";

export const API = import.meta.env.VITE_GROOVY_API ?? "http://127.0.0.1:8188";

export type LiveIoSettings = {
  midi_input_enabled: boolean;
  midi_output_enabled: boolean;
  osc_live_enabled: boolean;
  default_input_id: string | null;
  default_output_id: string | null;
};

export type MidiDevice = {
  id: string;
  name: string;
  manufacturer: string;
  direction: string;
};

export async function fetchLiveIoSettings(): Promise<LiveIoSettings> {
  const res = await fetch(`${API}/api/settings/live-io`);
  if (!res.ok) throw new Error("Failed to load live I/O settings");
  return res.json();
}

export async function updateLiveIoSettings(patch: Partial<LiveIoSettings>): Promise<LiveIoSettings> {
  const res = await fetch(`${API}/api/settings/live-io`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error("Failed to update live I/O settings");
  return res.json();
}

export async function fetchMidiDevices(direction?: "in" | "out"): Promise<MidiDevice[]> {
  const query = direction ? `?direction=${direction}` : "";
  const res = await fetch(`${API}/api/midi/devices${query}`);
  if (!res.ok) throw new Error("Failed to list MIDI devices");
  const data = await res.json();
  return data.devices;
}

export async function postMidiInEvent(
  deviceId: string,
  event: Record<string, unknown>,
): Promise<void> {
  const res = await fetch(`${API}/api/midi/in/event`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId, event }),
  });
  if (!res.ok) throw new Error("MIDI input rejected");
}

export async function generateTemplateFromWorkflow(
  workflow: Workflow,
  title?: string,
): Promise<{ template: Workflow; template_id: string; suggested_readme: string }> {
  const res = await fetch(`${API}/api/workflow/generate-template`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow, title }),
  });
  if (!res.ok) throw new Error("Template generation failed");
  return res.json();
}

export type NodePack = {
  id: string;
  version: string;
  name: string;
  description: string;
  trust_tier: string;
};

export async function listPacks(): Promise<NodePack[]> {
  const res = await fetch(`${API}/api/packs`);
  if (!res.ok) throw new Error("Failed to list packs");
  const data = await res.json();
  return data.packs;
}

export async function installPack(packId: string): Promise<void> {
  const res = await fetch(`${API}/api/packs/${packId}/install`, { method: "POST" });
  if (!res.ok) throw new Error(`Pack install failed: ${packId}`);
}

export async function fetchRegistryFreshness(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API}/api/registry/freshness`);
  if (!res.ok) throw new Error("Registry freshness scan failed");
  return res.json();
}

export function wsUrl(): string {
  const url = new URL(API);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return `${url.origin}/api/ws`;
}

export async function importComfyWorkflow(
  comfyJson: Record<string, unknown>,
  title?: string,
): Promise<{ workflow: Workflow; import_meta: Record<string, unknown>; validation: { valid: boolean } }> {
  const res = await fetch(`${API}/api/workflow/import/comfy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow: comfyJson, title }),
  });
  if (!res.ok) {
    throw new Error(`ComfyUI import failed (${res.status})`);
  }
  return res.json();
}

export async function uploadProjectAudio(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/api/project/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    throw new Error(`Upload failed (${res.status})`);
  }
  const data = await res.json();
  return data.path as string;
}

export async function fetchHealth(): Promise<string> {
  const res = await fetch(`${API}/api/health`);
  const data = await res.json();
  return data.groovy_version ?? "unknown";
}

export async function fetchTemplate(templateId: string): Promise<Workflow> {
  const res = await fetch(`${API}/api/templates/${templateId}`);
  if (!res.ok) {
    throw new Error(`Template not found: ${templateId}`);
  }
  return res.json();
}

export async function fetchNodeSchema(nodeType: string): Promise<NodeSchema> {
  const res = await fetch(`${API}/api/nodes/${nodeType}`);
  if (!res.ok) {
    throw new Error(`Unknown node type: ${nodeType}`);
  }
  return res.json();
}

export async function fetchModelCard(modelId: string): Promise<ModelCard> {
  const res = await fetch(`${API}/api/models/${modelId}`);
  if (!res.ok) {
    throw new Error(`Model not found: ${modelId}`);
  }
  return res.json();
}

export async function fetchWaveform(cacheId: string, width = 128): Promise<{ peaks: number[]; duration: number }> {
  const res = await fetch(`${API}/api/cache/${cacheId}/waveform?width=${width}`);
  if (!res.ok) {
    throw new Error(`Waveform not found: ${cacheId}`);
  }
  return res.json();
}

export async function fetchCacheMeta(cacheId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API}/api/cache/${cacheId}/meta`);
  if (!res.ok) {
    throw new Error(`Cache not found: ${cacheId}`);
  }
  return res.json();
}

export async function fetchAudioFileMeta(path: string): Promise<Record<string, unknown> | null> {
  const query = new URLSearchParams({ path });
  const res = await fetch(`${API}/api/project/audio-meta?${query}`);
  if (!res.ok) {
    return null;
  }
  return res.json();
}

export async function searchModels(
  query: string,
  filters?: { task_type?: string; commercial_ok?: boolean },
): Promise<ModelCard[]> {
  const res = await fetch(`${API}/api/models/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, ...filters }),
  });
  if (!res.ok) {
    throw new Error(`Model search failed (${res.status})`);
  }
  const data = await res.json();
  return data.models;
}

export async function recommendModels(
  prompt: string,
  filters?: { commercial_ok?: boolean },
): Promise<{ results: Array<{ model: ModelCard; rationale: string }>; inferred_task?: string }> {
  const res = await fetch(`${API}/api/models/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, ...filters }),
  });
  if (!res.ok) {
    throw new Error(`Model recommend failed (${res.status})`);
  }
  return res.json();
}

export async function fetchInstallRecovery(modelId: string): Promise<import("./types").InstallRecovery> {
  const res = await fetch(`${API}/api/models/${modelId}/recovery`);
  if (!res.ok) {
    throw new Error("Recovery lookup failed");
  }
  return res.json();
}

export async function ensureWorkflowModels(workflow: Workflow): Promise<string[]> {
  const modelIds = new Set<string>();
  for (const node of workflow.nodes) {
    const model = node.widgets.model;
    if (typeof model === "string" && model) {
      modelIds.add(model);
    }
  }
  const installed: string[] = [];
  for (const modelId of modelIds) {
    await installModel(modelId);
    installed.push(modelId);
  }
  return installed;
}

export async function installModel(modelId: string): Promise<void> {
  const res = await fetch(`${API}/api/models/${modelId}/install`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Install failed: ${modelId}`);
  }
}

export async function fetchCompliance(workflow: Workflow): Promise<ComplianceSummary> {
  const res = await fetch(`${API}/api/workflow/compliance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow }),
  });
  if (!res.ok) {
    throw new Error("Compliance summary failed");
  }
  return res.json();
}

export async function fetchLicenseScan(workflow: Workflow): Promise<LicenseScanSummary> {
  const res = await fetch(`${API}/api/workflow/license-scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow }),
  });
  if (!res.ok) {
    throw new Error("License scan failed");
  }
  return res.json();
}

export async function batchRenderWorkflow(
  workflow: Workflow,
  options: {
    input_dir: string;
    file_glob?: string;
    load_node_id?: string;
    target_nodes?: string[];
  },
): Promise<BatchRenderResult> {
  const res = await fetch(`${API}/api/batch/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow, ...options }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Batch render failed: ${detail}`);
  }
  return res.json();
}

export async function fetchAuthenticity(reportId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API}/api/authenticity/${reportId}`);
  if (!res.ok) {
    throw new Error("Authenticity report not found");
  }
  return res.json();
}

export type AbCompareResult = {
  mode: "signal" | "transcript";
  model_id: string;
  transcription_model?: string;
  verdict: "no_difference" | "subtle" | "moderate" | "substantial";
  verdict_summary: string;
  difference_count: number;
  differences: string[];
  narrative: string;
  facts: string[];
  transcript_a?: string;
  transcript_b?: string;
  clip_a: Record<string, unknown>;
  clip_b: Record<string, unknown>;
  comparison: Record<string, unknown>;
};

export async function fetchCompareModels(): Promise<ModelCard[]> {
  return searchModels("", { task_type: "audio-compare" });
}

function formatApiError(detail: unknown, fallback: string): string {
  if (typeof detail === "string") {
    if (detail === "Not Found") {
      return "API route not found — restart groovy-server (uv run groovy-server) and try again.";
    }
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => String(item)).join("; ");
  }
  return fallback;
}

export async function analyzeAbCompare(params: {
  cache_id_a: string;
  cache_id_b: string;
  model_id: string;
  label_a: string;
  label_b: string;
  question?: string;
}): Promise<AbCompareResult> {
  const res = await fetch(`${API}/api/compare/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    let detail = "A/B analysis failed";
    try {
      const data = await res.json();
      detail = formatApiError(data.detail, detail);
    } catch {
      const text = await res.text();
      detail = text.includes("Not Found")
        ? "API route not found — restart groovy-server (uv run groovy-server) and try again."
        : text || detail;
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchProvenance(
  workflow: Workflow,
  outputs: Record<string, import("./types").JobOutput>,
  targetNodeId?: string | null,
): Promise<ProvenanceSummary> {
  const res = await fetch(`${API}/api/workflow/provenance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow,
      outputs,
      target_node_id: targetNodeId ?? undefined,
    }),
  });
  if (!res.ok) {
    throw new Error("Provenance summary failed");
  }
  return res.json();
}

export async function suggestWorkflows(
  prompt: string,
): Promise<{
  prompt: string;
  mode: string;
  results: Array<{
    template_id: string;
    title: string;
    description: string;
    rationale: string;
    score: number;
    workflow: Workflow;
  }>;
}> {
  const res = await fetch(`${API}/api/workflow/suggest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) {
    throw new Error("Workflow suggest failed");
  }
  return res.json();
}

export async function listTemplates(): Promise<Array<{ id: string; title: string; description: string }>> {
  const res = await fetch(`${API}/api/templates`);
  if (!res.ok) {
    throw new Error("Failed to list templates");
  }
  const data = await res.json();
  return data.templates;
}

export function previewUrl(cacheId: string): string {
  return `${API}/api/cache/${cacheId}/preview?format=wav`;
}

export type JobProgressHandler = (job: JobState) => void;

export async function executeWorkflow(
  workflow: Workflow,
  targetNodes: string[],
  onProgress: JobProgressHandler,
): Promise<JobState> {
  const res = await fetch(`${API}/api/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow, target_nodes: targetNodes }),
  });
  if (!res.ok) {
    throw new Error(`Execute failed: ${res.status}`);
  }
  const { job_id } = await res.json();

  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (job: JobState) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(job);
    };
    const fail = (err: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(err);
    };

    const ws = new WebSocket(wsUrl());
    const poll = window.setInterval(async () => {
      try {
        const job = await pollJob(job_id);
        onProgress(job);
        if (job.status === "completed" || job.status === "failed") {
          finish(job);
        }
      } catch (err) {
        fail(err instanceof Error ? err : new Error(String(err)));
      }
    }, 400);

    const cleanup = () => {
      window.clearInterval(poll);
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "subscribe", job_id }));
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "job.progress") {
          onProgress({
            status: "running",
            progress: msg.progress,
            current_node: msg.node_id,
          });
        } else if (msg.type === "job.complete") {
          onProgress({
            status: "completed",
            progress: 1,
            outputs: msg.outputs,
          });
          finish({
            status: "completed",
            progress: 1,
            outputs: msg.outputs,
          });
        } else if (msg.type === "job.failed") {
          const message = msg.error?.message ?? "Execution failed";
          onProgress({ status: "failed", error: message });
          finish({ status: "failed", error: message });
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      // polling remains the fallback
    };
  });
}

async function pollJob(jobId: string): Promise<JobState> {
  const res = await fetch(`${API}/api/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error(`Job not found: ${jobId}`);
  }
  return res.json();
}
