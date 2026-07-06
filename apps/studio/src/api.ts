import type { JobState, ModelCard, NodeSchema, Workflow } from "./types";

export const API = import.meta.env.VITE_GROOVY_API ?? "http://127.0.0.1:8188";

export function wsUrl(): string {
  const url = new URL(API);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return `${url.origin}/api/ws`;
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

export async function fetchCacheMeta(cacheId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API}/api/cache/${cacheId}/meta`);
  if (!res.ok) {
    throw new Error(`Cache not found: ${cacheId}`);
  }
  return res.json();
}

export async function searchModels(query: string, filters?: { task_type?: string }): Promise<ModelCard[]> {
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

export async function installModel(modelId: string): Promise<void> {
  const res = await fetch(`${API}/api/models/${modelId}/install`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Install failed: ${modelId}`);
  }
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
