import type { ReactNode } from "react";
import type { ModelInternalConnection } from "../types";
import { socketTypeColor } from "../socketTypes";
import SocketTypeBadge from "./SocketTypeBadge";

export type SubgraphPort = {
  index: number;
  name: string;
  type: string;
  optional?: boolean;
  connected: boolean;
  detail?: string;
};

type Props = {
  nodeType: string;
  modelLabel: string | null;
  inputs: SubgraphPort[];
  outputs: SubgraphPort[];
  config: ReactNode;
  architectureNotes?: string | null;
  internalConnections?: ModelInternalConnection[] | null;
  onDisconnectInput: (slot: number) => void;
  onDisconnectOutput: (slot: number) => void;
};

function PortColumn({
  title,
  ports,
  side,
  onDisconnect,
}: {
  title: string;
  ports: SubgraphPort[];
  side: "in" | "out";
  onDisconnect: (slot: number) => void;
}) {
  if (ports.length === 0) {
    return (
      <div className={`model-subgraph__ports model-subgraph__ports--${side}`}>
        <h4 className="node-helper__compare-subtitle">{title}</h4>
        <p className="node-helper__hint">None</p>
      </div>
    );
  }
  return (
    <div className={`model-subgraph__ports model-subgraph__ports--${side}`}>
      <h4 className="node-helper__compare-subtitle">{title}</h4>
      <ul className="model-subgraph__port-list">
        {ports.map((port) => (
          <li
            key={`${side}-${port.index}-${port.name}`}
            className={[
              "model-subgraph__port",
              port.connected ? "model-subgraph__port--live" : "model-subgraph__port--idle",
            ].join(" ")}
            style={{ borderColor: socketTypeColor(port.type) }}
          >
            <label className="model-subgraph__port-toggle" title={port.connected ? "Uncheck to disconnect canvas wires" : "Wire this port on the main canvas"}>
              <input
                type="checkbox"
                checked={port.connected}
                disabled={!port.connected}
                onChange={(e) => {
                  if (!e.target.checked && port.connected) onDisconnect(port.index);
                }}
              />
              <span className="model-subgraph__port-name">{port.name}</span>
            </label>
            <div className="model-subgraph__port-meta">
              <SocketTypeBadge type={port.type} />
              {port.optional ? <span className="node-helper__socket-opt">optional</span> : null}
            </div>
            {port.detail ? <small className="node-helper__hint">{port.detail}</small> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function InternalConnectionsBlock({
  notes,
  connections,
}: {
  notes?: string | null;
  connections?: ModelInternalConnection[] | null;
}) {
  const rows = (connections ?? []).filter((row) => row.from || row.to);
  if (!notes && rows.length === 0) {
    return (
      <section className="model-subgraph__internals">
        <h4 className="node-helper__compare-subtitle">Model internals</h4>
        <p className="node-helper__hint">
          No architecture / internal connection graph is published for this model in the registry. When HF card
          notes are curated into the catalog, they appear here as-is.
        </p>
      </section>
    );
  }
  return (
    <section className="model-subgraph__internals">
      <h4 className="node-helper__compare-subtitle">Model internals</h4>
      {notes ? <pre className="model-subgraph__notes">{notes}</pre> : null}
      {rows.length > 0 ? (
        <ul className="model-subgraph__edge-list">
          {rows.map((row, i) => (
            <li key={`${row.from}-${row.to}-${i}`}>
              <code>{row.from || "?"}</code>
              <span aria-hidden="true"> → </span>
              <code>{row.to || "?"}</code>
              {row.label ? <span className="node-helper__hint"> · {row.label}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** Compact I/O + config canvas for the Inspector Subgraph tab. */
export default function ModelSubgraphPanel({
  nodeType,
  modelLabel,
  inputs,
  outputs,
  config,
  architectureNotes,
  internalConnections,
  onDisconnectInput,
  onDisconnectOutput,
}: Props) {
  return (
    <div className="model-subgraph">
      <p className="node-helper__hint">
        Node interface map — uncheck a live port to disconnect its canvas wires. Rewire on the main graph;
        edit parameters in the center box.
      </p>
      <div className="model-subgraph__canvas" role="group" aria-label="Node subgraph">
        <PortColumn title="Inputs" ports={inputs} side="in" onDisconnect={onDisconnectInput} />
        <div className="model-subgraph__center">
          <div className="model-subgraph__wires" aria-hidden="true">
            <span className="model-subgraph__rail model-subgraph__rail--in" />
            <span className="model-subgraph__rail model-subgraph__rail--out" />
          </div>
          <div className="model-subgraph__node">
            <header className="model-subgraph__node-head">
              <strong>{nodeType}</strong>
              {modelLabel ? <span className="model-subgraph__model-id">{modelLabel}</span> : null}
            </header>
            <div className="model-subgraph__config">{config}</div>
          </div>
        </div>
        <PortColumn title="Outputs" ports={outputs} side="out" onDisconnect={onDisconnectOutput} />
      </div>
      <InternalConnectionsBlock notes={architectureNotes} connections={internalConnections} />
    </div>
  );
}
