import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelModelInstall,
  discoverModels,
  fetchInstallRecovery,
  fetchModelCard,
  InstallCancelledError,
  installModelWithProgress,
  planAgentRequest,
  recommendModels,
  removeModelInstall,
  searchModels,
  suggestWorkflows,
} from "../api";
import type {
  AgentPlan,
  AgentPlanAction,
  DiscoverModelResult,
  InstallRecovery,
  ModelCard,
  ModelInstallState,
  Workflow,
} from "../types";
import { PLAN_LLM_OPTIONS, type PlanLlmModelId } from "../planLlmOptions";
import {
  buildModelRequestIssueUrl,
  prefillFromDiscover,
  prefillFromUnknownModelId,
} from "../modelRequestIssue";

function openModelRequestIssue(
  prefill: Parameters<typeof buildModelRequestIssueUrl>[0],
): void {
  const repo = import.meta.env.VITE_GROOVY_GITHUB_REPO;
  const url = buildModelRequestIssueUrl(prefill, { repo });
  window.open(url, "_blank", "noopener,noreferrer");
}

type Props = {
  open: boolean;
  onClose: () => void;
  onSelectModel?: (modelId: string) => void;
  onDropModel?: (modelId: string, nodeType: string) => void;
  onApplyWorkflow?: (workflow: Workflow) => void;
  onOpenCompliance?: () => void;
  initialMode?: "search" | "recommend" | "workflow" | "discover" | "plan";
  /** When browsing from a node's MODEL_REF widget, filter to compatible models. */
  filterNodeType?: string | null;
  /** Deep-link filters when opened from Compliance / Comfy import. */
  launch?: import("../types").ModelBrowserLaunch | null;
};

const TASK_FILTERS = [
  { value: "", label: "All tasks" },
  { value: "denoise", label: "Denoise" },
  { value: "stem-separation", label: "Stem separation" },
  { value: "speech-to-text", label: "Speech-to-text" },
  { value: "text-to-speech", label: "Text-to-speech" },
  { value: "voice-conversion", label: "Voice conversion" },
  { value: "audio-to-midi", label: "Audio to MIDI" },
  { value: "music-generation", label: "Music generation" },
  { value: "video-to-audio", label: "Video to audio" },
  { value: "singing-synthesis", label: "Singing synthesis" },
  { value: "deepfake-detection", label: "Deepfake detection" },
  { value: "audio-compare", label: "A/B compare" },
];

type BrowserMode = "search" | "workflow" | "discover" | "plan";

function normalizeBrowserMode(
  mode: string | null | undefined,
): BrowserMode {
  if (mode === "workflow" || mode === "discover" || mode === "plan") return mode;
  // Legacy "recommend" launches land on Search (recommender is merged into Search).
  return "search";
}

function isDraftModel(model: ModelCard): boolean {
  return model.status === "draft" || model.trust === "draft" || model.install_status === "draft";
}

function filterDiscoverResults(
  results: DiscoverModelResult[],
  commercialOnly: boolean,
  nodeType: string | null | undefined,
): DiscoverModelResult[] {
  return results.filter((entry) => {
    if (commercialOnly && entry.license.commercial_ok === false) return false;
    if (nodeType && !entry.suggested_compatible_nodes.includes(nodeType)) return false;
    return true;
  });
}

function formatDiscoverUpdated(value?: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString();
}

function filterModelsForNode(models: ModelCard[], nodeType: string | null | undefined): ModelCard[] {
  if (!nodeType) return models;
  return models.filter((model) => model.compatible_nodes.includes(nodeType));
}

function installStatusLabel(status: string, progress?: number): string {
  if (status === "downloading") {
    return progress != null ? `Downloading ${Math.round(progress * 100)}%` : "Downloading…";
  }
  if (status === "verifying") return "Verifying…";
  if (status === "ready") return "ready";
  if (status === "failed") return "failed";
  return status.replace(/_/g, " ");
}

function licenseBadge(license: ModelCard["license"] | undefined): { label: string; className: string } {
  if (!license) {
    return { label: "Unknown", className: "pill pill--neutral" };
  }
  if (license.commercial_ok) {
    return { label: "Commercial OK", className: "pill pill--ready" };
  }
  if (license.spdx.includes("NC")) {
    return { label: `${license.spdx} NC`, className: "pill pill--warning" };
  }
  return { label: license.spdx, className: "pill pill--warning" };
}

function licenseDetailLines(license: ModelCard["license"] | undefined): string[] {
  if (!license) return [];
  const lines: string[] = [];
  if (license.code_spdx && license.code_spdx !== license.spdx) {
    lines.push(`Code: ${license.code_spdx}`);
    lines.push(`Weights: ${license.spdx}`);
  } else {
    lines.push(license.spdx);
  }
  if (license.notes?.trim()) {
    lines.push(license.notes.trim());
  }
  return lines;
}

function modelIsReady(model: ModelCard): boolean {
  if (model.install_status !== "ready") return false;
  if (model.dev_stub) return true;
  return model.inference_ready !== false;
}

function modelNeedsReinstall(model: ModelCard): boolean {
  return model.install_status === "ready" && !model.dev_stub && model.inference_ready === false;
}

function modelCardStatus(model: ModelCard, live?: ModelInstallState): string {
  const status = live?.status ?? model.install_status;
  if (status === "ready" && modelNeedsReinstall(model)) {
    return "needs setup";
  }
  return status;
}

export default function ModelBrowser({
  open,
  onClose,
  onSelectModel,
  onDropModel,
  onApplyWorkflow,
  onOpenCompliance,
  initialMode,
  filterNodeType,
  launch,
}: Props) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [mode, setMode] = useState<BrowserMode>(normalizeBrowserMode(initialMode ?? launch?.mode ?? "search"));
  const [taskType, setTaskType] = useState("");
  const [commercialOnly, setCommercialOnly] = useState(false);
  const [discoverResults, setDiscoverResults] = useState<DiscoverModelResult[]>([]);
  const [searchHits, setSearchHits] = useState<Array<{ model: ModelCard; rationale?: string }>>([]);
  const [agentPlan, setAgentPlan] = useState<AgentPlan | null>(null);
  const [planLlmModel, setPlanLlmModel] = useState<PlanLlmModelId>(PLAN_LLM_OPTIONS[0].id);
  /** Plan mode only submits after Enter — not while typing. */
  const [planSubmittedQuery, setPlanSubmittedQuery] = useState<string | null>(null);
  /** Bumps on each Enter so re-submitting the same prompt still refreshes. */
  const [planSubmitNonce, setPlanSubmitNonce] = useState(0);
  const [workflowSuggestions, setWorkflowSuggestions] = useState<
    Array<{
      template_id: string;
      title: string;
      description: string;
      rationale: string;
      score: number;
      workflow: Workflow;
    }>
  >([]);
  const [loading, setLoading] = useState(false);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [installProgress, setInstallProgress] = useState<Record<string, ModelInstallState>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<InstallRecovery | null>(null);
  const [failedModelId, setFailedModelId] = useState<string | null>(null);
  const [workflowHandoffHint, setWorkflowHandoffHint] = useState<string | null>(null);
  const [detailModelId, setDetailModelId] = useState<string | null>(null);
  const [showInstallLogs, setShowInstallLogs] = useState(false);
  const [requiredModels, setRequiredModels] = useState<ModelCard[]>([]);
  const [unknownRequiredIds, setUnknownRequiredIds] = useState<string[]>([]);
  const [installingAllRequired, setInstallingAllRequired] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const installStopRef = useRef(false);

  const requiredModelIds = launch?.requiredModelIds ?? [];

  useEffect(() => {
    if (!open) return;
    if (launch?.mode) {
      setMode(normalizeBrowserMode(launch.mode));
    } else if (initialMode) {
      setMode(normalizeBrowserMode(initialMode));
    }
    if (launch?.query != null) {
      setQuery(launch.query);
      setDebouncedQuery(launch.query);
    }
    if (launch?.taskType != null) {
      setTaskType(launch.taskType);
    }
    if (launch?.commercialOnly != null) {
      setCommercialOnly(launch.commercialOnly);
    }
  }, [open, launch, initialMode]);

  const effectiveNodeFilter = filterNodeType ?? launch?.filterNodeType ?? null;

  useEffect(() => {
    if (!open) return;
    if (mode === "plan") return;
    const timer = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(timer);
  }, [query, open, mode]);

  useEffect(() => {
    if (mode !== "plan") {
      setPlanSubmittedQuery(null);
    }
  }, [mode]);

  const refresh = useCallback(async () => {
    if (mode === "plan" && !(planSubmittedQuery ?? "").trim()) {
      setAgentPlan(null);
      setSearchHits([]);
      setWorkflowSuggestions([]);
      setDiscoverResults([]);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (mode === "plan") {
        const prompt = (planSubmittedQuery ?? "").trim();
        const data = await planAgentRequest(prompt, {
          commercial_ok: commercialOnly ? true : undefined,
          task_type: taskType || undefined,
          node_type: effectiveNodeFilter || undefined,
          planner: "llm",
          llm_model: planLlmModel,
        });
        setAgentPlan(data);
        setSearchHits([]);
        setWorkflowSuggestions([]);
        setDiscoverResults([]);
        setWorkflowHandoffHint(null);
        return;
      }
      setAgentPlan(null);
      if (mode === "workflow") {
        // Suggest workflow = deterministic bundled templates; Patch Generation (⌘G) is LLM-only.
        const data = await suggestWorkflows(debouncedQuery, { prefer_llm: false });
        setWorkflowSuggestions(data.results);
        setSearchHits([]);
        setDiscoverResults([]);
        return;
      }
      if (mode === "discover") {
        const results = await discoverModels(debouncedQuery, {
          task_type: taskType || undefined,
          limit: 20,
        });
        setDiscoverResults(filterDiscoverResults(results, commercialOnly, effectiveNodeFilter));
        setSearchHits([]);
        setWorkflowSuggestions([]);
        setWorkflowHandoffHint(null);
        return;
      }
      // Search: empty query browses catalog; non-empty uses recommender (ranked + rationale).
      const filters = {
        task_type: taskType || undefined,
        commercial_ok: commercialOnly ? true : undefined,
        node_type: effectiveNodeFilter || undefined,
      };
      if (!debouncedQuery.trim()) {
        const results = await searchModels("", filters);
        setSearchHits(
          filterModelsForNode(results, effectiveNodeFilter).map((model) => ({ model })),
        );
        setWorkflowSuggestions([]);
        setDiscoverResults([]);
        setWorkflowHandoffHint(null);
        return;
      }
      const data = await recommendModels(debouncedQuery, {
        commercial_ok: filters.commercial_ok,
        task_type: filters.task_type,
        node_type: filters.node_type,
      });
      const filtered = filterModelsForNode(
        data.results.map((entry) => entry.model),
        effectiveNodeFilter,
      );
      const rationaleById = new Map(data.results.map((entry) => [entry.model.id, entry.rationale]));
      setSearchHits(
        filtered.map((model) => ({
          model,
          rationale: rationaleById.get(model.id) ?? "",
        })),
      );
      setWorkflowSuggestions([]);
      setDiscoverResults([]);
      setWorkflowHandoffHint(data.workflow_handoff_hint ?? null);
    } catch (err) {
      setSearchHits([]);
      setWorkflowSuggestions([]);
      setDiscoverResults([]);
      setAgentPlan(null);
      setWorkflowHandoffHint(null);
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, planSubmittedQuery, planSubmitNonce, mode, taskType, commercialOnly, effectiveNodeFilter, planLlmModel]);

  useEffect(() => {
    if (!open) return;
    if (!requiredModelIds.length) {
      setRequiredModels([]);
      setUnknownRequiredIds([]);
      return;
    }
    let cancelled = false;
    void Promise.all(
      requiredModelIds.map(async (modelId) => {
        try {
          const card = await fetchModelCard(modelId);
          return { modelId, card };
        } catch {
          return { modelId, card: null };
        }
      }),
    ).then((rows) => {
      if (cancelled) return;
      setRequiredModels(
        rows.map((row) => row.card).filter((card): card is ModelCard => card != null),
      );
      setUnknownRequiredIds(rows.filter((row) => row.card == null).map((row) => row.modelId));
    });
    return () => {
      cancelled = true;
    };
  }, [open, requiredModelIds.join("|")]);

  useEffect(() => {
    if (!open) return;
    if (initialMode && !launch?.mode) {
      setMode(normalizeBrowserMode(initialMode));
    }
  }, [open, initialMode, launch?.mode]);

  useEffect(() => {
    if (!open) return;
    void refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (!open) {
      setDetailModelId(null);
      setShowInstallLogs(false);
      setRecovery(null);
      setFailedModelId(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (detailModelId) {
          setDetailModelId(null);
          return;
        }
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, detailModelId]);

  const loadRecovery = async (modelId: string) => {
    setFailedModelId(modelId);
    setShowInstallLogs(false);
    setError(null);
    try {
      const recoveryData = await fetchInstallRecovery(modelId);
      setRecovery(recoveryData);
    } catch (err) {
      setRecovery(null);
      setError(err instanceof Error ? err.message : "Recovery lookup failed");
    }
  };

  const handleInstall = async (modelId: string) => {
    setInstallingId(modelId);
    setRecovery(null);
    setFailedModelId(null);
    setShowInstallLogs(false);
    setError(null);
    setNotice(null);
    installStopRef.current = false;
    try {
      await installModelWithProgress(
        modelId,
        (state) => {
          setInstallProgress((prev) => ({ ...prev, [modelId]: state }));
        },
        { shouldStop: () => installStopRef.current },
      );
      await refresh();
    } catch (err) {
      if (err instanceof InstallCancelledError) {
        setError(null);
        await refresh();
        return;
      }
      await loadRecovery(modelId);
    } finally {
      setInstallingId(null);
    }
  };

  const handleCancelInstall = (modelId: string) => {
    installStopRef.current = true;
    void cancelModelInstall(modelId).catch(() => {
      // Polling loop still observes shouldStop / cancelled status.
    });
  };

  const handleRemoveInstall = async (modelId: string, modelName: string) => {
    const confirmed = window.confirm(
      `Remove local files for “${modelName}”? This frees disk space. Shared Python packages stay installed; reinstall from Model Browser when needed.`,
    );
    if (!confirmed) return;
    setRemovingId(modelId);
    setError(null);
    setNotice(null);
    setRecovery(null);
    setFailedModelId(null);
    try {
      const result = await removeModelInstall(modelId);
      setInstallProgress((prev) => {
        const next = { ...prev };
        delete next[modelId];
        return next;
      });
      await refresh();
      setRequiredModels((prev) =>
        prev.map((entry) =>
          entry.id === modelId
            ? {
                ...entry,
                install_status: "not_installed",
                install_progress: 0,
                install_error: null,
                install_complete: false,
                inference_ready: false,
              }
            : entry,
        ),
      );
      setNotice(
        result.freed_mb > 0
          ? `Removed ${modelName} (~${result.freed_mb} MB freed).`
          : `Removed ${modelName} install record.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remove failed");
    } finally {
      setRemovingId(null);
    }
  };

  const handleInstallAllRequired = async () => {
    const pending = requiredModels.filter((model) => !modelIsReady(model));
    if (!pending.length) return;
    setInstallingAllRequired(true);
    setError(null);
    setRecovery(null);
    setFailedModelId(null);
    installStopRef.current = false;
    try {
      for (const model of pending) {
        if (installStopRef.current) break;
        setInstallingId(model.id);
        try {
          await installModelWithProgress(
            model.id,
            (state) => {
              setInstallProgress((prev) => ({ ...prev, [model.id]: state }));
            },
            { shouldStop: () => installStopRef.current },
          );
        } catch (err) {
          if (err instanceof InstallCancelledError) break;
          throw err;
        }
        const refreshed = await fetchModelCard(model.id);
        setRequiredModels((prev) => prev.map((entry) => (entry.id === model.id ? refreshed : entry)));
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Install failed");
    } finally {
      setInstallingId(null);
      setInstallingAllRequired(false);
    }
  };

  const runPlanAction = (action: AgentPlanAction) => {
    if (action.type === "install_model" && action.model_id) {
      void handleInstall(action.model_id);
      return;
    }
    if (action.type === "drop_node" && action.model_id && action.node_type) {
      onDropModel?.(action.model_id, action.node_type);
      onClose();
      return;
    }
    if (action.type === "open_compliance") {
      onClose();
      onOpenCompliance?.();
    }
  };

  const planModelActions = useMemo(
    () =>
      agentPlan?.actions.filter(
        (action) =>
          action.type === "install_model" ||
          action.type === "drop_node" ||
          action.type === "suggest_public_model",
      ) ?? [],
    [agentPlan],
  );
  const planInstallActions = useMemo(
    () => planModelActions.filter((action) => action.type === "install_model"),
    [planModelActions],
  );
  const planPublicActions = useMemo(
    () => planModelActions.filter((action) => action.type === "suggest_public_model"),
    [planModelActions],
  );

  const cards = useMemo(() => searchHits, [searchHits]);

  const detailModel = useMemo(() => {
    if (!detailModelId) return null;
    return cards.find(({ model }) => model.id === detailModelId)?.model ?? null;
  }, [cards, detailModelId]);

  if (!open) return null;

  const catalogHint =
    mode === "plan"
      ? "Model Plan — describe a task; Claude (or deterministic fallback) picks published registry models to Install / Drop. Does not install from Discover or compose graphs — use Patch Generation (⌘G) for a full patch."
      : mode === "search"
        ? "Search ranks the local published catalog (keywords or natural-language task). Install only works for published entries — not live Hugging Face (use Discover to browse)."
        : mode === "discover"
          ? "Hugging Face browse only — no Install here. File a GitHub request; Install unlocks after a verified registry entry is merged (no secrets; no GroovyUI account)."
          : mode === "workflow"
            ? "Suggest workflow — match a bundled template from your description (no LLM). For a new graph draft, use Patch Generation (⌘G)."
            : null;

  const requiredPending = requiredModels.filter((model) => !modelIsReady(model));

  const renderModelActions = (model: ModelCard, nodeType: string | undefined, isInstalling: boolean, status: string) => {
    if (isDraftModel(model)) {
      return (
        <span className="model-card__draft-note">
          Draft — pending maintainer review. Install unlocks after publish.
        </span>
      );
    }

    const needsSetup = modelNeedsReinstall(model);
    const readyForUse = status === "ready" && !needsSetup;
    const isRemoving = removingId === model.id;
    const canRemove =
      !isInstalling &&
      !isRemoving &&
      (readyForUse || needsSetup || status === "failed" || status === "cancelled");
    const removeButton = canRemove ? (
      <button type="button" onClick={() => void handleRemoveInstall(model.id, model.name)}>
        Remove
      </button>
    ) : isRemoving ? (
      <button type="button" disabled>
        Removing…
      </button>
    ) : null;

    if (readyForUse) {
      return (
        <>
          {filterNodeType ? (
            <button type="button" onClick={() => onSelectModel?.(model.id)}>
              Use model
            </button>
          ) : null}
          {nodeType && onDropModel && !filterNodeType ? (
            <button type="button" onClick={() => onDropModel(model.id, nodeType)}>
              Drop node
            </button>
          ) : null}
          {!filterNodeType && !onDropModel ? (
            <button type="button" onClick={() => onSelectModel?.(model.id)}>
              Select
            </button>
          ) : null}
          {removeButton}
        </>
      );
    }

    if (needsSetup) {
      return isInstalling ? (
        <button type="button" onClick={() => handleCancelInstall(model.id)}>
          Cancel install
        </button>
      ) : (
        <>
          <button type="button" onClick={() => void handleInstall(model.id)}>
            Reinstall / fix setup
          </button>
          {removeButton}
        </>
      );
    }

    if (status === "failed" || status === "cancelled") {
      return (
        <>
          <button type="button" disabled={isInstalling} onClick={() => void handleInstall(model.id)}>
            Retry install
          </button>
          <button type="button" onClick={() => void loadRecovery(model.id)}>
            Explain failure
          </button>
          {removeButton}
        </>
      );
    }

    return isInstalling ? (
      <button type="button" onClick={() => handleCancelInstall(model.id)}>
        {status === "cancelling" ? "Cancelling…" : "Cancel install"}
      </button>
    ) : (
      <button type="button" onClick={() => void handleInstall(model.id)}>
        Install
      </button>
    );
  };

  return (
    <div className="model-browser-backdrop" onClick={onClose}>
      <div className={`model-browser${detailModel ? " model-browser--with-detail" : ""}${mode === "plan" ? " model-browser--plan" : ""}`} onClick={(event) => event.stopPropagation()}>
        <header className="model-browser__header">
          <h2>Model Browser</h2>
          <button type="button" className="model-browser__close" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="model-browser__body">
          <div className="model-browser__main">
            <div className="model-browser__modes">
              <button type="button" className={mode === "search" ? "active" : ""} onClick={() => setMode("search")}>
                Search
              </button>
              <button
                type="button"
                className={mode === "discover" ? "active" : ""}
                onClick={() => {
                  setMode("discover");
                  setError(null);
                }}
              >
                Discover
              </button>
              <button
                type="button"
                className={mode === "plan" ? "active" : ""}
                onClick={() => {
                  setMode("plan");
                  setError(null);
                }}
              >
                Plan
              </button>
              <button type="button" className={mode === "workflow" ? "active" : ""} onClick={() => setMode("workflow")}>
                Suggest workflow
              </button>
            </div>
            {effectiveNodeFilter ? (
              <p className="model-browser__context">
                Showing models compatible with <strong>{effectiveNodeFilter}</strong>
              </p>
            ) : null}
            {requiredModels.length > 0 || unknownRequiredIds.length > 0 ? (
              <div className="model-browser__required">
                <p>
                  <strong>Required for this workflow</strong>
                  {unknownRequiredIds.length > 0
                    ? ` — ${unknownRequiredIds.length} not in catalog`
                    : requiredPending.length === 0
                      ? " — all models ready"
                      : ` — ${requiredPending.length} need install`}
                </p>
                <ul className="model-browser__required-list">
                  {requiredModels.map((model) => {
                    const ready = modelIsReady(model);
                    const live = installProgress[model.id];
                    const installing =
                      installingId === model.id ||
                      live?.status === "downloading" ||
                      live?.status === "verifying";
                    return (
                      <li key={model.id}>
                        <span>{model.name}</span>
                        <span className={`pill pill--${ready ? "ready" : installing ? "neutral" : "warning"}`}>
                          {installing
                            ? installStatusLabel(live?.status ?? "downloading", live?.progress)
                            : ready
                              ? "ready"
                              : modelNeedsReinstall(model)
                                ? "needs setup"
                                : model.install_status}
                        </span>
                      </li>
                    );
                  })}
                  {unknownRequiredIds.map((modelId) => (
                    <li key={`unknown-${modelId}`}>
                      <span>{modelId}</span>
                      <span className="pill pill--warning">not in catalog</span>
                      <button
                        type="button"
                        className="model-browser__request-link"
                        onClick={() => openModelRequestIssue(prefillFromUnknownModelId(modelId))}
                      >
                        File GitHub request
                      </button>
                    </li>
                  ))}
                </ul>
                {requiredPending.length > 0 ? (
                  <button
                    type="button"
                    className="model-browser__install-all"
                    disabled={installingAllRequired || installingId != null}
                    onClick={() => void handleInstallAllRequired()}
                  >
                    {installingAllRequired ? "Installing…" : `Install all required (${requiredPending.length})`}
                  </button>
                ) : null}
              </div>
            ) : null}
            <input
              className="model-browser__search"
              placeholder={
                mode === "plan"
                  ? "Describe the task, then press Enter — e.g. commercial podcast denoise"
                  : mode === "workflow"
                  ? "Deterministic match — e.g. denoise podcast then normalize"
                  : mode === "discover"
                      ? "Search Hugging Face — e.g. denoise podcast whisper demucs"
                      : "Search or describe a task — e.g. denoise, stems, commercial podcast cleanup…"
              }
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (mode !== "plan") return;
                if (event.key !== "Enter" && event.code !== "Enter" && event.code !== "NumpadEnter") {
                  return;
                }
                if (event.nativeEvent.isComposing || event.repeat) return;
                event.preventDefault();
                event.stopPropagation();
                const prompt = event.currentTarget.value.trim();
                setPlanSubmittedQuery(prompt || null);
                if (!prompt) {
                  setAgentPlan(null);
                  return;
                }
                setPlanSubmitNonce((n) => n + 1);
              }}
              autoFocus
            />
            <div className="model-browser__filters">
              {mode === "workflow" ? (
                <p className="model-browser__hint">
                  Deterministic template match — same suggestions for the same prompt. Preview-only until you Apply.
                </p>
              ) : (
                <>
                  <label className="model-browser__filter-select">
                    Task
                    <select
                      value={taskType}
                      onChange={(event) => setTaskType(event.target.value)}
                      aria-label="Task filter"
                    >
                      {TASK_FILTERS.map((filter) => (
                        <option key={filter.value} value={filter.value}>
                          {filter.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="model-browser__filter-check">
                    <input
                      type="checkbox"
                      checked={commercialOnly}
                      onChange={(event) => setCommercialOnly(event.target.checked)}
                    />
                    {mode === "discover" ? "Commercial OK only" : "Commercial OK"}
                  </label>
                  <button
                    type="button"
                    className="model-browser__request-link model-browser__request-blank"
                    title="Opens a blank model-request issue — paste any Hugging Face (or allowlisted) model URL"
                    onClick={() => openModelRequestIssue({})}
                  >
                    File GitHub request
                  </button>
                  {mode === "plan" ? (
                    <div className="model-browser__llm-options" role="radiogroup" aria-label="LLM options">
                      <p className="model-browser__llm-options-label">LLM for model picks</p>
                      {PLAN_LLM_OPTIONS.map((option) => {
                        const selected = planLlmModel === option.id;
                        return (
                          <button
                            key={option.id}
                            type="button"
                            role="radio"
                            aria-checked={selected}
                            className={`model-browser__llm-option${selected ? " model-browser__llm-option--active" : ""}`}
                            onClick={() => setPlanLlmModel(option.id)}
                          >
                            <span className="model-browser__llm-option-title">{option.label}</span>
                            <span className="model-browser__llm-option-desc">{option.description}</span>
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </>
              )}
            </div>
            {catalogHint ? <p className="model-browser__hint model-browser__hint--catalog">{catalogHint}</p> : null}
            {recovery && failedModelId ? (
              <div className="model-browser__recovery">
                <p>
                  <strong>Install failed:</strong> {recovery.summary}
                </p>
                {recovery.explain ? <p className="model-browser__hint">{recovery.explain}</p> : null}
                {recovery.error ? (
                  <pre className={`model-browser__logs${showInstallLogs ? " model-browser__logs--open" : ""}`}>
                    {recovery.error}
                  </pre>
                ) : null}
                <ul>
                  {recovery.suggested_fixes.map((fix) => (
                    <li key={fix}>{fix}</li>
                  ))}
                </ul>
                <div className="model-card__actions">
                  <button type="button" onClick={() => void handleInstall(failedModelId)}>
                    Retry install
                  </button>
                  {recovery.error ? (
                    <button type="button" onClick={() => setShowInstallLogs((value) => !value)}>
                      {showInstallLogs ? "Hide logs" : "Open logs"}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => {
                      setRecovery(null);
                      setFailedModelId(null);
                    }}
                  >
                    Dismiss
                  </button>
                </div>
                {recovery.similar_models.length > 0 ? (
                  <>
                    <p>Similar models (install is your choice):</p>
                    <div className="model-browser__similar">
                      {recovery.similar_models.map((model) => (
                        <div key={model.id} className="model-browser__similar-item">
                          <button type="button" onClick={() => void handleInstall(model.id)}>
                            Install {model.name}
                          </button>
                          {model.similar_rationale ? (
                            <span className="model-browser__hint">{model.similar_rationale}</span>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>
            ) : null}
            <div className={`model-browser__list${mode === "plan" ? " model-browser__list--plan" : ""}`}>
              {loading ? (
                <p className="model-browser__hint model-browser__hint--waiting">
                  {mode === "plan"
                    ? "Planning models for this task…"
                    : "Searching…"}
                </p>
              ) : null}
              {error ? <p className="model-browser__error">{error}</p> : null}
              {notice ? <p className="model-browser__notice">{notice}</p> : null}
              {mode === "plan" ? (
                <>
                  {!loading && !error && !planSubmittedQuery ? (
                    <p className="model-browser__hint">
                      Type a task and press <strong>Enter</strong> — Plan recommends which published
                      models to install (and optional Drop node). Graph drafting is{" "}
                      <strong>Patch Generation (⌘G)</strong>, not Plan.
                    </p>
                  ) : null}
                  {loading && planSubmittedQuery ? (
                    <p className="model-browser__hint model-browser__hint--waiting" aria-live="polite">
                      Planning models for “{planSubmittedQuery}”…
                    </p>
                  ) : null}
                  {agentPlan?.notes ? <p className="model-browser__hint">{agentPlan.notes}</p> : null}
                  {agentPlan?.tools_used?.length ? (
                    <p className="model-browser__hint">
                      {agentPlan.deterministic === false ? "LLM model plan" : "Deterministic model plan"}
                      {agentPlan.inferred_task ? ` · task ${agentPlan.inferred_task}` : ""}
                      {agentPlan.public_pick_count != null
                        ? ` · ${agentPlan.public_pick_count} public pick(s)`
                        : agentPlan.recommend_count != null
                          ? ` · ${agentPlan.recommend_count} model(s)`
                          : ""}
                    </p>
                  ) : null}
                  {!loading &&
                  planSubmittedQuery &&
                  planInstallActions.length === 0 &&
                  planPublicActions.length === 0 &&
                  agentPlan ? (
                    <p className="model-browser__hint">
                      No models matched this task — try another description, relax Commercial OK, or use Find
                      models / Search.
                    </p>
                  ) : null}
                  {planInstallActions.map((action) => {
                    const model = action.model;
                    if (!model) return null;
                    const drop = planModelActions.find(
                      (entry) =>
                        entry.type === "drop_node" &&
                        entry.model_id === action.model_id &&
                        entry.node_type,
                    );
                    const status = installProgress[model.id]?.status ?? model.install_status ?? "not_installed";
                    const isInstalling = installingId === model.id;
                    const nodeType = model.compatible_nodes?.[0];
                    return (
                      <article key={action.id} className="model-card">
                        <div className="model-card__row">
                          <strong>{action.public_name || model.name}</strong>
                          <span className="pill">
                            {action.public_name ? `${action.public_name} → ${model.id}` : model.id}
                          </span>
                        </div>
                        <p className="model-card__desc">{model.description}</p>
                        <p className="model-card__rationale">{action.rationale}</p>
                        <div className="model-card__meta">
                          <span className="pill">local registry</span>
                          {(model.task_types || []).slice(0, 3).map((task) => (
                            <span key={task} className="pill">
                              {task}
                            </span>
                          ))}
                          {model.license?.spdx ? <span className="pill">{model.license.spdx}</span> : null}
                        </div>
                        <div className="model-card__actions">
                          {renderModelActions(model, nodeType, isInstalling, status)}
                          {drop?.node_type ? (
                            <button type="button" onClick={() => runPlanAction(drop)}>
                              Drop {drop.node_type}
                            </button>
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                  {planPublicActions.map((action) => (
                    <article key={action.id} className="model-card model-card--public-pick">
                      <div className="model-card__row">
                        <strong>{action.public_name || action.title}</strong>
                        <span className="pill">public</span>
                      </div>
                      <p className="model-card__rationale">{action.rationale}</p>
                      <div className="model-card__meta">
                        <span className="pill">not in local registry</span>
                        {action.task_type ? <span className="pill">{action.task_type}</span> : null}
                        {action.node_type ? <span className="pill">{action.node_type}</span> : null}
                      </div>
                      <div className="model-card__actions">
                        <button
                          type="button"
                          onClick={() => {
                            setMode("discover");
                            const q = action.public_name || action.title;
                            setQuery(q);
                            setDebouncedQuery(q);
                          }}
                        >
                          Search Discover
                        </button>
                      </div>
                    </article>
                  ))}
                </>
              ) : mode === "workflow" ? (
                <>
                  {!loading && !error && workflowSuggestions.length === 0 ? (
                    <p className="model-browser__hint">No workflow suggestions yet — try describing your task.</p>
                  ) : null}
                  {workflowSuggestions.map((item) => (
                    <article key={item.template_id} className="model-card">
                      <div className="model-card__row">
                        <strong>{item.title}</strong>
                        <span className="pill">{item.template_id}</span>
                      </div>
                      <p className="model-card__desc">{item.description}</p>
                      <p className="model-card__rationale">{item.rationale}</p>
                      <div className="model-card__actions">
                        <button
                          type="button"
                          onClick={() => {
                            onApplyWorkflow?.(item.workflow);
                            onClose();
                          }}
                        >
                          Apply workflow
                        </button>
                      </div>
                    </article>
                  ))}
                </>
              ) : mode === "discover" ? (
                <>
                  {!loading && !error && discoverResults.length === 0 ? (
                    <p className="model-browser__hint">
                      No Hugging Face models matched — try another task filter or search term.
                    </p>
                  ) : null}
                  {discoverResults.map((entry) => {
                    const badge = licenseBadge({
                      spdx: entry.license.spdx,
                      commercial_ok: entry.license.commercial_ok ?? false,
                      attribution_required: false,
                    });
                    const updated = formatDiscoverUpdated(entry.updated_at);
                    return (
                      <article key={entry.external_id} className="model-card model-card--external">
                        <div className="model-card__row">
                          <strong>{entry.name}</strong>
                          <span className="pill pill--neutral">external</span>
                        </div>
                        <p className="model-card__desc">{entry.description}</p>
                        <div className="model-card__meta">
                          <span className={badge.className}>{badge.label}</span>
                          {entry.author ? <span>{entry.author}</span> : null}
                          {updated ? <span>Updated {updated}</span> : null}
                          {entry.downloads != null ? <span>{entry.downloads.toLocaleString()} downloads</span> : null}
                        </div>
                        {entry.suggested_compatible_nodes.length > 0 ? (
                          <p className="model-card__nodes">Nodes: {entry.suggested_compatible_nodes.join(", ")}</p>
                        ) : null}
                        {entry.tags.length > 0 ? (
                          <p className="model-card__tags">{entry.tags.slice(0, 6).map((tag) => `#${tag}`).join(" ")}</p>
                        ) : null}
                        <div className="model-card__actions">
                          <a
                            className="model-card__link-btn"
                            href={entry.source_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open on Hugging Face
                          </a>
                          <button
                            type="button"
                            className="model-card__link-btn"
                            onClick={() => openModelRequestIssue(prefillFromDiscover(entry))}
                          >
                            File GitHub request
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </>
              ) : (
                <>
                  {!loading && !error && cards.length === 0 ? (
                    <p className="model-browser__hint">
                      {debouncedQuery.trim()
                        ? `No models found in the local catalog${effectiveNodeFilter ? ` for ${effectiveNodeFilter}` : ""}. Try another phrase, task filter, or Discover.`
                        : "Type a keyword or task description to rank published models — or leave empty to browse the catalog."}
                    </p>
                  ) : null}
                  {!loading && cards.length > 0 && debouncedQuery.trim() ? (
                    <div className="model-browser__handoff">
                      <p className="model-browser__hint">
                        {workflowHandoffHint ??
                          "Ranked for your query — Install / Drop stay explicit. You can also preview a workflow template."}
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          setMode("workflow");
                          setWorkflowHandoffHint(null);
                        }}
                      >
                        Also suggest workflow
                      </button>
                    </div>
                  ) : null}
                  {cards.map(({ model, rationale }) => {
                    const liveProgress = installProgress[model.id];
                    const status = modelCardStatus(model, liveProgress);
                    const progress = liveProgress?.progress ?? model.install_progress;
                    const isInstalling =
                      installingId === model.id ||
                      status === "downloading" ||
                      status === "verifying" ||
                      status === "cancelling";
                    const nodeType = model.compatible_nodes?.[0];
                    const badge = licenseBadge(model.license);
                    const tags = model.tags ?? [];
                    const compatibleNodes = model.compatible_nodes ?? [];
                    const pillClass =
                      isDraftModel(model)
                        ? "warning"
                        : status === "ready"
                        ? "ready"
                        : status === "needs setup"
                          ? "warning"
                          : status === "failed"
                            ? "failed"
                            : "neutral";
                    return (
                      <article key={model.id} className="model-card">
                        <div className="model-card__row">
                          <strong>{model.name}</strong>
                          <span className={`pill pill--${pillClass}`}>
                            {isDraftModel(model)
                              ? "draft"
                              : isInstalling
                                ? installStatusLabel(liveProgress?.status ?? "downloading", progress)
                                : status}
                          </span>
                        </div>
                        <p className="model-card__desc">{model.description}</p>
                        {rationale ? <p className="model-card__rationale">{rationale}</p> : null}
                        <div className="model-card__meta">
                          <span className={badge.className}>{badge.label}</span>
                          {model.license?.code_spdx && model.license.code_spdx !== model.license.spdx ? (
                            <span className="pill pill--neutral">code {model.license.code_spdx}</span>
                          ) : null}
                          {model.license?.attribution_required ? (
                            <span className="pill pill--neutral">Attribution</span>
                          ) : null}
                          <span>{model.vram_gb_estimate} GB VRAM</span>
                          {model.dev_stub && !isDraftModel(model) ? <span className="pill pill--neutral">stub</span> : null}
                          {isDraftModel(model) ? <span className="pill pill--warning">pending review</span> : null}
                          {model.inference_ready === false && model.install_status === "ready" ? (
                            <span className="pill pill--warning">runtime missing</span>
                          ) : null}
                        </div>
                        {compatibleNodes.length > 0 ? (
                          <p className="model-card__nodes">Nodes: {compatibleNodes.join(", ")}</p>
                        ) : null}
                        {tags.length > 0 ? (
                          <p className="model-card__tags">{tags.slice(0, 6).map((tag) => `#${tag}`).join(" ")}</p>
                        ) : null}
                        {isInstalling && progress != null ? (
                          <div className="model-card__progress" aria-hidden>
                            <div className="model-card__progress-bar" style={{ width: `${Math.round(progress * 100)}%` }} />
                          </div>
                        ) : null}
                        <div className="model-card__actions">
                          <button type="button" className="model-card__detail-btn" onClick={() => setDetailModelId(model.id)}>
                            Open
                          </button>
                          {renderModelActions(model, nodeType, isInstalling, liveProgress?.status ?? model.install_status)}
                        </div>
                      </article>
                    );
                  })}
                </>
              )}
            </div>
          </div>
          {detailModel ? (
            <aside className="model-browser__detail">
              <header className="model-browser__detail-header">
                <h3>{detailModel.name}</h3>
                <button type="button" onClick={() => setDetailModelId(null)}>
                  ✕
                </button>
              </header>
              <p className="model-browser__detail-id">{detailModel.id}</p>
              {detailModel.author ? <p className="model-browser__detail-meta">Author: {detailModel.author}</p> : null}
              <p className="model-card__desc">{detailModel.description}</p>
              <div className="model-card__meta">
                <span className={licenseBadge(detailModel.license).className}>
                  {licenseBadge(detailModel.license).label}
                </span>
                <span>{detailModel.vram_gb_estimate} GB VRAM</span>
                {detailModel.dev_stub ? <span className="pill pill--neutral">dev stub</span> : null}
              </div>
              {licenseDetailLines(detailModel.license).map((line) => (
                <p key={line} className="model-browser__detail-meta">
                  {line}
                </p>
              ))}
              <p className="model-browser__detail-meta">
                Install: {detailModel.install_status}
                {detailModel.inference_ready === false && !detailModel.dev_stub ? " · inference not ready" : ""}
              </p>
              {detailModel.install_error ? (
                <pre className="model-browser__logs model-browser__logs--open">{detailModel.install_error}</pre>
              ) : null}
              {detailModel.install_status === "failed" || detailModel.install_status === "cancelled" ? (
                <div className="model-card__actions">
                  <button type="button" onClick={() => void loadRecovery(detailModel.id)}>
                    Explain failure
                  </button>
                </div>
              ) : null}
              {detailModel.task_types?.length ? (
                <p className="model-browser__detail-meta">Tasks: {detailModel.task_types.join(", ")}</p>
              ) : null}
              {(detailModel.compatible_nodes ?? []).length > 0 ? (
                <p className="model-browser__detail-meta">Nodes: {detailModel.compatible_nodes!.join(", ")}</p>
              ) : null}
              {(detailModel.tags ?? []).length > 0 ? (
                <p className="model-card__tags">{detailModel.tags!.map((tag) => `#${tag}`).join(" ")}</p>
              ) : null}
              {detailModel.inference_params && detailModel.inference_params.length > 0 ? (
                <div className="model-browser__params">
                  <h4>Inference params</h4>
                  <ul>
                    {detailModel.inference_params.map((param) => (
                      <li key={param.name}>
                        <strong>{param.name}</strong>
                        {param.default != null ? ` (default ${String(param.default)})` : ""}
                        {param.description ? ` — ${param.description}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div className="model-card__actions">
                {renderModelActions(
                  detailModel,
                  detailModel.compatible_nodes[0],
                  installingId === detailModel.id,
                  detailModel.install_status,
                )}
              </div>
            </aside>
          ) : null}
        </div>
      </div>
    </div>
  );
}
