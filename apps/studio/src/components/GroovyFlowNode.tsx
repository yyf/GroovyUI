import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useAudition } from "../context/AuditionContext";
import { socketTypeColor } from "../socketTypes";
import type { NodeRenderStatus } from "../types";

export type NodeSocketSpec = {
  name: string;
  type: string;
  optional?: boolean;
  /** Workflow link slot index — must match handle id when present. */
  slot?: number;
};

export type GroovyNodeData = {
  label: string;
  status: NodeRenderStatus;
  nodeId: string;
  canAudition?: boolean;
  issue?: string;
  /** Truncated TEXT output shown on-node (Preview / Whisper / Prompt). */
  previewText?: string;
  inputs?: NodeSocketSpec[];
  outputs?: NodeSocketSpec[];
};

function statusLabel(status: NodeRenderStatus): string {
  switch (status) {
    case "running":
      return "●";
    case "cached":
      return "✓";
    case "stale":
      return "…";
    default:
      return "";
  }
}

function handleTop(index: number, total: number): string {
  if (total <= 1) return "50%";
  return `${((index + 1) / (total + 1)) * 100}%`;
}

function handleId(socket: NodeSocketSpec, index: number): string {
  return String(socket.slot ?? index);
}

function GroovyFlowNode({ data, selected }: NodeProps) {
  const nodeData = data as GroovyNodeData;
  const badge = statusLabel(nodeData.status);
  const audition = useAudition();
  const inputs =
    nodeData.inputs !== undefined ? nodeData.inputs : [{ name: "in", type: "AUDIO", slot: 0 }];
  const outputs =
    nodeData.outputs !== undefined ? nodeData.outputs : [{ name: "out", type: "AUDIO", slot: 0 }];
  const minHeight = Math.max(52, Math.max(inputs.length, outputs.length) * 24 + 20);

  return (
    <div
      className={`groovy-node groovy-node--${nodeData.status}${nodeData.issue ? " groovy-node--issue" : ""}${selected ? " groovy-node--selected" : ""}`}
      style={{ minHeight }}
      title={nodeData.issue ?? undefined}
    >
      <span className="groovy-node__ticks" aria-hidden />
      {inputs.map((socket, index) => (
        <Handle
          key={`in-${socket.slot ?? index}-${socket.name}`}
          id={handleId(socket, index)}
          type="target"
          position={Position.Left}
          className="groovy-handle"
          style={{
            top: handleTop(index, inputs.length),
            background: socketTypeColor(socket.type),
          }}
          title={`${socket.name} (${socket.type})`}
        />
      ))}
      <div className="groovy-node__body">
        <div className="groovy-node__title">
          <span>{nodeData.label}</span>
          <span className="groovy-node__actions">
            {nodeData.canAudition ? (
              <button
                type="button"
                className="groovy-node__headphone"
                title="Audition node"
                onClick={(event) => {
                  event.stopPropagation();
                  audition(nodeData.nodeId);
                }}
              >
                🎧
              </button>
            ) : null}
            {badge ? <span className={`groovy-node__badge groovy-node__badge--${nodeData.status}`}>{badge}</span> : null}
          </span>
        </div>
        {inputs.length > 1 ? (
          <ul className="groovy-node__socket-list" aria-hidden>
            {inputs.map((socket) => (
              <li key={socket.name}>
                <span className="groovy-node__socket-dot" style={{ background: socketTypeColor(socket.type) }} />
                {socket.name}
              </li>
            ))}
          </ul>
        ) : null}
        {nodeData.previewText ? (
          <p className="groovy-node__preview-text" title={nodeData.previewText}>
            {nodeData.previewText}
          </p>
        ) : null}
        {nodeData.issue ? <p className="groovy-node__issue">{nodeData.issue}</p> : null}
      </div>
      {outputs.map((socket, index) => (
        <Handle
          key={`out-${socket.slot ?? index}-${socket.name}`}
          id={handleId(socket, index)}
          type="source"
          position={Position.Right}
          className="groovy-handle"
          style={{
            top: handleTop(index, outputs.length),
            background: socketTypeColor(socket.type),
          }}
          title={`${socket.name} (${socket.type})`}
        />
      ))}
    </div>
  );
}

export default memo(GroovyFlowNode);
