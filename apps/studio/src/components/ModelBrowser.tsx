import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createModelDraft,
  discoverModels,
  fetchInstallRecovery,
  fetchModelCard,
  installModelWithProgress,
  recommendModels,
  searchModels,
  suggestWorkflows,
} from "../api";
import type { DiscoverModelResult, InstallRecovery, ModelCard, ModelInstallState, Workflow } from "../types";

type Props = {
  open: boolean;
  onClose: () => void;
  onSelectModel?: (modelId: string) => void;
  onDropModel?: (modelId: string, nodeType: string) => void;
  onApplyWorkflow?: (workflow: Workflow) => void;
  initialMode?: "search" | "recommend" | "workflow" | "discover";
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
  { value: "singing-synthesis", label: "Singing synthesis" },
  { value: "deepfake-detection", label: "Deepfake detection" },
  { value: "audio-compare", label: "A/B compare" },
];

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
  initialMode,
  filterNodeType,
  launch,
}: Props) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [mode, setMode] = useState<"search" | "recommend" | "workflow" | "discover">(initialMode ?? "search");
  const [taskType, setTaskType] = useState("");
  const [commercialOnly, setCommercialOnly] = useState(false);
  const [models, setModels] = useState<ModelCard[]>([]);
  const [discoverResults, setDiscoverResults] = useState<DiscoverModelResult[]>([]);
  const [draftResult, setDraftResult] = useState<{ id: string; created: boolean } | null>(null);
  const [draftingId, setDraftingId] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Array<{ model: ModelCard; rationale: string }>>([]);
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
  const [recovery, setRecovery] = useState<InstallRecovery | null>(null);
  const [failedModelId, setFailedModelId] = useState<string | null>(null);
  const [detailModelId, setDetailModelId] = useState<string | null>(null);
  const [showInstallLogs, setShowInstallLogs] = useState(false);
  const [requiredModels, setRequiredModels] = useState<ModelCard[]>([]);
  const [installingAllRequired, setInstallingAllRequired] = useState(false);

  const requiredModelIds = launch?.requiredModelIds ?? [];

  useEffect(() => {
    if (!open) return;
    if (launch?.mode) {
      setMode(launch.mode);
    } else if (initialMode) {
      setMode(initialMode);
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
    const timer = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(timer);
  }, [query, open]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (mode === "workflow") {
        const data = await suggestWorkflows(debouncedQuery);
        setWorkflowSuggestions(data.results);
        setModels([]);
        setRecommendations([]);
        setDiscoverResults([]);
        return;
      }
      if (mode === "discover") {
        const results = await discoverModels(debouncedQuery, {
          task_type: taskType || undefined,
          limit: 20,
        });
        setDiscoverResults(filterDiscoverResults(results, commercialOnly, effectiveNodeFilter));
        setModels([]);
        setRecommendations([]);
        setWorkflowSuggestions([]);
        return;
      }
      const filters = {
        task_type: taskType || undefined,
        commercial_ok: commercialOnly ? true : undefined,
        node_type: effectiveNodeFilter || undefined,
      };
      if (mode === "recommend") {
        if (!debouncedQuery.trim()) {
          setRecommendations([]);
          setModels([]);
          setWorkflowSuggestions([]);
          return;
        }
        const data = await recommendModels(debouncedQuery, {
          commercial_ok: filters.commercial_ok,
        });
        const filtered = filterModelsForNode(
          data.results.map((entry) => entry.model),
          effectiveNodeFilter,
        );
        const rationaleById = new Map(data.results.map((entry) => [entry.model.id, entry.rationale]));
        setRecommendations(
          filtered.map((model) => ({
            model,
            rationale: rationaleById.get(model.id) ?? "",
          })),
        );
        setModels([]);
        setWorkflowSuggestions([]);
      } else {
        const results = await searchModels(debouncedQuery, filters);
        setModels(filterModelsForNode(results, effectiveNodeFilter));
        setRecommendations([]);
        setWorkflowSuggestions([]);
        setDiscoverResults([]);
      }
    } catch (err) {
      setModels([]);
      setRecommendations([]);
      setWorkflowSuggestions([]);
      setDiscoverResults([]);
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, mode, taskType, commercialOnly, effectiveNodeFilter]);

  useEffect(() => {
    if (!open) return;
    if (!requiredModelIds.length) {
      setRequiredModels([]);
      return;
    }
    let cancelled = false;
    void Promise.all(
      requiredModelIds.map(async (modelId) => {
        try {
          return await fetchModelCard(modelId);
        } catch {
          return null;
        }
      }),
    ).then((cards) => {
      if (!cancelled) {
        setRequiredModels(cards.filter((card): card is ModelCard => card != null));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [open, requiredModelIds.join("|")]);

  useEffect(() => {
    if (!open) return;
    if (initialMode && !launch?.mode) {
      setMode(initialMode);
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
      setDraftResult(null);
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

  const handleInstall = async (modelId: string) => {
    setInstallingId(modelId);
    setRecovery(null);
    setFailedModelId(null);
    setShowInstallLogs(false);
    setError(null);
    try {
      await installModelWithProgress(modelId, (state) => {
        setInstallProgress((prev) => ({ ...prev, [modelId]: state }));
      });
      await refresh();
    } catch (err) {
      setFailedModelId(modelId);
      try {
        const recoveryData = await fetchInstallRecovery(modelId);
        setRecovery(recoveryData);
      } catch {
        setError(err instanceof Error ? err.message : "Install failed");
      }
    } finally {
      setInstallingId(null);
    }
  };

  const handleInstallAllRequired = async () => {
    const pending = requiredModels.filter((model) => !modelIsReady(model));
    if (!pending.length) return;
    setInstallingAllRequired(true);
    setError(null);
    setRecovery(null);
    setFailedModelId(null);
    try {
      for (const model of pending) {
        setInstallingId(model.id);
        await installModelWithProgress(model.id, (state) => {
          setInstallProgress((prev) => ({ ...prev, [model.id]: state }));
        });
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

  const handleCreateDraft = async (entry: DiscoverModelResult) => {
    setDraftingId(entry.external_id);
    setDraftResult(null);
    setError(null);
    try {
      const result = await createModelDraft(entry);
      setDraftResult({ id: result.model.id, created: result.created });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save draft");
    } finally {
      setDraftingId(null);
    }
  };

  const viewDraftInSearch = (draftId: string) => {
    setMode("search");
    setQuery(draftId);
    setDebouncedQuery(draftId);
    setTaskType("");
    setCommercialOnly(false);
    setError(null);
    setDetailModelId(draftId);
  };

  const cards = useMemo(
    () =>
      mode === "recommend"
        ? recommendations.map((entry) => ({ model: entry.model, rationale: entry.rationale }))
        : models.map((model) => ({ model, rationale: undefined as string | undefined })),
    [mode, recommendations, models],
  );

  const detailModel = useMemo(() => {
    if (!detailModelId) return null;
    return cards.find(({ model }) => model.id === detailModelId)?.model ?? null;
  }, [cards, detailModelId]);

  if (!open) return null;

  const catalogHint =
    mode === "recommend"
      ? "Find models searches the local published catalog only — not live Hugging Face."
      : mode === "search"
        ? "Verified catalog — safe to install from Model Browser."
        : mode === "discover"
          ? "Latest models from Hugging Face — browse only. Install after GroovyUI verifies the registry entry."
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
        </>
      );
    }

    if (needsSetup) {
      return (
        <button type="button" disabled={isInstalling} onClick={() => void handleInstall(model.id)}>
          {isInstalling ? installStatusLabel(status) : "Reinstall / fix setup"}
        </button>
      );
    }

    return (
      <button type="button" disabled={isInstalling} onClick={() => void handleInstall(model.id)}>
        {isInstalling ? installStatusLabel(status, model.install_progress) : "Install"}
      </button>
    );
  };

  return (
    <div className="model-browser-backdrop" onClick={onClose}>
      <div className={`model-browser${detailModel ? " model-browser--with-detail" : ""}`} onClick={(event) => event.stopPropagation()}>
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
                className={mode === "recommend" ? "active" : ""}
                onClick={() => {
                  setMode("recommend");
                  setError(null);
                }}
              >
                Find models
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
              <button type="button" className={mode === "workflow" ? "active" : ""} onClick={() => setMode("workflow")}>
                Suggest workflow
              </button>
            </div>
            {effectiveNodeFilter ? (
              <p className="model-browser__context">
                Showing models compatible with <strong>{effectiveNodeFilter}</strong>
              </p>
            ) : null}
            {requiredModels.length > 0 ? (
              <div className="model-browser__required">
                <p>
                  <strong>Required for this workflow</strong>
                  {requiredPending.length === 0
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
                mode === "workflow"
                  ? "Describe your pipeline — e.g. denoise podcast then normalize"
                  : mode === "recommend"
                    ? "Describe your task — e.g. commercial-friendly podcast denoise"
                    : mode === "discover"
                      ? "Search Hugging Face — e.g. denoise podcast whisper demucs"
                      : "Search models — denoise, stems, voice clone…"
              }
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              autoFocus
            />
            <div className="model-browser__filters">
              {mode !== "workflow" ? (
                <>
                  <select value={taskType} onChange={(event) => setTaskType(event.target.value)}>
                    {TASK_FILTERS.map((filter) => (
                      <option key={filter.value} value={filter.value}>
                        {filter.label}
                      </option>
                    ))}
                  </select>
                  {mode !== "discover" ? (
                    <label>
                      <input type="checkbox" checked={commercialOnly} onChange={(event) => setCommercialOnly(event.target.checked)} />
                      Commercial OK
                    </label>
                  ) : (
                    <label>
                      <input type="checkbox" checked={commercialOnly} onChange={(event) => setCommercialOnly(event.target.checked)} />
                      Commercial OK only
                    </label>
                  )}
                </>
              ) : (
                <p className="model-browser__hint">Suggestions are preview-only — click Apply to replace the canvas.</p>
              )}
            </div>
            {catalogHint ? <p className="model-browser__hint model-browser__hint--catalog">{catalogHint}</p> : null}
            {draftResult ? (
              <div className="model-browser__draft-next">
                <p>
                  <strong>{draftResult.created ? "Draft saved" : "Draft already exists"}:</strong>{" "}
                  <code>{draftResult.id}</code>
                </p>
                <p>
                  Install stays off until a maintainer publishes it. Meanwhile, use a verified model from Search, or keep
                  exploring in Discover.
                </p>
                <div className="model-card__actions">
                  <button type="button" onClick={() => viewDraftInSearch(draftResult.id)}>
                    View in Search
                  </button>
                  <button type="button" onClick={() => setDraftResult(null)}>
                    Dismiss
                  </button>
                </div>
              </div>
            ) : null}
            {recovery && failedModelId ? (
              <div className="model-browser__recovery">
                <p>
                  <strong>Install failed:</strong> {recovery.summary}
                </p>
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
                </div>
                {recovery.similar_models.length > 0 ? (
                  <>
                    <p>Similar models:</p>
                    <div className="model-browser__similar">
                      {recovery.similar_models.map((model) => (
                        <button key={model.id} type="button" onClick={() => void handleInstall(model.id)}>
                          Install {model.name}
                        </button>
                      ))}
                    </div>
                  </>
                ) : null}
              </div>
            ) : null}
            <div className="model-browser__list">
              {loading ? <p className="model-browser__hint">Searching…</p> : null}
              {error ? <p className="model-browser__error">{error}</p> : null}
              {mode === "workflow" ? (
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
                    const isDrafting = draftingId === entry.external_id;
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
                            disabled={isDrafting}
                            onClick={() => void handleCreateDraft(entry)}
                          >
                            {isDrafting ? "Saving draft…" : "Draft registry entry"}
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
                      {mode === "recommend"
                        ? "Describe your task above to get model recommendations from the local catalog."
                        : `No models found in the local catalog${effectiveNodeFilter ? ` for ${effectiveNodeFilter}` : ""}. Try another task filter or install from the required list above.`}
                    </p>
                  ) : null}
                  {cards.map(({ model, rationale }) => {
                    const liveProgress = installProgress[model.id];
                    const status = modelCardStatus(model, liveProgress);
                    const progress = liveProgress?.progress ?? model.install_progress;
                    const isInstalling = installingId === model.id || status === "downloading" || status === "verifying";
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
              <p className="model-browser__detail-meta">
                Install: {detailModel.install_status}
                {detailModel.inference_ready === false && !detailModel.dev_stub ? " · inference not ready" : ""}
              </p>
              {detailModel.install_error ? (
                <pre className="model-browser__logs model-browser__logs--open">{detailModel.install_error}</pre>
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
