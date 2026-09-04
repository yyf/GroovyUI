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
  /** Optional stroke from EDGE_COLOR_PALETTE; omit = socket-type default. */
  color?: string;
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
  inference_mode: "real" | "stub";
  inference_effective: "real" | "stub";
  inference_effective_source: "environment" | "settings";
  inference_stub_active: boolean;
  content_credentials_mode: "off" | "sign_if_configured" | "required";
  content_credentials_effective: "off" | "sign_if_configured" | "required";
  content_credentials_effective_source: "environment" | "settings";
  project_dir: string;
  cache_dir: string;
  nodes_schema_url: string;
  c2pa_status_url: string;
};

export type C2paStatus = {
  mode: "off" | "sign_if_configured" | "required";
  effective_mode: "off" | "sign_if_configured" | "required";
  effective_source: "environment" | "settings";
  provider: string;
  configured: boolean;
  sdk_available: boolean;
  supported_formats: string[];
};

export type ActivationDiagnosticEvent =
  | "task_started"
  | "workflow_applied"
  | "compliance_confirmed"
  | "install_started"
  | "install_completed"
  | "render_started"
  | "render_completed"
  | "playback_requested"
  | "playback_started"
  | "playback_failed"
  | "cancelled"
  | "failed";

export type ActivationDiagnosticMilestone = {
  event: ActivationDiagnosticEvent;
  elapsed_ms: number;
  context: Record<string, string | number | boolean>;
};

export type ActivationDiagnosticsSummary = {
  path: string;
  stored_locally: true;
  session_count: number;
  event_count: number;
  latest_session: {
    session_id: string;
    started_at: string;
    outcome: "audible" | "failed" | "cancelled" | "playback_blocked" | "in_progress";
    elapsed_ms: number;
    time_to_first_audible_ms: number | null;
    context: Record<string, string | number | boolean>;
    milestones: ActivationDiagnosticMilestone[];
  } | null;
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

export type ModelInternalConnection = {
  from: string;
  to: string;
  label?: string;
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
  download_size_mb_estimate?: number | null;
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
  /** Curated / HF-card architecture notes for Inspector Subgraph (optional). */
  architecture_notes?: string | null;
  /** Published internal edges; shown as-is when present. */
  internal_connections?: ModelInternalConnection[];
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
  provenance_class?: string;
  /** Offline frame-indexed audio bus (metadata; not an executor gate). */
  sample_accurate?: boolean;
  /** False for AI / stochastic hops — PCM may vary by seed/hardware. */
  deterministic?: boolean;
  /** False when model chooses output length (TTS / MusicGen / etc.). Metadata only. */
  duration_locked?: boolean;
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
  sample_check_id?: string;
  automation_id?: string;
  outputs?: JobOutput[];
};

export type ComplianceSummary = {
  workflow_id: string;
  workflow_title: string;
  license_rows: Array<{
    component: string;
    component_id?: string;
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
  explain?: string;
  browse_hint?: {
    node_type: string;
    commercial_only: boolean;
    query: string;
    mode?: string;
  };
  alternatives: Array<{
    model_id: string;
    name: string;
    license_spdx: string;
    attribution_required?: boolean;
    license_confidence?: number;
    vram_gb_estimate?: number;
    download_size_mb_estimate?: number | null;
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
    explain?: string;
    model_id?: string;
  }>;
  swap_suggestions: LicenseSwapSuggestion[];
  optimization_plan?: {
    intent: "commercial";
    swaps: Array<{
      node_id: string;
      node_type: string;
      from_model_id: string;
      to_model_id: string;
      to_model_name: string;
      license_spdx: string;
      rationale: string;
    }>;
    unresolved: Array<{
      node_id: string;
      node_type: string;
      model_id?: string;
      message: string;
      explain?: string;
      next_step?: string;
    }>;
    can_optimize: boolean;
  };
  preflight?: {
    download: {
      known_mb: number;
      unknown_models: string[];
      already_installed: string[];
    };
    peak_vram_gb: number;
    render_time: {
      basis_audio_seconds: number;
      low_seconds: number;
      high_seconds: number;
      confidence: "rough";
      note: string;
    };
    models: Array<{
      model_id: string;
      installed: boolean;
      download_size_mb_estimate?: number | null;
      vram_gb_estimate: number;
    }>;
    nodes: Array<{
      node_id: string;
      node_type: string;
      seconds_per_audio_minute: { low: number; high: number };
    }>;
    machine?: {
      disk_free_mb: number;
      disk_path: string;
      models_dir?: string;
      models_used_mb?: number;
      ram_available_gb: number | null;
      vram_available_gb: number | null;
      vram_source: string;
      torch_cuda_available: boolean;
      python_executable: string;
      uv_available: boolean;
    };
    checks?: Array<{
      code: string;
      severity: "ok" | "warning" | "error";
      message: string;
    }>;
  };
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
  explain?: string;
  similar_models: Array<ModelCard & { similar_rationale?: string }>;
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
