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

export type WorkflowGroup = {
  id: string;
  title: string;
  node_ids: string[];
  color?: string;
  collapsed?: boolean;
  proxy_pos?: { x: number; y: number };
};

export type ModulePort = {
  id: string;
  name: string;
  type: string;
  node_id: string;
  slot: number;
  direction: "in" | "out";
};

export type WorkflowModule = {
  schema_version: string;
  metadata: { title: string; description?: string };
  nodes: WorkflowNode[];
  links: WorkflowLink[];
  inlets?: ModulePort[];
  outlets?: ModulePort[];
};

export type Workflow = {
  schema_version: string;
  groovy_version: string;
  id: string;
  metadata: { title: string; description?: string };
  nodes: WorkflowNode[];
  links: WorkflowLink[];
  groups: WorkflowGroup[];
  view?: { zoom: number; pan: { x: number; y: number } };
};

export type NodeWidgetSpec = {
  name: string;
  type: string;
  default?: unknown;
  optional?: boolean;
  description?: string;
  min?: number;
  max?: number;
  step?: number;
};

export type InferenceParamSpec = {
  name: string;
  type: string;
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
  description?: string;
};

export type ModelBrowserLaunch = {
  mode?: "search" | "recommend" | "workflow" | "discover";
  query?: string;
  taskType?: string;
  commercialOnly?: boolean;
  filterNodeType?: string | null;
  /** When opened from render/template gate — highlight and batch-install workflow models. */
  requiredModelIds?: string[];
};

export type DiscoverModelResult = {
  external_id: string;
  name: string;
  author: string;
  description: string;
  task_types: string[];
  tags: string[];
  license: { spdx: string; commercial_ok: boolean | null; confidence: number };
  updated_at?: string;
  downloads?: number;
  likes?: number;
  source_url: string;
  suggested_compatible_nodes: string[];
  trust: "external";
};

export type StudioSettings = {
  hf_token_set: boolean;
  hf_token_source: "environment" | "settings" | null;
};

export type MissingWorkflowModel = {
  model_id: string;
  name: string;
  status: string;
  reason: string;
  dev_stub?: boolean;
  node_ids?: string[];
  compatible_nodes?: string[];
};

export type ModelCard = {
  id: string;
  name: string;
  description: string;
  task_types: string[];
  tags: string[];
  author?: string;
  license: { spdx: string; commercial_ok: boolean; attribution_required: boolean };
  vram_gb_estimate: number;
  compatible_nodes: string[];
  install_status: string;
  install_progress?: number;
  install_error?: string | null;
  dev_stub?: boolean;
  inference_ready?: boolean;
  install_complete?: boolean;
  inference_params?: InferenceParamSpec[];
  status?: string;
  trust?: string;
  source_url?: string;
};

export type ModelInstallState = {
  model_id: string;
  status: string;
  version?: string | null;
  error?: string | null;
  progress?: number;
  installed_at?: string | null;
};

export type NodeSchema = {
  type: string;
  category: string;
  description?: string;
  enriched?: boolean;
  inputs: Array<{ name: string; type: string; optional?: boolean; description?: string }>;
  outputs: Array<{ name: string; type: string; description?: string }>;
  widgets: NodeWidgetSpec[];
};

export type JobOutput = {
  cache_id?: string;
  type: string;
  name?: string;
  text?: string;
  path?: string;
  provenance_path?: string;
  stems_id?: string;
  stems?: Record<string, string>;
  midi_id?: string;
  authenticity_id?: string;
  automation_id?: string;
  outputs?: JobOutput[];
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

export type LicenseSwapSuggestion = {
  node_id: string;
  node_type: string;
  widget: string;
  current_model_id: string;
  current_license: string;
  rationale: string;
  alternatives: Array<{
    model_id: string;
    name: string;
    license_spdx: string;
    task_types: string[];
    rationale: string;
  }>;
};

export type LicenseScanSummary = ComplianceSummary & {
  flags: Array<{
    node_id: string;
    node_type: string;
    severity: string;
    code: string;
    message: string;
    model_id?: string;
  }>;
  swap_suggestions: LicenseSwapSuggestion[];
  scan_ok: boolean;
  agent: string;
};

export type BatchRenderResult = {
  input_dir: string;
  file_glob: string;
  load_node_id: string;
  total: number;
  completed: number;
  failed: number;
  runs: Array<{
    input_path: string;
    status: string;
    job_id: string;
    error?: string | null;
  }>;
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
  status: "running" | "completed" | "failed" | "cancelled";
  progress?: number;
  current_node?: string;
  message?: string;
  outputs?: Record<string, JobOutput>;
  error?: string | null;
  manifest_path?: string;
};

export type NodeRenderStatus = "idle" | "running" | "cached" | "stale";

export type WorkflowValidationIssue = {
  code: string;
  message: string;
  node_id?: string | null;
  link_id?: string | null;
};

export type WorkflowValidationResult = {
  valid: boolean;
  errors: WorkflowValidationIssue[];
  warnings: WorkflowValidationIssue[];
};
