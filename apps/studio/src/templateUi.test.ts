import { describe, expect, it } from "vitest";
import {
  domainIdForTemplate,
  groupBundledTemplatesByDomain,
  isNodeVisibleInStudio,
  STANDARD_MODE_NODE_TYPES,
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
    bundled("ambisonic-trajectory-demo"),
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

  it("shows only ISMIR demo templates in standard mode", () => {
    const visible = templatesVisibleInUi([
      ...allBundled,
      bundled("empty-canvas", "Empty Canvas"),
    ]);
    expect(visible.map((t) => t.id)).toEqual([
      "empty-canvas",
      "hello-groovy",
      "isolate-vocals-to-transcribe",
      "podcast-denoise",
      "prompt-modular-synth",
    ]);
  });

  it("keeps Immersive templates off the standard picker (⌘⇧D only)", () => {
    const withImmersive = [
      ...allBundled,
      bundled("stereo-to-binaural"),
      bundled("stereo-to-atmos-bed"),
    ];
    const standard = templatesVisibleInUi(withImmersive);
    expect(standard.map((t) => t.id)).not.toContain("ambisonic-trajectory-demo");
    expect(standard.map((t) => t.id)).not.toContain("stereo-to-binaural");
    expect(standard.map((t) => t.id)).not.toContain("stereo-to-atmos-bed");
    expect(groupBundledTemplatesByDomain(standard).map((g) => g.domain.id)).not.toContain(
      "immersive",
    );

    // Same as other featured-only templates: active selection stays visible in standard mode.
    const withSelection = templatesVisibleInUi(
      withImmersive,
      "ambisonic-trajectory-demo",
      false,
    );
    expect(withSelection.map((t) => t.id)).toContain("ambisonic-trajectory-demo");

    const featured = templatesVisibleInUi(withImmersive, undefined, true);
    expect(featured.map((t) => t.id)).toContain("ambisonic-trajectory-demo");
    expect(featured.map((t) => t.id)).toContain("stereo-to-binaural");
    expect(featured.map((t) => t.id)).toContain("stereo-to-atmos-bed");
    expect(groupBundledTemplatesByDomain(featured).map((g) => g.domain.id)).toContain("immersive");
  });

  it("shows featured bundled templates in studio dev mode", () => {
    const visible = templatesVisibleInUi(allBundled, undefined, true);
    expect(visible.map((t) => t.id)).toEqual([
      "ace-step-1.5",
      "ambisonic-trajectory-demo",
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
    expect(withTitles.map((t) => t.title)).toEqual(["Hello GroovyUI", "Podcast Denoise"]);
  });

  it("hides simple-fm-synth unless it is the active selection", () => {
    expect(templatesVisibleInUi(allBundled).map((t) => t.id)).not.toContain("simple-fm-synth");
    expect(templatesVisibleInUi(allBundled, "simple-fm-synth").map((t) => t.id)).toContain(
      "simple-fm-synth",
    );
  });

  it("hides self-playing-neural-rack even when it is the active selection", () => {
    expect(templatesVisibleInUi(allBundled).map((t) => t.id)).not.toContain(
      "self-playing-neural-rack",
    );
    expect(
      templatesVisibleInUi(allBundled, "self-playing-neural-rack").map((t) => t.id),
    ).not.toContain("self-playing-neural-rack");
    expect(
      templatesVisibleInUi(allBundled, "self-playing-neural-rack", true).map((t) => t.id),
    ).not.toContain("self-playing-neural-rack");
  });

  it("hides melody-to-modular-synth even when it is the active selection", () => {
    expect(templatesVisibleInUi(allBundled).map((t) => t.id)).not.toContain(
      "melody-to-modular-synth",
    );
    expect(
      templatesVisibleInUi(allBundled, "melody-to-modular-synth").map((t) => t.id),
    ).not.toContain("melody-to-modular-synth");
    expect(
      templatesVisibleInUi(allBundled, "melody-to-modular-synth", true).map((t) => t.id),
    ).not.toContain("melody-to-modular-synth");
  });

  it("always shows user templates", () => {
    const visible = templatesVisibleInUi([...allBundled, user("my-export")]);
    expect(visible.some((t) => t.id === "my-export")).toBe(true);
    expect(visible.some((t) => t.id === "hello-groovy")).toBe(true);
    expect(visible.some((t) => t.id === "authenticity-check")).toBe(false);
    expect(visible.some((t) => t.id === "simple-fm-synth")).toBe(false);
  });

  it("keeps a non-featured bundled template visible when it is the active selection", () => {
    const visible = templatesVisibleInUi(allBundled, "simple-fm-synth");
    expect(visible.map((t) => t.id)).toContain("simple-fm-synth");
  });

  it("keeps a featured-but-non-ISMIR template visible when selected in standard mode", () => {
    const visible = templatesVisibleInUi(allBundled, "stem-separation");
    expect(visible.map((t) => t.id)).toContain("stem-separation");
    expect(visible.map((t) => t.id)).toContain("hello-groovy");
  });
});

describe("groupBundledTemplatesByDomain", () => {
  it("groups featured templates into domain submenus", () => {
    const visible = templatesVisibleInUi(
      [
        bundled("empty-canvas", "Empty Canvas"),
        bundled("hello-groovy", "Hello GroovyUI"),
        bundled("podcast-denoise", "Podcast Denoise"),
        bundled("stem-separation", "Stem Separation"),
        bundled("text-to-music", "Text to Music"),
        bundled("voice-cloning", "Voice Cloning"),
        bundled("modular-generative-rack", "Modular Generative Rack"),
        bundled("compare-stemmers", "Compare Stemmers"),
        bundled("authenticity-check", "Authenticity Check"),
        user("my-patch"),
      ],
      undefined,
      true,
    );
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
    expect(groups.find((g) => g.domain.id === "start")?.templates.map((t) => t.id)).toEqual([
      "empty-canvas",
      "hello-groovy",
    ]);
    expect(groups.find((g) => g.domain.id === "speech")?.templates.map((t) => t.id)).toEqual([
      "podcast-denoise",
    ]);
    expect(groups.every((g) => g.templates.every((t) => t.source !== "user"))).toBe(true);
  });

  it("places empty-canvas and hello-groovy in Start", () => {
    expect(domainIdForTemplate("empty-canvas")).toBe("start");
    expect(domainIdForTemplate("hello-groovy")).toBe("start");
  });

  it("puts unknown bundled ids in Other", () => {
    expect(domainIdForTemplate("no-such-template")).toBe("other");
    const groups = groupBundledTemplatesByDomain([
      bundled("no-such-template", "Mystery Template"),
    ]);
    expect(groups).toEqual([
      {
        domain: { id: "other", label: "Other" },
        templates: [bundled("no-such-template", "Mystery Template")],
      },
    ]);
  });

  it("places sample-verify and ab-compare-demo in Compare", () => {
    expect(domainIdForTemplate("sample-verify")).toBe("compare");
    expect(domainIdForTemplate("ab-compare-demo")).toBe("compare");
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

  it("places prompt-modular-synth in Modular", () => {
    expect(domainIdForTemplate("prompt-modular-synth")).toBe("modular");
  });
});

describe("isNodeVisibleInStudio", () => {
  it("limits standard mode to ISMIR demo template nodes", () => {
    expect(isNodeVisibleInStudio("Denoise")).toBe(true);
    expect(isNodeVisibleInStudio("LoadAudio")).toBe(true);
    expect(isNodeVisibleInStudio("Mix")).toBe(false);
    expect(isNodeVisibleInStudio("GenerateAudio")).toBe(false);
    expect(STANDARD_MODE_NODE_TYPES).toContain("TTS");
  });

  it("shows all node types in studio dev mode", () => {
    expect(isNodeVisibleInStudio("Mix", true)).toBe(true);
    expect(isNodeVisibleInStudio("GenerateAudio", true)).toBe(true);
  });
});
