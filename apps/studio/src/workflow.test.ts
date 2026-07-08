import { describe, expect, it } from "vitest";
import type { Workflow } from "./types";
import {
  duplicateSelection,
  extractSelection,
  mergeFlowEdges,
  mergeFlowNodes,
  pasteSelection,
  removeNodesFromWorkflow,
  wiredInputsForNode,
  workflowToFlowEdges,
} from "./workflow";

function sampleWorkflow(): Workflow {
  return {
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: "wf",
    metadata: { title: "Test" },
    nodes: [
      { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } },
      { id: "n2", type: "Normalize", pos: { x: 200, y: 0 }, widgets: {} },
      { id: "n3", type: "Preview", pos: { x: 400, y: 0 }, widgets: {} },
    ],
    links: [
      { id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" },
      { id: "l2", from: ["n2", 0], to: ["n3", 0], type: "AUDIO" },
    ],
    groups: [],
  };
}

describe("mergeFlowNodes", () => {
  it("preserves measured dimensions when syncing data", () => {
    const next = [{ id: "n1", type: "groovy", position: { x: 0, y: 0 }, data: { label: "Load" } }];
    const current = [
      {
        id: "n1",
        type: "groovy",
        position: { x: 0, y: 0 },
        data: { label: "Old" },
        width: 180,
        height: 72,
        measured: { width: 180, height: 72 },
        selected: true,
      },
    ];
    const merged = mergeFlowNodes(current, next);
    expect(merged[0]?.data).toEqual({ label: "Load" });
    expect(merged[0]?.width).toBe(180);
    expect(merged[0]?.selected).toBe(true);
  });
});

describe("mergeFlowEdges", () => {
  it("keeps current edges when next is temporarily empty", () => {
    const current = [{ id: "l1", source: "n1", target: "n2" }];
    expect(mergeFlowEdges(current, [])).toEqual(current);
  });
});

describe("wiredInputsForNode", () => {
  it("maps links to input sockets by slot index", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        ...sampleWorkflow().nodes,
        { id: "n0", type: "Prompt", pos: { x: 0, y: 120 }, widgets: { text: "hi" } },
      ],
      links: [
        { id: "l0", from: ["n0", 0], to: ["n4", 0], type: "TEXT" },
        ...sampleWorkflow().links,
      ],
    };
    const schema = {
      type: "GenerateAudio",
      category: "GroovyUI/AI",
      inputs: [
        { name: "prompt", type: "TEXT" },
        { name: "midi", type: "MIDI", optional: true },
        { name: "reference_audio", type: "AUDIO", optional: true },
      ],
      outputs: [{ name: "output_0", type: "AUDIO" }],
      widgets: [{ name: "model", type: "MODEL_REF" }],
    };
    const rows = wiredInputsForNode(workflow, "n4", schema.inputs);
    expect(rows[0]?.connected).toBe(true);
    expect(rows[0]?.sourceNode?.type).toBe("Prompt");
    expect(rows[1]?.connected).toBe(false);
  });
});

describe("workflowToFlowEdges", () => {
  it("assigns typed edge classes and labels", () => {
    const edges = workflowToFlowEdges(sampleWorkflow());
    expect(edges[0]?.label).toBe("AUDIO");
    expect(edges[0]?.className).toContain("groovy-edge--type-audio");
  });
});

describe("selection clipboard", () => {
  it("extracts only internal links between selected nodes", () => {
    const workflow = sampleWorkflow();
    const clip = extractSelection(workflow, ["n1", "n2"]);
    expect(clip.nodes.map((node) => node.id)).toEqual(["n1", "n2"]);
    expect(clip.links.map((link) => link.id)).toEqual(["l1"]);
  });

  it("pastes with new ids and offset positions", () => {
    const workflow = sampleWorkflow();
    const clip = extractSelection(workflow, ["n1", "n2"]);
    const { workflow: next, newNodeIds } = pasteSelection(workflow, clip, { x: 10, y: 20 });
    expect(newNodeIds).toHaveLength(2);
    expect(next.nodes).toHaveLength(5);
    expect(next.links).toHaveLength(3);
    const pasted = next.nodes.filter((node) => newNodeIds.includes(node.id));
    expect(pasted[0]?.pos).toEqual({ x: 10, y: 20 });
    expect(pasted[1]?.pos).toEqual({ x: 210, y: 20 });
  });

  it("duplicates a selection in one step", () => {
    const workflow = sampleWorkflow();
    const { workflow: next, newNodeIds } = duplicateSelection(workflow, ["n2", "n3"]);
    expect(newNodeIds).toHaveLength(2);
    expect(next.nodes).toHaveLength(5);
    expect(next.links.some((link) => link.from[0] === newNodeIds[0] && link.to[0] === newNodeIds[1])).toBe(
      true,
    );
  });
});

describe("removeNodesFromWorkflow", () => {
  it("removes nodes, dangling links, and empty groups", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      groups: [{ id: "g1", title: "Pair", node_ids: ["n1", "n2"] }],
    };
    const next = removeNodesFromWorkflow(workflow, new Set(["n2"]));
    expect(next.nodes.map((node) => node.id)).toEqual(["n1", "n3"]);
    expect(next.links).toEqual([]);
    expect(next.groups).toEqual([]);
  });

  it("removes collapsed group members when proxy is deleted", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      groups: [{ id: "g1", title: "Pair", node_ids: ["n1", "n2"], collapsed: true }],
    };
    const next = removeNodesFromWorkflow(workflow, new Set(["proxy_g1"]));
    expect(next.nodes.map((node) => node.id)).toEqual(["n3"]);
    expect(next.links).toEqual([]);
  });
});
