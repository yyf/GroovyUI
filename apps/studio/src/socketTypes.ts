/** Typed socket colors — aligned with modular synth / Max-style patching. */
export const SOCKET_TYPE_COLORS: Record<string, string> = {
  AUDIO: "#60a5fa",
  STEMS: "#a78bfa",
  MIDI: "#fbbf24",
  TEXT: "#22d3ee",
  AUTOMATION: "#fb923c",
  FLOAT: "#f472b6",
  AUTHENTICITY: "#f87171",
  AMBISONICS: "#2dd4bf",
  OBA: "#4ade80",
  OSC: "#a3e635",
};

export function socketTypeClass(type: string): string {
  return `socket-type--${type.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export function socketTypeColor(type: string): string {
  return SOCKET_TYPE_COLORS[type.toUpperCase()] ?? "#9ca3af";
}

export function edgeTypeClass(type: string): string {
  return `groovy-edge--type-${type.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}
