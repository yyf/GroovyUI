import { useMemo } from "react";
import { controlCurveFromWidgets, type CurvePoint } from "./ControlCurvePreview";

type Props = {
  widgetsA: Record<string, unknown>;
  widgetsB: Record<string, unknown>;
  labelA: string;
  labelB: string;
  titleA?: string;
  titleB?: string;
};

const WIDTH = 280;
const HEIGHT = 120;
const PAD_X = 12;
const PAD_Y = 14;

function valueRange(pointsA: CurvePoint[], pointsB: CurvePoint[]): { minY: number; maxY: number } {
  let minY = 0;
  let maxY = 1;
  for (const p of [...pointsA, ...pointsB]) {
    minY = Math.min(minY, p.v);
    maxY = Math.max(maxY, p.v);
  }
  if (Math.abs(maxY - minY) < 1e-6) {
    minY -= 0.1;
    maxY += 0.1;
  }
  return { minY, maxY };
}

function polylinePath(
  points: CurvePoint[],
  minY: number,
  maxY: number,
  plotW: number,
  plotH: number,
): string {
  if (points.length === 0) return "";
  const span = Math.max(1e-9, maxY - minY);
  return points
    .map((p, i) => {
      const x = PAD_X + p.t * plotW;
      const y = PAD_Y + plotH * (1 - (p.v - minY) / span);
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

/** Overlay two ControlCurve widget curves (A/B) — no PCM metrics. */
export default function ControlCurveCompare({
  widgetsA,
  widgetsB,
  labelA,
  labelB,
  titleA,
  titleB,
}: Props) {
  const curveA = useMemo(() => controlCurveFromWidgets(widgetsA), [widgetsA]);
  const curveB = useMemo(() => controlCurveFromWidgets(widgetsB), [widgetsB]);
  const { minY, maxY } = valueRange(curveA.points, curveB.points);
  const plotW = WIDTH - PAD_X * 2;
  const plotH = HEIGHT - PAD_Y * 2;
  const pathA = polylinePath(curveA.points, minY, maxY, plotW, plotH);
  const pathB = polylinePath(curveB.points, minY, maxY, plotW, plotH);

  if (curveA.points.length < 2 && curveB.points.length < 2) {
    return <div className="curve-compare curve-compare--empty" />;
  }

  return (
    <div className="curve-compare">
      <div className="curve-compare__legend">
        <span className="curve-compare__swatch curve-compare__swatch--a" />
        <span className="curve-compare__label" title={titleA ?? labelA}>
          {labelA}
        </span>
        <span className="curve-compare__swatch curve-compare__swatch--b" />
        <span className="curve-compare__label" title={titleB ?? labelB}>
          {labelB}
        </span>
      </div>
      <svg className="curve-compare__svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" aria-hidden>
        <line
          className="curve-compare__grid"
          x1={PAD_X}
          x2={WIDTH - PAD_X}
          y1={PAD_Y + plotH / 2}
          y2={PAD_Y + plotH / 2}
        />
        {pathA ? <path className="curve-compare__path curve-compare__path--a" d={pathA} fill="none" /> : null}
        {pathB ? <path className="curve-compare__path curve-compare__path--b" d={pathB} fill="none" /> : null}
        {curveA.points.map((p, i) => {
          const span = Math.max(1e-9, maxY - minY);
          const x = PAD_X + p.t * plotW;
          const y = PAD_Y + plotH * (1 - (p.v - minY) / span);
          return <circle key={`a-${i}`} className="curve-compare__dot curve-compare__dot--a" cx={x} cy={y} r={3} />;
        })}
        {curveB.points.map((p, i) => {
          const span = Math.max(1e-9, maxY - minY);
          const x = PAD_X + p.t * plotW;
          const y = PAD_Y + plotH * (1 - (p.v - minY) / span);
          return <circle key={`b-${i}`} className="curve-compare__dot curve-compare__dot--b" cx={x} cy={y} r={3} />;
        })}
      </svg>
      <p className="curve-compare__meta">
        Normalized time 0–1
        {curveA.durationSec > 0 || curveB.durationSec > 0
          ? ` · A ${curveA.durationSec.toFixed(2)}s / B ${curveB.durationSec.toFixed(2)}s`
          : null}
      </p>
    </div>
  );
}
