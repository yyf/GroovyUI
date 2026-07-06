import { useEffect, useState } from "react";
import { fetchCacheMeta, fetchNodeSchema } from "../api";
import type { JobOutput, NodeSchema, Workflow, WorkflowNode } from "../types";

type Tab = "config" | "inputs" | "outputs";

type Props = {
  node: WorkflowNode | null;
  workflow: Workflow;
  output?: JobOutput;
  onWidgetChange: (nodeId: string, name: string, value: unknown) => void;
};

export default function NodeHelper({ node, workflow, output, onWidgetChange }: Props) {
  const [tab, setTab] = useState<Tab>("config");
  const [schema, setSchema] = useState<NodeSchema | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    setTab("config");
    if (!node) {
      setSchema(null);
      return;
    }
    fetchNodeSchema(node.type)
      .then(setSchema)
      .catch(() => setSchema(null));
  }, [node]);

  useEffect(() => {
    if (!output?.cache_id) {
      setMeta(null);
      return;
    }
    fetchCacheMeta(output.cache_id)
      .then(setMeta)
      .catch(() => setMeta(null));
  }, [output?.cache_id]);

  if (!node) {
    return (
      <aside className="node-helper node-helper--empty">
        <p>Select a node to edit parameters.</p>
      </aside>
    );
  }

  const upstream = workflow.links
    .filter((link) => link.to[0] === node.id)
    .map((link) => {
      const source = workflow.nodes.find((n) => n.id === link.from[0]);
      return {
        socket: link.to[1],
        type: link.type,
        sourceType: source?.type ?? link.from[0],
      };
    });

  return (
    <aside className="node-helper">
      <header className="node-helper__header">
        <h2>{node.type}</h2>
        <span className="node-helper__id">{node.id}</span>
      </header>
      <nav className="node-helper__tabs">
        <button type="button" className={tab === "config" ? "active" : ""} onClick={() => setTab("config")}>
          Config
        </button>
        <button type="button" className={tab === "inputs" ? "active" : ""} onClick={() => setTab("inputs")}>
          Inputs
        </button>
        <button
          type="button"
          className={tab === "outputs" ? "active" : ""}
          onClick={() => setTab("outputs")}
          disabled={!output}
        >
          Outputs
        </button>
      </nav>
      <div className="node-helper__body">
        {tab === "config" && schema ? (
          <div className="node-helper__widgets">
            {schema.widgets.map((widget) => (
              <label key={widget.name} className="node-helper__field">
                <span>{widget.name}</span>
                <WidgetInput
                  spec={widget}
                  value={node.widgets[widget.name] ?? widget.default ?? ""}
                  onChange={(value) => onWidgetChange(node.id, widget.name, value)}
                />
              </label>
            ))}
            {schema.widgets.length === 0 ? <p className="node-helper__hint">No configurable parameters.</p> : null}
          </div>
        ) : null}
        {tab === "inputs" ? (
          <ul className="node-helper__list">
            {upstream.length === 0 ? (
              <li className="node-helper__hint">No wired inputs.</li>
            ) : (
              upstream.map((item) => (
                <li key={`${item.sourceType}-${item.socket}`}>
                  <strong>{item.type}</strong> ← {item.sourceType}
                </li>
              ))
            )}
          </ul>
        ) : null}
        {tab === "outputs" && output ? (
          <div className="node-helper__outputs">
            <p>
              <strong>{output.type}</strong> cached
            </p>
            {meta ? (
              <>
                <p>
                  {String(meta.frame_count)} frames @ {String(meta.sample_rate)} Hz
                </p>
                <p className="node-helper__mono">{output.cache_id}</p>
              </>
            ) : (
              <p className="node-helper__hint">Render to populate output metadata.</p>
            )}
          </div>
        ) : null}
      </div>
    </aside>
  );
}

type WidgetInputProps = {
  spec: { name: string; type: string; default?: unknown };
  value: unknown;
  onChange: (value: unknown) => void;
};

function WidgetInput({ spec, value, onChange }: WidgetInputProps) {
  if (spec.type === "FLOAT" || spec.type === "INT") {
    return (
      <input
        type="number"
        step={spec.type === "FLOAT" ? "any" : "1"}
        value={typeof value === "number" ? value : Number(value)}
        onChange={(e) => onChange(spec.type === "INT" ? parseInt(e.target.value, 10) : parseFloat(e.target.value))}
      />
    );
  }
  return (
    <input
      type="text"
      value={typeof value === "string" ? value : String(value ?? "")}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
