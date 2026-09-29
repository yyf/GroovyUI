import { useCallback, useEffect, useState } from "react";
import {
  clearActivationDiagnostics,
  clearInstalledModels,
  clearRenderCache,
  fetchActivationDiagnostics,
  fetchC2paStatus,
  fetchInstalledModels,
  fetchStudioSettings,
  fetchSystemCapabilities,
  removeModelInstall,
  revealHfCache,
  updateStudioSettings,
  type InstalledModelRow,
  type StudioSettings,
} from "../api";
import { buildCleanMachineReport } from "../cleanMachineReport";
import { displayProjectPath } from "../displayProjectPath";
import type { ActivationDiagnosticsSummary, C2paStatus } from "../types";

type Props = {
  onSettingsChange?: (settings: StudioSettings) => void;
  onForceRebuildNext?: () => void;
};

type SystemCapabilities = Awaited<ReturnType<typeof fetchSystemCapabilities>>;

async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

function formatInstalledSize(model: InstalledModelRow): string {
  if (model.size_label?.trim()) return model.size_label.trim();
  if (typeof model.size_mb === "number" && model.size_mb > 0) {
    return `${model.size_mb} MB`;
  }
  if (typeof model.size_bytes === "number" && model.size_bytes > 0) {
    if (model.size_bytes >= 1024 * 1024) {
      return `${(model.size_bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    if (model.size_bytes >= 1024) {
      return `${Math.round(model.size_bytes / 1024)} KB`;
    }
    return `${model.size_bytes} B`;
  }
  return "size unknown";
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

/** Studio settings for the Inspector (same surface as About / API status). */
export default function SettingsDrawer({
  onSettingsChange,
  onForceRebuildNext,
}: Props) {
  const [studioSettings, setStudioSettings] = useState<StudioSettings | null>(null);
  const [c2paStatus, setC2paStatus] = useState<C2paStatus | null>(null);
  const [activationDiagnostics, setActivationDiagnostics] =
    useState<ActivationDiagnosticsSummary | null>(null);
  const [capabilities, setCapabilities] = useState<SystemCapabilities | null>(null);
  const [installedModels, setInstalledModels] = useState<InstalledModelRow[]>([]);
  const [modelsUsedMb, setModelsUsedMb] = useState<number | null>(null);
  const [modelsDir, setModelsDir] = useState<string | null>(null);
  const [modelsBusy, setModelsBusy] = useState(false);
  const [removingModelId, setRemovingModelId] = useState<string | null>(null);
  const [hfTokenDraft, setHfTokenDraft] = useState("");
  const [anthropicKeyDraft, setAnthropicKeyDraft] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  const refreshInstalledModels = useCallback(async () => {
    try {
      const installed = await fetchInstalledModels();
      setInstalledModels(installed.models);
      setModelsUsedMb(installed.models_used_mb);
      setModelsDir(installed.models_dir);
    } catch {
      setInstalledModels([]);
      setModelsUsedMb(null);
      setModelsDir(null);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [studio, credentials, diagnostics, caps] = await Promise.all([
        fetchStudioSettings(),
        fetchC2paStatus(),
        fetchActivationDiagnostics(),
        fetchSystemCapabilities().catch(() => null),
      ]);
      setStudioSettings(studio);
      setC2paStatus(credentials);
      setActivationDiagnostics(diagnostics);
      setCapabilities(caps);
      onSettingsChange?.(studio);
      setHfTokenDraft("");
      setAnthropicKeyDraft("");
      setStatus("");
      await refreshInstalledModels();
    } catch {
      setStudioSettings(null);
      setC2paStatus(null);
      setActivationDiagnostics(null);
      setCapabilities(null);
      setStatus("Could not load settings");
    } finally {
      setLoading(false);
    }
  }, [onSettingsChange, refreshInstalledModels]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const saveStudio = async (patch: {
    hf_token?: string | null;
    anthropic_api_key?: string | null;
    inference_mode?: "real" | "stub";
    content_credentials_mode?: "off" | "sign_if_configured" | "required";
  }) => {
    try {
      const next = await updateStudioSettings(patch);
      setStudioSettings(next);
      onSettingsChange?.(next);
      setHfTokenDraft("");
      setAnthropicKeyDraft("");
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

  const handleRemoveInstalledModel = async (model: InstalledModelRow) => {
    const confirmed = window.confirm(
      `Remove Groovy install entry for “${model.name}”? Deletes files under .groovy/models only — not the Hugging Face cache. Shared Python packages stay installed.`,
    );
    if (!confirmed) return;
    setRemovingModelId(model.id);
    try {
      const result = await removeModelInstall(model.id);
      await Promise.all([
        refreshInstalledModels(),
        fetchSystemCapabilities()
          .then(setCapabilities)
          .catch(() => null),
      ]);
      setStatus(
        result.freed_mb > 0
          ? `Removed ${model.name} (~${result.freed_mb} MB freed).`
          : `Removed ${model.name} install record.`,
      );
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not remove model");
    } finally {
      setRemovingModelId(null);
    }
  };

  const handleClearAllInstalledModels = async () => {
    const removable = installedModels.filter((model) => model.can_remove);
    if (!removable.length) {
      setStatus("No removable model installs");
      return;
    }
    const totalMb = Math.round(
      removable.reduce((sum, model) => sum + (Number(model.size_mb) || 0), 0),
    );
    const confirmed = window.confirm(
      `Remove all ${removable.length} installed model${removable.length === 1 ? "" : "s"}` +
        (totalMb > 0 ? ` (~${totalMb} MB)` : "") +
        "? Weight files are deleted. Shared Python packages stay installed.",
    );
    if (!confirmed) return;
    setModelsBusy(true);
    try {
      const result = await clearInstalledModels();
      await Promise.all([
        refreshInstalledModels(),
        fetchSystemCapabilities()
          .then(setCapabilities)
          .catch(() => null),
      ]);
      const skipped = result.skipped.length;
      setStatus(
        skipped > 0
          ? `Removed ${result.removed.length} model(s) (~${result.freed_mb} MB). Skipped ${skipped} in-progress install(s).`
          : `Removed ${result.removed.length} model(s) (~${result.freed_mb} MB freed).`,
      );
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not clear installed models");
    } finally {
      setModelsBusy(false);
    }
  };

  const handleOpenHfCache = async () => {
    try {
      const result = await revealHfCache();
      setStatus(`Opened HF cache: ${result.path}`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not open HF cache");
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
    <aside className="node-helper node-helper--about node-helper--settings" aria-label="Studio settings">
      <header className="node-helper__header">
        <h2>Studio settings</h2>
      </header>
      <div className="node-helper__scroll settings-panel__scroll">
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

                <h4 className="settings-subsection-title">Plan / Claude</h4>
                <p className="compliance-hint">
                  Anthropic API key for Model Plan (model picks in the browser) and Generate-by-LLM (graph
                  drafts). Environment variable <code>ANTHROPIC_API_KEY</code> takes precedence. Prefer env
                  over saving in the project file. Keys never leave this machine except to api.anthropic.com.
                </p>
                {studioSettings.anthropic_api_key_source === "environment" ? (
                  <p className="compliance-hint">Using ANTHROPIC_API_KEY from environment.</p>
                ) : studioSettings.anthropic_api_key_set ? (
                  <p className="compliance-hint">Key saved in project settings (.groovy/, gitignored).</p>
                ) : (
                  <p className="compliance-hint">
                    No Claude key — Model Plan falls back to deterministic recommendations; Generate (⌘G)
                    stays locked until a key is set. Bundled templates: Model Browser → Suggest workflow.
                  </p>
                )}
                <label className="settings-field">
                  Anthropic API key
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder={
                      studioSettings.anthropic_api_key_set
                        ? "••••••••  (leave blank to keep)"
                        : "sk-ant-…"
                    }
                    value={anthropicKeyDraft}
                    onChange={(event) => setAnthropicKeyDraft(event.target.value)}
                  />
                </label>
                <div className="model-card__actions">
                  <button
                    type="button"
                    disabled={!anthropicKeyDraft.trim()}
                    onClick={() => void saveStudio({ anthropic_api_key: anthropicKeyDraft.trim() })}
                  >
                    Save Claude key
                  </button>
                  {studioSettings.anthropic_api_key_set &&
                  studioSettings.anthropic_api_key_source !== "environment" ? (
                    <button type="button" onClick={() => void saveStudio({ anthropic_api_key: null })}>
                      Clear Claude key
                    </button>
                  ) : null}
                </div>

                <h4 className="settings-subsection-title">Installed models</h4>
                <p className="compliance-hint">
                  Local weight files under{" "}
                  <code>
                    {displayProjectPath(
                      modelsDir ?? `${studioSettings.project_dir}/.groovy/models`,
                      studioSettings.project_dir,
                    )}
                  </code>
                  {modelsUsedMb != null ? (
                    <>
                      {" "}
                      (~
                      <strong>{Math.round(modelsUsedMb)} MB</strong> in this folder)
                    </>
                  ) : null}
                  . Many models only keep a small marker here; size then shows a catalog estimate
                  for HF cache / package weights. Remove clears the Groovy install record (+ any
                  files in this folder); shared Python packages and the HF cache stay unless you
                  clean those separately. Reinstall from Model Browser (Cmd+K).
                </p>
                {installedModels.length === 0 ? (
                  <p className="compliance-hint">No local model installs yet.</p>
                ) : (
                  <ul className="settings-installed-list" aria-label="Installed models">
                    {installedModels.map((model) => {
                      const removing = removingModelId === model.id;
                      return (
                        <li key={model.id} className="settings-installed-row">
                          <label className="settings-installed-toggle">
                            <input
                              type="checkbox"
                              checked
                              disabled={!model.can_remove || modelsBusy || removing}
                              aria-label={`Keep ${model.name} installed`}
                              onChange={() => {
                                if (!model.can_remove || modelsBusy || removing) return;
                                void handleRemoveInstalledModel(model);
                              }}
                            />
                            <span className="settings-installed-meta">
                              <span className="settings-installed-name">{model.name}</span>
                              <span className="settings-installed-detail">
                                {model.id} · {model.install_status} · {formatInstalledSize(model)}
                                {!model.can_remove ? " · in progress" : ""}
                              </span>
                            </span>
                          </label>
                          <div className="settings-installed-actions">
                            <button
                              type="button"
                              className="settings-installed-remove"
                              disabled={!model.can_remove || modelsBusy || removing}
                              onClick={() => void handleRemoveInstalledModel(model)}
                            >
                              {removing ? "Removing…" : "Remove entry"}
                            </button>
                            <button
                              type="button"
                              className="settings-installed-hf"
                              title="Open shared Hugging Face cache folder to delete weights manually"
                              disabled={modelsBusy}
                              onClick={() => void handleOpenHfCache()}
                            >
                              HF cache
                            </button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
                <div className="model-card__actions">
                  <button
                    type="button"
                    disabled={
                      modelsBusy ||
                      removingModelId != null ||
                      !installedModels.some((model) => model.can_remove)
                    }
                    onClick={() => void handleClearAllInstalledModels()}
                  >
                    {modelsBusy ? "Removing…" : "Remove all installed models"}
                  </button>
                  <button
                    type="button"
                    disabled={modelsBusy || removingModelId != null}
                    onClick={() =>
                      void refreshInstalledModels().then(() =>
                        setStatus("Refreshed installed models"),
                      )
                    }
                  >
                    Refresh list
                  </button>
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
                  Local-only timing from task start to audible playback, plus a live machine
                  snapshot for clean-machine / user-run comparison. Prompts, audio, filenames,
                  paths, and tokens are never recorded or uploaded.
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
                {capabilities ? (
                  <div className="settings-diagnostic-summary" aria-label="Machine snapshot">
                    <span>
                      Inference:{" "}
                      <strong>{capabilities.inference_effective}</strong>
                      {capabilities.inference_stub_active ? " (stub active)" : ""}
                    </span>
                    <span>
                      Disk free: {Math.round(capabilities.machine.disk_free_mb)} MB
                    </span>
                    <span>
                      Models on disk:{" "}
                      {Math.round(capabilities.machine.models_used_mb ?? 0)} MB
                    </span>
                    <span>
                      VRAM free:{" "}
                      {capabilities.machine.vram_available_gb != null
                        ? `${capabilities.machine.vram_available_gb} GB`
                        : "unmeasured"}
                      {capabilities.machine.torch_cuda_available ? " · CUDA" : " · CPU"}
                    </span>
                    <span>
                      RAM free:{" "}
                      {capabilities.machine.ram_available_gb != null
                        ? `${capabilities.machine.ram_available_gb} GB`
                        : "unmeasured"}
                    </span>
                  </div>
                ) : null}
                {activationDiagnostics ? (
                  <label className="settings-field">
                    Local trace
                    <div className="settings-path-row">
                      <code className="settings-path">
                        {displayProjectPath(
                          activationDiagnostics.path,
                          studioSettings.project_dir,
                        )}
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
                    disabled={!activationDiagnostics?.latest_session && !capabilities}
                    onClick={() => {
                      const report = buildCleanMachineReport({
                        diagnostics: activationDiagnostics
                          ? {
                              ...activationDiagnostics,
                              path: displayProjectPath(
                                activationDiagnostics.path,
                                studioSettings.project_dir,
                              ),
                            }
                          : null,
                        capabilities,
                      });
                      void copyText(JSON.stringify(report, null, 2)).then((ok) =>
                        setStatus(
                          ok ? "Copied clean-machine report" : "Copy failed",
                        ),
                      );
                    }}
                  >
                    Copy clean-machine report
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
                    <code className="settings-path">
                      {displayProjectPath(
                        studioSettings.project_dir,
                        studioSettings.project_dir,
                      )}
                    </code>
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
                    <code className="settings-path">
                      {displayProjectPath(
                        studioSettings.cache_dir,
                        studioSettings.project_dir,
                      )}
                    </code>
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
                {capabilities ? (
                  <p className="compliance-hint">
                    Model weights use{" "}
                    <strong>{Math.round(capabilities.machine.models_used_mb ?? 0)} MB</strong>
                    {" · "}
                    <strong>{Math.round(capabilities.machine.disk_free_mb)} MB</strong> free on
                    the project volume. Remove unused models under{" "}
                    <strong>Model installs</strong> above, or clear the render cache below.
                  </p>
                ) : null}
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
  );
}
