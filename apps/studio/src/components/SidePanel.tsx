import type { ReactNode } from "react";

type Props = {
  side: "left" | "right";
  label: string;
  open: boolean;
  onToggle: () => void;
  /** Expand body width (multi-param Config, Subgraph, compare, settings). */
  wide?: boolean;
  /** Freeze width transitions during canvas marquee select. */
  selectionBusy?: boolean;
  children: ReactNode;
};

export default function SidePanel({
  side,
  label,
  open,
  onToggle,
  wide = false,
  selectionBusy = false,
  children,
}: Props) {
  return (
    <aside
      className={[
        "side-panel",
        `side-panel--${side}`,
        open ? "side-panel--open" : "",
        open && wide ? "side-panel--wide" : "",
        selectionBusy ? "side-panel--selection-busy" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <button
        type="button"
        className="side-panel__tab"
        onClick={onToggle}
        title={open ? `Hide ${label}` : `Show ${label}`}
        aria-expanded={open}
      >
        <span className="side-panel__tab-label">{label}</span>
      </button>
      {open ? <div className="side-panel__body">{children}</div> : null}
    </aside>
  );
}
