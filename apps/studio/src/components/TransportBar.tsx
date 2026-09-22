import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSpectrogram, type SpectrogramData } from "../api";
import SpectrogramMini from "./SpectrogramMini";
import StatusLeds, { type StatusLedSpec } from "./StatusLeds";
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

function waitForAudioMetadata(audio: HTMLAudioElement): Promise<void> {
  if (audio.readyState >= HTMLMediaElement.HAVE_METADATA && Number.isFinite(audio.duration) && audio.duration > 0) {
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
      audio.removeEventListener("loadedmetadata", onReady);
      audio.removeEventListener("durationchange", onReady);
      audio.removeEventListener("error", onError);
    };
    audio.addEventListener("loadedmetadata", onReady);
    audio.addEventListener("durationchange", onReady);
    audio.addEventListener("error", onError);
  });
}

type Props = {
  previewUrl: string | null;
  previewKind?: "audio" | "midi" | null;
  waveformPeaks?: number[];
  /** Clip duration from waveform API (seconds); preferred for seek math. */
  waveformDuration?: number;
  midiRoll?: {
    duration: number;
    notes: MidiRollNote[];
    minPitch: number;
    maxPitch: number;
  } | null;
  emptyHint?: string;
  running: boolean;
  statusMessage?: string;
  statusLeds?: StatusLedSpec[];
  onRender: () => void;
  onRenderAll?: () => void;
  onPlay: () => void;
  auditionNonce?: number;
  onPlaybackStarted?: () => void;
  onPlaybackFailed?: (reason: string) => void;
};

type AudioVisualMode = "waveform" | "spectrogram";

export default function TransportBar({
  previewUrl,
  previewKind = null,
  waveformPeaks = [],
  waveformDuration = 0,
  midiRoll = null,
  emptyHint = "No render yet",
  running,
  statusMessage,
  statusLeds = [],
  onRender,
  onRenderAll,
  onPlay,
  auditionNonce = 0,
  onPlaybackStarted,
  onPlaybackFailed,
}: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const blobUrlRef = useRef<string | null>(null);
  const loadedCacheIdRef = useRef<string | null>(null);
  const loadPromiseRef = useRef<Promise<void> | null>(null);
  const playheadRatioRef = useRef(0);
  const rafRef = useRef(0);
  const [playbackProgress, setPlaybackProgress] = useState(0);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioVisualMode, setAudioVisualMode] = useState<AudioVisualMode>("waveform");
  const [spectrogram, setSpectrogram] = useState<SpectrogramData | null>(null);
  const [spectrogramLoading, setSpectrogramLoading] = useState(false);
  const [spectrogramError, setSpectrogramError] = useState<string | null>(null);
  const [playbackError, setPlaybackError] = useState<string | null>(null);
  const statusFailed = Boolean(
    statusMessage?.toLowerCase().includes("fail") || statusMessage?.toLowerCase().startsWith("error"),
  );

  const isMidiVisual = previewKind === "midi";
  const hasPreview = Boolean(previewUrl);
  const midiTimelineDuration = midiRoll?.duration && midiRoll.duration > 0 ? midiRoll.duration : 0;

  const revokeBlobUrl = useCallback(() => {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
  }, []);

  const timelineDuration = useCallback(() => {
    if (isMidiVisual && midiTimelineDuration > 0) return midiTimelineDuration;
    if (waveformDuration > 0) return waveformDuration;
    const audio = audioRef.current;
    const dur = audio?.duration;
    return dur && Number.isFinite(dur) && dur > 0 ? dur : 0;
  }, [isMidiVisual, midiTimelineDuration, waveformDuration]);

  const setPlayheadRatio = useCallback(
    (ratio: number, options?: { commitAudio?: boolean }) => {
      const commitAudio = options?.commitAudio ?? false;
      const clamped = Math.min(1, Math.max(0, ratio));
      playheadRatioRef.current = clamped;
      const dur = timelineDuration();
      setPlaybackProgress(clamped);
      const playheadSec = dur > 0 ? clamped * dur : 0;
      if (dur > 0) {
        setPlaybackTime(playheadSec);
        setDuration(dur);
      }
      const audio = audioRef.current;
      // Expose intended playhead for Inspector meters / XYZ pads (updates on scrub
      // even before media seek settles).
      if (audio) {
        audio.dataset.playheadSec = String(playheadSec);
      }
      if (!commitAudio) return;
      if (!audio || !dur) return;
      if (!(audio.readyState >= HTMLMediaElement.HAVE_METADATA && Number.isFinite(audio.duration) && audio.duration > 0)) {
        return;
      }
      // Ratio is against the waveform/MIDI timeline; map that to media seconds.
      // Using audio.duration alone breaks when preview WAV duration disagrees (e.g. stereo flattened to mono).
      const mediaDur = audio.duration;
      const seekSec = Math.min(clamped * dur, Math.max(0, mediaDur - 0.001));
      audio.currentTime = seekSec;
      audio.dataset.playheadSec = String(seekSec);
    },
    [timelineDuration],
  );

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
      const dur = timelineDuration() || audio.duration || 0;
      if (dur > 0) {
        const ratio = Math.min(1, audio.currentTime / dur);
        playheadRatioRef.current = ratio;
        setPlaybackProgress(ratio);
        setPlaybackTime(audio.currentTime);
        setDuration(dur);
        audio.dataset.playheadSec = String(audio.currentTime);
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [stopRaf, timelineDuration]);

  const ensureBlobLoaded = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio || !previewUrl) return;

    const cacheId = cacheIdFromPreviewUrl(previewUrl);
    if (cacheId && loadedCacheIdRef.current === cacheId && blobUrlRef.current && audio.src === blobUrlRef.current) {
      if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) return;
      await waitForAudioMetadata(audio);
      return;
    }

    if (loadPromiseRef.current) {
      await loadPromiseRef.current;
      if (cacheId && loadedCacheIdRef.current === cacheId) return;
    }

    const loadTask = (async () => {
      const response = await fetch(previewUrl);
      if (!response.ok) {
        throw new Error(`Preview fetch failed (${response.status})`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      revokeBlobUrl();
      blobUrlRef.current = objectUrl;
      audio.pause();
      audio.src = objectUrl;
      audio.load();
      await waitForAudioMetadata(audio);
      if (cacheId) loadedCacheIdRef.current = cacheId;
      // Re-apply playhead after load (blob load resets currentTime to 0).
      setPlayheadRatio(playheadRatioRef.current, { commitAudio: true });
    })();

    loadPromiseRef.current = loadTask;
    try {
      await loadTask;
    } finally {
      if (loadPromiseRef.current === loadTask) {
        loadPromiseRef.current = null;
      }
    }
  }, [previewUrl, revokeBlobUrl, setPlayheadRatio]);

  const playAudio = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio || !previewUrl) return;
    try {
      await ensureBlobLoaded();
      setPlayheadRatio(playheadRatioRef.current, { commitAudio: true });
      await audio.play();
    } catch (error) {
      const blocked =
        error instanceof DOMException && error.name === "NotAllowedError";
      const reason = blocked ? "autoplay_blocked" : "preview_playback_failed";
      setPlaybackError(
        blocked
          ? "Playback was blocked by the browser. Click Play now to audition."
          : "Preview playback failed. Click Play now to retry.",
      );
      onPlaybackFailed?.(reason);
    }
  }, [ensureBlobLoaded, onPlaybackFailed, previewUrl, setPlayheadRatio]);

  const playAudioRef = useRef(playAudio);
  playAudioRef.current = playAudio;

  // Prefetch blob when preview changes so seek/play are ready.
  useEffect(() => {
    playheadRatioRef.current = 0;
    setPlaybackProgress(0);
    setPlaybackTime(0);
    setDuration(0);
    setIsPlaying(false);
    setSpectrogram(null);
    setSpectrogramError(null);
    setPlaybackError(null);
    stopRaf();
    loadedCacheIdRef.current = null;
    loadPromiseRef.current = null;

    const audio = audioRef.current;
    if (!previewUrl || !audio) {
      revokeBlobUrl();
      if (audio) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      }
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        await ensureBlobLoaded();
        if (cancelled) return;
      } catch {
        // ignore prefetch errors; play/seek will retry
      }
    })();
    return () => {
      cancelled = true;
    };
    // Only remount media when the preview clip identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewUrl, previewKind, isMidiVisual ? midiTimelineDuration : 0]);

  useEffect(() => {
    return () => {
      revokeBlobUrl();
      stopRaf();
    };
  }, [revokeBlobUrl, stopRaf]);

  useEffect(() => {
    if (waveformDuration > 0) {
      setDuration(waveformDuration);
      setPlaybackTime(playheadRatioRef.current * waveformDuration);
    }
  }, [waveformDuration]);

  useEffect(() => {
    if (audioVisualMode !== "spectrogram" || isMidiVisual || !previewUrl) {
      return;
    }
    const cacheId = cacheIdFromPreviewUrl(previewUrl);
    if (!cacheId) {
      setSpectrogram(null);
      setSpectrogramError("No preview cache for spectrogram");
      return;
    }
    let cancelled = false;
    setSpectrogramLoading(true);
    setSpectrogramError(null);
    fetchSpectrogram(cacheId, 512, 48)
      .then((data) => {
        if (cancelled) return;
        if (!data.values.length) {
          setSpectrogram(null);
          setSpectrogramError("Spectrogram unavailable for this clip");
          return;
        }
        setSpectrogram(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setSpectrogram(null);
        setSpectrogramError(err instanceof Error ? err.message : "Spectrogram failed to load");
      })
      .finally(() => {
        if (!cancelled) setSpectrogramLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [audioVisualMode, isMidiVisual, previewUrl]);

  useEffect(() => {
    if (!auditionNonce) return;
    void playAudioRef.current();
  }, [auditionNonce]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onPlay = () => {
      setPlaybackError(null);
      setIsPlaying(true);
      startRaf();
    };
    const onPlaying = () => {
      onPlaybackStarted?.();
    };
    const onPause = () => {
      setIsPlaying(false);
      stopRaf();
      const dur = timelineDuration() || audio.duration || 0;
      if (dur > 0) {
        const ratio = Math.min(1, audio.currentTime / dur);
        playheadRatioRef.current = ratio;
        setPlaybackProgress(ratio);
        setPlaybackTime(audio.currentTime);
        audio.dataset.playheadSec = String(audio.currentTime);
      }
    };
    const onEnded = () => {
      setIsPlaying(false);
      stopRaf();
      playheadRatioRef.current = 0;
      setPlaybackProgress(0);
      setPlaybackTime(0);
    };

    audio.addEventListener("play", onPlay);
    audio.addEventListener("playing", onPlaying);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);
    return () => {
      stopRaf();
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("playing", onPlaying);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
    };
  }, [onPlaybackStarted, previewUrl, startRaf, stopRaf, timelineDuration]);

  const handleSeek = useCallback(
    (ratio: number) => {
      if (!previewUrl) return;
      // Move playhead immediately; commit to audio element (blob) when ready.
      setPlayheadRatio(ratio, { commitAudio: true });
      void ensureBlobLoaded()
        .then(() => {
          setPlayheadRatio(playheadRatioRef.current, { commitAudio: true });
        })
        .catch(() => undefined);
    },
    [ensureBlobLoaded, previewUrl, setPlayheadRatio],
  );

  const handlePause = useCallback(() => {
    audioRef.current?.pause();
  }, []);

  const handleStop = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    setPlayheadRatio(0, { commitAudio: true });
    setIsPlaying(false);
    stopRaf();
  }, [setPlayheadRatio, stopRaf]);

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
  const displayDuration = duration > 0 ? duration : timelineDuration();

  const statusLine =
    !running && statusMessage && statusMessage !== "Ready" ? (
      <p className={`transport__status${statusFailed ? " transport__status--error" : ""}`}>{statusMessage}</p>
    ) : null;

  return (
    <footer className="transport">
      <div className="transport__shell">
        <div className="transport__controls">
          {statusLeds.length > 0 ? <StatusLeds leds={statusLeds} /> : null}
          <div className="transport__transport-group">
            <button
              type="button"
              className="transport__play"
              onClick={() => {
                onPlay();
                void playAudio();
              }}
              disabled={transportDisabled}
              title="Play from playhead (Space) — click waveform to set start"
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
              title="Render entire graph (⌘J / Ctrl+J)"
              aria-keyshortcuts="Meta+J Control+J"
            >
              Render all
              <kbd className="workflow-generate__kbd">⌘J</kbd>
            </button>
          ) : null}
        </div>

        <div className="transport__stage">
          <div className="transport__wave-wrap">
            {!isMidiVisual && previewUrl ? (
              <div className="transport__visual-toggle" role="group" aria-label="Audio visualization mode">
                <button
                  type="button"
                  className={audioVisualMode === "waveform" ? "active" : undefined}
                  onClick={() => setAudioVisualMode("waveform")}
                  title="Waveform"
                >
                  Wave
                </button>
                <button
                  type="button"
                  className={audioVisualMode === "spectrogram" ? "active" : undefined}
                  onClick={() => setAudioVisualMode("spectrogram")}
                  title="Spectrogram"
                >
                  Spec
                </button>
              </div>
            ) : null}
            <div className="transport__wave-visual" title={hasPreview ? "Click waveform to set playhead" : undefined}>
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
                audioVisualMode === "spectrogram" ? (
                  <SpectrogramMini
                    data={spectrogram}
                    progress={playbackProgress}
                    onSeek={handleSeek}
                    fitContainer
                    className="transport__spectrogram"
                  />
                ) : (
                  <WaveformMini
                    peaks={waveformPeaks}
                    progress={playbackProgress}
                    onSeek={handleSeek}
                    fitContainer
                    showScale
                    className="transport__waveform"
                  />
                )
              ) : (
                <div className="transport__wave-empty">
                  <WaveformMini peaks={[]} fitContainer className="transport__waveform" />
                  <p className="transport__empty">{emptyHint}</p>
                </div>
              )}
              {hasPreview && !isMidiVisual && audioVisualMode === "spectrogram" && spectrogramLoading ? (
                <div className="transport__visual-loading">Loading spectrogram…</div>
              ) : null}
              {hasPreview && !isMidiVisual && audioVisualMode === "spectrogram" && spectrogramError ? (
                <div className="transport__visual-error">{spectrogramError}</div>
              ) : null}
            </div>
            {hasPreview ? (
              <div className="transport__time-tag" aria-live="off">
                <span className="transport__time-current">{formatTimeTag(playbackTime)}</span>
                <span className="transport__time-sep">/</span>
                <span className="transport__time-duration">{formatTimeTag(displayDuration)}</span>
              </div>
            ) : null}
            {statusLine ? <div className="transport__status-overlay">{statusLine}</div> : null}
            {playbackError ? (
              <div className="transport__playback-error" role="alert">
                <span>{playbackError}</span>
                <button type="button" onClick={() => void playAudio()}>
                  Play now
                </button>
              </div>
            ) : null}
          </div>
          <audio ref={audioRef} className="transport__audio" preload="auto" />
        </div>
      </div>
    </footer>
  );
}
