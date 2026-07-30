import { useEffect, useState } from "react";

/** Tiny rAF FPS readout for canvas perf — display-only, no interaction. */
export default function FpsMeter() {
  const [fps, setFps] = useState(0);

  useEffect(() => {
    let frames = 0;
    let last = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      frames += 1;
      const elapsed = now - last;
      if (elapsed >= 500) {
        setFps(Math.round((frames * 1000) / elapsed));
        frames = 0;
        last = now;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="canvas__fps" title={`${fps} frames per second`} aria-hidden>
      {fps > 0 ? fps : "—"}
    </div>
  );
}
