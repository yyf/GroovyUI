import { describe, expect, it } from "vitest";
import { rankCanvasFindHits } from "./canvasNodeFind";

const hits = [
  { id: "n14", name: "Osc" },
  { id: "n19", name: "VCA" },
  { id: "n29", name: "Mix" },
  { id: "n44", name: "Filter" },
  { id: "n28", name: "Mix" },
];

describe("rankCanvasFindHits", () => {
  it("keeps canvas order when the query is empty", () => {
    expect(rankCanvasFindHits(hits, "  ")).toEqual(hits);
  });

  it("matches node name case-insensitively", () => {
    expect(rankCanvasFindHits(hits, "mix").map((hit) => hit.id)).toEqual(["n29", "n28"]);
  });

  it("matches node id", () => {
    expect(rankCanvasFindHits(hits, "n44")).toEqual([{ id: "n44", name: "Filter" }]);
  });

  it("prefers exact and prefix name matches", () => {
    const ranked = rankCanvasFindHits(
      [
        { id: "a", name: "FilterLP" },
        { id: "b", name: "Filter" },
        { id: "c", name: "Bandpass" },
      ],
      "filter",
    );
    expect(ranked.map((hit) => hit.id)).toEqual(["b", "a"]);
  });
});
