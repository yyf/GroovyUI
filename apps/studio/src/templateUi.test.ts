import { describe, expect, it } from "vitest";
import { templatesVisibleInUi } from "./templateUi";
import type { TemplateListItem } from "./api";

function bundled(id: string): TemplateListItem {
  return { id, title: id, description: "", source: "bundled" };
}

function user(id: string): TemplateListItem {
  return { id, title: id, description: "", source: "user" };
}

describe("templatesVisibleInUi", () => {
  const allBundled = [
    bundled("hello-groovy"),
    bundled("podcast-denoise"),
    bundled("stem-split-vocals"),
    bundled("transcribe-dialogue"),
    bundled("transcribe-and-regenerate"),
    bundled("text-to-music"),
  ];

  it("shows only featured bundled templates", () => {
    const visible = templatesVisibleInUi(allBundled);
    expect(visible.map((t) => t.id)).toEqual([
      "podcast-denoise",
      "stem-split-vocals",
      "transcribe-and-regenerate",
      "transcribe-dialogue",
      "hello-groovy",
    ]);
  });

  it("always shows user templates", () => {
    const visible = templatesVisibleInUi([...allBundled, user("my-export")]);
    expect(visible.some((t) => t.id === "my-export")).toBe(true);
    expect(visible.some((t) => t.id === "text-to-music")).toBe(false);
  });

  it("keeps the active bundled template visible when it is not featured", () => {
    const visible = templatesVisibleInUi(allBundled, "transcribe-dialogue");
    expect(visible.map((t) => t.id)).toContain("transcribe-dialogue");
    expect(visible.map((t) => t.id)).not.toContain("text-to-music");
  });
});
