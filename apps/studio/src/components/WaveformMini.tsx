import { useEffect, useRef, useState } from "react";

type Props = {
  peaks: number[];
  /** Target bar count when resampling (overridden when fitContainer is true). */
  displayWidth?: number;
  /** Playback position 0–1; draws playhead and played/unplayed styling. */
  progress?: number;
  /** Click/drag seek callback with ratio 0–1. */
  onSeek?: (ratio: number) => void;
  fitContainer?: boolean;
  /** Show minimal dB scale (relative to peak in view). */
  showScale?: boolean;
  className?: string;
};

function resamplePeaks(peaks: number[], width: number): number[] {
  if (peaks.length === 0) return [];
  if (peaks.length === width) return peaks;
  const out: number[] = [];
  for (let i = 0; i < width; i++) {
    const pos = (i / Math.max(width - 1, 1)) * (peaks.length - 1);
    const left = Math.floor(pos);
    const right = Math.min(peaks.length - 1, left + 1);
    const t = pos - left;
    out.push((peaks[left] ?? 0) * (1 - t) + (peaks[right] ?? 0) * t);
  }
  return out;
}

function ratioFromPointer(clientX: number, rect: DOMRect): number {
  return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
}

function WaveformBars({
  samples,
  max,
  height,
  barClass,
}: {
  samples: number[];
  max: number;
  height: number;
  barClass: string;
}) {
  const mid = height / 2;
  return (
    <>
      {samples.map((peak, index) => {
        const amp = (peak / max) * (mid - 2);
        const x = index + 0.5;
        return (
          <line
            key={index}
            x1={x}
            x2={x}
            y1={mid - amp}
            y2={mid + amp}
            className={barClass}
            vectorEffect="non-scaling-stroke"
          />
        );
      })}
    </>
  );
}

function VolumeScale() {
  return (
    <div className="waveform-mini__scale" aria-hidden>
      <span className="waveform-mini__scale-mark waveform-mini__scale-mark--top">0</span>
      <span className="waveform-mini__scale-mark waveform-mini__scale-mark--mid">−12</span>
      <span className="waveform-mini__scale-mark waveform-mini__scale-mark--bot">−24</span>
    </div>
  );
}

export default function WaveformMini({
  peaks,
  displayWidth = 512,
  progress = 0,
  onSeek,
  fitContainer = false,
  showScale = false,
  className,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const clipId = useRef(`waveform-clip-${Math.random().toString(36).slice(2, 9)}`);
  const [containerWidth, setContainerWidth] = useState(displayWidth);

  useEffect(() => {
    if (!fitContainer) {
      setContainerWidth(displayWidth);
      return;
    }
    const element = containerRef.current;
    if (!element) return;
    const measure = () => setContainerWidth(Math.max(64, Math.floor(element.clientWidth)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [displayWidth, fitContainer]);

  const seekFromEvent = (clientX: number) => {
    if (!onSeek || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    onSeek(ratioFromPointer(clientX, rect));
  };

  if (!peaks.length) {
    return (
      <div
        className={[
          "waveform-mini",
          "waveform-mini--empty",
          showScale ? "waveform-mini--with-scale" : "",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {showScale ? <VolumeScale /> : null}
        <div ref={fitContainer ? containerRef : undefined} className="waveform-mini__plot waveform-mini__plot--empty" />
      </div>
    );
  }

  const samples = resamplePeaks(peaks, containerWidth);
  const max = Math.max(...samples, 0.001);
  const width = samples.length;
  const height = 40;
  const playbackMode = onSeek != null;
  const clampedProgress = Math.min(1, Math.max(0, progress));
  const playheadPct = `${clampedProgress * 100}%`;
  const clipWidth = clampedProgress * width;

  const rootClass = [
    "waveform-mini",
    onSeek ? "waveform-mini--seekable" : "",
    showScale ? "waveform-mini--with-scale" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const plot = playbackMode ? (
    <>
      <svg className="waveform-mini__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden>
        <defs>
          <clipPath id={clipId.current}>
            <rect x={0} y={0} width={clipWidth} height={height} />
          </clipPath>
        </defs>
        <WaveformBars samples={samples} max={max} height={height} barClass="waveform-mini__bar waveform-mini__bar--unplayed" />
        <g clipPath={`url(#${clipId.current})`}>
          <WaveformBars samples={samples} max={max} height={height} barClass="waveform-mini__bar waveform-mini__bar--played" />
        </g>
      </svg>
      <div className="waveform-mini__playhead" style={{ left: playheadPct }} />
    </>
  ) : (
    <svg className="waveform-mini__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden>
      <WaveformBars samples={samples} max={max} height={height} barClass="waveform-mini__bar" />
    </svg>
  );

  const plotProps = onSeek
    ? {
        onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => {
          event.preventDefault();
          seekFromEvent(event.clientX);
          const onMove = (moveEvent: PointerEvent) => seekFromEvent(moveEvent.clientX);
          const onUp = () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
          };
          window.addEventListener("pointermove", onMove);
          window.addEventListener("pointerup", onUp);
        },
      }
    : {};

  return (
    <div className={rootClass}>
      {showScale ? <VolumeScale /> : null}
      <div
        ref={containerRef}
        className={["waveform-mini__plot", onSeek ? "waveform-mini__plot--seekable" : ""].filter(Boolean).join(" ")}
        {...plotProps}
      >
        {plot}
      </div>
    </div>
  );
}
