import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useAudition } from "../context/AuditionContext";
import type { NodeRenderStatus } from "../types";

export type GroovyNodeData = {
  label: string;
  status: NodeRenderStatus;
  nodeId: string;
  canAudition?: boolean;
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

function GroovyFlowNode({ data, selected }: NodeProps) {
  const nodeData = data as GroovyNodeData;
  const badge = statusLabel(nodeData.status);
  const audition = useAudition();

  return (
    <div className={`groovy-node groovy-node--${nodeData.status}${selected ? " groovy-node--selected" : ""}`}>
      <Handle type="target" position={Position.Left} className="groovy-handle" />
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
      <Handle type="source" position={Position.Right} className="groovy-handle" />
    </div>
  );
}

export default memo(GroovyFlowNode);
