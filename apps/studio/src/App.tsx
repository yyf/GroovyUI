import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  type Connection,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeTypes,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  finishActivationSession,
  hasActiveActivationSession,
  recordActivationMilestone,
  startActivationSession,
} from "./activationDiagnostics";
import {
  executeWorkflow,
  fetchCompliance,
  fetchAllNodeSchemas,
  fetchStudioSettings,
  fetchWorkflowValidation,
  fetchTemplate,
  fetchModelCard,
  findMissingWorkflowModels,
  installModelWithProgress,
  fetchWaveform,
  fetchMidiRoll,
  listTemplates,
  saveUserTemplate,
  shareWorkflow,
  deleteUserTemplate,
  previewUrl,
  uploadProjectAudio,
  type TemplateListItem,
} from "./api";
import ComplianceDrawer from "./components/ComplianceDrawer";
import FlowViewportBridge from "./components/FlowViewportBridge";
import GroovyFlowNode from "./components/GroovyFlowNode";
import type { GroovyNodeData } from "./components/GroovyFlowNode";
import ModuleGroupNode from "./components/ModuleGroupNode";
import ModelBrowser from "./components/ModelBrowser";
import NodeHelper from "./components/NodeHelper";
import NodePalette, { defaultWidgetsForNode } from "./components/NodePalette";
import OnboardingOverlay, { isOnboardingComplete } from "./components/OnboardingOverlay";
import SettingsDrawer from "./components/SettingsDrawer";
import SidePanel from "./components/SidePanel";
import StudioTopBar from "./components/StudioTopBar";
import TransportBar from "./components/TransportBar";
import RenderActivityBar from "./components/RenderActivityBar";
import { AuditionContext } from "./context/AuditionContext";
import { augmentNodeWithExample, getMinimalPatch, type MinimalPatch } from "./nodeMinimalPatches";
import { useLiveIo } from "./hooks/useLiveIo";
import { useWorkflowHistory } from "./hooks/useWorkflowHistory";
import {
  applyModelSwaps,
  resolveFastPathPreviewTarget,
  runFastPathSequence,
  type FastPathRunResult,
} from "./fastPath";
import {
  resolveInferenceParams,
  widgetsAfterModelSwap,
  widgetsForDroppedModel,
} from "./modelNodeWidgets";
import type { JobState, ModelBrowserLaunch, NodeRenderStatus, NodeSchema, Workflow } from "./types";
import type { WorkflowClipboard } from "./workflow";
import {
  cachedStatusFromOutputs,
  connectNodes,
  addNodeToWorkflow,
  applyDroppedAudio,
  groupForSelection,
  edgeIdsOnPathToNode,
  formatJobError,
  layoutWorkflowNodes,
  flowNodesSyncKey,
  listDistinctChainHops,
  mergeFlowNodes,
  nodeIssuesFromValidation,
  previewCacheId,
  previewMidiId,
  savedFilePath,
  savedProvenancePath,
  duplicateSelection,
  extractSelection,
  pasteSelection,
  preferredAuditionNodeId,
  removeLinks,
  removeNodesFromWorkflow,
  resolveComparePair,
  resolveNodeListenId,
  resolveNodeListenOutput,
  resolveNodeInspectorOutput,
  resolveRenderAllTargets,
  resolveTargetNode,
  syncPositions,
  toggleGroupCollapsed,
  workflowToFlowEdges,
  workflowToFlowNodes,
} from "./workflow";

const nodeTypes: NodeTypes = { groovy: GroovyFlowNode, groovyGroup: ModuleGroupNode };

function emptyWorkflow(): Workflow {
  return {
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: crypto.randomUUID(),
    metadata: { title: "Untitled", description: "Pick a template or add nodes to start." },
    nodes: [],
    links: [],
    groups: [],
    view: { zoom: 1, pan: { x: 0, y: 0 } },
  };
}

function formatActivationDuration(elapsedMs: number): string {
  const totalSeconds = Math.max(0, Math.round(elapsedMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

export default function App() {
  const { workflow, setWorkflow, resetHistory, undo, redo } = useWorkflowHistory(emptyWorkflow());
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [activeTemplateId, setActiveTemplateId] = useState("");
  const [viewportFitKey, setViewportFitKey] = useState(0);
  const [nodeSchemas, setNodeSchemas] = useState<Record<string, NodeSchema>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const clipboardRef = useRef<WorkflowClipboard | null>(null);
  const flowCenterRef = useRef(() => ({ x: 320, y: 200 }));
  const pendingSelectionRef = useRef<Set<string> | null>(null);
  const workflowRef = useRef(workflow);
  workflowRef.current = workflow;
  const pasteCountRef = useRef(0);
  const [nodeStatus, setNodeStatus] = useState<Record<string, NodeRenderStatus>>({});
  const [nodeIssues, setNodeIssues] = useState<Record<string, string>>({});
  const [failedNodeId, setFailedNodeId] = useState<string | null>(null);
  const [lastJob, setLastJob] = useState<JobState | null>(null);
  const [status, setStatus] = useState("Ready");
  const [running, setRunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [progress, setProgress] = useState<number | undefined>();
  const [currentNode, setCurrentNode] = useState<string | undefined>();
  const [renderMessage, setRenderMessage] = useState<string | undefined>();
  const [renderStartedAt, setRenderStartedAt] = useState<number | undefined>();
  const [lastProgressAt, setLastProgressAt] = useState<number | undefined>();
  const activeExecutionRef = useRef<{ cancel: () => Promise<void> } | null>(null);
  const fastPathStopRef = useRef(false);
  const [modelBrowserOpen, setModelBrowserOpen] = useState(false);
  const [modelBrowserLaunch, setModelBrowserLaunch] = useState<ModelBrowserLaunch | null>(null);
  const [modelPickTarget, setModelPickTarget] = useState<{ nodeId: string; widget: string } | null>(null);
  const [complianceOpen, setComplianceOpen] = useState(false);
  const [complianceWarnings, setComplianceWarnings] = useState(0);
  const [complianceFastPath, setComplianceFastPath] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [inferenceStubActive, setInferenceStubActive] = useState(false);
  const [forceRebuildNext, setForceRebuildNext] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helperOpen, setHelperOpen] = useState(false);
  const [workflowBarOpen, setWorkflowBarOpen] = useState(true);
  const [generateOpenNonce, setGenerateOpenNonce] = useState(0);
  const [onboardingOpen, setOnboardingOpen] = useState(() => !isOnboardingComplete());
  const [dropHint, setDropHint] = useState(false);
  const [transportWaveform, setTransportWaveform] = useState<number[]>([]);
  const [transportWaveformDuration, setTransportWaveformDuration] = useState(0);
  const [transportMidiRoll, setTransportMidiRoll] = useState<{
    duration: number;
    notes: { start: number; end: number; pitch: number; velocity: number; drum?: boolean }[];
    minPitch: number;
    maxPitch: number;
  } | null>(null);
  const [activeEdgeIds, setActiveEdgeIds] = useState<Set<string>>(new Set());
  const [auditionNonce, setAuditionNonce] = useState(0);

  const handleStudioSettingsChange = useCallback(
    (settings: import("./types").StudioSettings) => {
      setInferenceStubActive(settings.inference_stub_active);
    },
    [],
  );

  const beginGenerateTask = useCallback(() => {
    startActivationSession({ source: "generate" });
  }, []);

  const handlePlaybackStarted = useCallback(() => {
    const elapsedMs = finishActivationSession("playback_started", {
      preview_kind: "audio",
    });
    if (elapsedMs != null) {
      setStatus(`First audition ready in ${formatActivationDuration(elapsedMs)}`);
    }
  }, []);

  const handlePlaybackFailed = useCallback((reason: string) => {
    if (!hasActiveActivationSession()) return;
    recordActivationMilestone("playback_failed", { reason });
    setStatus("Render complete — click Play now to audition");
  }, []);

  const openModelBrowser = useCallback((launch?: ModelBrowserLaunch | null) => {
    setModelBrowserLaunch(launch ?? null);
    setModelBrowserOpen(true);
  }, []);

  const onOscWidget = useCallback(
    (target: { node_id: string; param: string }, value: number) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        if (!prev.nodes.some((node) => node.id === target.node_id)) return prev;
        return {
          ...prev,
          nodes: prev.nodes.map((node) =>
            node.id === target.node_id
              ? { ...node, widgets: { ...node.widgets, [target.param]: value } }
              : node,
          ),
        };
      });
    },
    [setWorkflow],
  );

  useLiveIo({ enabled: true, onOscWidget });

  const flowNodes = useMemo(
    () => (workflow ? workflowToFlowNodes(workflow, nodeStatus, lastJob?.outputs, nodeSchemas, nodeIssues) : []),
    [workflow, nodeStatus, lastJob?.outputs, nodeSchemas, nodeIssues],
  );
  const flowEdges = useMemo(
    () => (workflow ? workflowToFlowEdges(workflow, activeEdgeIds) : []),
    [workflow, activeEdgeIds],
  );
  const flowNodeSyncKey = useMemo(() => flowNodesSyncKey(flowNodes), [flowNodes]);
  const [nodes, setNodes, applyNodeChanges] = useNodesState<Node>([]);
  const displayNodes = useMemo(() => {
    let merged = mergeFlowNodes(nodes, flowNodes);
    const pending = pendingSelectionRef.current;
    if (pending) {
      merged = merged.map((node) => ({ ...node, selected: pending.has(node.id) }));
    }
    return merged;
  }, [nodes, flowNodes, flowNodeSyncKey]);

  const loadTemplate = useCallback(
    async (templateId: string) => {
      setStatus("Loading template…");
      setLastJob(null);
      setNodeStatus({});
      setComplianceFastPath(false);
      clipboardRef.current = null;
      pasteCountRef.current = 0;
      const data = layoutWorkflowNodes(await fetchTemplate(templateId));
      resetHistory(data);
      setActiveTemplateId(templateId);
      setViewportFitKey((key) => key + 1);
      setLoadError(null);
      try {
        const missing = await findMissingWorkflowModels(data);
        if (missing.length > 0) {
          const label = missing.map((entry) => entry.name || entry.modelId).join(", ");
          setStatus(`Install required: ${label} — Cmd+K to open Model Browser`);
        } else {
          setStatus("Ready");
        }
      } catch {
        setStatus("Ready");
      }
    },
    [resetHistory],
  );

  useEffect(() => {
    if (!workflow) {
      setNodeIssues({});
      return;
    }
    fetchWorkflowValidation(workflow)
      .then((result) => setNodeIssues(nodeIssuesFromValidation(workflow, result)))
      .catch(() => setNodeIssues({}));
  }, [workflow]);

  useEffect(() => {
    fetchAllNodeSchemas()
      .then(setNodeSchemas)
      .catch(() => setNodeSchemas({}));
    listTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]));
    fetchStudioSettings()
      .then((settings) => setInferenceStubActive(settings.inference_stub_active))
      .catch(() => setInferenceStubActive(false));
  }, []);

  useEffect(() => {
    setNodes((current) => {
      let merged = mergeFlowNodes(current, flowNodes);
      const pending = pendingSelectionRef.current;
      if (pending) {
        pendingSelectionRef.current = null;
        merged = merged.map((node) => ({ ...node, selected: pending.has(node.id) }));
      }
      return merged;
    });
  }, [flowNodeSyncKey, flowNodes, setNodes]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const removedIds = changes
        .filter((change): change is NodeChange & { type: "remove"; id: string } => change.type === "remove")
        .map((change) => change.id);
      if (removedIds.length > 0) {
        setWorkflow((prev) => {
          if (!prev) return prev;
          return removeNodesFromWorkflow(prev, new Set(removedIds));
        });
        setLastJob(null);
        setNodeStatus((prev) => {
          const next = { ...prev };
          for (const id of removedIds) delete next[id];
          return next;
        });
      }
      applyNodeChanges(changes);
    },
    [applyNodeChanges, setWorkflow],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const removedIds = changes
        .filter((change): change is EdgeChange & { type: "remove"; id: string } => change.type === "remove")
        .map((change) => change.id);
      if (removedIds.length === 0) return;
      setWorkflow((prev) => {
        if (!prev) return prev;
        return removeLinks(prev, new Set(removedIds));
      });
      setLastJob(null);
    },
    [setWorkflow],
  );

  const selectedNodeIds = useMemo(
    () => nodes.filter((node) => node.selected).map((node) => node.id),
    [nodes],
  );
  const selectedNodeId = selectedNodeIds[0] ?? null;

  const openInspector = useCallback(() => {
    if (!focusMode) setHelperOpen(true);
  }, [focusMode]);

  const registerFlowCenter = useCallback((getter: () => { x: number; y: number }) => {
    flowCenterRef.current = getter;
  }, []);

  useEffect(() => {
    if (selectedNodeId) openInspector();
  }, [selectedNodeId, openInspector]);

  const updateWidget = useCallback(
    (nodeId: string, name: string, value: unknown) => {
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
    },
    [setWorkflow],
  );

  const onNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        return syncPositions(prev, [node]);
      });
    },
    [setWorkflow],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      setWorkflow((prev) => {
        if (!prev) return prev;
        return connectNodes(prev, connection, nodeSchemas);
      });
      setLastJob(null);
    },
    [setWorkflow, nodeSchemas],
  );

  const runRender = useCallback(
    async (targetNodeId?: string, renderAll = false, autoAudition = false) => {
      if (!workflow) return false;
      const singleTarget = targetNodeId ?? resolveTargetNode(workflow, selectedNodeId);
      const targets = renderAll ? resolveRenderAllTargets(workflow) : singleTarget ? [singleTarget] : [];
      if (!targets.length) {
        setStatus("No render target — add nodes to the canvas");
        return false;
      }
      setRunning(true);
      setCancelling(false);
      setStatus("Rendering…");
      setProgress(0);
      setCurrentNode(undefined);
      setRenderMessage(undefined);
      const startedAt = Date.now();
      setRenderStartedAt(startedAt);
      setLastProgressAt(startedAt);
      setFailedNodeId(null);
      setNodeStatus((prev) => {
        const next = { ...prev };
        for (const node of workflow.nodes) {
          next[node.id] = "stale";
        }
        return next;
      });

      try {
        const missing = await findMissingWorkflowModels(workflow);
        if (missing.length > 0) {
          const label = missing.map((entry) => entry.name || entry.modelId).join(", ");
          const needsRuntime = missing.some((entry) => entry.reason === "inference_not_ready");
          setStatus(
            needsRuntime
              ? `Inference setup required: ${label} — reinstall from Model Browser (Cmd+K)`
              : `Install required: ${label} — use Model Browser (Cmd+K)`,
          );
          openModelBrowser({
            mode: "search",
            requiredModelIds: missing.map((entry) => entry.modelId),
          });
          setRunning(false);
          return false;
        }

        setStatus("Rendering…");
        let lastRunningNode: string | undefined;
        const forceRebuild = forceRebuildNext;
        if (forceRebuild) setForceRebuildNext(false);
        const execution = await executeWorkflow(
          workflow,
          targets,
          (update) => {
            setLastProgressAt(Date.now());
            if (update.current_node) {
              lastRunningNode = update.current_node;
              setCurrentNode(update.current_node);
              setNodeStatus((prev) => ({
                ...prev,
                [update.current_node!]: "running",
              }));
            }
            if (update.message) {
              setRenderMessage(update.message);
            }
            if (update.progress != null) {
              setProgress(update.progress);
            }
          },
          { forceRebuild },
        );
        activeExecutionRef.current = execution;
        const job = await execution.promise;
        activeExecutionRef.current = null;

        setLastJob(job);
        if (job.status === "completed") {
          setFailedNodeId(null);
          const outputs = job.outputs ?? {};
          setNodeStatus((prev) => ({ ...prev, ...cachedStatusFromOutputs(workflow, outputs) }));
          let auditionNodeId: string | null = null;
          if (autoAudition) {
            recordActivationMilestone("render_completed");
            auditionNodeId = preferredAuditionNodeId(workflow, outputs);
            if (auditionNodeId) {
              setNodes((current) =>
                current.map((node) => ({
                  ...node,
                  selected: node.id === auditionNodeId,
                })),
              );
              setActiveEdgeIds(edgeIdsOnPathToNode(workflow, auditionNodeId));
              recordActivationMilestone("playback_requested", {
                preview_node_id: auditionNodeId,
              });
              setAuditionNonce((nonce) => nonce + 1);
            } else {
              finishActivationSession("failed", {
                reason: "preview_not_listenable",
              });
            }
          }
          const savedOutput = targets
            .map((nodeId) => {
              const node = workflow.nodes.find((n) => n.id === nodeId);
              return node?.type === "SaveAudio" ? outputs[nodeId] : undefined;
            })
            .find(Boolean);
          const saved = savedFilePath(savedOutput);
          const provenance = savedProvenancePath(savedOutput);
          setStatus(
            saved && provenance
              ? `Saved audio + provenance: ${saved}`
              : saved
                ? `Saved to ${saved}`
                : autoAudition && !auditionNodeId
                  ? "Render complete — Preview produced no listenable output"
                  : "Complete",
          );
        } else if (job.status === "cancelled") {
          const outputs = job.outputs ?? {};
          setNodeStatus((prev) => ({ ...prev, ...cachedStatusFromOutputs(workflow, outputs) }));
          setStatus("Cancelled — completed nodes kept");
        } else {
          const message = formatJobError(job.error);
          setStatus(`Failed: ${message}`);
          if (job.outputs && Object.keys(job.outputs).length > 0) {
            setNodeStatus((prev) => ({
              ...prev,
              ...cachedStatusFromOutputs(workflow, job.outputs ?? {}),
            }));
          }
          if (lastRunningNode) {
            setFailedNodeId(lastRunningNode);
            setNodeIssues((prev) => ({ ...prev, [lastRunningNode!]: message }));
          }
        }
        return job.status === "completed";
      } catch (err) {
        setStatus(`Error: ${formatJobError(String(err))}`);
        return false;
      } finally {
        activeExecutionRef.current = null;
        setRunning(false);
        setCancelling(false);
        setCurrentNode(undefined);
        setRenderMessage(undefined);
        setRenderStartedAt(undefined);
        setLastProgressAt(undefined);
        setProgress(undefined);
      }
    },
    [workflow, selectedNodeId, openModelBrowser, setNodes, forceRebuildNext],
  );

  const cancelRender = useCallback(() => {
    const active = activeExecutionRef.current;
    if (!active || cancelling) return;
    setCancelling(true);
    setStatus("Stopping render…");
    void active.cancel().catch(() => {
      setCancelling(false);
      setStatus("Could not stop render");
    });
  }, [cancelling]);

  const auditionNode = useCallback(
    (nodeId: string) => {
      if (!workflow) return;
      setNodes((current) => current.map((node) => ({ ...node, selected: node.id === nodeId })));
      if (!resolveNodeListenId(workflow, nodeId, lastJob?.outputs)) return;
      setActiveEdgeIds(edgeIdsOnPathToNode(workflow, nodeId));
      setAuditionNonce((nonce) => nonce + 1);
    },
    [lastJob?.outputs, workflow, setNodes],
  );

  const playSelectedNode = useCallback(() => {
    if (running || !workflow || !selectedNodeId) return;
    if (!resolveNodeListenId(workflow, selectedNodeId, lastJob?.outputs)) {
      setStatus("Render this node first");
      return;
    }
    setActiveEdgeIds(edgeIdsOnPathToNode(workflow, selectedNodeId));
    setAuditionNonce((nonce) => nonce + 1);
  }, [running, workflow, selectedNodeId, lastJob?.outputs]);

  const augmentMinimalPatchForNode = useCallback(
    (patch: MinimalPatch, nodeId: string, schema: NodeSchema | undefined) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        const { workflow: next, focusNodeId, changed } = augmentNodeWithExample(
          prev,
          nodeId,
          schema,
          patch,
        );
        if (!changed) {
          setStatus("Node already wired");
          return prev;
        }
        pendingSelectionRef.current = new Set([focusNodeId]);
        setLastJob(null);
        setActiveEdgeIds(new Set());
        setStatus(`Wired example I/O for ${patch.workflow.metadata.title}`);
        return next;
      });
    },
    [setWorkflow],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openModelBrowser();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "g") {
        event.preventDefault();
        setWorkflowBarOpen(true);
        setGenerateOpenNonce((n) => n + 1);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) {
          redo();
        } else {
          undo();
        }
        setLastJob(null);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a") {
        if (nodes.length === 0) return;
        event.preventDefault();
        setNodes((current) => current.map((node) => ({ ...node, selected: true })));
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "c") {
        if (!workflow || selectedNodeIds.length === 0) return;
        event.preventDefault();
        clipboardRef.current = extractSelection(workflow, selectedNodeIds);
        pasteCountRef.current = 0;
        setStatus(`Copied ${clipboardRef.current.nodes.length} node(s)`);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "v") {
        const clip = clipboardRef.current;
        if (!clip?.nodes.length || !workflow) return;
        event.preventDefault();
        pasteCountRef.current += 1;
        const offset = { x: 48 * pasteCountRef.current, y: 48 * pasteCountRef.current };
        const { workflow: next, newNodeIds } = pasteSelection(workflow, clip, offset);
        pendingSelectionRef.current = new Set(newNodeIds);
        setWorkflow(next);
        setLastJob(null);
        setStatus(`Pasted ${newNodeIds.length} node(s)`);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d") {
        if (!workflow || selectedNodeIds.length === 0) return;
        event.preventDefault();
        const { workflow: next, newNodeIds } = duplicateSelection(workflow, selectedNodeIds);
        pendingSelectionRef.current = new Set(newNodeIds);
        setWorkflow(next);
        setLastJob(null);
        setStatus(`Duplicated ${newNodeIds.length} node(s)`);
        return;
      }
      if (event.key === "Tab" && selectedNodeIds.length === 1 && selectedNodeId && workflow) {
        const workflowNode = workflow.nodes.find((node) => node.id === selectedNodeId);
        const rfNode = nodes.find((node) => node.id === selectedNodeId);
        const nodeType =
          workflowNode?.type ?? (rfNode?.data as GroovyNodeData | undefined)?.label ?? null;
        if (nodeType) {
          const patch = getMinimalPatch(nodeType, nodeSchemas);
          if (patch) {
            event.preventDefault();
            augmentMinimalPatchForNode(patch, selectedNodeId, nodeSchemas[nodeType]);
            return;
          }
        }
      }
      if (event.key === "f" || event.key === "\\") {
        event.preventDefault();
        setFocusMode((prev) => !prev);
        return;
      }
      if (event.key === "Escape" && running && activeExecutionRef.current) {
        event.preventDefault();
        cancelRender();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
        event.preventDefault();
        if (!running) void runRender(undefined, true);
        return;
      }
      if (event.shiftKey && event.key.toLowerCase() === "r") {
        event.preventDefault();
        if (!running) void runRender(undefined, true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [running, runRender, cancelRender, undo, redo, workflow, nodes, selectedNodeIds, selectedNodeId, nodeSchemas, augmentMinimalPatchForNode, openModelBrowser, setNodes]);

  useEffect(() => {
    if (!workflow) return;
    fetchCompliance(workflow)
      .then((data) => setComplianceWarnings(data.warnings.length))
      .catch(() => setComplianceWarnings(0));
  }, [workflow]);

  const handleModelSelect = useCallback(
    (modelId: string) => {
      if (modelPickTarget) {
        const { nodeId, widget } = modelPickTarget;
        const node = workflowRef.current?.nodes.find((entry) => entry.id === nodeId);
        void Promise.all([
          fetchModelCard(modelId).catch(() => null),
          node?.widgets.model
            ? fetchModelCard(String(node.widgets.model)).catch(() => null)
            : Promise.resolve(null),
        ]).then(([nextCard, prevCard]) => {
          const nextParams = resolveInferenceParams(modelId, nextCard?.inference_params);
          const previousParams = resolveInferenceParams(
            String(node?.widgets.model ?? ""),
            prevCard?.inference_params,
          );
          const schema = node ? nodeSchemas[node.type] : undefined;
          const schemaWidgetNames = (schema?.widgets ?? []).map((entry) => entry.name);
          setWorkflow((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              nodes: prev.nodes.map((entry) => {
                if (entry.id !== nodeId) return entry;
                if (widget !== "model") {
                  return { ...entry, widgets: { ...entry.widgets, [widget]: modelId } };
                }
                return {
                  ...entry,
                  widgets: widgetsAfterModelSwap({
                    existing: entry.widgets,
                    modelId,
                    schemaWidgetNames,
                    previousParams,
                    nextParams,
                  }),
                };
              }),
            };
          });
          setNodeStatus((prev) => ({ ...prev, [nodeId]: "stale" }));
        });
        setModelPickTarget(null);
      }
      setModelBrowserOpen(false);
    },
    [modelPickTarget, nodeSchemas, setWorkflow],
  );

  const handleDropModel = useCallback(
    (modelId: string, nodeType: string) => {
      if (!workflow) return;
      void Promise.all([
        defaultWidgetsForNode(nodeType),
        fetchModelCard(modelId).catch(() => null),
      ]).then(([schemaDefaults, card]) => {
        const params = resolveInferenceParams(modelId, card?.inference_params);
        const widgets = widgetsForDroppedModel({
          schemaDefaults,
          modelId,
          params,
        });
        setWorkflow((prev) => {
          if (!prev) return prev;
          const { workflow: next, nodeId } = addNodeToWorkflow(prev, nodeType, widgets);
          pendingSelectionRef.current = new Set([nodeId]);
          return next;
        });
        setLastJob(null);
        setStatus(`Dropped ${nodeType} with ${modelId}`);
      });
      setModelBrowserOpen(false);
    },
    [workflow, setWorkflow],
  );

  const handleAudioDrop = useCallback(
    async (files: FileList | null) => {
      if (!files?.length || !workflow) return;
      const file = files[0];
      if (!file.type.startsWith("audio/") && !file.name.match(/\.(wav|flac|mp3|ogg|mp4|m4a)$/i)) {
        setStatus("Drop an audio file (WAV, FLAC, MP3, OGG)");
        return;
      }
      try {
        setStatus("Uploading audio…");
        const path = await uploadProjectAudio(file);
        setWorkflow((prev) => {
          if (!prev) return prev;
          return applyDroppedAudio(prev, path);
        });
        setNodeStatus((prev) => {
          const next = { ...prev };
          for (const node of workflow.nodes) {
            if (node.type === "LoadAudio") next[node.id] = "stale";
          }
          const loadNode = workflow.nodes.find((node) => node.type === "LoadAudio");
          if (!loadNode) {
            next[`n${workflow.nodes.length + 1}`] = "stale";
          }
          return next;
        });
        setLastJob(null);
        setStatus(`Loaded ${file.name}`);
      } catch (err) {
        setStatus(`Upload failed: ${formatJobError(String(err))}`);
      }
    },
    [workflow, setWorkflow],
  );

  const activeGroup = useMemo(
    () => (workflow ? groupForSelection(workflow, selectedNodeIds) : null),
    [workflow, selectedNodeIds],
  );

  const handleToggleGroupCollapse = useCallback(() => {
    if (!workflow || !activeGroup) return;
    setWorkflow(toggleGroupCollapsed(workflow, activeGroup.id));
    setStatus(activeGroup.collapsed ? `Expanded ${activeGroup.title}` : `Collapsed ${activeGroup.title}`);
  }, [workflow, activeGroup, setWorkflow]);

  const handleSaveAsTemplate = useCallback(async () => {
    if (!workflow) return;
    try {
      const title = window.prompt("Template title", workflow.metadata.title) ?? workflow.metadata.title;
      const saved = await saveUserTemplate(workflow, title);
      const nextTemplates = await listTemplates();
      setTemplates(nextTemplates);
      // Stay on the current canvas — the graph is already what was saved.
      // Share (workflow bar) is the explicit JSON export path.
      setActiveTemplateId(saved.template_id);
      setStatus(`Saved to Your templates: ${title.trim() || saved.template_id}`);
    } catch (err) {
      setStatus(`Template save failed: ${String(err)}`);
    }
  }, [workflow]);

  const handleShareWorkflow = useCallback(async () => {
    if (!workflow) return;
    try {
      const shared = await shareWorkflow(workflow);
      if (shared.status === "cancelled") {
        setStatus("Share cancelled");
        return;
      }
      setStatus(`Shared ${shared.relative_path}`);
    } catch (err) {
      setStatus(`Share failed: ${String(err)}`);
    }
  }, [workflow]);

  useEffect(() => {
    const onShareShortcut = (event: KeyboardEvent) => {
      if (
        event.repeat ||
        (!event.metaKey && !event.ctrlKey) ||
        event.altKey ||
        event.shiftKey ||
        event.key.toLowerCase() !== "s"
      ) {
        return;
      }
      event.preventDefault();
      void handleShareWorkflow();
    };
    window.addEventListener("keydown", onShareShortcut);
    return () => window.removeEventListener("keydown", onShareShortcut);
  }, [handleShareWorkflow]);

  const handleDeleteUserTemplate = useCallback(
    async (templateId: string) => {
      try {
        await deleteUserTemplate(templateId);
        const nextTemplates = await listTemplates();
        setTemplates(nextTemplates);
        if (activeTemplateId === templateId) {
          resetHistory(emptyWorkflow());
          setActiveTemplateId("");
          setLastJob(null);
          setNodeStatus({});
          setComplianceFastPath(false);
        }
        setStatus(`Removed from Your templates: ${templateId}`);
      } catch (err) {
        setStatus(`Template remove failed: ${String(err)}`);
      }
    },
    [activeTemplateId, resetHistory],
  );

  const currentNodeLabel = useMemo(() => {
    if (!workflow || !currentNode) return undefined;
    const node = workflow.nodes.find((n) => n.id === currentNode);
    return node?.type ?? currentNode;
  }, [workflow, currentNode]);

  const selectedNode = workflow?.nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedNodes = useMemo(() => {
    if (!workflow) return [];
    const byId = new Map(workflow.nodes.map((node) => [node.id, node]));
    return selectedNodeIds.map((id) => byId.get(id)).filter((node): node is NonNullable<typeof node> => Boolean(node));
  }, [workflow, selectedNodeIds]);
  const selectedOutput = selectedNodeId && lastJob?.outputs ? lastJob.outputs[selectedNodeId] : undefined;
  const selectedListenOutput =
    workflow && selectedNodeId
      ? resolveNodeListenOutput(workflow, selectedNodeId, lastJob?.outputs)
      : undefined;
  const selectedInspectorOutput = resolveNodeInspectorOutput(selectedOutput, selectedListenOutput);
  const selectedMidiId = previewMidiId(selectedListenOutput) ?? previewMidiId(selectedOutput);
  const selectedPreviewId = previewCacheId(selectedListenOutput) ?? previewCacheId(selectedOutput);
  const selectedListenId =
    workflow && selectedNodeId
      ? resolveNodeListenId(workflow, selectedNodeId, lastJob?.outputs)
      : null;
  const selectedNodePreview = selectedListenId ? previewUrl(selectedListenId) : null;
  const previewKind =
    selectedMidiId || selectedOutput?.type === "MIDI"
      ? "midi"
      : selectedPreviewId
        ? "audio"
        : selectedNode?.type === "AudioToMIDI" || selectedNode?.type === "LoadMIDI"
          ? "midi"
          : null;
  const compareResolution = useMemo(
    () =>
      workflow && selectedNodeIds.length === 2
        ? resolveComparePair(workflow, lastJob?.outputs, selectedNodeIds)
        : null,
    [workflow, selectedNodeIds, lastJob?.outputs],
  );
  const comparePair = compareResolution?.pair.length ? compareResolution.pair : null;
  const compareNote = compareResolution?.note ?? null;
  const compareMissingRender = compareResolution?.missingRender ?? false;
  const chainHops = useMemo(
    () => (workflow ? listDistinctChainHops(workflow, lastJob?.outputs) : []),
    [workflow, lastJob?.outputs],
  );
  const focusCompareHop = useCallback(
    (nodeIdA: string, nodeIdB: string) => {
      setNodes((current) =>
        current.map((node) => ({
          ...node,
          selected: node.id === nodeIdA || node.id === nodeIdB,
        })),
      );
    },
    [setNodes],
  );
  const selectedSavedPath = savedFilePath(selectedOutput);
  const transportEmptyHint = !selectedNodeId
    ? "Select a node"
    : selectedNode?.type === "SaveAudio"
      ? selectedSavedPath
        ? `Saved to ${selectedSavedPath}`
        : "Render to write audio file"
      : selectedMidiId || selectedNodePreview
        ? ""
        : previewKind === "midi"
          ? "Render to preview MIDI"
          : "Render to preview this node";

  useEffect(() => {
    document.querySelector<HTMLAudioElement>(".transport__audio")?.pause();
  }, [selectedNodeId]);

  useEffect(() => {
    if (!selectedMidiId) {
      setTransportMidiRoll(null);
      return;
    }
    fetchMidiRoll(selectedMidiId)
      .then((data) =>
        setTransportMidiRoll({
          duration: data.duration,
          notes: data.notes,
          minPitch: data.min_pitch,
          maxPitch: data.max_pitch,
        }),
      )
      .catch(() => setTransportMidiRoll(null));
  }, [selectedMidiId]);

  useEffect(() => {
    if (!selectedNodePreview || previewKind === "midi") {
      setTransportWaveform([]);
      setTransportWaveformDuration(0);
      return;
    }
    const match = selectedNodePreview.match(/\/api\/cache\/([^/?]+)\/preview/);
    if (!match) {
      setTransportWaveform([]);
      setTransportWaveformDuration(0);
      return;
    }
    fetchWaveform(match[1], 512)
      .then((data) => {
        setTransportWaveform(data.peaks);
        setTransportWaveformDuration(data.duration);
      })
      .catch(() => {
        setTransportWaveform([]);
        setTransportWaveformDuration(0);
      });
  }, [selectedNodePreview, previewKind]);

  useEffect(() => {
    const onAudioEvent = (event: Event) => {
      if (!workflow || !selectedNodeId) return;
      if (event.type === "play") {
        setActiveEdgeIds(edgeIdsOnPathToNode(workflow, selectedNodeId));
      } else {
        setActiveEdgeIds(new Set());
      }
      if (event.type === "ended") {
        setActiveEdgeIds(new Set());
      }
    };
    const transport = document.querySelector<HTMLAudioElement>(".transport__audio");
    if (!transport) return;
    transport.addEventListener("play", onAudioEvent);
    transport.addEventListener("pause", onAudioEvent);
    transport.addEventListener("ended", onAudioEvent);
    return () => {
      transport.removeEventListener("play", onAudioEvent);
      transport.removeEventListener("pause", onAudioEvent);
      transport.removeEventListener("ended", onAudioEvent);
    };
  }, [workflow, selectedNodeId, selectedNodePreview]);

  const selectedTemplateId = activeTemplateId;

  const applyWorkflow = useCallback(
    (next: Workflow) => {
      resetHistory(next);
      setLastJob(null);
      setNodeStatus({});
      setComplianceFastPath(false);
      setStatus("Workflow applied — ready to render");
      setLoadError(null);
    },
    [resetHistory],
  );

  const handleImportWorkflow = useCallback(
    async (file: File) => {
      setStatus(`Importing ${file.name}…`);
      try {
        const parsed: unknown = JSON.parse(await file.text());
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("The selected file does not contain a workflow object.");
        }
        const next = parsed as Workflow;
        const validation = await fetchWorkflowValidation(next);
        if (!validation.valid) {
          const details = validation.errors.map((issue) => issue.message).join("; ");
          throw new Error(details || "The workflow is invalid.");
        }
        applyWorkflow(next);
        setActiveTemplateId("");
        setViewportFitKey((key) => key + 1);
        clipboardRef.current = null;
        pasteCountRef.current = 0;
        setStatus(`Imported ${file.name}`);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setStatus(`Workflow import failed: ${message}`);
      }
    },
    [applyWorkflow],
  );

  const applyGeneratedWorkflow = useCallback(
    (next: Workflow) => {
      if (!hasActiveActivationSession()) {
        startActivationSession({ source: "suggestion_apply" });
      }
      recordActivationMilestone("workflow_applied");
      applyWorkflow(layoutWorkflowNodes(next));
      setComplianceFastPath(true);
      setComplianceOpen(true);
      setStatus("Review licenses before installing or rendering");
    },
    [applyWorkflow],
  );

  const installRenderAndAudition = useCallback(async (): Promise<FastPathRunResult> => {
    const current = workflowRef.current;
    if (!current) throw new Error("No workflow is loaded.");
    const previewTarget = resolveFastPathPreviewTarget(current);
    if (!previewTarget) {
      finishActivationSession("failed", { reason: "preview_missing" });
      throw new Error("Fast audition needs a Preview node.");
    }
    if (!hasActiveActivationSession()) {
      startActivationSession({ source: "fast_path_commit" });
      recordActivationMilestone("workflow_applied");
    }
    recordActivationMilestone("compliance_confirmed", {
      preview_node_id: previewTarget,
    });
    fastPathStopRef.current = false;
    try {
      const result = await runFastPathSequence({
        workflow: current,
        findMissing: findMissingWorkflowModels,
        installModel: installModelWithProgress,
        shouldStop: () => fastPathStopRef.current,
        onInstallStart: (model, _index, total) => {
          recordActivationMilestone("install_started", {
            model_id: model.modelId,
            model_count: total,
          });
        },
        onInstallComplete: (model, _index, total) => {
          recordActivationMilestone("install_completed", {
            model_id: model.modelId,
            model_count: total,
          });
        },
        onInstallProgress: (model, index, total, state) => {
          const percent = Math.round((state.progress ?? 0) * 100);
          setStatus(
            `Installing ${model.name || model.modelId} (${index + 1}/${total}) — ${percent}%`,
          );
        },
        renderPreview: async () => {
          setComplianceOpen(false);
          setStatus("Models ready — rendering Preview branch…");
          recordActivationMilestone("render_started", {
            preview_node_id: previewTarget,
          });
          return runRender(previewTarget, false, true);
        },
      });
      if (result === "cancelled") {
        finishActivationSession("cancelled", { reason: "install_stop" });
        setStatus("Install chain stopped safely — render was not started");
        return result;
      }
      setComplianceFastPath(false);
      return result;
    } catch (err) {
      finishActivationSession("failed", { reason: "fast_path_error" });
      setStatus(`Fast path stopped: ${formatJobError(String(err))}`);
      throw err;
    }
  }, [runRender]);

  const stopFastPathInstall = useCallback(() => {
    fastPathStopRef.current = true;
    setStatus("Interrupting active model download…");
  }, []);

  const handleBrowseModelsFromCompliance = useCallback(
    (opts: { nodeType?: string; commercialOnly?: boolean; query?: string }) => {
      setComplianceOpen(false);
      openModelBrowser({
        mode: "search",
        commercialOnly: opts.commercialOnly ?? true,
        taskType: opts.query,
        query: opts.query,
        filterNodeType: opts.nodeType ?? null,
      });
    },
    [openModelBrowser],
  );

  const handleApplyModelSwap = useCallback(
    (nodeId: string, modelId: string) => {
      updateWidget(nodeId, "model", modelId);
      if (!complianceFastPath) setComplianceOpen(false);
      setStatus(`Swapped ${nodeId} model → ${modelId}`);
    },
    [complianceFastPath, updateWidget],
  );

  const handleApplyModelSwaps = useCallback(
    (swaps: Array<{ nodeId: string; modelId: string }>) => {
      setWorkflow((prev) => (prev ? applyModelSwaps(prev, swaps) : prev));
      setNodeStatus((prev) => {
        const next = { ...prev };
        for (const swap of swaps) next[swap.nodeId] = "stale";
        return next;
      });
      setStatus(`Applied ${swaps.length} commercial-safe model replacement${swaps.length === 1 ? "" : "s"}`);
    },
    [setWorkflow],
  );

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
    <AuditionContext.Provider value={auditionNode}>
      <div className={`app ${focusMode ? "app--focus" : ""}`}>
        <StudioTopBar
          templates={templates}
          selectedTemplateId={selectedTemplateId}
          onSelectTemplate={(id) => void loadTemplate(id)}
          onDeleteUserTemplate={(id) => void handleDeleteUserTemplate(id)}
          onApplyWorkflow={applyGeneratedWorkflow}
          onGenerateTaskStart={beginGenerateTask}
          generateOpenNonce={generateOpenNonce}
          complianceWarnings={complianceWarnings}
          inferenceStubActive={inferenceStubActive}
          onModelBrowser={() => openModelBrowser()}
          onCompliance={() => setComplianceOpen(true)}
          onShareWorkflow={() => void handleShareWorkflow()}
          workflowBarOpen={workflowBarOpen}
          onToggleWorkflowBar={() => setWorkflowBarOpen((prev) => !prev)}
          settings={{
            groupCollapsed: activeGroup ? (activeGroup.collapsed ?? false) : null,
            paletteOpen,
            helperOpen,
            onImportWorkflow: (file) => void handleImportWorkflow(file),
            onSaveAsTemplate: () => void handleSaveAsTemplate(),
            onToggleGroupCollapse: handleToggleGroupCollapse,
            onTogglePalette: () => setPaletteOpen((prev) => !prev),
            onToggleHelper: () => setHelperOpen((prev) => !prev),
            onOpenStudioSettings: () => setSettingsOpen(true),
          }}
        />
        <div
          className={[
            "workspace",
            paletteOpen && !focusMode ? "workspace--palette-open" : "",
            helperOpen && !focusMode ? "workspace--helper-open" : "",
            focusMode ? "workspace--focus" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {!focusMode ? (
            <SidePanel side="left" label="Nodes" open={paletteOpen} onToggle={() => setPaletteOpen((prev) => !prev)}>
              <NodePalette
                onAddNode={(nodeType) => {
                  void defaultWidgetsForNode(nodeType).then((widgets) => {
                    const center = flowCenterRef.current();
                    setWorkflow((prev) => {
                      if (!prev) return prev;
                      const { workflow: next, nodeId } = addNodeToWorkflow(prev, nodeType, widgets, center);
                      pendingSelectionRef.current = new Set([nodeId]);
                      return next;
                    });
                    setLastJob(null);
                  });
                }}
              />
            </SidePanel>
          ) : null}
          <div
            className={`canvas${dropHint ? " canvas--drop" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDropHint(true);
            }}
            onDragLeave={() => setDropHint(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDropHint(false);
              void handleAudioDrop(event.dataTransfer.files);
            }}
          >
            {dropHint ? <div className="canvas__drop-hint">Drop audio to load</div> : null}
            <ReactFlowProvider>
              <ReactFlow
                nodes={displayNodes}
                edges={flowEdges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeDragStop={onNodeDragStop}
                onNodeClick={() => openInspector()}
                onNodeDoubleClick={(_, node) => auditionNode(node.id)}
                deleteKeyCode={["Backspace", "Delete"]}
                panOnDrag={[1, 2]}
                panActivationKeyCode="Space"
                selectionOnDrag
                selectionKeyCode={null}
                multiSelectionKeyCode={["Shift", "Meta", "Control"]}
                proOptions={{ hideAttribution: true }}
              >
                <FlowViewportBridge
                  canvasSelector=".canvas"
                  onCenterReady={registerFlowCenter}
                  nodeSyncKey={flowNodeSyncKey}
                  fitViewKey={viewportFitKey}
                />
                <Background gap={28} color="#222222" size={1} />
                <Controls className="flow-controls" showInteractive={false} />
              </ReactFlow>
            </ReactFlowProvider>
          </div>
          {!focusMode ? (
            <SidePanel side="right" label="Inspector" open={helperOpen} onToggle={() => setHelperOpen((prev) => !prev)}>
              <NodeHelper
                node={selectedNode}
                selectedNodes={selectedNodes}
                selectionOutputs={lastJob?.outputs ?? null}
                workflow={workflow}
                output={selectedInspectorOutput}
                previewUrl={selectedNodePreview}
                comparePair={comparePair}
                compareNote={compareNote}
                compareMissingRender={compareMissingRender}
                chainHops={chainHops}
                onSelectCompareHop={focusCompareHop}
                showCompare={selectedNodeIds.length === 2}
                onWidgetChange={updateWidget}
                onBrowseModel={(nodeId, widget) => {
                  setModelPickTarget({ nodeId, widget });
                  openModelBrowser();
                }}
                onAudition={() => {
                  if (selectedNodeId) auditionNode(selectedNodeId);
                }}
                onCompareAudition={(nodeId) => auditionNode(nodeId)}
                onOpenCompliance={() => setComplianceOpen(true)}
                renderIssue={selectedNodeId ? nodeIssues[selectedNodeId] : null}
                renderIssueDetail={
                  failedNodeId === selectedNodeId && lastJob?.status === "failed"
                    ? lastJob.error ?? null
                    : null
                }
              />
            </SidePanel>
          ) : null}
        </div>
        <RenderActivityBar
          running={running}
          nodeLabel={currentNodeLabel}
          message={renderMessage}
          progress={progress}
          startedAt={renderStartedAt}
          lastProgressAt={lastProgressAt}
          cancelling={cancelling}
          onCancel={cancelRender}
        />
        <TransportBar
          previewUrl={selectedNodePreview}
          previewKind={previewKind}
          waveformPeaks={transportWaveform}
          waveformDuration={transportWaveformDuration}
          midiRoll={transportMidiRoll}
          emptyHint={transportEmptyHint}
          running={running}
          statusMessage={status}
          onRender={() => void runRender()}
          onRenderAll={() => void runRender(undefined, true)}
          onPlay={playSelectedNode}
          auditionNonce={auditionNonce}
          onPlaybackStarted={handlePlaybackStarted}
          onPlaybackFailed={handlePlaybackFailed}
        />
        <ModelBrowser
          open={modelBrowserOpen}
          onClose={() => {
            setModelBrowserOpen(false);
            setModelBrowserLaunch(null);
            setModelPickTarget(null);
          }}
          onSelectModel={handleModelSelect}
          onDropModel={handleDropModel}
          onApplyWorkflow={applyGeneratedWorkflow}
          launch={modelBrowserLaunch}
          filterNodeType={
            modelPickTarget
              ? workflow?.nodes.find((node) => node.id === modelPickTarget.nodeId)?.type ?? null
              : null
          }
        />
        <ComplianceDrawer
          open={complianceOpen}
          workflow={workflow}
          outputs={lastJob?.outputs}
          targetNodeId={selectedNodeId}
          onClose={() => setComplianceOpen(false)}
          onBrowseModels={handleBrowseModelsFromCompliance}
          onApplyModelSwap={handleApplyModelSwap}
          onApplyModelSwaps={handleApplyModelSwaps}
          fastPath={complianceFastPath}
          onInstallRenderAudition={installRenderAndAudition}
          onCancelInstall={stopFastPathInstall}
        />
        <SettingsDrawer
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          onSettingsChange={handleStudioSettingsChange}
          onForceRebuildNext={() => setForceRebuildNext(true)}
        />
        <OnboardingOverlay
          open={onboardingOpen}
          onClose={() => setOnboardingOpen(false)}
          onStartHello={() => void loadTemplate("podcast-denoise")}
        />
      </div>
    </AuditionContext.Provider>
  );
}
