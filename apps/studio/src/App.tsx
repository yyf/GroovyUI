import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
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
  fetchHealth,
  generateTemplateFromWorkflow,
  listPacks,
  installPack,
  fetchTemplate,
  fetchWaveform,
  listTemplates,
  previewUrl,
  uploadProjectAudio,
} from "./api";
import ComplianceDrawer from "./components/ComplianceDrawer";
import SettingsDrawer from "./components/SettingsDrawer";
import GroovyFlowNode from "./components/GroovyFlowNode";
import ModuleGroupNode from "./components/ModuleGroupNode";
import ModelBrowser from "./components/ModelBrowser";
import NodeHelper from "./components/NodeHelper";
import NodePalette, { defaultWidgetsForNode } from "./components/NodePalette";
import OnboardingOverlay, { isOnboardingComplete } from "./components/OnboardingOverlay";
import TransportBar from "./components/TransportBar";
import { AuditionContext } from "./context/AuditionContext";
import { useLiveIo } from "./hooks/useLiveIo";
import { useWorkflowHistory } from "./hooks/useWorkflowHistory";
import type { JobState, NodeRenderStatus, Workflow } from "./types";
import type { WorkflowClipboard } from "./workflow";
import {
  addLink,
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
  const [templates, setTemplates] = useState<Array<{ id: string; title: string }>>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const comfyImportRef = useRef<HTMLInputElement>(null);
  const moduleImportRef = useRef<HTMLInputElement>(null);
  const clipboardRef = useRef<WorkflowClipboard | null>(null);
  const pendingSelectionRef = useRef<Set<string> | null>(null);
  const pasteCountRef = useRef(0);
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [complianceWarnings, setComplianceWarnings] = useState(0);
  const [focusMode, setFocusMode] = useState(false);
  const [nodePreviewUrl, setNodePreviewUrl] = useState<string | null>(null);
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
    () => (workflow ? workflowToFlowNodes(workflow, nodeStatus, lastJob?.outputs) : []),
    [workflow, nodeStatus, lastJob?.outputs],
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
      setPreview(null);
      setLastJob(null);
      setNodeStatus({});
      clipboardRef.current = null;
      pasteCountRef.current = 0;
      const data = await fetchTemplate(templateId);
      resetHistory(data);
      setStatus("Ready");
      setLoadError(null);
    },
    [resetHistory],
  );

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
        setPreview(null);
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
      setPreview(null);
    },
    [setWorkflow],
  );

  const selectedNodeIds = useMemo(
    () => nodes.filter((node) => node.selected).map((node) => node.id),
    [nodes],
  );
  const selectedNodeId = selectedNodeIds[0] ?? null;

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
        return addLink(prev, connection.source, connection.target);
      });
      setLastJob(null);
      setPreview(null);
    },
    [setWorkflow],
  );

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
              out?.type === "TEXT"
            ) {
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

  const auditionNode = useCallback(
    (nodeId: string) => {
      const cacheId = lastJob?.outputs?.[nodeId]?.cache_id;
      if (!cacheId) return;
      setNodePreviewUrl(previewUrl(cacheId));
      setTimeout(() => {
        document.querySelector<HTMLAudioElement>(".node-audition")?.play();
      }, 0);
    },
    [lastJob],
  );

  const playChain = useCallback(() => {
    const hasStale = workflow?.nodes.some((n) => nodeStatus[n.id] === "stale" || !nodeStatus[n.id]);
    if (preview && !running && !hasStale) {
      const audio = document.querySelector<HTMLAudioElement>(".transport__audio");
      if (workflow) {
        const target = resolveTargetNode(workflow, selectedNodeId);
        setActiveEdgeIds(edgeIdsOnPathToNode(workflow, target));
      }
      void audio?.play();
      return;
    }
    void runRender();
  }, [preview, running, runRender, workflow, nodeStatus, selectedNodeId]);

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
        setPreview(null);
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
        setPreview(null);
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
        setPreview(null);
        setStatus(`Duplicated ${newNodeIds.length} node(s)`);
        return;
      }
      if (event.key === "f" || event.key === "\\") {
        event.preventDefault();
        setFocusMode((prev) => !prev);
        return;
      }
      if (event.key === " " && !running) {
        event.preventDefault();
        playChain();
        return;
      }
      if (event.shiftKey && event.key.toLowerCase() === "r") {
        event.preventDefault();
        if (!running) void runRender(undefined, true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [running, runRender, undo, redo, playChain, workflow, selectedNodeIds, setWorkflow]);

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
        setPreview(null);
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
      const result = await generateTemplateFromWorkflow(workflow, title);
      downloadTemplateJson(result.template, `${result.template_id}.groovy.json`);
      setStatus(`Template generated: ${result.template_id}`);
    } catch (err) {
      setStatus(`Template generation failed: ${String(err)}`);
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
        setPreview(null);
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
  const chainPreview =
    preview ??
    (lastJob?.outputs && workflow
      ? (() => {
          const target = resolveTargetNode(workflow, selectedNodeId);
          const cacheId = lastJob.outputs?.[target]?.cache_id;
          return cacheId ? previewUrl(cacheId) : null;
        })()
      : null);

  useEffect(() => {
    if (!chainPreview) {
      setTransportWaveform([]);
      return;
    }
    const match = chainPreview.match(/\/api\/cache\/([^/?]+)\/preview/);
    if (!match) {
      setTransportWaveform([]);
      return;
    }
    fetchWaveform(match[1], 256)
      .then((data) => setTransportWaveform(data.peaks))
      .catch(() => setTransportWaveform([]));
  }, [chainPreview]);

  useEffect(() => {
    const onAudioEvent = (event: Event) => {
      if (!workflow) return;
      if (event.type === "play") {
        const nodeId = resolveTargetNode(workflow, selectedNodeId);
        setActiveEdgeIds(edgeIdsOnPathToNode(workflow, nodeId));
      } else {
        setActiveEdgeIds(new Set());
      }
      if (event.type === "ended") {
        setActiveEdgeIds(new Set());
      }
    };
    const transport = document.querySelector<HTMLAudioElement>(".transport__audio");
    const audition = document.querySelector<HTMLAudioElement>(".node-audition");
    for (const audio of [transport, audition]) {
      if (!audio) continue;
      audio.addEventListener("play", onAudioEvent);
      audio.addEventListener("pause", onAudioEvent);
      audio.addEventListener("ended", onAudioEvent);
    }
    return () => {
      for (const audio of [transport, audition]) {
        if (!audio) continue;
        audio.removeEventListener("play", onAudioEvent);
        audio.removeEventListener("pause", onAudioEvent);
        audio.removeEventListener("ended", onAudioEvent);
      }
    };
  }, [workflow, selectedNodeId, chainPreview]);

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
          <button type="button" onClick={() => setSettingsOpen(true)}>
            Settings
          </button>
          <button
            type="button"
            className={complianceWarnings > 0 ? "toolbar__warn" : ""}
            onClick={() => setComplianceOpen(true)}
          >
            Compliance{complianceWarnings > 0 ? ` (${complianceWarnings})` : ""}
          </button>
          <button type="button" onClick={() => downloadWorkflow(workflow)}>
            Save workflow
          </button>
          <button
            type="button"
            disabled={selectedNodeIds.length < 2}
            onClick={handleGroupSelection}
            title="Group selected nodes (Shift- or ⌘/Ctrl-click, or drag a box on the canvas)"
          >
            Group ({selectedNodeIds.length})
          </button>
          <button
            type="button"
            disabled={selectedNodeIds.length === 0}
            onClick={handleExportModule}
          >
            Export module
          </button>
          <button
            type="button"
            disabled={!activeGroup}
            onClick={handleToggleGroupCollapse}
            title="Collapse or expand the selected group"
          >
            {activeGroup?.collapsed ? "Expand group" : "Collapse group"}
          </button>
          <button type="button" onClick={() => void handleSaveAsTemplate()}>
            Save as template
          </button>
          <button type="button" onClick={() => void handleInstallPack()}>
            Install pack
          </button>
          <button type="button" onClick={() => comfyImportRef.current?.click()}>
            Import ComfyUI
          </button>
          <button type="button" onClick={() => moduleImportRef.current?.click()}>
            Import module
          </button>
          <button type="button" disabled={running} onClick={() => void handleBatchRender()}>
            Batch folder
          </button>
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
            <ReactFlow
              nodes={nodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeDragStop={onNodeDragStop}
              onNodeDoubleClick={(_, node) => auditionNode(node.id)}
              fitView
              deleteKeyCode={["Backspace", "Delete"]}
              panOnDrag={[1, 2]}
              panActivationKeyCode="Space"
              selectionOnDrag
              selectionKeyCode={null}
              multiSelectionKeyCode={["Shift", "Meta", "Control"]}
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
          ) : null}
        </div>
        {nodePreviewUrl ? <audio className="node-audition" src={nodePreviewUrl} hidden /> : null}
        <TransportBar
          workflow={workflow}
          previewUrl={chainPreview}
          waveformPeaks={transportWaveform}
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
          onApplyWorkflow={(next: Workflow) => {
            resetHistory(next);
            setLastJob(null);
            setPreview(null);
            setNodeStatus({});
            setStatus("Workflow applied — ready to render");
            setLoadError(null);
          }}
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
