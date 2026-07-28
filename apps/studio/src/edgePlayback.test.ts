import { describe, expect, it } from "vitest";
import type { Workflow } from "./types";
import {
  nextActiveEdgeIds,
  resolveEdgePlaybackTarget,
  type EdgePlaybackEvent,
} from "./edgePlayback";

function chainWorkflow(): Workflow {
  return {
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: "wf",
    metadata: { title: "Chain" },
    nodes: [
      { id: "n1", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
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

function diamondWorkflow(): Workflow {
  return {
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: "wf",
    metadata: { title: "Diamond" },
    nodes: [
      { id: "src", type: "LoadAudio", pos: { x: 0, y: 0 }, widgets: {} },
      { id: "a", type: "Normalize", pos: { x: 200, y: -40 }, widgets: {} },
      { id: "b", type: "Normalize", pos: { x: 200, y: 40 }, widgets: {} },
      { id: "mix", type: "Mix", pos: { x: 400, y: 0 }, widgets: {} },
    ],
    links: [
      { id: "l-src-a", from: ["src", 0], to: ["a", 0], type: "AUDIO" },
      { id: "l-src-b", from: ["src", 0], to: ["b", 0], type: "AUDIO" },
      { id: "l-a-mix", from: ["a", 0], to: ["mix", 0], type: "AUDIO" },
      { id: "l-b-mix", from: ["b", 0], to: ["mix", 1], type: "AUDIO" },
    ],
    groups: [],
  };
}

describe("nextActiveEdgeIds", () => {
  it("turns animation on only for the upstream path on play", () => {
    const ids = nextActiveEdgeIds({
      event: "play",
      workflow: chainWorkflow(),
      targetNodeId: "n3",
    });
    expect([...ids].sort()).toEqual(["l1", "l2"]);
  });

  it("animates only the path into a mid-chain audition target", () => {
    const ids = nextActiveEdgeIds({
      event: "play",
      workflow: chainWorkflow(),
      targetNodeId: "n2",
    });
    expect([...ids]).toEqual(["l1"]);
  });

  it("includes every branch on a diamond into Mix", () => {
    const ids = nextActiveEdgeIds({
      event: "play",
      workflow: diamondWorkflow(),
      targetNodeId: "mix",
    });
    expect([...ids].sort()).toEqual(["l-a-mix", "l-b-mix", "l-src-a", "l-src-b"]);
  });

  it.each<EdgePlaybackEvent>(["pause", "ended", "playback_failed", "preview_cleared"])(
    "clears animation on %s even when a target is still selected",
    (event) => {
      const ids = nextActiveEdgeIds({
        event,
        workflow: chainWorkflow(),
        targetNodeId: "n3",
      });
      expect(ids.size).toBe(0);
    },
  );

  it("clears on pause/ended with no selection (avoids stuck animated wires)", () => {
    for (const event of ["pause", "ended"] as const) {
      expect(
        nextActiveEdgeIds({
          event,
          workflow: chainWorkflow(),
          targetNodeId: null,
        }).size,
      ).toBe(0);
    }
  });

  it("does not animate on play without a workflow", () => {
    expect(
      nextActiveEdgeIds({
        event: "play",
        workflow: null,
        targetNodeId: "n3",
      }).size,
    ).toBe(0);
  });

  it("does not animate on play without a target node (failed eager path)", () => {
    expect(
      nextActiveEdgeIds({
        event: "play",
        workflow: chainWorkflow(),
        targetNodeId: null,
      }).size,
    ).toBe(0);
  });

  it("returns empty for an unknown target rather than animating all edges", () => {
    expect(
      nextActiveEdgeIds({
        event: "play",
        workflow: chainWorkflow(),
        targetNodeId: "missing",
      }).size,
    ).toBe(0);
  });

  it("keeps play and failure mutually exclusive (autoplay blocked)", () => {
    const workflow = chainWorkflow();
    // Correct model: no successful play → no animation; failure always clears.
    expect(
      nextActiveEdgeIds({
        event: "playback_failed",
        workflow,
        targetNodeId: "n3",
      }).size,
    ).toBe(0);
  });

  it("survives pause-then-play (blob load pauses before play)", () => {
    const workflow = chainWorkflow();
    const afterPause = nextActiveEdgeIds({
      event: "pause",
      workflow,
      targetNodeId: "n3",
    });
    expect(afterPause.size).toBe(0);
    const afterPlay = nextActiveEdgeIds({
      event: "play",
      workflow,
      targetNodeId: "n3",
    });
    expect([...afterPlay].sort()).toEqual(["l1", "l2"]);
  });
});

describe("resolveEdgePlaybackTarget", () => {
  it("prefers audition target over selection (race before selection commits)", () => {
    expect(resolveEdgePlaybackTarget("audition", "selected")).toBe("audition");
  });

  it("falls back to selection when audition target was not set", () => {
    expect(resolveEdgePlaybackTarget(null, "selected")).toBe("selected");
  });

  it("returns null when neither is set", () => {
    expect(resolveEdgePlaybackTarget(null, null)).toBeNull();
  });
});
