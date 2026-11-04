import { describe, expect, it } from "vitest";
import { alignTextDiff, computeWerPercent, normalizeText } from "./textCompare";

describe("normalizeText", () => {
  it("lowercases and strips punctuation", () => {
    expect(normalizeText("Hello, World!")).toBe("hello world");
  });
});

describe("alignTextDiff", () => {
  it("marks identical strings as equal", () => {
    const result = alignTextDiff("one two three", "one two three");
    expect(result.werPercent).toBe(0);
    expect(result.spansA.every((s) => s.op === "equal")).toBe(true);
    expect(result.spansB.every((s) => s.op === "equal")).toBe(true);
  });

  it("highlights substitutions on original tokens", () => {
    const result = alignTextDiff("the cat sat", "the dog sat");
    expect(result.counts.substitutions).toBe(1);
    expect(result.spansA.find((s) => s.op === "replace")?.text).toBe("cat");
    expect(result.spansB.find((s) => s.op === "replace")?.text).toBe("dog");
    expect(result.werPercent).toBeCloseTo(33.33, 1);
  });

  it("highlights deletions and insertions", () => {
    const deleted = alignTextDiff("alpha beta gamma", "alpha gamma");
    expect(deleted.counts.deletions).toBe(1);
    expect(deleted.spansA.some((s) => s.op === "delete" && s.text === "beta")).toBe(true);

    const inserted = alignTextDiff("alpha gamma", "alpha beta gamma");
    expect(inserted.counts.insertions).toBe(1);
    expect(inserted.spansB.some((s) => s.op === "insert" && s.text === "beta")).toBe(true);
  });

  it("ignores case/punct for WER but keeps original display", () => {
    const result = alignTextDiff("Hello, World.", "hello world");
    expect(result.werPercent).toBe(0);
    expect(result.spansA.map((s) => s.text)).toEqual(["Hello,", "World."]);
    expect(result.spansB.map((s) => s.text)).toEqual(["hello", "world"]);
  });
});

describe("computeWerPercent", () => {
  it("matches perfect and total-mismatch cases", () => {
    expect(computeWerPercent("a b c", "a b c")).toBe(0);
    expect(computeWerPercent("a b c", "x y z")).toBe(100);
  });
});
