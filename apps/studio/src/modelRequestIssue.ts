/**
 * Build a GitHub "new issue" URL for model requests.
 * Deep link only — no GitHub API, no tokens, public metadata only.
 */

export const DEFAULT_MODEL_REQUEST_REPO = "yyf/GroovyUI";
export const MODEL_REQUEST_TEMPLATE = "model_request.yml";

/** Allowlisted query keys that match ISSUE_TEMPLATE/model_request.yml field ids. */
const FIELD_IDS = [
  "hf_id",
  "source_url",
  "task_type",
  "suggested_nodes",
  "license",
  "why_needed",
  "groovy_version",
] as const;

export type ModelRequestFieldId = (typeof FIELD_IDS)[number];

export type ModelRequestPrefill = {
  title?: string;
  hf_id?: string;
  source_url?: string;
  task_type?: string;
  suggested_nodes?: string;
  license?: string;
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

export function resolveModelRequestRepo(envRepo?: string | null): string {
  const raw = (envRepo ?? "").trim() || DEFAULT_MODEL_REQUEST_REPO;
  // owner/name only — no paths, URLs, or ".."
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]*\/[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(raw)) {
    return DEFAULT_MODEL_REQUEST_REPO;
  }
  if (raw.includes("..")) {
    return DEFAULT_MODEL_REQUEST_REPO;
  }
  return raw;
}

/**
 * Build https://github.com/{owner}/{repo}/issues/new?template=model_request.yml&…
 * Only allowlisted public fields are included.
 */
export function buildModelRequestIssueUrl(
  prefill: ModelRequestPrefill = {},
  options?: { repo?: string; template?: string },
): string {
  const repo = resolveModelRequestRepo(options?.repo);
  const template = options?.template ?? MODEL_REQUEST_TEMPLATE;
  const params = new URLSearchParams();
  params.set("template", template);

  const titleBase = prefill.title?.trim() || prefill.hf_id?.trim();
  if (titleBase) {
    const short = scrub(titleBase.replace(/^\[model-request\]\s*/i, ""), 120);
    params.set("title", `[model-request] ${short}`);
  }

  const values: Partial<Record<ModelRequestFieldId, string>> = {
    hf_id: prefill.hf_id,
    source_url: prefill.source_url,
    task_type: prefill.task_type,
    suggested_nodes: prefill.suggested_nodes,
    license: prefill.license,
    why_needed: prefill.why_needed,
    groovy_version: prefill.groovy_version,
  };

  for (const id of FIELD_IDS) {
    const raw = values[id];
    if (raw == null || !String(raw).trim()) continue;
    const max = id === "why_needed" ? 2000 : id === "source_url" ? 500 : 200;
    params.set(id, scrub(String(raw), max));
  }

  return `https://github.com/${repo}/issues/new?${params.toString()}`;
}

export type DiscoverLike = {
  external_id: string;
  name?: string;
  source_url: string;
  task_types?: string[];
  suggested_compatible_nodes?: string[];
  license?: { spdx?: string };
};

/** Map a Discover card to safe issue prefill (no tokens / paths). */
export function prefillFromDiscover(entry: DiscoverLike, groovyVersion?: string): ModelRequestPrefill {
  const nodes = entry.suggested_compatible_nodes?.filter(Boolean).join(", ");
  const task = entry.task_types?.[0];
  return {
    hf_id: entry.external_id,
    source_url: entry.source_url,
    task_type: task,
    suggested_nodes: nodes || undefined,
    license: entry.license?.spdx || undefined,
    why_needed: `Request verifying ${entry.name || entry.external_id} for Install in GroovyUI (from Discover).`,
    groovy_version: groovyVersion,
  };
}

export function prefillFromUnknownModelId(
  modelId: string,
  groovyVersion?: string,
): ModelRequestPrefill {
  const id = modelId.trim();
  const looksLikeHf = id.includes("/");
  return {
    hf_id: id,
    source_url: looksLikeHf ? `https://huggingface.co/${id}` : undefined,
    why_needed: `Model id "${id}" is referenced but not in the published catalog / not installable.`,
    groovy_version: groovyVersion,
  };
}
