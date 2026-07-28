/** Canvas / palette classification for AI vs non-AI nodes. */

/** Fallback when `/api/nodes` schema is not loaded yet. Keep in sync with NodePalette AI sets. */
const AI_NODE_TYPES = new Set([
  "Denoise",
  "SeparateStems",
  "SeparateToObjects",
  "WhisperSTT",
  "DiarizeTranscribe",
  "TTS",
  "VoiceConvert",
  "TimbreTransfer",
  "AudioToMIDI",
  "DeepfakeDetect",
  "MIDIToAudio",
  "GenerateAudio",
  "SingFromMIDI",
]);

export type CanvasNodeKind = "ai" | "core";

export function isAiNodeType(nodeType: string, category?: string | null): boolean {
  if (category && category.includes("AI")) return true;
  return AI_NODE_TYPES.has(nodeType);
}

export function canvasNodeKind(nodeType: string, category?: string | null): CanvasNodeKind {
  return isAiNodeType(nodeType, category) ? "ai" : "core";
}
