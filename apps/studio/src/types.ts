export type WorkflowNode = {
  id: string;
  type: string;
  pos?: { x: number; y: number };
  widgets: Record<string, unknown>;
};

export type WorkflowLink = {
  id: string;
  from: [string, number];
  to: [string, number];
  type: string;
};

export type Workflow = {
  schema_version: string;
  groovy_version: string;
  id: string;
  metadata: { title: string; description?: string };
  nodes: WorkflowNode[];
  links: WorkflowLink[];
  groups: unknown[];
  view?: { zoom: number; pan: { x: number; y: number } };
};

export type NodeWidgetSpec = {
  name: string;
  type: string;
  default?: unknown;
  optional?: boolean;
};

export type ModelCard = {
  id: string;
  name: string;
  description: string;
  task_types: string[];
  tags: string[];
  license: { spdx: string; commercial_ok: boolean; attribution_required: boolean };
  vram_gb_estimate: number;
  compatible_nodes: string[];
  install_status: string;
  install_progress?: number;
  install_error?: string | null;
};

export type NodeSchema = {
  type: string;
  category: string;
  inputs: Array<{ name: string; type: string; optional?: boolean }>;
  outputs: Array<{ name: string; type: string }>;
  widgets: NodeWidgetSpec[];
};

export type JobOutput = {
  cache_id?: string;
  type: string;
  text?: string;
  stems_id?: string;
  stems?: Record<string, string>;
};

export type ComplianceSummary = {
  workflow_id: string;
  workflow_title: string;
  license_rows: Array<{
    component: string;
    kind: string;
    license_spdx: string;
    commercial_ok: boolean;
    attribution_required?: boolean;
  }>;
  warnings: string[];
  commercial_ok: boolean;
};

export type ProvenanceEntry = {
  node_id: string;
  cache_id: string;
  chain: Array<{
    contribution?: { class?: string; disclosure_label?: string };
    node?: { node_id?: string; node_type?: string };
    models?: Array<{ registry_id?: string }>;
  }>;
  disclosure: string;
};

export type ProvenanceSummary = {
  entries: ProvenanceEntry[];
  focus_node_id: string | null;
  focus_disclosure: string;
  contains_ai: boolean;
};

export type ModelRecommendation = {
  model: ModelCard;
  rationale: string;
  score: number;
};

export type InstallRecovery = {
  model_id: string;
  error: string | null;
  summary: string;
  similar_models: ModelCard[];
  suggested_fixes: string[];
};

export type JobState = {
  status: "running" | "completed" | "failed";
  progress?: number;
  current_node?: string;
  outputs?: Record<string, JobOutput>;
  error?: string | null;
  manifest_path?: string;
};

export type NodeRenderStatus = "idle" | "running" | "cached" | "stale";
