import { useEffect, useState } from "react";
import { fetchCompliance, fetchProvenance } from "../api";
import type { JobOutput, ProvenanceSummary, Workflow } from "../types";

type Tab = "license" | "provenance" | "disclosure";

type Props = {
  open: boolean;
  workflow: Workflow;
  outputs?: Record<string, JobOutput>;
  targetNodeId?: string | null;
  onClose: () => void;
};

export default function ComplianceDrawer({ open, workflow, outputs, targetNodeId, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("license");
  const [license, setLicense] = useState<Awaited<ReturnType<typeof fetchCompliance>> | null>(null);
  const [provenance, setProvenance] = useState<ProvenanceSummary | null>(null);

  useEffect(() => {
    if (!open) return;
    fetchCompliance(workflow)
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

  return (
    <div className="compliance-backdrop" onClick={onClose}>
      <aside className="compliance-drawer" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Compliance</h2>
          {provenance?.contains_ai ? <span className="pill pill--warning">AI</span> : null}
          <button type="button" onClick={onClose}>
            ✕
          </button>
        </header>
        <nav>
          <button type="button" className={tab === "license" ? "active" : ""} onClick={() => setTab("license")}>
            License
          </button>
          <button type="button" className={tab === "provenance" ? "active" : ""} onClick={() => setTab("provenance")}>
            Provenance
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
                        {step.models?.length ? (
                          <span className="provenance-models">
                            {step.models.map((m) => m.registry_id).filter(Boolean).join(", ")}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                </section>
              ))
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
