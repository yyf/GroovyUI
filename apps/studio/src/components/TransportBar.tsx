import type { Workflow } from "../types";
import WaveformMini from "./WaveformMini";

type Props = {
  workflow: Workflow;
  previewUrl: string | null;
  waveformPeaks?: number[];
  running: boolean;
  currentNode?: string;
  progress?: number;
  onRender: () => void;
  onRenderAll?: () => void;
  onPlay: () => void;
};

export default function TransportBar({
  workflow,
  previewUrl,
  waveformPeaks = [],
  running,
  currentNode,
  progress,
  onRender,
  onRenderAll,
  onPlay,
}: Props) {
  const title = workflow.metadata.title;
  const pct = progress != null ? Math.round(progress * 100) : null;

  return (
    <footer className="transport">
      <button type="button" className="transport__play" onClick={onPlay} disabled={running}>
        ▶ Play chain
      </button>
      <button type="button" className="transport__render" onClick={onRender} disabled={running} title="Render chain">
        {running ? "Rendering…" : "Render chain"}
      </button>
      {onRenderAll ? (
        <button type="button" className="transport__render-all" onClick={onRenderAll} disabled={running} title="Shift+R">
          Render all
        </button>
      ) : null}
      <div className="transport__progress">
        {running && currentNode ? (
          <span>
            {currentNode} {pct != null ? `· ${pct}%` : ""}
          </span>
        ) : (
          <span>{title}</span>
        )}
        {running ? <div className="transport__bar" style={{ width: `${pct ?? 8}%` }} /> : null}
      </div>
      {previewUrl ? (
        <div className="transport__preview">
          {waveformPeaks.length > 0 ? <WaveformMini peaks={waveformPeaks} /> : null}
          <audio controls src={previewUrl} className="transport__audio" />
        </div>
      ) : (
        <span className="status">No render yet</span>
      )}
    </footer>
  );
}
