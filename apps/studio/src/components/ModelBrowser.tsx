import { useCallback, useEffect, useState } from "react";
import { fetchInstallRecovery, recommendModels, searchModels, suggestWorkflows } from "../api";
import type { InstallRecovery, ModelCard, Workflow } from "../types";

type Props = {
  open: boolean;
  onClose: () => void;
  onSelectModel?: (modelId: string) => void;
  onApplyWorkflow?: (workflow: Workflow) => void;
  initialMode?: "search" | "recommend" | "workflow";
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
];

export default function ModelBrowser({ open, onClose, onSelectModel, onApplyWorkflow, initialMode }: Props) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"search" | "recommend" | "workflow">(initialMode ?? "search");
  const [taskType, setTaskType] = useState("");
  const [commercialOnly, setCommercialOnly] = useState(false);
  const [models, setModels] = useState<ModelCard[]>([]);
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
  const [installing, setInstalling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<InstallRecovery | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setRecovery(null);
    try {
      if (mode === "workflow") {
        const data = await suggestWorkflows(query);
        setWorkflowSuggestions(data.results);
        setModels([]);
        setRecommendations([]);
        return;
      }
      const filters = {
        task_type: taskType || undefined,
        commercial_ok: commercialOnly ? true : undefined,
      };
      if (mode === "recommend" && query.trim()) {
        const data = await recommendModels(query, filters);
        setRecommendations(data.results);
        setModels([]);
        setWorkflowSuggestions([]);
      } else {
        const results = await searchModels(query, filters);
        setModels(results);
        setRecommendations([]);
        setWorkflowSuggestions([]);
      }
    } catch (err) {
      setModels([]);
      setRecommendations([]);
      setWorkflowSuggestions([]);
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [query, mode, taskType, commercialOnly]);

  useEffect(() => {
    if (!open) return;
    if (initialMode) {
      setMode(initialMode);
    }
  }, [open, initialMode]);

  useEffect(() => {
    if (!open) return;
    void refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const handleInstall = async (modelId: string) => {
    setInstalling(modelId);
    setRecovery(null);
    try {
      const res = await fetch(`${import.meta.env.VITE_GROOVY_API ?? "http://127.0.0.1:8188"}/api/models/${modelId}/install`, {
        method: "POST",
      });
      const state = await res.json();
      if (state.status === "failed") {
        const recoveryData = await fetchInstallRecovery(modelId);
        setRecovery(recoveryData);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Install failed");
    } finally {
      setInstalling(null);
    }
  };

  const cards =
    mode === "recommend"
      ? recommendations.map((r) => ({ model: r.model, rationale: r.rationale }))
      : models.map((m) => ({ model: m, rationale: undefined as string | undefined }));

  return (
    <div className="model-browser-backdrop" onClick={onClose}>
      <div className="model-browser" onClick={(e) => e.stopPropagation()}>
        <header className="model-browser__header">
          <h2>Command Palette</h2>
          <button type="button" className="model-browser__close" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="model-browser__modes">
          <button type="button" className={mode === "search" ? "active" : ""} onClick={() => setMode("search")}>
            Search
          </button>
          <button type="button" className={mode === "recommend" ? "active" : ""} onClick={() => setMode("recommend")}>
            Find models
          </button>
          <button type="button" className={mode === "workflow" ? "active" : ""} onClick={() => setMode("workflow")}>
            Suggest workflow
          </button>
        </div>
        <input
          className="model-browser__search"
          placeholder={
            mode === "workflow"
              ? "Describe your pipeline — e.g. denoise podcast then normalize"
              : mode === "recommend"
                ? "Describe your task — e.g. commercial-friendly podcast denoise"
                : "Search models — denoise, stems, voice clone…"
          }
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <div className="model-browser__filters">
          {mode !== "workflow" ? (
            <>
              <select value={taskType} onChange={(e) => setTaskType(e.target.value)}>
                {TASK_FILTERS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
              <label>
                <input type="checkbox" checked={commercialOnly} onChange={(e) => setCommercialOnly(e.target.checked)} />
                Commercial OK
              </label>
            </>
          ) : (
            <p className="model-browser__hint">Suggestions are preview-only — click Apply to replace the canvas.</p>
          )}
        </div>
        {recovery ? (
          <div className="model-browser__recovery">
            <p>
              <strong>Install failed:</strong> {recovery.summary}
            </p>
            <ul>
              {recovery.suggested_fixes.map((fix) => (
                <li key={fix}>{fix}</li>
              ))}
            </ul>
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
          ) : (
            <>
              {!loading && !error && cards.length === 0 ? (
                <p className="model-browser__hint">No models found.</p>
              ) : null}
              {cards.map(({ model, rationale }) => (
                <article key={model.id} className="model-card">
                  <div className="model-card__row">
                    <strong>{model.name}</strong>
                    <span className={`pill pill--${model.install_status}`}>{model.install_status}</span>
                  </div>
                  <p className="model-card__desc">{model.description}</p>
                  {rationale ? <p className="model-card__rationale">{rationale}</p> : null}
                  <div className="model-card__meta">
                    <span>{model.license.spdx}</span>
                    <span>{model.vram_gb_estimate} GB VRAM</span>
                    <span>{model.task_types.join(", ")}</span>
                  </div>
                  <div className="model-card__actions">
                    {model.install_status === "ready" ? (
                      <button type="button" onClick={() => onSelectModel?.(model.id)}>
                        Use model
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={installing === model.id}
                        onClick={() => void handleInstall(model.id)}
                      >
                        {installing === model.id ? "Installing…" : "Install"}
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
