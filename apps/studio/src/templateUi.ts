import type { TemplateListItem } from "./api";

/** Bundled templates shown in the workflow template picker (general / high-demand starters). */
export const FEATURED_BUNDLED_TEMPLATE_IDS = [
  "hello-groovy",
  "podcast-denoise",
  "stem-split-vocals",
  "transcribe-and-regenerate",
] as const;

const featuredBundledIds = new Set<string>(FEATURED_BUNDLED_TEMPLATE_IDS);

/** Hide non-featured bundled templates from the studio UI; user templates always show. */
export function templatesVisibleInUi(
  templates: TemplateListItem[],
  selectedId?: string,
): TemplateListItem[] {
  return templates.filter(
    (template) =>
      template.source === "user" ||
      featuredBundledIds.has(template.id) ||
      template.id === selectedId,
  );
}
