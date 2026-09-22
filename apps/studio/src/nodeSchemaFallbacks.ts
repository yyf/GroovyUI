import type { NodeSchema, NodeWidgetSpec } from "./types";

type OutputSocket = { name: string; type: string; description?: string };

/** Widgets when the API is on an older build (e.g. SaveAudio before path/filename fields). */
const NODE_WIDGET_FALLBACKS: Record<string, NodeWidgetSpec[]> = {
  Resample: [
    {
      name: "target_sample_rate",
      type: "INT",
      default: 48000,
      min: 8000,
      max: 192000,
      description: "Output sample rate in Hz",
    },
    { name: "quality", type: "STRING", default: "good" },
  ],
  SaveAudio: [
    {
      name: "path",
      type: "STRING",
      default: "exports",
      description: "Folder under the project directory (e.g. exports/podcast)",
    },
    {
      name: "filename",
      type: "STRING",
      default: "output.wav",
      description: "File name including extension",
    },
    { name: "format", type: "STRING", default: "wav" },
    { name: "bit_depth", type: "STRING", default: "float" },
  ],
  Meter: [
    {
      name: "layout",
      type: "STRING",
      default: "stereo",
      description: "Channel labels: stereo (default), mono, 5.1, 7.1, auto",
    },
    {
      name: "edge_fraction",
      type: "FLOAT",
      default: 0.05,
      description: "Fraction of clip for head/tail peak windows",
    },
  ],
};

/** Output sockets when the API is on an older build (e.g. SeparateStems before four AUDIO outputs). */
const NODE_OUTPUT_FALLBACKS: Record<string, OutputSocket[]> = {
  SeparateStems: [
    { name: "vocals", type: "AUDIO" },
    { name: "drums", type: "AUDIO" },
    { name: "bass", type: "AUDIO" },
    { name: "other", type: "AUDIO" },
  ],
  Meter: [
    { name: "audio", type: "AUDIO" },
    { name: "levels", type: "TEXT" },
  ],
};

function hasLegacySeparateStemsOutputs(outputs: OutputSocket[] | undefined): boolean {
  return (
    outputs?.length === 1 &&
    (outputs[0].type === "STEMS" || outputs[0].name === "output_0")
  );
}

export function applyNodeSchemaFallbacks(schema: NodeSchema): NodeSchema {
  let next = schema;
  const fallback = NODE_WIDGET_FALLBACKS[schema.type];
  if (fallback?.length) {
    const existing = new Set((next.widgets ?? []).map((widget) => widget.name));
    const widgets = [...(next.widgets ?? [])];
    for (const widget of fallback) {
      if (!existing.has(widget.name)) widgets.push(widget);
    }
    if (widgets.length !== (next.widgets ?? []).length) {
      next = { ...next, widgets };
    }
  }
  const outputFallback = NODE_OUTPUT_FALLBACKS[schema.type];
  if (outputFallback?.length) {
    if (schema.type === "SeparateStems" && hasLegacySeparateStemsOutputs(next.outputs)) {
      next = { ...next, outputs: outputFallback };
    } else if (schema.type === "Meter" && (next.outputs?.length ?? 0) < 2) {
      next = { ...next, outputs: outputFallback };
    }
  }
  return next;
}
