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

export type NodeSchema = {
  type: string;
  category: string;
  inputs: Array<{ name: string; type: string; optional?: boolean }>;
  outputs: Array<{ name: string; type: string }>;
  widgets: NodeWidgetSpec[];
};

export type JobOutput = {
  cache_id: string;
  type: string;
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
