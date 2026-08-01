import { useEffect, useRef, useState } from "react";
import {
  openAboutWindow,
  openApiStatusWindow,
  openTemplateLicenseWindow,
} from "../aboutWindow";

export type StudioSettingsMenuProps = {
  groupCollapsed: boolean | null;
  paletteOpen: boolean;
  helperOpen: boolean;
  workflowBarOpen: boolean;
  onImportWorkflow: (file: File) => void;
  onSaveAsTemplate: () => void;
  onToggleGroupCollapse: () => void;
  onTogglePalette: () => void;
  onToggleHelper: () => void;
  onToggleWorkflowBar: () => void;
  onOpenStudioSettings: () => void;
};

export default function StudioSettingsMenu({
  groupCollapsed,
  paletteOpen,
  helperOpen,
  workflowBarOpen,
  onImportWorkflow,
  onSaveAsTemplate,
  onToggleGroupCollapse,
  onTogglePalette,
  onToggleHelper,
  onToggleWorkflowBar,
  onOpenStudioSettings,
}: StudioSettingsMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const importInputRef = useRef<HTMLInputElement>(null);

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

  useEffect(() => {
    const onImportShortcut = (event: KeyboardEvent) => {
      if (
        event.repeat ||
        (!event.metaKey && !event.ctrlKey) ||
        event.altKey ||
        event.shiftKey ||
        event.key.toLowerCase() !== "i"
      ) {
        return;
      }
      event.preventDefault();
      setOpen(false);
      importInputRef.current?.click();
    };
    window.addEventListener("keydown", onImportShortcut);
    return () => window.removeEventListener("keydown", onImportShortcut);
  }, []);

  const item = (
    label: string,
    action: () => void,
    opts?: { disabled?: boolean; warn?: boolean; shortcut?: string; ariaKeyShortcuts?: string },
  ) => (
    <button
      key={label}
      type="button"
      className={`studio-menu__item${opts?.warn ? " studio-menu__item--warn" : ""}`}
      disabled={opts?.disabled}
      aria-keyshortcuts={opts?.ariaKeyShortcuts}
      onClick={() => {
        setOpen(false);
        action();
      }}
    >
      <span>{label}</span>
      {opts?.shortcut ? <kbd className="workflow-generate__kbd">{opts.shortcut}</kbd> : null}
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
            <span className="studio-menu__heading">Workflow</span>
            {item("Import workflow JSON…", () => importInputRef.current?.click(), {
              shortcut: "⌘I",
              ariaKeyShortcuts: "Meta+I Control+I",
            })}
            {item("Save to Your templates", onSaveAsTemplate)}
            {groupCollapsed != null
              ? item(groupCollapsed ? "Expand group" : "Collapse group", onToggleGroupCollapse)
              : null}
          </div>
          <div className="studio-menu__section studio-menu__section--tail">
            {item("Studio settings…", onOpenStudioSettings)}
            {item("Template licenses…", () => openTemplateLicenseWindow())}
            {item("About GroovyUI", () => openAboutWindow())}
            {item("API status", () => void openApiStatusWindow())}
          </div>
        </div>
      ) : null}
      <input
        ref={importInputRef}
        type="file"
        accept=".json,application/json"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onImportWorkflow(file);
        }}
      />
    </div>
  );
}
