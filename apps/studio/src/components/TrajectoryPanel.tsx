import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { fetchTrajectory, type TrajectoryPayload } from "../api";

type Props = {
  /** Authored / input trajectory cache id */
  inputId?: string | null;
  /** Extracted / output trajectory cache id */
  outputId?: string | null;
  /** Compact mode for Node Helper */
  compact?: boolean;
  className?: string;
};

function sampleAt(
  points: TrajectoryPayload["points"],
  tSec: number,
): { x: number; y: number; z: number } | null {
  if (!points.length) return null;
  if (points.length === 1) return { x: points[0].x, y: points[0].y, z: points[0].z };
  if (tSec <= points[0].t_sec) return { x: points[0].x, y: points[0].y, z: points[0].z };
  const last = points[points.length - 1];
  if (tSec >= last.t_sec) return { x: last.x, y: last.y, z: last.z };
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    if (a.t_sec <= tSec && tSec <= b.t_sec) {
      const span = b.t_sec - a.t_sec;
      const alpha = span <= 1e-9 ? 0 : (tSec - a.t_sec) / span;
      return {
        x: a.x + alpha * (b.x - a.x),
        y: a.y + alpha * (b.y - a.y),
        z: a.z + alpha * (b.z - a.z),
      };
    }
  }
  return { x: last.x, y: last.y, z: last.z };
}

/**
 * Top-down XZ (Multi-ACCDOA): +X = listener-left → drawn on the LEFT of the pad.
 * Matches stereo: left of pad = left ear = +X.
 */
function projectXZ(x: number, z: number, size: number): { px: number; py: number } {
  const pad = size * 0.12;
  const mid = size / 2;
  const scale = size / 2 - pad;
  return { px: mid - x * scale, py: mid - z * scale };
}

function unprojectXZ(px: number, py: number, size: number): { x: number; z: number } {
  const pad = size * 0.12;
  const mid = size / 2;
  const scale = size / 2 - pad;
  if (scale <= 1e-9) return { x: 0, z: 0 };
  return { x: (mid - px) / scale, z: (mid - py) / scale };
}

function clampUnit(x: number, z: number): { x: number; z: number } {
  const n = Math.hypot(x, z);
  if (n < 1e-9) return { x: 0, z: 1 };
  if (n <= 1) return { x, z };
  return { x: x / n, z: z / n };
}

function useTransportTime(): number {
  const [tSec, setTSec] = useState(0);
  const rafRef = useRef<number | null>(null);
  useEffect(() => {
    const tick = () => {
      const transport = document.querySelector<HTMLAudioElement>(".transport__audio");
      if (transport) {
        const fromUi = Number(transport.dataset.playheadSec);
        if (Number.isFinite(fromUi) && fromUi >= 0) {
          setTSec(fromUi);
        } else if (!Number.isNaN(transport.currentTime)) {
          setTSec(transport.currentTime);
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, []);
  return tSec;
}

function AxisLabels({ size }: { size: number }) {
  return (
    <>
      <text x={size / 2} y={14} textAnchor="middle" className="trajectory-panel__label">
        Front
      </text>
      <text x={12} y={size / 2 + 4} textAnchor="start" className="trajectory-panel__label">
        L
      </text>
      <text x={size - 12} y={size / 2 + 4} textAnchor="end" className="trajectory-panel__label">
        R
      </text>
    </>
  );
}

function TrajectoryPlot({
  label,
  variant,
  points,
  pos,
  size,
  tSec,
}: {
  label: string;
  variant: "input" | "output";
  points: TrajectoryPayload["points"] | null;
  pos: { x: number; y: number; z: number } | null;
  size: number;
  tSec: number;
}) {
  const pathD =
    points && points.length >= 2
      ? points
          .map((p, i) => {
            const { px, py } = projectXZ(p.x, p.z, size);
            return `${i === 0 ? "M" : "L"}${px.toFixed(1)} ${py.toFixed(1)}`;
          })
          .join(" ")
      : "";

  return (
    <div className={`trajectory-plot trajectory-plot--${variant}`}>
      <div className="trajectory-plot__header">
        <span className="trajectory-plot__label">{label}</span>
        <span className="trajectory-plot__time">{tSec.toFixed(2)}s</span>
      </div>
      <svg
        className="trajectory-panel__svg"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`${label} top-down trajectory (L left, R right)`}
      >
        <circle cx={size / 2} cy={size / 2} r={size * 0.38} className="trajectory-panel__ring" />
        <line x1={size / 2} y1={size * 0.08} x2={size / 2} y2={size * 0.92} className="trajectory-panel__axis" />
        <line x1={size * 0.08} y1={size / 2} x2={size * 0.92} y2={size / 2} className="trajectory-panel__axis" />
        <AxisLabels size={size} />
        {pathD ? (
          <path d={pathD} className={`trajectory-panel__path trajectory-panel__path--${variant}`} />
        ) : null}
        {pos ? (
          <circle
            cx={projectXZ(pos.x, pos.z, size).px}
            cy={projectXZ(pos.x, pos.z, size).py}
            r={5}
            className={`trajectory-panel__dot trajectory-panel__dot--${variant}`}
          />
        ) : null}
      </svg>
      <p className="trajectory-plot__coords">
        {pos ? `(${pos.x.toFixed(2)}, ${pos.y.toFixed(2)}, ${pos.z.toFixed(2)})` : "—"}
      </p>
    </div>
  );
}

/** Compact single-trajectory plot for on-canvas TrajectoryMonitor nodes. */
export function TrajectoryMini({
  trajectoryId,
  role = "input",
  size = 96,
}: {
  trajectoryId: string;
  role?: "input" | "output";
  size?: number;
}) {
  const [traj, setTraj] = useState<TrajectoryPayload | null>(null);
  const tSec = useTransportTime();

  useEffect(() => {
    let cancelled = false;
    setTraj(null);
    fetchTrajectory(trajectoryId)
      .then((data) => {
        if (!cancelled) setTraj(data);
      })
      .catch(() => {
        if (!cancelled) setTraj(null);
      });
    return () => {
      cancelled = true;
    };
  }, [trajectoryId]);

  const pos = useMemo(() => (traj ? sampleAt(traj.points, tSec) : null), [traj, tSec]);

  return (
    <TrajectoryPlot
      label={role === "output" ? "Out" : "In"}
      variant={role}
      points={traj?.points ?? null}
      pos={pos}
      size={size}
      tSec={tSec}
    />
  );
}

type AuthorWidgets = Record<string, unknown>;

type XZPoint = { x: number; z: number };

function parsePointsWidget(
  raw: unknown,
  durationSec: number,
): TrajectoryPayload["points"] | null {
  if (typeof raw !== "string" || !raw.trim()) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed) || parsed.length < 2) return null;
    const points: TrajectoryPayload["points"] = [];
    for (const item of parsed) {
      if (!item || typeof item !== "object") continue;
      const row = item as Record<string, unknown>;
      const x = Number(row.x);
      const z = Number(row.z);
      const y = Number(row.y ?? 0);
      const t = Number(row.t_sec ?? row.t ?? NaN);
      if (!Number.isFinite(x) || !Number.isFinite(z)) continue;
      points.push({
        t_sec: Number.isFinite(t) ? Math.max(0, t) : points.length,
        x,
        y: Number.isFinite(y) ? y : 0,
        z,
      });
    }
    if (points.length < 2) return null;
    // If times were missing/placeholder indices, re-spread over duration.
    const maxT = points[points.length - 1].t_sec;
    if (maxT <= 0 || points.every((p, i) => p.t_sec === i)) {
      const span = Math.max(0.05, durationSec);
      return points.map((p, i) => ({
        ...p,
        t_sec: span * (i / (points.length - 1)),
      }));
    }
    return points;
  } catch {
    return null;
  }
}

function strokeToPointsJson(stroke: XZPoint[], durationSec: number): string {
  const span = Math.max(0.05, durationSec);
  const points = stroke.map((p, i) => ({
    t_sec: span * (i / Math.max(1, stroke.length - 1)),
    x: p.x,
    y: 0,
    z: p.z,
  }));
  return JSON.stringify(points);
}

/**
 * Canvas / helper XYZ pad — drag Start/End, draw freehand path, scrub with transport.
 * Optional rendered trajectoryId prefers cache path after Render.
 */
export function TrajectoryAuthorPad({
  widgets,
  onChange,
  size = 180,
  compact = false,
  trajectoryId,
  role = "input",
}: {
  widgets: AuthorWidgets;
  onChange?: (patch: Record<string, number | string>) => void;
  size?: number;
  /** Hide long hint — for on-canvas nodes. */
  compact?: boolean;
  /** After render: scrub along cached trajectory during Preview play. */
  trajectoryId?: string | null;
  role?: "input" | "output";
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<"start" | "end" | "draw" | null>(null);
  const strokeRef = useRef<XZPoint[]>([]);
  const editable = typeof onChange === "function";
  const tSec = useTransportTime();
  const [traj, setTraj] = useState<TrajectoryPayload | null>(null);
  const [liveStroke, setLiveStroke] = useState<XZPoint[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    setTraj(null);
    if (!trajectoryId) return;
    fetchTrajectory(trajectoryId)
      .then((data) => {
        if (!cancelled) setTraj(data);
      })
      .catch(() => {
        if (!cancelled) setTraj(null);
      });
    return () => {
      cancelled = true;
    };
  }, [trajectoryId]);

  const start = {
    x: Number(widgets.start_x ?? 0.707),
    y: Number(widgets.start_y ?? 0),
    z: Number(widgets.start_z ?? 0.707),
  };
  const end = {
    x: Number(widgets.end_x ?? -0.707),
    y: Number(widgets.end_y ?? 0),
    z: Number(widgets.end_z ?? 0.707),
  };
  const durationSec = Math.max(0.05, Number(widgets.duration_sec ?? 1));
  const widgetPoints = useMemo(
    () => parsePointsWidget(widgets.points, durationSec),
    [widgets.points, durationSec],
  );

  const fallbackPoints = useMemo(
    () => [
      { t_sec: 0, x: start.x, y: start.y, z: start.z },
      { t_sec: durationSec, x: end.x, y: end.y, z: end.z },
    ],
    [start.x, start.y, start.z, end.x, end.y, end.z, durationSec],
  );

  // Prefer live draw, then authored widget points (editable), then rendered cache.
  const points =
    liveStroke && liveStroke.length >= 2
      ? liveStroke.map((p, i) => ({
          t_sec: durationSec * (i / (liveStroke.length - 1)),
          x: p.x,
          y: 0,
          z: p.z,
        }))
      : editable && widgetPoints && widgetPoints.length >= 2
        ? widgetPoints
        : traj?.points && traj.points.length >= 2
          ? traj.points
          : widgetPoints && widgetPoints.length >= 2
            ? widgetPoints
            : fallbackPoints;
  const playhead = useMemo(() => sampleAt(points, tSec), [points, tSec]);

  const startPx = projectXZ(start.x, start.z, size);
  const endPx = projectXZ(end.x, end.z, size);
  const pathD =
    points.length >= 2
      ? points
          .map((p, i) => {
            const { px, py } = projectXZ(p.x, p.z, size);
            return `${i === 0 ? "M" : "L"}${px.toFixed(1)} ${py.toFixed(1)}`;
          })
          .join(" ")
      : `M${startPx.px.toFixed(1)} ${startPx.py.toFixed(1)} L${endPx.px.toFixed(1)} ${endPx.py.toFixed(1)}`;

  const clientToLocal = useCallback(
    (clientX: number, clientY: number) => {
      const el = svgRef.current;
      if (!el) return { x: 0, z: 1 };
      const rect = el.getBoundingClientRect();
      const px = ((clientX - rect.left) / rect.width) * size;
      const py = ((clientY - rect.top) / rect.height) * size;
      const raw = unprojectXZ(px, py, size);
      return clampUnit(raw.x, raw.z);
    },
    [size],
  );

  const appendStroke = useCallback((xz: XZPoint) => {
    const prev = strokeRef.current;
    const last = prev[prev.length - 1];
    if (last) {
      const dist = Math.hypot(xz.x - last.x, xz.z - last.z);
      if (dist < 0.02) return;
    }
    strokeRef.current = [...prev, xz];
    setLiveStroke(strokeRef.current);
  }, []);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent) => {
      if (!dragRef.current || !onChange) return;
      const { x, z } = clientToLocal(event.clientX, event.clientY);
      if (dragRef.current === "start") {
        onChange({ start_x: x, start_z: z, points: "" });
      } else if (dragRef.current === "end") {
        onChange({ end_x: x, end_z: z, points: "" });
      } else if (dragRef.current === "draw") {
        appendStroke({ x, z });
      }
    },
    [appendStroke, clientToLocal, onChange],
  );

  const endDrag = useCallback(() => {
    if (dragRef.current === "draw" && onChange && strokeRef.current.length >= 2) {
      const stroke = strokeRef.current;
      const first = stroke[0];
      const last = stroke[stroke.length - 1];
      onChange({
        points: strokeToPointsJson(stroke, durationSec),
        start_x: first.x,
        start_z: first.z,
        end_x: last.x,
        end_z: last.z,
      });
    }
    dragRef.current = null;
    strokeRef.current = [];
    setLiveStroke(null);
  }, [durationSec, onChange]);

  const beginDraw = useCallback(
    (event: ReactPointerEvent<SVGSVGElement>) => {
      if (!editable || !onChange) return;
      // Ignore if starting on a handle (handles stopPropagation).
      event.stopPropagation();
      event.currentTarget.setPointerCapture(event.pointerId);
      const { x, z } = clientToLocal(event.clientX, event.clientY);
      dragRef.current = "draw";
      strokeRef.current = [{ x, z }];
      setLiveStroke(strokeRef.current);
    },
    [clientToLocal, editable, onChange],
  );

  const playPx = playhead ? projectXZ(playhead.x, playhead.z, size) : null;
  const drawn = Boolean(widgetPoints && widgetPoints.length >= 2) || Boolean(liveStroke);

  return (
    <div className={`trajectory-author-pad${compact ? " trajectory-author-pad--compact" : ""}`}>
      {compact ? null : (
        <p className="trajectory-author-pad__hint">
          Draw a path on the pad, or drag S/E. Then Render. Play Preview to scrub — not live audio.
        </p>
      )}
      <svg
        ref={svgRef}
        className="trajectory-panel__svg trajectory-author-pad__svg"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label="XYZ trajectory on canvas (L left, R right). Draw to author a path."
        onPointerDown={editable ? beginDraw : undefined}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
        style={editable ? { cursor: "crosshair" } : undefined}
      >
        <circle cx={size / 2} cy={size / 2} r={size * 0.38} className="trajectory-panel__ring" />
        <line x1={size / 2} y1={size * 0.08} x2={size / 2} y2={size * 0.92} className="trajectory-panel__axis" />
        <line x1={size * 0.08} y1={size / 2} x2={size * 0.92} y2={size / 2} className="trajectory-panel__axis" />
        <AxisLabels size={size} />
        <path d={pathD} className={`trajectory-panel__path trajectory-panel__path--${role}`} />
        {editable ? (
          <>
            <circle
              cx={startPx.px}
              cy={startPx.py}
              r={compact ? 7 : 8}
              className="trajectory-author-pad__handle trajectory-author-pad__handle--start"
              onPointerDown={(event) => {
                event.stopPropagation();
                event.currentTarget.setPointerCapture(event.pointerId);
                dragRef.current = "start";
              }}
            />
            <text x={startPx.px} y={startPx.py - 10} textAnchor="middle" className="trajectory-panel__label">
              S
            </text>
            <circle
              cx={endPx.px}
              cy={endPx.py}
              r={compact ? 7 : 8}
              className="trajectory-author-pad__handle trajectory-author-pad__handle--end"
              onPointerDown={(event) => {
                event.stopPropagation();
                event.currentTarget.setPointerCapture(event.pointerId);
                dragRef.current = "end";
              }}
            />
            <text x={endPx.px} y={endPx.py - 10} textAnchor="middle" className="trajectory-panel__label">
              E
            </text>
          </>
        ) : null}
        {playPx ? (
          <circle
            cx={playPx.px}
            cy={playPx.py}
            r={6}
            className={`trajectory-panel__dot trajectory-panel__dot--${role} trajectory-panel__dot--playhead`}
          />
        ) : null}
      </svg>
      {compact ? (
        <p className="trajectory-plot__coords trajectory-plot__coords--compact">
          {playhead
            ? `${playhead.x.toFixed(2)}, ${playhead.z.toFixed(2)} · ${tSec.toFixed(2)}s`
            : editable
              ? drawn
                ? "Path set · Render · Play"
                : "Draw / drag S·E · Render"
              : trajectoryId
                ? "Render · Play"
                : "No trajectory yet"}
        </p>
      ) : (
        <p className="trajectory-plot__coords">
          {playhead
            ? `Object (${playhead.x.toFixed(2)}, ${playhead.y.toFixed(2)}, ${playhead.z.toFixed(2)}) @ ${tSec.toFixed(2)}s`
            : drawn
              ? `Drawn path (${points.length} pts) · Render to apply`
              : `S (${start.x.toFixed(2)}, ${start.z.toFixed(2)}) → E (${end.x.toFixed(2)}, ${end.z.toFixed(2)})`}
        </p>
      )}
    </div>
  );
}

export default function TrajectoryPanel({ inputId, outputId, compact = false, className }: Props) {
  const [inputTraj, setInputTraj] = useState<TrajectoryPayload | null>(null);
  const [outputTraj, setOutputTraj] = useState<TrajectoryPayload | null>(null);
  const tSec = useTransportTime();
  const size = compact ? 140 : 180;

  useEffect(() => {
    let cancelled = false;
    setInputTraj(null);
    if (!inputId) return;
    fetchTrajectory(inputId)
      .then((data) => {
        if (!cancelled) setInputTraj(data);
      })
      .catch(() => {
        if (!cancelled) setInputTraj(null);
      });
    return () => {
      cancelled = true;
    };
  }, [inputId]);

  useEffect(() => {
    let cancelled = false;
    setOutputTraj(null);
    if (!outputId) return;
    fetchTrajectory(outputId)
      .then((data) => {
        if (!cancelled) setOutputTraj(data);
      })
      .catch(() => {
        if (!cancelled) setOutputTraj(null);
      });
    return () => {
      cancelled = true;
    };
  }, [outputId]);

  const inputPos = useMemo(
    () => (inputTraj ? sampleAt(inputTraj.points, tSec) : null),
    [inputTraj, tSec],
  );
  const outputPos = useMemo(
    () => (outputTraj ? sampleAt(outputTraj.points, tSec) : null),
    [outputTraj, tSec],
  );

  if (!inputId && !outputId) {
    return <p className="node-helper__hint">Render to populate trajectories.</p>;
  }

  return (
    <div className={`trajectory-panel trajectory-panel--split ${compact ? "trajectory-panel--compact" : ""} ${className ?? ""}`}>
      <div className="trajectory-panel__header">
        <span className="trajectory-panel__title">XYZ trajectory</span>
        <span className="trajectory-panel__hint">L ← · → R (listener view)</span>
      </div>
      <div className="trajectory-panel__plots">
        <TrajectoryPlot
          label="Input"
          variant="input"
          points={inputTraj?.points ?? null}
          pos={inputPos}
          size={size}
          tSec={tSec}
        />
        <TrajectoryPlot
          label="Output"
          variant="output"
          points={outputTraj?.points ?? null}
          pos={outputPos}
          size={size}
          tSec={tSec}
        />
      </div>
    </div>
  );
}
