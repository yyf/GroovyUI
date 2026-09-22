/** Edge stroke palette locked to studio aesthetic (B/W/signal-red + greys). */
export const EDGE_COLOR_PALETTE = [
  "#ff002b", // signal red (AUDIO default)
  "#ffffff", // primary white
  "#a3a3a3", // TEXT grey
  "#8a8a8a", // STEMS
  "#6e6e6e", // MIDI
  "#5a5a5a", // AUTOMATION
  "#4a4a4a", // FLOAT
  "#3a3a3a", // idle wire
] as const;

export type EdgePaletteColor = (typeof EDGE_COLOR_PALETTE)[number];

const PALETTE_SET = new Set<string>(EDGE_COLOR_PALETTE.map((c) => c.toLowerCase()));

/** Typed socket colors — AUDIO is signal-red; other types stay muted greys. */
export const SOCKET_TYPE_COLORS: Record<string, string> = {
  AUDIO: "#ff002b",
  STEMS: "#8a8a8a",
  MIDI: "#6e6e6e",
  TEXT: "#a3a3a3",
  AUTOMATION: "#5a5a5a",
  FLOAT: "#4a4a4a",
  AUTHENTICITY: "#7a7a7a",
  SAMPLE_CHECK: "#8c8c8c",
  AMBISONICS: "#9a9a9a",
  OBA: "#707070",
  OSC: "#555555",
  TRAJECTORY: "#d4a84b",
};

export function socketTypeClass(type: string): string {
  return `socket-type--${type.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export function socketTypeColor(type: string): string {
  return SOCKET_TYPE_COLORS[type.toUpperCase()] ?? "#6e6e6e";
}

export function edgeTypeClass(type: string): string {
  return `groovy-edge--type-${type.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

/** Accept only palette hex (case-insensitive); otherwise null. */
export function normalizeEdgeColor(color: string | null | undefined): EdgePaletteColor | null {
  if (!color || typeof color !== "string") return null;
  const hex = color.trim().toLowerCase();
  if (!PALETTE_SET.has(hex)) return null;
  return EDGE_COLOR_PALETTE.find((c) => c.toLowerCase() === hex) ?? null;
}

/** Stroke for a link: optional user color if in palette, else socket-type default. */
export function resolveEdgeStroke(type: string, color?: string | null): string {
  return normalizeEdgeColor(color) ?? socketTypeColor(type);
}
