import { useCallback, useEffect, useState } from "react";
import { installModel, searchModels } from "../api";
import type { ModelCard } from "../types";

type Props = {
  open: boolean;
  onClose: () => void;
  onSelectModel?: (modelId: string) => void;
};

export default function ModelBrowser({ open, onClose, onSelectModel }: Props) {
  const [query, setQuery] = useState("");
  const [models, setModels] = useState<ModelCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [installing, setInstalling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (q: string) => {
    setLoading(true);
    setError(null);
    try {
      const results = await searchModels(q);
      setModels(results);
    } catch (err) {
      setModels([]);
      setError(err instanceof Error ? err.message : "Model search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void refresh(query);
  }, [open, query, refresh]);

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
    try {
      await installModel(modelId);
      await refresh(query);
    } finally {
      setInstalling(null);
    }
  };

  return (
    <div className="model-browser-backdrop" onClick={onClose}>
      <div className="model-browser" onClick={(e) => e.stopPropagation()}>
        <header className="model-browser__header">
          <h2>Model Browser</h2>
          <button type="button" className="model-browser__close" onClick={onClose}>
            ✕
          </button>
        </header>
        <input
          className="model-browser__search"
          placeholder="Search models — e.g. denoise, voice clone, stems"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <div className="model-browser__list">
          {loading ? <p className="model-browser__hint">Searching…</p> : null}
          {error ? (
            <p className="model-browser__error">
              {error}. Restart the API server after upgrading:{" "}
              <code>uv run --package groovy-server groovy-server</code>
            </p>
          ) : null}
          {!loading && !error && models.length === 0 ? (
            <p className="model-browser__hint">No models found.</p>
          ) : null}
          {models.map((model) => (
            <article key={model.id} className="model-card">
              <div className="model-card__row">
                <strong>{model.name}</strong>
                <span className={`pill pill--${model.install_status}`}>{model.install_status}</span>
              </div>
              <p className="model-card__desc">{model.description}</p>
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
