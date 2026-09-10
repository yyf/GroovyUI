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

function slugifyFilename(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return slug || "blueprint";
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function downloadBlueprintJson(workflow: Workflow, basename: string) {
  const meta = workflow.metadata as { title: string; description?: string; tags?: string[] };
  const tags = Array.from(new Set([...(meta.tags ?? []), "blueprint", "snapshot"]));
  const payload = {
    ...workflow,
    metadata: {
      ...workflow.metadata,
      tags,
    },
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  triggerDownload(blob, `${basename}.groovy.json`);
}

const NODE_W = 128;
const NODE_H = 44;

/** Draw blueprint nodes/edges to a PNG (no DOM snapshot deps). */
function downloadBlueprintPng(
  nodes: BlueprintNodeType[],
  edges: Edge[],
  basename: string,
  title?: string,
) {
  if (!nodes.length) return;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const node of nodes) {
    minX = Math.min(minX, node.position.x);
    minY = Math.min(minY, node.position.y);
    maxX = Math.max(maxX, node.position.x + NODE_W);
    maxY = Math.max(maxY, node.position.y + NODE_H);
  }
  const pad = 48;
  const header = 56;
  const width = Math.ceil(maxX - minX + pad * 2);
  const height = Math.ceil(maxY - minY + pad * 2 + header);
  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = width * scale;
  canvas.height = height * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.scale(scale, scale);
  ctx.fillStyle = "#081224";
  ctx.fillRect(0, 0, width, height);

  // Grid
  ctx.strokeStyle = "#1c3a66";
  ctx.lineWidth = 1;
  for (let x = 0; x < width; x += 22) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  for (let y = 0; y < height; y += 22) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  ctx.fillStyle = "#5b8def";
  ctx.font = "600 11px ui-sans-serif, system-ui, sans-serif";
  ctx.fillText("BLUEPRINT", pad, 28);
  if (title) {
    ctx.fillStyle = "#d7e6ff";
    ctx.font = "600 14px ui-sans-serif, system-ui, sans-serif";
    ctx.fillText(title.slice(0, 64), pad + 88, 28);
  }

  const ox = pad - minX;
  const oy = pad + header - minY;
  const center = (node: BlueprintNodeType, side: "left" | "right") => ({
    x: node.position.x + ox + (side === "left" ? 0 : NODE_W),
    y: node.position.y + oy + NODE_H / 2,
  });

  const byId = new Map(nodes.map((node) => [node.id, node]));
  ctx.setLineDash([4, 3]);
  ctx.strokeStyle = "#5b8def";
  ctx.lineWidth = 1.5;
  for (const edge of edges) {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) continue;
    const a = center(source, "right");
    const b = center(target, "left");
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.bezierCurveTo((a.x + b.x) / 2, a.y, (a.x + b.x) / 2, b.y, b.x, b.y);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  for (const node of nodes) {
    const x = node.position.x + ox;
    const y = node.position.y + oy;
    const missing = Boolean(node.data.missing);
    ctx.fillStyle = missing ? "rgba(64, 36, 8, 0.95)" : "rgba(16, 40, 72, 0.95)";
    ctx.strokeStyle = missing ? "#e0a04a" : "#5b8def";
    ctx.lineWidth = 1.5;
    if (missing) ctx.setLineDash([5, 3]);
    ctx.fillRect(x, y, NODE_W, NODE_H);
    ctx.strokeRect(x, y, NODE_W, NODE_H);
    ctx.setLineDash([]);
    ctx.fillStyle = missing ? "#ffd9a8" : "#cfe0ff";
    ctx.font = "600 11px ui-sans-serif, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(node.data.label.slice(0, 18), x + NODE_W / 2, y + (missing ? 18 : 26));
    if (missing) {
      ctx.fillStyle = "#e0a04a";
      ctx.font = "500 9px ui-sans-serif, system-ui, sans-serif";
      ctx.fillText("NOT AVAILABLE", x + NODE_W / 2, y + 34);
    }
    ctx.textAlign = "left";
  }

  canvas.toBlob((blob) => {
    if (!blob) return;
    triggerDownload(blob, `${basename}.png`);
  }, "image/png");
}

type Props = {
  workflow: Workflow;
  title?: string;
  subtitle?: string;
  /** Node type names that are not registered in this studio build. */
  unknownNodeTypes?: string[];
  /** When true, offer Save JSON / Save image for brainstorming snapshots. */
  showSnapshotExport?: boolean;
};

function BlueprintCanvas({
  workflow,
  title,
  subtitle,
  unknownNodeTypes,
  showSnapshotExport,
}: Props) {
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
  const basename = slugifyFilename(title || workflow.metadata?.title || "blueprint");

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
        {showSnapshotExport ? (
          <div className="workflow-blueprint__exports">
            <button
              type="button"
              className="workflow-blueprint__export-btn"
              onClick={() => downloadBlueprintJson(workflow, basename)}
            >
              Save JSON
            </button>
            <button
              type="button"
              className="workflow-blueprint__export-btn"
              onClick={() => downloadBlueprintPng(nodes, edges, basename, title)}
            >
              Save image
            </button>
          </div>
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
