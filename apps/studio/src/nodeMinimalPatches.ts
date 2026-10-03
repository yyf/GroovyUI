import type { NodeSchema, Workflow, WorkflowLink, WorkflowNode } from "./types";
import { DEFAULT_LOAD_AUDIO_PATH } from "./sampleDefaults";
import {
  allocatePatchNodeIdMap,
  estimateNodeSize,
  findOpenNodePosition,
  isWireableInput,
} from "./workflow";

export type MinimalPatch = {
  workflow: Workflow;
  focusNodeId: string;
  hint: string;
};

const SAMPLE = DEFAULT_LOAD_AUDIO_PATH;
const MIDI_SAMPLE = "assets/samples/automation_cc7.mid";

type PatchNode = {
  id: string;
  type: string;
  x: number;
  y?: number;
  widgets?: Record<string, unknown>;
};

type PatchLink = {
  id: string;
  from: [string, number];
  to: [string, number];
  type: string;
};

type PatchRecipe = {
  title: string;
  description: string;
  focusNodeId: string;
  nodes: PatchNode[];
  links: PatchLink[];
};

function load(id: string, x: number, y = 0, path = SAMPLE): PatchNode {
  return { id, type: "LoadAudio", x, y, widgets: { path } };
}

function preview(id: string, x: number, y = 0): PatchNode {
  return { id, type: "Preview", x, y, widgets: {} };
}

function link(id: string, from: string, to: string, type: string, fromSlot = 0, toSlot = 0): PatchLink {
  return { id, from: [from, fromSlot], to: [to, toSlot], type };
}

function recipeToWorkflow(recipe: PatchRecipe): Workflow {
  return {
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: `minimal-${recipe.focusNodeId}-${Date.now()}`,
    metadata: { title: recipe.title, description: recipe.description },
    nodes: recipe.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      pos: { x: node.x, y: node.y ?? 0 },
      widgets: node.widgets ?? {},
    })),
    links: recipe.links,
    groups: [],
    view: { zoom: 1.0, pan: { x: 0, y: 0 } },
  };
}

function define(recipe: PatchRecipe): MinimalPatch {
  return {
    workflow: recipeToWorkflow(recipe),
    focusNodeId: recipe.focusNodeId,
    hint: `Expanded minimal ${recipe.title.toLowerCase()} chain at the selected node`,
  };
}

/** Minimal example graph per node type (Tab on a selected node). */
const PATCH_RECIPES: Record<string, PatchRecipe> = {
  LoadAudio: {
    title: "Load Audio",
    description: "Load a sample, normalize, and preview.",
    focusNodeId: "n1",
    nodes: [load("n1", 0), { id: "n2", type: "Normalize", x: 260, widgets: { mode: "lufs", target_lufs: -16 } }, preview("n3", 520)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  SaveAudio: {
    title: "Save Audio",
    description: "Load, normalize, and write to exports.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "Normalize", x: 260, widgets: { mode: "lufs", target_lufs: -16 } },
      { id: "n3", type: "SaveAudio", x: 520, widgets: { path: "exports", filename: "saved.wav", format: "wav" } },
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  Resample: {
    title: "Resample",
    description: "Load audio and resample to 44.1 kHz.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "Resample", x: 260, widgets: { target_sample_rate: 44100 } }, preview("n3", 520)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  Trim: {
    title: "Trim",
    description: "Load audio and trim to the first second.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "Trim", x: 260, widgets: { start_frame: 0, end_frame: 48000 } }, preview("n3", 520)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  Mix: {
    title: "Mix",
    description: "Sum two loaded clips with explicit layout matching.",
    focusNodeId: "n3",
    nodes: [load("n1", 0), load("n2", 0, 120), { id: "n3", type: "Mix", x: 280, widgets: {} }, preview("n4", 540)],
    links: [
      link("l1", "n1", "n3", "AUDIO", 0, 0),
      link("l2", "n2", "n3", "AUDIO", 0, 1),
      link("l3", "n3", "n4", "AUDIO"),
    ],
  },
  Pan: {
    title: "Pan",
    description: "Mono → stereo equal-power pan (−1 left … +1 right). Layout-agnostic — also targets surround beds.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "ChannelConvert", x: 260, widgets: { layout: "mono" } },
      { id: "n3", type: "Pan", x: 520, widgets: { pan: 0.55, output_layout: "stereo" } },
      preview("n4", 780),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n3", "AUDIO"),
      link("l3", "n3", "n4", "AUDIO"),
    ],
  },
  ChannelMerge: {
    title: "Channel Merge",
    description: "Combine LoadAudio L/R (or mono) outlets into one stereo buffer for SaveAudio.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0, 0, "assets/samples/stem_separation_demo.wav"),
      { id: "n2", type: "ChannelMerge", x: 280, widgets: { output_layout: "stereo" } },
      preview("n3", 540),
      {
        id: "n4",
        type: "SaveAudio",
        x: 540,
        y: 120,
        widgets: { path: "exports", filename: "stereo-merge.wav" },
      },
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO", 0, 0),
      link("l2", "n1", "n2", "AUDIO", 1, 1),
      link("l3", "n2", "n3", "AUDIO"),
      link("l4", "n2", "n4", "AUDIO"),
    ],
  },
  Normalize: {
    title: "Normalize",
    description: "Load audio and normalize to −16 LUFS.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "Normalize", x: 260, widgets: { mode: "lufs", target_lufs: -16 } }, preview("n3", 520)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  Granulate: {
    title: "Granulate",
    description: "Load audio into a grain cloud — size, hop, pitch, density, and stereo width via curves.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      {
        id: "n4",
        type: "ControlCurve",
        x: 0,
        y: 140,
        widgets: {
          start_value: 95,
          end_value: 8,
          frame_count: 96000,
          sample_rate: 48000,
          points: '[{"t":0,"v":95},{"t":0.4,"v":70},{"t":0.7,"v":28},{"t":1,"v":8}]',
        },
      },
      {
        id: "n5",
        type: "ControlCurve",
        x: 0,
        y: 280,
        widgets: {
          start_value: 42,
          end_value: 10,
          frame_count: 96000,
          sample_rate: 48000,
          points: '[{"t":0,"v":42},{"t":0.4,"v":32},{"t":0.7,"v":16},{"t":1,"v":10}]',
        },
      },
      {
        id: "n6",
        type: "ControlCurve",
        x: 0,
        y: 420,
        widgets: {
          start_value: 0,
          end_value: 420,
          frame_count: 96000,
          sample_rate: 48000,
          points: '[{"t":0,"v":0},{"t":0.45,"v":40},{"t":0.75,"v":220},{"t":1,"v":420}]',
        },
      },
      {
        id: "n7",
        type: "ControlCurve",
        x: 0,
        y: 560,
        widgets: {
          start_value: 0,
          end_value: 110,
          frame_count: 96000,
          sample_rate: 48000,
          points: '[{"t":0,"v":0},{"t":0.4,"v":8},{"t":0.7,"v":45},{"t":1,"v":110}]',
        },
      },
      {
        id: "n8",
        type: "ControlCurve",
        x: 0,
        y: 700,
        widgets: {
          start_value: 0,
          end_value: 0.95,
          frame_count: 96000,
          sample_rate: 48000,
          points: '[{"t":0,"v":0},{"t":0.5,"v":0.15},{"t":0.8,"v":0.65},{"t":1,"v":0.95}]',
        },
      },
      {
        id: "n2",
        type: "Granulate",
        x: 280,
        widgets: {
          grain_ms: 45,
          hop_ms: 18,
          pitch_cents: 0,
          density: 0,
          spray: 4,
          width: 0,
          window: "exp",
          window_alpha: 0.35,
          scatter_ms: 320,
          wet_start: 0,
          wet_end: 1,
          seed: 7,
        },
      },
      preview("n3", 560),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l3", "n4", "n2", "AUTOMATION", 0, 1),
      link("l4", "n5", "n2", "AUTOMATION", 0, 2),
      link("l5", "n6", "n2", "AUTOMATION", 0, 3),
      link("l6", "n7", "n2", "AUTOMATION", 0, 4),
      link("l7", "n8", "n2", "AUTOMATION", 0, 5),
      link("l2", "n2", "n3", "AUDIO"),
    ],
  },
  MultichannelNormalize: {
    title: "Multichannel Normalize",
    description: "Normalize multichannel audio to broadcast loudness.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "MultichannelNormalize", x: 260, widgets: { mode: "lufs" } }, preview("n3", 520)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  Preview: {
    title: "Preview",
    description: "Terminal sink — wire audio for audition or text for on-canvas transcript.",
    focusNodeId: "n3",
    nodes: [load("n1", 0), { id: "n2", type: "Normalize", x: 260, widgets: { mode: "lufs" } }, preview("n3", 520)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  ChannelConvert: {
    title: "Channel Convert",
    description: "Explicit layout conversion to stereo.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "ChannelConvert", x: 260, widgets: { layout: "stereo" } }, preview("n3", 520)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  Transcode: {
    title: "Transcode",
    description: "Export cached audio to FLAC while passing through.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "Transcode", x: 260, widgets: { format: "flac", path: "assets/exports/example.flac" } },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  Prompt: {
    title: "Prompt",
    description: "Text prompt into MusicGen generation.",
    focusNodeId: "n1",
    nodes: [
      { id: "n1", type: "Prompt", x: 0, widgets: { text: "warm lo-fi beat with soft piano" } },
      { id: "n2", type: "GenerateAudio", x: 260, widgets: { model: "musicgen-small", prompt: "", seed: -1 } },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "TEXT"), link("l2", "n2", "n3", "AUDIO")],
  },
  LoadMIDI: {
    title: "Load MIDI",
    description: "Load a MIDI file and synthesize audio.",
    focusNodeId: "n1",
    nodes: [
      { id: "n1", type: "LoadMIDI", x: 0, widgets: { path: MIDI_SAMPLE, midi_kind: "performance" } },
      { id: "n2", type: "MIDIToAudio", x: 260, widgets: { model: "musicgen-melody-small", prompt: "keyboard melody" } },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "MIDI"), link("l2", "n2", "n3", "AUDIO")],
  },
  ControlCurve: {
    title: "Control Curve",
    description: "Generate an automation envelope and apply gain.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "ControlCurve", x: 260, widgets: { start_value: 0.5, end_value: 1.0 } },
      { id: "n3", type: "AutomationApply", x: 520, widgets: {} },
      preview("n4", 780),
    ],
    links: [
      link("l1", "n1", "n3", "AUDIO"),
      link("l2", "n2", "n3", "AUTOMATION", 0, 1),
      link("l3", "n3", "n4", "AUDIO"),
    ],
  },
  MIDIToFloat: {
    title: "MIDI to Float",
    description: "Extract a CC curve from MIDI control data.",
    focusNodeId: "n2",
    nodes: [
      { id: "n1", type: "LoadMIDI", x: 0, widgets: { path: MIDI_SAMPLE, midi_kind: "control" } },
      { id: "n2", type: "MIDIToFloat", x: 260, widgets: { cc: 7, default_value: 0.75 } },
      { id: "n3", type: "FloatRoute", x: 520, widgets: {} },
    ],
    links: [link("l1", "n1", "n2", "MIDI"), link("l2", "n2", "n3", "AUTOMATION")],
  },
  AutomationToMIDI: {
    title: "Automation to MIDI",
    description: "Read Quantizer Hz CV as MIDI notes for an AI oscillator.",
    focusNodeId: "n3",
    nodes: [
      {
        id: "n1",
        type: "ControlCurve",
        x: 0,
        widgets: { start_value: 110, end_value: 440, frame_count: 48000, sample_rate: 48000 },
      },
      { id: "n2", type: "Quantizer", x: 240, widgets: { scale: "minor", root_hz: 110 } },
      { id: "n3", type: "AutomationToMIDI", x: 480, widgets: { midi_kind: "score", velocity: 0.8 } },
    ],
    links: [link("l1", "n1", "n2", "AUTOMATION"), link("l2", "n2", "n3", "AUTOMATION")],
  },
  BeatTrack: {
    title: "Beat Track",
    description: "Analyze audio for beats and rebuild a clock; fall back to a free Clock if tracking is weak.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      {
        id: "n2",
        type: "Clock",
        x: 0,
        y: 140,
        widgets: { bpm: 92, pulse_ms: 160, duration_sec: 4, sample_rate: 48000 },
      },
      {
        id: "n3",
        type: "BeatTrack",
        x: 280,
        widgets: { fallback_bpm: 92, pulse_ms: 160, min_bpm: 80, max_bpm: 110, tightness: 0.55 },
      },
      { id: "n4", type: "SampleAndHold", x: 540, widgets: { threshold: 0.5 } },
    ],
    links: [
      link("l1", "n1", "n3", "AUDIO"),
      link("l2", "n2", "n3", "AUTOMATION", 0, 1),
      link("l3", "n3", "n4", "AUTOMATION"),
    ],
  },
  MIDINoteGate: {
    title: "MIDI Note Gate",
    description: "Gate audio with MIDI note events.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "LoadMIDI", x: 0, y: 120, widgets: { path: MIDI_SAMPLE, midi_kind: "performance" } },
      { id: "n3", type: "MIDINoteGate", x: 280, widgets: { note: 60, channel: 1 } },
      preview("n4", 540),
    ],
    links: [link("l1", "n1", "n3", "AUDIO"), link("l2", "n2", "n3", "MIDI"), link("l3", "n3", "n4", "AUDIO")],
  },
  AutomationApply: {
    title: "Automation Apply",
    description: "Multiply audio by a control-rate envelope.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "LoadMIDI", x: 0, y: 120, widgets: { path: MIDI_SAMPLE, midi_kind: "control" } },
      { id: "n3", type: "AutomationApply", x: 280, widgets: {} },
      preview("n4", 540),
    ],
    links: [
      link("l1", "n1", "n3", "AUDIO"),
      link("l2", "n2", "n3", "AUTOMATION", 0, 1),
      link("l3", "n3", "n4", "AUDIO"),
    ],
  },
  FloatMath: {
    title: "Float Math",
    description: "Combine two automation curves.",
    focusNodeId: "n3",
    nodes: [
      { id: "n1", type: "ControlCurve", x: 0, widgets: { start_value: 0.25, end_value: 0.75 } },
      { id: "n2", type: "ControlCurve", x: 0, y: 120, widgets: { start_value: 0.5, end_value: 1.0 } },
      { id: "n3", type: "FloatMath", x: 280, widgets: { operation: "add" } },
    ],
    links: [link("l1", "n1", "n3", "AUTOMATION", 0, 0), link("l2", "n2", "n3", "AUTOMATION", 0, 1)],
  },
  FloatRoute: {
    title: "Float Route",
    description: "Select between two automation sources.",
    focusNodeId: "n3",
    nodes: [
      { id: "n1", type: "ControlCurve", x: 0, widgets: {} },
      { id: "n2", type: "ControlCurve", x: 0, y: 120, widgets: { start_value: 1.0, end_value: 0.0 } },
      { id: "n3", type: "FloatRoute", x: 280, widgets: { select: 0.5 } },
    ],
    links: [link("l1", "n1", "n3", "AUTOMATION", 0, 0), link("l2", "n2", "n3", "AUTOMATION", 0, 1)],
  },
  Denoise: {
    title: "Denoise",
    description: "AI denoise then normalize for preview.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0, 0, SAMPLE),
      { id: "n2", type: "Denoise", x: 260, widgets: { model: "deepfilternet-v3", strength: 1.0 } },
      { id: "n3", type: "Normalize", x: 520, widgets: { mode: "lufs", target_lufs: -16 } },
      preview("n4", 780),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO"), link("l3", "n3", "n4", "AUDIO")],
  },
  SeparateStems: {
    title: "Separate Stems",
    description: "Demucs stem split — vocals output wired to preview.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      {
        id: "n2",
        type: "SeparateStems",
        x: 260,
        widgets: { model: "demucs-v4", shifts: 1, overlap: 0.25, segment: 0, split: true },
      },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO", 0, 0)],
  },
  WhisperSTT: {
    title: "Whisper STT",
    description: "Load audio and transcribe with Whisper.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "WhisperSTT", x: 260, widgets: { model: "whisper-large-v3-turbo", language: "en" } }],
    links: [link("l1", "n1", "n2", "AUDIO")],
  },
  DiarizeTranscribe: {
    title: "Diarize + Transcribe",
    description: "Speaker-labeled meeting/podcast transcript.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      {
        id: "n2",
        type: "DiarizeTranscribe",
        x: 260,
        widgets: { model: "whisper-large-v3-turbo", diarize_model: "pyannote-diarization-3.1", language: "en" },
      },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "TEXT", 0, 1)],
  },
  TTS: {
    title: "TTS",
    description: "Synthesize speech from text (optional reference for cloning).",
    focusNodeId: "n1",
    nodes: [
      { id: "n1", type: "TTS", x: 0, widgets: { text: "Hello from GroovyUI.", model: "kokoro-82m" } },
      { id: "n2", type: "Normalize", x: 260, widgets: { mode: "lufs", target_lufs: -16 } },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  VoiceConvert: {
    title: "Voice Convert",
    description: "Convert speaker timbre with RVC.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "VoiceConvert", x: 260, widgets: { model: "rvc-v2-base" } }, preview("n3", 520)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  TimbreTransfer: {
    title: "RAVE Timbre Transfer",
    description: "Neural resynthesis / timbre transfer with RAVE.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "TimbreTransfer", x: 260, widgets: { model: "rave-v1", fidelity: 0.85 } },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  AudioToMIDI: {
    title: "Audio to MIDI",
    description: "Transcribe pitched audio to MIDI.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "AudioToMIDI", x: 260, widgets: { model: "basic-pitch" } }],
    links: [link("l1", "n1", "n2", "AUDIO")],
  },
  DeepfakeDetect: {
    title: "Deepfake Detect",
    description: "Run spoof detection; route authenticity report and audio pass-through.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "DeepfakeDetect", x: 260, widgets: { model: "rawnet2-asvspoof", threshold: 0.5 } },
      { id: "n3", type: "AuthenticitySummary", x: 520, y: 80, widgets: { spoof_threshold: 0.5 } },
      preview("n4", 520, -80),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n3", "AUTHENTICITY", 0, 1),
      link("l3", "n2", "n4", "AUDIO", 1, 0),
    ],
  },
  EmbedWatermark: {
    title: "Embed Watermark",
    description: "Embed an imperceptible AudioSeal watermark with a 16-bit payload.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      {
        id: "n2",
        type: "EmbedWatermark",
        x: 260,
        widgets: { model: "audioseal-16bit", message_id: 42, strength: 1.0 },
      },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  DetectWatermark: {
    title: "Detect Watermark",
    description: "Detect AudioSeal watermark probability and decode payload.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "DetectWatermark", x: 260, widgets: { model: "audioseal-16bit", threshold: 0.5 } },
      preview("n3", 520, -80),
      preview("n4", 520, 80),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n3", "AUDIO", 1, 0),
      link("l3", "n2", "n4", "TEXT", 0, 1),
    ],
  },
  MIDIToAudio: {
    title: "MIDI to Audio",
    description: "Synthesize audio from MIDI melody.",
    focusNodeId: "n2",
    nodes: [
      { id: "n1", type: "LoadMIDI", x: 0, widgets: { path: MIDI_SAMPLE, midi_kind: "performance" } },
      { id: "n2", type: "MIDIToAudio", x: 260, widgets: { model: "musicgen-melody-small", prompt: "playful melody" } },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "MIDI"), link("l2", "n2", "n3", "AUDIO")],
  },
  GenerateAudio: {
    title: "Generate Audio",
    description: "Text-to-music with MusicGen.",
    focusNodeId: "n2",
    nodes: [
      { id: "n1", type: "Prompt", x: 0, widgets: { text: "warm lo-fi beat with soft piano" } },
      {
        id: "n2",
        type: "GenerateAudio",
        x: 260,
        widgets: { model: "musicgen-small", prompt: "warm lo-fi beat with soft piano", seed: -1 },
      },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "TEXT"), link("l2", "n2", "n3", "AUDIO")],
  },
  Video2Audio: {
    title: "Video to Audio",
    description:
      "Generic video→audio node (Diff-Foley is the example default). Browse Model Browser for alternative models.",
    focusNodeId: "n1",
    nodes: [
      {
        id: "n1",
        type: "Video2Audio",
        x: 0,
        widgets: {
          model: "diff-foley",
          path: "assets/samples/video480p.mov",
          prompt: "footsteps on wet pavement, light rain, distant traffic",
          duration: 8,
          seed: -1,
        },
      },
      preview("n2", 280),
      {
        id: "n3",
        type: "MuxVideo",
        x: 280,
        y: 140,
        widgets: { path: "assets/samples/video480p.mov" },
      },
      { id: "n4", type: "PreviewVideo", x: 560, y: 140, widgets: {} },
      {
        id: "n5",
        type: "SaveVideo",
        x: 560,
        y: 280,
        widgets: { path: "exports", filename: "video2audio.mp4" },
      },
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n1", "n3", "AUDIO"),
      link("l3", "n3", "n4", "VIDEO"),
      link("l4", "n4", "n5", "VIDEO"),
    ],
  },
  SingFromMIDI: {
    title: "Sing from MIDI",
    description: "Singing synthesis from MIDI melody and lyrics.",
    focusNodeId: "n3",
    nodes: [
      { id: "n1", type: "LoadMIDI", x: 0, widgets: { path: MIDI_SAMPLE, midi_kind: "performance" } },
      { id: "n2", type: "Prompt", x: 0, y: 120, widgets: { text: "la la la groovy melody" } },
      { id: "n3", type: "SingFromMIDI", x: 280, widgets: { model: "diffsinger-opencpop" } },
      preview("n4", 540),
    ],
    links: [
      link("l1", "n1", "n3", "MIDI", 0, 0),
      link("l2", "n2", "n3", "TEXT", 0, 1),
      link("l3", "n3", "n4", "AUDIO"),
    ],
  },
  SeparateToObjects: {
    title: "Separate to Objects",
    description: "Stem separation into spatial objects.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "SeparateToObjects", x: 260, widgets: { model: "demucs-v4-objects" } },
      { id: "n3", type: "RenderObjectScene", x: 520, widgets: { output: "stereo" } },
      preview("n4", 780),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "OBA"), link("l3", "n3", "n4", "AUDIO")],
  },
  VerifyProvenance: {
    title: "Verify Provenance",
    description: "Check provenance sidecar on loaded audio.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "VerifyProvenance", x: 260, widgets: { check_sidecar: true } }],
    links: [link("l1", "n1", "n2", "AUDIO")],
  },
  VerifySamples: {
    title: "Verify Samples",
    description: "Check PCM content hash, sample rate, frames, and layout on a cached buffer.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "VerifySamples", x: 260, widgets: {} },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO", 1, 0)],
  },
  Meter: {
    title: "Meter",
    description:
      "Multi-channel peak/RMS levels (auto from inlet + FOA/HOA meta) with AUDIO or AMBISONICS passthrough.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "Meter", x: 260, widgets: { layout: "auto", edge_fraction: 0.05 } },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO", 0, 0)],
  },
  AuthenticitySummary: {
    title: "Authenticity Summary",
    description: "Combine provenance and spoof checks.",
    focusNodeId: "n4",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "VerifyProvenance", x: 260, y: -80, widgets: { check_sidecar: true } },
      { id: "n3", type: "DeepfakeDetect", x: 260, y: 80, widgets: { model: "rawnet2-asvspoof", threshold: 0.5 } },
      { id: "n4", type: "AuthenticitySummary", x: 520, widgets: { spoof_threshold: 0.5 } },
      preview("n5", 780),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n1", "n3", "AUDIO"),
      link("l3", "n2", "n4", "AUTHENTICITY", 0, 0),
      link("l4", "n3", "n4", "AUTHENTICITY", 0, 1),
      link("l5", "n1", "n5", "AUDIO"),
    ],
  },
  AmbisonicEncode: {
    title: "Ambisonic Encode",
    description: "Encode mono audio to first-order ambisonics.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "AmbisonicEncode", x: 260, widgets: { order: 1 } }, { id: "n3", type: "AmbisonicDecode", x: 520, widgets: { layout: "stereo" } }, preview("n4", 780)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AMBISONICS"), link("l3", "n3", "n4", "AUDIO")],
  },
  TrajectoryAuthor: {
    title: "Trajectory Author",
    description: "Author XYZ trajectory locked to audio, upmix to FOA, extract DOA, decode.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      {
        id: "n2",
        type: "TrajectoryAuthor",
        x: 260,
        y: 140,
        widgets: {
          start_x: 0.707,
          start_y: 0,
          start_z: 0.707,
          end_x: -0.707,
          end_y: 0,
          end_z: 0.707,
        },
      },
      { id: "n7", type: "TrajectoryMonitor", x: 520, y: 140, widgets: { role: "input", label: "Input XYZ" } },
      { id: "n3", type: "AmbisonicUpmix", x: 780, widgets: { model: "helix-v0.7" } },
      { id: "n4", type: "AmbisonicTrajectoryExtract", x: 1040, y: 140, widgets: { model: "dcase-seld-foa-multiaccdoa" } },
      { id: "n8", type: "TrajectoryMonitor", x: 1300, y: 140, widgets: { role: "output", label: "Output XYZ" } },
      { id: "n5", type: "AmbisonicDecode", x: 1040, widgets: { layout: "stereo" } },
      preview("n6", 1300),
    ],
    links: [
      link("l1", "n1", "n3", "AUDIO"),
      link("l1b", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n7", "TRAJECTORY"),
      link("l2c", "n7", "n3", "TRAJECTORY", 0, 1),
      link("l3", "n3", "n4", "AMBISONICS"),
      link("l4", "n3", "n5", "AMBISONICS"),
      link("l5", "n5", "n6", "AUDIO"),
      link("l6", "n4", "n8", "TRAJECTORY"),
    ],
  },
  TrajectoryMonitor: {
    title: "Trajectory Monitor",
    description: "Monitor an XYZ trajectory on canvas (input or output role).",
    focusNodeId: "n7",
    nodes: [
      load("n1", 0),
      {
        id: "n2",
        type: "TrajectoryAuthor",
        x: 260,
        y: 140,
        widgets: {
          start_x: 0.707,
          start_y: 0,
          start_z: 0.707,
          end_x: -0.707,
          end_y: 0,
          end_z: 0.707,
        },
      },
      { id: "n7", type: "TrajectoryMonitor", x: 520, y: 140, widgets: { role: "input", label: "Input XYZ" } },
      { id: "n3", type: "AmbisonicUpmix", x: 780, widgets: { model: "helix-v0.7" } },
    ],
    links: [
      link("l1", "n1", "n3", "AUDIO"),
      link("l1b", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n7", "TRAJECTORY"),
      link("l2c", "n7", "n3", "TRAJECTORY", 0, 1),
    ],
  },
  AmbisonicUpmix: {
    title: "Ambisonic Upmix",
    description: "Neural mono/stereo to FOA with optional trajectory conditioning.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      {
        id: "n2",
        type: "TrajectoryAuthor",
        x: 260,
        y: 140,
        widgets: { start_x: 0.707, start_z: 0.707, end_x: -0.707, end_z: 0.707 },
      },
      { id: "n7", type: "TrajectoryMonitor", x: 520, y: 140, widgets: { role: "input", label: "Input XYZ" } },
      { id: "n3", type: "AmbisonicUpmix", x: 780, widgets: { model: "helix-v0.7" } },
      { id: "n4", type: "AmbisonicDecode", x: 1040, widgets: { layout: "stereo" } },
      preview("n5", 1300),
    ],
    links: [
      link("l1", "n1", "n3", "AUDIO"),
      link("l1b", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n7", "TRAJECTORY"),
      link("l2c", "n7", "n3", "TRAJECTORY", 0, 1),
      link("l3", "n3", "n4", "AMBISONICS"),
      link("l4", "n4", "n5", "AUDIO"),
    ],
  },
  BinauralRender: {
    title: "Binaural Render",
    description: "Stereo → binaural headphones (hrtf-binaural-v0 stub; no applicable open neural model yet).",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "BinauralRender", x: 260, widgets: { model: "hrtf-binaural-v0", strength: 0.45 } },
      preview("n3", 520),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AUDIO")],
  },
  SpatialUpmix: {
    title: "Spatial Upmix",
    description: "Stereo → Atmos 7.1.4 bed (stereo-atmos-bed-v0 stub; no applicable open neural model yet).",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "SpatialUpmix", x: 260, widgets: { model: "stereo-atmos-bed-v0", layout: "7.1.4" } },
      { id: "n3", type: "ChannelConvert", x: 520, widgets: { layout: "stereo" } },
      preview("n4", 780),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n3", "AUDIO"),
      link("l3", "n3", "n4", "AUDIO"),
    ],
  },
  AmbisonicTrajectoryExtract: {
    title: "Ambisonic Trajectory Extract",
    description: "Recover XYZ DOA trajectory from FOA Ambisonics.",
    focusNodeId: "n4",
    nodes: [
      load("n1", 0),
      {
        id: "n2",
        type: "TrajectoryAuthor",
        x: 260,
        y: 140,
        widgets: { start_x: 0.707, start_z: 0.707, end_x: -0.707, end_z: 0.707 },
      },
      { id: "n7", type: "TrajectoryMonitor", x: 520, y: 140, widgets: { role: "input", label: "Input XYZ" } },
      { id: "n3", type: "AmbisonicUpmix", x: 780, widgets: { model: "helix-v0.7" } },
      { id: "n4", type: "AmbisonicTrajectoryExtract", x: 1040, widgets: { model: "dcase-seld-foa-multiaccdoa" } },
      { id: "n8", type: "TrajectoryMonitor", x: 1300, y: 140, widgets: { role: "output", label: "Output XYZ" } },
      { id: "n5", type: "AmbisonicDecode", x: 1040, y: 280, widgets: { layout: "stereo" } },
      preview("n6", 1300),
    ],
    links: [
      link("l1", "n1", "n3", "AUDIO"),
      link("l1b", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n7", "TRAJECTORY"),
      link("l2c", "n7", "n3", "TRAJECTORY", 0, 1),
      link("l3", "n3", "n4", "AMBISONICS"),
      link("l4", "n3", "n5", "AMBISONICS"),
      link("l5", "n5", "n6", "AUDIO"),
      link("l6", "n4", "n8", "TRAJECTORY"),
    ],
  },
  AmbisonicDecode: {
    title: "Ambisonic Decode",
    description: "Decode FOA ambisonics to stereo.",
    focusNodeId: "n3",
    nodes: [load("n1", 0), { id: "n2", type: "AmbisonicEncode", x: 260, widgets: { order: 1 } }, { id: "n3", type: "AmbisonicDecode", x: 520, widgets: { layout: "stereo" } }, preview("n4", 780)],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "AMBISONICS"), link("l3", "n3", "n4", "AUDIO")],
  },
  AmbisonicRotate: {
    title: "Ambisonic Rotate",
    description: "Rotate ambisonic soundfield for VR preview.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "AmbisonicEncode", x: 260, widgets: { order: 1 } },
      { id: "n3", type: "AmbisonicRotate", x: 520, widgets: { yaw: 45 } },
      { id: "n4", type: "AmbisonicDecode", x: 780, widgets: { layout: "stereo" } },
      preview("n5", 1040),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n3", "AMBISONICS"),
      link("l3", "n3", "n4", "AMBISONICS"),
      link("l4", "n4", "n5", "AUDIO"),
    ],
  },
  ObjectFromAudio: {
    title: "Object from Audio",
    description: "Wrap audio as a spatial object.",
    focusNodeId: "n2",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "ObjectFromAudio", x: 260, widgets: { name: "Dialogue", azimuth: -30, elevation: 0 } },
      { id: "n3", type: "RenderObjectScene", x: 520, widgets: { output: "stereo" } },
      preview("n4", 780),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "OBA"), link("l3", "n3", "n4", "AUDIO")],
  },
  ObjectPlacement: {
    title: "Object Placement",
    description: "Auto-place separated stems in a scene.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "SeparateToObjects", x: 260, widgets: { model: "demucs-v4-objects" } },
      { id: "n3", type: "ObjectPlacement", x: 520, widgets: { model: "object-placement-heuristic", spread_deg: 90 } },
      { id: "n4", type: "RenderObjectScene", x: 780, widgets: { output: "stereo" } },
      preview("n5", 1040),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n3", "OBA"),
      link("l3", "n3", "n4", "OBA"),
      link("l4", "n4", "n5", "AUDIO"),
    ],
  },
  ObjectMerge: {
    title: "Object Merge",
    description: "Merge two spatial objects into one scene.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "ObjectFromAudio", x: 260, y: -80, widgets: { name: "Left", azimuth: -30 } },
      { id: "n3", type: "ObjectMerge", x: 520, widgets: {} },
      { id: "n4", type: "ObjectFromAudio", x: 260, y: 80, widgets: { name: "Right", azimuth: 30 } },
      { id: "n5", type: "RenderObjectScene", x: 780, widgets: { output: "stereo" } },
      preview("n6", 1040),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n1", "n4", "AUDIO"),
      link("l3", "n2", "n3", "OBA", 0, 0),
      link("l4", "n4", "n3", "OBA", 0, 1),
      link("l5", "n3", "n5", "OBA"),
      link("l6", "n5", "n6", "AUDIO"),
    ],
  },
  ObjectAnimate: {
    title: "Object Animate",
    description: "Animate object position over time.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "ObjectFromAudio", x: 260, widgets: { name: "Moving", azimuth: 0 } },
      { id: "n3", type: "ObjectAnimate", x: 520, widgets: { azimuth_start: -30, azimuth_end: 30 } },
      { id: "n4", type: "RenderObjectScene", x: 780, widgets: { output: "stereo" } },
      preview("n5", 1040),
    ],
    links: [
      link("l1", "n1", "n2", "AUDIO"),
      link("l2", "n2", "n3", "OBA"),
      link("l3", "n3", "n4", "OBA"),
      link("l4", "n4", "n5", "AUDIO"),
    ],
  },
  RenderObjectScene: {
    title: "Render Object Scene",
    description: "Render an object scene to channelized audio.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "ObjectFromAudio", x: 260, widgets: { name: "Dialogue", azimuth: 0 } },
      { id: "n3", type: "RenderObjectScene", x: 520, widgets: { output: "stereo" } },
      preview("n4", 780),
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "OBA"), link("l3", "n3", "n4", "AUDIO")],
  },
  MIDIInDevice: {
    title: "MIDI In Device",
    description: "Capture MIDI from a device and synthesize.",
    focusNodeId: "n1",
    nodes: [
      { id: "n1", type: "MIDIInDevice", x: 0, widgets: { device_id: "virtual:in-demo", mode: "performance" } },
      { id: "n2", type: "MIDIToAudio", x: 280, widgets: { model: "musicgen-melody-small", prompt: "keyboard melody" } },
      preview("n3", 560),
    ],
    links: [link("l1", "n1", "n2", "MIDI"), link("l2", "n2", "n3", "AUDIO")],
  },
  MIDIOutDevice: {
    title: "MIDI Out Device",
    description: "Transcribe audio to MIDI and stream to hardware.",
    focusNodeId: "n3",
    nodes: [
      load("n1", 0),
      { id: "n2", type: "AudioToMIDI", x: 260, widgets: { model: "basic-pitch" } },
      { id: "n3", type: "MIDIOutDevice", x: 520, widgets: { device_id: "virtual:out-demo", mode: "stream" } },
    ],
    links: [link("l1", "n1", "n2", "AUDIO"), link("l2", "n2", "n3", "MIDI")],
  },
  OSCInLive: {
    title: "OSC In Live",
    description: "Capture live OSC into a buffer.",
    focusNodeId: "n1",
    nodes: [{ id: "n1", type: "OSCInLive", x: 0, widgets: { sample_rate: 48000, frame_count: 48000 } }],
    links: [],
  },
  ModuleInlet: {
    title: "Module Inlet",
    description: "Subgraph input boundary passthrough.",
    focusNodeId: "n2",
    nodes: [load("n1", 0), { id: "n2", type: "ModuleInlet", x: 260, widgets: { name: "audio_in" } }, preview("n3", 520)],
    links: [link("l1", "n1", "n2", "AUDIO", 0, 0), link("l2", "n2", "n3", "AUDIO")],
  },
  ModuleOutlet: {
    title: "Module Outlet",
    description: "Subgraph output boundary.",
    focusNodeId: "n3",
    nodes: [load("n1", 0), { id: "n2", type: "ModuleInlet", x: 260, widgets: { name: "audio_in" } }, { id: "n3", type: "ModuleOutlet", x: 520, widgets: { name: "audio_out" } }],
    links: [link("l1", "n1", "n2", "AUDIO", 0, 0), link("l2", "n2", "n3", "AUDIO")],
  },
};

const PATCH_X_STEP = 260;
const PATCH_Y_STEP = 140;

/** Terminal nodes — Tab wires upstream only, not another chain leg downstream. */
const SKIP_DOWNSTREAM_TYPES = new Set(["Preview", "SaveAudio", "ModuleOutlet", "WhisperSTT"]);

/** Text outputs are terminal in v1 — no auto downstream chain. */
const SKIP_DOWNSTREAM_OUTPUT_TYPES = new Set(["TEXT", "STRING"]);

type SocketWithSlot = { name: string; type: string; optional?: boolean; slot: number };

function wireableInputsWithSlots(schema: NodeSchema): SocketWithSlot[] {
  return schema.inputs
    .map((socket, slot) => ({ ...socket, slot }))
    .filter((socket) => isWireableInput(socket));
}

function inputsToWire(schema: NodeSchema): SocketWithSlot[] {
  return wireableInputsWithSlots(schema);
}

function nextPatchNodeId(nodes: PatchNode[]): string {
  let max = 0;
  for (const node of nodes) {
    const match = /^n(\d+)$/.exec(node.id);
    if (match) max = Math.max(max, Number(match[1]));
  }
  return `n${max + 1}`;
}

function nextAugmentPatchNodeId(patchNodes: PatchNode[], reservedIds: Set<string>): string {
  let candidate = nextPatchNodeId(patchNodes);
  while (reservedIds.has(candidate)) {
    const match = /^n(\d+)$/.exec(candidate);
    candidate = match ? `n${Number(match[1]) + 1}` : `_${candidate}`;
  }
  reservedIds.add(candidate);
  return candidate;
}

function appendSourceForInput(
  input: SocketWithSlot,
  patchNodes: PatchNode[],
  links: PatchLink[],
  focusNodeId: string,
  focusPos: { x: number; y: number },
  inputIndex: number,
  linkIndex: { value: number },
): void {
  const reservedIds = new Set([focusNodeId]);
  const sourceY = focusPos.y + inputIndex * PATCH_Y_STEP;
  const sourceX = focusPos.x - PATCH_X_STEP;

  if (input.type === "AUDIO") {
    const sourceId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({ id: sourceId, type: "LoadAudio", x: sourceX, y: sourceY, widgets: { path: SAMPLE } });
    links.push(link(`l${linkIndex.value++}`, sourceId, focusNodeId, "AUDIO", 0, input.slot));
    return;
  }
  if (input.type === "MIDI") {
    const sourceId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({
      id: sourceId,
      type: "LoadMIDI",
      x: sourceX,
      y: sourceY,
      widgets: { path: MIDI_SAMPLE, midi_kind: "performance" },
    });
    links.push(link(`l${linkIndex.value++}`, sourceId, focusNodeId, "MIDI", 0, input.slot));
    return;
  }
  if (input.type === "TEXT") {
    const sourceId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({
      id: sourceId,
      type: "Prompt",
      x: sourceX,
      y: sourceY,
      widgets: { text: "Example prompt for generation." },
    });
    links.push(link(`l${linkIndex.value++}`, sourceId, focusNodeId, "TEXT", 0, input.slot));
    return;
  }
  if (input.type === "AUTOMATION") {
    const sourceId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({
      id: sourceId,
      type: "ControlCurve",
      x: sourceX,
      y: sourceY,
      widgets: { start_value: 0.25 + inputIndex * 0.2, end_value: 0.75 + inputIndex * 0.1 },
    });
    links.push(link(`l${linkIndex.value++}`, sourceId, focusNodeId, "AUTOMATION", 0, input.slot));
    return;
  }
  if (input.type === "AUTHENTICITY") {
    const loadId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({ id: loadId, type: "LoadAudio", x: sourceX - PATCH_X_STEP, y: sourceY, widgets: { path: SAMPLE } });
    const verifyId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({
      id: verifyId,
      type: "VerifyProvenance",
      x: sourceX,
      y: sourceY,
      widgets: { check_sidecar: true },
    });
    links.push(link(`l${linkIndex.value++}`, loadId, verifyId, "AUDIO"));
    links.push(link(`l${linkIndex.value++}`, verifyId, focusNodeId, "AUTHENTICITY", 0, input.slot));
    return;
  }
  if (input.type === "STEMS") {
    return;
  }
  if (input.type === "AMBISONICS") {
    const loadId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({ id: loadId, type: "LoadAudio", x: sourceX - PATCH_X_STEP, y: sourceY, widgets: { path: SAMPLE } });
    const encId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({ id: encId, type: "AmbisonicEncode", x: sourceX, y: sourceY, widgets: { order: 1 } });
    links.push(link(`l${linkIndex.value++}`, loadId, encId, "AUDIO"));
    links.push(link(`l${linkIndex.value++}`, encId, focusNodeId, "AMBISONICS", 0, input.slot));
    return;
  }
  if (input.type === "TRAJECTORY") {
    const trajId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({
      id: trajId,
      type: "TrajectoryAuthor",
      x: sourceX,
      y: sourceY,
      widgets: {
        start_x: 0.707,
        start_y: 0,
        start_z: 0.707,
        end_x: -0.707,
        end_y: 0,
        end_z: 0.707,
        duration_sec: 1,
      },
    });
    links.push(link(`l${linkIndex.value++}`, trajId, focusNodeId, "TRAJECTORY", 0, input.slot));
    return;
  }
  if (input.type === "OBA") {
    const loadId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({ id: loadId, type: "LoadAudio", x: sourceX - PATCH_X_STEP, y: sourceY, widgets: { path: SAMPLE } });
    const objId = nextAugmentPatchNodeId(patchNodes, reservedIds);
    patchNodes.push({
      id: objId,
      type: "ObjectFromAudio",
      x: sourceX,
      y: sourceY,
      widgets: { name: "Object", azimuth: 0 },
    });
    links.push(link(`l${linkIndex.value++}`, loadId, objId, "AUDIO"));
    links.push(link(`l${linkIndex.value++}`, objId, focusNodeId, "OBA", 0, input.slot));
  }
}

function appendSinkForOutput(
  output: { name: string; type: string },
  outputSlot: number,
  patchNodes: PatchNode[],
  links: PatchLink[],
  focusNodeId: string,
  focusPos: { x: number; y: number },
  outputIndex: number,
  linkIndex: { value: number },
): void {
  const reservedIds = new Set([focusNodeId]);
  const sinkX = focusPos.x + PATCH_X_STEP;
  const sinkY = focusPos.y + outputIndex * PATCH_Y_STEP;
  // Legacy STEMS bundle — SeparateStems now exposes per-stem AUDIO outs; no sink node.
  if (output.type === "STEMS") {
    return;
  }
  const sinkId = nextAugmentPatchNodeId(patchNodes, reservedIds);

  if (output.type === "AUDIO") {
    patchNodes.push({ id: sinkId, type: "Preview", x: sinkX, y: sinkY, widgets: {} });
    links.push(link(`l${linkIndex.value++}`, focusNodeId, sinkId, "AUDIO", outputSlot, 0));
    return;
  }
  if (output.type === "AUTHENTICITY") {
    patchNodes.push({ id: sinkId, type: "AuthenticitySummary", x: sinkX, y: sinkY, widgets: { spoof_threshold: 0.5 } });
    links.push(link(`l${linkIndex.value++}`, focusNodeId, sinkId, "AUTHENTICITY", outputSlot, 1));
    return;
  }
  if (output.type === "MIDI") {
    patchNodes.push({ id: sinkId, type: "MIDIToFloat", x: sinkX, y: sinkY, widgets: { cc: 7, default_value: 0.75 } });
    links.push(link(`l${linkIndex.value++}`, focusNodeId, sinkId, "MIDI", outputSlot, 0));
    return;
  }
  if (output.type === "AUTOMATION") {
    patchNodes.push({ id: sinkId, type: "FloatRoute", x: sinkX, y: sinkY, widgets: { select: 0.5 } });
    links.push(link(`l${linkIndex.value++}`, focusNodeId, sinkId, "AUTOMATION", outputSlot, 0));
  }
}

function workflowToPatchRecipe(patch: MinimalPatch): PatchRecipe {
  const workflow = patch.workflow;
  return {
    title: workflow.metadata.title,
    description: workflow.metadata.description ?? "",
    focusNodeId: patch.focusNodeId,
    nodes: workflow.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      x: node.pos?.x ?? 0,
      y: node.pos?.y ?? 0,
      widgets: node.widgets,
    })),
    links: workflow.links.map((edge) => ({
      id: edge.id,
      from: edge.from as [string, number],
      to: edge.to as [string, number],
      type: edge.type,
    })),
  };
}

function ensureSchemaIoWiring(patch: MinimalPatch, schema: NodeSchema): MinimalPatch {
  const recipe = workflowToPatchRecipe(patch);
  const focusNode = recipe.nodes.find((node) => node.id === recipe.focusNodeId);
  if (!focusNode) return patch;

  const focusPos = { x: focusNode.x, y: focusNode.y ?? 0 };
  const linkIndex = { value: recipe.links.length + 1 };
  const wiredInputSlots = new Set(recipe.links.filter((edge) => edge.to[0] === recipe.focusNodeId).map((edge) => edge.to[1]));
  const wiredOutputSlots = new Set(
    recipe.links.filter((edge) => edge.from[0] === recipe.focusNodeId).map((edge) => edge.from[1]),
  );

  inputsToWire(schema).forEach((input, index) => {
    if (wiredInputSlots.has(input.slot)) return;
    appendSourceForInput(input, recipe.nodes, recipe.links, recipe.focusNodeId, focusPos, index, linkIndex);
  });

  schema.outputs.forEach((output, slot) => {
    if (wiredOutputSlots.has(slot)) return;
    appendSinkForOutput(output, slot, recipe.nodes, recipe.links, recipe.focusNodeId, focusPos, slot, linkIndex);
  });

  return define(recipe);
}

function genericPatch(nodeType: string, schema: NodeSchema): MinimalPatch | null {
  if (inputsToWire(schema).length === 0 && schema.outputs.length === 0) {
    return null;
  }
  const skeleton = define({
    title: nodeType,
    description: schema.description ?? `Minimal ${nodeType} example.`,
    focusNodeId: "n1",
    nodes: [{ id: "n1", type: nodeType, x: PATCH_X_STEP, y: 0, widgets: {} }],
    links: [],
  });
  return ensureSchemaIoWiring(skeleton, schema);
}

function ioSpecForAugment(
  schema: NodeSchema | undefined,
  patch: MinimalPatch,
): { inputs: SocketWithSlot[]; outputs: Array<{ slot: number; type: string }> } {
  if (schema) {
    return {
      inputs: inputsToWire(schema),
      outputs: schema.outputs.map((output, slot) => ({ slot, type: output.type })),
    };
  }
  const focusId = patch.focusNodeId;
  const inputs: SocketWithSlot[] = [];
  const outputs: Array<{ slot: number; type: string }> = [];
  for (const edge of patch.workflow.links) {
    if (edge.to[0] === focusId) {
      inputs.push({ name: `in_${edge.to[1]}`, type: edge.type, slot: edge.to[1] });
    }
    if (edge.from[0] === focusId) {
      outputs.push({ slot: edge.from[1], type: edge.type });
    }
  }
  return { inputs, outputs };
}

function mergeAugmentFragment(
  workflow: Workflow,
  _focusNodeId: string,
  tempNodes: PatchNode[],
  tempLinks: PatchLink[],
): Workflow {
  if (tempNodes.length === 0) return workflow;

  const fragmentNodes: WorkflowNode[] = tempNodes.map((node) => ({
    id: node.id,
    type: node.type,
    pos: { x: node.x, y: node.y ?? 0 },
    widgets: node.widgets ?? {},
  }));
  const fragmentLinks: WorkflowLink[] = tempLinks.map((edge) => ({
    id: edge.id,
    from: edge.from as [string, number],
    to: edge.to as [string, number],
    type: edge.type,
  }));

  const stub: Workflow = {
    schema_version: workflow.schema_version,
    groovy_version: workflow.groovy_version,
    id: workflow.id,
    metadata: workflow.metadata,
    nodes: fragmentNodes,
    links: fragmentLinks,
    groups: [],
  };
  const idMap = allocatePatchNodeIdMap(workflow, stub);
  const mapEndpoint = (id: string) => (idMap.has(id) ? idMap.get(id)! : id);

  let placedWorkflow = workflow;
  const newNodes: WorkflowNode[] = [];
  for (const node of fragmentNodes) {
    const size = estimateNodeSize(node);
    const center = {
      x: (node.pos?.x ?? 0) + size.width / 2,
      y: (node.pos?.y ?? 0) + size.height / 2,
    };
    const pos = findOpenNodePosition(placedWorkflow, center, size);
    const placed = {
      ...node,
      id: idMap.get(node.id)!,
      pos,
    };
    newNodes.push(placed);
    placedWorkflow = { ...placedWorkflow, nodes: [...placedWorkflow.nodes, placed] };
  }
  const newLinks = fragmentLinks
    .map((edge) => {
      const fromId = mapEndpoint(edge.from[0]);
      const toId = mapEndpoint(edge.to[0]);
      return {
        id: `aug_${fromId}_${toId}_${edge.from[1]}_${edge.to[1]}`,
        from: [fromId, edge.from[1]] as [string, number],
        to: [toId, edge.to[1]] as [string, number],
        type: edge.type,
      };
    })
    .filter(
      (edge) =>
        !placedWorkflow.links.some((link) => link.to[0] === edge.to[0] && link.to[1] === edge.to[1]),
    );

  if (newNodes.length === 0 && newLinks.length === 0) return workflow;

  return {
    ...workflow,
    nodes: [...workflow.nodes, ...newNodes],
    links: [...workflow.links, ...newLinks],
  };
}

/** Add only missing upstream/downstream example nodes; keep the selected node in place. */
export function augmentNodeWithExample(
  workflow: Workflow,
  selectedNodeId: string,
  schema: NodeSchema | undefined,
  patch: MinimalPatch,
): { workflow: Workflow; focusNodeId: string; changed: boolean } {
  const anchor = workflow.nodes.find((node) => node.id === selectedNodeId);
  if (!anchor) {
    return { workflow, focusNodeId: selectedNodeId, changed: false };
  }

  const io = ioSpecForAugment(schema, patch);
  const isInputWired = (wf: Workflow, slot: number) =>
    wf.links.some((link) => link.to[0] === selectedNodeId && link.to[1] === slot);
  const isOutputWired = (wf: Workflow, slot: number) =>
    wf.links.some((link) => link.from[0] === selectedNodeId && link.from[1] === slot);

  const focusPos = anchor.pos ?? { x: 0, y: 0 };
  let next = workflow;
  let changed = false;
  let inputIndex = 0;

  for (const input of io.inputs) {
    if (isInputWired(next, input.slot)) continue;
    const tempNodes: PatchNode[] = [];
    const tempLinks: PatchLink[] = [];
    appendSourceForInput(
      input,
      tempNodes,
      tempLinks,
      selectedNodeId,
      focusPos,
      inputIndex,
      { value: 1 },
    );
    if (tempNodes.length === 0) continue;
    const merged = mergeAugmentFragment(next, selectedNodeId, tempNodes, tempLinks);
    if (merged !== next) {
      next = merged;
      changed = true;
    }
    inputIndex += 1;
  }

  for (const output of io.outputs) {
    if (SKIP_DOWNSTREAM_TYPES.has(anchor.type)) continue;
    if (SKIP_DOWNSTREAM_OUTPUT_TYPES.has(output.type)) continue;
    if (isOutputWired(next, output.slot)) continue;
    const tempNodes: PatchNode[] = [];
    const tempLinks: PatchLink[] = [];
    appendSinkForOutput(
      { name: `output_${output.slot}`, type: output.type },
      output.slot,
      tempNodes,
      tempLinks,
      selectedNodeId,
      focusPos,
      output.slot,
      { value: 1 },
    );
    if (tempNodes.length === 0) continue;
    const merged = mergeAugmentFragment(next, selectedNodeId, tempNodes, tempLinks);
    if (merged !== next) {
      next = merged;
      changed = true;
    }
  }

  return { workflow: next, focusNodeId: selectedNodeId, changed };
}

export function hasMinimalPatch(nodeType: string, schemas: Record<string, NodeSchema> = {}): boolean {
  return Boolean(PATCH_RECIPES[nodeType] ?? schemas[nodeType]);
}

export function getMinimalPatch(nodeType: string, schemas: Record<string, NodeSchema> = {}): MinimalPatch | null {
  const schema = schemas[nodeType];
  const recipe = PATCH_RECIPES[nodeType];
  let patch = recipe ? define(recipe) : schema ? genericPatch(nodeType, schema) : null;
  if (patch && schema) {
    patch = ensureSchemaIoWiring(patch, schema);
  }
  return patch;
}
