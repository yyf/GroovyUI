import type { TemplateListItem } from "./api";

/**
 * Bundled templates shown in standard (demo) mode — ISMIR 2026 LBD hero set.
 * Files live in repo `templates/`. Studio dev mode reveals the full featured picker list
 * (local `docs/internal/templates/` when present) and full node palette.
 */
export const STANDARD_BUNDLED_TEMPLATE_IDS = [
  "ace-step-1.5-sft",
  "ace-step-dual-lora-ab",
  "asr-benchmark-wer-cer",
  "demucs-vs-openunmix",
  "empty-canvas",
  "hello-groovy",
  "isolate-vocals-to-transcribe",
  "isolate-vocals-to-transcribe-translate",
  "moving-clouds",
  "podcast-denoise",
  "prompt-modular-synth",
  "rutt-etra-scan",
  "shepard-tone",
  "text-to-midi",
  "text-to-video",
  "tts-emotion-edit",
  "watermark-embed-detect",
] as const;

/** Bundled templates shown in the workflow template picker in studio dev mode. */
export const FEATURED_BUNDLED_TEMPLATE_IDS = [
  "ace-step-1.5",
  "ace-step-1.5-sft",
  "ace-step-lora-demo",
  "ace-step-dual-lora-ab",
  "ambisonic-trajectory-demo",
  "authenticity-check",
  "watermark-embed-detect",
  "asr-benchmark-wer-cer",
  "compare-stemmers",
  "demucs-vs-openunmix",
  "compare-whisper-sizes",
  "empty-canvas",
  "extract-lyrics-to-music-with-ace-step",
  "groove-systems-replica",
  "groove-systems-study",
  "hello-groovy",
  "instrumental-tts-dub",
  "isolate-vocals-to-transcribe",
  "isolate-vocals-to-transcribe-translate",
  "isolate-vocals-to-voice-convert",
  "karaoke-guide-vocal",
  "layered-music-sfx",
  "localize-dialogue-a-to-b",
  "modular-generative-rack",
  "mono-to-stereo-pan",
  "podcast-denoise",
  "prompt-modular-synth",
  "rave-timbre-transfer",
  "sample-verify",
  "script-to-vo-master",
  "neural-modular-rack",
  "song-cover-remix",
  "moving-clouds",
  "rutt-etra-scan",
  "shepard-tone",
  "spiegel-drums-1975",
  "stable-audio",
  "stereo-to-atmos-bed",
  "stereo-to-binaural",
  "stem-lyrics-to-ace",
  "stem-separation",
  "text-to-midi",
  "text-to-music",
  "text-to-video",
  "transcribe-and-diarize",
  "transcribe-and-regenerate",
  "transcribe-dialogue",
  "tts-emotion-edit",
  "voice-cloning",
] as const;

/** Bundled templates that never appear in the picker, even if currently loaded. */
export const PICKER_HIDDEN_BUNDLED_TEMPLATE_IDS = [
  "melody-to-modular-synth",
  "self-playing-neural-rack",
  "tab-creative-grow",
  "video-to-audio",
] as const;

/** Node types hidden from palette / canvas picker (even in studio dev mode). CUDA-only / experimental. */
export const PICKER_HIDDEN_NODE_TYPES = ["Video2Audio"] as const;

export type TemplateDomainId =
  | "start"
  | "experimental"
  | "speech"
  | "stems"
  | "generate"
  | "video"
  | "modular"
  | "immersive"
  | "compare"
  | "trust"
  | "other";

export type TemplateDomain = {
  id: TemplateDomainId;
  label: string;
};

/** Picker domains — Hub/job-aligned, not phase numbers. */
export const TEMPLATE_DOMAINS: readonly TemplateDomain[] = [
  { id: "start", label: "Starter Templates" },
  { id: "experimental", label: "Experimental" },
  { id: "speech", label: "Podcast & Gaming VO" },
  { id: "stems", label: "Stems & Remix" },
  { id: "generate", label: "Generate Music" },
  { id: "video", label: "Generate Video" },
  { id: "modular", label: "Modular Synth" },
  { id: "immersive", label: "Immersive" },
  { id: "compare", label: "A/B Compare" },
  { id: "trust", label: "AI Trust" },
  { id: "other", label: "Other" },
] as const;

/** Featured (and known) template → domain. Unknown featured IDs fall into Other. */
export const TEMPLATE_DOMAIN_BY_ID: Readonly<Record<string, TemplateDomainId>> = {
  "empty-canvas": "start",
  "hello-groovy": "start",
  "tab-creative-grow": "experimental",
  "groove-systems-replica": "experimental",
  "groove-systems-study": "experimental",
  "spiegel-drums-1975": "experimental",

  "podcast-denoise": "speech",
  "transcribe-dialogue": "speech",
  "transcribe-and-diarize": "speech",
  "cleanup-and-transcribe": "speech",
  "denoise-diarize-transcribe": "speech",
  "isolate-vocals-to-transcribe": "speech",
  "isolate-vocals-to-transcribe-translate": "speech",
  "tts-emotion-edit": "speech",
  "voice-cloning": "speech",
  "script-to-vo-master": "speech",
  "localize-dialogue-a-to-b": "speech",
  "instrumental-tts-dub": "speech",
  "isolate-vocals-to-voice-convert": "speech",
  "compare-whisper-sizes": "compare",
  "asr-benchmark-wer-cer": "compare",
  "demucs-vs-openunmix": "compare",
  "sample-verify": "compare",
  "ab-compare-demo": "compare",

  "prompt-modular-synth": "modular",
  "moving-clouds": "modular",
  "rutt-etra-scan": "modular",
  "shepard-tone": "modular",

  "stem-separation": "stems",
  "karaoke-stems": "stems",
  "karaoke-guide-vocal": "stems",
  "song-cover-remix": "stems",
  "rave-timbre-transfer": "stems",
  "stem-lyrics-to-ace": "stems",
  "compare-stemmers": "compare",

  "text-to-midi": "generate",
  "text-to-music": "generate",
  "stable-audio": "generate",
  "layered-music-sfx": "generate",
  "ace-step-1.5": "generate",
  "ace-step-1.5-sft": "generate",
  "ace-step-lora-demo": "compare",
  "ace-step-dual-lora-ab": "compare",
  "extract-lyrics-to-music-with-ace-step": "generate",
  "transcribe-and-regenerate": "generate",

  "text-to-video": "video",
  "video-to-audio": "video",

  "modular-generative-rack": "modular",
  "melody-to-modular-synth": "modular",
  "neural-modular-rack": "modular",
  "self-playing-neural-rack": "modular",
  "simple-fm-synth": "modular",
  "mono-to-stereo-pan": "modular",

  "authenticity-check": "trust",
  "watermark-embed-detect": "trust",

  "ambisonic-trajectory-demo": "immersive",
  "ambisonic-vr-preview": "immersive",
  "stereo-to-binaural": "immersive",
  "stereo-to-atmos-bed": "immersive",
  "stems-to-spatial": "immersive",
  "object-spatial-demo": "immersive",
  "surround-mix": "immersive",
};

const standardBundledIds = new Set<string>(STANDARD_BUNDLED_TEMPLATE_IDS);
const featuredBundledIds = new Set<string>(FEATURED_BUNDLED_TEMPLATE_IDS);
const pickerHiddenBundledIds = new Set<string>(PICKER_HIDDEN_BUNDLED_TEMPLATE_IDS);
const pickerHiddenNodeTypes = new Set<string>(PICKER_HIDDEN_NODE_TYPES);

/**
 * Node types used by {@link STANDARD_BUNDLED_TEMPLATE_IDS} graphs.
 * Standard mode (non–studio-dev) palette / canvas picker only lists these.
 * Keep in sync when ISMIR demo templates change.
 */
export const STANDARD_MODE_NODE_TYPES = [
  "AutomationApply",
  "Benchmark",
  "ControlCurve",
  "Denoise",
  "DetectWatermark",
  "EmbedWatermark",
  "GenerateAudio",
  "GenerateImage",
  "GenerateMidi",
  "GenerateSpeech",
  "GenerateVideo",
  "Granulate",
  "SwitchImage",
  "LoadAudio",
  "LoadImage",
  "LoadVideo",
  "MuxVideo",
  "Normalize",
  "Note",
  "PreviewAudio",
  "PreviewImage",
  "PreviewMidi",
  "PreviewVideo",
  "Prompt",
  "SaveAudio",
  "SaveGenerateLog",
  "SaveImage",
  "SaveMidi",
  "SaveVideo",
  "SeparateStems",
  "SynthMidi",
  "TranslateText",
  "VoiceConvert",
  "WhisperSTT",
] as const;

/**
 * Modular synth + control-rate nodes always available in Modular / All tiers
 * (without requiring studio dev mode). Keep in sync with NodePalette MODULAR_NODES.
 */
export const MODULAR_MODE_NODE_TYPES = [
  "Amplifier",
  "Attenuator",
  "AutomationApply",
  "AutomationToMIDI",
  "BeatTrack",
  "Clock",
  "Comparator",
  "ControlCurve",
  "Envelope",
  "EnvelopeFollower",
  "Filter",
  "Float",
  "FloatMath",
  "FloatRoute",
  "Granulate",
  "LFO",
  "LoadMIDI",
  "Logic",
  "MatrixMixer",
  "MIDINoteGate",
  "MIDIToFloat",
  "Mix",
  "NoiseGenerator",
  "Oscillator",
  "Pan",
  "Quantizer",
  "Reverb",
  "SampleAndHold",
  "ScanProcessor",
  "SignalGenerator",
] as const;

const standardModeNodeTypes = new Set<string>(STANDARD_MODE_NODE_TYPES);
const modularModeNodeTypes = new Set<string>(MODULAR_MODE_NODE_TYPES);

/** Standard mode: ISMIR demo nodes + modular synth set. Studio dev mode: all palette-eligible except picker-hidden. */
export function isNodeVisibleInStudio(nodeType: string, studioDevMode = false): boolean {
  if (pickerHiddenNodeTypes.has(nodeType)) return false;
  if (studioDevMode) return true;
  return standardModeNodeTypes.has(nodeType) || modularModeNodeTypes.has(nodeType);
}

export function domainIdForTemplate(templateId: string): TemplateDomainId {
  return TEMPLATE_DOMAIN_BY_ID[templateId] ?? "other";
}

/**
 * Hide non-featured bundled templates from the studio UI; user templates always show.
 * Standard mode: ISMIR demo set only (Immersive not included). Studio dev mode: full featured list.
 */
export function templatesVisibleInUi(
  templates: TemplateListItem[],
  selectedId?: string,
  studioDevMode = false,
): TemplateListItem[] {
  const allowedIds = studioDevMode ? featuredBundledIds : standardBundledIds;
  return templates
    .filter((template) => {
      if (template.source === "user") return true;
      if (pickerHiddenBundledIds.has(template.id)) return false;
      return allowedIds.has(template.id) || template.id === selectedId;
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
