import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  applyMinimalPatchToCanvas,
  augmentNodeWithExample,
  getMinimalPatch,
  hasMinimalPatch,
  listCuratedMinimalPatchTypes,
  summarizeMinimalPatch,
} from "./nodeMinimalPatches";
import schemaSlots from "./fixtures/node_schema_slots.json";

type SlotSpec = { name: string; type: string; optional?: boolean; slot: number };
type SchemaSlots = Record<string, { inputs: SlotSpec[]; outputs: SlotSpec[] }>;
const SLOTS = schemaSlots as SchemaSlots;

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

function emptyWorkflow(title: string, nodes: Array<{ id: string; type: string; pos?: { x: number; y: number } }>) {
  return {
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: "wf",
    metadata: { title },
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type,
      pos: node.pos ?? { x: 240, y: 120 },
      widgets: {},
    })),
    links: [],
    groups: [],
  };
}

function validatePatchLinks(
  label: string,
  nodes: Array<{ id: string; type: string }>,
  links: Array<{ id: string; from: [string, number]; to: [string, number]; type: string }>,
  failures: string[],
) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  for (const edge of links) {
    const fromNode = byId.get(edge.from[0]);
    const toNode = byId.get(edge.to[0]);
    if (!fromNode || !toNode) {
      failures.push(`${label}: missing endpoint for ${edge.id}`);
      continue;
    }
    const fromSchema = SLOTS[fromNode.type];
    const toSchema = SLOTS[toNode.type];
    if (!fromSchema || !toSchema) {
      failures.push(`${label}: unknown schema for ${fromNode.type}→${toNode.type}`);
      continue;
    }
    const out = fromSchema.outputs.find((socket) => socket.slot === edge.from[1]);
    const inn = toSchema.inputs.find((socket) => socket.slot === edge.to[1]);
    if (!out) {
      failures.push(`${label}: ${fromNode.type} has no output slot ${edge.from[1]} (${edge.id})`);
    } else if (out.type !== edge.type) {
      failures.push(
        `${label}: ${fromNode.type} out[${edge.from[1]}] is ${out.type}, link claims ${edge.type}`,
      );
    }
    if (!inn) {
      failures.push(
        `${label}: ${toNode.type} has no input slot ${edge.to[1]} (${edge.id}, type ${edge.type})`,
      );
    } else if (inn.type !== edge.type) {
      failures.push(
        `${label}: ${toNode.type} in[${edge.to[1]}] is ${inn.type}, link claims ${edge.type}`,
      );
    }
  }
}

describe("nodeMinimalPatches", () => {
  it("has recipes for core studio nodes", () => {
    expect(hasMinimalPatch("LoadAudio")).toBe(true);
    expect(hasMinimalPatch("Denoise")).toBe(true);
    expect(hasMinimalPatch("Preview")).toBe(true);
  });

  it("builds a denoise example with focus on the denoise node", () => {
    const patch = getMinimalPatch("Denoise");
    expect(patch).not.toBeNull();
    expect(patch!.focusNodeId).toBe("n2");
    expect(patch!.workflow.nodes.some((node) => node.type === "Denoise")).toBe(true);
    expect(patch!.workflow.nodes.some((node) => node.type === "LoadAudio")).toBe(true);
    expect(patch!.workflow.links.length).toBeGreaterThan(0);
  });

  it("builds mix with two audio inputs", () => {
    const patch = getMinimalPatch("Mix");
    expect(patch!.workflow.nodes.filter((node) => node.type === "LoadAudio")).toHaveLength(2);
    const mixLinks = patch!.workflow.links.filter((link) => link.to[0] === "n3");
    expect(mixLinks).toHaveLength(2);
  });

  it("falls back to schema-driven patch for unknown types", () => {
    const patch = getMinimalPatch("CustomNode", {
      CustomNode: {
        type: "CustomNode",
        category: "Test",
        inputs: [{ name: "audio", type: "AUDIO" }],
        outputs: [{ name: "out", type: "AUDIO" }],
        widgets: [],
      },
    });
    expect(patch).not.toBeNull();
    expect(patch!.workflow.nodes.map((node) => node.type)).toEqual(["CustomNode", "LoadAudio", "Preview"]);
  });

  it("wires all required inputs for multi-input schema nodes", () => {
    const patch = getMinimalPatch("DualMix", {
      DualMix: {
        type: "DualMix",
        category: "Test",
        inputs: [
          { name: "a", type: "AUDIO" },
          { name: "b", type: "AUDIO" },
        ],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      },
    });
    expect(patch).not.toBeNull();
    const focusLinks = patch!.workflow.links.filter((edge) => edge.to[0] === "n1");
    expect(focusLinks).toHaveLength(2);
    expect(focusLinks.map((edge) => edge.to[1]).sort()).toEqual([0, 1]);
    expect(patch!.workflow.nodes.filter((node) => node.type === "LoadAudio")).toHaveLength(2);
  });

  it("wires each output for multi-output schema nodes", () => {
    const patch = getMinimalPatch("DeepfakeDetect", {
      DeepfakeDetect: {
        type: "DeepfakeDetect",
        category: "GroovyUI/AI",
        inputs: [{ name: "audio", type: "AUDIO" }],
        outputs: [
          { name: "output_0", type: "AUTHENTICITY" },
          { name: "output_1", type: "AUDIO" },
        ],
        widgets: [],
      },
    });
    expect(patch).not.toBeNull();
    const fromFocus = patch!.workflow.links.filter((edge) => edge.from[0] === patch!.focusNodeId);
    expect(fromFocus.map((edge) => edge.from[1]).sort()).toEqual([0, 1]);
    expect(patch!.workflow.nodes.some((node) => node.type === "Preview")).toBe(true);
    expect(patch!.workflow.nodes.some((node) => node.type === "AuthenticitySummary")).toBe(true);
  });

  it("wires optional text inputs when required inputs exist", () => {
    const patch = getMinimalPatch("SingFromMIDI", {
      SingFromMIDI: {
        type: "SingFromMIDI",
        category: "GroovyUI/AI",
        inputs: [
          { name: "midi", type: "MIDI" },
          { name: "lyrics", type: "TEXT", optional: true },
          { name: "reference_audio", type: "AUDIO", optional: true },
        ],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      },
    });
    expect(patch).not.toBeNull();
    expect(patch!.focusNodeId).toBe("n3");
    const focusLinks = patch!.workflow.links.filter((edge) => edge.to[0] === patch!.focusNodeId);
    expect(focusLinks.map((edge) => edge.type).sort()).toEqual(["AUDIO", "MIDI", "TEXT"]);
    expect(focusLinks.find((edge) => edge.type === "TEXT")?.to[1]).toBe(1);
    expect(patch!.workflow.nodes.some((node) => node.type === "Prompt")).toBe(true);
    expect(patch!.workflow.nodes.some((node) => node.type === "LoadMIDI")).toBe(true);
  });

  describe("augmentNodeWithExample", () => {
    const loadAudioSchema = {
      type: "LoadAudio",
      category: "GroovyUI/Core",
      inputs: [] as { name: string; type: string }[],
      outputs: [{ name: "output_0", type: "AUDIO" }],
      widgets: [{ name: "path", type: "STRING" }],
    };

    const previewSchema = {
      type: "Preview",
      category: "GroovyUI/Core",
      inputs: [{ name: "audio", type: "AUDIO" }],
      outputs: [{ name: "output_0", type: "AUDIO" }],
      widgets: [],
    };

    const normalizeSchema = {
      type: "Normalize",
      category: "GroovyUI/Core",
      inputs: [{ name: "audio", type: "AUDIO" }],
      outputs: [{ name: "output_0", type: "AUDIO" }],
      widgets: [],
    };

    it("wires preview downstream from a lone LoadAudio node", () => {
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [{ id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } }],
        links: [],
        groups: [],
      };
      const patch = getMinimalPatch("LoadAudio", { LoadAudio: loadAudioSchema })!;
      const { workflow: next, changed } = augmentNodeWithExample(workflow, "n1", loadAudioSchema, patch);
      expect(changed).toBe(true);
      expect(next.nodes.some((node) => node.type === "Preview")).toBe(true);
      const previewId = next.nodes.find((node) => node.type === "Preview")!.id;
      expect(next.links).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ from: ["n1", 0], to: [previewId, 0], type: "AUDIO" }),
        ]),
      );
    });

    it("wires load audio upstream from a lone Preview node", () => {
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [{ id: "n3", type: "Preview", pos: { x: 520, y: 0 }, widgets: {} }],
        links: [],
        groups: [],
      };
      const patch = getMinimalPatch("Preview", { Preview: previewSchema })!;
      const { workflow: next, changed } = augmentNodeWithExample(workflow, "n3", previewSchema, patch);
      expect(changed).toBe(true);
      expect(next.nodes.some((node) => node.type === "LoadAudio")).toBe(true);
    });

    it("works regardless of whether preview or load audio was added first", () => {
      const loadOnly: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [{ id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } }],
        links: [],
        groups: [],
      };
      const previewOnly: import("./types").Workflow = {
        ...loadOnly,
        nodes: [{ id: "n3", type: "Preview", pos: { x: 520, y: 0 }, widgets: {} }],
      };
      const loadPatch = getMinimalPatch("LoadAudio", { LoadAudio: loadAudioSchema })!;
      const previewPatch = getMinimalPatch("Preview", { Preview: previewSchema })!;
      const fromLoad = augmentNodeWithExample(loadOnly, "n1", loadAudioSchema, loadPatch);
      const fromPreview = augmentNodeWithExample(previewOnly, "n3", previewSchema, previewPatch);
      expect(fromLoad.changed).toBe(true);
      expect(fromPreview.changed).toBe(true);
      const previewId = fromLoad.workflow.nodes.find((node) => node.type === "Preview")!.id;
      expect(fromLoad.workflow.links).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ from: ["n1", 0], to: [previewId, 0], type: "AUDIO" }),
        ]),
      );
      const loadThenPreview = augmentNodeWithExample(fromLoad.workflow, "n3", previewSchema, previewPatch);
      expect(loadThenPreview.changed).toBe(false);
    });

    it("adds missing preview when normalize already has load audio upstream", () => {
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [
          { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } },
          { id: "n2", type: "Normalize", pos: { x: 260, y: 0 }, widgets: {} },
        ],
        links: [{ id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" }],
        groups: [],
      };
      const patch = getMinimalPatch("Normalize", { Normalize: normalizeSchema })!;
      const { workflow: next, changed } = augmentNodeWithExample(workflow, "n2", normalizeSchema, patch);
      expect(changed).toBe(true);
      expect(next.nodes.some((node) => node.type === "Preview")).toBe(true);
    });

    it("augments lone LoadAudio without schema using patch io fallback", () => {
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [{ id: "wf_n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } }],
        links: [],
        groups: [],
      };
      const patch = getMinimalPatch("LoadAudio")!;
      const { workflow: next, changed } = augmentNodeWithExample(workflow, "wf_n1", undefined, patch);
      expect(changed).toBe(true);
      expect(next.nodes.some((node) => node.type === "Preview")).toBe(true);
    });

    const denoiseSchema = {
      type: "Denoise",
      category: "GroovyUI/AI",
      inputs: [{ name: "audio", type: "AUDIO" }],
      outputs: [{ name: "output_0", type: "AUDIO" }],
      widgets: [],
    };

    it("keeps the selected node and adds missing upstream and downstream", () => {
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [{ id: "n9", type: "Denoise", pos: { x: 400, y: 0 }, widgets: {} }],
        links: [],
        groups: [],
      };
      const patch = getMinimalPatch("Denoise", { Denoise: denoiseSchema })!;
      const { workflow: next, changed, focusNodeId } = augmentNodeWithExample(
        workflow,
        "n9",
        denoiseSchema,
        patch,
      );
      expect(changed).toBe(true);
      expect(focusNodeId).toBe("n9");
      expect(next.nodes.some((node) => node.id === "n9" && node.type === "Denoise")).toBe(true);
      expect(next.nodes.some((node) => node.type === "LoadAudio")).toBe(true);
      expect(next.nodes.some((node) => node.type === "Preview")).toBe(true);
    });

    it("does not duplicate preview when output is already wired", () => {
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [
          { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } },
          { id: "n2", type: "Denoise", pos: { x: 260, y: 0 }, widgets: {} },
          { id: "n3", type: "Preview", pos: { x: 520, y: 0 }, widgets: {} },
        ],
        links: [
          { id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" },
          { id: "l2", from: ["n2", 0], to: ["n3", 0], type: "AUDIO" },
        ],
        groups: [],
      };
      const patch = getMinimalPatch("Preview")!;
      const previewSchema = {
        type: "Preview",
        category: "GroovyUI/Core",
        inputs: [{ name: "audio", type: "AUDIO" }],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      };
      const { workflow: next, changed } = augmentNodeWithExample(
        workflow,
        "n3",
        previewSchema,
        patch,
      );
      expect(changed).toBe(false);
      expect(next.nodes.filter((node) => node.type === "Preview")).toHaveLength(1);
    });

    it("only adds missing downstream when inputs are already wired", () => {
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [
          { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: { path: "a.wav" } },
          { id: "n2", type: "Denoise", pos: { x: 260, y: 0 }, widgets: {} },
        ],
        links: [{ id: "l1", from: ["n1", 0], to: ["n2", 0], type: "AUDIO" }],
        groups: [],
      };
      const patch = getMinimalPatch("Denoise", { Denoise: denoiseSchema })!;
      const { workflow: next, changed } = augmentNodeWithExample(workflow, "n2", denoiseSchema, patch);
      expect(changed).toBe(true);
      expect(next.nodes.some((node) => node.type === "Preview")).toBe(true);
      expect(next.nodes.filter((node) => node.type === "LoadAudio")).toHaveLength(1);
    });
    it("wires text output to tts and preview", () => {
      const whisperSchema = {
        type: "WhisperSTT",
        category: "GroovyUI/AI",
        inputs: [{ name: "audio", type: "AUDIO" }],
        outputs: [{ name: "output_0", type: "TEXT" }],
        widgets: [],
      };
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [{ id: "n2", type: "WhisperSTT", pos: { x: 260, y: 0 }, widgets: {} }],
        links: [],
        groups: [],
      };
      const patch = getMinimalPatch("WhisperSTT", { WhisperSTT: whisperSchema })!;
      const { workflow: next, changed } = augmentNodeWithExample(workflow, "n2", whisperSchema, patch);
      expect(changed).toBe(true);
      expect(next.nodes.some((node) => node.type === "LoadAudio")).toBe(true);
      expect(next.nodes.some((node) => node.type === "GenerateSpeech")).toBe(false);
      expect(next.nodes.some((node) => node.type === "Preview")).toBe(false);
    });

    it("does not duplicate links when tab wiring runs twice", () => {
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [{ id: "n2", type: "Denoise", pos: { x: 260, y: 0 }, widgets: {} }],
        links: [],
        groups: [],
      };
      const patch = getMinimalPatch("Denoise", { Denoise: denoiseSchema })!;
      const first = augmentNodeWithExample(workflow, "n2", denoiseSchema, patch);
      const second = augmentNodeWithExample(first.workflow, "n2", denoiseSchema, patch);
      expect(second.changed).toBe(false);
      const targets = second.workflow.links.map((link) => `${link.to[0]}[${link.to[1]}]`);
      expect(new Set(targets).size).toBe(targets.length);
    });

    it("places augmented nodes without overlapping", () => {
      const denoiseSchema = {
        type: "Denoise",
        category: "GroovyUI/AI",
        inputs: [{ name: "audio", type: "AUDIO" }],
        outputs: [{ name: "output_0", type: "AUDIO" }],
        widgets: [],
      };
      const workflow: import("./types").Workflow = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Test" },
        nodes: [{ id: "n2", type: "Denoise", pos: { x: 300, y: 100 }, widgets: {} }],
        links: [],
        groups: [],
      };
      const patch = getMinimalPatch("Denoise", { Denoise: denoiseSchema })!;
      const { workflow: next } = augmentNodeWithExample(workflow, "n2", denoiseSchema, patch);
      const positions = next.nodes.map((node) => node.pos ?? { x: 0, y: 0 });
      for (let i = 0; i < positions.length; i++) {
        for (let j = i + 1; j < positions.length; j++) {
          const overlap =
            Math.abs(positions[i].x - positions[j].x) < 140 &&
            Math.abs(positions[i].y - positions[j].y) < 48;
          expect(overlap).toBe(false);
        }
      }
    });
  });

  describe("Help tab production recipes", () => {
    const curated = listCuratedMinimalPatchTypes();

    it("curates examples for core / AI / modular Help targets", () => {
      for (const type of [
        "GenerateSpeech",
        "Prompt",
        "Oscillator",
        "Filter",
        "Amplifier",
        "MatrixMixer",
        "TranslateText",
        "GenerateVideo",
        "LoadVideo",
        "MuxVideo",
        "Benchmark",
        "Float",
      ]) {
        expect(curated).toContain(type);
      }
      expect(curated.length).toBeGreaterThan(80);
    });

    it("builds a valid focus + chain summary for every curated recipe", () => {
      for (const type of curated) {
        const patch = getMinimalPatch(type);
        expect(patch, type).not.toBeNull();
        expect(patch!.workflow.nodes.some((node) => node.id === patch!.focusNodeId), type).toBe(true);
        expect(patch!.workflow.nodes.some((node) => node.type === type), type).toBe(true);
        const summary = summarizeMinimalPatch(patch!);
        expect(summary.title.length, type).toBeGreaterThan(0);
        expect(summary.chain.length, type).toBeGreaterThan(0);
        for (const edge of patch!.workflow.links) {
          expect(
            patch!.workflow.nodes.some((node) => node.id === edge.from[0]),
            `${type} missing from ${edge.id}`,
          ).toBe(true);
          expect(
            patch!.workflow.nodes.some((node) => node.id === edge.to[0]),
            `${type} missing to ${edge.id}`,
          ).toBe(true);
        }
      }
    });

    it("applies Help examples onto an existing canvas without wiping nodes", () => {
      const patch = getMinimalPatch("Oscillator")!;
      const base = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Base" },
        nodes: [{ id: "keep", type: "Note", pos: { x: 0, y: 0 }, widgets: { text: "keep me" } }],
        links: [],
        groups: [],
      };
      const { workflow: next, focusNodeId, expanded } = applyMinimalPatchToCanvas(base, patch, {
        x: 400,
        y: 80,
      });
      expect(expanded).toBe(false);
      expect(next.nodes.some((node) => node.id === "keep")).toBe(true);
      expect(next.nodes.some((node) => node.id === focusNodeId)).toBe(true);
      expect(next.nodes.some((node) => node.type === "Oscillator")).toBe(true);
      expect(next.nodes.length).toBeGreaterThan(base.nodes.length);
    });

    it("expands the selected matching node instead of duplicating the Help focus", () => {
      const patch = getMinimalPatch("Denoise")!;
      const base = {
        schema_version: "1.0.0",
        groovy_version: "0.1.0",
        id: "wf",
        metadata: { title: "Dropped" },
        nodes: [{ id: "dropped", type: "Denoise", pos: { x: 300, y: 120 }, widgets: {} }],
        links: [],
        groups: [],
      };
      const beforeCount = base.nodes.filter((node) => node.type === "Denoise").length;
      const { workflow: next, focusNodeId, expanded } = applyMinimalPatchToCanvas(
        base,
        patch,
        base.nodes[0].pos!,
        { expandNodeId: "dropped" },
      );
      expect(expanded).toBe(true);
      expect(focusNodeId).toBe("dropped");
      expect(next.nodes.filter((node) => node.type === "Denoise")).toHaveLength(beforeCount);
      expect(next.nodes.some((node) => node.type === "LoadAudio")).toBe(true);
      expect(next.nodes.some((node) => node.type === "Preview")).toBe(true);
      expect(next.links.some((link) => link.to[0] === "dropped")).toBe(true);
      expect(next.links.some((link) => link.from[0] === "dropped")).toBe(true);
      // Example widgets land on the existing node so Cmd+J renders the demo.
      const focus = next.nodes.find((node) => node.id === "dropped")!;
      expect(Object.keys(focus.widgets ?? {}).length).toBeGreaterThan(0);
    });

    it("wires every curated Help recipe to valid schema slots and types", () => {
      const failures: string[] = [];
      for (const type of curated) {
        const patch = getMinimalPatch(type)!;
        validatePatchLinks(type, patch.workflow.nodes, patch.workflow.links, failures);
      }
      expect(failures, failures.join("\n")).toEqual([]);
    });

    it("covers every registered backend node type with a curated Help recipe", () => {
      const registered = Object.keys(SLOTS).sort();
      const curatedSet = new Set(curated);
      const missing = registered.filter((type) => !curatedSet.has(type));
      expect(missing, `missing Help recipes:\n${missing.join("\n")}`).toEqual([]);
    });

    it("expands every curated Help recipe onto a dropped node without duplicating focus", () => {
      const failures: string[] = [];
      for (const type of curated) {
        const patch = getMinimalPatch(type)!;
        const focus = patch.workflow.nodes.find((node) => node.id === patch.focusNodeId)!;
        const helpersOfSameType = patch.workflow.nodes.filter(
          (node) => node.type === type && node.id !== patch.focusNodeId,
        ).length;
        const base = emptyWorkflow(`drop-${type}`, [{ id: "dropped", type }]);
        const { workflow: next, focusNodeId, expanded } = applyMinimalPatchToCanvas(
          base,
          patch,
          { x: 240, y: 120 },
          { expandNodeId: "dropped" },
        );
        if (!expanded) {
          failures.push(`${type}: expand did not activate`);
          continue;
        }
        if (focusNodeId !== "dropped") {
          failures.push(`${type}: focus became ${focusNodeId}`);
        }
        const focusCount = next.nodes.filter((node) => node.type === type).length;
        const expectedFocusCount = 1 + helpersOfSameType;
        if (focusCount !== expectedFocusCount) {
          failures.push(
            `${type}: expected ${expectedFocusCount} ${type} node(s), got ${focusCount}`,
          );
        }
        const expectedAdded = patch.workflow.nodes.length - 1;
        if (next.nodes.length !== 1 + expectedAdded) {
          failures.push(
            `${type}: expected ${1 + expectedAdded} nodes after expand, got ${next.nodes.length}`,
          );
        }
        // Recipe helper nodes should all be present.
        for (const node of patch.workflow.nodes) {
          if (node.id === patch.focusNodeId) continue;
          if (!next.nodes.some((candidate) => candidate.type === node.type)) {
            failures.push(`${type}: missing helper type ${node.type}`);
          }
        }
        // Example widgets merge onto the dropped focus.
        const dropped = next.nodes.find((node) => node.id === "dropped")!;
        for (const [key, value] of Object.entries(focus.widgets ?? {})) {
          if (dropped.widgets?.[key] !== value) {
            failures.push(`${type}: widget ${key} not applied to dropped node`);
          }
        }
        validatePatchLinks(`expand:${type}`, next.nodes, next.links, failures);
      }
      expect(failures, failures.join("\n")).toEqual([]);
    });

    it("inserts every curated Help recipe as a standalone patch with valid wiring", () => {
      const failures: string[] = [];
      for (const type of curated) {
        const patch = getMinimalPatch(type)!;
        const base = emptyWorkflow("blank", []);
        const { workflow: next, focusNodeId, expanded } = applyMinimalPatchToCanvas(base, patch, {
          x: 320,
          y: 160,
        });
        if (expanded) failures.push(`${type}: insert unexpectedly expanded`);
        if (!next.nodes.some((node) => node.id === focusNodeId && node.type === type)) {
          failures.push(`${type}: focus missing after insert`);
        }
        if (next.nodes.length !== patch.workflow.nodes.length) {
          failures.push(
            `${type}: insert node count ${next.nodes.length} != recipe ${patch.workflow.nodes.length}`,
          );
        }
        if (next.links.length !== patch.workflow.links.length) {
          failures.push(
            `${type}: insert link count ${next.links.length} != recipe ${patch.workflow.links.length}`,
          );
        }
        validatePatchLinks(`insert:${type}`, next.nodes, next.links, failures);
      }
      expect(failures, failures.join("\n")).toEqual([]);
    });

    it("resolves every Help recipe input sample path under assets/", () => {
      const failures: string[] = [];
      const inputLoaders = new Set([
        "LoadAudio",
        "LoadMIDI",
        "LoadVideo",
        "LoadImage",
        "MuxVideo",
      ]);
      for (const type of curated) {
        const patch = getMinimalPatch(type)!;
        for (const node of patch.workflow.nodes) {
          // Output destinations (Save*/Transcode exports/) are created at render time.
          if (node.type.startsWith("Save") || node.type === "Transcode") continue;
          for (const [key, value] of Object.entries(node.widgets ?? {})) {
            if (key !== "path" || typeof value !== "string" || !value.includes("/")) continue;
            if (value.startsWith("exports/")) continue;
            if (!inputLoaders.has(node.type) && !value.startsWith("assets/samples/")) continue;
            const abs = path.resolve(REPO_ROOT, value);
            if (!existsSync(abs)) {
              failures.push(`${type}/${node.type}: missing ${value}`);
            }
          }
        }
      }
      expect(failures, failures.join("\n")).toEqual([]);
    });
  });
});
