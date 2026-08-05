import type { TemplateListItem } from "./api";

/** Bundled templates shown in the workflow template picker (alphabetical by title in UI). */
export const FEATURED_BUNDLED_TEMPLATE_IDS = [
  "ace-step-1.5",
  "extract-lyrics-to-music-with-ace-step",
  "transcribe-and-diarize",
  "hello-groovy",
  "podcast-denoise",
  "prompt-modular-synth",
  "modular-generative-rack",
  "rave-timbre-transfer",
  "song-cover-remix",
  "stable-audio",
  "stem-separation",
  "text-to-music",
  "transcribe-and-regenerate",
  "transcribe-dialogue",
  "isolate-vocals-to-transcribe",
  "isolate-vocals-to-voice-convert",
  "localize-dialogue-a-to-b",
  "voice-cloning",
] as const;

const featuredBundledIds = new Set<string>(FEATURED_BUNDLED_TEMPLATE_IDS);

/** Hide non-featured bundled templates from the studio UI; user templates always show. */
export function templatesVisibleInUi(
  templates: TemplateListItem[],
  selectedId?: string,
): TemplateListItem[] {
  return templates
    .filter(
      (template) =>
        template.source === "user" ||
        featuredBundledIds.has(template.id) ||
        template.id === selectedId,
    )
    .sort((a, b) => {
      if (a.source === "user" && b.source !== "user") return 1;
      if (b.source === "user" && a.source !== "user") return -1;
      return a.title.localeCompare(b.title, undefined, { sensitivity: "base" });
    });
}
