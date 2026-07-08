import type { NodeSchema, NodeWidgetSpec } from "./types";

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

export function applyNodeSchemaFallbacks(schema: NodeSchema): NodeSchema {
  const fallback = NODE_WIDGET_FALLBACKS[schema.type];
  if (!fallback?.length) return schema;
  const existing = new Set((schema.widgets ?? []).map((widget) => widget.name));
  const widgets = [...(schema.widgets ?? [])];
  for (const widget of fallback) {
    if (!existing.has(widget.name)) widgets.push(widget);
  }
  return widgets.length === (schema.widgets ?? []).length ? schema : { ...schema, widgets };
}
