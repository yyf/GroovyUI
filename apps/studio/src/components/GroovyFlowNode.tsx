import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useAudition } from "../context/AuditionContext";
import type { CanvasNodeKind } from "../nodeKinds";
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
  /** AI vs DSP/core — drives canvas chrome. */
  kind?: CanvasNodeKind;
  status: NodeRenderStatus;
  nodeId: string;
  canAudition?: boolean;
  issue?: string;
  /** Live render hint (e.g. model download on a slow AI hop). */
  activityLabel?: string;
  /** Truncated TEXT output shown on-node (Preview / Whisper / Prompt). */
  previewText?: string;
  /** Freeform Note comment shown on-node. */
  noteText?: string;
  /** Channel layout / count chip (LoadAudio, Preview, SaveAudio). */
  channelLabel?: string;
  /** Brief ⌘F locate pulse. */
  found?: boolean;
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

function isGenericSocketName(name: string): boolean {
  const normalized = name.trim().toLowerCase();
  return (
    normalized === "" ||
    normalized === "in" ||
    normalized === "out" ||
    normalized === "audio" ||
    normalized === "output_0" ||
    /^in_\d+$/.test(normalized) ||
    /^out_\d+$/.test(normalized)
  );
}

function GroovyFlowNode({ data, selected }: NodeProps) {
  const nodeData = data as GroovyNodeData;
  const badge = statusLabel(nodeData.status);
  const audition = useAudition();
  const inputs =
    nodeData.inputs !== undefined ? nodeData.inputs : [{ name: "in", type: "AUDIO", slot: 0 }];
  const outputs =
    nodeData.outputs !== undefined ? nodeData.outputs : [{ name: "out", type: "AUDIO", slot: 0 }];
  const minHeight = Math.max(
    nodeData.noteText != null ? 72 : 52,
    Math.max(inputs.length, outputs.length) * 24 + 20,
  );
  const isNote = nodeData.label === "Note";
  const kind = nodeData.kind ?? "core";
  const kindClass = isNote ? "" : ` groovy-node--${kind}`;
  const namedInlets = inputs.some((socket) => !isGenericSocketName(socket.name));
  const namedOutlets = outputs.some((socket) => !isGenericSocketName(socket.name));
  const showInputLabels = inputs.length > 1 || namedInlets;
  const showOutputLabels =
    outputs.length > 1 ||
    (nodeData.channelLabel && outputs.length === 1 && nodeData.label === "LoadAudio") ||
    namedOutlets;

  return (
    <div
      className={`groovy-node groovy-node--${nodeData.status}${kindClass}${nodeData.issue ? " groovy-node--issue" : ""}${selected ? " groovy-node--selected" : ""}${nodeData.found ? " groovy-node--found" : ""}${isNote ? " groovy-node--note" : ""}`}
      style={{ minHeight }}
      data-kind={isNote ? "note" : kind}
      aria-busy={nodeData.status === "running"}
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
          <span className="groovy-node__label-row">
            {!isNote && kind === "ai" ? (
              <span className="groovy-node__kind-tag" title="AI inference node">
                AI
              </span>
            ) : null}
            <span>{isNote ? "Note" : nodeData.label}</span>
          </span>
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
        {showInputLabels ? (
          <ul className="groovy-node__socket-list" aria-hidden>
            {inputs.map((socket) => (
              <li key={socket.name}>
                <span className="groovy-node__socket-dot" style={{ background: socketTypeColor(socket.type) }} />
                {socket.name}
              </li>
            ))}
          </ul>
        ) : null}
        {showOutputLabels ? (
          <ul className="groovy-node__socket-list groovy-node__socket-list--outputs" aria-hidden>
            {outputs.map((socket) => (
              <li key={`out-label-${socket.slot ?? socket.name}`}>
                <span className="groovy-node__socket-dot" style={{ background: socketTypeColor(socket.type) }} />
                {socket.name}
              </li>
            ))}
          </ul>
        ) : null}
        {nodeData.channelLabel ? (
          <p className="groovy-node__channel" title={`Channel layout: ${nodeData.channelLabel}`}>
            {nodeData.channelLabel}
          </p>
        ) : null}
        {nodeData.noteText != null ? (
          <p
            className={`groovy-node__note-text${nodeData.noteText.trim() ? "" : " groovy-node__note-text--empty"}`}
            title={nodeData.noteText.trim() ? nodeData.noteText : undefined}
          >
            {nodeData.noteText.trim() ? nodeData.noteText : "Add a comment…"}
          </p>
        ) : null}
        {nodeData.issue ? (
          <p className="groovy-node__issue" title={nodeData.issue}>
            {nodeData.issue}
          </p>
        ) : null}
        {nodeData.activityLabel ? (
          <p className="groovy-node__activity" role="status">
            {nodeData.activityLabel}
          </p>
        ) : null}
        {nodeData.previewText ? (
          <p className="groovy-node__preview-text" title={nodeData.previewText}>
            {nodeData.previewText}
          </p>
        ) : null}
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
