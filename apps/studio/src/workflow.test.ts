import { describe, expect, it } from "vitest";
import type { JobOutput, Workflow } from "./types";
import {
  connectNodes,
  duplicateSelection,
  inferNodeSocketCounts,
  isWireableInput,
  extractSelection,
  findOpenNodePosition,
  formatJobError,
  mergeFlowEdges,
  mergeFlowNodes,
  previewCacheId,
  previewMidiId,
  previewListenId,
  pasteSelection,
  removeNodesFromWorkflow,
  nodeIssuesFromValidation,
  resolveNodeListenId,
  resolveComparePair,
  nodeHasListenableOutput,
  cachedStatusFromOutputs,
  jobOutputAtSlot,
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

  it("dedupes duplicate ids from the next snapshot", () => {
    const next = [
      { id: "n1", type: "groovy", position: { x: 0, y: 0 }, data: { label: "First" } },
      { id: "n1", type: "groovy", position: { x: 10, y: 0 }, data: { label: "Second" } },
    ];
    const merged = mergeFlowNodes([], next);
    expect(merged).toHaveLength(1);
    expect(merged[0]?.data).toEqual({ label: "First" });
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

  it("treats model refs as widget-only", () => {
    expect(isWireableInput({ type: "MODEL_REF" })).toBe(false);
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

describe("nodeIssuesFromValidation", () => {
  it("maps link errors onto endpoint nodes", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      links: [
        { id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" },
        { id: "l2", from: ["n2", 0], to: ["n3", 0], type: "AUDIO" },
        { id: "bad", from: ["n1", 0], to: ["n3", 0], type: "AUDIO" },
      ],
    };
    const issues = nodeIssuesFromValidation(workflow, {
      valid: false,
      errors: [
        {
          code: "MULTIPLE_INPUTS",
          message: "Input slot n3[0] already connected",
          link_id: "bad",
        },
      ],
      warnings: [],
    });
    expect(issues.n1).toContain("already connected");
    expect(issues.n3).toContain("already connected");
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

describe("formatJobError", () => {
  it("extracts FILE_NOT_FOUND with context", () => {
    const err = "FileNotFoundError: FILE_NOT_FOUND: foo.wav\nResolved to: /tmp/workspace/foo.wav";
    expect(formatJobError(err)).toContain("FILE_NOT_FOUND: foo.wav");
  });

  it("extracts ImportError instead of trailing runtime.", () => {
    const err = `ImportError: 
MusicgenMelodyProcessor requires the torchaudio library but it was not found in your environment. Please install it and restart your
runtime.`;
    expect(formatJobError(err)).toContain("torchaudio");
    expect(formatJobError(err)).not.toBe("runtime.");
  });
});

describe("resolveNodeListenId", () => {
  const workflow = sampleWorkflow();

  it("auditions Preview via upstream SeparateStems slot", () => {
    const outputs: Record<string, JobOutput> = {
      n2: {
        type: "MULTI",
        outputs: [
          { type: "AUDIO", cache_id: "vocals", name: "vocals" },
          { type: "AUDIO", cache_id: "drums", name: "drums" },
        ],
      },
    };
    expect(resolveNodeListenId(workflow, "n3", outputs)).toBe("vocals");
  });

  it("prefers wired upstream slot over stale Preview cache entry", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", widgets: { path: "a.wav" } },
        { id: "n2", type: "SeparateStems", widgets: { model: "demucs-v4" } },
        { id: "p2", type: "Preview", widgets: {} },
      ],
      links: [
        { id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" },
        { id: "l2", from: ["n2", 1], to: ["p2", 0], type: "AUDIO" },
      ],
    };
    const outputs: Record<string, JobOutput> = {
      n2: {
        type: "MULTI",
        outputs: [
          { type: "AUDIO", cache_id: "vocals", name: "vocals" },
          { type: "AUDIO", cache_id: "drums", name: "drums" },
        ],
      },
      p2: { type: "AUDIO", cache_id: "vocals" },
    };
    expect(resolveNodeListenId(workflow, "p2", outputs)).toBe("drums");
  });

  it("auditions SeparateStems via wired preview branch", () => {
    const outputs: Record<string, JobOutput> = {
      n2: {
        type: "MULTI",
        outputs: [
          { type: "AUDIO", cache_id: "vocals", name: "vocals" },
          { type: "AUDIO", cache_id: "drums", name: "drums" },
        ],
      },
      n3: { type: "AUDIO", cache_id: "vocals" },
    };
    expect(resolveNodeListenId(workflow, "n2", outputs)).toBe("vocals");
    expect(nodeHasListenableOutput(workflow, "n2", outputs)).toBe(true);
  });

  it("marks wired Preview cached when only upstream rendered", () => {
    const outputs: Record<string, JobOutput> = {
      n2: {
        type: "MULTI",
        outputs: [{ type: "AUDIO", cache_id: "vocals", name: "vocals" }],
      },
    };
    const cached = cachedStatusFromOutputs(workflow, outputs);
    expect(cached.n3).toBe("cached");
  });
  it("resolves compare pair for preview nodes wired to stem slots", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", widgets: { path: "a.wav" } },
        { id: "n2", type: "SeparateStems", widgets: { model: "demucs-v4" } },
        { id: "p1", type: "Preview", widgets: {} },
        { id: "p2", type: "Preview", widgets: {} },
      ],
      links: [
        { id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" },
        { id: "l2", from: ["n2", 0], to: ["p1", 0], type: "AUDIO" },
        { id: "l3", from: ["n2", 1], to: ["p2", 0], type: "AUDIO" },
      ],
    };
    const outputs: Record<string, JobOutput> = {
      n2: {
        type: "MULTI",
        outputs: [
          { type: "AUDIO", cache_id: "vocals", name: "vocals" },
          { type: "AUDIO", cache_id: "drums", name: "drums" },
        ],
      },
    };
    const resolution = resolveComparePair(workflow, outputs, ["p1", "p2"]);
    expect(resolution?.missingRender).toBe(false);
    expect(resolution?.pair[0]?.output.cache_id).toBe("vocals");
    expect(resolution?.pair[1]?.output.cache_id).toBe("drums");
  });

  it("resolves STEMS bundle slots for listen", () => {
    const stems = {
      type: "STEMS" as const,
      stems_id: "bundle",
      stems: { vocals: "v", drums: "d", bass: "b", other: "o" },
    };
    expect(jobOutputAtSlot(stems, 0)?.cache_id).toBe("v");
    expect(jobOutputAtSlot(stems, 1)?.cache_id).toBe("d");
    expect(resolveNodeListenId(sampleWorkflow(), "n3", { n2: stems })).toBe("v");
  });
});

describe("preview ids", () => {
  it("resolves audio cache id", () => {
    expect(previewCacheId({ type: "AUDIO", cache_id: "abc" })).toBe("abc");
    expect(previewCacheId({ type: "MIDI", midi_id: "mid" })).toBeNull();
  });

  it("resolves midi id for MIDI outputs", () => {
    expect(previewMidiId({ type: "MIDI", midi_id: "mid-1" })).toBe("mid-1");
    expect(previewMidiId({ type: "AUDIO", cache_id: "abc" })).toBeNull();
  });

  it("prefers audio cache for listen when both exist", () => {
    expect(previewListenId({ type: "AUDIO", cache_id: "a", midi_id: "m" })).toBe("a");
    expect(previewListenId({ type: "MIDI", midi_id: "m" })).toBe("m");
  });

  it("resolves multi-output slot for listen", () => {
    const multi = {
      type: "MULTI" as const,
      outputs: [
        { type: "AUDIO" as const, cache_id: "vocals", name: "vocals" },
        { type: "AUDIO" as const, cache_id: "drums", name: "drums" },
      ],
    };
    expect(previewListenId(multi, 0)).toBe("vocals");
    expect(previewListenId(multi, 1)).toBe("drums");
  });
});
