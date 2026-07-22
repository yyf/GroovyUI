import { useCallback, useEffect, useState } from "react";
import {
  API,
  clearActivationDiagnostics,
  clearRenderCache,
  fetchActivationDiagnostics,
  fetchC2paStatus,
  fetchStudioSettings,
  updateStudioSettings,
  type StudioSettings,
} from "../api";
import type { ActivationDiagnosticsSummary, C2paStatus } from "../types";

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

function formatElapsed(elapsedMs: number): string {
  const seconds = Math.round(elapsedMs / 1000);
  const minutes = Math.floor(seconds / 60);
  return minutes > 0 ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
}

function stageDuration(
  summary: ActivationDiagnosticsSummary["latest_session"],
  startEvent: string,
  endEvent: string,
): number | null {
  if (!summary) return null;
  const start = summary.milestones.find(
    (milestone) => milestone.event === startEvent,
  );
  const end = [...summary.milestones]
    .reverse()
    .find((milestone) => milestone.event === endEvent);
  if (!start || !end || end.elapsed_ms < start.elapsed_ms) return null;
  return end.elapsed_ms - start.elapsed_ms;
}

export default function SettingsDrawer({
  open,
  onClose,
  onSettingsChange,
  onForceRebuildNext,
}: Props) {
  const [studioSettings, setStudioSettings] = useState<StudioSettings | null>(null);
  const [c2paStatus, setC2paStatus] = useState<C2paStatus | null>(null);
  const [activationDiagnostics, setActivationDiagnostics] =
    useState<ActivationDiagnosticsSummary | null>(null);
  const [hfTokenDraft, setHfTokenDraft] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [studio, credentials, diagnostics] = await Promise.all([
        fetchStudioSettings(),
        fetchC2paStatus(),
        fetchActivationDiagnostics(),
      ]);
      setStudioSettings(studio);
      setC2paStatus(credentials);
      setActivationDiagnostics(diagnostics);
      onSettingsChange?.(studio);
      setHfTokenDraft("");
      setStatus("");
    } catch {
      setStudioSettings(null);
      setC2paStatus(null);
      setActivationDiagnostics(null);
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
    content_credentials_mode?: "off" | "sign_if_configured" | "required";
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

  const handleClearActivationDiagnostics = async () => {
    try {
      await clearActivationDiagnostics();
      setActivationDiagnostics((current) =>
        current
          ? {
              ...current,
              session_count: 0,
              event_count: 0,
              latest_session: null,
            }
          : current,
      );
      setStatus("Cleared activation diagnostics");
    } catch {
      setStatus("Could not clear activation diagnostics");
    }
  };

  if (!open) return null;

  const envLocksMode = studioSettings?.inference_effective_source === "environment";
  const envLocksCredentials =
    studioSettings?.content_credentials_effective_source === "environment";
  const stubActive = studioSettings?.inference_stub_active ?? false;
  const latestDiagnostics = activationDiagnostics?.latest_session ?? null;
  const installDuration = stageDuration(
    latestDiagnostics,
    "install_started",
    "install_completed",
  );
  const renderDuration = stageDuration(
    latestDiagnostics,
    "render_started",
    "render_completed",
  );
  const playbackDelay = stageDuration(
    latestDiagnostics,
    "playback_requested",
    "playback_started",
  );

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
                <h3>Content Credentials</h3>
                <p className="compliance-hint">
                  Optional C2PA signing at the SaveAudio boundary. Provenance JSON remains the default;
                  exports are never silently claimed as signed.
                </p>
                <div
                  className="settings-mode-toggle"
                  role="group"
                  aria-label="Content Credentials mode"
                >
                  <button
                    type="button"
                    className={`settings-mode-toggle__btn${
                      studioSettings.content_credentials_mode === "off"
                        ? " settings-mode-toggle__btn--active"
                        : ""
                    }`}
                    disabled={envLocksCredentials}
                    onClick={() => void saveStudio({ content_credentials_mode: "off" })}
                  >
                    Off
                  </button>
                  <button
                    type="button"
                    className={`settings-mode-toggle__btn${
                      studioSettings.content_credentials_mode === "sign_if_configured"
                        ? " settings-mode-toggle__btn--active"
                        : ""
                    }`}
                    disabled={envLocksCredentials}
                    onClick={() =>
                      void saveStudio({ content_credentials_mode: "sign_if_configured" })
                    }
                  >
                    Sign if configured
                  </button>
                </div>
                {envLocksCredentials ? (
                  <p className="compliance-hint">
                    Locked by <code>GROOVY_C2PA_MODE</code> → effective{" "}
                    <strong>{studioSettings.content_credentials_effective}</strong>.
                  </p>
                ) : c2paStatus?.configured ? (
                  <p className="compliance-hint">
                    Signer configured: <strong>{c2paStatus.provider}</strong>. Every signed export is
                    verified before it is published.
                  </p>
                ) : (
                  <p className="compliance-hint">
                    No signer configured.{" "}
                    {studioSettings.content_credentials_effective === "sign_if_configured"
                      ? "Exports remain unsigned and are labeled unconfigured."
                      : "Exports remain unsigned with a Provenance 1.1 sidecar."}
                  </p>
                )}
              </section>

              <section className="settings-section">
                <h3>First-audition diagnostics</h3>
                <p className="compliance-hint">
                  Local-only timing from task start to actual audible playback. Prompts, audio,
                  filenames, paths, and tokens are never recorded or uploaded.
                </p>
                {activationDiagnostics?.latest_session ? (
                  <div className="settings-diagnostic-summary">
                    <span>
                      Last run:{" "}
                      <strong>{activationDiagnostics.latest_session.outcome}</strong>
                    </span>
                    <span>
                      {activationDiagnostics.latest_session.time_to_first_audible_ms != null
                        ? `First audible preview in ${formatElapsed(
                            activationDiagnostics.latest_session
                              .time_to_first_audible_ms,
                          )}`
                        : `Elapsed ${formatElapsed(
                            activationDiagnostics.latest_session.elapsed_ms,
                          )}`}
                    </span>
                    <span>
                      {activationDiagnostics.session_count} local session
                      {activationDiagnostics.session_count === 1 ? "" : "s"}
                    </span>
                    {installDuration != null ? (
                      <span>Model installation: {formatElapsed(installDuration)}</span>
                    ) : null}
                    {renderDuration != null ? (
                      <span>Preview render: {formatElapsed(renderDuration)}</span>
                    ) : null}
                    {playbackDelay != null ? (
                      <span>Playback readiness: {formatElapsed(playbackDelay)}</span>
                    ) : null}
                  </div>
                ) : (
                  <p className="compliance-hint">
                    No first-audition session has been recorded yet.
                  </p>
                )}
                {activationDiagnostics ? (
                  <label className="settings-field">
                    Local trace
                    <div className="settings-path-row">
                      <code className="settings-path">
                        {activationDiagnostics.path}
                      </code>
                      <button
                        type="button"
                        onClick={() =>
                          void copyText(activationDiagnostics.path).then((ok) =>
                            setStatus(
                              ok ? "Copied diagnostics path" : "Copy failed",
                            ),
                          )
                        }
                      >
                        Copy
                      </button>
                    </div>
                  </label>
                ) : null}
                <div className="model-card__actions">
                  <button
                    type="button"
                    disabled={!activationDiagnostics?.latest_session}
                    onClick={() => {
                      const latest = activationDiagnostics?.latest_session;
                      if (!latest) return;
                      void copyText(JSON.stringify(latest, null, 2)).then((ok) =>
                        setStatus(
                          ok ? "Copied activation report" : "Copy failed",
                        ),
                      );
                    }}
                  >
                    Copy latest report
                  </button>
                  <button
                    type="button"
                    disabled={!activationDiagnostics?.session_count}
                    onClick={() => void handleClearActivationDiagnostics()}
                  >
                    Clear history
                  </button>
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
