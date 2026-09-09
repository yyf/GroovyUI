import { useEffect, useMemo } from "react";
import {
  Background,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Workflow } from "../types";
import { layoutWorkflowNodes, workflowToFlowEdges, workflowToFlowNodes } from "../workflow";

type BlueprintData = { label: string; missing?: boolean };
type BlueprintNodeType = Node<BlueprintData, "blueprint">;

function BlueprintNode({ data }: NodeProps<BlueprintNodeType>) {
  return (
    <div className={`blueprint-node${data.missing ? " blueprint-node--missing" : ""}`}>
      <Handle type="target" position={Position.Left} className="blueprint-node__handle" />
      <span className="blueprint-node__label">{data.label}</span>
      {data.missing ? <span className="blueprint-node__missing-tag">not available</span> : null}
      <Handle type="source" position={Position.Right} className="blueprint-node__handle" />
    </div>
  );
}

const nodeTypes = { blueprint: BlueprintNode };

function FitBlueprint({ nodeCount }: { nodeCount: number }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (nodeCount === 0) return;
    const frame = window.requestAnimationFrame(() => {
      void fitView({ padding: 0.2, duration: 0 });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [fitView, nodeCount]);
  return null;
}

type Props = {
  workflow: Workflow;
  title?: string;
  subtitle?: string;
  /** Node type names that are not registered in this studio build. */
  unknownNodeTypes?: string[];
};

function BlueprintCanvas({ workflow, title, subtitle, unknownNodeTypes }: Props) {
  const missingTypes = useMemo(() => new Set(unknownNodeTypes ?? []), [unknownNodeTypes]);
  const prepared = useMemo(() => layoutWorkflowNodes(workflow), [workflow]);
  const { nodes, edges } = useMemo(() => {
    const flowNodes = workflowToFlowNodes(prepared, {});
    const blueprintNodes: BlueprintNodeType[] = flowNodes
      .filter((node) => node.type === "groovy")
      .map((node) => {
        const label = String((node.data as { label?: string })?.label ?? node.id);
        const missing = missingTypes.has(label);
        return {
          id: node.id,
          type: "blueprint" as const,
          position: node.position,
          data: { label, missing },
          className: missing ? "blueprint-node-wrap--missing" : undefined,
          draggable: false,
          selectable: false,
        };
      });
    const blueprintEdges: Edge[] = workflowToFlowEdges(prepared).map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      animated: false,
      selectable: false,
      focusable: false,
      style: {
        stroke: "#5b8def",
        strokeWidth: 1.5,
        strokeDasharray: "4 3",
      },
    }));
    return { nodes: blueprintNodes, edges: blueprintEdges };
  }, [prepared, missingTypes]);

  const missingCount = nodes.filter((node) => node.data.missing).length;

  return (
    <div className="workflow-blueprint">
      <div className="workflow-blueprint__chrome">
        <span className="workflow-blueprint__badge">Blueprint</span>
        {title ? <strong className="workflow-blueprint__title">{title}</strong> : null}
        {subtitle ? <span className="workflow-blueprint__subtitle">{subtitle}</span> : null}
        {missingCount > 0 ? (
          <span className="workflow-blueprint__missing-legend">
            {missingCount} node{missingCount === 1 ? "" : "s"} not available yet
          </span>
        ) : null}
      </div>
      <div className="workflow-blueprint__canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          edgesFocusable={false}
          panOnDrag
          zoomOnScroll
          preventScrolling
          fitView
          minZoom={0.25}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={22} color="#1c3a66" size={1} />
          <FitBlueprint nodeCount={nodes.length} />
        </ReactFlow>
      </div>
    </div>
  );
}

/** Read-only blueprint graph of building blocks (no render / audition). */
export default function WorkflowBlueprintPreview(props: Props) {
  return (
    <ReactFlowProvider>
      <BlueprintCanvas {...props} />
    </ReactFlowProvider>
  );
}
