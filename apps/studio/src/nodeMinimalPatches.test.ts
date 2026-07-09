import { describe, expect, it } from "vitest";
import { augmentNodeWithExample, getMinimalPatch, hasMinimalPatch } from "./nodeMinimalPatches";

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
      expect(next.nodes.some((node) => node.type === "TTS")).toBe(false);
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
});
