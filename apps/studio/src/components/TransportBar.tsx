import type { Workflow } from "../types";

type Props = {
  workflow: Workflow;
  previewUrl: string | null;
  running: boolean;
  currentNode?: string;
  progress?: number;
  onRender: () => void;
  onPlay: () => void;
};

export default function TransportBar({
  workflow,
  previewUrl,
  running,
  currentNode,
  progress,
  onRender,
  onPlay,
}: Props) {
  const title = workflow.metadata.title;
  const pct = progress != null ? Math.round(progress * 100) : null;

  return (
    <footer className="transport">
      <button type="button" className="transport__play" onClick={onPlay} disabled={running}>
        ▶ Play chain
      </button>
      <button type="button" className="transport__render" onClick={onRender} disabled={running}>
        {running ? "Rendering…" : "Render chain"}
      </button>
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
      {previewUrl ? <audio controls src={previewUrl} className="transport__audio" /> : <span className="status">No render yet</span>}
    </footer>
  );
}
