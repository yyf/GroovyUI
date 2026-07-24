import { useEffect, useMemo, useRef, useState } from "react";
import type { TemplateListItem } from "../api";
import { templatesVisibleInUi } from "../templateUi";

type Props = {
  templates: TemplateListItem[];
  selectedId: string;
  onSelect: (templateId: string) => void;
  onDeleteUserTemplate?: (templateId: string) => void | Promise<void>;
};

function groupTemplates(templates: TemplateListItem[]) {
  const bundled = templates.filter((template) => template.source !== "user");
  const user = templates.filter((template) => template.source === "user");
  return { bundled, user };
}

export default function TemplateSelector({
  templates,
  selectedId,
  onSelect,
  onDeleteUserTemplate,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const visibleTemplates = useMemo(
    () => templatesVisibleInUi(templates, selectedId),
    [templates, selectedId],
  );
  const { bundled, user } = useMemo(() => groupTemplates(visibleTemplates), [visibleTemplates]);
  const selected = templates.find((template) => template.id === selectedId);

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

  const renderBundledOption = (template: TemplateListItem) => (
    <li key={template.id}>
      <button
        type="button"
        role="option"
        aria-selected={template.id === selectedId}
        className={`template-select__option${template.id === selectedId ? " template-select__option--active" : ""}`}
        onClick={() => {
          setOpen(false);
          if (template.id !== selectedId) onSelect(template.id);
        }}
      >
        {template.title}
      </button>
    </li>
  );

  const renderUserOption = (template: TemplateListItem) => (
    <li key={template.id} className="template-select__row">
      <button
        type="button"
        role="option"
        aria-selected={template.id === selectedId}
        className={`template-select__option${template.id === selectedId ? " template-select__option--active" : ""}`}
        onClick={() => {
          setOpen(false);
          if (template.id !== selectedId) onSelect(template.id);
        }}
      >
        {template.title}
      </button>
      {onDeleteUserTemplate ? (
        <button
          type="button"
          className="template-select__remove"
          title={`Remove “${template.title}”`}
          aria-label={`Remove ${template.title}`}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!window.confirm(`Remove “${template.title}” from Your templates?`)) return;
            void onDeleteUserTemplate(template.id);
          }}
        >
          ×
        </button>
      ) : null}
    </li>
  );

  return (
    <div className="template-select" ref={rootRef}>
      <button
        type="button"
        className={`template-select__trigger${open ? " template-select__trigger--open" : ""}`}
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="listbox"
        title={selected?.description || undefined}
      >
        {selected?.title ?? "Workflow Templates"}
      </button>
      {open ? (
        <ul className="template-select__menu" role="listbox" aria-label="Workflow Templates">
          <li className="template-select__group" role="presentation">
            <span className="template-select__group-label">Default templates</span>
            <ul className="template-select__group-list">
              {bundled.length > 0 ? bundled.map(renderBundledOption) : (
                <li className="template-select__empty">No default templates</li>
              )}
            </ul>
          </li>
          <li className="template-select__group" role="presentation">
            <span className="template-select__group-label">Your templates</span>
            <ul className="template-select__group-list">
              {user.length > 0 ? user.map(renderUserOption) : (
                <li className="template-select__empty">Use Settings → Save to Your templates</li>
              )}
            </ul>
          </li>
        </ul>
      ) : null}
    </div>
  );
}
