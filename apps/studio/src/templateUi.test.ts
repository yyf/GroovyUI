import { describe, expect, it } from "vitest";
import {
  domainIdForTemplate,
  groupBundledTemplatesByDomain,
  templatesVisibleInUi,
} from "./templateUi";
import type { TemplateListItem } from "./api";

function bundled(id: string, title?: string): TemplateListItem {
  return { id, title: title ?? id, description: "", source: "bundled" };
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
    bundled("denoise-diarize-transcribe"),
    bundled("song-cover-remix"),
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
    bundled("localize-dialogue-a-to-b"),
    bundled("modular-generative-rack"),
    bundled("rave-timbre-transfer"),
    bundled("compare-whisper-sizes"),
    bundled("script-to-vo-master"),
    bundled("neural-modular-rack"),
    bundled("self-playing-neural-rack"),
    bundled("karaoke-guide-vocal"),
    bundled("instrumental-tts-dub"),
    bundled("melody-to-modular-synth"),
    bundled("compare-stemmers"),
    bundled("stem-lyrics-to-ace"),
  ];

  it("shows featured bundled templates sorted by title", () => {
    const visible = templatesVisibleInUi(allBundled);
    expect(visible.map((t) => t.id)).toEqual([
      "ace-step-1.5",
      "authenticity-check",
      "compare-stemmers",
      "compare-whisper-sizes",
      "extract-lyrics-to-music-with-ace-step",
      "hello-groovy",
      "instrumental-tts-dub",
      "isolate-vocals-to-transcribe",
      "isolate-vocals-to-voice-convert",
      "karaoke-guide-vocal",
      "localize-dialogue-a-to-b",
      "melody-to-modular-synth",
      "modular-generative-rack",
      "neural-modular-rack",
      "podcast-denoise",
      "prompt-modular-synth",
      "rave-timbre-transfer",
      "script-to-vo-master",
      "song-cover-remix",
      "stable-audio",
      "stem-lyrics-to-ace",
      "stem-separation",
      "text-to-music",
      "transcribe-and-diarize",
      "transcribe-and-regenerate",
      "transcribe-dialogue",
      "voice-cloning",
    ]);
  });

  it("hides denoise-diarize-transcribe unless it is the active selection", () => {
    expect(templatesVisibleInUi(allBundled).map((t) => t.id)).not.toContain(
      "denoise-diarize-transcribe",
    );
    expect(
      templatesVisibleInUi(allBundled, "denoise-diarize-transcribe").map((t) => t.id),
    ).toContain("denoise-diarize-transcribe");
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

  it("hides self-playing-neural-rack unless it is the active selection", () => {
    expect(templatesVisibleInUi(allBundled).map((t) => t.id)).not.toContain(
      "self-playing-neural-rack",
    );
    expect(
      templatesVisibleInUi(allBundled, "self-playing-neural-rack").map((t) => t.id),
    ).toContain("self-playing-neural-rack");
  });

  it("always shows user templates", () => {
    const visible = templatesVisibleInUi([...allBundled, user("my-export")]);
    expect(visible.some((t) => t.id === "my-export")).toBe(true);
    expect(visible.some((t) => t.id === "authenticity-check")).toBe(true);
    expect(visible.some((t) => t.id === "simple-fm-synth")).toBe(false);
  });

  it("keeps a non-featured bundled template visible when it is the active selection", () => {
    const visible = templatesVisibleInUi(allBundled, "simple-fm-synth");
    expect(visible.map((t) => t.id)).toContain("simple-fm-synth");
  });
});

describe("groupBundledTemplatesByDomain", () => {
  it("groups featured templates into domain submenus", () => {
    const visible = templatesVisibleInUi([
      bundled("hello-groovy", "Hello GroovyUI"),
      bundled("podcast-denoise", "Podcast Denoise"),
      bundled("stem-separation", "Stem Separation"),
      bundled("text-to-music", "Text to Music"),
      bundled("voice-cloning", "Voice Cloning"),
      bundled("modular-generative-rack", "Modular Generative Rack"),
      bundled("compare-stemmers", "Compare Stemmers"),
      bundled("authenticity-check", "Authenticity Check"),
      user("my-patch"),
    ]);
    const groups = groupBundledTemplatesByDomain(visible);
    expect(groups.map((g) => g.domain.id)).toEqual([
      "start",
      "speech",
      "voice",
      "stems",
      "generate",
      "modular",
      "compare",
      "trust",
    ]);
    expect(groups.find((g) => g.domain.id === "speech")?.templates.map((t) => t.id)).toEqual([
      "podcast-denoise",
    ]);
    expect(groups.every((g) => g.templates.every((t) => t.source !== "user"))).toBe(true);
  });

  it("puts unknown bundled ids in Other", () => {
    expect(domainIdForTemplate("ab-compare-demo")).toBe("other");
    const groups = groupBundledTemplatesByDomain([
      bundled("ab-compare-demo", "A/B Compare Demo"),
    ]);
    expect(groups).toEqual([
      {
        domain: { id: "other", label: "Other" },
        templates: [bundled("ab-compare-demo", "A/B Compare Demo")],
      },
    ]);
  });

  it("places authenticity-check in Trust", () => {
    expect(domainIdForTemplate("authenticity-check")).toBe("trust");
  });

  it("places self-playing-neural-rack in Modular", () => {
    expect(domainIdForTemplate("self-playing-neural-rack")).toBe("modular");
  });

  it("places neural-modular-rack in Modular", () => {
    expect(domainIdForTemplate("neural-modular-rack")).toBe("modular");
  });
});
