/**
 * Build a GitHub "new issue" URL for node type requests.
 * Deep link only — no GitHub API, no tokens, public metadata only.
 */

import type { Workflow } from "./types";
import { resolveModelRequestRepo } from "./modelRequestIssue";
import type { GenerateBlueprintSuggestionLike } from "./generateRequestIssue";

export const NODE_REQUEST_TEMPLATE = "node_request.yml";
export const NODE_REQUEST_SCHEMA = "groovy.node_request.v1";

const FIELD_IDS = [
  "node_types",
  "category",
  "similar_nodes",
  "generate_context",
  "node_payload",
  "why_needed",
  "groovy_version",
] as const;

export type NodeRequestCategory =
  | "ai-inference"
  | "audio-dsp"
  | "control-modular"
  | "io-load-save"
  | "trust-compliance"
  | "utility"
  | "other";

export type NodeRequestPrefill = {
  title?: string;
  node_types?: string;
  category?: NodeRequestCategory;
  similar_nodes?: string;
  generate_context?: string;
  node_payload?: string;
  why_needed?: string;
  groovy_version?: string;
};

const SECRETISH =
  /\b(hf_[a-zA-Z0-9]+|sk-ant-[a-zA-Z0-9_-]+|ghp_[a-zA-Z0-9]+|github_pat_[a-zA-Z0-9_]+|api[_-]?key|bearer\s+[a-z0-9._-]+)\b/i;

function scrub(value: string, maxLen: number): string {
  const trimmed = value.trim().slice(0, maxLen);
  if (SECRETISH.test(trimmed)) {
    return "[redacted — do not paste secrets]";
  }
  return trimmed;
}

export type NodeRequestPayload = {
  schema: typeof NODE_REQUEST_SCHEMA;
  created_from: "studio-generate";
  node_types: string[];
  blueprint_title?: string;
  user_prompt?: string;
  known_node_types?: string[];
  link_count?: number;
};

function guessCategory(nodeTypes: string[]): NodeRequestCategory {
  const joined = nodeTypes.join(" ").toLowerCase();
  if (/deepfake|provenance|watermark|authenticity|verify/.test(joined)) return "trust-compliance";
  if (/midi|automation|clock|quant|osc|filter|envelope|lfo|control/.test(joined)) {
    return "control-modular";
  }
  if (/load|save|preview|export|transcode/.test(joined)) return "io-load-save";
  if (/denoise|stem|whisper|tts|music|generate|separate|voice|pitch|transcribe|ai/.test(joined)) {
    return "ai-inference";
  }
  if (/mix|eq|reverb|granular|resample|normalize|trim|dsp|filter/.test(joined)) {
    return "audio-dsp";
  }
  return "other";
}

export function buildNodeRequestPayload(
  unknownTypes: string[],
  context?: { userPrompt?: string; blueprintTitle?: string; workflow?: Workflow },
): NodeRequestPayload {
  const types = [...new Set(unknownTypes.map((t) => t.trim()).filter(Boolean))];
  const known = context?.workflow?.nodes
    .map((n) => n.type)
    .filter((t) => types.every((u) => u !== t));
  return {
    schema: NODE_REQUEST_SCHEMA,
    created_from: "studio-generate",
    node_types: types,
    blueprint_title: context?.blueprintTitle,
    user_prompt: context?.userPrompt ? scrub(context.userPrompt, 2000) : undefined,
    known_node_types: known?.length ? [...new Set(known)] : undefined,
    link_count: context?.workflow?.links.length,
  };
}

export function prefillFromUnknownNodeTypes(
  unknownTypes: string[],
  options?: {
    userPrompt?: string;
    suggestion?: GenerateBlueprintSuggestionLike;
    groovyVersion?: string;
    category?: NodeRequestCategory;
  },
): NodeRequestPrefill {
  const types = [...new Set(unknownTypes.map((t) => t.trim()).filter(Boolean))];
  const workflow = options?.suggestion?.workflow;
  const payload = buildNodeRequestPayload(types, {
    userPrompt: options?.userPrompt,
    blueprintTitle: options?.suggestion?.title,
    workflow,
  });
  const contextParts: string[] = [];
  if (options?.userPrompt?.trim()) {
    contextParts.push(`Prompt: ${scrub(options.userPrompt.trim(), 500)}`);
  }
  if (options?.suggestion?.title) {
    contextParts.push(`Blueprint: ${scrub(options.suggestion.title, 200)}`);
  }

  return {
    title: types[0] ?? "Node",
    node_types: types.join(", "),
    category: options?.category ?? guessCategory(types),
    generate_context: contextParts.length ? contextParts.join("\n") : undefined,
    node_payload: JSON.stringify(payload, null, 2),
    why_needed: `Generate draft references node type(s) not in this Studio build: ${types.join(", ")}.`,
    groovy_version: options?.groovyVersion,
  };
}

export function prefillFromGenerateUnknownNodes(
  userPrompt: string,
  suggestion: GenerateBlueprintSuggestionLike,
  groovyVersion?: string,
): NodeRequestPrefill | null {
  const unknown = [...new Set((suggestion.unknown_node_types ?? []).filter(Boolean))];
  if (!unknown.length) return null;
  return prefillFromUnknownNodeTypes(unknown, { userPrompt, suggestion, groovyVersion });
}

export function buildNodeRequestIssueUrl(
  prefill: NodeRequestPrefill = {},
  options?: { repo?: string; template?: string },
): string {
  const repo = resolveModelRequestRepo(options?.repo);
  const template = options?.template ?? NODE_REQUEST_TEMPLATE;
  const params = new URLSearchParams();
  params.set("template", template);

  const titleBase = prefill.title?.trim() || prefill.node_types?.split(",")[0]?.trim();
  if (titleBase) {
    const short = scrub(titleBase.replace(/^\[node-request\]\s*/i, ""), 120);
    params.set("title", `[node-request] ${short}`);
  }

  const values: Partial<Record<(typeof FIELD_IDS)[number], string>> = {
    node_types: prefill.node_types,
    category: prefill.category,
    similar_nodes: prefill.similar_nodes,
    generate_context: prefill.generate_context,
    node_payload: prefill.node_payload,
    why_needed: prefill.why_needed,
    groovy_version: prefill.groovy_version,
  };

  for (const id of FIELD_IDS) {
    const raw = values[id];
    if (raw == null || !String(raw).trim()) continue;
    const max =
      id === "node_payload" || id === "generate_context" || id === "why_needed" ? 4000 : 200;
    params.set(id, scrub(String(raw), max));
  }

  return `https://github.com/${repo}/issues/new?${params.toString()}`;
}

export function openNodeRequestIssue(prefill: NodeRequestPrefill): void {
  const repo = import.meta.env.VITE_GROOVY_GITHUB_REPO;
  const url = buildNodeRequestIssueUrl(prefill, { repo });
  window.open(url, "_blank", "noopener,noreferrer");
}
