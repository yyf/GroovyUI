import { describe, expect, it } from "vitest";
import type { Workflow } from "./types";
import {
  BLUEPRINT_REQUEST_TEMPLATE,
  GENERATE_BLUEPRINT_REQUEST_SCHEMA,
  buildGenerateBlueprintIssueUrl,
  buildGenerateBlueprintRequestPayload,
  prefillFromGenerateBlueprint,
  sanitizeWorkflowForBlueprintRequest,
} from "./generateRequestIssue";

const sampleWorkflow: Workflow = {
  schema_version: "1.0",
  groovy_version: "0.21.0",
  id: "draft-1",
  metadata: { title: "Test draft" },
  nodes: [
    {
      id: "n1",
      type: "LoadAudio",
      widgets: { path: "/Users/secret/audio.wav" },
    },
    { id: "n2", type: "FantasyNode", widgets: {} },
  ],
  links: [{ id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" }],
  groups: [],
};

describe("sanitizeWorkflowForBlueprintRequest", () => {
  it("redacts absolute paths in widgets", () => {
    const sanitized = sanitizeWorkflowForBlueprintRequest(sampleWorkflow);
    expect(sanitized.nodes[0].widgets.path).not.toContain("/Users/");
    expect(String(sanitized.nodes[0].widgets.path)).toContain("redacted");
  });
});

describe("buildGenerateBlueprintRequestPayload", () => {
  it("uses structured schema and lists unknown types", () => {
    const payload = buildGenerateBlueprintRequestPayload("drone patch", {
      template_id: "llm-1",
      title: "Drone",
      workflow: sampleWorkflow,
      unknown_node_types: ["FantasyNode"],
    });
    expect(payload.schema).toBe(GENERATE_BLUEPRINT_REQUEST_SCHEMA);
    expect(payload.blueprint.unknown_node_types).toEqual(["FantasyNode"]);
    expect(payload.blueprint.node_types).toEqual(["LoadAudio", "FantasyNode"]);
  });
});

describe("prefillFromGenerateBlueprint", () => {
  it("sets missing-nodes kind when unknown types present", () => {
    const prefill = prefillFromGenerateBlueprint("my prompt", {
      template_id: "llm-1",
      title: "Drone",
      workflow: sampleWorkflow,
      unknown_node_types: ["FantasyNode"],
    });
    expect(prefill.request_kind).toBe("missing-nodes");
    expect(prefill.unavailable_nodes).toBe("FantasyNode");
    expect(prefill.blueprint_payload).toContain(GENERATE_BLUEPRINT_REQUEST_SCHEMA);
  });

  it("sets catalog-template when all nodes known", () => {
    const wf: Workflow = {
      ...sampleWorkflow,
      nodes: [{ id: "n1", type: "Preview", widgets: {} }],
      links: [],
    };
    const prefill = prefillFromGenerateBlueprint("template me", {
      template_id: "llm-2",
      title: "Preview only",
      workflow: wf,
      unknown_node_types: [],
    });
    expect(prefill.request_kind).toBe("catalog-template");
    expect(prefill.unavailable_nodes).toBeUndefined();
  });
});

describe("buildGenerateBlueprintIssueUrl", () => {
  it("uses blueprint template and allowlisted fields", () => {
    const url = buildGenerateBlueprintIssueUrl({
      request_kind: "missing-nodes",
      user_prompt: "granular drone",
      blueprint_title: "Drone draft",
      unavailable_nodes: "FantasyNode",
      blueprint_payload: '{"schema":"groovy.generate_blueprint_request.v1"}',
      why_needed: "Need this node",
      groovy_version: "0.21.0",
    });
    const parsed = new URL(url);
    expect(parsed.pathname).toBe("/yyf/GroovyUI/issues/new");
    expect(parsed.searchParams.get("template")).toBe(BLUEPRINT_REQUEST_TEMPLATE);
    expect(parsed.searchParams.get("request_kind")).toBe("missing-nodes");
    expect(parsed.searchParams.get("title")).toContain("Drone draft");
    expect(parsed.searchParams.has("hf_token")).toBe(false);
  });

  it("redacts secret-like strings from prefill", () => {
    const url = buildGenerateBlueprintIssueUrl({
      user_prompt: "debug hf_NotARealTokenValue1234567890",
      blueprint_title: "X",
      blueprint_payload: "{}",
      why_needed: "test",
    });
    expect(url).toContain("redacted");
    expect(url.toLowerCase()).not.toContain("hf_notarealtokenvalue");
  });
});
