import { useEffect, useState } from "react";
import { API, fetchNodeSchema } from "../api";

type NodeTypeInfo = { type: string; category: string };

type Props = {
  onAddNode: (nodeType: string) => void;
};

export default function NodePalette({ onAddNode }: Props) {
  const [nodes, setNodes] = useState<NodeTypeInfo[]>([]);

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

  const core = nodes.filter((n) => n.category.includes("Core"));
  const ai = nodes.filter((n) => n.category.includes("AI"));

  return (
    <aside className="node-palette">
      <h2>Nodes</h2>
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
