import { useEffect, useMemo, useState } from "react";

function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes > 0) {
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }
  return `${seconds}s`;
}

type Props = {
  running: boolean;
  nodeLabel?: string;
  message?: string;
  progress?: number;
  startedAt?: number;
  lastProgressAt?: number;
  downloadingModel?: boolean;
  onCancel?: () => void;
  cancelling?: boolean;
};

export default function RenderActivityBar({
  running,
  nodeLabel,
  message,
  progress,
  startedAt,
  lastProgressAt,
  downloadingModel = false,
  onCancel,
  cancelling = false,
}: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  const elapsed = startedAt ? now - startedAt : 0;
  const staleMs = lastProgressAt ? now - lastProgressAt : 0;
  const pct = progress != null ? Math.round(progress * 100) : null;
  const showPatienceHint = running && (downloadingModel || staleMs > 30_000);

  const detail = useMemo(() => {
    if (downloadingModel) {
      return nodeLabel ? `Downloading model · ${nodeLabel}` : "Downloading model…";
    }
    if (message && message !== nodeLabel) return message;
    if (nodeLabel) return `Running ${nodeLabel}`;
    return "Rendering workflow…";
  }, [downloadingModel, message, nodeLabel]);

  if (!running) return null;

  return (
    <div className="render-activity" role="status" aria-live="polite">
      <div className="render-activity__main">
        <span className="render-activity__spinner" aria-hidden />
        <div className="render-activity__text">
          <span className="render-activity__label">{detail}</span>
          <span className="render-activity__meta">
            {formatElapsed(elapsed)}
            {pct != null ? ` · ${pct}%` : ""}
          </span>
        </div>
        {onCancel ? (
          <button
            type="button"
            className="render-activity__cancel"
            onClick={onCancel}
            disabled={cancelling}
            title="Stop render (keeps completed nodes)"
          >
            {cancelling ? "Stopping…" : "Stop"}
          </button>
        ) : null}
      </div>
      <div
        className="render-activity__bar"
        aria-hidden
        style={pct != null ? { ["--render-progress" as string]: `${pct}%` } : undefined}
        data-indeterminate={pct == null ? "true" : undefined}
      />
      {showPatienceHint ? (
        <p className="render-activity__hint">
          {downloadingModel
            ? "First Hub load can take several minutes. The graph is still rendering."
            : "Still working — AI nodes can take several minutes, especially on first model load."}
        </p>
      ) : null}
    </div>
  );
}
