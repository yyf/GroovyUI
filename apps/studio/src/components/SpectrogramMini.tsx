import { useCallback, useEffect, useRef, useState } from "react";
import type { SpectrogramData } from "../api";

type Props = {
  data: SpectrogramData | null;
  /** Playback position 0–1; draws playhead and played/unplayed styling. */
  progress?: number;
  /** Click/drag seek callback with ratio 0–1. */
  onSeek?: (ratio: number) => void;
  fitContainer?: boolean;
  className?: string;
};

function ratioFromPointer(clientX: number, rect: DOMRect): number {
  return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
}

function formatFreqLabel(hz: number): string {
  if (hz >= 10_000) return `${Math.round(hz / 1000)}kHz`;
  if (hz >= 1000) return `${(hz / 1000).toFixed(1)}kHz`;
  return `${Math.round(hz)}Hz`;
}

function FreqScale({ maxFreqHz }: { maxFreqHz: number }) {
  const mid = maxFreqHz / 2;
  return (
    <div className="spectrogram-mini__scale" aria-hidden>
      <span className="spectrogram-mini__scale-mark spectrogram-mini__scale-mark--top">
        {formatFreqLabel(maxFreqHz)}
      </span>
      <span className="spectrogram-mini__scale-mark spectrogram-mini__scale-mark--mid">
        {formatFreqLabel(mid)}
      </span>
      <span className="spectrogram-mini__scale-mark spectrogram-mini__scale-mark--bot">0Hz</span>
    </div>
  );
}

/** Scientific intensity → black / signal-red / white-hot (palette only; dB mapping unchanged). */
function dbToSignalRgb(db: number, minDb: number, maxDb: number, dim = 1): [number, number, number] {
  const span = Math.max(1e-6, maxDb - minDb);
  const t = Math.min(1, Math.max(0, (db - minDb) / span));
  let r: number;
  let g: number;
  let b: number;
  if (t < 0.55) {
    const u = t / 0.55;
    r = Math.round(12 + u * 243);
    g = Math.round(u * 18);
    b = Math.round(u * 28);
  } else {
    const u = (t - 0.55) / 0.45;
    r = 255;
    g = Math.round(18 + u * 220);
    b = Math.round(28 + u * 200);
  }
  return [Math.round(r * dim), Math.round(g * dim), Math.round(b * dim)];
}

export default function SpectrogramMini({
  data,
  progress = 0,
  onSeek,
  fitContainer = false,
  className,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [, setMeasureTick] = useState(0);

  useEffect(() => {
    if (!fitContainer) return;
    const element = containerRef.current;
    if (!element) return;
    const measure = () => setMeasureTick((tick) => tick + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fitContainer]);

  const draw = useCallback(() => {
    const plot = containerRef.current;
    const canvas = canvasRef.current;
    if (!plot || !canvas || !data?.values.length || data.width <= 0 || data.height <= 0) return;

    const width = Math.max(64, plot.clientWidth);
    const height = Math.max(32, plot.clientHeight);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const offscreen = document.createElement("canvas");
    offscreen.width = data.width;
    offscreen.height = data.height;
    const offCtx = offscreen.getContext("2d");
    if (!offCtx) return;

    const image = offCtx.createImageData(data.width, data.height);
    const pixels = image.data;
    const minDb = data.min_db;
    const maxDb = data.max_db;
    const clampedProgress = Math.min(1, Math.max(0, progress));
    const playCol = Math.floor(clampedProgress * data.width);

    for (let y = 0; y < data.height; y++) {
      const srcY = data.height - 1 - y;
      for (let x = 0; x < data.width; x++) {
        const idx = srcY * data.width + x;
        const db = data.values[idx] ?? minDb;
        const dim = x <= playCol || onSeek == null ? 1 : 0.42;
        const [r, g, b] = dbToSignalRgb(db, minDb, maxDb, dim);
        const pixel = (y * data.width + x) * 4;
        pixels[pixel] = r;
        pixels[pixel + 1] = g;
        pixels[pixel + 2] = b;
        pixels[pixel + 3] = 255;
      }
    }
    offCtx.putImageData(image, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(offscreen, 0, 0, data.width, data.height, 0, 0, width, height);
  }, [data, onSeek, progress, fitContainer]);

  useEffect(() => {
    draw();
  }, [draw, fitContainer]);

  const seekFromEvent = (clientX: number) => {
    if (!onSeek || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    onSeek(ratioFromPointer(clientX, rect));
  };

  const rootClass = [
    "spectrogram-mini",
    "spectrogram-mini--with-scale",
    onSeek ? "spectrogram-mini--seekable" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  if (!data?.values.length) {
    return (
      <div className={["spectrogram-mini", "spectrogram-mini--empty", className].filter(Boolean).join(" ")}>
        <FreqScale maxFreqHz={data?.max_freq_hz ?? 24_000} />
        <div
          ref={fitContainer ? containerRef : undefined}
          className="spectrogram-mini__plot spectrogram-mini__plot--empty"
        />
      </div>
    );
  }

  const clampedProgress = Math.min(1, Math.max(0, progress));
  const playheadPct = `${clampedProgress * 100}%`;

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
      <FreqScale maxFreqHz={data.max_freq_hz} />
      <div
        ref={containerRef}
        className={["spectrogram-mini__plot", onSeek ? "spectrogram-mini__plot--seekable" : ""]
          .filter(Boolean)
          .join(" ")}
        {...plotProps}
      >
        <canvas ref={canvasRef} className="spectrogram-mini__canvas" aria-hidden />
        {onSeek ? <div className="spectrogram-mini__playhead" style={{ left: playheadPct }} /> : null}
      </div>
    </div>
  );
}
