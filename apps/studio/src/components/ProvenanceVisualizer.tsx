import { useMemo, useState } from "react";
import { layoutProvenanceGraph, lineageFromEntry } from "../provenanceLayout";
import type { ProvenanceEntry } from "../types";

type Props = {
  entry: ProvenanceEntry;
};

function modelLabel(model: {
  registry_id?: string;
  role?: string;
  lora_scale?: number;
}): string {
  const id = model.registry_id ?? "unknown";
  if (model.role === "adapter") {
    const scale = typeof model.lora_scale === "number" ? ` ×${model.lora_scale}` : "";
    return `LoRA: ${id}${scale}`;
  }
  return `Model: ${id}`;
}

export default function ProvenanceVisualizer({ entry }: Props) {
  const lineage = useMemo(() => lineageFromEntry(entry), [entry]);
  const layout = useMemo(
    () => (lineage ? layoutProvenanceGraph(lineage) : null),
    [lineage],
  );
  const [selectedCacheId, setSelectedCacheId] = useState<string | null>(null);

  const selected = useMemo(() => {
    if (!layout) return null;
    const id = selectedCacheId ?? lineage?.root_cache_id;
    return layout.nodes.find((n) => n.cacheId === id) ?? layout.nodes.find((n) => n.isRoot) ?? null;
  }, [layout, lineage?.root_cache_id, selectedCacheId]);

  if (!layout || layout.nodes.length === 0) {
    return (
      <p className="compliance-hint">
        No provenance.json lineage for this output yet. Render the workflow to populate the graph.
      </p>
    );
  }

  const { glance } = layout;
  const story =
    glance.hopCount === 1
      ? "Single hop"
      : glance.hasBranching
        ? "Sources merge into this output"
        : "Source → transforms → output";

  return (
    <div className="provenance-viz">
      <div className="provenance-viz__summary" aria-label="Provenance at a glance">
        <div className="provenance-viz__summary-top">
          <div>
            <span className="provenance-viz__eyebrow">How this output was made</span>
            <p className="provenance-viz__story">{story}</p>
          </div>
          <strong className="provenance-viz__hops">
            {glance.hopCount} hop{glance.hopCount === 1 ? "" : "s"}
          </strong>
        </div>
        {(glance.human > 0 || glance.ai > 0 || glance.mixed > 0) && (
          <div className="provenance-viz__mix">
            <div
              className="provenance-viz__mix-bar"
              role="img"
              aria-label={`Human ${glance.humanPercent}%, AI ${glance.aiPercent}%`}
            >
              <span
                className="provenance-viz__mix-seg provenance-viz__mix-seg--human"
                style={{ width: `${glance.humanPercent}%` }}
              />
              <span
                className="provenance-viz__mix-seg provenance-viz__mix-seg--ai"
                style={{ width: `${glance.aiPercent}%` }}
              />
            </div>
            <span className="provenance-viz__mix-label">
              Human {glance.humanPercent}% · AI {glance.aiPercent}%
              <span className="provenance-viz__mix-counts"> · {glance.label}</span>
            </span>
          </div>
        )}
        <div className="provenance-viz__legend" aria-hidden>
          <span className="provenance-viz__legend-item provenance-viz__legend-item--human">
            Human
          </span>
          <span className="provenance-viz__legend-item provenance-viz__legend-item--ai">AI</span>
          <span className="provenance-viz__legend-item provenance-viz__legend-item--mixed">
            Mixed
          </span>
        </div>
      </div>

      <div className="provenance-viz__flow-label">
        <span>Source</span>
        <span className="provenance-viz__flow-arrow" aria-hidden>
          {layout.orientation === "vertical" ? "↓" : "→"}
        </span>
        <span>Output</span>
      </div>

      <div className="provenance-viz__scroll">
        <div
          className={`provenance-viz__canvas provenance-viz__canvas--${layout.orientation}`}
          style={{ width: layout.width, height: layout.height }}
          role="list"
          aria-label="Provenance hops from source to output"
        >
          <svg
            className="provenance-viz__svg"
            width={layout.width}
            height={layout.height}
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            aria-hidden
          >
            <defs>
              <marker
                id={`provenance-arrow-${entry.node_id}`}
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" className="provenance-viz__arrow" />
              </marker>
            </defs>
            {layout.edges.map((edge) => (
              <path
                key={edge.id}
                d={edge.path}
                className="provenance-viz__edge"
                markerEnd={`url(#provenance-arrow-${entry.node_id})`}
                fill="none"
              />
            ))}
          </svg>
          {layout.nodes.map((node) => {
            const active = selected?.cacheId === node.cacheId;
            return (
              <button
                key={node.cacheId}
                type="button"
                role="listitem"
                className={[
                  "provenance-viz__card",
                  `provenance-viz__card--${node.kind}`,
                  node.isRoot ? "provenance-viz__card--root" : "",
                  node.isSource ? "provenance-viz__card--source" : "",
                  active ? "provenance-viz__card--active" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                style={{
                  left: node.x,
                  top: node.y,
                  width: node.width,
                  height: node.height,
                }}
                onClick={() => setSelectedCacheId(node.cacheId)}
                aria-pressed={active}
                title={`${node.nodeType} — ${node.kindLabel}`}
              >
                <span className="provenance-viz__role">
                  {node.isRoot ? "Output" : node.isSource ? "Source" : "Hop"}
                </span>
                <span className="provenance-viz__type">{node.nodeType}</span>
                <span className="provenance-viz__kind">{node.kindLabel}</span>
                {node.modelSummary ? (
                  <span className="provenance-viz__model">{node.modelSummary}</span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      {selected ? (
        <div className="provenance-viz__detail">
          <div className="provenance-viz__detail-heading">
            <strong>{selected.nodeType}</strong>
            <span className={`pill pill--${selected.contributionClass}`}>{selected.kindLabel}</span>
            {selected.isRoot ? <span className="pill">output</span> : null}
            {selected.isSource && !selected.isRoot ? <span className="pill">source</span> : null}
          </div>
          <p className="node-helper__mono provenance-viz__detail-ids">
            {selected.nodeId} · {selected.cacheId.slice(0, 12)}…
          </p>
          {selected.models.length > 0 ? (
            <ul className="node-helper__list provenance-models">
              {selected.models.map((model, idx) => (
                <li key={`${model.registry_id ?? "m"}-${idx}`}>{modelLabel(model)}</li>
              ))}
            </ul>
          ) : (
            <p className="compliance-hint">No model on this hop — DSP / passthrough / load.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
