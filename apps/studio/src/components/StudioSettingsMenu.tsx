import { useEffect, useRef, useState } from "react";
import { openAboutWindow, openApiStatusWindow } from "../aboutWindow";

export type StudioSettingsMenuProps = {
  groupCollapsed: boolean | null;
  paletteOpen: boolean;
  helperOpen: boolean;
  workflowBarOpen: boolean;
  onOpenIoSettings: () => void;
  onSaveWorkflow: () => void;
  onSaveAsTemplate: () => void;
  onToggleGroupCollapse: () => void;
  onTogglePalette: () => void;
  onToggleHelper: () => void;
  onToggleWorkflowBar: () => void;
  onImportComfy?: () => void;
};

export default function StudioSettingsMenu({
  groupCollapsed,
  paletteOpen,
  helperOpen,
  workflowBarOpen,
  onOpenIoSettings,
  onSaveWorkflow,
  onSaveAsTemplate,
  onToggleGroupCollapse,
  onTogglePalette,
  onToggleHelper,
  onToggleWorkflowBar,
  onImportComfy,
}: StudioSettingsMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const frame = window.requestAnimationFrame(() => {
      window.addEventListener("mousedown", onPointer);
      window.addEventListener("keydown", onKey);
    });
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const item = (label: string, action: () => void, opts?: { disabled?: boolean; warn?: boolean }) => (
    <button
      key={label}
      type="button"
      className={`studio-menu__item${opts?.warn ? " studio-menu__item--warn" : ""}`}
      disabled={opts?.disabled}
      onClick={() => {
        setOpen(false);
        action();
      }}
    >
      {label}
    </button>
  );

  return (
    <div className="studio-menu" ref={rootRef}>
      <button
        type="button"
        className={`studio-menu__trigger${open ? " studio-menu__trigger--open" : ""}`}
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        Settings
      </button>
      {open ? (
        <div className="studio-menu__panel" role="menu">
          <div className="studio-menu__section">
            <span className="studio-menu__heading">Panels</span>
            {item(paletteOpen ? "Hide node palette" : "Show node palette", onTogglePalette)}
            {item(helperOpen ? "Hide node inspector" : "Show node inspector", onToggleHelper)}
            {item(workflowBarOpen ? "Hide workflow bar" : "Show workflow bar", onToggleWorkflowBar)}
          </div>
          <div className="studio-menu__section">
            <span className="studio-menu__heading">Tools</span>
            {item("Audio & I/O…", onOpenIoSettings)}
          </div>
          <div className="studio-menu__section">
            <span className="studio-menu__heading">Workflow</span>
            {item("Save workflow", onSaveWorkflow)}
            {item("Save as template", onSaveAsTemplate)}
            {onImportComfy ? item("Import ComfyUI JSON…", onImportComfy) : null}
            {groupCollapsed != null
              ? item(groupCollapsed ? "Expand group" : "Collapse group", onToggleGroupCollapse)
              : null}
          </div>
          <div className="studio-menu__section studio-menu__section--tail">
            {item("About GroovyUI", () => openAboutWindow())}
            {item("API status", () => void openApiStatusWindow())}
          </div>
        </div>
      ) : null}
    </div>
  );
}
