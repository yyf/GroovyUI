import { useCallback, useEffect, useState } from "react";
import { API } from "../api";

type HealthPayload = Record<string, unknown>;

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; health: HealthPayload }
  | { kind: "offline"; error?: string };

function formatValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "boolean" || typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** API / health readout for the Inspector (replaces the old popup window). */
export default function ApiStatusPanel() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const refresh = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const res = await fetch(`${API}/api/health`);
      if (!res.ok) {
        setState({ kind: "offline", error: `HTTP ${res.status}` });
        return;
      }
      const health = (await res.json()) as HealthPayload;
      setState({ kind: "ok", health });
    } catch (err) {
      setState({
        kind: "offline",
        error: err instanceof Error ? err.message : "unreachable",
      });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const status =
    state.kind === "ok" ? String(state.health.status ?? "ok") : state.kind === "loading" ? "…" : "offline";
  const version =
    state.kind === "ok" ? String(state.health.groovy_version ?? "unknown") : "—";
  const statusOk = state.kind === "ok" && status === "ok";
  const extras =
    state.kind === "ok"
      ? Object.entries(state.health).filter(
          ([key]) => key !== "status" && key !== "groovy_version",
        )
      : [];

  return (
    <aside className="node-helper node-helper--about node-helper--api-status" aria-label="API status">
      <header className="node-helper__header">
        <h2>API status</h2>
        <button type="button" className="node-helper__header-action" onClick={() => void refresh()}>
          Refresh
        </button>
      </header>
      <div className="node-helper__scroll">
        <p className="about-panel__lede">Live connection to the GroovyUI backend.</p>
        {state.kind === "offline" ? (
          <p className="about-panel__body api-status-panel__hint">
            API is offline{state.error ? ` (${state.error})` : ""}. Start the server with{" "}
            <code>uv run --package groovy-server groovy-server</code> or{" "}
            <code>./scripts/dev.sh</code>. Studio expects <code>{API}</code>.
          </p>
        ) : null}
        <dl className="about-panel__meta api-status-panel__meta">
          <div className="about-panel__meta-row api-status-panel__row">
            <dt>Endpoint</dt>
            <dd>
              <code className="api-status-panel__code">{API}</code>
            </dd>
          </div>
          <div className="about-panel__meta-row api-status-panel__row">
            <dt>Status</dt>
            <dd className={statusOk ? "api-status-panel__ok" : "api-status-panel__bad"}>{status}</dd>
          </div>
          <div className="about-panel__meta-row api-status-panel__row">
            <dt>Version</dt>
            <dd>{version}</dd>
          </div>
          {extras.map(([key, value]) => (
            <div key={key} className="about-panel__meta-row api-status-panel__row">
              <dt>{key}</dt>
              <dd>{formatValue(value)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </aside>
  );
}
