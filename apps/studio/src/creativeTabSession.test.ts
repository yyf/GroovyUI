import { describe, expect, it } from "vitest";
import {
  creativeTabPrompt,
  FLOW_ROW,
  formatCreativePlanTiming,
  ghostOpacityForOffset,
  ghostTierClass,
  parallelBranchRanks,
  projectCreativeGhosts,
  resolveCreativeAnchor,
  type CreativeTabSession,
} from "./creativeTabSession";
import type { Workflow } from "./types";

const emptyWorkflow: Workflow = {
  schema_version: "1.0.0",
  groovy_version: "0.1.0",
  id: "w1",
  metadata: { title: "t", description: "" },
  nodes: [{ id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} }],
  links: [],
  groups: [],
  view: { zoom: 1, pan: { x: 0, y: 0 } },
};

describe("creativeTabSession", () => {
  it("opacity ladder favors the next hop", () => {
    expect(ghostOpacityForOffset(0)).toBeGreaterThan(0.9);
    expect(ghostOpacityForOffset(1)).toBeLessThan(0.55);
    expect(ghostTierClass(0)).toBe("groovy-node-ghost--next");
  });

  it("parallel ranks fan up and down", () => {
    expect(parallelBranchRanks(1)).toEqual([0]);
    expect(parallelBranchRanks(2)).toEqual([-1, 1]);
    expect(parallelBranchRanks(3)).toEqual([-1, 0, 1]);
  });

  it("prompt focuses selected node", () => {
    const text = creativeTabPrompt({
      selectedNodeId: "n1",
      selectedNodeType: "LoadAudio",
      nodeCount: 1,
    });
    expect(text).toContain("LoadAudio");
    expect(text).toMatch(/Hero grow|Grow this patch/);
    expect(text).toMatch(/parallel/i);
  });

  it("formats planning progress as percent", () => {
    expect(formatCreativePlanTiming(2000, 14000)).toMatch(/AI agent · \d+%/);
    expect(formatCreativePlanTiming(20000, 14000)).toContain("finishing");
  });

  it("anchors a linear chain on the first signal node", () => {
    const withNote: Workflow = {
      ...emptyWorkflow,
      nodes: [
        { id: "note", type: "Note", pos: { x: 0, y: 0 }, widgets: { text: "hint" } },
        { id: "n1", type: "LoadAudio", pos: { x: 40, y: 140 }, widgets: {} },
      ],
    };
    const origin = resolveCreativeAnchor(withNote);
    expect(origin.x).toBe(40);
    expect(origin.y).toBe(140);

    const session: CreativeTabSession = {
      goal: "grow",
      notes: null,
      cursor: 0,
      planning: false,
      steps: [
        {
          id: "s1",
          index: 0,
          title: "Denoise",
          rationale: "",
          action: { type: "add_node", node: { id: "n2", type: "Denoise", widgets: {} } },
        },
        {
          id: "s2",
          index: 1,
          title: "Normalize",
          rationale: "",
          action: { type: "add_node", node: { id: "n3", type: "Normalize", widgets: {} } },
        },
        {
          id: "c1",
          index: 2,
          title: "Wire denoise",
          rationale: "",
          action: { type: "connect", from: ["n1", 0], to: ["n2", 0], link_type: "AUDIO" },
        },
        {
          id: "c2",
          index: 3,
          title: "Wire norm",
          rationale: "",
          action: { type: "connect", from: ["n2", 0], to: ["n3", 0], link_type: "AUDIO" },
        },
      ],
    };
    const { nodes } = projectCreativeGhosts(session, withNote, {});
    const g1 = nodes.find((n) => n.id === "__ghost__s1")!;
    const g2 = nodes.find((n) => n.id === "__ghost__s2")!;
    expect(g1.position.y).toBe(140);
    expect(g2.position.y).toBe(140);
    expect(g1.position.x).toBeLessThan(g2.position.x);
  });

  it("full hero grow stays on one lane until Preview/Save fan", () => {
    const withNote: Workflow = {
      ...emptyWorkflow,
      nodes: [
        { id: "note", type: "Note", pos: { x: 0, y: 0 }, widgets: { text: "hint" } },
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 140 }, widgets: {} },
      ],
    };
    const session: CreativeTabSession = {
      goal: "grow",
      notes: null,
      cursor: 0,
      planning: false,
      steps: [
        {
          id: "s-denoise",
          index: 0,
          title: "Denoise",
          rationale: "",
          action: { type: "add_node", node: { id: "n2", type: "Denoise", widgets: {} } },
        },
        {
          id: "s-norm",
          index: 1,
          title: "Normalize",
          rationale: "",
          action: { type: "add_node", node: { id: "n3", type: "Normalize", widgets: {} } },
        },
        {
          id: "s-preview",
          index: 2,
          title: "Preview",
          rationale: "",
          action: { type: "add_node", node: { id: "n4", type: "Preview", widgets: {} } },
        },
        {
          id: "s-save",
          index: 3,
          title: "Save",
          rationale: "",
          action: { type: "add_node", node: { id: "n5", type: "SaveAudio", widgets: {} } },
        },
        {
          id: "c1",
          index: 4,
          title: "to denoise",
          rationale: "",
          action: { type: "connect", from: ["n1", 0], to: ["n2", 0], link_type: "AUDIO" },
        },
        {
          id: "c2",
          index: 5,
          title: "to norm",
          rationale: "",
          action: { type: "connect", from: ["n2", 0], to: ["n3", 0], link_type: "AUDIO" },
        },
        {
          id: "c3",
          index: 6,
          title: "to preview",
          rationale: "",
          action: { type: "connect", from: ["n3", 0], to: ["n4", 0], link_type: "AUDIO" },
        },
        {
          id: "c4",
          index: 7,
          title: "to save",
          rationale: "",
          action: { type: "connect", from: ["n3", 0], to: ["n5", 0], link_type: "AUDIO" },
        },
      ],
    };
    const { nodes } = projectCreativeGhosts(session, withNote, {});
    const denoise = nodes.find((n) => n.id === "__ghost__s-denoise")!;
    const norm = nodes.find((n) => n.id === "__ghost__s-norm")!;
    const preview = nodes.find((n) => n.id === "__ghost__s-preview")!;
    const save = nodes.find((n) => n.id === "__ghost__s-save")!;
    expect(denoise.position.y).toBe(140);
    expect(norm.position.y).toBe(140);
    expect(preview.position.y).toBe(140 - FLOW_ROW);
    expect(save.position.y).toBe(140 + FLOW_ROW);
    expect(denoise.position.x).toBeLessThan(norm.position.x);
    expect(norm.position.x).toBeLessThan(preview.position.x);
    expect(preview.position.x).toBe(save.position.x);
  });

  it("keeps Denoise→Normalize on the lane even if both attach to LoadAudio", () => {
    const withNote: Workflow = {
      ...emptyWorkflow,
      nodes: [
        { id: "note", type: "Note", pos: { x: 0, y: 0 }, widgets: { text: "hint" } },
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 140 }, widgets: {} },
      ],
    };
    // Claude sometimes wires both hops from LoadAudio — must not fan ±Y.
    const session: CreativeTabSession = {
      goal: "grow",
      notes: null,
      cursor: 0,
      planning: false,
      steps: [
        {
          id: "s-denoise",
          index: 0,
          title: "Denoise",
          rationale: "",
          action: { type: "add_node", node: { id: "n2", type: "Denoise", widgets: {} } },
        },
        {
          id: "s-norm",
          index: 1,
          title: "Normalize",
          rationale: "",
          action: { type: "add_node", node: { id: "n3", type: "Normalize", widgets: {} } },
        },
        {
          id: "c1",
          index: 2,
          title: "to denoise",
          rationale: "",
          action: { type: "connect", from: ["n1", 0], to: ["n2", 0], link_type: "AUDIO" },
        },
        {
          id: "c2",
          index: 3,
          title: "to norm",
          rationale: "",
          action: { type: "connect", from: ["n1", 0], to: ["n3", 0], link_type: "AUDIO" },
        },
      ],
    };
    const { nodes } = projectCreativeGhosts(session, withNote, {});
    const denoise = nodes.find((n) => n.id === "__ghost__s-denoise")!;
    const norm = nodes.find((n) => n.id === "__ghost__s-norm")!;
    expect(denoise.position.y).toBe(140);
    expect(norm.position.y).toBe(140);
    expect(denoise.position.x).toBeLessThan(norm.position.x);
  });

  it("fans Preview above and SaveAudio below from the same parent", () => {
    const withNote: Workflow = {
      ...emptyWorkflow,
      nodes: [
        { id: "note", type: "Note", pos: { x: 0, y: 0 }, widgets: { text: "hint" } },
        { id: "n1", type: "LoadAudio", pos: { x: 0, y: 140 }, widgets: {} },
      ],
    };
    const session: CreativeTabSession = {
      goal: "grow",
      notes: null,
      cursor: 0,
      planning: false,
      steps: [
        {
          id: "s-denoise",
          index: 0,
          title: "Denoise",
          rationale: "",
          action: { type: "add_node", node: { id: "n2", type: "Denoise", widgets: {} } },
        },
        {
          id: "s-preview",
          index: 1,
          title: "Preview",
          rationale: "",
          action: { type: "add_node", node: { id: "n3", type: "Preview", widgets: {} } },
        },
        {
          id: "s-save",
          index: 2,
          title: "Save",
          rationale: "",
          action: { type: "add_node", node: { id: "n4", type: "SaveAudio", widgets: {} } },
        },
        {
          id: "c1",
          index: 3,
          title: "to denoise",
          rationale: "",
          action: { type: "connect", from: ["n1", 0], to: ["n2", 0], link_type: "AUDIO" },
        },
        {
          id: "c2",
          index: 4,
          title: "to preview",
          rationale: "",
          action: { type: "connect", from: ["n2", 0], to: ["n3", 0], link_type: "AUDIO" },
        },
        {
          id: "c3",
          index: 5,
          title: "to save",
          rationale: "",
          action: { type: "connect", from: ["n2", 0], to: ["n4", 0], link_type: "AUDIO" },
        },
      ],
    };
    const { nodes } = projectCreativeGhosts(session, withNote, {});
    const denoise = nodes.find((n) => n.id === "__ghost__s-denoise")!;
    const preview = nodes.find((n) => n.id === "__ghost__s-preview")!;
    const save = nodes.find((n) => n.id === "__ghost__s-save")!;
    expect(denoise.position.y).toBe(140);
    expect(preview.position.y).toBe(140 - FLOW_ROW);
    expect(save.position.y).toBe(140 + FLOW_ROW);
    expect(preview.position.x).toBe(save.position.x);
    expect(preview.position.x).toBeGreaterThan(denoise.position.x);
  });
});
