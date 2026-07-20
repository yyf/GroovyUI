import { useCallback, useEffect, useState } from "react";
import {
  API,
  clearRenderCache,
  fetchStudioSettings,
  updateStudioSettings,
  type StudioSettings,
} from "../api";

type Props = {
  open: boolean;
  onClose: () => void;
  onSettingsChange?: (settings: StudioSettings) => void;
  onForceRebuildNext?: () => void;
};

async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

export default function SettingsDrawer({
  open,
  onClose,
  onSettingsChange,
  onForceRebuildNext,
}: Props) {
  const [studioSettings, setStudioSettings] = useState<StudioSettings | null>(null);
  const [hfTokenDraft, setHfTokenDraft] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const studio = await fetchStudioSettings();
      setStudioSettings(studio);
      onSettingsChange?.(studio);
      setHfTokenDraft("");
      setStatus("");
    } catch {
      setStudioSettings(null);
      setStatus("Could not load settings");
    } finally {
      setLoading(false);
    }
  }, [onSettingsChange]);

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

  const saveStudio = async (patch: {
    hf_token?: string | null;
    inference_mode?: "real" | "stub";
  }) => {
    try {
      const next = await updateStudioSettings(patch);
      setStudioSettings(next);
      onSettingsChange?.(next);
      setHfTokenDraft("");
      setStatus("Saved");
    } catch {
      setStatus("Could not save studio settings");
    }
  };

  const handleClearCache = async () => {
    try {
      const result = await clearRenderCache();
      setStatus(`Cleared ${result.removed} cache file${result.removed === 1 ? "" : "s"}`);
    } catch {
      setStatus("Could not clear render cache");
    }
  };

  if (!open) return null;

  const envLocksMode = studioSettings?.inference_effective_source === "environment";
  const stubActive = studioSettings?.inference_stub_active ?? false;

  return (
    <div className="compliance-backdrop" onClick={onClose}>
      <aside className="compliance-drawer settings-drawer" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Settings</h2>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="compliance-body">
          {loading && !studioSettings ? <p className="compliance-hint">Loading settings…</p> : null}
          {!loading && !studioSettings ? (
            <div className="settings-error">
              <p className="compliance-hint">{status || "Could not load settings."}</p>
              <button type="button" onClick={() => void refresh()}>
                Retry
              </button>
            </div>
          ) : null}

          {studioSettings ? (
            <>
              <section className="settings-section">
                <h3>Inference</h3>
                <p className="compliance-hint">
                  Real mode runs installed model weights. Stub mode uses lightweight DSP stand-ins for
                  UI and CI — not for judging model quality. Default is real.
                </p>
                <div className="settings-mode-toggle" role="group" aria-label="Inference mode">
                  <button
                    type="button"
                    className={`settings-mode-toggle__btn${
                      studioSettings.inference_mode === "real" ? " settings-mode-toggle__btn--active" : ""
                    }`}
                    disabled={envLocksMode}
                    onClick={() => void saveStudio({ inference_mode: "real" })}
                  >
                    Real
                  </button>
                  <button
                    type="button"
                    className={`settings-mode-toggle__btn${
                      studioSettings.inference_mode === "stub" ? " settings-mode-toggle__btn--active" : ""
                    }`}
                    disabled={envLocksMode}
                    onClick={() => void saveStudio({ inference_mode: "stub" })}
                  >
                    Stub
                  </button>
                </div>
                {envLocksMode ? (
                  <p className="compliance-hint">
                    Locked by <code>GROOVY_INFERENCE_STUB</code> → effective{" "}
                    <strong>{studioSettings.inference_effective}</strong>.
                  </p>
                ) : stubActive ? (
                  <p className="compliance-hint settings-hint--stub">
                    Stub inference is on — renders will not use real model weights.
                  </p>
                ) : (
                  <p className="compliance-hint">
                    Real inference — missing models or runtimes block render (no silent stub).
                  </p>
                )}
              </section>

              <section className="settings-section">
                <h3>Model installs</h3>
                <p className="compliance-hint">
                  Hugging Face token for gated model weights. Environment variable{" "}
                  <code>HF_TOKEN</code> takes precedence over this field.
                </p>
                {studioSettings.hf_token_source === "environment" ? (
                  <p className="compliance-hint">Using HF_TOKEN from environment.</p>
                ) : studioSettings.hf_token_set ? (
                  <p className="compliance-hint">Token saved in project settings.</p>
                ) : (
                  <p className="compliance-hint">No token configured — gated downloads may fail.</p>
                )}
                <label className="settings-field">
                  HF token
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder={studioSettings.hf_token_set ? "••••••••  (leave blank to keep)" : "hf_…"}
                    value={hfTokenDraft}
                    onChange={(event) => setHfTokenDraft(event.target.value)}
                  />
                </label>
                <div className="model-card__actions">
                  <button
                    type="button"
                    disabled={!hfTokenDraft.trim()}
                    onClick={() => void saveStudio({ hf_token: hfTokenDraft.trim() })}
                  >
                    Save token
                  </button>
                  {studioSettings.hf_token_set && studioSettings.hf_token_source !== "environment" ? (
                    <button type="button" onClick={() => void saveStudio({ hf_token: null })}>
                      Clear token
                    </button>
                  ) : null}
                </div>
              </section>

              <section className="settings-section">
                <h3>Developer</h3>
                <p className="compliance-hint">
                  Project and render-cache paths for this workspace. Force rebuild skips the PCM cache
                  on the next render only.
                </p>
                <label className="settings-field">
                  Project
                  <div className="settings-path-row">
                    <code className="settings-path">{studioSettings.project_dir}</code>
                    <button
                      type="button"
                      onClick={() =>
                        void copyText(studioSettings.project_dir).then((ok) =>
                          setStatus(ok ? "Copied project path" : "Copy failed"),
                        )
                      }
                    >
                      Copy
                    </button>
                  </div>
                </label>
                <label className="settings-field">
                  Render cache
                  <div className="settings-path-row">
                    <code className="settings-path">{studioSettings.cache_dir}</code>
                    <button
                      type="button"
                      onClick={() =>
                        void copyText(studioSettings.cache_dir).then((ok) =>
                          setStatus(ok ? "Copied cache path" : "Copy failed"),
                        )
                      }
                    >
                      Copy
                    </button>
                  </div>
                </label>
                <div className="model-card__actions">
                  <button
                    type="button"
                    onClick={() => {
                      onForceRebuildNext?.();
                      setStatus("Next render will force rebuild");
                    }}
                  >
                    Force rebuild next render
                  </button>
                  <button type="button" onClick={() => void handleClearCache()}>
                    Clear render cache
                  </button>
                  <button
                    type="button"
                    onClick={() => window.open(`${API}${studioSettings.nodes_schema_url}`, "_blank")}
                  >
                    Open node schema
                  </button>
                </div>
              </section>
            </>
          ) : null}

          {status && studioSettings ? (
            <p
              className={`settings-status${
                status === "Saved" ||
                status.startsWith("Copied") ||
                status.startsWith("Cleared") ||
                status.startsWith("Next")
                  ? ""
                  : " settings-status--warn"
              }`}
            >
              {status}
            </p>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
