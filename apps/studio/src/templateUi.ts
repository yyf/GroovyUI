import type { TemplateListItem } from "./api";

/** Bundled templates shown in the workflow template picker (alphabetical by title in UI). */
export const FEATURED_BUNDLED_TEMPLATE_IDS = [
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
  "modular-generative-rack",
  "podcast-denoise",
  "prompt-modular-synth",
  "rave-timbre-transfer",
  "sample-verify",
  "script-to-vo-master",
  "neural-modular-rack",
  "song-cover-remix",
  "stable-audio",
  "stem-lyrics-to-ace",
  "stem-separation",
  "text-to-music",
  "transcribe-and-diarize",
  "transcribe-and-regenerate",
  "transcribe-dialogue",
  "voice-cloning",
] as const;

/** Bundled templates that never appear in the picker, even if currently loaded. */
export const PICKER_HIDDEN_BUNDLED_TEMPLATE_IDS = [
  "melody-to-modular-synth",
  "self-playing-neural-rack",
] as const;

export type TemplateDomainId =
  | "start"
  | "speech"
  | "voice"
  | "stems"
  | "generate"
  | "modular"
  | "compare"
  | "trust"
  | "other";

export type TemplateDomain = {
  id: TemplateDomainId;
  label: string;
};

/** Picker domains — Hub/job-aligned, not phase numbers. */
export const TEMPLATE_DOMAINS: readonly TemplateDomain[] = [
  { id: "start", label: "Start" },
  { id: "speech", label: "Speech & Podcast" },
  { id: "voice", label: "Voice & VO" },
  { id: "stems", label: "Stems & Remix" },
  { id: "generate", label: "Generate Music" },
  { id: "modular", label: "Modular" },
  { id: "compare", label: "Compare" },
  { id: "trust", label: "Trust" },
  { id: "other", label: "Other" },
] as const;

/** Featured (and known) template → domain. Unknown featured IDs fall into Other. */
export const TEMPLATE_DOMAIN_BY_ID: Readonly<Record<string, TemplateDomainId>> = {
  "hello-groovy": "start",

  "podcast-denoise": "speech",
  "transcribe-dialogue": "speech",
  "transcribe-and-diarize": "speech",
  "cleanup-and-transcribe": "speech",
  "denoise-diarize-transcribe": "speech",
  "isolate-vocals-to-transcribe": "speech",
  "compare-whisper-sizes": "compare",
  "sample-verify": "compare",
  "ab-compare-demo": "compare",

  "voice-cloning": "voice",
  "script-to-vo-master": "voice",
  "localize-dialogue-a-to-b": "voice",
  "instrumental-tts-dub": "voice",
  "isolate-vocals-to-voice-convert": "voice",
  "prompt-modular-synth": "voice",

  "stem-separation": "stems",
  "karaoke-stems": "stems",
  "karaoke-guide-vocal": "stems",
  "song-cover-remix": "stems",
  "rave-timbre-transfer": "stems",
  "stem-lyrics-to-ace": "stems",
  "compare-stemmers": "compare",

  "text-to-music": "generate",
  "stable-audio": "generate",
  "ace-step-1.5": "generate",
  "extract-lyrics-to-music-with-ace-step": "generate",
  "transcribe-and-regenerate": "generate",

  "modular-generative-rack": "modular",
  "melody-to-modular-synth": "modular",
  "neural-modular-rack": "modular",
  "self-playing-neural-rack": "modular",
  "simple-fm-synth": "modular",

  "authenticity-check": "trust",
};

const featuredBundledIds = new Set<string>(FEATURED_BUNDLED_TEMPLATE_IDS);
const pickerHiddenBundledIds = new Set<string>(PICKER_HIDDEN_BUNDLED_TEMPLATE_IDS);

export function domainIdForTemplate(templateId: string): TemplateDomainId {
  return TEMPLATE_DOMAIN_BY_ID[templateId] ?? "other";
}

/** Hide non-featured bundled templates from the studio UI; user templates always show. */
export function templatesVisibleInUi(
  templates: TemplateListItem[],
  selectedId?: string,
): TemplateListItem[] {
  return templates
    .filter((template) => {
      if (template.source === "user") return true;
      if (pickerHiddenBundledIds.has(template.id)) return false;
      return featuredBundledIds.has(template.id) || template.id === selectedId;
    })
    .sort((a, b) => {
      if (a.source === "user" && b.source !== "user") return 1;
      if (b.source === "user" && a.source !== "user") return -1;
      return a.title.localeCompare(b.title, undefined, { sensitivity: "base" });
    });
}

export type TemplateDomainGroup = {
  domain: TemplateDomain;
  templates: TemplateListItem[];
};

/** Group visible bundled templates into domain menus (empty domains omitted). */
export function groupBundledTemplatesByDomain(
  templates: TemplateListItem[],
): TemplateDomainGroup[] {
  const bundled = templates.filter((template) => template.source !== "user");
  const byDomain = new Map<TemplateDomainId, TemplateListItem[]>();
  for (const template of bundled) {
    const domainId = domainIdForTemplate(template.id);
    const list = byDomain.get(domainId) ?? [];
    list.push(template);
    byDomain.set(domainId, list);
  }
  for (const list of byDomain.values()) {
    list.sort((a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: "base" }));
  }
  return TEMPLATE_DOMAINS.map((domain) => ({
    domain,
    templates: byDomain.get(domain.id) ?? [],
  })).filter((group) => group.templates.length > 0);
}
