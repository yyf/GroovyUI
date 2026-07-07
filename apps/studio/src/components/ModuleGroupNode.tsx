import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

export type GroovyGroupNodeData = {
  label: string;
  groupId: string;
  nodeCount: number;
};

function ModuleGroupNode({ data, selected }: NodeProps) {
  const nodeData = data as GroovyGroupNodeData;
  return (
    <div className={`groovy-group-node${selected ? " groovy-group-node--selected" : ""}`}>
      <Handle type="target" position={Position.Left} className="groovy-handle" />
      <div className="groovy-group-node__title">{nodeData.label}</div>
      <div className="groovy-group-node__meta">{nodeData.nodeCount} nodes (collapsed)</div>
      <Handle type="source" position={Position.Right} className="groovy-handle" />
    </div>
  );
}

export default memo(ModuleGroupNode);
