import { useCallback, useEffect, useRef, useState } from "react";
import WaveformMini from "./WaveformMini";

function formatTimeTag(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "00:00:00";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

type Props = {
  previewUrl: string | null;
  waveformPeaks?: number[];
  emptyHint?: string;
  running: boolean;
  statusMessage?: string;
  currentNode?: string;
  progress?: number;
  onRender: () => void;
  onRenderAll?: () => void;
  onPlay: () => void;
};

export default function TransportBar({
  previewUrl,
  waveformPeaks = [],
  emptyHint = "No render yet",
  running,
  statusMessage,
  currentNode,
  progress,
  onRender,
  onRenderAll,
  onPlay,
}: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const rafRef = useRef<number>(0);
  const [playbackProgress, setPlaybackProgress] = useState(0);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const pct = progress != null ? Math.round(progress * 100) : null;
  const statusFailed = Boolean(
    statusMessage?.toLowerCase().includes("fail") || statusMessage?.toLowerCase().startsWith("error"),
  );

  const syncProgress = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) {
      setPlaybackProgress(0);
      setPlaybackTime(0);
      setDuration(0);
      return;
    }
    const dur = audio.duration;
    if (!dur || !Number.isFinite(dur)) {
      setPlaybackProgress(0);
      setPlaybackTime(0);
      setDuration(0);
      return;
    }
    setPlaybackTime(audio.currentTime);
    setDuration(dur);
    setPlaybackProgress(audio.currentTime / dur);
  }, []);

  const stopRaf = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    }
  }, []);

  const startRaf = useCallback(() => {
    stopRaf();
    const tick = () => {
      const audio = audioRef.current;
      if (!audio || audio.paused || audio.ended) {
        rafRef.current = 0;
        return;
      }
      syncProgress();
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [stopRaf, syncProgress]);

  useEffect(() => {
    setPlaybackProgress(0);
    setPlaybackTime(0);
    setDuration(0);
    setIsPlaying(false);
    stopRaf();
  }, [previewUrl, stopRaf]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onPlay = () => {
      setIsPlaying(true);
      startRaf();
    };
    const onPause = () => {
      setIsPlaying(false);
      stopRaf();
      syncProgress();
    };
    const onEnded = () => {
      setIsPlaying(false);
      stopRaf();
      setPlaybackProgress(0);
      setPlaybackTime(0);
    };

    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);
    audio.addEventListener("seeked", syncProgress);
    audio.addEventListener("loadedmetadata", syncProgress);

    if (!audio.paused && !audio.ended) {
      setIsPlaying(true);
      startRaf();
    }

    return () => {
      stopRaf();
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("seeked", syncProgress);
      audio.removeEventListener("loadedmetadata", syncProgress);
    };
  }, [previewUrl, startRaf, stopRaf, syncProgress]);

  const handleSeek = useCallback(
    (ratio: number) => {
      const audio = audioRef.current;
      if (!audio || !audio.duration) return;
      audio.currentTime = ratio * audio.duration;
      setPlaybackProgress(ratio);
      if (!audio.paused) startRaf();
    },
    [startRaf],
  );

  const handlePause = useCallback(() => {
    audioRef.current?.pause();
  }, []);

  const handleStop = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
    setPlaybackProgress(0);
    setPlaybackTime(0);
    setIsPlaying(false);
    stopRaf();
  }, [stopRaf]);

  const togglePlayPause = useCallback(() => {
    if (running || !previewUrl) return;
    const audio = audioRef.current;
    if (audio && !audio.paused && !audio.ended) {
      audio.pause();
      return;
    }
    onPlay();
  }, [running, previewUrl, onPlay]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== " " && event.code !== "Space") return;
      if (event.repeat) return;
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (running) return;
      event.preventDefault();
      togglePlayPause();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [running, togglePlayPause]);

  const transportDisabled = running || !previewUrl;
  const canPause = Boolean(previewUrl) && isPlaying && !running;
  const canStop = Boolean(previewUrl) && (isPlaying || playbackProgress > 0) && !running;

  const statusLine =
    running && currentNode ? (
      <p className="transport__status">
        {currentNode}
        {pct != null ? ` · ${pct}%` : ""}
      </p>
    ) : statusMessage && statusMessage !== "Ready" ? (
      <p className={`transport__status${statusFailed ? " transport__status--error" : ""}`}>{statusMessage}</p>
    ) : null;

  return (
    <footer className="transport">
      <div className="transport__shell">
        <div className="transport__controls">
          <div className="transport__transport-group">
            <button
              type="button"
              className="transport__play"
              onClick={onPlay}
              disabled={transportDisabled}
              title="Play selected node (Space)"
            >
              Play
            </button>
            <button
              type="button"
              className="transport__pause"
              onClick={handlePause}
              disabled={!canPause}
              title="Pause (Space)"
            >
              Pause
            </button>
            <button type="button" className="transport__stop" onClick={handleStop} disabled={!canStop} title="Stop">
              Stop
            </button>
          </div>
          <button
            type="button"
            className="transport__render"
            onClick={onRender}
            disabled={running}
            title="Render selected node chain"
          >
            {running ? "Rendering…" : "Render"}
          </button>
          {onRenderAll ? (
            <button
              type="button"
              className="transport__render-all"
              onClick={onRenderAll}
              disabled={running}
              title="Shift+R"
            >
              Render all
            </button>
          ) : null}
        </div>

        <div className="transport__stage">
          <div className="transport__wave-wrap">
            {previewUrl ? (
              <WaveformMini
                peaks={waveformPeaks}
                progress={playbackProgress}
                onSeek={handleSeek}
                fitContainer
                className="transport__waveform"
              />
            ) : (
              <div className="transport__wave-empty">
                <WaveformMini peaks={[]} fitContainer className="transport__waveform" />
                <p className="transport__empty">{emptyHint}</p>
              </div>
            )}
            {previewUrl ? (
              <div className="transport__time-tag" aria-live="off">
                <span className="transport__time-current">{formatTimeTag(playbackTime)}</span>
                <span className="transport__time-sep">/</span>
                <span className="transport__time-duration">{formatTimeTag(duration)}</span>
              </div>
            ) : null}
            {statusLine ? <div className="transport__status-overlay">{statusLine}</div> : null}
          </div>
          {previewUrl ? <audio ref={audioRef} src={previewUrl} className="transport__audio" preload="metadata" /> : null}
        </div>
      </div>
    </footer>
  );
}
