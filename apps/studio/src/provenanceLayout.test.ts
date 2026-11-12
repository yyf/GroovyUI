import { describe, expect, it } from "vitest";
import {
  contributionKind,
  contributionKindLabel,
  glanceFromLineage,
  layoutProvenanceGraph,
  lineageFromEntry,
} from "./provenanceLayout";
import type { ProvenanceEntry, ProvenanceLineage } from "./types";

describe("contribution labels", () => {
  it("maps classes to glanceable kinds", () => {
    expect(contributionKind("human_recorded")).toBe("human");
    expect(contributionKind("ai_transformed")).toBe("ai");
    expect(contributionKindLabel("ai_generated")).toBe("AI generated");
    expect(contributionKindLabel("human_edited")).toBe("Human edit");
  });
});

describe("lineageFromEntry", () => {
  it("prefers API lineage DAG", () => {
    const lineage: ProvenanceLineage = {
      root_cache_id: "out",
      nodes: [
        { cache_id: "src", node: { node_id: "n1", node_type: "LoadAudio" } },
        { cache_id: "out", node: { node_id: "n2", node_type: "Preview" } },
      ],
      edges: [{ from_cache_id: "src", to_cache_id: "out" }],
    };
    const entry: ProvenanceEntry = {
      node_id: "n2",
      cache_id: "out",
      chain: [],
      lineage,
      disclosure: "ok",
    };
    expect(lineageFromEntry(entry)?.root_cache_id).toBe("out");
    expect(lineageFromEntry(entry)?.edges).toHaveLength(1);
  });

  it("falls back to linear chain when lineage missing", () => {
    const entry: ProvenanceEntry = {
      node_id: "n3",
      cache_id: "c3",
      chain: [
        {
          cache_id: "c3",
          node: { node_id: "n3", node_type: "Preview" },
          contribution: { class: "human_edited" },
        },
        {
          cache_id: "c2",
          node: { node_id: "n2", node_type: "Denoise" },
          contribution: { class: "ai_transformed" },
          models: [{ registry_id: "deepfilternet-v3", role: "base" }],
        },
        {
          cache_id: "c1",
          node: { node_id: "n1", node_type: "LoadAudio" },
          contribution: { class: "human_recorded" },
        },
      ],
      disclosure: "AI processing was applied.",
    };
    const lineage = lineageFromEntry(entry);
    expect(lineage?.root_cache_id).toBe("c3");
    expect(lineage?.edges).toEqual([
      { from_cache_id: "c2", to_cache_id: "c3" },
      { from_cache_id: "c1", to_cache_id: "c2" },
    ]);
  });
});

describe("layoutProvenanceGraph", () => {
  it("stacks a linear chain top→bottom for glanceable recipe reading", () => {
    const lineage: ProvenanceLineage = {
      root_cache_id: "c3",
      nodes: [
        {
          cache_id: "c1",
          node: { node_id: "n1", node_type: "LoadAudio" },
          contribution: { class: "human_recorded" },
        },
        {
          cache_id: "c2",
          node: { node_id: "n2", node_type: "Denoise" },
          contribution: { class: "ai_transformed" },
          models: [{ registry_id: "deepfilternet-v3" }],
        },
        {
          cache_id: "c3",
          node: { node_id: "n3", node_type: "Preview" },
          contribution: { class: "human_edited" },
        },
      ],
      edges: [
        { from_cache_id: "c1", to_cache_id: "c2" },
        { from_cache_id: "c2", to_cache_id: "c3" },
      ],
    };
    const layout = layoutProvenanceGraph(lineage);
    const byId = Object.fromEntries(layout.nodes.map((n) => [n.cacheId, n]));
    expect(layout.orientation).toBe("vertical");
    expect(byId.c1.y).toBeLessThan(byId.c2.y);
    expect(byId.c2.y).toBeLessThan(byId.c3.y);
    expect(byId.c1.isSource).toBe(true);
    expect(byId.c3.isRoot).toBe(true);
    expect(byId.c2.kind).toBe("ai");
    expect(byId.c2.modelSummary).toContain("deepfilternet");
    expect(layout.glance.label).toContain("human");
    expect(layout.glance.label).toContain("AI");
  });

  it("places branching sources above a mix output", () => {
    const lineage: ProvenanceLineage = {
      root_cache_id: "mix",
      nodes: [
        {
          cache_id: "a",
          node: { node_id: "n1", node_type: "LoadAudio" },
          contribution: { class: "human_recorded" },
        },
        {
          cache_id: "b",
          node: { node_id: "n2", node_type: "TTS" },
          contribution: { class: "ai_generated" },
        },
        {
          cache_id: "mix",
          node: { node_id: "n3", node_type: "Mix" },
          contribution: { class: "mixed" },
        },
      ],
      edges: [
        { from_cache_id: "a", to_cache_id: "mix" },
        { from_cache_id: "b", to_cache_id: "mix" },
      ],
    };
    const glance = glanceFromLineage(lineage);
    expect(glance.hasBranching).toBe(true);
    expect(glance.humanPercent + glance.aiPercent).toBe(100);

    const layout = layoutProvenanceGraph(lineage);
    const byId = Object.fromEntries(layout.nodes.map((n) => [n.cacheId, n]));
    expect(byId.a.y).toBeLessThan(byId.mix.y);
    expect(byId.b.y).toBeLessThan(byId.mix.y);
    expect(layout.edges).toHaveLength(2);
  });
});
