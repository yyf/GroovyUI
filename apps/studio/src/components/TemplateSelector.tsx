import { useEffect, useRef, useState } from "react";

type Template = { id: string; title: string };

type Props = {
  templates: Template[];
  selectedId: string;
  onSelect: (templateId: string) => void;
};

export default function TemplateSelector({ templates, selectedId, onSelect }: Props) {
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
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="template-select" ref={rootRef}>
      <button
        type="button"
        className={`template-select__trigger${open ? " template-select__trigger--open" : ""}`}
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        Workflow template
      </button>
      {open ? (
        <ul className="template-select__menu" role="listbox" aria-label="Workflow template">
          {templates.map((template) => (
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
          ))}
        </ul>
      ) : null}
    </div>
  );
}
