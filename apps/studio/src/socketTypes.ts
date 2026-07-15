/** Typed socket colors — AUDIO is signal-red; other types stay muted greys. */
export const SOCKET_TYPE_COLORS: Record<string, string> = {
  AUDIO: "#ff002b",
  STEMS: "#8a8a8a",
  MIDI: "#6e6e6e",
  TEXT: "#a3a3a3",
  AUTOMATION: "#5a5a5a",
  FLOAT: "#4a4a4a",
  AUTHENTICITY: "#7a7a7a",
  AMBISONICS: "#9a9a9a",
  OBA: "#707070",
  OSC: "#555555",
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
