import { useEffect, useMemo, useState } from "react";
import { downloadComplianceReport, fetchAuthenticity, fetchLicenseScan, fetchProvenance } from "../api";
import type { JobOutput, LicenseScanSummary, ProvenanceSummary, Workflow } from "../types";

type Tab = "license" | "provenance" | "authenticity" | "disclosure";

type Props = {
  open: boolean;
  workflow: Workflow;
  outputs?: Record<string, JobOutput>;
  targetNodeId?: string | null;
  onClose: () => void;
};

export default function ComplianceDrawer({ open, workflow, outputs, targetNodeId, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("license");
  const [license, setLicense] = useState<LicenseScanSummary | null>(null);
  const [provenance, setProvenance] = useState<ProvenanceSummary | null>(null);
  const [authenticity, setAuthenticity] = useState<Record<string, unknown> | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

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
            {license.swap_suggestions.length > 0 ? (
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
                        </li>
                      ))}
                    </ul>
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
