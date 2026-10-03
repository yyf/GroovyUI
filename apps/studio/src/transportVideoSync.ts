/**
 * Keep on-canvas PreviewVideo elements locked to the transport `<audio>` clock.
 * Space / transport Play·Pause·Seek is the master; in-node video is muted picture.
 */

const TRANSPORT_AUDIO = ".transport__audio";
const NODE_VIDEO = ".groovy-node__video-player";
const DRIFT_SEC = 0.1;

function nodeVideos(): HTMLVideoElement[] {
  return Array.from(document.querySelectorAll<HTMLVideoElement>(NODE_VIDEO));
}

function syncVideosTo(audio: HTMLAudioElement, force = false): void {
  const t = audio.currentTime;
  if (!Number.isFinite(t)) return;
  for (const video of nodeVideos()) {
    if (!force && Math.abs(video.currentTime - t) <= DRIFT_SEC) continue;
    try {
      video.currentTime = t;
    } catch {
      /* seeking before metadata */
    }
  }
}

export function attachTransportVideoSync(): () => void {
  const audio = document.querySelector<HTMLAudioElement>(TRANSPORT_AUDIO);
  if (!audio) return () => {};

  let raf = 0;

  const stopRaf = () => {
    if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
  };

  const tick = () => {
    if (!audio.paused && !audio.ended) {
      syncVideosTo(audio, false);
      raf = requestAnimationFrame(tick);
    } else {
      raf = 0;
    }
  };

  const onPlay = () => {
    for (const video of nodeVideos()) {
      video.muted = true;
    }
    syncVideosTo(audio, true);
    for (const video of nodeVideos()) {
      void video.play().catch(() => {
        /* autoplay / not ready */
      });
    }
    stopRaf();
    raf = requestAnimationFrame(tick);
  };

  const onPauseOrEnd = () => {
    stopRaf();
    for (const video of nodeVideos()) {
      video.pause();
    }
    syncVideosTo(audio, true);
  };

  const onSeeked = () => {
    syncVideosTo(audio, true);
    if (!audio.paused && !audio.ended) {
      for (const video of nodeVideos()) {
        void video.play().catch(() => {});
      }
      if (!raf) raf = requestAnimationFrame(tick);
    }
  };

  audio.addEventListener("play", onPlay);
  audio.addEventListener("pause", onPauseOrEnd);
  audio.addEventListener("ended", onPauseOrEnd);
  audio.addEventListener("seeked", onSeeked);

  // If transport is already playing when a PreviewVideo mounts after render.
  if (!audio.paused && !audio.ended) {
    onPlay();
  }

  return () => {
    stopRaf();
    audio.removeEventListener("play", onPlay);
    audio.removeEventListener("pause", onPauseOrEnd);
    audio.removeEventListener("ended", onPauseOrEnd);
    audio.removeEventListener("seeked", onSeeked);
  };
}
