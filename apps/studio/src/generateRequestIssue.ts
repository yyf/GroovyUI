/**
 * Build a GitHub "new issue" URL for LLM Generate blueprint requests.
 * Deep link only — no GitHub API, no tokens, public metadata only.
 */

import type { Workflow } from "./types";
import { resolveModelRequestRepo } from "./modelRequestIssue";

export const DEFAULT_BLUEPRINT_REQUEST_REPO = "yyf/GroovyUI";
export const BLUEPRINT_REQUEST_TEMPLATE = "blueprint_request.yml";
export const GENERATE_BLUEPRINT_REQUEST_SCHEMA = "groovy.generate_blueprint_request.v1";

/** Max encoded payload size for issue URL prefill (GitHub/browser limits). */
export const MAX_BLUEPRINT_PAYLOAD_CHARS = 5500;

/** Allowlisted query keys matching ISSUE_TEMPLATE/blueprint_request.yml field ids. */
const FIELD_IDS = [
  "request_kind",
  "user_prompt",
  "blueprint_title",
  "unavailable_nodes",
  "blueprint_payload",
  "why_needed",
  "groovy_version",
] as const;

export type BlueprintRequestKind = "missing-nodes" | "catalog-template";

export type BlueprintRequestFieldId = (typeof FIELD_IDS)[number];

export type BlueprintRequestPrefill = {
  title?: string;
  request_kind?: BlueprintRequestKind;
  user_prompt?: string;
  blueprint_title?: string;
  unavailable_nodes?: string;
  blueprint_payload?: string;
  why_needed?: string;
  groovy_version?: string;
};

const SECRETISH =
  /\b(hf_[a-zA-Z0-9]+|sk-ant-[a-zA-Z0-9_-]+|ghp_[a-zA-Z0-9]+|github_pat_[a-zA-Z0-9_]+|api[_-]?key|bearer\s+[a-z0-9._-]+)\b/i;

const ABSOLUTE_PATH =
  /(?:^|[\s"'`])(\/(?:Users|home|var|tmp|private)[^\s"'`]*|[A-Za-z]:\\[^\s"'`]*|~\/[^\s"'`]*)/;

function scrub(value: string, maxLen: number): string {
  let trimmed = value.trim().slice(0, maxLen);
  if (SECRETISH.test(trimmed)) {
    return "[redacted — do not paste secrets]";
  }
  trimmed = trimmed.replace(ABSOLUTE_PATH, "[path-redacted]");
  return trimmed;
}

function scrubWidgetValue(value: unknown): unknown {
  if (typeof value === "string") {
    return scrub(value, 800);
  }
  if (Array.isArray(value)) {
    return value.map((item) => scrubWidgetValue(item));
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      out[key] = scrubWidgetValue(nested);
    }
    return out;
  }
  return value;
}

/** Strip absolute paths and secrets before embedding workflow in a public issue. */
export function sanitizeWorkflowForBlueprintRequest(workflow: Workflow): Workflow {
  const nodes = workflow.nodes.map((node) => ({
    ...node,
    widgets: scrubWidgetValue(node.widgets) as Record<string, unknown>,
  }));
  const { view: _view, ...rest } = workflow;
  return { ...rest, nodes };
}

export type GenerateBlueprintRequestPayload = {
  schema: typeof GENERATE_BLUEPRINT_REQUEST_SCHEMA;
  created_from: "studio-generate";
  user_prompt: string;
  blueprint: {
    title: string;
    description?: string;
    template_id?: string;
    rationale?: string;
    unknown_node_types: string[];
    node_types: string[];
    link_count: number;
  };
  workflow?: Workflow;
  workflow_omitted?: boolean;
  workflow_omit_reason?: string;
};

export type GenerateBlueprintSuggestionLike = {
  template_id: string;
  title: string;
  description?: string;
  rationale?: string;
  workflow: Workflow;
  unknown_node_types?: string[];
};

function inferRequestKind(unknownNodeTypes: string[]): BlueprintRequestKind {
  return unknownNodeTypes.length > 0 ? "missing-nodes" : "catalog-template";
}

function buildPayloadJson(
  input: GenerateBlueprintRequestPayload,
  maxChars: number,
): { json: string; omittedWorkflow: boolean } {
  const withWorkflow = JSON.stringify(input, null, 2);
  if (withWorkflow.length <= maxChars) {
    return { json: withWorkflow, omittedWorkflow: false };
  }
  const { workflow: _drop, ...withoutWorkflow } = input;
  const slim: GenerateBlueprintRequestPayload = {
    ...withoutWorkflow,
    workflow_omitted: true,
    workflow_omit_reason:
      "Full graph omitted for GitHub URL size — attach Save JSON from Generate blueprint if needed.",
  };
  const slimJson = JSON.stringify(slim, null, 2);
  if (slimJson.length <= maxChars) {
    return { json: slimJson, omittedWorkflow: true };
  }
  return {
    json: JSON.stringify(
      {
        schema: GENERATE_BLUEPRINT_REQUEST_SCHEMA,
        created_from: "studio-generate",
        user_prompt: scrub(input.user_prompt, 500),
        blueprint: input.blueprint,
        workflow_omitted: true,
        workflow_omit_reason: "Payload truncated for URL size — attach Save JSON from Generate.",
      },
      null,
      2,
    ).slice(0, maxChars),
    omittedWorkflow: true,
  };
}

export function buildGenerateBlueprintRequestPayload(
  userPrompt: string,
  suggestion: GenerateBlueprintSuggestionLike,
): GenerateBlueprintRequestPayload {
  const unknown = [...new Set((suggestion.unknown_node_types ?? []).filter(Boolean))];
  const nodeTypes = suggestion.workflow.nodes.map((node) => node.type);
  const sanitized = sanitizeWorkflowForBlueprintRequest(suggestion.workflow);
  return {
    schema: GENERATE_BLUEPRINT_REQUEST_SCHEMA,
    created_from: "studio-generate",
    user_prompt: scrub(userPrompt.trim(), 2000),
    blueprint: {
      title: suggestion.title,
      description: suggestion.description,
      template_id: suggestion.template_id,
      rationale: suggestion.rationale,
      unknown_node_types: unknown,
      node_types: nodeTypes,
      link_count: suggestion.workflow.links.length,
    },
    workflow: sanitized,
  };
}

export function prefillFromGenerateBlueprint(
  userPrompt: string,
  suggestion: GenerateBlueprintSuggestionLike,
  groovyVersion?: string,
): BlueprintRequestPrefill {
  const unknown = [...new Set((suggestion.unknown_node_types ?? []).filter(Boolean))];
  const kind = inferRequestKind(unknown);
  const payloadBase = buildGenerateBlueprintRequestPayload(userPrompt, suggestion);
  const { json } = buildPayloadJson(payloadBase, MAX_BLUEPRINT_PAYLOAD_CHARS);

  const why =
    kind === "missing-nodes"
      ? `Generate draft uses node type(s) not in this build: ${unknown.join(", ")}. Please consider nodes and/or a verified template.`
      : `All nodes in this LLM draft exist in Studio — request adding it as a verified bundled template.`;

  return {
    title: suggestion.title,
    request_kind: kind,
    user_prompt: userPrompt.trim(),
    blueprint_title: suggestion.title,
    unavailable_nodes: unknown.length ? unknown.join(", ") : undefined,
    blueprint_payload: json,
    why_needed: why,
    groovy_version: groovyVersion,
  };
}

/**
 * Build https://github.com/{owner}/{repo}/issues/new?template=blueprint_request.yml&…
 */
export function buildGenerateBlueprintIssueUrl(
  prefill: BlueprintRequestPrefill = {},
  options?: { repo?: string; template?: string },
): string {
  const repo = resolveModelRequestRepo(options?.repo ?? DEFAULT_BLUEPRINT_REQUEST_REPO);
  const template = options?.template ?? BLUEPRINT_REQUEST_TEMPLATE;
  const params = new URLSearchParams();
  params.set("template", template);

  const titleBase = prefill.title?.trim() || prefill.blueprint_title?.trim();
  if (titleBase) {
    const short = scrub(titleBase.replace(/^\[blueprint-request\]\s*/i, ""), 120);
    params.set("title", `[blueprint-request] ${short}`);
  }

  const values: Partial<Record<BlueprintRequestFieldId, string>> = {
    request_kind: prefill.request_kind,
    user_prompt: prefill.user_prompt,
    blueprint_title: prefill.blueprint_title,
    unavailable_nodes: prefill.unavailable_nodes,
    blueprint_payload: prefill.blueprint_payload,
    why_needed: prefill.why_needed,
    groovy_version: prefill.groovy_version,
  };

  for (const id of FIELD_IDS) {
    const raw = values[id];
    if (raw == null || !String(raw).trim()) continue;
    const max =
      id === "blueprint_payload"
        ? MAX_BLUEPRINT_PAYLOAD_CHARS
        : id === "user_prompt" || id === "why_needed"
          ? 2000
          : 200;
    params.set(id, scrub(String(raw), max));
  }

  return `https://github.com/${repo}/issues/new?${params.toString()}`;
}

export function openGenerateBlueprintIssue(prefill: BlueprintRequestPrefill): void {
  const repo = import.meta.env.VITE_GROOVY_GITHUB_REPO;
  const url = buildGenerateBlueprintIssueUrl(prefill, { repo });
  window.open(url, "_blank", "noopener,noreferrer");
}
