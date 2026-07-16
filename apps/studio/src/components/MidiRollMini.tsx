import { useEffect, useRef, useState } from "react";

export type MidiRollNote = {
  start: number;
  end: number;
  pitch: number;
  velocity: number;
  drum?: boolean;
};

type Props = {
  duration: number;
  notes: MidiRollNote[];
  minPitch: number;
  maxPitch: number;
  progress?: number;
  onSeek?: (ratio: number) => void;
  fitContainer?: boolean;
  className?: string;
};

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"] as const;

function ratioFromPointer(clientX: number, rect: DOMRect): number {
  return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
}

/** Typical piano-roll label: note name + octave (MIDI pitch). */
function midiToLabel(pitch: number): string {
  const clamped = Math.round(pitch);
  const name = NOTE_NAMES[((clamped % 12) + 12) % 12];
  const octave = Math.floor(clamped / 12) - 1;
  return `${name}${octave}`;
}

function PitchScale({ minPitch, maxPitch }: { minPitch: number; maxPitch: number }) {
  const mid = Math.round((minPitch + maxPitch) / 2);
  return (
    <div className="midi-roll-mini__scale" aria-label="MIDI pitch">
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
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(512);

  useEffect(() => {
    if (!fitContainer) return;
    const element = containerRef.current;
    if (!element) return;
    const measure = () => setContainerWidth(Math.max(64, Math.floor(element.clientWidth)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fitContainer]);

  const seekFromEvent = (clientX: number) => {
    if (!onSeek || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    onSeek(ratioFromPointer(clientX, rect));
  };

  const width = fitContainer ? containerWidth : 512;
  const height = 40;
  const pitchSpan = Math.max(1, maxPitch - minPitch);
  const timeSpan = Math.max(0.001, duration);
  const clampedProgress = Math.min(1, Math.max(0, progress));
  const playheadPct = `${clampedProgress * 100}%`;
  const rootClass = [
    "midi-roll-mini",
    "midi-roll-mini--with-scale",
    onSeek ? "midi-roll-mini--seekable" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const plot = (
    <>
      <svg className="midi-roll-mini__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden>
        {Array.from({ length: pitchSpan + 1 }, (_, index) => {
          const pitch = minPitch + index;
          const y = ((maxPitch - pitch) / pitchSpan) * height;
          const isOctave = pitch % 12 === 0;
          return (
            <line
              key={pitch}
              x1={0}
              x2={width}
              y1={y}
              y2={y}
              className={isOctave ? "midi-roll-mini__grid midi-roll-mini__grid--octave" : "midi-roll-mini__grid"}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
        {notes.map((note, index) => {
          const x = (note.start / timeSpan) * width;
          const noteWidth = Math.max(1, ((note.end - note.start) / timeSpan) * width);
          const y = ((maxPitch - note.pitch) / pitchSpan) * height;
          const noteHeight = Math.max(1.5, height / pitchSpan - 0.5);
          const opacity = 0.35 + (note.velocity / 127) * 0.65;
          return (
            <rect
              key={`${note.start}-${note.pitch}-${index}`}
              x={x}
              y={y + 0.25}
              width={noteWidth}
              height={noteHeight}
              className={note.drum ? "midi-roll-mini__note midi-roll-mini__note--drum" : "midi-roll-mini__note"}
              opacity={opacity}
              rx={0.5}
            />
          );
        })}
      </svg>
      {onSeek ? <div className="midi-roll-mini__playhead" style={{ left: playheadPct }} /> : null}
    </>
  );

  const plotProps = onSeek
    ? {
        onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => {
          if (event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          seekFromEvent(event.clientX);
        },
        onPointerMove: (event: React.PointerEvent<HTMLDivElement>) => {
          if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
          seekFromEvent(event.clientX);
        },
        onPointerUp: (event: React.PointerEvent<HTMLDivElement>) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
        },
        onPointerCancel: (event: React.PointerEvent<HTMLDivElement>) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
        },
      }
    : {};

  return (
    <div className={rootClass}>
      <PitchScale minPitch={minPitch} maxPitch={maxPitch} />
      <div
        ref={containerRef}
        className={["midi-roll-mini__plot", onSeek ? "midi-roll-mini__plot--seekable" : ""].filter(Boolean).join(" ")}
        {...plotProps}
      >
        {plot}
      </div>
    </div>
  );
}
