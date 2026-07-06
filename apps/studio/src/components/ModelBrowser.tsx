import { useCallback, useEffect, useState } from "react";
import { fetchInstallRecovery, recommendModels, searchModels } from "../api";
import type { InstallRecovery, ModelCard } from "../types";

type Props = {
  open: boolean;
  onClose: () => void;
  onSelectModel?: (modelId: string) => void;
};

const TASK_FILTERS = [
  { value: "", label: "All tasks" },
  { value: "denoise", label: "Denoise" },
  { value: "stem-separation", label: "Stem separation" },
  { value: "speech-to-text", label: "Speech-to-text" },
  { value: "text-to-speech", label: "Text-to-speech" },
  { value: "voice-conversion", label: "Voice conversion" },
];

export default function ModelBrowser({ open, onClose, onSelectModel }: Props) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"search" | "recommend">("search");
  const [taskType, setTaskType] = useState("");
  const [commercialOnly, setCommercialOnly] = useState(false);
  const [models, setModels] = useState<ModelCard[]>([]);
  const [recommendations, setRecommendations] = useState<Array<{ model: ModelCard; rationale: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [installing, setInstalling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<InstallRecovery | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setRecovery(null);
    try {
      const filters = {
        task_type: taskType || undefined,
        commercial_ok: commercialOnly ? true : undefined,
      };
      if (mode === "recommend" && query.trim()) {
        const data = await recommendModels(query, filters);
        setRecommendations(data.results);
        setModels([]);
      } else {
        const results = await searchModels(query, filters);
        setModels(results);
        setRecommendations([]);
      }
    } catch (err) {
      setModels([]);
      setRecommendations([]);
      setError(err instanceof Error ? err.message : "Model search failed");
    } finally {
      setLoading(false);
    }
  }, [query, mode, taskType, commercialOnly]);

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
          <h2>Model Browser</h2>
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
        </div>
        <input
          className="model-browser__search"
          placeholder={
            mode === "recommend"
              ? "Describe your task — e.g. commercial-friendly podcast denoise"
              : "Search models — denoise, stems, voice clone…"
          }
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <div className="model-browser__filters">
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
        </div>
      </div>
    </div>
  );
}
