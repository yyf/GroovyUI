/**
 * Curated template × model license overview for the public OSS template set.
 * Source of truth for Settings → Template licenses (studio dev mode / ⌘⇧D only).
 * Keep in sync with `STANDARD_BUNDLED_TEMPLATE_IDS` / repo `templates/` (not docs/internal).
 */

import { STANDARD_BUNDLED_TEMPLATE_IDS } from "./templateUi";

export type TemplateLicenseTone = "safe" | "nc" | "caution";

export type TemplateLicenseRow = {
  id: string;
  title: string;
  models: string;
  licenses: string;
  impact: string;
  cluster: string;
  /** Short commercial label: Safe | Not safe */
  commercial: "Safe" | "Not safe";
  conference: string;
  final: string;
  tone: TemplateLicenseTone;
};

/** Public shipped templates only (ISMIR LBD / standard picker). */
const PUBLIC_TEMPLATE_LICENSE_ROWS: TemplateLicenseRow[] = [
  {
    id: "empty-canvas",
    title: "Empty Canvas",
    models: "— (blank graph)",
    licenses: "— (DSP / no AI weights)",
    impact: "High",
    cluster: "Onboarding",
    commercial: "Safe",
    conference: "Safe",
    final: "Commercial Safe",
    tone: "safe",
  },
  {
    id: "hello-groovy",
    title: "Hello GroovyUI",
    models: "kokoro-82m",
    licenses: "kokoro-82m: Apache-2.0",
    impact: "High",
    cluster: "Onboarding",
    commercial: "Safe",
    conference: "Safe",
    final: "Commercial Safe",
    tone: "safe",
  },
  {
    id: "podcast-denoise",
    title: "Podcast Denoise",
    models: "deepfilternet-v3",
    licenses: "deepfilternet-v3: MIT",
    impact: "High",
    cluster: "Speech cleanup",
    commercial: "Safe",
    conference: "Safe",
    final: "Commercial Safe",
    tone: "safe",
  },
  {
    id: "isolate-vocals-to-transcribe",
    title: "Isolate to Transcribe",
    models: "demucs-v4, whisper-large-v3-turbo",
    licenses: "demucs-v4: MIT; whisper-large-v3-turbo: MIT",
    impact: "Med",
    cluster: "Stems + ASR",
    commercial: "Safe",
    conference: "Safe",
    final: "Commercial Safe",
    tone: "safe",
  },
  {
    id: "prompt-modular-synth",
    title: "Prompt Modular Synth",
    models: "kokoro-82m",
    licenses: "kokoro-82m: Apache-2.0",
    impact: "Med",
    cluster: "Modular teach",
    commercial: "Safe",
    conference: "Safe",
    final: "Commercial Safe",
    tone: "safe",
  },
  {
    id: "video-to-audio",
    title: "Video to Audio",
    models: "diff-foley (default)",
    licenses: "diff-foley: code Apache-2.0 / weights MIT",
    impact: "Med",
    cluster: "Generate Foley",
    commercial: "Safe",
    conference: "Safe",
    final: "Commercial Safe",
    tone: "safe",
  },
];

const publicIdSet = new Set<string>(STANDARD_BUNDLED_TEMPLATE_IDS);

/** Rows shown in Settings → Template licenses (public `templates/` only). */
export const TEMPLATE_LICENSE_MATRIX: TemplateLicenseRow[] = PUBLIC_TEMPLATE_LICENSE_ROWS.filter(
  (row) => publicIdSet.has(row.id),
);

export function templateLicenseSummary(): {
  total: number;
  commercialSafe: number;
  conferenceOnly: number;
  caution: number;
} {
  return {
    total: TEMPLATE_LICENSE_MATRIX.length,
    commercialSafe: TEMPLATE_LICENSE_MATRIX.filter((r) => r.tone === "safe").length,
    conferenceOnly: TEMPLATE_LICENSE_MATRIX.filter((r) => r.tone === "nc").length,
    caution: TEMPLATE_LICENSE_MATRIX.filter((r) => r.tone === "caution").length,
  };
}

export function isCommerciallyCleared(templateId: string): boolean {
  return TEMPLATE_LICENSE_MATRIX.some((r) => r.id === templateId && r.commercial === "Safe");
}
