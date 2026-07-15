/** Map widget specs → industrial control chrome (pots / faders / switches). */

export type ControlKind = "text" | "switch" | "pot" | "fader" | "stepped";

export type ResolvedControl = {
  kind: ControlKind;
  min: number;
  max: number;
  step: number;
  options?: string[];
};

const TEXT_NAMES = new Set([
  "path",
  "filename",
  "text",
  "prompt",
  "lyrics",
  "model",
  "name",
  "socket_type",
  "language",
  "external_id",
  "description",
]);

const FADER_NAMES = /^(gain|gain_[ab]|volume|level|wet|dry|amount|mix|select|strength|opacity|balance)$/i;

const STRING_OPTIONS: Record<string, string[]> = {
  format: ["wav", "flac"],
  bit_depth: ["16", "24", "32", "float"],
  quality: ["fast", "good", "best"],
  mode: ["lufs", "peak"],
  stem: ["vocals", "drums", "bass", "other", "accompaniment"],
  midi_kind: ["control", "performance", "transcript"],
  layout: ["mono", "stereo", "5.1", "7.1", "7.1.4"],
  operation: ["add", "multiply"],
  output: ["stereo", "binaural", "5.1"],
  source_layout: ["mono", "stereo", "5.1", "7.1"],
};

const SAMPLE_RATES = [8000, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000, 192000];

type SpecLike = {
  name: string;
  type: string;
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
};

function isTextLike(name: string, type: string): boolean {
  if (type === "MODEL_REF") return true;
  if (type !== "STRING" && type !== "TEXT") return false;
  if (TEXT_NAMES.has(name)) return true;
  if (STRING_OPTIONS[name]) return false;
  return true;
}

function floatRange(spec: SpecLike): { min: number; max: number; step: number } {
  const name = spec.name.toLowerCase();
  let min = spec.min;
  let max = spec.max;
  const def = typeof spec.default === "number" ? spec.default : Number(spec.default);
  if (min == null || max == null) {
    if (/lufs/.test(name)) {
      min = min ?? -40;
      max = max ?? 0;
    } else if (/db|peak/.test(name)) {
      min = min ?? -60;
      max = max ?? 6;
    } else if (FADER_NAMES.test(name) || /overlap|select/.test(name)) {
      min = min ?? 0;
      max = max ?? 1;
    } else if (Number.isFinite(def) && Math.abs(def) > 1) {
      min = min ?? Math.min(0, def * 2);
      max = max ?? Math.max(Math.abs(def) * 2, 1);
    } else {
      min = min ?? 0;
      max = max ?? 2;
    }
  }
  const span = Math.max(1e-9, max - min);
  const step =
    spec.step ??
    (span <= 1 ? 0.01 : span <= 10 ? 0.05 : span <= 100 ? 0.5 : 1);
  return { min, max, step };
}

function intRange(spec: SpecLike): { min: number; max: number; step: number } {
  let min = spec.min ?? 0;
  let max = spec.max;
  const def = typeof spec.default === "number" ? spec.default : Number(spec.default);
  const name = spec.name.toLowerCase();
  if (max == null) {
    if (/sample_rate|samplerate/.test(name)) {
      min = spec.min ?? 8000;
      max = 192000;
    } else if (/frame/.test(name)) {
      max = Math.max(48000, Number.isFinite(def) ? Math.abs(def) * 2 : 48000);
      if (def === -1) max = 480000;
    } else if (/channel|note|cc/.test(name)) {
      max = /note/.test(name) ? 127 : /cc/.test(name) ? 127 : 16;
    } else if (Number.isFinite(def) && def > 0) {
      max = Math.max(def * 4, 16);
    } else {
      max = 32;
    }
  }
  if (/end_frame/.test(name) && min > -1) {
    min = -1;
  }
  return { min, max, step: spec.step ?? 1 };
}

export function resolveWidgetControl(spec: SpecLike): ResolvedControl {
  const type = spec.type.toUpperCase();
  const name = spec.name;

  if (type === "BOOLEAN" || type === "BOOL") {
    return { kind: "switch", min: 0, max: 1, step: 1 };
  }

  if (isTextLike(name, type)) {
    return { kind: "text", min: 0, max: 0, step: 0 };
  }

  if (type === "STRING" || type === "TEXT") {
    const options = STRING_OPTIONS[name];
    if (options?.length) {
      return { kind: "stepped", min: 0, max: options.length - 1, step: 1, options };
    }
    return { kind: "text", min: 0, max: 0, step: 0 };
  }

  if (type === "INT") {
    if (/sample_rate|samplerate/.test(name.toLowerCase())) {
      return {
        kind: "stepped",
        min: 0,
        max: SAMPLE_RATES.length - 1,
        step: 1,
        options: SAMPLE_RATES.map(String),
      };
    }
    const range = intRange(spec);
    const span = range.max - range.min;
    const kind: ControlKind = span > 64 || /frame/.test(name.toLowerCase()) ? "fader" : "pot";
    return { kind, ...range };
  }

  if (type === "FLOAT") {
    const range = floatRange(spec);
    const kind: ControlKind = FADER_NAMES.test(name) ? "fader" : "pot";
    return { kind, ...range };
  }

  return { kind: "text", min: 0, max: 0, step: 0 };
}

export function snapToStep(value: number, min: number, max: number, step: number): number {
  const clamped = Math.min(max, Math.max(min, value));
  if (step <= 0) return clamped;
  const steps = Math.round((clamped - min) / step);
  return Math.min(max, Math.max(min, min + steps * step));
}

export function formatControlValue(value: number, step: number, isInt: boolean): string {
  if (isInt) return String(Math.round(value));
  if (step >= 1) return value.toFixed(0);
  if (step >= 0.1) return value.toFixed(1);
  if (step >= 0.01) return value.toFixed(2);
  return value.toFixed(3);
}
