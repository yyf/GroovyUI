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
  batchRenderWorkflow,
  importComfyWorkflow,
  ensureWorkflowModels,
  executeWorkflow,
  fetchCompliance,
  fetchAllNodeSchemas,
  listPacks,
  installPack,
  fetchTemplate,
  fetchWaveform,
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
import ModuleGroupNode from "./components/ModuleGroupNode";
import ModelBrowser from "./components/ModelBrowser";
import NodeHelper from "./components/NodeHelper";
import NodePalette, { defaultWidgetsForNode } from "./components/NodePalette";
import OnboardingOverlay, { isOnboardingComplete } from "./components/OnboardingOverlay";
import SidePanel from "./components/SidePanel";
import StudioTopBar from "./components/StudioTopBar";
import TransportBar from "./components/TransportBar";
import { AuditionContext } from "./context/AuditionContext";
import { useLiveIo } from "./hooks/useLiveIo";
import { useWorkflowHistory } from "./hooks/useWorkflowHistory";
import type { JobState, NodeRenderStatus, NodeSchema, Workflow } from "./types";
import type { WorkflowClipboard } from "./workflow";
import {
  connectNodes,
  addNodeToWorkflow,
  applyDroppedAudio,
  createGroup,
  downloadModule,
  downloadTemplateJson,
  downloadWorkflow,
  importModule,
  extractModule,
  groupForSelection,
  edgeIdsOnPathToNode,
  formatJobError,
  flowNodesSyncKey,
  listDistinctChainHops,
  mergeFlowNodes,
  previewCacheId,
  savedFilePath,
  duplicateSelection,
  extractSelection,
  pasteSelection,
  removeLinks,
  removeNodesFromWorkflow,
  resolveComparePair,
  resolveTargetNode,
  syncPositions,
  toggleGroupCollapsed,
  workflowToFlowEdges,
  workflowToFlowNodes,
} from "./workflow";

const nodeTypes: NodeTypes = { groovy: GroovyFlowNode, groovyGroup: ModuleGroupNode };
const DEFAULT_TEMPLATE = "podcast-denoise";

export default function App() {
  const { workflow, setWorkflow, resetHistory, undo, redo } = useWorkflowHistory();
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [activeTemplateId, setActiveTemplateId] = useState(DEFAULT_TEMPLATE);
  const [nodeSchemas, setNodeSchemas] = useState<Record<string, NodeSchema>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const comfyImportRef = useRef<HTMLInputElement>(null);
  const moduleImportRef = useRef<HTMLInputElement>(null);
  const clipboardRef = useRef<WorkflowClipboard | null>(null);
  const flowCenterRef = useRef(() => ({ x: 320, y: 200 }));
  const pendingSelectionRef = useRef<Set<string> | null>(null);
  const pasteCountRef = useRef(0);
  const [nodeStatus, setNodeStatus] = useState<Record<string, NodeRenderStatus>>({});
  const [lastJob, setLastJob] = useState<JobState | null>(null);
  const [status, setStatus] = useState("Loading template…");
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<number | undefined>();
  const [currentNode, setCurrentNode] = useState<string | undefined>();
  const [modelBrowserOpen, setModelBrowserOpen] = useState(false);
  const [modelPickTarget, setModelPickTarget] = useState<{ nodeId: string; widget: string } | null>(null);
  const [complianceOpen, setComplianceOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [complianceWarnings, setComplianceWarnings] = useState(0);
  const [focusMode, setFocusMode] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helperOpen, setHelperOpen] = useState(false);
  const [workflowBarOpen, setWorkflowBarOpen] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(() => !isOnboardingComplete());
  const [dropHint, setDropHint] = useState(false);
  const [transportWaveform, setTransportWaveform] = useState<number[]>([]);
  const [activeEdgeIds, setActiveEdgeIds] = useState<Set<string>>(new Set());

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
    () => (workflow ? workflowToFlowNodes(workflow, nodeStatus, lastJob?.outputs, nodeSchemas) : []),
    [workflow, nodeStatus, lastJob?.outputs, nodeSchemas],
  );
  const flowEdges = useMemo(
    () => (workflow ? workflowToFlowEdges(workflow, activeEdgeIds) : []),
    [workflow, activeEdgeIds],
  );
  const flowNodeSyncKey = useMemo(() => flowNodesSyncKey(flowNodes), [flowNodes]);
  const [nodes, setNodes, applyNodeChanges] = useNodesState<Node>([]);

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
      setStatus("Ready");
      setLoadError(null);
    },
    [resetHistory],
  );

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
      const target = renderAll
        ? resolveTargetNode(workflow, selectedNodeId)
        : (targetNodeId ?? resolveTargetNode(workflow, selectedNodeId));
      if (!target) {
        setStatus("No render target — add a Preview node or select one");
        return;
      }
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
        const modelIds = [
          ...new Set(workflow.nodes.map((n) => n.widgets.model).filter((m): m is string => typeof m === "string" && !!m)),
        ];
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
            if (
              out?.cache_id ||
              out?.stems_id ||
              out?.midi_id ||
              out?.authenticity_id ||
              out?.automation_id ||
              out?.type === "TEXT" ||
              out?.type === "STRING"
            ) {
              cached[nodeId] = "cached";
            }
          }
          setNodeStatus((prev) => ({ ...prev, ...cached }));
          const saved = targets
            .map((nodeId) => {
              const node = workflow.nodes.find((n) => n.id === nodeId);
              const path = savedFilePath(outputs[nodeId]);
              return node?.type === "SaveAudio" && path ? path : null;
            })
            .find(Boolean);
          setStatus(saved ? `Saved to ${saved}` : "Complete");
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

  const auditionNode = useCallback(
    (nodeId: string) => {
      if (!workflow) return;
      setNodes((current) => current.map((node) => ({ ...node, selected: node.id === nodeId })));
      const cacheId = lastJob?.outputs?.[nodeId]?.cache_id;
      if (!cacheId) return;
      setActiveEdgeIds(edgeIdsOnPathToNode(workflow, nodeId));
      setTimeout(() => {
        document.querySelector<HTMLAudioElement>(".transport__audio")?.play();
      }, 0);
    },
    [lastJob, workflow, setNodes],
  );

  const playSelectedNode = useCallback(() => {
    if (running || !workflow || !selectedNodeId) return;
    if (!lastJob?.outputs?.[selectedNodeId]?.cache_id) {
      setStatus("Render this node first");
      return;
    }
    setActiveEdgeIds(edgeIdsOnPathToNode(workflow, selectedNodeId));
    void document.querySelector<HTMLAudioElement>(".transport__audio")?.play();
  }, [running, workflow, selectedNodeId, lastJob?.outputs]);

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
      if (event.key === "f" || event.key === "\\") {
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
  }, [running, runRender, undo, redo, workflow, selectedNodeIds, setWorkflow]);

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

  const handleExportModule = useCallback(() => {
    if (!workflow || selectedNodeIds.length === 0) return;
    downloadModule(extractModule(workflow, selectedNodeIds));
  }, [workflow, selectedNodeIds]);

  const handleGroupSelection = useCallback(() => {
    if (!workflow || selectedNodeIds.length < 2) return;
    const title = window.prompt("Group title", "Module") ?? "Module";
    setWorkflow(createGroup(workflow, selectedNodeIds, title));
  }, [workflow, selectedNodeIds, setWorkflow]);

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

  const handleInstallPack = useCallback(async () => {
    try {
      const packs = await listPacks();
      const packId = window.prompt(
        `Install community pack:\n${packs.map((pack) => pack.id).join("\n")}`,
        packs[0]?.id ?? "",
      );
      if (!packId) return;
      await installPack(packId);
      setStatus(`Installed pack: ${packId}`);
    } catch (err) {
      setStatus(`Pack install failed: ${String(err)}`);
    }
  }, []);

  const handleComfyImport = useCallback(
    async (file: File) => {
      try {
        const text = await file.text();
        const comfyJson = JSON.parse(text) as Record<string, unknown>;
        const result = await importComfyWorkflow(comfyJson, file.name.replace(/\.json$/i, ""));
        resetHistory(result.workflow);
        setLastJob(null);
        setNodeStatus({});
        const unmapped = (result.import_meta.unmapped_node_types as string[] | undefined) ?? [];
        setStatus(
          unmapped.length
            ? `Imported — ${unmapped.length} unmapped node type(s): ${unmapped.join(", ")}`
            : "Imported from ComfyUI — ready to render",
        );
        setLoadError(null);
      } catch (err) {
        setStatus(`ComfyUI import failed: ${String(err)}`);
      }
    },
    [resetHistory],
  );

  const handleModuleImport = useCallback(
    async (file: File) => {
      if (!workflow) return;
      try {
        const text = await file.text();
        const module = JSON.parse(text) as import("./types").WorkflowModule;
        setWorkflow(importModule(workflow, module));
        setStatus(`Imported module: ${module.metadata.title}`);
      } catch (err) {
        setStatus(`Module import failed: ${String(err)}`);
      }
    },
    [workflow, setWorkflow],
  );

  const handleBatchRender = useCallback(async () => {
    if (!workflow) return;
    const inputDir = window.prompt("Input folder (relative to project)", "assets/samples") ?? "";
    if (!inputDir) return;
    setStatus("Batch render running…");
    setRunning(true);
    try {
      const loadNode = workflow.nodes.find((node) => node.type === "LoadAudio");
      const previewNode = workflow.nodes.find((node) => node.type === "Preview");
      const result = await batchRenderWorkflow(workflow, {
        input_dir: inputDir,
        file_glob: "*.wav,*.flac",
        load_node_id: loadNode?.id,
        target_nodes: previewNode ? [previewNode.id] : undefined,
      });
      setStatus(`Batch done — ${result.completed}/${result.total} completed`);
    } catch (err) {
      setStatus(`Batch failed: ${String(err)}`);
    } finally {
      setRunning(false);
    }
  }, [workflow]);

  const selectedNode = workflow?.nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedOutput = selectedNodeId && lastJob?.outputs ? lastJob.outputs[selectedNodeId] : undefined;
  const selectedPreviewId = previewCacheId(selectedOutput);
  const selectedNodePreview = selectedPreviewId ? previewUrl(selectedPreviewId) : null;
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
      : !selectedNodePreview
        ? "Render to preview this node"
        : "No render yet";

  useEffect(() => {
    document.querySelector<HTMLAudioElement>(".transport__audio")?.pause();
  }, [selectedNodeId]);

  useEffect(() => {
    if (!selectedNodePreview) {
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
  }, [selectedNodePreview]);

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
            selectedCount: selectedNodeIds.length,
            groupCollapsed: activeGroup ? (activeGroup.collapsed ?? false) : null,
            paletteOpen,
            helperOpen,
            running,
            onOpenIoSettings: () => setSettingsOpen(true),
            onSaveWorkflow: () => downloadWorkflow(workflow),
            onSaveAsTemplate: () => void handleSaveAsTemplate(),
            onGroup: handleGroupSelection,
            onExportModule: handleExportModule,
            onToggleGroupCollapse: handleToggleGroupCollapse,
            onInstallPack: () => void handleInstallPack(),
            onImportComfy: () => comfyImportRef.current?.click(),
            onImportModule: () => moduleImportRef.current?.click(),
            onBatchRender: () => void handleBatchRender(),
            onTogglePalette: () => setPaletteOpen((prev) => !prev),
            onToggleHelper: () => setHelperOpen((prev) => !prev),
          }}
        />
        <input
          ref={comfyImportRef}
          type="file"
          accept=".json,application/json"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleComfyImport(file);
            event.target.value = "";
          }}
        />
        <input
          ref={moduleImportRef}
          type="file"
          accept=".json,application/json"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleModuleImport(file);
            event.target.value = "";
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
                    setWorkflow((prev) => (prev ? addNodeToWorkflow(prev, nodeType, widgets, center) : prev));
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
                nodes={nodes}
                edges={flowEdges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeDragStop={onNodeDragStop}
                onNodeClick={() => openInspector()}
                onNodeDoubleClick={(_, node) => auditionNode(node.id)}
                fitView
                deleteKeyCode={["Backspace", "Delete"]}
                panOnDrag={[1, 2]}
                panActivationKeyCode="Space"
                selectionOnDrag
                selectionKeyCode={null}
                multiSelectionKeyCode={["Shift", "Meta", "Control"]}
                proOptions={{ hideAttribution: true }}
              >
                <FlowViewportBridge canvasSelector=".canvas" onCenterReady={registerFlowCenter} />
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
                output={selectedOutput}
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
              />
            </SidePanel>
          ) : null}
        </div>
        <TransportBar
          previewUrl={selectedNodePreview}
          waveformPeaks={transportWaveform}
          emptyHint={transportEmptyHint}
          running={running}
          statusMessage={status}
          currentNode={currentNode}
          progress={progress}
          onRender={() => void runRender()}
          onRenderAll={() => void runRender(undefined, true)}
          onPlay={playSelectedNode}
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
