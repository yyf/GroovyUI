import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import WaveformMini from "./WaveformMini";
import MidiRollMini, { type MidiRollNote } from "./MidiRollMini";

function formatTimeTag(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "00:00:00";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function cacheIdFromPreviewUrl(url: string): string | null {
  const match = url.match(/\/api\/cache\/([^/?]+)\/preview/);
  return match?.[1] ?? null;
}

function waitForAudioReady(audio: HTMLAudioElement): Promise<void> {
  if (audio.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) {
    return Promise.resolve();
  }
  return new Promise<void>((resolve, reject) => {
    const onReady = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("Preview audio failed to load"));
    };
    const cleanup = () => {
      audio.removeEventListener("canplaythrough", onReady);
      audio.removeEventListener("canplay", onReady);
      audio.removeEventListener("error", onError);
    };
    audio.addEventListener("canplaythrough", onReady);
    audio.addEventListener("canplay", onReady);
    audio.addEventListener("error", onError);
  });
}

type Props = {
  previewUrl: string | null;
  previewKind?: "audio" | "midi" | null;
  waveformPeaks?: number[];
  midiRoll?: {
    duration: number;
    notes: MidiRollNote[];
    minPitch: number;
    maxPitch: number;
  } | null;
  emptyHint?: string;
  running: boolean;
  statusMessage?: string;
  onRender: () => void;
  onRenderAll?: () => void;
  onPlay: () => void;
  auditionNonce?: number;
};

export default function TransportBar({
  previewUrl,
  previewKind = null,
  waveformPeaks = [],
  midiRoll = null,
  emptyHint = "No render yet",
  running,
  statusMessage,
  onRender,
  onRenderAll,
  onPlay,
  auditionNonce = 0,
}: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const loadedCacheIdRef = useRef<string | null>(null);
  const rafRef = useRef<number>(0);
  const [playbackProgress, setPlaybackProgress] = useState(0);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const isMidiVisual = previewKind === "midi";
  const hasPreview = Boolean(previewUrl);
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

  const loadPreviewSource = useCallback(async (url: string) => {
    const audio = audioRef.current;
    if (!audio) return;
    const cacheId = cacheIdFromPreviewUrl(url);
    if (cacheId && loadedCacheIdRef.current === cacheId && audio.src) {
      return;
    }
    audio.pause();
    audio.currentTime = 0;
    audio.src = url;
    audio.load();
    await waitForAudioReady(audio);
    if (cacheId) loadedCacheIdRef.current = cacheId;
  }, []);

  const playAudio = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio || !previewUrl) return;
    try {
      await loadPreviewSource(previewUrl);
      await audio.play();
    } catch {
      // Browser may block autoplay without a direct gesture; ignore.
    }
  }, [loadPreviewSource, previewUrl]);

  useLayoutEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (!previewUrl) {
      loadedCacheIdRef.current = null;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      return;
    }
    const cacheId = cacheIdFromPreviewUrl(previewUrl);
    if (cacheId && loadedCacheIdRef.current === cacheId && audio.src) {
      return;
    }
    audio.pause();
    audio.currentTime = 0;
    audio.src = previewUrl;
    audio.load();
    if (cacheId) loadedCacheIdRef.current = cacheId;
  }, [previewUrl]);

  useEffect(() => {
    setPlaybackProgress(0);
    setPlaybackTime(0);
    setDuration(0);
    setIsPlaying(false);
    stopRaf();
  }, [previewUrl, previewKind, midiRoll, stopRaf]);

  useEffect(() => {
    if (!auditionNonce) return;
    void playAudio();
  }, [auditionNonce, playAudio]);

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
    if (running || !hasPreview) return;
    const audio = audioRef.current;
    if (audio && !audio.paused && !audio.ended) {
      audio.pause();
      return;
    }
    onPlay();
    void playAudio();
  }, [running, hasPreview, onPlay, playAudio]);

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

  const transportDisabled = running || !hasPreview;
  const canPause = Boolean(previewUrl) && isPlaying && !running;
  const canStop = Boolean(previewUrl) && (isPlaying || playbackProgress > 0) && !running;

  const statusLine =
    !running && statusMessage && statusMessage !== "Ready" ? (
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
              onClick={() => {
                onPlay();
                void playAudio();
              }}
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
            {isMidiVisual ? (
              <div className={previewUrl ? undefined : "transport__wave-empty"}>
                <MidiRollMini
                  duration={midiRoll?.duration ?? 1}
                  notes={midiRoll?.notes ?? []}
                  minPitch={midiRoll?.minPitch ?? 60}
                  maxPitch={midiRoll?.maxPitch ?? 72}
                  progress={playbackProgress}
                  onSeek={previewUrl ? handleSeek : undefined}
                  fitContainer
                  className="transport__midi-roll"
                />
                {!previewUrl ? <p className="transport__empty">{emptyHint}</p> : null}
              </div>
            ) : previewUrl ? (
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
            {hasPreview ? (
              <div className="transport__time-tag" aria-live="off">
                <span className="transport__time-current">{formatTimeTag(playbackTime)}</span>
                <span className="transport__time-sep">/</span>
                <span className="transport__time-duration">{formatTimeTag(duration)}</span>
              </div>
            ) : null}
            {statusLine ? <div className="transport__status-overlay">{statusLine}</div> : null}
          </div>
          <audio ref={audioRef} className="transport__audio" preload="auto" />
        </div>
      </div>
    </footer>
  );
}
