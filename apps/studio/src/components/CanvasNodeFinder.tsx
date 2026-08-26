import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useReactFlow } from "@xyflow/react";
import { CANVAS_MIN_ZOOM } from "../canvasViewport";
import { rankCanvasFindHits, type CanvasFindHit } from "../canvasNodeFind";

type Props = {
  hits: CanvasFindHit[];
  onClose: () => void;
  onPick: (nodeId: string) => void;
};

const VISIBLE_LIMIT = 16;

/** ⌘F dialog: search on-canvas nodes by name (type / group title) or id. */
export default function CanvasNodeFinder({ hits, onClose, onPick }: Props) {
  const { fitView } = useReactFlow();
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const ranked = useMemo(() => rankCanvasFindHits(hits, query), [hits, query]);
  const visible = useMemo(() => ranked.slice(0, VISIBLE_LIMIT), [ranked]);
  const visibleRef = useRef(visible);
  visibleRef.current = visible;

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "f") return;
      event.preventDefault();
      const list = visibleRef.current;
      if (list.length === 0) return;
      setActive((index) => (index + (event.shiftKey ? -1 : 1) + list.length) % list.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const confirm = (nodeId: string) => {
    onPick(nodeId);
    void fitView({
      nodes: [{ id: nodeId }],
      padding: 0.4,
      duration: 220,
      minZoom: CANVAS_MIN_ZOOM,
      maxZoom: 1.2,
    });
  };

  const cycle = (delta: number) => {
    if (visible.length === 0) return;
    setActive((index) => (index + delta + visible.length) % visible.length);
  };

  return createPortal(
    <div className="canvas-node-finder" role="dialog" aria-modal="true" aria-label="Find node">
      <button type="button" className="canvas-node-finder__backdrop" aria-label="Close find node" onClick={onClose} />
      <div ref={panelRef} className="canvas-node-finder__panel">
        <p className="canvas-node-finder__title">Find node</p>
        <input
          ref={inputRef}
          className="canvas-node-finder__input"
          type="text"
          value={query}
          placeholder="Node name or id…"
          aria-autocomplete="list"
          aria-activedescendant={visible[active] ? `canvas-find-${visible[active].id}` : undefined}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              cycle(1);
              return;
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              cycle(-1);
              return;
            }
            if (event.key === "Enter") {
              event.preventDefault();
              const pick = visible[active];
              if (pick) confirm(pick.id);
            }
          }}
        />
        <ul className="canvas-node-finder__list" role="listbox">
          {hits.length === 0 ? (
            <li className="canvas-node-finder__empty">No nodes on canvas</li>
          ) : visible.length === 0 ? (
            <li className="canvas-node-finder__empty">No match</li>
          ) : (
            visible.map((hit, index) => (
              <li key={hit.id}>
                <button
                  type="button"
                  id={`canvas-find-${hit.id}`}
                  role="option"
                  aria-selected={index === active}
                  className={`canvas-node-finder__option${index === active ? " canvas-node-finder__option--active" : ""}`}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => confirm(hit.id)}
                >
                  <span>{hit.name}</span>
                  <span className="canvas-node-finder__meta">{hit.id}</span>
                </button>
              </li>
            ))
          )}
        </ul>
        <p className="canvas-node-finder__hint">Enter selects · ⌘F cycles · Esc closes</p>
      </div>
    </div>,
    document.body,
  );
}
