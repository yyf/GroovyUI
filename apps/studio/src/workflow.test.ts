import { describe, expect, it } from "vitest";
import type { Workflow } from "./types";
import {
  connectNodes,
  duplicateSelection,
  inferNodeSocketCounts,
  isWireableInput,
  extractSelection,
  findOpenNodePosition,
  mergeFlowEdges,
  mergeFlowNodes,
  pasteSelection,
  removeNodesFromWorkflow,
  wiredInputsForNode,
  workflowToFlowEdges,
  workflowToFlowNodes,
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

describe("workflowToFlowNodes", () => {
  it("shows only wireable Mix inputs with stable slot ids", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [{ id: "mix", type: "Mix", pos: { x: 0, y: 0 }, widgets: {} }],
      links: [],
    };
    const schemas: Record<string, import("./types").NodeSchema> = {
      Mix: {
        type: "Mix",
        category: "GroovyUI/Core",
        inputs: [
          { name: "a", type: "AUDIO" },
          { name: "b", type: "AUDIO" },
          { name: "gain_a", type: "FLOAT", optional: true },
          { name: "gain_b", type: "FLOAT", optional: true },
        ],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      },
    };
    const nodes = workflowToFlowNodes(workflow, {}, undefined, schemas);
    const mix = nodes.find((node) => node.id === "mix");
    expect(mix?.data.inputs).toEqual([
      { name: "a", type: "AUDIO", optional: undefined, slot: 0 },
      { name: "b", type: "AUDIO", optional: undefined, slot: 1 },
    ]);
  });
});

describe("inferNodeSocketCounts", () => {
  it("derives handle counts from link slot indices", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
        { id: "n2", type: "LoadAudio", pos: { x: 0, y: 120 }, widgets: {} },
        { id: "n3", type: "Mix", pos: { x: 240, y: 0 }, widgets: {} },
      ],
      links: [
        { id: "l1", from: ["n1", 0], to: ["n3", 0], type: "AUDIO" },
        { id: "l2", from: ["n2", 0], to: ["n3", 1], type: "AUDIO" },
      ],
    };
    expect(inferNodeSocketCounts(workflow, "n3")).toEqual({ inputs: 2, outputs: 1 });
    expect(inferNodeSocketCounts(workflow, "n1")).toEqual({ inputs: 0, outputs: 1 });
  });
});

describe("isWireableInput", () => {
  it("hides optional float gain sockets from the canvas", () => {
    expect(isWireableInput({ type: "AUDIO" })).toBe(true);
    expect(isWireableInput({ type: "FLOAT", optional: true })).toBe(false);
    expect(isWireableInput({ type: "MIDI", optional: true })).toBe(true);
  });
});

describe("connectNodes", () => {
  const schemas: Record<string, import("./types").NodeSchema> = {
    Mix: {
      type: "Mix",
      category: "GroovyUI/Core",
      inputs: [
        { name: "a", type: "AUDIO" },
        { name: "b", type: "AUDIO" },
        { name: "gain_a", type: "FLOAT", optional: true },
        { name: "gain_b", type: "FLOAT", optional: true },
      ],
      outputs: [{ name: "output_0", type: "AUDIO" }],
      widgets: [],
    },
    LoadAudio: {
      type: "LoadAudio",
      category: "GroovyUI/Core",
      inputs: [],
      outputs: [{ name: "output_0", type: "AUDIO" }],
      widgets: [],
    },
  };

  it("wires second Mix input to slot 1", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
        { id: "n2", type: "LoadAudio", pos: { x: 0, y: 120 }, widgets: { path: "b.wav" } },
        { id: "n3", type: "Mix", pos: { x: 240, y: 0 }, widgets: {} },
      ],
      links: [],
    };
    const next = connectNodes(
      connectNodes(workflow, { source: "n1", target: "n3", sourceHandle: "0", targetHandle: "0" }, schemas),
      { source: "n2", target: "n3", sourceHandle: "0", targetHandle: "1" },
      schemas,
    );
    expect(next.links).toHaveLength(2);
    expect(next.links.find((link) => link.to[1] === 1)?.from).toEqual(["n2", 0]);
  });
});

describe("findOpenNodePosition", () => {
  it("places at center when canvas is empty at that point", () => {
    const pos = findOpenNodePosition(sampleWorkflow(), { x: 100, y: 100 });
    expect(pos).toEqual({ x: 30, y: 76 });
  });

  it("offsets when center overlaps an existing node", () => {
    const pos = findOpenNodePosition(sampleWorkflow(), { x: 10, y: 10 });
    expect(pos.x !== 10 || pos.y !== 10).toBe(true);
    const workflow = { ...sampleWorkflow(), nodes: [...sampleWorkflow().nodes, { id: "n4", type: "Mix", pos, widgets: {} }] };
    const overlaps = workflow.nodes.some(
      (node, index, all) =>
        index < all.length - 1 &&
        Math.abs((node.pos?.x ?? 0) - pos.x) < 140 &&
        Math.abs((node.pos?.y ?? 0) - pos.y) < 48,
    );
    expect(overlaps).toBe(false);
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
