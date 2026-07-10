import type { NodeSchema, NodeWidgetSpec } from "./types";

type OutputSocket = { name: string; type: string; description?: string };

/** Widgets when the API is on an older build (e.g. SaveAudio before path/filename fields). */
const NODE_WIDGET_FALLBACKS: Record<string, NodeWidgetSpec[]> = {
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
};

/** Output sockets when the API is on an older build (e.g. SeparateStems before four AUDIO outputs). */
const NODE_OUTPUT_FALLBACKS: Record<string, OutputSocket[]> = {
  SeparateStems: [
    { name: "vocals", type: "AUDIO" },
    { name: "drums", type: "AUDIO" },
    { name: "bass", type: "AUDIO" },
    { name: "other", type: "AUDIO" },
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
  if (outputFallback?.length && hasLegacySeparateStemsOutputs(next.outputs)) {
    next = { ...next, outputs: outputFallback };
  }
  return next;
}
