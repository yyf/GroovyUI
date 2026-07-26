import { useEffect, useMemo, useState } from "react";
import { API, fetchNodeSchema } from "../api";
import { DEFAULT_LOAD_AUDIO_PATH } from "../sampleDefaults";

type NodeTypeInfo = { type: string; category: string };

type PaletteTier = "core" | "modular" | "all";

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
};

const MODULAR_NODES = new Set([
  "LoadMIDI",
  "Prompt",
  "SignalGenerator",
  "ControlCurve",
  "MIDIToFloat",
  "MIDINoteGate",
  "AutomationApply",
  "FloatMath",
  "FloatRoute",
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
  "MIDIInDevice",
  "MIDIOutDevice",
  "OSCInLive",
  "ModuleInlet",
  "ModuleOutlet",
]);

const CORE_IO = new Set(["LoadAudio", "SaveAudio", "Preview", "Mix", "Note"]);

const AUTHENTICITY = new Set(["VerifyProvenance", "AuthenticitySummary", "DeepfakeDetect"]);

/** Create audio from text / MIDI / prompts (sources). */
const AI_GENERATE = new Set(["GenerateAudio", "TTS", "MIDIToAudio", "SingFromMIDI"]);

/** Shape or convert existing audio (processors). */
const AI_TRANSFORM = new Set(["Denoise", "SeparateStems", "VoiceConvert"]);

/** Read audio into text / MIDI (analysis — neither generate nor transform). */
const AI_ANALYZE = new Set(["WhisperSTT", "DiarizeTranscribe", "AudioToMIDI"]);

const TIERS: Array<{ id: PaletteTier; label: string; description: string }> = [
  { id: "core", label: "Core", description: "Essential I/O, processing, and AI exploration." },
  { id: "modular", label: "Modular", description: "Control wires, MIDI, and automation." },
  { id: "all", label: "All", description: "Core and modular nodes (immersive / live I/O / subgraph hidden)." },
];

const GROUP_ORDER: GroupId[] = [
  "core-io",
  "core-dsp",
  "ai-generate",
  "ai-transform",
  "ai-analyze",
  "authenticity",
  "control",
  "subgraph",
];

const GROUP_META: Record<GroupId, { title: string; hint: string; tiers: PaletteTier[] }> = {
  "core-io": {
    title: "I/O",
    hint: "Load, save, mix, preview, notes",
    tiers: ["core", "all"],
  },
  "core-dsp": {
    title: "Processing",
    hint: "Level, trim, resample, oscillators",
    tiers: ["core", "modular", "all"],
  },
  "ai-generate": {
    title: "AI generate",
    hint: "Text-to-audio, TTS, MIDI-conditioned synth",
    tiers: ["core", "all"],
  },
  "ai-transform": {
    title: "AI transform",
    hint: "Denoise, stems, voice convert",
    tiers: ["core", "all"],
  },
  "ai-analyze": {
    title: "AI analyze",
    hint: "Speech-to-text, audio-to-MIDI",
    tiers: ["core", "all"],
  },
  authenticity: {
    title: "Authenticity",
    hint: "Provenance verify, deepfake check",
    tiers: ["core", "all"],
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

function isPaletteVisible(node: NodeTypeInfo): boolean {
  if (HIDDEN_FROM_PALETTE.has(node.type)) return false;
  if (node.category.includes("Immersive") || node.category.includes("Live")) return false;
  return true;
}

function tierForNode(node: NodeTypeInfo): PaletteTier[] {
  const tiers: PaletteTier[] = ["all"];
  // Oscillators are both Core sources and Modular synth building blocks.
  if (node.type === "SignalGenerator") {
    tiers.push("core", "modular");
    return tiers;
  }
  if (node.category.includes("Core") && !MODULAR_NODES.has(node.type)) {
    tiers.push("core");
  }
  if (MODULAR_NODES.has(node.type) || node.type.includes("MIDI") || node.type.includes("Automation")) {
    tiers.push("modular");
  }
  if (node.category.includes("Modular")) {
    tiers.push("modular");
  }
  if (node.category.includes("AI")) {
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
  if (node.category.includes("AI")) return aiPaletteGroup(node.type);
  if (node.type === "ModuleInlet" || node.type === "ModuleOutlet") return "subgraph";
  if (node.type === "SignalGenerator") return "core-dsp";
  if (MODULAR_NODES.has(node.type) || node.type.includes("Float")) return "control";
  if (CORE_IO.has(node.type)) return "core-io";
  return "core-dsp";
}

export default function NodePalette({ onAddNode }: Props) {
  const [nodes, setNodes] = useState<NodeTypeInfo[]>([]);
  const [tier, setTier] = useState<PaletteTier>("core");

  useEffect(() => {
    fetch(`${API}/api/nodes`)
      .then((r) => r.json())
      .then((d) => {
        const list = (d.nodes as Array<{ type: string; category: string }>).map((n) => ({
          type: n.type,
          category: n.category,
        }));
        setNodes(list.filter(isPaletteVisible));
      })
      .catch(() => setNodes([]));
  }, []);

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
