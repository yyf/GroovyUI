import { useEffect, useMemo, useRef, useState } from "react";
import { useReactFlow } from "@xyflow/react";
import { API } from "../api";
import { isPaletteVisible } from "./NodePalette";

type Props = {
  clientX: number;
  clientY: number;
  onClose: () => void;
  onPick: (nodeType: string, flowPos: { x: number; y: number }) => void;
  /** ⌘⇧D — full node list; otherwise ISMIR-demo nodes only. */
  studioDevMode?: boolean;
};

/** Right-click canvas typeahead: filter node types, Enter to drop at click. */
export default function CanvasNodePicker({
  clientX,
  clientY,
  onClose,
  onPick,
  studioDevMode = false,
}: Props) {
  const { screenToFlowPosition } = useReactFlow();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [active, setActive] = useState(0);

  useEffect(() => {
    fetch(`${API}/api/nodes`)
      .then((r) => r.json())
      .then((d) => {
        const list = (d.nodes as Array<{ type: string; category: string }>)
          .filter((n) => isPaletteVisible(n, studioDevMode))
          .map((n) => n.type)
          .sort((a, b) => a.localeCompare(b));
        setTypes(list);
      })
      .catch(() => setTypes([]));
  }, [studioDevMode]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      if (event.button === 2) return;
      if (!rootRef.current?.contains(event.target as Node)) onClose();
    };
    // Defer so the opening right-click cannot instantly dismiss the picker.
    const timer = window.setTimeout(() => {
      window.addEventListener("mousedown", onPointer);
    }, 0);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("mousedown", onPointer);
    };
  }, [onClose]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return types;
    return types.filter((t) => t.toLowerCase().includes(q));
  }, [query, types]);

  const visible = useMemo(() => filtered.slice(0, 12), [filtered]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  const confirm = (nodeType: string) => {
    const flowPos = screenToFlowPosition({ x: clientX, y: clientY });
    onPick(nodeType, flowPos);
  };

  const left = Math.min(clientX, window.innerWidth - 220);
  const top = Math.min(clientY, window.innerHeight - 260);

  return (
    <div
      ref={rootRef}
      className="canvas-node-picker"
      style={{ left, top }}
      role="listbox"
      aria-label="Add node"
    >
      <input
        ref={inputRef}
        className="canvas-node-picker__input"
        type="text"
        value={query}
        placeholder="Add node…"
        aria-autocomplete="list"
        aria-activedescendant={visible[active] ? `canvas-node-${visible[active]}` : undefined}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            onClose();
            return;
          }
          if (event.key === "ArrowDown") {
            event.preventDefault();
            if (visible.length === 0) return;
            setActive((i) => (i + 1) % visible.length);
            return;
          }
          if (event.key === "ArrowUp") {
            event.preventDefault();
            if (visible.length === 0) return;
            setActive((i) => (i - 1 + visible.length) % visible.length);
            return;
          }
          if (event.key === "Enter") {
            event.preventDefault();
            const pick = visible[active];
            if (pick) confirm(pick);
          }
        }}
      />
      <ul className="canvas-node-picker__list">
        {visible.length === 0 ? (
          <li className="canvas-node-picker__empty">No match</li>
        ) : (
          visible.map((type, index) => (
            <li key={type}>
              <button
                type="button"
                id={`canvas-node-${type}`}
                role="option"
                aria-selected={index === active}
                className={`canvas-node-picker__option${index === active ? " canvas-node-picker__option--active" : ""}`}
                onMouseEnter={() => setActive(index)}
                onClick={() => confirm(type)}
              >
                {type}
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
