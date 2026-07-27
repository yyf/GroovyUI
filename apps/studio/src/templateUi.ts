import type { TemplateListItem } from "./api";

/** Bundled templates shown in the workflow template picker (alphabetical by title in UI). */
export const FEATURED_BUNDLED_TEMPLATE_IDS = [
  "ace-step-1.5",
  "diarize-and-transcribe",
  "hello-groovy",
  "podcast-denoise",
  "prompt-tts-modular",
  "stable-audio",
  "stem-split-vocals",
  "text-to-music",
  "transcribe-and-regenerate",
  "transcribe-dialogue",
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
