import { describe, expect, it } from "vitest";
import { applyCreativeAgentAction } from "./creativeAgentApply";
import type { Workflow } from "./types";

const baseWorkflow: Workflow = {
  schema_version: "1.0.0",
  groovy_version: "0.1.0",
  id: "w1",
  metadata: { title: "t", description: "" },
  nodes: [
    { id: "note", type: "Note", pos: { x: 0, y: 0 }, widgets: { text: "hint" } },
    { id: "n1", type: "LoadAudio", pos: { x: 0, y: 140 }, widgets: {} },
  ],
  links: [],
  groups: [],
  view: { zoom: 1, pan: { x: 0, y: 0 } },
};

describe("applyCreativeAgentAction", () => {
  it("honors exact add_node pos (no findOpenNodePosition center shift)", () => {
    const exact = { x: 260, y: 140 };
    const result = applyCreativeAgentAction(
      baseWorkflow,
      {
        type: "add_node",
        node: { id: "n2", type: "Denoise", widgets: {}, pos: exact },
      },
      {},
      { x: 900, y: 900 },
    );
    const added = result.workflow.nodes.find((n) => n.id === "n2");
    expect(added?.pos).toEqual(exact);
  });
});
