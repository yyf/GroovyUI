import { describe, expect, it } from "vitest";
import {
  DEFAULT_MODEL_REQUEST_REPO,
  buildModelRequestIssueUrl,
  prefillFromDiscover,
  prefillFromUnknownModelId,
  resolveModelRequestRepo,
} from "./modelRequestIssue";

describe("resolveModelRequestRepo", () => {
  it("defaults to yyf/GroovyUI", () => {
    expect(resolveModelRequestRepo(undefined)).toBe(DEFAULT_MODEL_REQUEST_REPO);
    expect(resolveModelRequestRepo("")).toBe(DEFAULT_MODEL_REQUEST_REPO);
  });

  it("rejects malformed repos", () => {
    expect(resolveModelRequestRepo("../evil")).toBe(DEFAULT_MODEL_REQUEST_REPO);
    expect(resolveModelRequestRepo("https://github.com/yyf/GroovyUI")).toBe(
      DEFAULT_MODEL_REQUEST_REPO,
    );
  });

  it("accepts owner/name", () => {
    expect(resolveModelRequestRepo("acme/GroovyUI-fork")).toBe("acme/GroovyUI-fork");
  });
});

describe("buildModelRequestIssueUrl", () => {
  it("uses template and allowlisted fields only", () => {
    const url = buildModelRequestIssueUrl({
      hf_id: "facebook/demucs",
      source_url: "https://huggingface.co/facebook/demucs",
      task_type: "stem-separation",
      suggested_nodes: "SeparateStems",
      license: "MIT",
      why_needed: "Want stems in a patch",
      groovy_version: "0.20.0",
    });
    const parsed = new URL(url);
    expect(parsed.origin + parsed.pathname).toBe(
      "https://github.com/yyf/GroovyUI/issues/new",
    );
    expect(parsed.searchParams.get("template")).toBe("model_request.yml");
    expect(parsed.searchParams.get("hf_id")).toBe("facebook/demucs");
    expect(parsed.searchParams.get("task_type")).toBe("stem-separation");
    expect(parsed.searchParams.get("title")).toContain("facebook/demucs");
    expect(parsed.searchParams.has("hf_token")).toBe(false);
  });

  it("redacts secret-like strings from prefill", () => {
    const url = buildModelRequestIssueUrl({
      hf_id: "org/model",
      why_needed: "here is hf_NotARealTokenValue1234567890 for debug",
    });
    expect(url).toContain("redacted");
    expect(url.toLowerCase()).not.toContain("hf_notarealtokenvalue");
  });
});

describe("prefill helpers", () => {
  it("maps discover cards without secrets", () => {
    const prefill = prefillFromDiscover({
      external_id: "org/cool-model",
      name: "Cool",
      source_url: "https://huggingface.co/org/cool-model",
      task_types: ["denoise"],
      suggested_compatible_nodes: ["Denoise"],
      license: { spdx: "Apache-2.0" },
    });
    expect(prefill.hf_id).toBe("org/cool-model");
    expect(prefill.suggested_nodes).toBe("Denoise");
    expect(prefill).not.toHaveProperty("hf_token");
    expect(JSON.stringify(prefill)).not.toMatch(/sk-ant-|ghp_|github_pat_/i);
  });

  it("maps unknown catalog ids", () => {
    const prefill = prefillFromUnknownModelId("some-org/weights");
    expect(prefill.source_url).toBe("https://huggingface.co/some-org/weights");
  });
});
