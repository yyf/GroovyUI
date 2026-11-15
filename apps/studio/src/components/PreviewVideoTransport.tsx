import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { projectMediaUrl } from "../api";

type Props = {
  path: string;
  width: number;
  height: number;
  selected?: boolean;
  onResizePointerDown: (event: ReactPointerEvent<HTMLSpanElement>) => void;
};

function formatClock(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "0:00";
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

/**
 * On-canvas PreviewVideo picture + mini transport (play / scrub).
 * Global transport remains master when it is playing (muted sync via transportVideoSync);
 * local controls drive the clip when Space has nothing to audition (e.g. pure T2V).
 */
export function PreviewVideoTransport({
  path,
  width,
  height,
  selected,
  onResizePointerDown,
}: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const scrubbing = useRef(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onMeta = () => setDuration(Number.isFinite(video.duration) ? video.duration : 0);
    const onTime = () => {
      if (!scrubbing.current) setCurrent(video.currentTime);
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => {
      setPlaying(false);
      setCurrent(video.duration || 0);
    };

    video.addEventListener("loadedmetadata", onMeta);
    video.addEventListener("durationchange", onMeta);
    video.addEventListener("timeupdate", onTime);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("ended", onEnded);
    onMeta();
    setPlaying(!video.paused && !video.ended);

    return () => {
      video.removeEventListener("loadedmetadata", onMeta);
      video.removeEventListener("durationchange", onMeta);
      video.removeEventListener("timeupdate", onTime);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("ended", onEnded);
    };
  }, [path]);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    const transport = document.querySelector<HTMLAudioElement>(".transport__audio");
    const transportDriving = Boolean(transport && !transport.paused && !transport.ended);
    if (transportDriving) {
      // Hand control back to the global bar when it is already the master clock.
      if (transport.paused) void transport.play().catch(() => {});
      else transport.pause();
      return;
    }
    if (video.paused || video.ended) {
      video.muted = false;
      void video.play().catch(() => {});
    } else {
      video.pause();
    }
  }, []);

  const onScrubInput = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const video = videoRef.current;
    if (!video) return;
    const next = Number(event.target.value);
    if (!Number.isFinite(next)) return;
    scrubbing.current = true;
    video.currentTime = next;
    setCurrent(next);
  }, []);

  const onScrubEnd = useCallback(() => {
    scrubbing.current = false;
  }, []);

  const max = duration > 0 ? duration : 0;

  return (
    <div
      className={`groovy-node__video nodrag nopan${selected ? " groovy-node__video--selected" : ""}`}
      style={{ width }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <div className="groovy-node__video-frame" style={{ width, height }}>
        <video
          ref={videoRef}
          key={path}
          playsInline
          preload="auto"
          src={projectMediaUrl(path)}
          className="groovy-node__video-player"
          title="Play here, or Space when transport has audio"
        />
        <span
          className="groovy-node__video-resize"
          title="Drag to scale (aspect locked)"
          onPointerDown={onResizePointerDown}
        />
      </div>
      <div className="groovy-node__video-transport" role="group" aria-label="Video transport">
        <button
          type="button"
          className="groovy-node__video-play"
          aria-label={playing ? "Pause" : "Play"}
          onClick={togglePlay}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <input
          type="range"
          className="groovy-node__video-scrub"
          min={0}
          max={max || 1}
          step={0.01}
          value={Math.min(current, max || 1)}
          disabled={max <= 0}
          aria-label="Seek"
          onChange={onScrubInput}
          onPointerUp={onScrubEnd}
          onKeyUp={onScrubEnd}
        />
        <span className="groovy-node__video-time" aria-hidden="true">
          {formatClock(current)}/{formatClock(duration)}
        </span>
      </div>
    </div>
  );
}
