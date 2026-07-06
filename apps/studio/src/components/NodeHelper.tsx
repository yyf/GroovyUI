import { useEffect, useState } from "react";
import { fetchCacheMeta, fetchNodeSchema } from "../api";
import type { JobOutput, NodeSchema, Workflow, WorkflowNode } from "../types";

type Tab = "config" | "inputs" | "outputs" | "provenance";

type Props = {
  node: WorkflowNode | null;
  workflow: Workflow;
  output?: JobOutput;
  previewUrl?: string | null;
  onWidgetChange: (nodeId: string, name: string, value: unknown) => void;
  onBrowseModel?: (nodeId: string, widgetName: string) => void;
  onAudition?: () => void;
};

export default function NodeHelper({
  node,
  workflow,
  output,
  previewUrl,
  onWidgetChange,
  onBrowseModel,
  onAudition,
}: Props) {
  const [tab, setTab] = useState<Tab>("config");
  const [schema, setSchema] = useState<NodeSchema | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [provenance, setProvenance] = useState<Record<string, unknown> | null>(null);

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
      setProvenance(null);
      return;
    }
    fetchCacheMeta(output.cache_id)
      .then(setMeta)
      .catch(() => setMeta(null));
    fetch(`${import.meta.env.VITE_GROOVY_API ?? "http://127.0.0.1:8188"}/api/cache/${output.cache_id}/provenance`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setProvenance)
      .catch(() => setProvenance(null));
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
        <button
          type="button"
          className={tab === "provenance" ? "active" : ""}
          onClick={() => setTab("provenance")}
          disabled={!output?.cache_id}
        >
          Provenance
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
                  onBrowse={
                    widget.type === "MODEL_REF"
                      ? () => onBrowseModel?.(node.id, widget.name)
                      : undefined
                  }
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
            {output.type === "TEXT" && output.text ? (
              <p className="node-helper__text">{output.text}</p>
            ) : null}
            {output.type === "STEMS" && output.stems ? (
              <ul className="node-helper__list">
                {Object.keys(output.stems).map((stem) => (
                  <li key={stem}>{stem}</li>
                ))}
              </ul>
            ) : null}
            {meta ? (
              <>
                <p>
                  {String(meta.frame_count)} frames @ {String(meta.sample_rate)} Hz
                </p>
                <p className="node-helper__mono">{output.cache_id}</p>
              </>
            ) : null}
            {previewUrl ? (
              <button type="button" className="node-helper__audition" onClick={onAudition}>
                ▶ Audition node
              </button>
            ) : null}
            {!meta && output.type === "AUDIO" ? (
              <p className="node-helper__hint">Render to populate output metadata.</p>
            ) : null}
          </div>
        ) : null}
        {tab === "provenance" && provenance ? (
          <div className="node-helper__provenance">
            <p>
              <span className={`pill pill--${String((provenance.contribution as { class?: string })?.class ?? "unknown")}`}>
                {String((provenance.contribution as { class?: string })?.class ?? "unknown")}
              </span>
            </p>
            <p>{String((provenance.contribution as { disclosure_label?: string })?.disclosure_label ?? "")}</p>
            <ul className="node-helper__list">
              {((provenance.parents as Array<{ node_type?: string; cache_id?: string }>) ?? []).map((parent) => (
                <li key={parent.cache_id}>
                  ↑ {parent.node_type ?? "parent"} ({parent.cache_id?.slice(0, 8)}…)
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {tab === "provenance" && !provenance ? (
          <p className="node-helper__hint">Render to populate provenance.</p>
        ) : null}
      </div>
    </aside>
  );
}

type WidgetInputProps = {
  spec: { name: string; type: string; default?: unknown };
  value: unknown;
  onChange: (value: unknown) => void;
  onBrowse?: () => void;
};

function WidgetInput({ spec, value, onChange, onBrowse }: WidgetInputProps) {
  if (spec.type === "MODEL_REF") {
    return (
      <div className="node-helper__model-ref">
        <input type="text" readOnly value={typeof value === "string" ? value : String(value ?? "")} />
        <button type="button" onClick={onBrowse}>
          Browse…
        </button>
      </div>
    );
  }
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
