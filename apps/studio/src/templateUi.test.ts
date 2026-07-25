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
    bundled("diarize-and-transcribe"),
    bundled("cleanup-and-transcribe"),
    bundled("tts-greeting"),
    bundled("voice-cloning"),
    bundled("prompt-tts-modular"),
    bundled("simple-fm-synth"),
    bundled("text-to-music"),
    bundled("karaoke-stems"),
    bundled("transcribe-and-regenerate"),
    bundled("authenticity-check"),
  ];

  it("shows featured bundled templates in portfolio order", () => {
    const visible = templatesVisibleInUi(allBundled);
    expect(visible.map((t) => t.id)).toEqual([
      "podcast-denoise",
      "stem-split-vocals",
      "transcribe-dialogue",
      "diarize-and-transcribe",
      "tts-greeting",
      "voice-cloning",
      "prompt-tts-modular",
      "simple-fm-synth",
      "text-to-music",
      "transcribe-and-regenerate",
      "hello-groovy",
    ]);
  });

  it("always shows user templates", () => {
    const visible = templatesVisibleInUi([...allBundled, user("my-export")]);
    expect(visible.some((t) => t.id === "my-export")).toBe(true);
    expect(visible.some((t) => t.id === "authenticity-check")).toBe(false);
  });

  it("keeps the active bundled template visible when it is not featured", () => {
    const visible = templatesVisibleInUi(allBundled, "authenticity-check");
    expect(visible.map((t) => t.id)).toContain("authenticity-check");
  });
});
