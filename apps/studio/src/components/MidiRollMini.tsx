import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export type MidiRollNote = {
  start: number;
  end: number;
  pitch: number;
  velocity: number;
  drum?: boolean;
};

export type SeekPhase = "start" | "move" | "end";

type Props = {
  duration: number;
  notes: MidiRollNote[];
  minPitch: number;
  maxPitch: number;
  progress?: number;
  /** ratio is 0–1 over the full clip; phase separates scrub vs commit (avoids scrub clicks). */
  onSeek?: (ratio: number, phase?: SeekPhase) => void;
  fitContainer?: boolean;
  className?: string;
};

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"] as const;
const TIME_ZOOM_MIN = 1;
const TIME_ZOOM_MAX = 16;
const PITCH_ZOOM_MIN = 1;
const PITCH_ZOOM_MAX = 8;
const NICE_TIME_STEPS = [0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60] as const;
/** Normalized SVG space — same units as CSS % so grid lines and axis ticks share coordinates. */
const SVG_W = 1000;
const SVG_H = 100;

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

function ratioFromPointer(clientX: number, rect: DOMRect): number {
  return clamp((clientX - rect.left) / rect.width, 0, 1);
}

/** Typical piano-roll label: note name + octave (MIDI pitch). */
function midiToLabel(pitch: number): string {
  const clamped = Math.round(pitch);
  const name = NOTE_NAMES[((clamped % 12) + 12) % 12];
  const octave = Math.floor(clamped / 12) - 1;
  return `${name}${octave}`;
}

function formatSeconds(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0.0s";
  if (sec >= 60) {
    const m = Math.floor(sec / 60);
    const s = sec - m * 60;
    return `${m}:${s.toFixed(1).padStart(4, "0")}`;
  }
  return `${sec.toFixed(1)}s`;
}

function pickTimeStep(visibleTime: number): number {
  const rough = visibleTime / 6;
  return NICE_TIME_STEPS.find((s) => s >= rough) ?? NICE_TIME_STEPS[NICE_TIME_STEPS.length - 1];
}

/** Snap floating time to the step grid without % drift on fractional steps. */
function nearlyMultiple(value: number, step: number, eps = 1e-6): boolean {
  if (step <= 0) return false;
  const q = value / step;
  return Math.abs(q - Math.round(q)) < eps;
}

function buildTimeMarks(t0: number, t1: number, step: number): number[] {
  if (!(t1 > t0) || step <= 0) return [t0];
  const startIndex = Math.ceil((t0 - 1e-9) / step);
  const endIndex = Math.floor((t1 + 1e-9) / step);
  const marks: number[] = [];
  for (let i = startIndex; i <= endIndex; i++) {
    marks.push(Number((i * step).toFixed(6)));
    if (marks.length > 32) break;
  }
  return marks.length > 0 ? marks : [t0, t1];
}

function PitchScale({
  minPitch,
  maxPitch,
  scaleRef,
}: {
  minPitch: number;
  maxPitch: number;
  scaleRef: React.RefObject<HTMLDivElement | null>;
}) {
  const mid = Math.round((minPitch + maxPitch) / 2);
  return (
    <div
      ref={scaleRef}
      className="midi-roll-mini__scale midi-roll-mini__scale--zoomable"
      aria-label="MIDI pitch — scroll to zoom"
      title="Scroll here to zoom pitch"
    >
      <span className="midi-roll-mini__scale-mark midi-roll-mini__scale-mark--top">{midiToLabel(maxPitch)}</span>
      <span className="midi-roll-mini__scale-mark midi-roll-mini__scale-mark--mid">{midiToLabel(mid)}</span>
      <span className="midi-roll-mini__scale-mark midi-roll-mini__scale-mark--bot">{midiToLabel(minPitch)}</span>
    </div>
  );
}

export default function MidiRollMini({
  duration,
  notes,
  minPitch,
  maxPitch,
  progress = 0,
  onSeek,
  fitContainer = false,
  className,
}: Props) {
  const plotRef = useRef<HTMLDivElement>(null);
  const pitchAxisRef = useRef<HTMLDivElement>(null);
  const timeAxisRef = useRef<HTMLDivElement>(null);
  const wheelZoomAtRef = useRef(0);
  const [, setPlotWidth] = useState(0);
  const [timeZoom, setTimeZoom] = useState(1);
  const [pitchZoom, setPitchZoom] = useState(1);
  const [timePan, setTimePan] = useState(0);
  const [pitchPan, setPitchPan] = useState(0);

  // Keep ResizeObserver so fitContainer still tracks layout; width no longer drives SVG coords.
  useEffect(() => {
    if (!fitContainer) return;
    const element = plotRef.current;
    if (!element) return;
    const measure = () => setPlotWidth(Math.max(64, Math.floor(element.clientWidth)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fitContainer]);

  const fullPitchSpan = Math.max(1, maxPitch - minPitch);
  const timeSpan = Math.max(0.001, duration);

  const view = useMemo(() => {
    const visibleTime = timeSpan / timeZoom;
    const maxTimePan = Math.max(0, timeSpan - visibleTime);
    const t0 = clamp(timePan, 0, maxTimePan);
    const t1 = t0 + visibleTime;

    const visiblePitch = fullPitchSpan / pitchZoom;
    const maxPitchPan = Math.max(0, fullPitchSpan - visiblePitch);
    const p0 = minPitch + clamp(pitchPan, 0, maxPitchPan);
    const p1 = p0 + visiblePitch;
    return { t0, t1, visibleTime, p0, p1, visiblePitch, maxTimePan, maxPitchPan };
  }, [timeSpan, timeZoom, timePan, fullPitchSpan, pitchZoom, pitchPan, minPitch]);

  useEffect(() => {
    setTimePan((prev) => clamp(prev, 0, view.maxTimePan));
    setPitchPan((prev) => clamp(prev, 0, view.maxPitchPan));
  }, [view.maxTimePan, view.maxPitchPan]);

  const seekFromEvent = (clientX: number, phase: SeekPhase) => {
    if (!onSeek || !plotRef.current) return;
    const rect = plotRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    const local = ratioFromPointer(clientX, rect);
    const absoluteSec = view.t0 + local * view.visibleTime;
    onSeek(clamp(absoluteSec / timeSpan, 0, 1), phase);
  };

  const zoomTimeAt = useCallback(
    (direction: 1 | -1, anchorSec?: number) => {
      setTimeZoom((z) => {
        const next = clamp(z * (direction > 0 ? 1.5 : 1 / 1.5), TIME_ZOOM_MIN, TIME_ZOOM_MAX);
        if (next === z) return z;
        const focus = anchorSec ?? clamp(progress, 0, 1) * timeSpan;
        const visible = timeSpan / next;
        const maxPan = Math.max(0, timeSpan - visible);
        setTimePan(clamp(focus - visible / 2, 0, maxPan));
        return next;
      });
    },
    [progress, timeSpan],
  );

  const zoomPitchAt = useCallback(
    (direction: 1 | -1, anchorPitch?: number) => {
      setPitchZoom((z) => {
        const next = clamp(z * (direction > 0 ? 1.5 : 1 / 1.5), PITCH_ZOOM_MIN, PITCH_ZOOM_MAX);
        if (next === z) return z;
        const focus = anchorPitch ?? (view.p0 + view.p1) / 2;
        const visible = fullPitchSpan / next;
        const maxPan = Math.max(0, fullPitchSpan - visible);
        setPitchPan(clamp(focus - minPitch - visible / 2, 0, maxPan));
        return next;
      });
    },
    [fullPitchSpan, minPitch, view.p0, view.p1],
  );

  // Scroll zoom only on axis label areas (not the note plot).
  useEffect(() => {
    const pitchEl = pitchAxisRef.current;
    const timeEl = timeAxisRef.current;
    if (!pitchEl || !timeEl) return;

    const allowZoom = () => {
      const now = performance.now();
      if (now - wheelZoomAtRef.current < 70) return false;
      wheelZoomAtRef.current = now;
      return true;
    };

    const onPitchWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
      if (Math.abs(delta) < 0.5 || !allowZoom()) return;
      const rect = pitchEl.getBoundingClientRect();
      const localY = rect.height > 0 ? clamp((event.clientY - rect.top) / rect.height, 0, 1) : 0.5;
      const anchorPitch = view.p1 - localY * view.visiblePitch;
      if (event.altKey || event.metaKey) {
        setPitchPan((p) => clamp(p + (delta / 400) * view.visiblePitch, 0, view.maxPitchPan));
        return;
      }
      zoomPitchAt(delta < 0 ? 1 : -1, anchorPitch);
    };

    const onTimeWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const delta = Math.abs(event.deltaX) >= Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
      if (Math.abs(delta) < 0.5 || !allowZoom()) return;
      const rect = timeEl.getBoundingClientRect();
      const localX = rect.width > 0 ? clamp((event.clientX - rect.left) / rect.width, 0, 1) : 0.5;
      const anchorSec = view.t0 + localX * view.visibleTime;
      if (event.altKey || event.metaKey) {
        setTimePan((p) => clamp(p + (delta / 400) * view.visibleTime, 0, view.maxTimePan));
        return;
      }
      zoomTimeAt(delta < 0 ? 1 : -1, anchorSec);
    };

    pitchEl.addEventListener("wheel", onPitchWheel, { passive: false });
    timeEl.addEventListener("wheel", onTimeWheel, { passive: false });
    return () => {
      pitchEl.removeEventListener("wheel", onPitchWheel);
      timeEl.removeEventListener("wheel", onTimeWheel);
    };
  }, [view, zoomPitchAt, zoomTimeAt]);

  const pitchSpan = Math.max(0.001, view.visiblePitch);
  const clampedProgress = clamp(progress, 0, 1);
  const playheadSec = clampedProgress * timeSpan;
  const playheadRatio =
    playheadSec >= view.t0 && playheadSec <= view.t1
      ? (playheadSec - view.t0) / view.visibleTime
      : null;

  const timeStep = useMemo(() => pickTimeStep(view.visibleTime), [view.visibleTime]);
  const timeMarks = useMemo(
    () => buildTimeMarks(view.t0, view.t1, timeStep),
    [view.t0, view.t1, timeStep],
  );

  /** Shared 0–1 x mapping for SVG grid + CSS axis labels. */
  const timeToRatio = useCallback(
    (t: number) => clamp((t - view.t0) / view.visibleTime, 0, 1),
    [view.t0, view.visibleTime],
  );

  const pitchLines = useMemo(() => {
    const lo = Math.ceil(view.p0 - 1e-9);
    const hi = Math.floor(view.p1 + 1e-9);
    const lines: { pitch: number; y: number; octave: boolean }[] = [];
    for (let pitch = lo; pitch <= hi; pitch++) {
      const y = ((view.p1 - pitch) / pitchSpan) * SVG_H;
      lines.push({ pitch, y, octave: pitch % 12 === 0 });
    }
    return lines;
  }, [view.p0, view.p1, pitchSpan]);

  const rootClass = [
    "midi-roll-mini",
    "midi-roll-mini--with-scale",
    "midi-roll-mini--with-time",
    onSeek ? "midi-roll-mini--seekable" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const plotProps = onSeek
    ? {
        onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => {
          if (event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          seekFromEvent(event.clientX, "start");
        },
        onPointerMove: (event: React.PointerEvent<HTMLDivElement>) => {
          if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
          seekFromEvent(event.clientX, "move");
        },
        onPointerUp: (event: React.PointerEvent<HTMLDivElement>) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
          seekFromEvent(event.clientX, "end");
        },
        onPointerCancel: (event: React.PointerEvent<HTMLDivElement>) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
          seekFromEvent(event.clientX, "end");
        },
      }
    : {};

  return (
    <div className={rootClass}>
      <div className="midi-roll-mini__body">
        <PitchScale minPitch={view.p0} maxPitch={view.p1} scaleRef={pitchAxisRef} />
        <div
          ref={plotRef}
          className={["midi-roll-mini__plot", onSeek ? "midi-roll-mini__plot--seekable" : ""].filter(Boolean).join(" ")}
          {...plotProps}
        >
          <svg
            className="midi-roll-mini__svg"
            viewBox={`0 0 ${SVG_W} ${SVG_H}`}
            preserveAspectRatio="none"
            aria-hidden
          >
            {/* Vertical time grid — x uses the same ratio as axis label left%. */}
            {timeMarks.map((t) => {
              const x = timeToRatio(t) * SVG_W;
              const isMajor = nearlyMultiple(t, timeStep * 2) || Math.abs(t) < 1e-9;
              return (
                <line
                  key={`t-${t}`}
                  x1={x}
                  x2={x}
                  y1={0}
                  y2={SVG_H}
                  className={
                    isMajor
                      ? "midi-roll-mini__grid midi-roll-mini__grid--time-major"
                      : "midi-roll-mini__grid midi-roll-mini__grid--time"
                  }
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
            {/* Horizontal pitch grid — integer semitones; octaves emphasized. */}
            {pitchLines.map(({ pitch, y, octave }) => (
              <line
                key={`p-${pitch}`}
                x1={0}
                x2={SVG_W}
                y1={y}
                y2={y}
                className={
                  octave
                    ? "midi-roll-mini__grid midi-roll-mini__grid--octave"
                    : "midi-roll-mini__grid midi-roll-mini__grid--pitch"
                }
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {notes.map((note, index) => {
              if (note.end < view.t0 || note.start > view.t1) return null;
              if (note.pitch < view.p0 - 1 || note.pitch > view.p1 + 1) return null;
              const x = timeToRatio(note.start) * SVG_W;
              const noteWidth = Math.max(1, ((note.end - note.start) / view.visibleTime) * SVG_W);
              const y = ((view.p1 - note.pitch) / pitchSpan) * SVG_H;
              const noteHeight = Math.max(1.2, SVG_H / pitchSpan - 0.4);
              const opacity = 0.35 + (note.velocity / 127) * 0.65;
              return (
                <rect
                  key={`${note.start}-${note.pitch}-${index}`}
                  x={x}
                  y={y + 0.2}
                  width={noteWidth}
                  height={noteHeight}
                  className={note.drum ? "midi-roll-mini__note midi-roll-mini__note--drum" : "midi-roll-mini__note"}
                  opacity={opacity}
                  rx={0.4}
                />
              );
            })}
          </svg>
          {onSeek && playheadRatio != null ? (
            <div className="midi-roll-mini__playhead" style={{ left: `${playheadRatio * 100}%` }} />
          ) : null}
        </div>
      </div>
      {/* Same 2-column grid as body so time-axis width === plot width (grid/ticks align). */}
      <div className="midi-roll-mini__footer">
        <div className="midi-roll-mini__footer-gutter" aria-hidden />
        <div className="midi-roll-mini__footer-main">
          <div
            ref={timeAxisRef}
            className="midi-roll-mini__time-axis midi-roll-mini__time-axis--zoomable"
            aria-label="Time in seconds — scroll to zoom"
            title="Scroll here to zoom time"
          >
            {timeMarks.map((t) => {
              const pct = timeToRatio(t) * 100;
              return (
                <span key={t} className="midi-roll-mini__time-mark" style={{ left: `${pct}%` }}>
                  <span className="midi-roll-mini__time-tick" aria-hidden />
                  {formatSeconds(t)}
                </span>
              );
            })}
            <span className="midi-roll-mini__time-unit">seconds</span>
          </div>
          <div className="midi-roll-mini__zoom" role="group" aria-label="MIDI roll zoom">
            <button
              type="button"
              title="Zoom time in (scroll x-axis)"
              onClick={() => zoomTimeAt(1)}
              disabled={timeZoom >= TIME_ZOOM_MAX}
            >
              T+
            </button>
            <button
              type="button"
              title="Zoom time out"
              onClick={() => zoomTimeAt(-1)}
              disabled={timeZoom <= TIME_ZOOM_MIN}
            >
              T−
            </button>
            <button
              type="button"
              title="Zoom pitch in (scroll y-axis)"
              onClick={() => zoomPitchAt(1)}
              disabled={pitchZoom >= PITCH_ZOOM_MAX}
            >
              P+
            </button>
            <button
              type="button"
              title="Zoom pitch out"
              onClick={() => zoomPitchAt(-1)}
              disabled={pitchZoom <= PITCH_ZOOM_MIN}
            >
              P−
            </button>
            {timeZoom > 1 || pitchZoom > 1 ? (
              <button
                type="button"
                title="Reset zoom"
                onClick={() => {
                  setTimeZoom(1);
                  setPitchZoom(1);
                  setTimePan(0);
                  setPitchPan(0);
                }}
              >
                1:1
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
