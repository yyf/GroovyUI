import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { NodeRenderStatus } from "../types";

export type GroovyNodeData = {
  label: string;
  status: NodeRenderStatus;
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

  return (
    <div className={`groovy-node groovy-node--${nodeData.status}${selected ? " groovy-node--selected" : ""}`}>
      <Handle type="target" position={Position.Left} className="groovy-handle" />
      <div className="groovy-node__title">
        {nodeData.label}
        {badge ? <span className={`groovy-node__badge groovy-node__badge--${nodeData.status}`}>{badge}</span> : null}
      </div>
      <Handle type="source" position={Position.Right} className="groovy-handle" />
    </div>
  );
}

export default memo(GroovyFlowNode);
