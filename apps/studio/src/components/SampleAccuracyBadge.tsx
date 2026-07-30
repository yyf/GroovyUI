import { useEffect, useId, useRef, useState } from "react";

type Props = {
  note: string;
};

/** Compact canvas control — full fidelity copy on click, stays out of the patch. */
export default function SampleAccuracyBadge({ note }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="canvas__integrity" ref={rootRef}>
      {open ? (
        <div className="canvas__integrity-panel" role="note" id={panelId}>
          {note}
        </div>
      ) : null}
      <button
        type="button"
        className={`canvas__integrity-btn${open ? " canvas__integrity-btn--open" : ""}`}
        aria-expanded={open}
        aria-controls={panelId}
        title="Open sample-accurate render note"
        onClick={() => setOpen((prev) => !prev)}
      >
        sample-accurate note
      </button>
    </div>
  );
}
