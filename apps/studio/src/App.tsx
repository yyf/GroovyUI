import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
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
  API,
  executeWorkflow,
  fetchCompliance,
  fetchAllNodeSchemas,
  fetchAudioFileMeta,
  fetchCacheMetrics,
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
import { CANVAS_MAX_ZOOM, CANVAS_MIN_ZOOM, FIT_ALL_OPTIONS } from "./canvasViewport";
import ComplianceDrawer from "./components/ComplianceDrawer";
import FlowViewportBridge from "./components/FlowViewportBridge";
import FitAllControl from "./components/FitAllControl";
import GridControl from "./components/GridControl";
import CanvasZoomGrid, { CANVAS_GRID_GAP, snapFlowPosition } from "./components/CanvasZoomGrid";
import SampleAccuracyBadge from "./components/SampleAccuracyBadge";
import CanvasNodeFinder from "./components/CanvasNodeFinder";
import CanvasNodePicker from "./components/CanvasNodePicker";
import { sanitizePlanWorkflowModels } from "./planModelSanitize";
import FpsMeter from "./components/FpsMeter";
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
import CanvasErrorBoundary from "./components/CanvasErrorBoundary";
import {
  apiLedTone,
  canvasLedTone,
  renderLedTone,
  type StatusLedSpec,
} from "./components/StatusLeds";
import RenderActivityBar from "./components/RenderActivityBar";
import { AuditionContext } from "./context/AuditionContext";
import { PreviewVideoSizeContext } from "./context/PreviewVideoSizeContext";
import { TrajectoryEditContext } from "./context/TrajectoryEditContext";
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
import { isAiNodeType } from "./nodeKinds";
import { nodeStatusOnProgress, slowAiDownloadLabel } from "./renderActivity";
import type { JobState, ModelBrowserLaunch, NodeRenderStatus, NodeSchema, Workflow } from "./types";
import type { WorkflowClipboard } from "./workflow";
import { nextActiveEdgeIds, resolveEdgePlaybackTarget } from "./edgePlayback";
import { attachTransportVideoSync } from "./transportVideoSync";
import {
  cachedStatusFromOutputs,
  connectNodes,
  addNodeToWorkflow,
  applyDroppedAudio,
  groupForSelection,
  formatJobError,
  layoutWorkflowNodes,
  ensureNoOverlappingNodes,
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
  preferredVideoPreviewNodeId,
  disconnectPort,
  removeLinks,
  removeNodesFromWorkflow,
  resolveComparePair,
  resolveNodeListenId,
  resolveNodeListenOutput,
  resolveNodeInspectorOutput,
  resolveRenderAllTargets,
  resolveTargetNode,
  withAuthenticityRenderTargets,
  findUpstreamLoadAudio,
  lockPreviewVideoSize,
  previewVideoAspect,
  rescalePointsWidgetJson,
  setLinkColor,
  syncPositions,
  toggleGroupCollapsed,
  workflowToFlowEdges,
  workflowToFlowNodes,
  normalizeLoadedWorkflow,
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
  /** LoadAudio node id → probed channel count (drives per-channel canvas outlets). */
  const [loadAudioChannels, setLoadAudioChannels] = useState<Record<string, number>>({});
  /** LoadAudio node id → probed duration / sample rate for TrajectoryAuthor lock. */
  const [loadAudioTiming, setLoadAudioTiming] = useState<
    Record<string, { durationSec: number; sampleRate: number }>
  >({});
  /** Preview / SaveAudio node id → layout label from cache metrics (post-render). */
  const [channelLayouts, setChannelLayouts] = useState<Record<string, string>>({});
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
  const [renderTick, setRenderTick] = useState(() => Date.now());
  const activeExecutionRef = useRef<{ cancel: () => Promise<void> } | null>(null);
  const fastPathStopRef = useRef(false);
  const [modelBrowserOpen, setModelBrowserOpen] = useState(false);
  const [modelBrowserLaunch, setModelBrowserLaunch] = useState<ModelBrowserLaunch | null>(null);
  const [modelPickTarget, setModelPickTarget] = useState<{ nodeId: string; widget: string } | null>(null);
  const [complianceOpen, setComplianceOpen] = useState(false);
  const [complianceWarnings, setComplianceWarnings] = useState(0);
  const [complianceFastPath, setComplianceFastPath] = useState(false);
  const [inferenceStubActive, setInferenceStubActive] = useState(false);
  const [forceRebuildNext, setForceRebuildNext] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  /** Lightweight React Flow dots grid — off by default; toggle with `g` (or `'`). */
  const [canvasGrid, setCanvasGrid] = useState(() => {
    try {
      return localStorage.getItem("groovy-canvas-grid") === "1";
    } catch {
      return false;
    }
  });
  /** Template picker: false = ISMIR demo set; true (⌘⇧D) = full featured list + nodes. */
  const [studioDevMode, setStudioDevMode] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helperOpen, setHelperOpen] = useState(false);
  const [inspectorAbout, setInspectorAbout] = useState(false);
  const [inspectorApiStatus, setInspectorApiStatus] = useState(false);
  const [inspectorStudioSettings, setInspectorStudioSettings] = useState(false);
  const [inspectorTemplateLicenses, setInspectorTemplateLicenses] = useState(false);
  const [inspectorWide, setInspectorWide] = useState(false);
  const [workflowBarOpen, setWorkflowBarOpen] = useState(true);
  const [generateOpenNonce, setGenerateOpenNonce] = useState(0);
  const [onboardingOpen, setOnboardingOpen] = useState(() => !isOnboardingComplete());
  const [dropHint, setDropHint] = useState(false);
  const [nodePicker, setNodePicker] = useState<{ x: number; y: number } | null>(null);
  const [nodeFinderOpen, setNodeFinderOpen] = useState(false);
  const [foundNodeId, setFoundNodeId] = useState<string | null>(null);
  const [transportWaveform, setTransportWaveform] = useState<number[]>([]);
  const [transportWaveformDuration, setTransportWaveformDuration] = useState(0);
  const [transportMidiRoll, setTransportMidiRoll] = useState<{
    duration: number;
    notes: { start: number; end: number; pitch: number; velocity: number; drum?: boolean }[];
    minPitch: number;
    maxPitch: number;
  } | null>(null);
  const [activeEdgeIds, setActiveEdgeIds] = useState<Set<string>>(new Set());
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  /** Set synchronously before auditionNonce so play events highlight the right path. */
  const auditionTargetRef = useRef<string | null>(null);
  const [auditionNonce, setAuditionNonce] = useState(0);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [canvasCrashed, setCanvasCrashed] = useState(false);
  const [canvasCrashMessage, setCanvasCrashMessage] = useState<string | null>(null);

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
    auditionTargetRef.current = null;
    setActiveEdgeIds(
      nextActiveEdgeIds({
        event: "playback_failed",
        workflow: workflowRef.current,
        targetNodeId: null,
      }),
    );
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

  const downloadHint = useMemo(() => {
    const node = workflow?.nodes.find((item) => item.id === currentNode);
    const schema = node ? nodeSchemas[node.type] : undefined;
    return slowAiDownloadLabel({
      running,
      nodeType: node?.type,
      category: schema?.category,
      staleMs: lastProgressAt ? renderTick - lastProgressAt : 0,
    });
  }, [workflow, currentNode, nodeSchemas, running, lastProgressAt, renderTick]);

  const flowNodes = useMemo(() => {
    if (!workflow) return [];
    const nodes = workflowToFlowNodes(
      workflow,
      nodeStatus,
      lastJob?.outputs,
      nodeSchemas,
      nodeIssues,
      loadAudioChannels,
      channelLayouts,
    );
    if (!currentNode) return nodes;
    return nodes.map((node) => {
      if (node.id !== currentNode || node.type !== "groovy") return node;
      return {
        ...node,
        data: { ...node.data, activityLabel: downloadHint },
      };
    });
  }, [
    workflow,
    nodeStatus,
    lastJob?.outputs,
    nodeSchemas,
    nodeIssues,
    loadAudioChannels,
    channelLayouts,
    currentNode,
    downloadHint,
  ]);

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setRenderTick(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [running]);
  const flowEdges = useMemo(
    () => (workflow ? workflowToFlowEdges(workflow, activeEdgeIds) : []),
    [workflow, activeEdgeIds],
  );
  const displayEdges = useMemo(
    () => flowEdges.map((edge) => ({ ...edge, selected: edge.id === selectedEdgeId })),
    [flowEdges, selectedEdgeId],
  );
  const flowNodeSyncKey = useMemo(() => flowNodesSyncKey(flowNodes), [flowNodes]);
  const [nodes, setNodes, applyNodeChanges] = useNodesState<Node>([]);

  const sampleAccuracyNote = useMemo(() => {
    if (!workflow?.nodes?.length) return null;
    const nondet = workflow.nodes.filter((node) => {
      const schema = nodeSchemas[node.type];
      if (schema?.deterministic === false) return true;
      return isAiNodeType(node.type, schema?.category);
    });
    if (nondet.length === 0) return null;
    const generative = new Set([
      "GenerateAudio",
      "MIDIToAudio",
      "TTS",
      "SingFromMIDI",
      "TimbreTransfer",
      "Video2Audio",
    ]);
    const hasGenerative = nondet.some((node) => generative.has(node.type));
    if (hasGenerative) {
      return "Sample-accurate offline render · Play = cached PCM · Generative hops choose length/timbre (seed/hardware may vary)";
    }
    return "Sample-accurate offline render · Play = cached PCM · AI hops may vary by seed/hardware (not bit-identical)";
  }, [workflow, nodeSchemas]);

  const displayNodes = useMemo(() => {
    let merged = mergeFlowNodes(nodes, flowNodes);
    const pending = pendingSelectionRef.current;
    if (pending) {
      merged = merged.map((node) => ({ ...node, selected: pending.has(node.id) }));
    }
    if (foundNodeId) {
      merged = merged.map((node) =>
        node.id === foundNodeId
          ? {
              ...node,
              selected: true,
              data: { ...(node.data as object), found: true },
            }
          : node,
      );
    }
    return merged;
  }, [nodes, flowNodes, flowNodeSyncKey, foundNodeId]);

  const loadTemplate = useCallback(
    async (templateId: string) => {
      setStatus("Loading template…");
      setLastJob(null);
      setNodeStatus({});
      setComplianceFastPath(false);
      clipboardRef.current = null;
      pasteCountRef.current = 0;
      // Always DAG-layout templates — authored positions often look fine with
      // underestimated footprints but TrajectoryMonitor / Note chrome overlaps.
      const data = layoutWorkflowNodes(await fetchTemplate(templateId));
      resetHistory(normalizeLoadedWorkflow(data));
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

  const loadAudioPathKey = useMemo(() => {
    if (!workflow) return "";
    return workflow.nodes
      .filter((node) => node.type === "LoadAudio")
      .map((node) => {
        const path = typeof node.widgets.path === "string" ? node.widgets.path.trim() : "";
        return `${node.id}=${path}`;
      })
      .sort()
      .join("|");
  }, [workflow]);

  const trajectoryAudioLockKey = useMemo(() => {
    if (!workflow) return "";
    return workflow.nodes
      .filter((node) => node.type === "TrajectoryAuthor")
      .map((node) => {
        const load = findUpstreamLoadAudio(workflow, node.id);
        const timing = load ? loadAudioTiming[load.id] : undefined;
        return `${node.id}:${load?.id ?? ""}:${timing?.durationSec ?? 0}:${timing?.sampleRate ?? 0}`;
      })
      .sort()
      .join("|");
  }, [workflow, loadAudioTiming]);

  useEffect(() => {
    if (!workflow) {
      setLoadAudioChannels({});
      setLoadAudioTiming({});
      return;
    }
    const loadNodes = workflow.nodes.filter((node) => node.type === "LoadAudio");
    if (loadNodes.length === 0) {
      setLoadAudioChannels({});
      setLoadAudioTiming({});
      return;
    }

    let cancelled = false;
    const targets = loadNodes.map((node) => ({
      id: node.id,
      path: typeof node.widgets.path === "string" ? node.widgets.path.trim() : "",
    }));

    Promise.all(
      targets.map(async ({ id, path }) => {
        if (!path) {
          return [id, { channels: 1, durationSec: 0, sampleRate: 48000 }] as const;
        }
        const { meta } = await fetchAudioFileMeta(path);
        const channels = Number(meta?.channels);
        const durationSec = Number(meta?.duration_seconds);
        const sampleRate = Number(meta?.sample_rate);
        return [
          id,
          {
            channels: Number.isFinite(channels) && channels > 0 ? channels : 1,
            durationSec: Number.isFinite(durationSec) && durationSec > 0 ? durationSec : 0,
            sampleRate: Number.isFinite(sampleRate) && sampleRate > 0 ? sampleRate : 48000,
          },
        ] as const;
      }),
    )
      .then((entries) => {
        if (cancelled) return;
        const nextChannels: Record<string, number> = {};
        const nextTiming: Record<string, { durationSec: number; sampleRate: number }> = {};
        for (const [id, probe] of entries) {
          nextChannels[id] = probe.channels;
          if (probe.durationSec > 0) {
            nextTiming[id] = { durationSec: probe.durationSec, sampleRate: probe.sampleRate };
          }
        }
        setLoadAudioChannels(nextChannels);
        setLoadAudioTiming(nextTiming);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadAudioChannels({});
          setLoadAudioTiming({});
        }
      });

    return () => {
      cancelled = true;
    };
  }, [workflow, loadAudioPathKey]);

  /** Lock TrajectoryAuthor duration_sec / sample_rate to wired LoadAudio length. */
  useEffect(() => {
    if (!workflow || Object.keys(loadAudioTiming).length === 0) return;
    setWorkflow((prev) => {
      if (!prev) return prev;
      let changed = false;
      const nodes = prev.nodes.map((node) => {
        if (node.type !== "TrajectoryAuthor") return node;
        const hasAudioWire = prev.links.some(
          (link) => link.to[0] === node.id && (link.type === "AUDIO" || link.type === "STEMS"),
        );
        if (!hasAudioWire) return node;
        const load = findUpstreamLoadAudio(prev, node.id);
        if (!load) return node;
        const timing = loadAudioTiming[load.id];
        if (!timing || timing.durationSec <= 0) return node;
        const curDur = Number(node.widgets.duration_sec ?? 0);
        const curSr = Number(node.widgets.sample_rate ?? 0);
        const durClose = Math.abs(curDur - timing.durationSec) < 1e-3;
        const srClose = Math.abs(curSr - timing.sampleRate) < 0.5;
        if (durClose && srClose) return node;
        changed = true;
        const nextWidgets: Record<string, unknown> = {
          ...node.widgets,
          duration_sec: timing.durationSec,
          sample_rate: timing.sampleRate,
        };
        const scaled = rescalePointsWidgetJson(node.widgets.points, timing.durationSec);
        if (scaled) nextWidgets.points = scaled;
        return { ...node, widgets: nextWidgets };
      });
      return changed ? { ...prev, nodes } : prev;
    });
  }, [loadAudioTiming, trajectoryAudioLockKey, setWorkflow]);

  useEffect(() => {
    if (!workflow || !lastJob?.outputs) {
      setChannelLayouts({});
      return;
    }
    const ioNodes = workflow.nodes.filter((node) => {
      const listen = resolveNodeListenOutput(workflow, node.id, lastJob.outputs);
      return Boolean(
        previewCacheId(listen) ?? previewCacheId(lastJob.outputs?.[node.id]),
      );
    });
    if (ioNodes.length === 0) {
      setChannelLayouts({});
      return;
    }

    let cancelled = false;
    Promise.all(
      ioNodes.map(async (node) => {
        const listen = resolveNodeListenOutput(workflow, node.id, lastJob.outputs);
        const cacheId = previewCacheId(listen) ?? previewCacheId(lastJob.outputs?.[node.id]);
        if (!cacheId) return null;
        try {
          const metrics = await fetchCacheMetrics(cacheId);
          const layout =
            typeof metrics.channel_layout === "string" && metrics.channel_layout.trim()
              ? metrics.channel_layout.trim()
              : metrics.channels > 0
                ? `${metrics.channels} ch`
                : null;
          return layout ? ([node.id, layout] as const) : null;
        } catch {
          return null;
        }
      }),
    ).then((entries) => {
      if (cancelled) return;
      const next: Record<string, string> = {};
      for (const entry of entries) {
        if (entry) next[entry[0]] = entry[1];
      }
      setChannelLayouts(next);
    });

    return () => {
      cancelled = true;
    };
  }, [workflow, lastJob?.outputs, lastJob?.status]);

  useEffect(() => {
    fetchAllNodeSchemas()
      .then((schemas) => {
        setNodeSchemas(schemas);
        setApiOnline(true);
      })
      .catch(() => {
        setNodeSchemas({});
        setApiOnline(false);
      });
    listTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]));
    fetchStudioSettings()
      .then((settings) => setInferenceStubActive(settings.inference_stub_active))
      .catch(() => setInferenceStubActive(false));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const ping = () => {
      fetch(`${API}/api/health`)
        .then(async (res) => {
          if (cancelled) return;
          const online = res.ok;
          setApiOnline(online);
          if (online) {
            try {
              const schemas = await fetchAllNodeSchemas();
              if (!cancelled) setNodeSchemas(schemas);
            } catch {
              /* keep prior schemas */
            }
          }
        })
        .catch(() => {
          if (!cancelled) setApiOnline(false);
        });
    };
    ping();
    const timer = window.setInterval(ping, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
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
      const selectedIds = changes
        .filter(
          (change): change is EdgeChange & { type: "select"; id: string; selected: boolean } =>
            change.type === "select" && change.selected,
        )
        .map((change) => change.id);
      if (removedIds.length > 0) {
        setSelectedEdgeId((prev) => (prev && removedIds.includes(prev) ? null : prev));
        setWorkflow((prev) => {
          if (!prev) return prev;
          return removeLinks(prev, new Set(removedIds));
        });
        setLastJob(null);
        return;
      }
      if (selectedIds.length > 0) {
        // Ignore edge select events when nodes are already selected (marquee overlap).
        setNodes((current) => {
          if (current.some((node) => node.selected)) {
            return current;
          }
          setSelectedEdgeId(selectedIds[0] ?? null);
          return current.map((node) => ({ ...node, selected: false }));
        });
      }
    },
    [setWorkflow, setNodes],
  );

  const selectedNodeIds = useMemo(
    () => nodes.filter((node) => node.selected).map((node) => node.id),
    [nodes],
  );
  const selectedNodeId = selectedNodeIds[0] ?? null;

  useEffect(() => {
    if (!foundNodeId) return;
    const timer = window.setTimeout(() => setFoundNodeId(null), 2200);
    return () => window.clearTimeout(timer);
  }, [foundNodeId]);

  const openInspector = useCallback(() => {
    if (!focusMode) setHelperOpen(true);
  }, [focusMode]);

  const selectionKey = `${selectedEdgeId ?? ""}|${selectedNodeIds.join(",")}`;
  const aboutOpenedAtSelectionRef = useRef(selectionKey);

  const openAbout = useCallback(() => {
    if (focusMode) return;
    aboutOpenedAtSelectionRef.current = selectionKey;
    setInspectorApiStatus(false);
    setInspectorStudioSettings(false);
    setInspectorTemplateLicenses(false);
    setInspectorAbout(true);
    setHelperOpen(true);
  }, [focusMode, selectionKey]);

  const openApiStatus = useCallback(() => {
    if (focusMode) return;
    aboutOpenedAtSelectionRef.current = selectionKey;
    setInspectorAbout(false);
    setInspectorStudioSettings(false);
    setInspectorTemplateLicenses(false);
    setInspectorApiStatus(true);
    setHelperOpen(true);
  }, [focusMode, selectionKey]);

  const openStudioSettings = useCallback(() => {
    if (focusMode) return;
    aboutOpenedAtSelectionRef.current = selectionKey;
    setInspectorAbout(false);
    setInspectorApiStatus(false);
    setInspectorTemplateLicenses(false);
    setInspectorStudioSettings(true);
    setHelperOpen(true);
  }, [focusMode, selectionKey]);

  const openTemplateLicenses = useCallback(() => {
    if (focusMode) return;
    aboutOpenedAtSelectionRef.current = selectionKey;
    setInspectorAbout(false);
    setInspectorApiStatus(false);
    setInspectorStudioSettings(false);
    setInspectorTemplateLicenses(true);
    setHelperOpen(true);
  }, [focusMode, selectionKey]);

  // Leave About / API status / Studio settings / Template licenses only when canvas selection changes after opening.
  useEffect(() => {
    if (
      !inspectorAbout &&
      !inspectorApiStatus &&
      !inspectorStudioSettings &&
      !inspectorTemplateLicenses
    ) {
      return;
    }
    if (selectionKey === aboutOpenedAtSelectionRef.current) return;
    setInspectorAbout(false);
    setInspectorApiStatus(false);
    setInspectorStudioSettings(false);
    setInspectorTemplateLicenses(false);
  }, [
    selectionKey,
    inspectorAbout,
    inspectorApiStatus,
    inspectorStudioSettings,
    inspectorTemplateLicenses,
  ]);

  const registerFlowCenter = useCallback((getter: () => { x: number; y: number }) => {
    flowCenterRef.current = getter;
  }, []);

  useEffect(() => {
    // Rubber-band / node select clears wire selection. Skip this tick when the
    // user just clicked an edge (nodes are deselected in the same React cycle).
    if (selectedNodeIds.length > 0 && !selectedEdgeId) {
      openInspector();
    }
  }, [selectedNodeIds, selectedEdgeId, openInspector]);

  useEffect(() => {
    if (selectedEdgeId) openInspector();
  }, [selectedEdgeId, openInspector]);

  const updateLinkColor = useCallback(
    (linkId: string, color: string | null) => {
      setWorkflow((prev) => (prev ? setLinkColor(prev, linkId, color) : prev));
    },
    [setWorkflow],
  );

  const updateWidget = useCallback(
    (nodeId: string, name: string, value: unknown) => {
      const displayOnly =
        name === "preview_width" || name === "preview_height";
      setWorkflow((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          nodes: prev.nodes.map((node) => {
            if (node.id !== nodeId) return node;
            if (
              node.type === "PreviewVideo" &&
              (name === "preview_width" || name === "preview_height")
            ) {
              const aspect =
                previewVideoAspect(lastJob?.outputs?.[nodeId]) ?? 16 / 9;
              const locked = lockPreviewVideoSize(
                name,
                Number(value),
                aspect,
              );
              return { ...node, widgets: { ...node.widgets, ...locked } };
            }
            return { ...node, widgets: { ...node.widgets, [name]: value } };
          }),
        };
      });
      if (!displayOnly) {
        setNodeStatus((prev) => ({ ...prev, [nodeId]: "stale" }));
      }
    },
    [lastJob?.outputs, setWorkflow],
  );

  const patchPreviewVideoSize = useCallback(
    (nodeId: string, width: number, height: number) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          nodes: prev.nodes.map((node) =>
            node.id === nodeId
              ? {
                  ...node,
                  widgets: {
                    ...node.widgets,
                    preview_width: width,
                    preview_height: height,
                  },
                }
              : node,
          ),
        };
      });
    },
    [setWorkflow],
  );

  const previewVideoSizeApi = useMemo(
    () => ({ patchSize: patchPreviewVideoSize }),
    [patchPreviewVideoSize],
  );

  const patchTrajectoryAuthor = useCallback(
    (authorNodeId: string, patch: Record<string, number | string>) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          nodes: prev.nodes.map((node) =>
            node.id === authorNodeId
              ? { ...node, widgets: { ...node.widgets, ...patch } }
              : node,
          ),
        };
      });
      setNodeStatus((prev) => {
        const next = { ...prev, [authorNodeId]: "stale" as const };
        // Mark TRAJECTORY consumers stale so canvas shows dirty until re-render.
        return next;
      });
    },
    [setWorkflow],
  );

  const trajectoryEditApi = useMemo(
    () => ({ patchAuthor: patchTrajectoryAuthor }),
    [patchTrajectoryAuthor],
  );

  const disconnectPortCb = useCallback(
    (nodeId: string, direction: "in" | "out", slot: number) => {
      setWorkflow((prev) => (prev ? disconnectPort(prev, nodeId, direction, slot) : prev));
      setLastJob(null);
    },
    [setWorkflow],
  );

  const deleteSelectedLink = useCallback(
    (linkId: string) => {
      setWorkflow((prev) => (prev ? removeLinks(prev, new Set([linkId])) : prev));
      setSelectedEdgeId((prev) => (prev === linkId ? null : prev));
      setLastJob(null);
    },
    [setWorkflow],
  );

  const onNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      const position = canvasGrid ? snapFlowPosition(node.position) : node.position;
      const snapped = position.x === node.position.x && position.y === node.position.y
        ? node
        : { ...node, position };
      if (snapped !== node) {
        setNodes((current) =>
          current.map((entry) => (entry.id === snapped.id ? { ...entry, position } : entry)),
        );
      }
      setWorkflow((prev) => {
        if (!prev) return prev;
        return syncPositions(prev, [snapped]);
      });
    },
    [setWorkflow, setNodes, canvasGrid],
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
      const targets = withAuthenticityRenderTargets(
        workflow,
        renderAll ? resolveRenderAllTargets(workflow) : singleTarget ? [singleTarget] : [],
      );
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
              const previousRunning = lastRunningNode;
              lastRunningNode = update.current_node;
              setCurrentNode(update.current_node);
              setNodeStatus((prev) =>
                nodeStatusOnProgress(prev, update.current_node!, previousRunning),
              );
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
          // Lock PreviewVideo canvas size to source frame aspect once VIDEO dims are known.
          setWorkflow((prev) => {
            if (!prev) return prev;
            let changed = false;
            const nodes = prev.nodes.map((node) => {
              if (node.type !== "PreviewVideo") return node;
              const aspect = previewVideoAspect(outputs[node.id]);
              if (!aspect) return node;
              const baseW = Number(node.widgets.preview_width) || 240;
              const locked = lockPreviewVideoSize("preview_width", baseW, aspect);
              if (
                Number(node.widgets.preview_width) === locked.preview_width &&
                Number(node.widgets.preview_height) === locked.preview_height
              ) {
                return node;
              }
              changed = true;
              return { ...node, widgets: { ...node.widgets, ...locked } };
            });
            return changed ? { ...prev, nodes } : prev;
          });
          setNodeStatus((prev) => ({ ...prev, ...cachedStatusFromOutputs(workflow, outputs) }));
          let auditionNodeId: string | null = null;
          const videoPreviewId = preferredVideoPreviewNodeId(workflow, outputs);
          if (autoAudition) {
            recordActivationMilestone("render_completed");
            // Prefer muxed VIDEO preview selection when present (A/V in Node Helper).
            auditionNodeId = preferredAuditionNodeId(workflow, outputs);
            const selectId = videoPreviewId ?? auditionNodeId;
            if (selectId) {
              setNodes((current) =>
                current.map((node) => ({
                  ...node,
                  selected: node.id === selectId,
                })),
              );
            }
            // Prefer PreviewVideo selection (on-node video); transport auditions its muxed PCM.
            const playId =
              videoPreviewId && resolveNodeListenId(workflow, videoPreviewId, outputs)
                ? videoPreviewId
                : auditionNodeId;
            if (playId) {
              // Edges animate only after the audio element fires `play` (not eagerly).
              auditionTargetRef.current = playId;
              recordActivationMilestone("playback_requested", {
                preview_node_id: playId,
              });
              setAuditionNonce((nonce) => nonce + 1);
            } else if (videoPreviewId) {
              auditionTargetRef.current = null;
              recordActivationMilestone("playback_requested", {
                preview_node_id: videoPreviewId,
              });
            } else {
              finishActivationSession("failed", {
                reason: "preview_not_listenable",
              });
            }
          } else {
            recordActivationMilestone("render_completed");
          }
          const savedOutput = targets
            .map((nodeId) => {
              const node = workflow.nodes.find((n) => n.id === nodeId);
              return node?.type === "SaveAudio" || node?.type === "SaveVideo"
                ? outputs[nodeId]
                : undefined;
            })
            .find(Boolean);
          const saved = savedFilePath(savedOutput);
          const provenance = savedProvenancePath(savedOutput);
          const savedVideo = targets.some(
            (nodeId) => workflow.nodes.find((n) => n.id === nodeId)?.type === "SaveVideo",
          );
          setStatus(
            saved && provenance
              ? `Saved audio + provenance: ${saved}`
              : saved
                ? savedVideo
                  ? `Saved video to ${saved}`
                  : `Saved to ${saved}`
                : autoAudition && !auditionNodeId && !videoPreviewId
                  ? "Render complete — Preview produced no listenable output"
                  : videoPreviewId
                    ? "Render complete — play muxed video in Node Helper → Outputs"
                    : "Render complete — click Play to audition",
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
            setNodes((current) =>
              current.map((node) => ({ ...node, selected: node.id === lastRunningNode })),
            );
            setSelectedEdgeId(null);
            openInspector();
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
    [workflow, selectedNodeId, openModelBrowser, setNodes, forceRebuildNext, openInspector],
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
      // Do not set activeEdgeIds here — wait for real `play` (autoplay can fail).
      auditionTargetRef.current = nodeId;
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
    auditionTargetRef.current = selectedNodeId;
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
        auditionTargetRef.current = null;
        setActiveEdgeIds(
          nextActiveEdgeIds({
            event: "preview_cleared",
            workflow: null,
            targetNodeId: null,
          }),
        );
        setStatus(`Wired example I/O for ${patch.workflow.metadata.title}`);
        return next;
      });
    },
    [setWorkflow],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      const editing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        if (nodeFinderOpen) return;
        setNodePicker(null);
        setNodeFinderOpen(true);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === "c") {
        if (editing) return;
        event.preventDefault();
        setComplianceOpen(true);
        return;
      }

      if (editing) return;

      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === "k") {
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
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "c") {
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
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "d") {
        event.preventDefault();
        const next = !studioDevMode;
        setStudioDevMode(next);
        setStatus(next ? "Dev mode — all templates + nodes" : "Standard mode — ISMIR templates + nodes");
        return;
      }
      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === "d") {
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
      if ((event.key === "f" || event.key === "\\") && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        setFocusMode((prev) => !prev);
        return;
      }
      // Grid: plain `g` or Quote key (`'` / `"`) — Cmd+G stays Generate.
      const gridKey =
        (!event.metaKey &&
          !event.ctrlKey &&
          !event.altKey &&
          (event.key.toLowerCase() === "g" ||
            event.key === "'" ||
            event.key === '"' ||
            event.code === "Quote")) ||
        false;
      if (gridKey) {
        event.preventDefault();
        setCanvasGrid((prev) => {
          const next = !prev;
          try {
            localStorage.setItem("groovy-canvas-grid", next ? "1" : "0");
          } catch {
            /* ignore quota / private mode */
          }
          queueMicrotask(() => setStatus(next ? "Canvas grid + snap on (g)" : "Canvas grid off (g)"));
          return next;
        });
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
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [running, runRender, cancelRender, undo, redo, workflow, nodes, selectedNodeIds, selectedNodeId, nodeSchemas, augmentMinimalPatchForNode, openModelBrowser, setNodes, nodeFinderOpen, studioDevMode]);

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
        setViewportFitKey((key) => key + 1);
        setStatus(`Dropped ${nodeType} with ${modelId}`);
      });
      setModelBrowserOpen(false);
    },
    [workflow, setWorkflow],
  );

  const handleAudioDrop = useCallback(
    async (files: FileList | null) => {
      if (!files?.length || !workflow) return;
      const audioMatch = (entry: File) =>
        entry.type.startsWith("audio/") || /\.(wav|flac|mp3|ogg|mp4|m4a)$/i.test(entry.name);
      const file = [...files].find(audioMatch);
      if (!file) {
        setStatus("Drop an audio file (WAV, FLAC, MP3, OGG)");
        return;
      }
      try {
        setStatus("Uploading audio…");
        const path = await uploadProjectAudio(file);
        const stem = file.name.replace(/\.[^.]+$/, "");
        const sidecar = [...files].find((entry) => entry.name === `${stem}.provenance.json`);
        if (sidecar && path.startsWith("assets/uploads/")) {
          await uploadProjectAudio(sidecar);
        }
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
  const selectedLink = workflow?.links.find((link) => link.id === selectedEdgeId) ?? null;
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
    : selectedNode?.type === "SaveAudio" || selectedNode?.type === "SaveVideo"
      ? selectedSavedPath
        ? `Saved to ${selectedSavedPath}`
        : selectedNode.type === "SaveVideo"
          ? "Render to write video under workspace/exports"
          : "Render to write audio file"
      : selectedMidiId || selectedNodePreview
        ? ""
        : selectedOutput?.type === "VIDEO" && selectedOutput.path
          ? "Render upstream audio — Space / Play drives video + waveform"
          : previewKind === "midi"
            ? "Render to preview MIDI"
            : "Render to preview this node";

  useEffect(() => {
    document.querySelector<HTMLAudioElement>(".transport__audio")?.pause();
    // Keep auditionTarget when it matches the new selection (audition just chose this node).
    // Drop it when the user selects someone else so play highlights the right path.
    if (auditionTargetRef.current && auditionTargetRef.current !== selectedNodeId) {
      auditionTargetRef.current = null;
    }
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
    if (!selectedNodePreview) {
      auditionTargetRef.current = null;
      setActiveEdgeIds(
        nextActiveEdgeIds({
          event: "preview_cleared",
          workflow: null,
          targetNodeId: null,
        }),
      );
    }
  }, [selectedNodePreview]);

  useEffect(() => {
    const onAudioEvent = (event: Event) => {
      const mediaEvent = event.type as "play" | "pause" | "ended";
      // Do not clear auditionTarget on pause — ensureBlobLoaded() pauses while
      // swapping the blob URL, and we still need the target for the following play.
      if (mediaEvent === "ended") {
        auditionTargetRef.current = null;
      }
      const targetNodeId = resolveEdgePlaybackTarget(
        auditionTargetRef.current,
        selectedNodeId,
      );
      setActiveEdgeIds(
        nextActiveEdgeIds({
          event: mediaEvent,
          workflow: workflowRef.current,
          targetNodeId,
        }),
      );
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
  }, [selectedNodeId, selectedNodePreview]);

  // PreviewVideo picture locks to transport Space / Play / seek (muted; PCM is master).
  useEffect(() => {
    return attachTransportVideoSync();
  }, [selectedNodeId, selectedNodePreview, lastJob?.id]);

  const selectedTemplateId = activeTemplateId;

  const applyWorkflow = useCallback(
    (next: Workflow) => {
      resetHistory(normalizeLoadedWorkflow(ensureNoOverlappingNodes(next)));
      setLastJob(null);
      setNodeStatus({});
      setComplianceFastPath(false);
      setViewportFitKey((key) => key + 1);
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
      const sanitized = sanitizePlanWorkflowModels(next, nodeSchemas);
      applyWorkflow(layoutWorkflowNodes(sanitized));
      setComplianceFastPath(true);
      setComplianceOpen(true);
      setStatus("Review licenses before installing or rendering");
    },
    [applyWorkflow, nodeSchemas],
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
          // Render only — Play remains explicit (patch-bay audition of cached PCM).
          return runRender(previewTarget, false, false);
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
    (opts: {
      nodeType?: string;
      commercialOnly?: boolean;
      query?: string;
      mode?: "search" | "recommend";
    }) => {
      setComplianceOpen(false);
      openModelBrowser({
        // Legacy recommend → Search (recommender is merged into Search).
        mode: opts.mode === "recommend" ? "search" : (opts.mode ?? "search"),
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

  const inspectFailedNode = useCallback(
    (nodeId: string | null) => {
      if (!nodeId) return;
      setNodes((current) => current.map((node) => ({ ...node, selected: node.id === nodeId })));
      setSelectedEdgeId(null);
      openInspector();
    },
    [setNodes, openInspector],
  );

  const canvasIssueCount = Object.keys(nodeIssues).length;
  const statusLeds = useMemo<StatusLedSpec[]>(() => {
    const apiTone = apiLedTone(apiOnline);
    const rndTone = renderLedTone({ running, statusMessage: status });
    const cvsTone = canvasLedTone({ issueCount: canvasIssueCount, crashed: canvasCrashed });
    const failedNode = workflow?.nodes.find((node) => node.id === failedNodeId);
    const issueLines = Object.entries(nodeIssues)
      .map(([id, message]) => {
        const type = workflow?.nodes.find((node) => node.id === id)?.type ?? id;
        return `• ${type} (${id})\n  ${message}`;
      })
      .join("\n\n");
    const rndReport = [
      status || "Render idle",
      failedNode ? `Node: ${failedNode.type} (${failedNode.id})` : "",
      lastJob?.error && lastJob.error !== status ? lastJob.error : "",
    ]
      .filter(Boolean)
      .join("\n\n");
    const cvsReport = [
      canvasCrashed ? `Canvas crash: ${canvasCrashMessage || "unknown error"}` : "",
      issueLines ? `Node issues:\n${issueLines}` : canvasCrashed ? "" : "No node issues.",
    ]
      .filter(Boolean)
      .join("\n\n");
    return [
      {
        id: "api",
        label: "API",
        tone: apiTone,
        title:
          apiOnline === null
            ? "API status unknown"
            : apiOnline
              ? "API online"
              : "API offline — start groovy-server",
        onInspect: openApiStatus,
      },
      {
        id: "rnd",
        label: "RND",
        tone: rndTone,
        title: running ? "Render in progress" : status || "Render idle",
        report: rndTone === "fault" || rndTone === "warn" ? rndReport : undefined,
        onInspect:
          rndTone === "fault" || rndTone === "warn"
            ? () => inspectFailedNode(failedNodeId)
            : undefined,
      },
      {
        id: "cvs",
        label: "CVS",
        tone: cvsTone,
        title: canvasCrashed
          ? "Canvas crashed — reset to recover"
          : canvasIssueCount > 0
            ? `${canvasIssueCount} node issue${canvasIssueCount === 1 ? "" : "s"}`
            : "Canvas OK",
        report: cvsTone === "fault" || cvsTone === "warn" ? cvsReport : undefined,
        onInspect:
          cvsTone === "fault" || cvsTone === "warn"
            ? () => inspectFailedNode(failedNodeId ?? Object.keys(nodeIssues)[0] ?? null)
            : undefined,
      },
    ];
  }, [
    apiOnline,
    running,
    status,
    canvasIssueCount,
    canvasCrashed,
    canvasCrashMessage,
    failedNodeId,
    lastJob?.error,
    nodeIssues,
    workflow,
    inspectFailedNode,
    openApiStatus,
  ]);

  const resetCanvasAfterCrash = useCallback(() => {
    setCanvasCrashed(false);
    setCanvasCrashMessage(null);
    setViewportFitKey((key) => key + 1);
    setStatus("Canvas reset");
  }, []);

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
      <PreviewVideoSizeContext.Provider value={previewVideoSizeApi}>
      <TrajectoryEditContext.Provider value={trajectoryEditApi}>
      <div className={`app ${focusMode ? "app--focus" : ""}`}>
        <StudioTopBar
          templates={templates}
          selectedTemplateId={selectedTemplateId}
          onSelectTemplate={(id) => void loadTemplate(id)}
          onDeleteUserTemplate={(id) => void handleDeleteUserTemplate(id)}
          studioDevMode={studioDevMode}
          onApplyWorkflow={applyGeneratedWorkflow}
          onGenerateTaskStart={beginGenerateTask}
          generateOpenNonce={generateOpenNonce}
          complianceWarnings={complianceWarnings}
          inferenceStubActive={inferenceStubActive}
          onModelBrowser={() => openModelBrowser()}
          onCompliance={() => setComplianceOpen(true)}
          onShareWorkflow={() => void handleShareWorkflow()}
          onAbout={openAbout}
          onApiStatus={openApiStatus}
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
            onOpenStudioSettings: openStudioSettings,
            onOpenTemplateLicenses: openTemplateLicenses,
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
                studioDevMode={studioDevMode}
                catalog={Object.values(nodeSchemas).map((schema) => ({
                  type: schema.type,
                  category: schema.category ?? "",
                }))}
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
                    setViewportFitKey((key) => key + 1);
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
            <FpsMeter />
            {sampleAccuracyNote && !dropHint ? (
              <SampleAccuracyBadge note={sampleAccuracyNote} />
            ) : null}
            <CanvasErrorBoundary
              crashed={canvasCrashed}
              onError={(error) => {
                setCanvasCrashed(true);
                setCanvasCrashMessage(error.message || "Canvas crashed");
                setStatus("Failed: canvas crash");
              }}
              onReset={resetCanvasAfterCrash}
            >
              <ReactFlowProvider>
                <ReactFlow
                  nodes={displayNodes}
                  edges={displayEdges}
                  nodeTypes={nodeTypes}
                  snapToGrid={canvasGrid}
                  snapGrid={[CANVAS_GRID_GAP, CANVAS_GRID_GAP]}
                  nodeOrigin={[0, 0]}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onConnect={onConnect}
                  onNodeDragStop={onNodeDragStop}
                  onSelectionChange={({ nodes: selectedFlowNodes, edges: selectedFlowEdges }) => {
                    // Marquee often includes wires between two nodes. Prefer node multi-select
                    // (A/B compare) over edge selection whenever any node is in the box.
                    if (selectedFlowNodes.length > 0) {
                      setSelectedEdgeId(null);
                      return;
                    }
                    const edgeId = selectedFlowEdges[0]?.id ?? null;
                    if (edgeId) {
                      setSelectedEdgeId(edgeId);
                    }
                  }}
                  onNodeClick={() => {
                    setSelectedEdgeId(null);
                    openInspector();
                  }}
                  onEdgeClick={(event, edge) => {
                    event.stopPropagation();
                    setSelectedEdgeId(edge.id);
                    setNodes((current) => current.map((node) => ({ ...node, selected: false })));
                    openInspector();
                  }}
                  onPaneClick={() => {
                    setSelectedEdgeId(null);
                    setNodePicker(null);
                  }}
                  onPaneContextMenu={(event) => {
                    event.preventDefault();
                    setNodePicker({ x: event.clientX, y: event.clientY });
                  }}
                  onNodeContextMenu={(event) => {
                    event.preventDefault();
                    setNodePicker({ x: event.clientX, y: event.clientY });
                  }}
                  onEdgeContextMenu={(event) => {
                    event.preventDefault();
                    setNodePicker({ x: event.clientX, y: event.clientY });
                  }}
                  onNodeDoubleClick={(_, node) => auditionNode(node.id)}
                  deleteKeyCode={["Backspace", "Delete"]}
                  panOnDrag={[1]}
                  panActivationKeyCode="Space"
                  selectionOnDrag
                  selectionKeyCode={null}
                  multiSelectionKeyCode={["Shift", "Meta", "Control"]}
                  edgesFocusable
                  elevateEdgesOnSelect
                  defaultEdgeOptions={{ interactionWidth: 36, selectable: false, focusable: true }}
                  minZoom={CANVAS_MIN_ZOOM}
                  maxZoom={CANVAS_MAX_ZOOM}
                  fitViewOptions={FIT_ALL_OPTIONS}
                  proOptions={{ hideAttribution: true }}
                >
                  {canvasGrid ? <CanvasZoomGrid /> : null}
                  <FlowViewportBridge
                    canvasSelector=".canvas"
                    onCenterReady={registerFlowCenter}
                    nodeSyncKey={flowNodeSyncKey}
                    fitViewKey={viewportFitKey}
                  />
                  <Controls
                    className="flow-controls"
                    showInteractive={false}
                    showFitView={false}
                    fitViewOptions={FIT_ALL_OPTIONS}
                  >
                    <FitAllControl />
                    <GridControl
                      enabled={canvasGrid}
                      onToggle={() => {
                        setCanvasGrid((prev) => {
                          const next = !prev;
                          try {
                            localStorage.setItem("groovy-canvas-grid", next ? "1" : "0");
                          } catch {
                            /* ignore */
                          }
                          queueMicrotask(() =>
                            setStatus(next ? "Canvas grid + snap on (g)" : "Canvas grid off (g)"),
                          );
                          return next;
                        });
                      }}
                    />
                  </Controls>
                </ReactFlow>
                {nodePicker ? (
                  <CanvasNodePicker
                    clientX={nodePicker.x}
                    clientY={nodePicker.y}
                    studioDevMode={studioDevMode}
                    onClose={() => setNodePicker(null)}
                    onPick={(nodeType, flowPos) => {
                      setNodePicker(null);
                      void defaultWidgetsForNode(nodeType).then((widgets) => {
                        setWorkflow((prev) => {
                          if (!prev) return prev;
                          const { workflow: next, nodeId } = addNodeToWorkflow(
                            prev,
                            nodeType,
                            widgets,
                            flowPos,
                          );
                          pendingSelectionRef.current = new Set([nodeId]);
                          return next;
                        });
                        setLastJob(null);
                        setViewportFitKey((key) => key + 1);
                      });
                    }}
                  />
                ) : null}
                {nodeFinderOpen ? (
                  <CanvasNodeFinder
                    hits={nodes.map((node) => ({
                      id: node.id,
                      name: String((node.data as { label?: string } | undefined)?.label ?? node.id),
                    }))}
                    onClose={() => setNodeFinderOpen(false)}
                    onPick={(nodeId) => {
                      pendingSelectionRef.current = new Set([nodeId]);
                      setNodeFinderOpen(false);
                      setFoundNodeId(nodeId);
                      setNodes((current) =>
                        current.map((node) => ({ ...node, selected: node.id === nodeId })),
                      );
                      setSelectedEdgeId(null);
                      openInspector();
                    }}
                  />
                ) : null}
              </ReactFlowProvider>
            </CanvasErrorBoundary>
          </div>
          {!focusMode ? (
            <SidePanel
              side="right"
              label="Inspector"
              open={helperOpen}
              wide={inspectorWide}
              onToggle={() => {
                setHelperOpen((prev) => {
                  if (prev) setInspectorWide(false);
                  return !prev;
                });
              }}
            >
              <NodeHelper
                node={selectedNode}
                selectedLink={selectedLink}
                onLinkColorChange={updateLinkColor}
                selectedNodes={selectedNodes}
                selectionOutputs={lastJob?.outputs ?? null}
                loadAudioChannels={loadAudioChannels}
                channelLayouts={channelLayouts}
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
                onDisconnectPort={disconnectPortCb}
                onDeleteLink={deleteSelectedLink}
                onSubgraphActiveChange={setInspectorWide}
                onBrowseModel={(nodeId, widget) => {
                  setModelPickTarget({ nodeId, widget });
                  openModelBrowser();
                }}
                onAudition={() => {
                  if (selectedNodeId) auditionNode(selectedNodeId);
                }}
                onCompareAudition={(nodeId) => auditionNode(nodeId)}
                onOpenCompliance={() => setComplianceOpen(true)}
                showAbout={inspectorAbout}
                showApiStatus={inspectorApiStatus}
                showStudioSettings={inspectorStudioSettings}
                showTemplateLicenses={inspectorTemplateLicenses}
                onSettingsChange={handleStudioSettingsChange}
                onForceRebuildNext={() => setForceRebuildNext(true)}
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
          message={downloadHint ?? renderMessage}
          progress={progress}
          startedAt={renderStartedAt}
          lastProgressAt={lastProgressAt}
          downloadingModel={Boolean(downloadHint)}
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
          statusLeds={statusLeds}
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
          onOpenCompliance={() => setComplianceOpen(true)}
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
          studioDevMode={studioDevMode}
          onInstallRenderAudition={installRenderAndAudition}
          onCancelInstall={stopFastPathInstall}
        />
        <OnboardingOverlay
          open={onboardingOpen}
          onClose={() => setOnboardingOpen(false)}
          onStartHello={() => void loadTemplate("podcast-denoise")}
        />
      </div>
      </TrajectoryEditContext.Provider>
      </PreviewVideoSizeContext.Provider>
    </AuditionContext.Provider>
  );
}
