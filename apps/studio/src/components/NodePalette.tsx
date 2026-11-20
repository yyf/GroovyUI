import { useEffect, useMemo, useState } from "react";
import { API, fetchNodeSchema } from "../api";
import { DEFAULT_LOAD_AUDIO_PATH } from "../sampleDefaults";
import { isNodeVisibleInStudio } from "../templateUi";

type NodeTypeInfo = { type: string; category: string };

type PaletteTier = "ai" | "core" | "modular" | "all";

type GroupId =
  | "core-io"
  | "core-dsp"
  | "ai-generate"
  | "ai-transform"
  | "ai-analyze"
  | "authenticity"
  | "control"
  | "subgraph";

type Props = {
  onAddNode: (nodeType: string) => void;
  /** Live /api/nodes catalog from App — keeps BeatTrack etc. in sync after server restart. */
  catalog?: NodeTypeInfo[];
  /** Studio dev mode — show full palette; otherwise only nodes used by ISMIR demo templates. */
  studioDevMode?: boolean;
};

/** Control-rate + modular synth building blocks (shown in Modular / All tiers). */
export const MODULAR_NODES = new Set([
  "LoadMIDI",
  "SignalGenerator",
  "NoiseGenerator",
  "Oscillator",
  "MatrixMixer",
  "Filter",
  "Amplifier",
  "Envelope",
  "LFO",
  "Attenuator",
  "Reverb",
  "Logic",
  "Comparator",
  "SampleAndHold",
  "Quantizer",
  "Clock",
  "BeatTrack",
  "ControlCurve",
  "MIDIToFloat",
  "MIDINoteGate",
  "AutomationApply",
  "AutomationToMIDI",
  "Float",
  "FloatMath",
  "FloatRoute",
  "Granulate",
  "ModuleInlet",
  "ModuleOutlet",
]);

/** Immersive + Live I/O + subgraph boundaries are deprioritized — hide from the nodes menu. */
const HIDDEN_FROM_PALETTE = new Set([
  "ChannelConvert",
  "Transcode",
  "MultichannelNormalize",
  "AmbisonicEncode",
  "AmbisonicDecode",
  "AmbisonicRotate",
  "ObjectFromAudio",
  "ObjectMerge",
  "ObjectAnimate",
  "RenderObjectScene",
  "ObjectPlacement",
  "SeparateToObjects",
  "TrajectoryAuthor",
  "TrajectoryMonitor",
  "AmbisonicUpmix",
  "AmbisonicTrajectoryExtract",
  "BinauralRender",
  "SpatialUpmix",
  "MIDIInDevice",
  "MIDIOutDevice",
  "OSCInLive",
  "ModuleInlet",
  "ModuleOutlet",
]);

const CORE_IO = new Set([
  "LoadAudio",
  "LoadImage",
  "SwitchImage",
  "SaveAudio",
  "SaveImage",
  "SaveMidi",
  "SaveVideo",
  "SaveGenerateLog",
  "MuxVideo",
  "Preview",
  "PreviewImage",
  "PreviewMidi",
  "PreviewVideo",
  "SynthMidi",
  "Mix",
  "ChannelMerge",
  "Note",
  "Prompt",
]);

const AUTHENTICITY = new Set([
  "VerifyProvenance",
  "AuthenticitySummary",
  "DeepfakeDetect",
  "EmbedWatermark",
  "DetectWatermark",
]);

const CORE_DSP_EXTRA = new Set(["VerifySamples", "Meter"]);

/** Create audio from text / MIDI / prompts (sources). */
const AI_GENERATE = new Set([
  "GenerateAudio",
  "GenerateImage",
  "GenerateMidi",
  "GenerateSpeech",
  "GenerateVideo",
  "MIDIToAudio",
  "SingFromMIDI",
  "Video2Audio",
]);

/** Shape or convert existing audio (processors). */
const AI_TRANSFORM = new Set([
  "Denoise",
  "SeparateStems",
  "VoiceConvert",
  "TimbreTransfer",
  "AmbisonicUpmix",
  "AmbisonicTrajectoryExtract",
  "BinauralRender",
  "SpatialUpmix",
]);

/** Read audio into text / MIDI (analysis — neither generate nor transform). */
const AI_ANALYZE = new Set(["WhisperSTT", "DiarizeTranscribe", "AudioToMIDI"]);

const TIERS: Array<{ id: PaletteTier; label: string; description: string }> = [
  { id: "ai", label: "AI", description: "Generate, transform, analyze, and authenticity nodes." },
  { id: "core", label: "Core", description: "Essential I/O and processing." },
  { id: "modular", label: "Modular", description: "Control wires, MIDI, and synth building blocks." },
  { id: "all", label: "All", description: "AI, core, and modular (immersive / live I/O / subgraph hidden)." },
];

const GROUP_ORDER: GroupId[] = [
  "ai-generate",
  "ai-transform",
  "ai-analyze",
  "authenticity",
  "core-io",
  "core-dsp",
  "control",
  "subgraph",
];

const GROUP_META: Record<GroupId, { title: string; hint: string; tiers: PaletteTier[] }> = {
  "core-io": {
    title: "I/O",
    hint: "Load, save, mix, preview, SynthMidi, notes, prompts",
    tiers: ["core", "all"],
  },
  "core-dsp": {
    title: "Processing",
    hint: "Level, trim, resample, meter, oscillators, sample verify",
    tiers: ["core", "modular", "all"],
  },
  "ai-generate": {
    title: "Generate",
    hint: "Text-to-audio, speech, MIDI-conditioned synth",
    tiers: ["ai", "all"],
  },
  "ai-transform": {
    title: "Transform",
    hint: "Denoise, stems, voice convert",
    tiers: ["ai", "all"],
  },
  "ai-analyze": {
    title: "Analyze",
    hint: "Speech-to-text, audio-to-MIDI",
    tiers: ["ai", "all"],
  },
  authenticity: {
    title: "Authenticity",
    hint: "Provenance verify, deepfake check, watermark",
    tiers: ["ai", "all"],
  },
  control: {
    title: "Control & MIDI",
    hint: "Curves, gates, float math",
    tiers: ["modular", "all"],
  },
  subgraph: {
    title: "Subgraph I/O",
    hint: "Module inlets and outlets",
    tiers: ["modular", "all"],
  },
};

export function isPaletteVisible(node: NodeTypeInfo, studioDevMode = false): boolean {
  if (HIDDEN_FROM_PALETTE.has(node.type)) return false;
  if (node.category.includes("Immersive") || node.category.includes("Live")) return false;
  if (!isNodeVisibleInStudio(node.type, studioDevMode)) return false;
  return true;
}

function tierForNode(node: NodeTypeInfo): PaletteTier[] {
  const tiers: PaletteTier[] = ["all"];
  if (AUTHENTICITY.has(node.type) || node.category.includes("AI")) {
    tiers.push("ai");
    return tiers;
  }
  // Oscillators / noise are both Core sources and Modular synth building blocks.
  if (node.type === "SignalGenerator" || node.type === "Oscillator" || node.type === "NoiseGenerator") {
    tiers.push("core", "modular");
    return tiers;
  }
  if (node.type === "BeatTrack" || node.type === "Clock") {
    tiers.push("core", "modular");
    return tiers;
  }
  // Core I/O MIDI helpers (PreviewMidi / SaveMidi / SynthMidi) stay on Core — not Modular.
  if (CORE_IO.has(node.type) || CORE_DSP_EXTRA.has(node.type)) {
    tiers.push("core");
  }
  if (
    MODULAR_NODES.has(node.type) ||
    node.type.includes("Automation") ||
    node.type === "LoadMIDI" ||
    node.type === "MIDIToFloat" ||
    node.type === "MIDINoteGate" ||
    node.type === "MIDIInDevice" ||
    node.type === "MIDIOutDevice" ||
    node.type === "AutomationToMIDI"
  ) {
    tiers.push("modular");
  }
  if (node.category.includes("Modular")) {
    tiers.push("modular");
  }
  if (node.category.includes("Core") && !MODULAR_NODES.has(node.type) && !CORE_IO.has(node.type)) {
    tiers.push("core");
  }
  return tiers;
}

function aiPaletteGroup(nodeType: string): GroupId {
  if (AI_GENERATE.has(nodeType)) return "ai-generate";
  if (AI_TRANSFORM.has(nodeType)) return "ai-transform";
  if (AI_ANALYZE.has(nodeType)) return "ai-analyze";
  return "ai-transform";
}

function paletteGroup(node: NodeTypeInfo): GroupId {
  if (AUTHENTICITY.has(node.type)) return "authenticity";
  if (CORE_DSP_EXTRA.has(node.type)) return "core-dsp";
  if (node.category.includes("AI")) return aiPaletteGroup(node.type);
  if (node.type === "ModuleInlet" || node.type === "ModuleOutlet") return "subgraph";
  if (node.type === "SignalGenerator" || node.type === "Oscillator" || node.type === "NoiseGenerator") {
    return "core-dsp";
  }
  if (node.type === "BeatTrack") {
    return "core-dsp";
  }
  if (
    MODULAR_NODES.has(node.type) ||
    node.type.includes("Float") ||
    ["Filter", "Amplifier", "Envelope", "LFO", "Attenuator", "Reverb", "Logic", "Comparator", "SampleAndHold", "Quantizer", "Clock", "BeatTrack", "MatrixMixer"].includes(
      node.type,
    )
  ) {
    return "control";
  }
  if (CORE_IO.has(node.type)) return "core-io";
  return "core-dsp";
}

export default function NodePalette({ onAddNode, catalog, studioDevMode = false }: Props) {
  const [fetched, setFetched] = useState<NodeTypeInfo[]>([]);
  const [tier, setTier] = useState<PaletteTier>("ai");

  useEffect(() => {
    if (catalog && catalog.length > 0) return;
    fetch(`${API}/api/nodes`)
      .then((r) => r.json())
      .then((d) => {
        const list = (d.nodes as Array<{ type: string; category: string }>).map((n) => ({
          type: n.type,
          category: n.category,
        }));
        setFetched(list.filter((node) => isPaletteVisible(node, studioDevMode)));
      })
      .catch(() => setFetched([]));
  }, [catalog, studioDevMode]);

  const nodes =
    catalog && catalog.length > 0
      ? catalog.filter((node) => isPaletteVisible(node, studioDevMode))
      : fetched;

  const tierMeta = TIERS.find((item) => item.id === tier) ?? TIERS[0];

  const groupedSections = useMemo(() => {
    const tierNodes =
      tier === "all" ? nodes : nodes.filter((node) => tierForNode(node).includes(tier));

    const buckets = new Map<GroupId, NodeTypeInfo[]>();
    for (const node of tierNodes) {
      const group = paletteGroup(node);
      const meta = GROUP_META[group];
      if (!meta.tiers.includes(tier)) continue;
      const list = buckets.get(group) ?? [];
      list.push(node);
      buckets.set(group, list);
    }

    return GROUP_ORDER.map((groupId) => {
      const items = buckets.get(groupId) ?? [];
      items.sort((a, b) => a.type.localeCompare(b.type));
      return { groupId, meta: GROUP_META[groupId], items };
    }).filter((section) => section.items.length > 0);
  }, [nodes, tier]);

  const totalCount = groupedSections.reduce((sum, section) => sum + section.items.length, 0);

  return (
    <aside className="node-palette">
      <nav className="node-palette__tiers" aria-label="Node palette tier">
        {TIERS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`node-palette__tier${tier === item.id ? " node-palette__tier--active" : ""}`}
            onClick={() => setTier(item.id)}
            aria-current={tier === item.id ? "true" : undefined}
          >
            <span className="node-palette__tier-label">{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="node-palette__tier-panel">
        <header className="node-palette__tier-head">
          <div className="node-palette__tier-title-row">
            <h2 className="node-palette__tier-title">{tierMeta.label}</h2>
            <span className="node-palette__tier-count">{totalCount}</span>
          </div>
          <p className="node-palette__tier-desc">{tierMeta.description}</p>
        </header>

        <div className="node-palette__groups">
          {groupedSections.length === 0 ? (
            <p className="node-palette__empty">No nodes in this tier.</p>
          ) : (
            groupedSections.map(({ groupId, meta, items }) => (
              <section key={groupId} className="node-palette__group">
                <div className="node-palette__group-head">
                  <h3 className="node-palette__group-title">{meta.title}</h3>
                  <span className="node-palette__group-count">{items.length}</span>
                </div>
                <p className="node-palette__group-hint">{meta.hint}</p>
                <ul className="node-palette__list">
                  {items.map((node) => (
                    <li key={node.type}>
                      <button type="button" className="node-palette__node" onClick={() => onAddNode(node.type)}>
                        {node.type}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}

export async function defaultWidgetsForNode(nodeType: string): Promise<Record<string, unknown>> {
  const schema = await fetchNodeSchema(nodeType);
  const widgets: Record<string, unknown> = {};
  for (const w of schema.widgets ?? []) {
    if (w.default !== undefined) widgets[w.name] = w.default;
  }
  if (nodeType === "LoadAudio" && !widgets.path) {
    widgets.path = DEFAULT_LOAD_AUDIO_PATH;
  }
  return widgets;
}
