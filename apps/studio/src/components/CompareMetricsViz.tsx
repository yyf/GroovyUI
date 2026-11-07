import type { ReactNode } from "react";
import type { AbCompareClip, AbCompareComparison } from "../api";
import type { StemSeparationCompareMeta } from "../workflow";

type Props = {
  clipA: AbCompareClip;
  clipB: AbCompareClip;
  comparison: AbCompareComparison;
  labelA: string;
  labelB: string;
  stemSeparation?: StemSeparationCompareMeta | null;
};

function resample(peaks: number[], width: number): number[] {
  if (peaks.length === 0) return Array(width).fill(0);
  if (peaks.length === width) return peaks;
  const out: number[] = [];
  for (let i = 0; i < width; i++) {
    const idx = Math.floor((i / width) * peaks.length);
    out.push(peaks[idx] ?? 0);
  }
  return out;
}

function fmtSigned(value: number, digits = 1, unit = ""): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}${unit}`;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function fmtDb(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)} dB`;
}

/** Bipolar meter: center = 0, left = negative (A louder/longer), right = positive (B). */
function DeltaMeter({
  label,
  value,
  unit,
  scale,
}: {
  label: string;
  value: number | null;
  unit: string;
  scale: number;
}) {
  if (value == null || Number.isNaN(value)) {
    return (
      <div className="compare-meter compare-meter--na">
        <div className="compare-meter__head">
          <span className="compare-meter__label">{label}</span>
          <span className="compare-meter__value">n/a</span>
        </div>
        <div className="compare-meter__track" />
      </div>
    );
  }
  const magnitude = clamp01(Math.abs(value) / scale);
  const side = value < 0 ? "neg" : value > 0 ? "pos" : "zero";
  return (
    <div className={`compare-meter compare-meter--${side}`}>
      <div className="compare-meter__head">
        <span className="compare-meter__label">{label}</span>
        <span className="compare-meter__value">{fmtSigned(value, Math.abs(value) >= 10 ? 0 : 1, unit)}</span>
      </div>
      <div className="compare-meter__track" aria-hidden>
        <span className="compare-meter__zero" />
        {magnitude > 0 ? (
          <span
            className="compare-meter__fill"
            style={
              value < 0
                ? { right: "50%", width: `${magnitude * 50}%` }
                : { left: "50%", width: `${magnitude * 50}%` }
            }
          />
        ) : null}
      </div>
    </div>
  );
}

function ResidualPlot({ peaksA, peaksB }: { peaksA: number[]; peaksB: number[] }) {
  const width = 240;
  const height = 56;
  const mid = height / 2;
  const a = resample(peaksA, width);
  const b = resample(peaksB, width);
  const residual = a.map((va, i) => (b[i] ?? 0) - va);
  const max = Math.max(...residual.map(Math.abs), 0.001);
  const points = residual
    .map((v, i) => {
      const y = mid - (v / max) * (mid - 2);
      return `${i},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <div className="compare-plot">
      <div className="compare-plot__head">
        <span className="compare-plot__title">Residual envelope</span>
        <span className="compare-plot__meta">B − A</span>
      </div>
      <svg className="compare-plot__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden>
        <line className="compare-plot__grid" x1={0} x2={width} y1={mid} y2={mid} />
        <line className="compare-plot__grid compare-plot__grid--soft" x1={0} x2={width} y1={mid / 2} y2={mid / 2} />
        <line
          className="compare-plot__grid compare-plot__grid--soft"
          x1={0}
          x2={width}
          y1={mid + mid / 2}
          y2={mid + mid / 2}
        />
        <polyline className="compare-plot__residual" points={points} fill="none" />
      </svg>
    </div>
  );
}

function LevelBars({
  clipA,
  clipB,
  labelA,
  labelB,
}: {
  clipA: AbCompareClip;
  clipB: AbCompareClip;
  labelA: string;
  labelB: string;
}) {
  const peakA = clipA.peak;
  const peakB = clipB.peak;
  const rmsA = clipA.rms;
  const rmsB = clipB.rms;
  const max = Math.max(peakA, peakB, rmsA, rmsB, 0.001);

  const bar = (value: number, tone: "a" | "b") => (
    <span
      className={`compare-bars__fill compare-bars__fill--${tone}`}
      style={{ width: `${clamp01(value / max) * 100}%` }}
    />
  );

  return (
    <div className="compare-bars">
      <div className="compare-plot__head">
        <span className="compare-plot__title">Level</span>
        <span className="compare-plot__meta">
          <span className="compare-plot__swatch compare-plot__swatch--a" />
          {labelA}
          <span className="compare-plot__swatch compare-plot__swatch--b" />
          {labelB}
        </span>
      </div>
      <div className="compare-bars__row">
        <span className="compare-bars__label">Peak</span>
        <div className="compare-bars__track">{bar(peakA, "a")}</div>
        <div className="compare-bars__track">{bar(peakB, "b")}</div>
      </div>
      <div className="compare-bars__row">
        <span className="compare-bars__label">RMS</span>
        <div className="compare-bars__track">{bar(rmsA, "a")}</div>
        <div className="compare-bars__track">{bar(rmsB, "b")}</div>
      </div>
    </div>
  );
}

function Readout({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="compare-readout" title={hint}>
      <span className="compare-readout__label">{label}</span>
      <span className="compare-readout__value">{value}</span>
    </div>
  );
}

function MetricsSection({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className="compare-metrics__section">
      <header className="compare-metrics__section-head">
        <h4 className="compare-metrics__section-title">{title}</h4>
        {hint ? <p className="compare-metrics__section-hint">{hint}</p> : null}
      </header>
      {children}
    </section>
  );
}

export default function CompareMetricsViz({
  clipA,
  clipB,
  comparison,
  labelA,
  labelB,
  stemSeparation = null,
}: Props) {
  const { waveform, pcm } = comparison;
  const snr = fmtDb(pcm.snr_db);
  const sdr = fmtDb(pcm.sdr_db);
  const siSdr = fmtDb(pcm.si_sdr_db);
  const stemLabel =
    stemSeparation?.modelA || stemSeparation?.modelB
      ? [stemSeparation.modelA ?? "A", stemSeparation.modelB ?? "B"].join(" ∥ ")
      : null;

  return (
    <div className="compare-metrics">
      <MetricsSection title="Loudness" hint="Peak / RMS / integrated loudness deltas (B − A)">
        <LevelBars clipA={clipA} clipB={clipB} labelA={labelA} labelB={labelB} />
        <div className="compare-meters">
          <DeltaMeter label="Peak Δ" value={comparison.peak_delta_db} unit=" dB" scale={6} />
          <DeltaMeter label="RMS Δ" value={comparison.rms_delta_db} unit=" dB" scale={6} />
          <DeltaMeter label="LUFS Δ" value={comparison.lufs_delta} unit=" LU" scale={6} />
          <DeltaMeter label="Dur Δ" value={comparison.duration_delta_sec} unit=" s" scale={1} />
        </div>
      </MetricsSection>

      <MetricsSection title="Waveform" hint="Aligned envelope residual and sample-level drift">
        <ResidualPlot peaksA={clipA.peaks} peaksB={clipB.peaks} />
        <div className="compare-readouts">
          <Readout label="Corr" value={waveform.correlation.toFixed(3)} hint="Waveform peak correlation" />
          <Readout label="SNR" value={snr} hint="Signal-to-residual ratio (aligned)" />
          <Readout
            label="Changed"
            value={`${pcm.changed_sample_pct.toFixed(1)}%`}
            hint="Share of samples with |Δ| > 1e-5"
          />
          <Readout
            label="Max Δ"
            value={pcm.max_sample_diff.toExponential(1)}
            hint="Maximum absolute sample difference"
          />
        </div>
      </MetricsSection>

      <MetricsSection
        title={stemSeparation ? "Stem separation (no ground truth)" : "Pairwise similarity (no ground truth)"}
        hint={
          stemSeparation
            ? `Comparing two model estimates${stemLabel ? ` · ${stemLabel}` : ""}. These measure A↔B agreement — not BSS Eval quality vs a true stem.`
            : "A↔B agreement only — not quality vs a ground-truth reference."
        }
      >
        <div className="compare-readouts compare-readouts--stem">
          <Readout
            label="SDR"
            value={sdr}
            hint="Pairwise SDR (A as ref). Higher = B closer to A. Not museval vs ground truth."
          />
          <Readout
            label="SI-SDR"
            value={siSdr}
            hint="Pairwise scale-invariant SDR. Higher = closer after gain match. Not vs ground truth."
          />
          <Readout
            label="Mel cos"
            value={
              pcm.mel_cosine == null || Number.isNaN(pcm.mel_cosine)
                ? "—"
                : pcm.mel_cosine.toFixed(3)
            }
            hint="Mel-spectrogram cosine (1 = identical timbre/shape). Common no-GT A/B distance proxy."
          />
          <Readout
            label="LSD"
            value={
              pcm.log_spectral_distance == null || Number.isNaN(pcm.log_spectral_distance)
                ? "—"
                : pcm.log_spectral_distance.toFixed(3)
            }
            hint="Log-spectral distance (lower = closer). Frequency-content disagreement between estimates."
          />
          <Readout
            label="Centroid Δ"
            value={
              pcm.spectral_centroid_delta_hz == null || Number.isNaN(pcm.spectral_centroid_delta_hz)
                ? "—"
                : `${pcm.spectral_centroid_delta_hz >= 0 ? "+" : ""}${pcm.spectral_centroid_delta_hz.toFixed(0)} Hz`
            }
            hint="Spectral centroid B − A. Brightness / timbre shift between stem estimates."
          />
          <Readout
            label="HF Δ"
            value={
              pcm.hf_energy_delta == null || Number.isNaN(pcm.hf_energy_delta)
                ? "—"
                : `${pcm.hf_energy_delta >= 0 ? "+" : ""}${pcm.hf_energy_delta.toFixed(3)}`
            }
            hint="High-band (>4 kHz) energy share B − A. Often rises with bleed or artifacts on vocals."
          />
        </div>
        {stemSeparation ? (
          <dl className="compare-stem-meta">
            <div className="compare-stem-meta__row">
              <dt>A model</dt>
              <dd>{stemSeparation.modelA ?? "—"}</dd>
            </div>
            <div className="compare-stem-meta__row">
              <dt>B model</dt>
              <dd>{stemSeparation.modelB ?? "—"}</dd>
            </div>
          </dl>
        ) : null}
      </MetricsSection>

      <div className="compare-metrics__footer">
        <span>
          {clipA.sample_rate} Hz · {clipA.channel_layout}
          {!comparison.same_sample_rate || !comparison.same_layout ? " ≠ " : " = "}
          {clipB.sample_rate} Hz · {clipB.channel_layout}
        </span>
        <span>
          {clipA.duration_sec.toFixed(2)}s / {clipB.duration_sec.toFixed(2)}s
        </span>
      </div>
    </div>
  );
}
