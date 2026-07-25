import type { TemplateListItem } from "./api";

/** Bundled templates shown in the workflow template picker (hero demos first). */
export const FEATURED_BUNDLED_TEMPLATE_IDS = [
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
] as const;

const featuredBundledIds = new Set<string>(FEATURED_BUNDLED_TEMPLATE_IDS);

/** Hide non-featured bundled templates from the studio UI; user templates always show. */
export function templatesVisibleInUi(
  templates: TemplateListItem[],
  selectedId?: string,
): TemplateListItem[] {
  const featuredOrder = new Map<string, number>(
    FEATURED_BUNDLED_TEMPLATE_IDS.map((id, index) => [id, index]),
  );
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
      const aRank = featuredOrder.get(a.id) ?? 999;
      const bRank = featuredOrder.get(b.id) ?? 999;
      if (aRank !== bRank) return aRank - bRank;
      return a.title.localeCompare(b.title);
    });
}
