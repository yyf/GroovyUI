import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export type CurvePoint = { t: number; v: number };

type Props = {
  widgets: Record<string, unknown>;
  onChange?: (patch: Record<string, unknown>) => void;
  className?: string;
};

const WIDTH = 280;
const HEIGHT = 140;
const PAD_X = 12;
const PAD_Y = 12;
const HIT_RADIUS = 10;
const DEFAULT_POINTS: CurvePoint[] = [
  { t: 0, v: 0 },
  { t: 1, v: 1 },
];

function num(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function sortPoints(points: CurvePoint[]): CurvePoint[] {
  return [...points].sort((a, b) => a.t - b.t);
}

/** Parse ControlCurve widgets into editable points + timing meta. */
export function controlCurveFromWidgets(widgets: Record<string, unknown>): {
  points: CurvePoint[];
  startValue: number;
  endValue: number;
  frameCount: number;
  sampleRate: number;
  durationSec: number;
} {
  const startValue = num(widgets.start_value, 0);
  const endValue = num(widgets.end_value, 1);
  const frameCount = Math.max(2, Math.round(num(widgets.frame_count, 48000)));
  const sampleRate = Math.max(1, Math.round(num(widgets.sample_rate, 48000)));
  let points = parsePoints(widgets.points);
  if (points.length < 2) {
    points = [
      { t: 0, v: startValue },
      { t: 1, v: endValue },
    ];
  } else {
    // Keep first/last in sync with start/end pots when they diverge from a simple 2-point curve.
    points = sortPoints(points);
    if (points[0]) points[0] = { ...points[0], t: 0 };
    if (points[points.length - 1]) points[points.length - 1] = { ...points[points.length - 1]!, t: 1 };
  }
  return {
    points,
    startValue: points[0]?.v ?? startValue,
    endValue: points[points.length - 1]?.v ?? endValue,
    frameCount,
    sampleRate,
    durationSec: frameCount / sampleRate,
  };
}

export function parsePoints(raw: unknown): CurvePoint[] {
  let data = raw;
  if (typeof data === "string") {
    const text = data.trim();
    if (!text) return [];
    try {
      data = JSON.parse(text);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(data)) return [];
  const out: CurvePoint[] = [];
  for (const item of data) {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      const rec = item as Record<string, unknown>;
      const t = num(rec.t ?? rec.x, NaN);
      const v = num(rec.v ?? rec.y, NaN);
      if (!Number.isFinite(t) || !Number.isFinite(v)) continue;
      out.push({ t: clamp(t, 0, 1), v });
    } else if (Array.isArray(item) && item.length >= 2) {
      const t = num(item[0], NaN);
      const v = num(item[1], NaN);
      if (!Number.isFinite(t) || !Number.isFinite(v)) continue;
      out.push({ t: clamp(t, 0, 1), v });
    }
  }
  return sortPoints(out);
}

export function serializePoints(points: CurvePoint[]): string {
  const normalized = sortPoints(points).map((p) => ({
    t: Math.round(p.t * 10000) / 10000,
    v: Math.round(p.v * 10000) / 10000,
  }));
  return JSON.stringify(normalized);
}

export function pointsPatch(points: CurvePoint[]): Record<string, unknown> {
  const sorted = sortPoints(points);
  const withEnds =
    sorted.length >= 2
      ? sorted.map((p, i, arr) => {
          if (i === 0) return { t: 0, v: p.v };
          if (i === arr.length - 1) return { t: 1, v: p.v };
          return { t: clamp(p.t, 0.001, 0.999), v: p.v };
        })
      : DEFAULT_POINTS;
  return {
    points: serializePoints(withEnds),
    start_value: withEnds[0]!.v,
    end_value: withEnds[withEnds.length - 1]!.v,
  };
}

function valueRange(points: CurvePoint[]): { minY: number; maxY: number } {
  let minY = 0;
  let maxY = 1;
  for (const p of points) {
    minY = Math.min(minY, p.v);
    maxY = Math.max(maxY, p.v);
  }
  if (Math.abs(maxY - minY) < 1e-6) {
    minY -= 0.1;
    maxY += 0.1;
  }
  return { minY, maxY };
}

export default function ControlCurvePreview({ widgets, onChange, className = "" }: Props) {
  const curve = useMemo(() => controlCurveFromWidgets(widgets), [widgets]);
  const { points, frameCount, sampleRate, durationSec } = curve;
  const editable = Boolean(onChange);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const dragIndexRef = useRef<number | null>(null);
  const pointsRef = useRef(points);
  pointsRef.current = points;

  const { minY, maxY } = valueRange(points);
  const span = Math.max(1e-9, maxY - minY);
  const plotW = WIDTH - PAD_X * 2;
  const plotH = HEIGHT - PAD_Y * 2;

  const toSvg = useCallback(
    (p: CurvePoint) => ({
      x: PAD_X + p.t * plotW,
      y: PAD_Y + plotH * (1 - (p.v - minY) / span),
    }),
    [minY, plotH, plotW, span],
  );

  const fromClient = useCallback(
    (clientX: number, clientY: number): CurvePoint | null => {
      const svg = svgRef.current;
      if (!svg) return null;
      const rect = svg.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return null;
      const x = ((clientX - rect.left) / rect.width) * WIDTH;
      const y = ((clientY - rect.top) / rect.height) * HEIGHT;
      const t = clamp((x - PAD_X) / plotW, 0, 1);
      const v = minY + (1 - (y - PAD_Y) / plotH) * span;
      return { t, v };
    },
    [minY, plotH, plotW, span],
  );

  const hitTest = useCallback(
    (clientX: number, clientY: number): number => {
      const svg = svgRef.current;
      if (!svg) return -1;
      const rect = svg.getBoundingClientRect();
      const sx = (rect.width / WIDTH) * HIT_RADIUS;
      const sy = (rect.height / HEIGHT) * HIT_RADIUS;
      const hit = Math.max(sx, sy);
      let best = -1;
      let bestDist = Number.POSITIVE_INFINITY;
      pointsRef.current.forEach((p, index) => {
        const { x, y } = toSvg(p);
        const cx = rect.left + (x / WIDTH) * rect.width;
        const cy = rect.top + (y / HEIGHT) * rect.height;
        const dist = Math.hypot(clientX - cx, clientY - cy);
        if (dist <= hit && dist < bestDist) {
          best = index;
          bestDist = dist;
        }
      });
      return best;
    },
    [toSvg],
  );

  const commit = useCallback(
    (next: CurvePoint[]) => {
      if (!onChange) return;
      onChange(pointsPatch(next));
    },
    [onChange],
  );

  useEffect(() => {
    if (dragIndex === null) return;
    const onMove = (event: PointerEvent) => {
      const index = dragIndexRef.current;
      if (index === null) return;
      const nextPt = fromClient(event.clientX, event.clientY);
      if (!nextPt) return;
      const current = pointsRef.current;
      const updated = current.map((p, i) => {
        if (i !== index) return p;
        if (i === 0) return { t: 0, v: nextPt.v };
        if (i === current.length - 1) return { t: 1, v: nextPt.v };
        return { t: clamp(nextPt.t, 0.001, 0.999), v: nextPt.v };
      });
      commit(updated);
    };
    const onUp = () => {
      dragIndexRef.current = null;
      setDragIndex(null);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [commit, dragIndex, fromClient]);

  const polyline = points.map((p) => {
    const { x, y } = toSvg(p);
    return `${x},${y}`;
  }).join(" ");

  const zeroY = PAD_Y + plotH * (1 - (0 - minY) / span);

  return (
    <div className={`control-curve-preview ${editable ? "control-curve-preview--editable" : ""} ${className}`.trim()}>
      <svg
        ref={svgRef}
        className="control-curve-preview__svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Editable control curve"
        onPointerDown={(event) => {
          if (!editable || event.button !== 0) return;
          event.preventDefault();
          const hit = hitTest(event.clientX, event.clientY);
          if (hit >= 0) {
            dragIndexRef.current = hit;
            setDragIndex(hit);
            return;
          }
          const pt = fromClient(event.clientX, event.clientY);
          if (!pt) return;
          const next = sortPoints([...points, { t: clamp(pt.t, 0.001, 0.999), v: pt.v }]);
          commit(next);
          let dragAt = 0;
          let best = Number.POSITIVE_INFINITY;
          next.forEach((p, i) => {
            const d = Math.abs(p.t - pt.t);
            if (d < best) {
              best = d;
              dragAt = i;
            }
          });
          dragIndexRef.current = dragAt;
          setDragIndex(dragAt);
        }}
        onDoubleClick={(event) => {
          if (!editable) return;
          event.preventDefault();
          const hit = hitTest(event.clientX, event.clientY);
          if (hit <= 0 || hit >= points.length - 1) return;
          commit(points.filter((_, i) => i !== hit));
        }}
      >
        <rect x={0} y={0} width={WIDTH} height={HEIGHT} className="control-curve-preview__bg" />
        {zeroY >= PAD_Y && zeroY <= HEIGHT - PAD_Y ? (
          <line
            x1={PAD_X}
            x2={WIDTH - PAD_X}
            y1={zeroY}
            y2={zeroY}
            className="control-curve-preview__zero"
          />
        ) : null}
        <polyline points={polyline} className="control-curve-preview__line" fill="none" />
        {points.map((p, index) => {
          const { x, y } = toSvg(p);
          const active = dragIndex === index;
          return (
            <circle
              key={`${index}-${p.t}-${p.v}`}
              cx={x}
              cy={y}
              r={active ? 4.5 : 3.5}
              className={
                active
                  ? "control-curve-preview__dot control-curve-preview__dot--active"
                  : "control-curve-preview__dot"
              }
            />
          );
        })}
      </svg>
      <p className="control-curve-preview__meta">
        {points.length} pts
        <span className="control-curve-preview__sep">·</span>
        {durationSec.toFixed(2)}s
        <span className="control-curve-preview__sep">·</span>
        {frameCount.toLocaleString()} frames @ {sampleRate} Hz
      </p>
      {editable ? (
        <p className="control-curve-preview__hint">Click to add · drag to move · double-click point to remove</p>
      ) : null}
    </div>
  );
}

/** Sync start/end pot edits into the points list (and vice versa storage). */
export function syncPointsFromStartEnd(
  widgets: Record<string, unknown>,
  name: string,
  value: unknown,
): Record<string, unknown> | null {
  if (name !== "start_value" && name !== "end_value") return null;
  const curve = controlCurveFromWidgets(widgets);
  const next = [...curve.points];
  if (next.length < 2) return null;
  if (name === "start_value") next[0] = { t: 0, v: num(value, next[0]!.v) };
  if (name === "end_value") next[next.length - 1] = { t: 1, v: num(value, next[next.length - 1]!.v) };
  return pointsPatch(next);
}
