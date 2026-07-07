import { useEffect, useMemo, useState } from "react";
import { API, fetchNodeSchema } from "../api";

type NodeTypeInfo = { type: string; category: string };

type PaletteTier = "core" | "modular" | "immersive" | "live" | "all";

type Props = {
  onAddNode: (nodeType: string) => void;
};

const MODULAR_NODES = new Set([
  "LoadMIDI",
  "Prompt",
  "ControlCurve",
  "MIDIToFloat",
  "MIDINoteGate",
  "AutomationApply",
  "FloatMath",
  "FloatRoute",
  "ModuleInlet",
  "ModuleOutlet",
]);

const IMMERSIVE_NODES = new Set([
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
]);

const LIVE_NODES = new Set(["MIDIInDevice", "MIDIOutDevice", "OSCInLive"]);

function tierForNode(node: NodeTypeInfo): PaletteTier[] {
  const tiers: PaletteTier[] = ["all"];
  if (node.category.includes("Core") && !MODULAR_NODES.has(node.type) && !IMMERSIVE_NODES.has(node.type)) {
    tiers.push("core");
  }
  if (MODULAR_NODES.has(node.type) || node.type.includes("MIDI") || node.type.includes("Automation")) {
    tiers.push("modular");
  }
  if (node.category.includes("Modular")) {
    tiers.push("modular");
  }
  if (IMMERSIVE_NODES.has(node.type) || node.category.includes("Immersive")) {
    tiers.push("immersive");
  }
  if (LIVE_NODES.has(node.type) || node.category.includes("Live")) {
    tiers.push("live");
  }
  if (node.category.includes("AI")) {
    tiers.push("core");
  }
  return tiers;
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
        setNodes(list);
      })
      .catch(() => setNodes([]));
  }, []);

  const filtered = useMemo(() => {
    if (tier === "all") return nodes;
    return nodes.filter((node) => tierForNode(node).includes(tier));
  }, [nodes, tier]);

  const core = filtered.filter((n) => n.category.includes("Core"));
  const ai = filtered.filter((n) => n.category.includes("AI"));
  const live = filtered.filter((n) => n.category.includes("Live"));

  return (
    <aside className="node-palette">
      <h2>Nodes</h2>
      <div className="node-palette__tiers">
        {(
          [
            ["core", "Core"],
            ["modular", "Modular"],
            ["immersive", "Immersive"],
            ["live", "Live I/O"],
            ["all", "All"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={tier === value ? "active" : ""}
            onClick={() => setTier(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <section>
        <h3>Core</h3>
        {core.map((n) => (
          <button key={n.type} type="button" onClick={() => onAddNode(n.type)}>
            {n.type}
          </button>
        ))}
      </section>
      <section>
        <h3>AI</h3>
        {ai.map((n) => (
          <button key={n.type} type="button" onClick={() => onAddNode(n.type)}>
            {n.type}
          </button>
        ))}
      </section>
      {live.length > 0 ? (
        <section>
          <h3>Live I/O</h3>
          {live.map((n) => (
            <button key={n.type} type="button" onClick={() => onAddNode(n.type)}>
              {n.type}
            </button>
          ))}
        </section>
      ) : null}
    </aside>
  );
}

export async function defaultWidgetsForNode(nodeType: string): Promise<Record<string, unknown>> {
  const schema = await fetchNodeSchema(nodeType);
  const widgets: Record<string, unknown> = {};
  for (const w of schema.widgets ?? []) {
    if (w.default !== undefined) widgets[w.name] = w.default;
  }
  return widgets;
}
