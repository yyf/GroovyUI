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
  layoutWorkflowNodes,
  workflowHasOverlappingNodes,
  ensureNoOverlappingNodes,
  estimateNodeSize,
  mergeFlowEdges,
  mergeFlowNodes,
  previewCacheId,
  previewMidiId,
  previewListenId,
  previewTextSnippet,
  promptWidgetSnippet,
  savedFilePath,
  savedProvenancePath,
  resolveNodeInspectorOutput,
  pasteSelection,
  removeNodesFromWorkflow,
  nodeIssuesFromValidation,
  preferredAuditionNodeId,
  resolveNodeListenId,
  resolveComparePair,
  resolveRenderAllTargets,
  nodeHasListenableOutput,
  cachedStatusFromOutputs,
  jobOutputAtSlot,
  authenticityReportId,
  withAuthenticityRenderTargets,
  wiredInputsForNode,
  wiredInputSupersedesWidget,
  wiredOutputsForNode,
  wiredPromptPreview,
  disconnectPort,
  workflowToFlowEdges,
  workflowToFlowNodes,
  channelConvertSocketLabels,
  edgeIdsOnPathToNode,
  normalizeLoadedWorkflow,
  setLinkColor,
} from "./workflow";

function sampleWorkflow(): Workflow {
  return {
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: "wf",
    metadata: { title: "Test" },
    nodes: [
      { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } },
      { id: "n2", type: "Normalize", pos: { x: 280, y: 0 }, widgets: {} },
      { id: "n3", type: "Preview", pos: { x: 560, y: 0 }, widgets: {} },
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

  it("clears the canvas when next is an empty workflow snapshot", () => {
    const current = [{ id: "n1", type: "groovy", position: { x: 0, y: 0 }, data: { label: "Stale" } }];
    expect(mergeFlowNodes(current, [])).toEqual([]);
  });
});

describe("mergeFlowEdges", () => {
  it("clears edges when next is an empty workflow snapshot", () => {
    const current = [{ id: "l1", source: "n1", target: "n2" }];
    expect(mergeFlowEdges(current, [])).toEqual([]);
  });

  it("updates animated and className from the next snapshot", () => {
    const current = [
      {
        id: "l1",
        source: "n1",
        target: "n2",
        animated: true,
        className: "groovy-edge--type-audio groovy-edge--active",
      },
    ];
    const next = [
      {
        id: "l1",
        source: "n1",
        target: "n2",
        animated: false,
        className: "groovy-edge--type-audio",
      },
    ];
    const merged = mergeFlowEdges(current, next);
    expect(merged[0]?.animated).toBe(false);
    expect(merged[0]?.className).toBe("groovy-edge--type-audio");
  });
});

describe("previewTextSnippet", () => {
  it("returns null for empty text", () => {
    expect(previewTextSnippet({ type: "AUDIO", cache_id: "x" })).toBeNull();
    expect(previewTextSnippet({ type: "TEXT", text: "   " })).toBeNull();
  });

  it("truncates long transcripts for on-node display", () => {
    const long = "word ".repeat(50).trim();
    const snippet = previewTextSnippet({ type: "TEXT", text: long }, 40);
    expect(snippet).not.toBeNull();
    expect(snippet!.endsWith("…")).toBe(true);
    expect(snippet!.length).toBeLessThanOrEqual(40);
  });

  it("reads transcript attached to AUDIO Preview outputs", () => {
    expect(
      previewTextSnippet({ type: "AUDIO", cache_id: "abc", text: "Heard on canvas" }),
    ).toBe("Heard on canvas");
  });

  it("pulls Meter TEXT from MULTI and strips §METER§ payload", () => {
    const snippet = previewTextSnippet(
      {
        type: "MULTI",
        outputs: [
          { type: "AUDIO", cache_id: "m1" },
          {
            type: "TEXT",
            text: "L −6.0 · R −12.0 dBFS peak\nL head −6.0 · tail −∞\n§METER§{\"channels\":[]}",
          },
        ],
      },
      280,
    );
    expect(snippet).toContain("L −6.0");
    expect(snippet).toContain("head");
    expect(snippet).not.toContain("§METER§");
  });

  it("keeps Preview transcript when merging listen + direct outputs", () => {
    const merged = resolveNodeInspectorOutput(
      { type: "AUDIO", cache_id: "preview", text: "from whisper" },
      { type: "AUDIO", cache_id: "load" },
    );
    expect(merged).toMatchObject({ type: "AUDIO", cache_id: "preview", text: "from whisper" });
  });

  it("keeps SaveAudio STRING payload over upstream listen AUDIO", () => {
    const merged = resolveNodeInspectorOutput(
      {
        type: "STRING",
        path: "exports/renders/take-20260717.wav",
        provenance_path: "exports/renders/take-20260717.provenance.json",
      },
      { type: "AUDIO", cache_id: "upstream" },
    );
    expect(merged).toMatchObject({
      type: "STRING",
      path: "exports/renders/take-20260717.wav",
      provenance_path: "exports/renders/take-20260717.provenance.json",
    });
  });

  it("keeps MULTI SampleCheck+Audio for inspector Outputs tab", () => {
    const multi: JobOutput = {
      type: "MULTI",
      outputs: [
        { type: "SAMPLE_CHECK", sample_check_id: "rep" },
        { type: "AUDIO", cache_id: "pcm" },
      ],
    };
    const merged = resolveNodeInspectorOutput(multi, { type: "AUDIO", cache_id: "pcm" });
    expect(merged).toEqual(multi);
  });

  it("attaches previewText on TEXT job outputs in flow nodes", () => {
    const workflow = sampleWorkflow();
    const schemas = {
      Preview: {
        type: "Preview",
        category: "Core",
        inputs: [
          { name: "audio", type: "AUDIO", optional: true },
          { name: "text", type: "TEXT", optional: true },
        ],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      },
    };
    const nodes = workflowToFlowNodes(
      workflow,
      {},
      { n3: { type: "TEXT", text: "Heard on canvas" } },
      schemas,
    );
    const preview = nodes.find((node) => node.id === "n3");
    expect(preview?.data).toMatchObject({ previewText: "Heard on canvas" });
    expect((preview?.data as { outputs?: { type: string }[] }).outputs?.[0]?.type).toBe("TEXT");
  });

  it("shows Prompt widget text on the canvas even when last render differs", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n0", type: "Prompt", pos: { x: 0, y: 120 }, widgets: { text: "new inspector prompt" } },
      ],
      links: [],
    };
    const nodes = workflowToFlowNodes(
      workflow,
      {},
      { n0: { type: "TEXT", text: "stale rendered prompt" } },
    );
    const prompt = nodes.find((node) => node.id === "n0");
    expect(prompt?.data).toMatchObject({ previewText: "new inspector prompt" });
    expect(promptWidgetSnippet(workflow.nodes[0]!)).toBe("new inspector prompt");
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
        { name: "text", type: "TEXT", optional: true },
        { name: "midi", type: "MIDI", optional: true },
        { name: "reference_audio", type: "AUDIO", optional: true },
      ],
      outputs: [{ name: "output_0", type: "AUDIO" }],
      widgets: [
        { name: "model", type: "MODEL_REF" },
        { name: "prompt", type: "STRING" },
        { name: "seed", type: "INT", default: -1 },
      ],
    };
    const rows = wiredInputsForNode(workflow, "n4", schema.inputs);
    expect(rows[0]?.connected).toBe(true);
    expect(rows[0]?.sourceNode?.type).toBe("Prompt");
    expect(rows[1]?.connected).toBe(false);
  });
});

describe("wiredInputSupersedesWidget", () => {
  it("disables MIDIToAudio prompt when text socket is wired", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        ...sampleWorkflow().nodes,
        { id: "p1", type: "Prompt", pos: { x: 0, y: 120 }, widgets: { text: "guitar lead" } },
        { id: "m4", type: "MIDIToAudio", pos: { x: 280, y: 0 }, widgets: { model: "musicgen-melody-small", prompt: "stale" } },
      ],
      links: [{ id: "l3", from: ["p1", 0], to: ["m4", 1], type: "TEXT" }],
    };
    const inputs = [
      { name: "midi", type: "MIDI" },
      { name: "text", type: "TEXT", optional: true },
      { name: "reference_audio", type: "AUDIO", optional: true },
    ];
    const rows = wiredInputsForNode(workflow, "m4", inputs);
    const superseded = wiredInputSupersedesWidget("MIDIToAudio", "prompt", rows);
    expect(superseded?.name).toBe("text");
    expect(superseded?.sourceNode?.id).toBe("p1");
    expect(wiredInputSupersedesWidget("MIDIToAudio", "model", rows)).toBeNull();
    expect(wiredPromptPreview(superseded?.sourceNode)).toBe("guitar lead");
  });

  it("leaves prompt editable when text socket is open", () => {
    const inputs = [
      { name: "midi", type: "MIDI" },
      { name: "text", type: "TEXT", optional: true },
    ];
    const rows = wiredInputsForNode(sampleWorkflow(), "n1", inputs);
    expect(wiredInputSupersedesWidget("MIDIToAudio", "prompt", rows)).toBeNull();
  });

  it("disables GenerateAudio prompt when text socket is wired", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        ...sampleWorkflow().nodes,
        { id: "p1", type: "Prompt", pos: { x: 0, y: 120 }, widgets: { text: "lo-fi bed" } },
        {
          id: "g1",
          type: "GenerateAudio",
          pos: { x: 280, y: 0 },
          widgets: { model: "musicgen-small", prompt: "stale", seed: -1 },
        },
      ],
      links: [{ id: "l3", from: ["p1", 0], to: ["g1", 0], type: "TEXT" }],
    };
    const inputs = [
      { name: "text", type: "TEXT", optional: true },
      { name: "midi", type: "MIDI", optional: true },
      { name: "reference_audio", type: "AUDIO", optional: true },
    ];
    const rows = wiredInputsForNode(workflow, "g1", inputs);
    const superseded = wiredInputSupersedesWidget("GenerateAudio", "prompt", rows);
    expect(superseded?.name).toBe("text");
    expect(wiredPromptPreview(superseded?.sourceNode)).toBe("lo-fi bed");
  });
});

describe("workflowToFlowEdges", () => {
  it("assigns typed edge classes and labels", () => {
    const edges = workflowToFlowEdges(sampleWorkflow());
    expect(edges[0]?.label).toBe("AUDIO");
    expect(edges[0]?.className).toContain("groovy-edge--type-audio");
    expect(edges[0]?.selectable).toBe(true);
    expect(edges[0]?.interactionWidth).toBe(36);
  });

  it("animates and marks only active path edges during playback", () => {
    const edges = workflowToFlowEdges(sampleWorkflow(), new Set(["l2"]));
    const byId = Object.fromEntries(edges.map((edge) => [edge.id, edge]));
    expect(byId.l1?.animated).toBe(false);
    expect(byId.l1?.className).not.toContain("groovy-edge--active");
    expect(byId.l2?.animated).toBe(true);
    expect(byId.l2?.className).toContain("groovy-edge--active");
  });

  it("leaves all edges idle when active set is empty", () => {
    const edges = workflowToFlowEdges(sampleWorkflow(), new Set());
    expect(edges.every((edge) => edge.animated === false)).toBe(true);
    expect(edges.every((edge) => !edge.className?.includes("groovy-edge--active"))).toBe(true);
  });

  it("uses palette color override and exposes glow CSS var", () => {
    const base = sampleWorkflow();
    const workflow: Workflow = {
      ...base,
      links: base.links.map((link, i) => (i === 0 ? { ...link, color: "#ffffff" } : link)),
    };
    const edges = workflowToFlowEdges(workflow);
    expect(edges[0]?.style?.stroke).toBe("#ffffff");
    expect((edges[0]?.style as Record<string, string>)["--edge-glow"]).toBe("#ffffff");
  });

  it("ignores out-of-palette colors and falls back to socket type", () => {
    const base = sampleWorkflow();
    const workflow: Workflow = {
      ...base,
      links: base.links.map((link, i) => (i === 0 ? { ...link, color: "#7c3aed" } : link)),
    };
    const edges = workflowToFlowEdges(workflow);
    expect(edges[0]?.style?.stroke).toBe("#ff002b");
  });
});

describe("setLinkColor", () => {
  it("sets palette color and clears with null", () => {
    const colored = setLinkColor(sampleWorkflow(), "l1", "#a3a3a3");
    expect(colored.links.find((l) => l.id === "l1")?.color).toBe("#a3a3a3");
    const cleared = setLinkColor(colored, "l1", null);
    expect(cleared.links.find((l) => l.id === "l1")?.color).toBeUndefined();
  });

  it("rejects non-palette colors", () => {
    const next = setLinkColor(sampleWorkflow(), "l1", "#00ff00");
    expect(next.links.find((l) => l.id === "l1")?.color).toBeUndefined();
  });
});

describe("edgeIdsOnPathToNode", () => {
  it("returns upstream link ids into the audition target", () => {
    expect([...edgeIdsOnPathToNode(sampleWorkflow(), "n3")].sort()).toEqual(["l1", "l2"]);
    expect([...edgeIdsOnPathToNode(sampleWorkflow(), "n2")]).toEqual(["l1"]);
    expect(edgeIdsOnPathToNode(sampleWorkflow(), "n1").size).toBe(0);
  });

  it("returns empty for an unknown node", () => {
    expect(edgeIdsOnPathToNode(sampleWorkflow(), "missing").size).toBe(0);
  });
});

describe("channelConvertSocketLabels", () => {
  it("labels mono→stereo conversion", () => {
    expect(channelConvertSocketLabels("stereo", 1)).toEqual({ input: "MONO", output: "STEREO" });
    expect(channelConvertSocketLabels("stereo", null)).toEqual({ input: "MONO", output: "STEREO" });
  });

  it("labels stereo→mono conversion", () => {
    expect(channelConvertSocketLabels("mono", 2)).toEqual({ input: "STEREO", output: "MONO" });
  });
});

describe("workflowToFlowNodes", () => {
  it("exposes TRAJECTORY handles without schemas so monitors can be wired", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n2", type: "TrajectoryAuthor", pos: { x: 0, y: 0 }, widgets: {} },
        { id: "n7", type: "TrajectoryMonitor", pos: { x: 200, y: 0 }, widgets: { role: "input" } },
        { id: "n3", type: "AmbisonicUpmix", pos: { x: 400, y: 0 }, widgets: {} },
      ],
      links: [
        { id: "l2", from: ["n2", 0], to: ["n7", 0], type: "TRAJECTORY" },
        { id: "l2c", from: ["n7", 0], to: ["n3", 1], type: "TRAJECTORY" },
      ],
    };
    const nodes = workflowToFlowNodes(workflow, {});
    const author = nodes.find((node) => node.id === "n2");
    const monitor = nodes.find((node) => node.id === "n7");
    const upmix = nodes.find((node) => node.id === "n3");
    expect(author?.data.outputs?.[0]).toMatchObject({ type: "TRAJECTORY", slot: 0 });
    expect(monitor?.data.inputs?.[0]).toMatchObject({ type: "TRAJECTORY", slot: 0 });
    expect(monitor?.data.outputs?.[0]).toMatchObject({ type: "TRAJECTORY", slot: 0 });
    expect(upmix?.data.inputs?.[1]).toMatchObject({ type: "TRAJECTORY", slot: 1 });
    const edges = workflowToFlowEdges(workflow);
    expect(edges.map((e) => `${e.source}:${e.sourceHandle}->${e.target}:${e.targetHandle}`)).toEqual([
      "n2:0->n7:0",
      "n7:0->n3:1",
    ]);
  });

  it("labels ChannelConvert sockets from layout widget", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "src", type: "MIDIToAudio", pos: { x: 0, y: 0 }, widgets: {} },
        {
          id: "cc",
          type: "ChannelConvert",
          pos: { x: 200, y: 0 },
          widgets: { layout: "stereo" },
        },
      ],
      links: [{ id: "l1", from: ["src", 0], to: ["cc", 0], type: "AUDIO" }],
    };
    const schemas: Record<string, import("./types").NodeSchema> = {
      MIDIToAudio: {
        type: "MIDIToAudio",
        category: "GroovyUI/AI",
        inputs: [{ name: "midi", type: "MIDI" }],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      },
      ChannelConvert: {
        type: "ChannelConvert",
        category: "GroovyUI/Core",
        inputs: [{ name: "audio", type: "AUDIO" }],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [{ name: "layout", type: "STRING", default: "mono" }],
      },
    };
    const nodes = workflowToFlowNodes(workflow, {}, undefined, schemas);
    const cc = nodes.find((node) => node.id === "cc");
    expect(cc?.data.inputs).toEqual([{ name: "MONO", type: "AUDIO", slot: 0 }]);
    expect(cc?.data.outputs).toEqual([{ name: "STEREO", type: "AUDIO", slot: 0 }]);
  });

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

  it("expands LoadAudio outlets from probed channel count before render", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        {
          id: "load",
          type: "LoadAudio",
          pos: { x: 0, y: 0 },
          widgets: { path: "assets/samples/stereo.wav" },
        },
      ],
      links: [],
    };
    const schemas: Record<string, import("./types").NodeSchema> = {
      LoadAudio: {
        type: "LoadAudio",
        category: "GroovyUI/Core",
        inputs: [],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [{ name: "path", type: "STRING", default: "" }],
      },
    };
    const nodes = workflowToFlowNodes(workflow, {}, undefined, schemas, undefined, { load: 2 });
    const load = nodes.find((node) => node.id === "load");
    expect(load?.data.outputs).toEqual([
      { name: "L", type: "AUDIO", slot: 0 },
      { name: "R", type: "AUDIO", slot: 1 },
    ]);
    expect((load?.data as { kind?: string; channelLabel?: string }).kind).toBe("core");
    expect((load?.data as { channelLabel?: string }).channelLabel).toBe("stereo");
  });

  it("always labels LoadAudio / Preview / SaveAudio channel layout", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "load", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } },
        { id: "prev", type: "Preview", pos: { x: 200, y: 0 }, widgets: {} },
        { id: "save", type: "SaveAudio", pos: { x: 400, y: 0 }, widgets: {} },
      ],
      links: [
        { id: "l1", from: ["load", 0], to: ["prev", 0], type: "AUDIO" },
        { id: "l2", from: ["load", 0], to: ["save", 0], type: "AUDIO" },
      ],
    };
    const schemas: Record<string, import("./types").NodeSchema> = {
      LoadAudio: {
        type: "LoadAudio",
        category: "GroovyUI/Core",
        inputs: [],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      },
      Preview: {
        type: "Preview",
        category: "GroovyUI/Core",
        inputs: [
          { name: "audio", type: "AUDIO", optional: true },
          { name: "text", type: "TEXT", optional: true },
        ],
        outputs: [{ name: "audio", type: "AUDIO" }],
        widgets: [],
      },
      SaveAudio: {
        type: "SaveAudio",
        category: "GroovyUI/Core",
        inputs: [{ name: "audio", type: "AUDIO" }],
        outputs: [{ name: "path", type: "STRING" }],
        widgets: [],
      },
    };
    const nodes = workflowToFlowNodes(workflow, {}, undefined, schemas, undefined, { load: 1 });
    const byId = Object.fromEntries(nodes.map((node) => [node.id, node.data as { channelLabel?: string; outputs?: { name: string }[] }]));
    expect(byId.load?.channelLabel).toBe("mono");
    expect(byId.load?.outputs?.[0]?.name).toBe("mono");
    expect(byId.prev?.channelLabel).toBe("mono");
    expect(byId.save?.channelLabel).toBe("mono");
  });

  it("marks AI vs core kind on canvas nodes", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
        { id: "n2", type: "GenerateAudio", pos: { x: 200, y: 0 }, widgets: {} },
      ],
      links: [],
    };
    const schemas: Record<string, import("./types").NodeSchema> = {
      LoadAudio: {
        type: "LoadAudio",
        category: "GroovyUI/Core",
        inputs: [],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      },
      GenerateAudio: {
        type: "GenerateAudio",
        category: "GroovyUI/AI",
        inputs: [],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      },
    };
    const nodes = workflowToFlowNodes(workflow, {}, undefined, schemas);
    expect((nodes.find((n) => n.id === "n1")?.data as { kind?: string }).kind).toBe("core");
    expect((nodes.find((n) => n.id === "n2")?.data as { kind?: string }).kind).toBe("ai");
  });

  it("surfaces Note comment text on the canvas node", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        {
          id: "note",
          type: "Note",
          pos: { x: 40, y: 40 },
          widgets: { text: "Keep vocals dry" },
        },
      ],
      links: [],
    };
    const schemas: Record<string, import("./types").NodeSchema> = {
      Note: {
        type: "Note",
        category: "GroovyUI/Core",
        inputs: [],
        outputs: [],
        widgets: [{ name: "text", type: "STRING", default: "" }],
      },
    };
    const nodes = workflowToFlowNodes(workflow, {}, undefined, schemas);
    const note = nodes.find((node) => node.id === "note");
    expect(note?.data).toMatchObject({
      label: "Note",
      noteText: "Keep vocals dry",
      inputs: [],
      outputs: [],
    });
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
    const empty: Workflow = { ...sampleWorkflow(), nodes: [], links: [] };
    const pos = findOpenNodePosition(empty, { x: 100, y: 100 });
    expect(pos).toEqual({ x: 0, y: 56 });
  });

  it("offsets when center overlaps an existing node", () => {
    const pos = findOpenNodePosition(sampleWorkflow(), { x: 10, y: 10 });
    expect(pos.x !== 10 || pos.y !== 10).toBe(true);
    const placed = {
      ...sampleWorkflow(),
      nodes: [...sampleWorkflow().nodes, { id: "n4", type: "Mix", pos, widgets: {} }],
    };
    expect(workflowHasOverlappingNodes(placed)).toBe(false);
  });
});

describe("normalizeLoadedWorkflow", () => {
  it("defaults missing groups so canvas helpers do not crash", () => {
    const raw = {
      ...sampleWorkflow(),
      groups: undefined,
    } as unknown as Workflow;
    const normalized = normalizeLoadedWorkflow(raw);
    expect(normalized.groups).toEqual([]);
    expect(() => workflowToFlowNodes(normalized, {})).not.toThrow();
  });
});

describe("layoutWorkflowNodes", () => {
  it("separates overlapping chain nodes into a left-to-right layout", () => {
    const crowded: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
        { id: "n2", type: "Normalize", pos: { x: 40, y: 10 }, widgets: {} },
        { id: "n3", type: "Preview", pos: { x: 60, y: 20 }, widgets: {} },
      ],
    };
    expect(workflowHasOverlappingNodes(crowded)).toBe(true);
    const laid = layoutWorkflowNodes(crowded);
    expect(workflowHasOverlappingNodes(laid)).toBe(false);
    expect(laid.nodes.find((n) => n.id === "n1")!.pos!.x).toBeLessThan(
      laid.nodes.find((n) => n.id === "n2")!.pos!.x,
    );
    expect(laid.nodes.find((n) => n.id === "n2")!.pos!.x).toBeLessThan(
      laid.nodes.find((n) => n.id === "n3")!.pos!.x,
    );
  });

  it("stacks fan-out previews without overlap", () => {
    const stems: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
        { id: "n2", type: "SeparateStems", pos: { x: 100, y: 0 }, widgets: {} },
        { id: "p0", type: "Preview", pos: { x: 200, y: 0 }, widgets: {} },
        { id: "p1", type: "Preview", pos: { x: 200, y: 10 }, widgets: {} },
        { id: "p2", type: "Preview", pos: { x: 200, y: 20 }, widgets: {} },
        { id: "p3", type: "Preview", pos: { x: 200, y: 30 }, widgets: {} },
      ],
      links: [
        { id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" },
        { id: "l2", from: ["n2", 0], to: ["p0", 0], type: "AUDIO" },
        { id: "l3", from: ["n2", 1], to: ["p1", 0], type: "AUDIO" },
        { id: "l4", from: ["n2", 2], to: ["p2", 0], type: "AUDIO" },
        { id: "l5", from: ["n2", 3], to: ["p3", 0], type: "AUDIO" },
      ],
    };
    const laid = layoutWorkflowNodes(stems);
    expect(workflowHasOverlappingNodes(laid)).toBe(false);
    expect(estimateNodeSize({ id: "n2", type: "SeparateStems", widgets: {} }).height).toBeGreaterThan(88);
  });
});

describe("ensureNoOverlappingNodes", () => {
  it("leaves well-spaced graphs untouched", () => {
    const spaced = sampleWorkflow();
    expect(workflowHasOverlappingNodes(spaced)).toBe(false);
    expect(ensureNoOverlappingNodes(spaced)).toBe(spaced);
  });

  it("relayouts only when nodes overlap", () => {
    const crowded: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
        { id: "n2", type: "Normalize", pos: { x: 10, y: 5 }, widgets: {} },
        { id: "n3", type: "Preview", pos: { x: 20, y: 8 }, widgets: {} },
      ],
      links: [
        { id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" },
        { id: "l2", from: ["n2", 0], to: ["n3", 0], type: "AUDIO" },
      ],
    };
    const fixed = ensureNoOverlappingNodes(crowded);
    expect(workflowHasOverlappingNodes(fixed)).toBe(false);
    expect(fixed).not.toBe(crowded);
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

  it("listens to AUDIO slot on SAMPLE_CHECK+AUDIO MULTI (VerifySamples)", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", widgets: { path: "a.wav" } },
        { id: "n2", type: "VerifySamples", widgets: {} },
      ],
      links: [{ id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" }],
    };
    const outputs: Record<string, JobOutput> = {
      n1: { type: "AUDIO", cache_id: "src" },
      n2: {
        type: "MULTI",
        outputs: [
          { type: "SAMPLE_CHECK", sample_check_id: "rep" },
          { type: "AUDIO", cache_id: "src" },
        ],
      },
    };
    expect(resolveNodeListenId(workflow, "n2", outputs)).toBe("src");
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

  it("prefers the Preview sink after render-all for automatic audition", () => {
    const outputs: Record<string, JobOutput> = {
      n1: { type: "AUDIO", cache_id: "source" },
      n2: { type: "AUDIO", cache_id: "normalized" },
      n3: { type: "AUDIO", cache_id: "preview" },
    };
    expect(preferredAuditionNodeId(workflow, outputs)).toBe("n3");
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

describe("authenticityReportId", () => {
  it("prefers AuthenticitySummary over VerifyProvenance", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n2", type: "VerifyProvenance", widgets: {} },
        { id: "n4", type: "AuthenticitySummary", widgets: {} },
      ],
      links: [],
    };
    const id = authenticityReportId(workflow, {
      n2: { type: "AUTHENTICITY", authenticity_id: "verify" },
      n4: { type: "AUTHENTICITY", authenticity_id: "summary" },
    });
    expect(id).toBe("summary");
  });

  it("reads AUTHENTICITY from a MULTI DeepfakeDetect slot", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [{ id: "n3", type: "DeepfakeDetect", widgets: {} }],
      links: [],
    };
    const id = authenticityReportId(workflow, {
      n3: {
        type: "MULTI",
        outputs: [
          { type: "AUTHENTICITY", authenticity_id: "ml" },
          { type: "AUDIO", cache_id: "pass" },
        ],
      },
    });
    expect(id).toBe("ml");
  });

  it("keeps AuthenticitySummary when DeepfakeDetect is selected", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n3", type: "DeepfakeDetect", widgets: {} },
        { id: "n4", type: "AuthenticitySummary", widgets: {} },
      ],
      links: [],
    };
    const id = authenticityReportId(
      workflow,
      {
        n3: {
          type: "MULTI",
          outputs: [{ type: "AUTHENTICITY", authenticity_id: "ml" }],
        },
        n4: { type: "AUTHENTICITY", authenticity_id: "summary" },
      },
      "n3",
    );
    expect(id).toBe("summary");
  });
});

describe("saved artifact paths", () => {
  const output: JobOutput = {
    type: "STRING",
    path: "/project/exports/render.wav",
    provenance_path: "/project/exports/render.provenance.json",
  };

  it("returns paired SaveAudio artifact paths", () => {
    expect(savedFilePath(output)).toBe("/project/exports/render.wav");
    expect(savedProvenancePath(output)).toBe(
      "/project/exports/render.provenance.json",
    );
  });
});

describe("resolveRenderAllTargets", () => {
  it("returns all terminal nodes in a multi-preview graph", () => {
    const workflow: Workflow = {
      version: 1,
      metadata: { title: "stems" },
      nodes: [
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } },
        { id: "n2", type: "SeparateStems", pos: { x: 200, y: 0 }, widgets: {} },
        { id: "p1", type: "Preview", pos: { x: 400, y: -40 }, widgets: {} },
        { id: "p2", type: "Preview", pos: { x: 400, y: 40 }, widgets: {} },
      ],
      links: [
        { id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" },
        { id: "l2", from: ["n2", 0], to: ["p1", 0], type: "AUDIO" },
        { id: "l3", from: ["n2", 1], to: ["p2", 0], type: "AUDIO" },
      ],
      groups: [],
    };
    expect(resolveRenderAllTargets(workflow).sort()).toEqual(["p1", "p2"]);
  });

  it("falls back to all nodes when graph has no links", () => {
    const workflow: Workflow = {
      version: 1,
      metadata: { title: "solo" },
      nodes: [
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
        { id: "n2", type: "Preview", pos: { x: 200, y: 0 }, widgets: {} },
      ],
      links: [],
      groups: [],
    };
    expect(resolveRenderAllTargets(workflow).sort()).toEqual(["n1", "n2"]);
  });
});

describe("withAuthenticityRenderTargets", () => {
  it("adds AuthenticitySummary when rendering a Preview", () => {
    const workflow: Workflow = {
      ...sampleWorkflow(),
      nodes: [
        { id: "n1", type: "LoadAudio", widgets: {} },
        { id: "n4", type: "AuthenticitySummary", widgets: {} },
        { id: "n5", type: "Preview", widgets: {} },
      ],
      links: [{ id: "l1", from: ["n1", 0], to: ["n5", 0], type: "AUDIO" }],
    };
    expect(withAuthenticityRenderTargets(workflow, ["n5"]).sort()).toEqual(["n4", "n5"]);
  });
});

describe("subgraph port wiring", () => {
  const stemsWorkflow = (): Workflow => ({
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: "wf",
    metadata: { title: "stems" },
    nodes: [
      { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
      { id: "n2", type: "SeparateStems", pos: { x: 200, y: 0 }, widgets: {} },
      { id: "p1", type: "Preview", pos: { x: 400, y: 0 }, widgets: {} },
      { id: "p2", type: "Preview", pos: { x: 400, y: 80 }, widgets: {} },
    ],
    links: [
      { id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" },
      { id: "l2", from: ["n2", 0], to: ["p1", 0], type: "AUDIO" },
      { id: "l3", from: ["n2", 1], to: ["p2", 0], type: "AUDIO" },
    ],
    groups: [],
  });

  it("maps outbound links per output slot", () => {
    const rows = wiredOutputsForNode(stemsWorkflow(), "n2", [
      { name: "vocals", type: "AUDIO" },
      { name: "drums", type: "AUDIO" },
      { name: "bass", type: "AUDIO" },
      { name: "other", type: "AUDIO" },
    ]);
    expect(rows.map((r) => r.connected)).toEqual([true, true, false, false]);
    expect(rows[0].linkCount).toBe(1);
    expect(rows[1].targetNodeIds).toEqual(["p2"]);
  });

  it("disconnects an output slot without touching other wires", () => {
    const next = disconnectPort(stemsWorkflow(), "n2", "out", 0);
    expect(next.links.map((l) => l.id).sort()).toEqual(["l1", "l3"]);
  });

  it("disconnects an input slot", () => {
    const next = disconnectPort(stemsWorkflow(), "n2", "in", 0);
    expect(next.links.map((l) => l.id).sort()).toEqual(["l2", "l3"]);
  });
});
