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
    bundled("stem-separation"),
    bundled("transcribe-dialogue"),
    bundled("transcribe-and-diarize"),
    bundled("cleanup-and-transcribe"),
    bundled("voice-cloning"),
    bundled("prompt-modular-synth"),
    bundled("simple-fm-synth"),
    bundled("ace-step-1.5"),
    bundled("extract-lyrics-to-music-with-ace-step"),
    bundled("stable-audio"),
    bundled("text-to-music"),
    bundled("karaoke-stems"),
    bundled("transcribe-and-regenerate"),
    bundled("authenticity-check"),
    bundled("isolate-vocals-to-transcribe"),
    bundled("isolate-vocals-to-voice-convert"),
  ];

  it("shows featured bundled templates sorted by title", () => {
    const visible = templatesVisibleInUi(allBundled);
    expect(visible.map((t) => t.id)).toEqual([
      "ace-step-1.5",
      "extract-lyrics-to-music-with-ace-step",
      "hello-groovy",
      "isolate-vocals-to-transcribe",
      "isolate-vocals-to-voice-convert",
      "podcast-denoise",
      "prompt-modular-synth",
      "stable-audio",
      "stem-separation",
      "text-to-music",
      "transcribe-and-diarize",
      "transcribe-and-regenerate",
      "transcribe-dialogue",
      "voice-cloning",
    ]);
  });

  it("sorts by display title, not id", () => {
    const withTitles = templatesVisibleInUi([
      { id: "hello-groovy", title: "Hello GroovyUI", description: "", source: "bundled" },
      { id: "ace-step-1.5", title: "Text to Music- ACE Step 1.5", description: "", source: "bundled" },
      { id: "podcast-denoise", title: "Podcast Denoise", description: "", source: "bundled" },
    ]);
    expect(withTitles.map((t) => t.title)).toEqual([
      "Hello GroovyUI",
      "Podcast Denoise",
      "Text to Music- ACE Step 1.5",
    ]);
  });

  it("hides simple-fm-synth unless it is the active selection", () => {
    expect(templatesVisibleInUi(allBundled).map((t) => t.id)).not.toContain("simple-fm-synth");
    expect(templatesVisibleInUi(allBundled, "simple-fm-synth").map((t) => t.id)).toContain(
      "simple-fm-synth",
    );
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
