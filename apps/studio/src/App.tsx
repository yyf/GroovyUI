import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ensureWorkflowModels, executeWorkflow, fetchCompliance, fetchHealth, fetchTemplate, listTemplates, previewUrl } from "./api";
import ComplianceDrawer from "./components/ComplianceDrawer";
import GroovyFlowNode from "./components/GroovyFlowNode";
import ModelBrowser from "./components/ModelBrowser";
import NodeHelper from "./components/NodeHelper";
import NodePalette, { defaultWidgetsForNode } from "./components/NodePalette";
import TransportBar from "./components/TransportBar";
import type { JobState, NodeRenderStatus, Workflow } from "./types";
import {
  addLink,
  addNodeToWorkflow,
  downloadWorkflow,
  formatJobError,
  previewCacheId,
  removeLinks,
  resolveTargetNode,
  syncPositions,
  workflowToFlow,
} from "./workflow";

const nodeTypes: NodeTypes = { groovy: GroovyFlowNode };
const DEFAULT_TEMPLATE = "podcast-denoise";

export default function App() {
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [templates, setTemplates] = useState<Array<{ id: string; title: string }>>([]);
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
  const [modelBrowserOpen, setModelBrowserOpen] = useState(false);
  const [modelPickTarget, setModelPickTarget] = useState<{ nodeId: string; widget: string } | null>(null);
  const [complianceOpen, setComplianceOpen] = useState(false);
  const [complianceWarnings, setComplianceWarnings] = useState(0);
  const [focusMode, setFocusMode] = useState(false);
  const [nodePreviewUrl, setNodePreviewUrl] = useState<string | null>(null);

  const flow = useMemo(
    () => (workflow ? workflowToFlow(workflow, nodeStatus) : { nodes: [], edges: [] }),
    [workflow, nodeStatus],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(flow.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flow.edges);

  const loadTemplate = useCallback(async (templateId: string) => {
    setStatus("Loading template…");
    setPreview(null);
    setLastJob(null);
    setNodeStatus({});
    const data = await fetchTemplate(templateId);
    setWorkflow(data);
    setStatus("Ready");
    setLoadError(null);
  }, []);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth("offline"));
    listTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]));
    loadTemplate(DEFAULT_TEMPLATE).catch((err) => {
      setLoadError(String(err));
      setStatus("Template load failed");
    });
  }, [loadTemplate]);

  useEffect(() => {
    setNodes(flow.nodes);
  }, [flow.nodes, setNodes]);

  useEffect(() => {
    setEdges(flow.edges);
  }, [flow.edges, setEdges]);

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

  const onNodeDragStop = useCallback((_: unknown, node: Node) => {
    setWorkflow((prev) => {
      if (!prev) return prev;
      return syncPositions(prev, [node]);
    });
  }, []);

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target) return;
    setWorkflow((prev) => {
      if (!prev) return prev;
      return addLink(prev, connection.source, connection.target);
    });
    setLastJob(null);
    setPreview(null);
  }, []);

  const onEdgesDelete = useCallback((deleted: Edge[]) => {
    const ids = new Set(deleted.map((edge) => edge.id));
    setWorkflow((prev) => {
      if (!prev) return prev;
      return removeLinks(prev, ids);
    });
    setLastJob(null);
    setPreview(null);
  }, []);

  const runRender = useCallback(
    async (targetNodeId?: string, renderAll = false) => {
      if (!workflow) return;
      const target = renderAll
        ? resolveTargetNode(workflow, selectedNodeId)
        : (targetNodeId ?? resolveTargetNode(workflow, selectedNodeId));
      const targets = renderAll ? workflow.nodes.map((n) => n.id) : [target];
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
        const modelIds = [...new Set(workflow.nodes.map((n) => n.widgets.model).filter((m): m is string => typeof m === "string" && !!m))];
        if (modelIds.length > 0) {
          setStatus("Installing models…");
          await ensureWorkflowModels(workflow);
        }

        setStatus("Rendering…");
        const job = await executeWorkflow(workflow, targets, (update) => {
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
            if (out?.cache_id || out?.stems_id || out?.type === "TEXT") {
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
          setStatus(`Failed: ${formatJobError(job.error)}`);
        }
      } catch (err) {
        setStatus(`Error: ${formatJobError(String(err))}`);
      } finally {
        setRunning(false);
        setCurrentNode(undefined);
        setProgress(undefined);
      }
    },
    [workflow, selectedNodeId],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setModelBrowserOpen(true);
        return;
      }
      if (event.key === "f" || event.key === "\\") {
        if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
        event.preventDefault();
        setFocusMode((prev) => !prev);
        return;
      }
      if (event.shiftKey && event.key.toLowerCase() === "r") {
        event.preventDefault();
        if (!running) void runRender(undefined, true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [running, runRender]);

  const playChain = useCallback(() => {
    const hasStale = workflow?.nodes.some((n) => nodeStatus[n.id] === "stale" || !nodeStatus[n.id]);
    if (preview && !running && !hasStale) {
      const audio = document.querySelector<HTMLAudioElement>(".transport__audio");
      void audio?.play();
      return;
    }
    void runRender();
  }, [preview, running, runRender, workflow, nodeStatus]);

  useEffect(() => {
    if (!workflow) return;
    fetchCompliance(workflow)
      .then((data) => setComplianceWarnings(data.warnings.length))
      .catch(() => setComplianceWarnings(0));
  }, [workflow]);

  const handleModelSelect = useCallback(
    (modelId: string) => {
      if (modelPickTarget) {
        updateWidget(modelPickTarget.nodeId, modelPickTarget.widget, modelId);
        setModelPickTarget(null);
      }
      setModelBrowserOpen(false);
    },
    [modelPickTarget, updateWidget],
  );

  const selectedNode = workflow?.nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedOutput = selectedNodeId && lastJob?.outputs ? lastJob.outputs[selectedNodeId] : undefined;
  const selectedPreviewId = previewCacheId(selectedOutput);
  const selectedNodePreview = selectedPreviewId ? previewUrl(selectedPreviewId) : null;
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
        <p>Could not load template: {loadError}</p>
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
    <div className={`app ${focusMode ? "app--focus" : ""}`}>
      <header className="toolbar">
        <h1>GroovyUI Studio</h1>
        <select
          className="toolbar__select"
          value={templates.find((t) => t.title === workflow.metadata.title)?.id ?? DEFAULT_TEMPLATE}
          onChange={(e) => void loadTemplate(e.target.value)}
        >
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.title}
            </option>
          ))}
        </select>
        <button type="button" onClick={() => setModelBrowserOpen(true)}>
          Model Browser
        </button>
        <button type="button" className={complianceWarnings > 0 ? "toolbar__warn" : ""} onClick={() => setComplianceOpen(true)}>
          Compliance{complianceWarnings > 0 ? ` (${complianceWarnings})` : ""}
        </button>
        <button type="button" onClick={() => downloadWorkflow(workflow)}>
          Save workflow
        </button>
        <span className="status">
          {status} · API {health}
        </span>
      </header>
      <div className={`workspace workspace--with-palette ${focusMode ? "workspace--focus" : ""}`}>
        {!focusMode ? (
          <NodePalette
            onAddNode={(nodeType) => {
              void defaultWidgetsForNode(nodeType).then((widgets) => {
                setWorkflow((prev) => (prev ? addNodeToWorkflow(prev, nodeType, widgets) : prev));
              });
            }}
          />
        ) : null}
        <div className="canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onEdgesDelete={onEdgesDelete}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            onNodeDragStop={onNodeDragStop}
            fitView
            deleteKeyCode={["Backspace", "Delete"]}
          >
            <Background gap={16} color="#2a2f3a" />
            <Controls />
          </ReactFlow>
        </div>
        {!focusMode ? (
          <NodeHelper
            node={selectedNode}
            workflow={workflow}
            output={selectedOutput}
            previewUrl={selectedNodePreview}
            onWidgetChange={updateWidget}
            onBrowseModel={(nodeId, widget) => {
              setModelPickTarget({ nodeId, widget });
              setModelBrowserOpen(true);
            }}
            onAudition={() => {
              if (selectedNodePreview) {
                setNodePreviewUrl(selectedNodePreview);
                setTimeout(() => {
                  document.querySelector<HTMLAudioElement>(".node-audition")?.play();
                }, 0);
              }
            }}
          />
        ) : null}
      </div>
      {nodePreviewUrl ? <audio className="node-audition" src={nodePreviewUrl} hidden /> : null}
      <TransportBar
        workflow={workflow}
        previewUrl={chainPreview}
        running={running}
        currentNode={currentNode}
        progress={progress}
        onRender={() => void runRender()}
        onRenderAll={() => void runRender(undefined, true)}
        onPlay={playChain}
      />
      <ModelBrowser
        open={modelBrowserOpen}
        onClose={() => {
          setModelBrowserOpen(false);
          setModelPickTarget(null);
        }}
        onSelectModel={handleModelSelect}
      />
      <ComplianceDrawer
        open={complianceOpen}
        workflow={workflow}
        outputs={lastJob?.outputs}
        targetNodeId={selectedNodeId}
        onClose={() => setComplianceOpen(false)}
      />
    </div>
  );
}
