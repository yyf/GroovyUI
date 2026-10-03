import { memo, useCallback, useRef, type PointerEvent as ReactPointerEvent } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { projectMediaUrl } from "../api";
import { useAudition } from "../context/AuditionContext";
import { usePreviewVideoSize } from "../context/PreviewVideoSizeContext";
import { useTrajectoryEdit } from "../context/TrajectoryEditContext";
import type { CanvasNodeKind } from "../nodeKinds";
import { shortCanvasIssueLabel } from "../planModelSanitize";
import { socketTypeColor } from "../socketTypes";
import type { NodeRenderStatus } from "../types";
import { lockPreviewVideoSize } from "../workflow";
import { TrajectoryAuthorPad } from "./TrajectoryPanel";

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
  /** Project-relative muxed VIDEO path for on-node player (PreviewVideo only). */
  previewVideoPath?: string;
  /** Aspect-locked on-canvas video panel size (PreviewVideo). */
  previewVideoWidth?: number;
  previewVideoHeight?: number;
  previewVideoAspect?: number;
  /** Freeform Note comment shown on-node. */
  noteText?: string;
  /** Channel layout / count chip (LoadAudio, Preview, SaveAudio). */
  channelLabel?: string;
  /** TRAJECTORY cache id for on-node XYZ mini plot. */
  trajectoryId?: string;
  /** Monitor role when this is a TrajectoryMonitor (input | output). */
  trajectoryRole?: "input" | "output";
  /** Upstream / self TrajectoryAuthor id for canvas XYZ drag edits. */
  trajectoryAuthorId?: string;
  /** Live author widgets mirrored onto canvas pads (includes optional drawn `points` JSON). */
  trajectoryWidgets?: Record<string, number | string>;
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
  const { patchAuthor } = useTrajectoryEdit();
  const { patchSize } = usePreviewVideoSize();
  const resizeDrag = useRef<{
    startX: number;
    startW: number;
    aspect: number;
  } | null>(null);
  const inputs =
    nodeData.inputs !== undefined ? nodeData.inputs : [{ name: "in", type: "AUDIO", slot: 0 }];
  const outputs =
    nodeData.outputs !== undefined ? nodeData.outputs : [{ name: "out", type: "AUDIO", slot: 0 }];
  const showAuthorPad = Boolean(nodeData.trajectoryAuthorId && nodeData.trajectoryWidgets);
  const videoW = nodeData.previewVideoWidth ?? 240;
  const videoH = nodeData.previewVideoHeight ?? 135;
  const videoAspect = nodeData.previewVideoAspect ?? 16 / 9;
  const minHeight = Math.max(
    nodeData.noteText != null ? 72 : 52,
    showAuthorPad ? 200 : nodeData.trajectoryId ? 160 : 0,
    nodeData.previewVideoPath || nodeData.label === "PreviewVideo" ? videoH + 36 : 0,
    Math.max(inputs.length, outputs.length) * 24 + 20,
  );

  const onVideoResizePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLSpanElement>) => {
      event.preventDefault();
      event.stopPropagation();
      const target = event.currentTarget;
      target.setPointerCapture(event.pointerId);
      resizeDrag.current = {
        startX: event.clientX,
        startW: videoW,
        aspect: videoAspect,
      };
      const onMove = (ev: PointerEvent) => {
        const drag = resizeDrag.current;
        if (!drag) return;
        const nextW = drag.startW + (ev.clientX - drag.startX);
        const locked = lockPreviewVideoSize("preview_width", nextW, drag.aspect);
        patchSize(nodeData.nodeId, locked.preview_width, locked.preview_height);
      };
      const onUp = (ev: PointerEvent) => {
        resizeDrag.current = null;
        try {
          target.releasePointerCapture(ev.pointerId);
        } catch {
          /* already released */
        }
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [nodeData.nodeId, patchSize, videoAspect, videoW],
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
            {shortCanvasIssueLabel(nodeData.issue)}
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
        {nodeData.label === "PreviewVideo" ? (
          <div
            className={`groovy-node__video nodrag nopan${selected ? " groovy-node__video--selected" : ""}`}
            style={{ width: videoW, height: videoH }}
            onPointerDown={(event) => event.stopPropagation()}
          >
            {nodeData.previewVideoPath ? (
              // Transport / Space is master clock — no local controls; video stays muted.
              <video
                key={nodeData.previewVideoPath}
                playsInline
                muted
                preload="auto"
                src={projectMediaUrl(nodeData.previewVideoPath)}
                className="groovy-node__video-player"
                title="Synced to transport (Space / Play)"
              />
            ) : (
              <div className="groovy-node__video-placeholder">Render to preview</div>
            )}
            <span
              className="groovy-node__video-resize"
              title="Drag to scale (aspect locked)"
              onPointerDown={onVideoResizePointerDown}
            />
          </div>
        ) : null}
        {showAuthorPad && nodeData.trajectoryAuthorId && nodeData.trajectoryWidgets ? (
          <div
            className="groovy-node__trajectory groovy-node__trajectory--editable nodrag nopan"
            onPointerDown={(event) => event.stopPropagation()}
          >
            <TrajectoryAuthorPad
              widgets={nodeData.trajectoryWidgets}
              size={128}
              compact
              role={nodeData.trajectoryRole ?? "input"}
              trajectoryId={nodeData.trajectoryId}
              onChange={(patch) => patchAuthor(nodeData.trajectoryAuthorId!, patch)}
            />
          </div>
        ) : nodeData.trajectoryId ? (
          <div className="groovy-node__trajectory" onPointerDown={(event) => event.stopPropagation()}>
            <TrajectoryAuthorPad
              widgets={{}}
              size={128}
              compact
              role={nodeData.trajectoryRole ?? "output"}
              trajectoryId={nodeData.trajectoryId}
            />
          </div>
        ) : nodeData.label === "TrajectoryMonitor" || nodeData.label === "TrajectoryAuthor" ? (
          <p className="groovy-node__trajectory-hint">Wire TRAJECTORY · Render · Play</p>
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
