import { useEffect, useMemo, useState } from "react";
import {
  downloadComplianceReport,
  fetchAuthenticity,
  fetchLicenseScan,
  fetchProvenance,
  findMissingWorkflowModels,
} from "../api";
import type { FastPathRunResult } from "../fastPath";
import type {
  JobOutput,
  LicenseScanSummary,
  ProvenanceSummary,
  Workflow,
} from "../types";

type Tab = "license" | "provenance" | "authenticity" | "disclosure";
export type ComplianceIntent = "commercial" | "evaluation";

export function fastPathBlockReason(
  license: LicenseScanSummary | null,
  intent: ComplianceIntent,
): string | null {
  if (!license) return "Compliance scan is still loading.";
  if (license.flags.some((flag) => flag.code === "UNKNOWN_MODEL")) {
    return "Resolve unknown model references before continuing.";
  }
  if (intent === "commercial" && !license.scan_ok) {
    return "Choose a commercial-safe alternative for each flagged model, or switch to evaluation use.";
  }
  const diskShort = license.preflight?.checks?.find(
    (check) => check.code === "DISK_SHORT" && check.severity === "error",
  );
  if (diskShort) {
    return diskShort.message;
  }
  return null;
}

type Props = {
  open: boolean;
  workflow: Workflow;
  outputs?: Record<string, JobOutput>;
  targetNodeId?: string | null;
  onClose: () => void;
  onBrowseModels?: (opts: { nodeType?: string; commercialOnly?: boolean; query?: string }) => void;
  onApplyModelSwap?: (nodeId: string, modelId: string) => void;
  onApplyModelSwaps?: (swaps: Array<{ nodeId: string; modelId: string }>) => void;
  fastPath?: boolean;
  onInstallRenderAudition?: () => Promise<FastPathRunResult>;
  onCancelInstall?: () => void;
};

export default function ComplianceDrawer({
  open,
  workflow,
  outputs,
  targetNodeId,
  onClose,
  onBrowseModels,
  onApplyModelSwap,
  onApplyModelSwaps,
  fastPath = false,
  onInstallRenderAudition,
  onCancelInstall,
}: Props) {
  const [tab, setTab] = useState<Tab>("license");
  const [license, setLicense] = useState<LicenseScanSummary | null>(null);
  const [provenance, setProvenance] = useState<ProvenanceSummary | null>(null);
  const [authenticity, setAuthenticity] = useState<Record<string, unknown> | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [intent, setIntent] = useState<ComplianceIntent>("commercial");
  const [missingModelCount, setMissingModelCount] = useState(0);
  const [fastPathBusy, setFastPathBusy] = useState(false);
  const [fastPathStopping, setFastPathStopping] = useState(false);
  const [fastPathResult, setFastPathResult] = useState<string | null>(null);
  const [fastPathError, setFastPathError] = useState<string | null>(null);

  const authenticityId = useMemo(() => {
    if (!outputs) return null;
    const focus = targetNodeId && outputs[targetNodeId]?.authenticity_id;
    if (focus) return focus;
    for (const out of Object.values(outputs)) {
      if (out.authenticity_id) return out.authenticity_id;
    }
    return null;
  }, [outputs, targetNodeId]);

  useEffect(() => {
    if (!open) return;
    fetchLicenseScan(workflow)
      .then(setLicense)
      .catch(() => setLicense(null));
  }, [open, workflow]);

  useEffect(() => {
    if (!open || !fastPath) {
      setMissingModelCount(0);
      return;
    }
    setTab("license");
    setFastPathError(null);
    setFastPathResult(null);
    findMissingWorkflowModels(workflow)
      .then((models) => setMissingModelCount(models.length))
      .catch(() => setMissingModelCount(0));
  }, [fastPath, open, workflow]);

  useEffect(() => {
    if (!open || !outputs || Object.keys(outputs).length === 0) {
      setProvenance(null);
      return;
    }
    fetchProvenance(workflow, outputs, targetNodeId)
      .then(setProvenance)
      .catch(() => setProvenance(null));
  }, [open, workflow, outputs, targetNodeId]);

  useEffect(() => {
    if (!open || !authenticityId) {
      setAuthenticity(null);
      return;
    }
    fetchAuthenticity(authenticityId)
      .then(setAuthenticity)
      .catch(() => setAuthenticity(null));
  }, [open, authenticityId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const copyDisclosure = () => {
    const text = provenance?.focus_disclosure ?? "Render the workflow to generate disclosure text.";
    void navigator.clipboard.writeText(text);
  };

  const copyAuthenticity = () => {
    if (authenticity) void navigator.clipboard.writeText(JSON.stringify(authenticity, null, 2));
  };

  const downloadReport = async () => {
    setReportBusy(true);
    setReportError(null);
    try {
      const blob = await downloadComplianceReport(workflow, {
        outputs,
        targetNodeId: targetNodeId,
      });
      const slug = (workflow.metadata?.title || workflow.id)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 60);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `groovy-compliance-${slug || "workflow"}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "Failed to export PDF");
    } finally {
      setReportBusy(false);
    }
  };

  const overall = authenticity?.overall as { label?: string; confidence?: number; summary?: string } | undefined;
  const provCheck = authenticity?.provenance_check as Record<string, unknown> | undefined;
  const mlDet = authenticity?.ml_detection as Record<string, unknown> | undefined;
  const blockReason = fastPathBlockReason(license, intent);
  const intentBlocked = blockReason != null;
  const optimizationPlan = license?.optimization_plan;
  const preflight = license?.preflight;
  const runFastPath = async () => {
    if (!onInstallRenderAudition || intentBlocked) return;
    setFastPathBusy(true);
    setFastPathStopping(false);
    setFastPathResult(null);
    setFastPathError(null);
    try {
      const result = await onInstallRenderAudition();
      if (result === "cancelled") {
        setFastPathResult("Stopped safely after the current model. Render did not start.");
      }
    } catch (err) {
      setFastPathError(err instanceof Error ? err.message : "Install or render failed");
    } finally {
      setFastPathBusy(false);
    }
  };

  return (
    <div className="compliance-backdrop" onClick={onClose}>
      <aside className="compliance-drawer" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Compliance</h2>
          {provenance?.contains_ai ? <span className="pill pill--warning">AI</span> : null}
          {overall?.label ? <span className={`pill pill--${overall.label}`}>{overall.label}</span> : null}
          <button
            type="button"
            className="compliance-export"
            onClick={() => void downloadReport()}
            disabled={reportBusy || !license}
          >
            {reportBusy ? "Exporting…" : "Download PDF"}
          </button>
          <button type="button" onClick={onClose}>
            ✕
          </button>
        </header>
        {reportError ? <p className="compliance-hint compliance-hint--error">{reportError}</p> : null}
        <nav>
          <button type="button" className={tab === "license" ? "active" : ""} onClick={() => setTab("license")}>
            License
          </button>
          <button type="button" className={tab === "provenance" ? "active" : ""} onClick={() => setTab("provenance")}>
            Provenance
          </button>
          <button type="button" className={tab === "authenticity" ? "active" : ""} onClick={() => setTab("authenticity")}>
            Authenticity
          </button>
          <button type="button" className={tab === "disclosure" ? "active" : ""} onClick={() => setTab("disclosure")}>
            Disclosure
          </button>
        </nav>
        {tab === "license" && license ? (
          <div className="compliance-body">
            {fastPath ? (
              <section className="compliance-preflight" aria-label="Pre-install compliance review">
                <div className="compliance-preflight__heading">
                  <div>
                    <span className="compliance-preflight__eyebrow">Pre-install review</span>
                    <h3>Choose a licensing strategy</h3>
                  </div>
                  <span className="pill">Registry metadata only</span>
                </div>
                <p className="compliance-hint">
                  No model weights have been downloaded and no inference has run.
                  Review the full chain, swap models if needed, then commit once.
                </p>
                <div className="compliance-intent" role="radiogroup" aria-label="Licensing intent">
                  <label>
                    <input
                      type="radio"
                      name="compliance-intent"
                      checked={intent === "commercial"}
                      onChange={() => setIntent("commercial")}
                    />
                    <span>
                      <strong>Commercial-safe</strong>
                      <small>Require every model to allow commercial use.</small>
                    </span>
                  </label>
                  <label>
                    <input
                      type="radio"
                      name="compliance-intent"
                      checked={intent === "evaluation"}
                      onChange={() => setIntent("evaluation")}
                    />
                    <span>
                      <strong>Evaluation / non-commercial</strong>
                      <small>Allow restricted models; warnings remain in the review.</small>
                    </span>
                  </label>
                </div>
                {intent === "commercial" && optimizationPlan?.swaps.length ? (
                  <section className="compliance-optimizer">
                    <div className="compliance-optimizer__heading">
                      <div>
                        <span className="compliance-preflight__eyebrow">License optimizer</span>
                        <h4>Most permissive compatible chain</h4>
                      </div>
                      <span className="pill pill--ready">
                        {optimizationPlan.swaps.length} replacement
                        {optimizationPlan.swaps.length === 1 ? "" : "s"}
                      </span>
                    </div>
                    <ul className="compliance-optimizer__plan">
                      {optimizationPlan.swaps.map((swap) => (
                        <li key={swap.node_id}>
                          <strong>{swap.node_type}</strong>
                          <code>{swap.from_model_id}</code>
                          <span>→</span>
                          <code>{swap.to_model_id}</code>
                          <span className="pill pill--ready">{swap.license_spdx}</span>
                        </li>
                      ))}
                    </ul>
                    {optimizationPlan.unresolved.length > 0 ? (
                      <p className="compliance-hint compliance-hint--error">
                        The full chain cannot be optimized automatically:{" "}
                        {optimizationPlan.unresolved.map((item) => item.node_id).join(", ")} has no cleared compatible alternative.
                      </p>
                    ) : null}
                    <button
                      type="button"
                      className="compliance-optimizer__apply"
                      disabled={
                        fastPathBusy ||
                        !optimizationPlan.can_optimize ||
                        !onApplyModelSwaps
                      }
                      onClick={() =>
                        onApplyModelSwaps?.(
                          optimizationPlan.swaps.map((swap) => ({
                            nodeId: swap.node_id,
                            modelId: swap.to_model_id,
                          })),
                        )
                      }
                    >
                      Confirm &amp; apply optimized chain
                    </button>
                  </section>
                ) : null}
                {preflight ? (
                  <section className="compliance-estimates" aria-label="Preflight estimates">
                    <div className="compliance-optimizer__heading">
                      <div>
                        <span className="compliance-preflight__eyebrow">Before you commit</span>
                        <h4>Preflight estimates</h4>
                      </div>
                      <span className="pill">Rough · offline</span>
                    </div>
                    <div className="compliance-estimates__grid">
                      <div>
                        <span>Missing download</span>
                        <strong>
                          {preflight.download.known_mb >= 1000
                            ? `~${(preflight.download.known_mb / 1000).toFixed(1)} GB`
                            : `~${Math.round(preflight.download.known_mb)} MB`}
                        </strong>
                        {preflight.download.unknown_models.length > 0 ? (
                          <small>
                            + {preflight.download.unknown_models.length} unestimated model
                            {preflight.download.unknown_models.length === 1 ? "" : "s"}
                          </small>
                        ) : null}
                      </div>
                      <div>
                        <span>Peak VRAM</span>
                        <strong>
                          {preflight.peak_vram_gb > 0
                            ? `~${preflight.peak_vram_gb} GB`
                            : "CPU / negligible"}
                        </strong>
                        <small>Peak, not sum (sequential executor)</small>
                      </div>
                      <div>
                        <span>Render · 1 min audio</span>
                        <strong>
                          ~{preflight.render_time.low_seconds}–{preflight.render_time.high_seconds}s
                        </strong>
                        <small>Hardware-agnostic range</small>
                      </div>
                    </div>
                    <p className="compliance-hint">{preflight.render_time.note}</p>
                    {preflight.checks && preflight.checks.length > 0 ? (
                      <ul className="compliance-machine-checks" aria-label="Machine checks">
                        {preflight.checks.map((check) => (
                          <li
                            key={check.code}
                            className={`compliance-machine-checks__item compliance-machine-checks__item--${check.severity}`}
                          >
                            <span className="pill">
                              {check.severity === "ok"
                                ? "OK"
                                : check.severity === "warning"
                                  ? "Warn"
                                  : "Block"}
                            </span>
                            <span>{check.message}</span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </section>
                ) : null}
                <div className="compliance-chain">
                  <h4>Chain preflight</h4>
                  {workflow.nodes.map((node) => {
                    const modelId =
                      typeof node.widgets.model === "string" ? node.widgets.model : null;
                    const modelRow = modelId
                      ? license.license_rows.find(
                          (row) => row.kind === "model" && row.component_id === modelId,
                        )
                      : null;
                    const nodeRow = license.license_rows.find(
                      (row) => row.kind === "node" && row.component_id === node.id,
                    );
                    const flagged = modelId != null && modelRow?.commercial_ok === false;
                    const swap = license.swap_suggestions.find((entry) => entry.node_id === node.id);
                    const alternatives = swap?.alternatives ?? [];
                    return (
                      <div
                        key={node.id}
                        className={`compliance-chain__node${flagged ? " compliance-chain__node--flagged" : ""}`}
                      >
                        <div>
                          <strong>{node.type}</strong>
                          <span className="node-helper__mono"> {node.id}</span>
                        </div>
                        <div className="compliance-chain__badges">
                          <span className={`pill ${flagged ? "pill--warning" : "pill--ready"}`}>
                            {modelRow?.license_spdx ?? nodeRow?.license_spdx ?? "Unknown license"}
                          </span>
                        </div>
                        <small>
                          {modelId ? `Model: ${modelId}` : "Built-in node; no model install required"}
                        </small>
                        {flagged ? (
                          <div className="compliance-chain__swap">
                            <span className="compliance-chain__swap-label">
                              Not cleared for commercial use — choose a cleared alternative:
                            </span>
                            {alternatives.length > 0 ? (
                              <div className="compliance-chain__alts">
                                {alternatives.map((alt) => (
                                  <button
                                    key={alt.model_id}
                                    type="button"
                                    className="compliance-chain__alt"
                                    title={`Replace ${modelId} with ${alt.model_id} (${alt.license_spdx})`}
                                    disabled={fastPathBusy || !onApplyModelSwap}
                                    onClick={() => onApplyModelSwap?.(node.id, alt.model_id)}
                                  >
                                    <span className="compliance-chain__alt-name">{alt.name}</span>
                                    <span className="compliance-chain__alt-license">{alt.license_spdx}</span>
                                  </button>
                                ))}
                              </div>
                            ) : (
                              <span className="compliance-chain__no-alt">
                                No cleared offline model for this node yet.
                              </span>
                            )}
                            {onBrowseModels ? (
                              <button
                                type="button"
                                className="compliance-chain__online"
                                disabled={fastPathBusy}
                                onClick={() =>
                                  onBrowseModels({
                                    nodeType: node.type,
                                    commercialOnly: true,
                                    query: swap?.alternatives?.[0]?.task_types?.[0] ?? node.type,
                                  })
                                }
                              >
                                Find online (cleared license) →
                              </button>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </section>
            ) : null}
            {license.warnings.length > 0 ? (
              <ul className="compliance-warnings">
                {license.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            ) : null}
            {license.flags.length > 0 ? (
              <ul className="compliance-warnings">
                {license.flags.map((flag) => (
                  <li key={`${flag.node_id}-${flag.code}`}>
                    <strong>{flag.node_id}</strong> — {flag.message}
                  </li>
                ))}
              </ul>
            ) : null}
            {!fastPath && license.swap_suggestions.length > 0 ? (
              <section className="compliance-swaps">
                <h3>Commercial-safe alternatives</h3>
                {license.swap_suggestions.map((swap) => (
                  <div key={swap.node_id} className="compliance-swap">
                    <p>
                      <strong>{swap.node_type}</strong> ({swap.node_id}) uses{" "}
                      <code>{swap.current_model_id}</code> ({swap.current_license})
                    </p>
                    <ul className="node-helper__list">
                      {swap.alternatives.map((alt) => (
                        <li key={alt.model_id}>
                          {alt.name} — {alt.license_spdx}
                          <span className="node-helper__hint"> ({alt.model_id})</span>
                          {onApplyModelSwap ? (
                            <button
                              type="button"
                              className="compliance-swap__apply"
                              onClick={() => onApplyModelSwap(swap.node_id, alt.model_id)}
                            >
                              Use
                            </button>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                    {onBrowseModels ? (
                      <button
                        type="button"
                        className="compliance-swap__browse"
                        onClick={() =>
                          onBrowseModels({
                            nodeType: swap.node_type,
                            commercialOnly: true,
                            query: swap.alternatives[0]?.task_types?.[0] ?? swap.node_type,
                          })
                        }
                      >
                        Browse in Model Browser
                      </button>
                    ) : null}
                  </div>
                ))}
              </section>
            ) : null}
            <table>
              <thead>
                <tr>
                  <th>Component</th>
                  <th>License</th>
                  <th>Commercial</th>
                </tr>
              </thead>
              <tbody>
                {license.license_rows.map((row, i) => (
                  <tr key={`${row.component}-${i}`}>
                    <td>{row.component}</td>
                    <td>{row.license_spdx}</td>
                    <td>{row.commercial_ok ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {fastPath ? (
              <section className="compliance-preflight__commit">
                {intentBlocked ? (
                  <p className="compliance-hint compliance-hint--error">
                    {blockReason}
                  </p>
                ) : (
                  <p className="compliance-hint">
                    {missingModelCount > 0
                      ? `${missingModelCount} model${missingModelCount === 1 ? "" : "s"} will be installed, then the Preview branch will render and audition.`
                      : "Models are ready. The workflow will render only its Preview branch and audition it."}
                  </p>
                )}
                {fastPathError ? (
                  <p className="compliance-hint compliance-hint--error">{fastPathError}</p>
                ) : null}
                {fastPathResult ? <p className="compliance-hint">{fastPathResult}</p> : null}
                {fastPathBusy ? (
                  <button
                    type="button"
                    className="compliance-preflight__cancel"
                    disabled={fastPathStopping || !onCancelInstall}
                    onClick={() => {
                      setFastPathStopping(true);
                      onCancelInstall?.();
                    }}
                  >
                    {fastPathStopping
                      ? "Interrupting active download…"
                      : "Stop install (interrupt download)"}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="compliance-preflight__run"
                    disabled={intentBlocked || !onInstallRenderAudition}
                    onClick={() => void runFastPath()}
                  >
                    {missingModelCount > 0
                      ? "Install chain, render Preview & audition"
                      : "Render Preview & audition"}
                  </button>
                )}
              </section>
            ) : null}
          </div>
        ) : null}
        {tab === "provenance" ? (
          <div className="compliance-body">
            {!provenance || provenance.entries.length === 0 ? (
              <p className="compliance-hint">Render the workflow to populate provenance lineage per cache entry.</p>
            ) : (
              provenance.entries.map((entry) => (
                <section key={entry.node_id} className="provenance-entry">
                  <h3>
                    {entry.node_id} <span className="node-helper__mono">{entry.cache_id.slice(0, 8)}…</span>
                  </h3>
                  <ol className="provenance-chain">
                    {entry.chain.map((step, idx) => (
                      <li key={`${step.node?.node_id ?? idx}-${idx}`}>
                        <strong>{step.node?.node_type ?? "unknown"}</strong>
                        <span className={`pill pill--${step.contribution?.class ?? "unknown"}`}>
                          {step.contribution?.class ?? "unknown"}
                        </span>
                      </li>
                    ))}
                  </ol>
                </section>
              ))
            )}
          </div>
        ) : null}
        {tab === "authenticity" ? (
          <div className="compliance-body">
            {!authenticity ? (
              <p className="compliance-hint">Render an authenticity workflow to populate this report.</p>
            ) : (
              <>
                <p className="disclosure-text">{overall?.summary}</p>
                <p>
                  <strong>Label:</strong> {overall?.label} ({Math.round((overall?.confidence ?? 0) * 100)}%)
                </p>
                {provCheck ? (
                  <section>
                    <h3>Provenance check</h3>
                    <ul className="node-helper__list">
                      <li>Status: {String(provCheck.status)}</li>
                      <li>Sidecar: {provCheck.sidecar_found ? "found" : "missing"}</li>
                      <li>Contribution: {String(provCheck.contribution_class)}</li>
                    </ul>
                  </section>
                ) : null}
                {mlDet ? (
                  <section>
                    <h3>ML detection</h3>
                    <ul className="node-helper__list">
                      <li>Model: {String(mlDet.model_id)}</li>
                      <li>Spoof: {Math.round(Number(mlDet.spoof_score) * 100)}%</li>
                      <li>Bonafide: {Math.round(Number(mlDet.bonafide_score) * 100)}%</li>
                    </ul>
                  </section>
                ) : null}
                <p className="compliance-hint">Indicators only — not legal proof.</p>
                <button type="button" onClick={copyAuthenticity}>
                  Copy report JSON
                </button>
              </>
            )}
          </div>
        ) : null}
        {tab === "disclosure" ? (
          <div className="compliance-body">
            <p className="disclosure-text">{provenance?.focus_disclosure ?? "Render first to generate disclosure copy."}</p>
            <button type="button" onClick={copyDisclosure}>
              Copy disclosure
            </button>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
