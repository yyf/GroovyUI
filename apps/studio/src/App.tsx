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
  ensureWorkflowModels,
  executeWorkflow,
  fetchCompliance,
  fetchAllNodeSchemas,
  fetchWorkflowValidation,
  fetchTemplate,
  fetchModelCard,
  fetchWaveform,
  fetchMidiRoll,
  listTemplates,
  saveUserTemplate,
  previewUrl,
  uploadProjectAudio,
  type TemplateListItem,
} from "./api";
import ComplianceDrawer from "./components/ComplianceDrawer";
import FlowViewportBridge from "./components/FlowViewportBridge";
import SettingsDrawer from "./components/SettingsDrawer";
import GroovyFlowNode from "./components/GroovyFlowNode";
import type { GroovyNodeData } from "./components/GroovyFlowNode";
import ModuleGroupNode from "./components/ModuleGroupNode";
import ModelBrowser from "./components/ModelBrowser";
import NodeHelper from "./components/NodeHelper";
import NodePalette, { defaultWidgetsForNode } from "./components/NodePalette";
import OnboardingOverlay, { isOnboardingComplete } from "./components/OnboardingOverlay";
import SidePanel from "./components/SidePanel";
import StudioTopBar from "./components/StudioTopBar";
import TransportBar from "./components/TransportBar";
import RenderActivityBar from "./components/RenderActivityBar";
import { AuditionContext } from "./context/AuditionContext";
import { augmentNodeWithExample, getMinimalPatch, type MinimalPatch } from "./nodeMinimalPatches";
import { useLiveIo } from "./hooks/useLiveIo";
import { useWorkflowHistory } from "./hooks/useWorkflowHistory";
import type { JobState, NodeRenderStatus, NodeSchema, Workflow } from "./types";
import type { WorkflowClipboard } from "./workflow";
import {
  cachedStatusFromOutputs,
  connectNodes,
  addNodeToWorkflow,
  applyDroppedAudio,
  downloadTemplateJson,
  downloadWorkflow,
  groupForSelection,
  edgeIdsOnPathToNode,
  formatJobError,
  flowNodesSyncKey,
  listDistinctChainHops,
  mergeFlowNodes,
  nodeIssuesFromValidation,
  previewCacheId,
  previewMidiId,
  savedFilePath,
  duplicateSelection,
  extractSelection,
  pasteSelection,
  removeLinks,
  removeNodesFromWorkflow,
  resolveComparePair,
  resolveNodeListenId,
  resolveNodeListenOutput,
  resolveTargetNode,
  syncPositions,
  toggleGroupCollapsed,
  workflowToFlowEdges,
  workflowToFlowNodes,
} from "./workflow";

const nodeTypes: NodeTypes = { groovy: GroovyFlowNode, groovyGroup: ModuleGroupNode };
const DEFAULT_TEMPLATE = "transcribe-and-regenerate";

export default function App() {
  const { workflow, setWorkflow, resetHistory, undo, redo } = useWorkflowHistory();
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [activeTemplateId, setActiveTemplateId] = useState(DEFAULT_TEMPLATE);
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
  const [status, setStatus] = useState("Loading template…");
  const [running, setRunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [progress, setProgress] = useState<number | undefined>();
  const [currentNode, setCurrentNode] = useState<string | undefined>();
  const [renderMessage, setRenderMessage] = useState<string | undefined>();
  const [renderStartedAt, setRenderStartedAt] = useState<number | undefined>();
  const [lastProgressAt, setLastProgressAt] = useState<number | undefined>();
  const activeExecutionRef = useRef<{ cancel: () => Promise<void> } | null>(null);
  const [modelBrowserOpen, setModelBrowserOpen] = useState(false);
  const [modelPickTarget, setModelPickTarget] = useState<{ nodeId: string; widget: string } | null>(null);
  const [complianceOpen, setComplianceOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [complianceWarnings, setComplianceWarnings] = useState(0);
  const [focusMode, setFocusMode] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helperOpen, setHelperOpen] = useState(false);
  const [workflowBarOpen, setWorkflowBarOpen] = useState(true);
  const [onboardingOpen, setOnboardingOpen] = useState(() => !isOnboardingComplete());
  const [dropHint, setDropHint] = useState(false);
  const [transportWaveform, setTransportWaveform] = useState<number[]>([]);
  const [transportMidiRoll, setTransportMidiRoll] = useState<{
    duration: number;
    notes: { start: number; end: number; pitch: number; velocity: number; drum?: boolean }[];
    minPitch: number;
    maxPitch: number;
  } | null>(null);
  const [activeEdgeIds, setActiveEdgeIds] = useState<Set<string>>(new Set());
  const [auditionNonce, setAuditionNonce] = useState(0);

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
      clipboardRef.current = null;
      pasteCountRef.current = 0;
      const data = await fetchTemplate(templateId);
      resetHistory(data);
      setActiveTemplateId(templateId);
      setViewportFitKey((key) => key + 1);
      setStatus("Ready");
      setLoadError(null);
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
    loadTemplate(DEFAULT_TEMPLATE).catch((err) => {
      setLoadError(String(err));
      setStatus("Template load failed");
    });
  }, [loadTemplate]);

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
    async (targetNodeId?: string, renderAll = false) => {
      if (!workflow) return;
      const previewNodes = workflow.nodes.filter((n) => n.type === "Preview").map((n) => n.id);
      const previewTarget =
        previewNodes[0] ??
        workflow.nodes[workflow.nodes.length - 1]?.id;
      const singleTarget = targetNodeId ?? resolveTargetNode(workflow, selectedNodeId);
      const targets = renderAll
        ? previewNodes.length > 0
          ? previewNodes
          : previewTarget
            ? [previewTarget]
            : []
        : singleTarget
          ? [singleTarget]
          : [];
      if (!targets.length) {
        setStatus("No render target — add a Preview node or select one");
        return;
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
        const modelIds = [
          ...new Set(workflow.nodes.map((n) => n.widgets.model).filter((m): m is string => typeof m === "string" && !!m)),
        ];
        if (modelIds.length > 0) {
          setStatus("Installing models…");
          await ensureWorkflowModels(workflow);
        }

        setStatus("Rendering…");
        let lastRunningNode: string | undefined;
        const execution = await executeWorkflow(workflow, targets, (update) => {
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
        });
        activeExecutionRef.current = execution;
        const job = await execution.promise;
        activeExecutionRef.current = null;

        setLastJob(job);
        if (job.status === "completed") {
          setFailedNodeId(null);
          const outputs = job.outputs ?? {};
          setNodeStatus((prev) => ({ ...prev, ...cachedStatusFromOutputs(workflow, outputs) }));
          const saved = targets
            .map((nodeId) => {
              const node = workflow.nodes.find((n) => n.id === nodeId);
              const path = savedFilePath(outputs[nodeId]);
              return node?.type === "SaveAudio" && path ? path : null;
            })
            .find(Boolean);
          setStatus(saved ? `Saved to ${saved}` : "Complete");
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
      } catch (err) {
        setStatus(`Error: ${formatJobError(String(err))}`);
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
    [workflow, selectedNodeId],
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
        setModelBrowserOpen(true);
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
      if (event.shiftKey && event.key.toLowerCase() === "r") {
        event.preventDefault();
        if (!running) void runRender(undefined, true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [running, runRender, cancelRender, undo, redo, workflow, nodes, selectedNodeIds, selectedNodeId, nodeSchemas, augmentMinimalPatchForNode]);

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
        updateWidget(nodeId, widget, modelId);
        void fetchModelCard(modelId)
          .then((card) => {
            for (const param of card.inference_params ?? []) {
              updateWidget(nodeId, param.name, param.default ?? "");
            }
          })
          .catch(() => undefined);
        setModelPickTarget(null);
      }
      setModelBrowserOpen(false);
    },
    [modelPickTarget, updateWidget],
  );

  const handleAudioDrop = useCallback(
    async (files: FileList | null) => {
      if (!files?.length || !workflow) return;
      const file = files[0];
      if (!file.type.startsWith("audio/") && !file.name.match(/\.(wav|flac|mp3|ogg)$/i)) {
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
      downloadTemplateJson(saved.template, `${saved.template_id}.groovy.json`);
      const nextTemplates = await listTemplates();
      setTemplates(nextTemplates);
      setActiveTemplateId(saved.template_id);
      setStatus(`Template saved: ${saved.template_id}`);
    } catch (err) {
      setStatus(`Template save failed: ${String(err)}`);
    }
  }, [workflow]);

  const currentNodeLabel = useMemo(() => {
    if (!workflow || !currentNode) return undefined;
    const node = workflow.nodes.find((n) => n.id === currentNode);
    return node?.type ?? currentNode;
  }, [workflow, currentNode]);

  const selectedNode = workflow?.nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedOutput = selectedNodeId && lastJob?.outputs ? lastJob.outputs[selectedNodeId] : undefined;
  const selectedListenOutput =
    workflow && selectedNodeId
      ? resolveNodeListenOutput(workflow, selectedNodeId, lastJob?.outputs)
      : undefined;
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
      return;
    }
    const match = selectedNodePreview.match(/\/api\/cache\/([^/?]+)\/preview/);
    if (!match) {
      setTransportWaveform([]);
      return;
    }
    fetchWaveform(match[1], 512)
      .then((data) => setTransportWaveform(data.peaks))
      .catch(() => setTransportWaveform([]));
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
      setStatus("Workflow applied — ready to render");
      setLoadError(null);
    },
    [resetHistory],
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
          onApplyWorkflow={applyWorkflow}
          complianceWarnings={complianceWarnings}
          onModelBrowser={() => setModelBrowserOpen(true)}
          onCompliance={() => setComplianceOpen(true)}
          workflowBarOpen={workflowBarOpen}
          onToggleWorkflowBar={() => setWorkflowBarOpen((prev) => !prev)}
          settings={{
            groupCollapsed: activeGroup ? (activeGroup.collapsed ?? false) : null,
            paletteOpen,
            helperOpen,
            onOpenIoSettings: () => setSettingsOpen(true),
            onSaveWorkflow: () => downloadWorkflow(workflow),
            onSaveAsTemplate: () => void handleSaveAsTemplate(),
            onToggleGroupCollapse: handleToggleGroupCollapse,
            onTogglePalette: () => setPaletteOpen((prev) => !prev),
            onToggleHelper: () => setHelperOpen((prev) => !prev),
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
                <Background gap={20} color="#1a1a1a" size={1} />
                <Controls className="flow-controls" showInteractive={false} />
              </ReactFlow>
            </ReactFlowProvider>
          </div>
          {!focusMode ? (
            <SidePanel side="right" label="Inspector" open={helperOpen} onToggle={() => setHelperOpen((prev) => !prev)}>
              <NodeHelper
                node={selectedNode}
                workflow={workflow}
                output={selectedListenOutput ?? selectedOutput}
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
                  setModelBrowserOpen(true);
                }}
                onAudition={() => {
                  if (selectedNodeId) auditionNode(selectedNodeId);
                }}
                onCompareAudition={(nodeId) => auditionNode(nodeId)}
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
          midiRoll={transportMidiRoll}
          emptyHint={transportEmptyHint}
          running={running}
          statusMessage={status}
          onRender={() => void runRender()}
          onRenderAll={() => void runRender(undefined, true)}
          onPlay={playSelectedNode}
          auditionNonce={auditionNonce}
        />
        <ModelBrowser
          open={modelBrowserOpen}
          onClose={() => {
            setModelBrowserOpen(false);
            setModelPickTarget(null);
          }}
          onSelectModel={handleModelSelect}
          onApplyWorkflow={applyWorkflow}
        />
        <ComplianceDrawer
          open={complianceOpen}
          workflow={workflow}
          outputs={lastJob?.outputs}
          targetNodeId={selectedNodeId}
          onClose={() => setComplianceOpen(false)}
        />
        <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
        <OnboardingOverlay
          open={onboardingOpen}
          onClose={() => setOnboardingOpen(false)}
          onStartHello={() => void loadTemplate("hello-groovy")}
        />
      </div>
    </AuditionContext.Provider>
  );
}
