import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Node,
  type NodeTypes,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { executeWorkflow, fetchHealth, fetchTemplate, previewUrl } from "./api";
import GroovyFlowNode from "./components/GroovyFlowNode";
import NodeHelper from "./components/NodeHelper";
import TransportBar from "./components/TransportBar";
import type { JobState, NodeRenderStatus, Workflow } from "./types";
import { downloadWorkflow, resolveTargetNode, syncPositions, workflowToFlow } from "./workflow";

const nodeTypes: NodeTypes = { groovy: GroovyFlowNode };

export default function App() {
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [nodeStatus, setNodeStatus] = useState<Record<string, NodeRenderStatus>>({});
  const [lastJob, setLastJob] = useState<JobState | null>(null);
  const [status, setStatus] = useState("Loading template…");
  const [preview, setPreview] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [health, setHealth] = useState("…");
  const [progress, setProgress] = useState<number | undefined>();
  const [currentNode, setCurrentNode] = useState<string | undefined>();

  const flow = useMemo(
    () => (workflow ? workflowToFlow(workflow, nodeStatus) : { nodes: [], edges: [] }),
    [workflow, nodeStatus],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(flow.nodes);
  const [edges, , onEdgesChange] = useEdgesState(flow.edges);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth("offline"));
    fetchTemplate("hello-groovy")
      .then((data) => {
        setWorkflow(data);
        setStatus("Ready");
        setLoadError(null);
      })
      .catch((err) => {
        setLoadError(String(err));
        setStatus("Template load failed");
      });
  }, []);

  useEffect(() => {
    setNodes(flow.nodes);
  }, [flow.nodes, setNodes]);

  const updateWidget = useCallback((nodeId: string, name: string, value: unknown) => {
    setWorkflow((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        nodes: prev.nodes.map((node) =>
          node.id === nodeId ? { ...node, widgets: { ...node.widgets, [name]: value } } : node,
        ),
      };
    });
    setNodeStatus((prev) => ({ ...prev, [nodeId]: "stale" }));
    setLastJob(null);
    setPreview(null);
  }, []);

  const onNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        return syncPositions(prev, [node]);
      });
    },
    [],
  );

  const runRender = useCallback(
    async (targetNodeId?: string) => {
      if (!workflow) return;
      const target = targetNodeId ?? resolveTargetNode(workflow, selectedNodeId);
      setRunning(true);
      setStatus("Rendering…");
      setProgress(0);
      setCurrentNode(undefined);
      setNodeStatus((prev) => {
        const next = { ...prev };
        for (const node of workflow.nodes) {
          next[node.id] = "stale";
        }
        return next;
      });

      try {
        const job = await executeWorkflow(workflow, [target], (update) => {
          if (update.current_node) {
            setCurrentNode(update.current_node);
            setNodeStatus((prev) => ({
              ...prev,
              [update.current_node!]: "running",
            }));
          }
          if (update.progress != null) {
            setProgress(update.progress);
          }
        });

        setLastJob(job);
        if (job.status === "completed") {
          const outputs = job.outputs ?? {};
          const cached: Record<string, NodeRenderStatus> = {};
          for (const [nodeId, out] of Object.entries(outputs)) {
            if (out?.cache_id) {
              cached[nodeId] = "cached";
            }
          }
          setNodeStatus((prev) => ({ ...prev, ...cached }));
          const cacheId = outputs[target]?.cache_id;
          if (cacheId) {
            setPreview(previewUrl(cacheId));
          }
          setStatus("Complete");
        } else {
          setStatus(`Failed: ${job.error ?? "unknown error"}`);
        }
      } catch (err) {
        setStatus(`Error: ${String(err)}`);
      } finally {
        setRunning(false);
        setCurrentNode(undefined);
        setProgress(undefined);
      }
    },
    [workflow, selectedNodeId],
  );

  const playChain = useCallback(() => {
    if (preview && !running) {
      const audio = document.querySelector<HTMLAudioElement>(".transport__audio");
      void audio?.play();
      return;
    }
    void runRender();
  }, [preview, running, runRender]);

  const selectedNode = workflow?.nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedOutput = selectedNodeId && lastJob?.outputs ? lastJob.outputs[selectedNodeId] : undefined;
  const chainPreview =
    preview ??
    (lastJob?.outputs && workflow
      ? (() => {
          const target = resolveTargetNode(workflow, selectedNodeId);
          const cacheId = lastJob.outputs?.[target]?.cache_id;
          return cacheId ? previewUrl(cacheId) : null;
        })()
      : null);

  if (loadError) {
    return (
      <div className="app app--error">
        <p>Could not load Hello Groovy template: {loadError}</p>
        <p className="status">Is the API running on port 8188?</p>
      </div>
    );
  }

  if (!workflow) {
    return (
      <div className="app app--loading">
        <p>{status}</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="toolbar">
        <h1>GroovyUI Studio</h1>
        <span className="toolbar__template">{workflow.metadata.title}</span>
        <button type="button" onClick={() => downloadWorkflow(workflow)}>
          Save workflow
        </button>
        <span className="status">
          {status} · API {health}
        </span>
      </header>
      <div className="workspace">
        <div className="canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            onNodeDragStop={onNodeDragStop}
            fitView
          >
            <Background gap={16} color="#2a2f3a" />
            <Controls />
          </ReactFlow>
        </div>
        <NodeHelper
          node={selectedNode}
          workflow={workflow}
          output={selectedOutput}
          onWidgetChange={updateWidget}
        />
      </div>
      <TransportBar
        workflow={workflow}
        previewUrl={chainPreview}
        running={running}
        currentNode={currentNode}
        progress={progress}
        onRender={() => void runRender()}
        onPlay={playChain}
      />
    </div>
  );
}
