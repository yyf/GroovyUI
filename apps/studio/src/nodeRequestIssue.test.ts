import { describe, expect, it } from "vitest";
import type { Workflow } from "./types";
import {
  NODE_REQUEST_SCHEMA,
  NODE_REQUEST_TEMPLATE,
  buildNodeRequestIssueUrl,
  prefillFromGenerateUnknownNodes,
  prefillFromUnknownNodeTypes,
} from "./nodeRequestIssue";

const wf: Workflow = {
  schema_version: "1.0",
  groovy_version: "0.21.0",
  id: "d1",
  metadata: { title: "Draft" },
  nodes: [
    { id: "a", type: "LoadAudio", widgets: {} },
    { id: "b", type: "FantasyStemAI", widgets: {} },
  ],
  links: [],
  groups: [],
};

describe("prefillFromUnknownNodeTypes", () => {
  it("builds JSON payload with schema", () => {
    const prefill = prefillFromUnknownNodeTypes(["FantasyStemAI"], {
      userPrompt: "stem granular",
      groovyVersion: "0.21.0",
    });
    expect(prefill.node_types).toBe("FantasyStemAI");
    expect(prefill.node_payload).toContain(NODE_REQUEST_SCHEMA);
    expect(prefill.category).toBe("ai-inference");
  });
});

describe("prefillFromGenerateUnknownNodes", () => {
  it("returns null when no unknown types", () => {
    expect(
      prefillFromGenerateUnknownNodes("p", {
        template_id: "x",
        title: "T",
        workflow: wf,
        unknown_node_types: [],
      }),
    ).toBeNull();
  });

  it("prefills from suggestion unknown list", () => {
    const prefill = prefillFromGenerateUnknownNodes(
      "granular stems",
      {
        template_id: "x",
        title: "Granular chain",
        workflow: wf,
        unknown_node_types: ["FantasyStemAI"],
      },
      "0.21.0",
    );
    expect(prefill?.node_types).toBe("FantasyStemAI");
    expect(prefill?.generate_context).toContain("granular stems");
  });
});

describe("buildNodeRequestIssueUrl", () => {
  it("uses node_request template", () => {
    const url = buildNodeRequestIssueUrl({
      node_types: "FantasyStemAI",
      category: "ai-inference",
      node_payload: `{"schema":"${NODE_REQUEST_SCHEMA}"}`,
      why_needed: "Need it",
    });
    const parsed = new URL(url);
    expect(parsed.searchParams.get("template")).toBe(NODE_REQUEST_TEMPLATE);
    expect(parsed.searchParams.get("node_types")).toBe("FantasyStemAI");
  });
});
