import { useEffect, useState } from "react";
import { fetchCacheMeta } from "../api";
import { samplePairCheck, type SamplePairCheck, type SampleMetaSummary } from "../sampleIntegrity";

function shortHash(hash: unknown): string {
  const text = typeof hash === "string" ? hash : "";
  if (!text) return "—";
  const bare = text.replace(/^sha256:/, "");
  return bare.length > 16 ? `${bare.slice(0, 12)}…` : bare;
}

function formatSamples(count: unknown): string {
  const n = Number(count);
  if (!Number.isFinite(n) || n < 0) return "—";
  return Math.round(n).toLocaleString();
}

function formatDuration(meta: SampleMetaSummary | Record<string, unknown> | null): string {
  if (!meta) return "—";
  const sr = Number(meta.sample_rate || 0);
  const frames = Number(meta.frame_count || 0);
  if (!(sr > 0) || !(frames > 0)) return "—";
  return `${(frames / sr).toFixed(3)} s`;
}

export function SamplePairVerdict({ check }: { check: SamplePairCheck | null }) {
  if (!check) return null;
  return (
    <p className={`node-helper__sample-verdict node-helper__sample-verdict--${check.label}`}>
      <span className="node-helper__compare-verdict-tag">{check.label.replaceAll("_", " ")}</span>
      {check.summary}
    </p>
  );
}

/** Single-node sample check report (VerifySamples Outputs tab). */
export function SampleCheckFromReport({
  sampleCheck,
}: {
  sampleCheck: Record<string, unknown> | null | undefined;
}) {
  if (!sampleCheck) return null;
  const match = Boolean(sampleCheck.hash_match);
  const samples = sampleCheck.sample_count ?? sampleCheck.frame_count;
  return (
    <section className="node-helper__sample-panel">
      <h4 className="node-helper__compare-section-title">Sample check</h4>
      <div className="node-helper__sample-hero">
        <span className="node-helper__sample-hero-label">Samples</span>
        <strong className="node-helper__sample-hero-value">{formatSamples(samples)}</strong>
      </div>
      <p className={`node-helper__sample-verdict node-helper__sample-verdict--${match ? "match" : "mismatch"}`}>
        <span className="node-helper__compare-verdict-tag">
          {String(sampleCheck.label ?? (match ? "match" : "mismatch"))}
        </span>
        {String(sampleCheck.summary ?? "")}
      </p>
      <div className="node-helper__sample-inline">
        <span>
          <em>Rate</em> {sampleCheck.sample_rate ? `${sampleCheck.sample_rate} Hz` : "—"}
        </span>
        <span>
          <em>Duration</em> {formatDuration(sampleCheck)}
        </span>
        <span>
          <em>Layout</em> {String(sampleCheck.channel_layout ?? "—")}
        </span>
        <span>
          <em>Hash</em>{" "}
          <code title={String(sampleCheck.content_hash ?? "")}>{shortHash(sampleCheck.content_hash)}</code>
        </span>
        <span>
          <em>Match</em> {match ? "yes" : "no"}
        </span>
      </div>
    </section>
  );
}

type CompareRow = { label: string; a: string; b: string; titleA?: string; titleB?: string };

/** Fetch and show sample meta for two A/B cache ids as a horizontal table. */
export default function CompareSampleIntegrity({
  cacheIdA,
  cacheIdB,
  labelA,
  labelB,
}: {
  cacheIdA?: string | null;
  cacheIdB?: string | null;
  labelA: string;
  labelB: string;
}) {
  const [metaA, setMetaA] = useState<SampleMetaSummary | null>(null);
  const [metaB, setMetaB] = useState<SampleMetaSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    setMetaA(null);
    setMetaB(null);
    const load = async () => {
      const [a, b] = await Promise.all([
        cacheIdA ? fetchCacheMeta(cacheIdA).catch(() => null) : Promise.resolve(null),
        cacheIdB ? fetchCacheMeta(cacheIdB).catch(() => null) : Promise.resolve(null),
      ]);
      if (cancelled) return;
      setMetaA(a);
      setMetaB(b);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [cacheIdA, cacheIdB]);

  const pair = metaA && metaB ? samplePairCheck(metaA, metaB) : null;
  const rows: CompareRow[] = [
    {
      label: "Samples",
      a: formatSamples(metaA?.frame_count),
      b: formatSamples(metaB?.frame_count),
    },
    {
      label: "Sample rate",
      a: metaA?.sample_rate ? `${metaA.sample_rate} Hz` : "—",
      b: metaB?.sample_rate ? `${metaB.sample_rate} Hz` : "—",
    },
    {
      label: "Duration",
      a: formatDuration(metaA),
      b: formatDuration(metaB),
    },
    {
      label: "Layout",
      a: metaA ? String(metaA.channel_layout ?? "—") : "—",
      b: metaB ? String(metaB.channel_layout ?? "—") : "—",
    },
    {
      label: "Channels",
      a: metaA?.channels != null ? String(metaA.channels) : "—",
      b: metaB?.channels != null ? String(metaB.channels) : "—",
    },
    {
      label: "Content hash",
      a: shortHash(metaA?.content_hash),
      b: shortHash(metaB?.content_hash),
      titleA: String(metaA?.content_hash ?? ""),
      titleB: String(metaB?.content_hash ?? ""),
    },
  ];

  return (
    <div className="node-helper__sample-compare">
      <h4 className="node-helper__compare-section-title">Sample check</h4>
      <SamplePairVerdict check={pair} />
      {!metaA && !metaB ? (
        <p className="node-helper__hint">No cache meta yet — render first.</p>
      ) : (
        <table className="node-helper__sample-table">
          <thead>
            <tr>
              <th scope="col"> </th>
              <th scope="col">A · {labelA}</th>
              <th scope="col">B · {labelB}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                <td title={row.titleA}>{row.a}</td>
                <td title={row.titleB}>{row.b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
