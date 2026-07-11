import type {
  BatchRenderResult,
  ComplianceSummary,
  JobOutput,
  JobState,
  LicenseScanSummary,
  ModelCard,
  ModelInstallState,
  NodeSchema,
  ProvenanceSummary,
  Workflow,
  WorkflowValidationResult,
} from "./types";
import { applyNodeSchemaFallbacks } from "./nodeSchemaFallbacks";

export const API = import.meta.env.VITE_GROOVY_API ?? "http://127.0.0.1:8188";

export type LiveIoSettings = {
  midi_input_enabled: boolean;
  midi_output_enabled: boolean;
  osc_live_enabled: boolean;
  default_input_id: string | null;
  default_output_id: string | null;
  audio_input_enabled: boolean;
  audio_output_enabled: boolean;
  default_audio_input_id: string | null;
  default_audio_output_id: string | null;
};

export type AudioDevice = {
  id: string;
  name: string;
  manufacturer: string;
  direction: string;
  channels: number;
  sample_rate: number;
};

const VIRTUAL_AUDIO_INPUT: AudioDevice = {
  id: "virtual:audio:in-demo",
  name: "Virtual Audio In (demo)",
  manufacturer: "GroovyUI",
  direction: "in",
  channels: 2,
  sample_rate: 48000,
};

const VIRTUAL_AUDIO_OUTPUT: AudioDevice = {
  id: "virtual:audio:out-demo",
  name: "Virtual Audio Out (preview route)",
  manufacturer: "GroovyUI",
  direction: "out",
  channels: 2,
  sample_rate: 48000,
};

export function normalizeLiveIoSettings(raw: Partial<LiveIoSettings>): LiveIoSettings {
  return {
    midi_input_enabled: raw.midi_input_enabled ?? false,
    midi_output_enabled: raw.midi_output_enabled ?? false,
    osc_live_enabled: raw.osc_live_enabled ?? false,
    default_input_id: raw.default_input_id ?? "virtual:in-demo",
    default_output_id: raw.default_output_id ?? "virtual:out-demo",
    audio_input_enabled: raw.audio_input_enabled ?? false,
    audio_output_enabled: raw.audio_output_enabled ?? false,
    default_audio_input_id: raw.default_audio_input_id ?? VIRTUAL_AUDIO_INPUT.id,
    default_audio_output_id: raw.default_audio_output_id ?? VIRTUAL_AUDIO_OUTPUT.id,
  };
}

export type MidiDevice = {
  id: string;
  name: string;
  manufacturer: string;
  direction: string;
};

export async function fetchLiveIoSettings(): Promise<LiveIoSettings> {
  const res = await fetch(`${API}/api/settings/live-io`);
  if (!res.ok) throw new Error("Failed to load live I/O settings");
  return normalizeLiveIoSettings(await res.json());
}

export async function updateLiveIoSettings(patch: Partial<LiveIoSettings>): Promise<LiveIoSettings> {
  const res = await fetch(`${API}/api/settings/live-io`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error("Failed to update live I/O settings");
  return normalizeLiveIoSettings(await res.json());
}

export async function fetchMidiDevices(direction?: "in" | "out"): Promise<MidiDevice[]> {
  const query = direction ? `?direction=${direction}` : "";
  const res = await fetch(`${API}/api/midi/devices${query}`);
  if (!res.ok) throw new Error("Failed to list MIDI devices");
  const data = await res.json();
  return data.devices;
}

export async function fetchAudioDevices(direction?: "in" | "out"): Promise<AudioDevice[]> {
  const query = direction ? `?direction=${direction}` : "";
  try {
    const res = await fetch(`${API}/api/audio/devices${query}`);
    if (res.status === 404) {
      if (direction === "in") return [VIRTUAL_AUDIO_INPUT];
      if (direction === "out") return [VIRTUAL_AUDIO_OUTPUT];
      return [VIRTUAL_AUDIO_INPUT, VIRTUAL_AUDIO_OUTPUT];
    }
    if (!res.ok) throw new Error("Failed to list audio devices");
    const data = await res.json();
    return data.devices;
  } catch {
    if (direction === "in") return [VIRTUAL_AUDIO_INPUT];
    if (direction === "out") return [VIRTUAL_AUDIO_OUTPUT];
    return [VIRTUAL_AUDIO_INPUT, VIRTUAL_AUDIO_OUTPUT];
  }
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

export async function fetchStudioSettings(): Promise<import("./types").StudioSettings> {
  const res = await fetch(`${API}/api/settings/studio`);
  if (!res.ok) throw new Error("Failed to load studio settings");
  return res.json();
}

export async function updateStudioSettings(patch: { hf_token?: string | null }): Promise<import("./types").StudioSettings> {
  const res = await fetch(`${API}/api/settings/studio`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error("Failed to save studio settings");
  return res.json();
}

export async function importComfyWorkflow(
  comfyJson: Record<string, unknown>,
  title?: string,
): Promise<{
  workflow: Workflow;
  import_meta: Record<string, unknown>;
  validation: { valid: boolean };
  missing_models: import("./types").MissingWorkflowModel[];
}> {
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
  return applyNodeSchemaFallbacks(await res.json());
}

export async function fetchAllNodeSchemas(): Promise<Record<string, NodeSchema>> {
  const res = await fetch(`${API}/api/nodes`);
  if (!res.ok) {
    throw new Error("Failed to load node schemas");
  }
  const data = await res.json();
  const map: Record<string, NodeSchema> = {};
  for (const schema of data.nodes as NodeSchema[]) {
    const merged = applyNodeSchemaFallbacks(schema);
    map[merged.type] = merged;
  }
  return map;
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

export type SpectrogramData = {
  width: number;
  height: number;
  values: number[];
  duration: number;
  min_db: number;
  max_db: number;
  sample_rate: number;
  max_freq_hz: number;
};

export async function fetchSpectrogram(
  cacheId: string,
  width = 512,
  height = 48,
): Promise<SpectrogramData> {
  const res = await fetch(`${API}/api/cache/${cacheId}/spectrogram?width=${width}&height=${height}`);
  if (!res.ok) {
    throw new Error(`Spectrogram not found: ${cacheId}`);
  }
  return res.json();
}

export type MidiRollData = {
  midi_id: string;
  duration: number;
  notes: {
    start: number;
    end: number;
    pitch: number;
    velocity: number;
    drum?: boolean;
  }[];
  min_pitch: number;
  max_pitch: number;
};

export async function fetchMidiRoll(midiId: string): Promise<MidiRollData> {
  const res = await fetch(`${API}/api/cache/${midiId}/midi-roll`);
  if (!res.ok) {
    throw new Error(`MIDI roll not found: ${midiId}`);
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

export type CacheSignalMetrics = {
  cache_id: string;
  label: string;
  duration_sec: number;
  sample_rate: number;
  channels: number;
  channel_layout: string;
  peak: number;
  rms: number;
  lufs: number | null;
  source_node_type: string | null;
};

export async function fetchCacheMetrics(cacheId: string): Promise<CacheSignalMetrics> {
  const res = await fetch(`${API}/api/cache/${cacheId}/metrics`);
  if (!res.ok) {
    throw new Error(`Metrics not found: ${cacheId}`);
  }
  return res.json();
}

export async function fetchJobManifest(jobId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API}/api/jobs/${jobId}/manifest`);
  if (!res.ok) {
    throw new Error(`Manifest not found for job ${jobId}`);
  }
  return res.json();
}

export function formatApiDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") {
    return detail.message;
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => String(item)).join("; ");
  }
  return fallback;
}

export async function fetchAudioFileMeta(
  path: string,
): Promise<{ meta: Record<string, unknown> | null; error: string | null }> {
  const query = new URLSearchParams({ path });
  const res = await fetch(`${API}/api/project/audio-meta?${query}`);
  if (!res.ok) {
    let detail = `File not found: ${path}`;
    try {
      const body = await res.json();
      detail = formatApiDetail(body.detail, detail);
    } catch {
      // ignore
    }
    return { meta: null, error: detail };
  }
  const meta = await res.json();
  return { meta, error: null };
}

export async function searchModels(
  query: string,
  filters?: { task_type?: string; commercial_ok?: boolean; node_type?: string },
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
    await installModelWithProgress(modelId);
    installed.push(modelId);
  }
  return installed;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchModelInstallStatus(modelId: string): Promise<ModelInstallState> {
  const res = await fetch(`${API}/api/models/${modelId}/install/status`);
  if (!res.ok) {
    throw new Error(`Install status failed: ${modelId}`);
  }
  return res.json();
}

export async function installModelWithProgress(
  modelId: string,
  onProgress?: (state: ModelInstallState) => void,
): Promise<ModelInstallState> {
  const res = await fetch(`${API}/api/models/${modelId}/install`, { method: "POST" });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Install failed to start: ${modelId}`);
  }
  let state = (await res.json()) as ModelInstallState;
  onProgress?.(state);
  if (state.status === "ready") {
    return state;
  }

  const deadline = Date.now() + 30 * 60 * 1000;
  while (Date.now() < deadline) {
    await sleep(400);
    state = await fetchModelInstallStatus(modelId);
    onProgress?.(state);
    if (state.status === "ready") {
      return state;
    }
    if (state.status === "failed") {
      throw new Error(state.error ?? `Install failed: ${modelId}`);
    }
  }
  throw new Error(`Install timed out: ${modelId}`);
}

/** @deprecated Prefer installModelWithProgress */
export async function installModel(modelId: string): Promise<void> {
  await installModelWithProgress(modelId);
}

export async function findMissingWorkflowModels(
  workflow: Workflow,
): Promise<Array<{ modelId: string; status: string; name: string; reason: string }>> {
  const modelIds = [
    ...new Set(
      workflow.nodes
        .map((node) => node.widgets.model)
        .filter((model): model is string => typeof model === "string" && model.trim().length > 0),
    ),
  ];
  const missing: Array<{ modelId: string; status: string; name: string; reason: string }> = [];
  for (const modelId of modelIds) {
    try {
      const card = await fetchModelCard(modelId);
      if (card.install_status !== "ready") {
        missing.push({
          modelId,
          status: card.install_status,
          name: card.name,
          reason: "not_installed",
        });
      } else if (!card.dev_stub && card.inference_ready === false) {
        missing.push({
          modelId,
          status: card.install_status,
          name: card.name,
          reason: "inference_not_ready",
        });
      }
    } catch {
      missing.push({ modelId, status: "unknown", name: modelId, reason: "unknown" });
    }
  }
  return missing;
}

export async function fetchWorkflowValidation(workflow: Workflow): Promise<WorkflowValidationResult> {
  const res = await fetch(`${API}/api/workflow/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow }),
  });
  if (!res.ok) {
    throw new Error("Workflow validation failed");
  }
  return res.json();
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

export async function downloadComplianceReport(
  workflow: Workflow,
  options?: {
    outputs?: Record<string, JobOutput>;
    targetNodeId?: string | null;
  },
): Promise<Blob> {
  const res = await fetch(`${API}/api/workflow/compliance-report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow,
      outputs: options?.outputs ?? {},
      target_node_id: options?.targetNodeId ?? null,
    }),
  });
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error(
        "Compliance PDF export is not available on this API — restart groovy-server (uv run --package groovy-server groovy-server) and try again.",
      );
    }
    let detail = "Compliance report export failed";
    try {
      const body = await res.json();
      detail = formatApiDetail(body.detail, detail);
    } catch {
      detail = (await res.text()) || detail;
    }
    throw new Error(detail);
  }
  return res.blob();
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
  if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") {
    return detail.message;
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

export type TemplateListItem = {
  id: string;
  title: string;
  description: string;
  source: "bundled" | "user";
};

export async function listTemplates(): Promise<TemplateListItem[]> {
  const res = await fetch(`${API}/api/templates`);
  if (!res.ok) {
    throw new Error("Failed to list templates");
  }
  const data = await res.json();
  return (data.templates as TemplateListItem[]).map((template) => ({
    ...template,
    source: template.source === "user" ? "user" : "bundled",
  }));
}

export async function saveUserTemplate(
  workflow: Workflow,
  title?: string,
  description?: string,
): Promise<{ template: Workflow; template_id: string; source: "user" }> {
  const res = await fetch(`${API}/api/templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow, title, description }),
  });
  if (!res.ok) throw new Error("Failed to save template");
  return res.json();
}

export function previewUrl(cacheId: string): string {
  return `${API}/api/cache/${cacheId}/preview?format=wav`;
}

export type JobProgressHandler = (job: JobState) => void;

export type WorkflowExecution = {
  jobId: string;
  promise: Promise<JobState>;
  cancel: () => Promise<void>;
};

export async function cancelJob(jobId: string): Promise<void> {
  const res = await fetch(`${API}/api/jobs/${jobId}/cancel`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Cancel failed: ${res.status}`);
  }
}

export async function executeWorkflow(
  workflow: Workflow,
  targetNodes: string[],
  onProgress: JobProgressHandler,
): Promise<WorkflowExecution> {
  const res = await fetch(`${API}/api/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow, target_nodes: targetNodes }),
  });
  if (!res.ok) {
    throw new Error(`Execute failed: ${res.status}`);
  }
  const { job_id } = await res.json();

  const promise = new Promise<JobState>((resolve, reject) => {
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
        if (job.status === "completed" || job.status === "failed" || job.status === "cancelled") {
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
            message: msg.message,
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
        } else if (msg.type === "job.cancelled") {
          const message = msg.error?.message ?? "Cancelled";
          const outputs = msg.outputs as Record<string, JobOutput> | undefined;
          onProgress({ status: "cancelled", error: message, outputs });
          finish({ status: "cancelled", error: message, outputs });
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      // polling remains the fallback
    };
  });

  return {
    jobId: job_id,
    promise,
    cancel: () => cancelJob(job_id),
  };
}

async function pollJob(jobId: string): Promise<JobState> {
  const res = await fetch(`${API}/api/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error(`Job not found: ${jobId}`);
  }
  return res.json();
}
