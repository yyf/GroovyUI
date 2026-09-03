import { useEffect, useMemo, useRef, useState } from "react";
import type { TemplateListItem } from "../api";
import { groupBundledTemplatesByDomain, templatesVisibleInUi } from "../templateUi";

type Props = {
  templates: TemplateListItem[];
  selectedId: string;
  onSelect: (templateId: string) => void;
  onDeleteUserTemplate?: (templateId: string) => void | Promise<void>;
};

export default function TemplateSelector({
  templates,
  selectedId,
  onSelect,
  onDeleteUserTemplate,
}: Props) {
  const [open, setOpen] = useState(false);
  const [openDomainId, setOpenDomainId] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const visibleTemplates = useMemo(
    () => templatesVisibleInUi(templates, selectedId),
    [templates, selectedId],
  );
  const domainGroups = useMemo(
    () => groupBundledTemplatesByDomain(visibleTemplates),
    [visibleTemplates],
  );
  const userTemplates = useMemo(
    () => visibleTemplates.filter((template) => template.source === "user"),
    [visibleTemplates],
  );
  const selected = templates.find((template) => template.id === selectedId);

  const wasMenuOpen = useRef(false);

  useEffect(() => {
    if (!open) {
      wasMenuOpen.current = false;
      setOpenDomainId(null);
      return;
    }
    if (wasMenuOpen.current) return;
    wasMenuOpen.current = true;
    const selectedGroup = domainGroups.find((group) =>
      group.templates.some((template) => template.id === selectedId),
    );
    // Expand the domain that holds the current selection — except Start, which
    // stays collapsed so the menu opens as a category list rather than Hello Groovy.
    const nextDomainId =
      selectedGroup && selectedGroup.domain.id !== "start" ? selectedGroup.domain.id : null;
    setOpenDomainId(nextDomainId);
  }, [open, domainGroups, selectedId]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (openDomainId) setOpenDomainId(null);
        else setOpen(false);
      }
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
  }, [open, openDomainId]);

  const pickTemplate = (templateId: string) => {
    setOpen(false);
    setOpenDomainId(null);
    if (templateId !== selectedId) onSelect(templateId);
  };

  const renderBundledOption = (template: TemplateListItem) => (
    <li key={template.id}>
      <button
        type="button"
        role="menuitem"
        aria-current={template.id === selectedId ? "true" : undefined}
        className={`template-select__option${template.id === selectedId ? " template-select__option--active" : ""}`}
        onClick={() => pickTemplate(template.id)}
      >
        {template.title}
      </button>
    </li>
  );

  const renderUserOption = (template: TemplateListItem) => (
    <li key={template.id} className="template-select__row">
      <button
        type="button"
        role="menuitem"
        aria-current={template.id === selectedId ? "true" : undefined}
        className={`template-select__option${template.id === selectedId ? " template-select__option--active" : ""}`}
        onClick={() => pickTemplate(template.id)}
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
        aria-haspopup="menu"
        title={selected?.description || undefined}
      >
        {selected?.title ?? "Workflow Templates"}
      </button>
      {open ? (
        <ul className="template-select__menu" role="menu" aria-label="Workflow Templates">
          <li className="template-select__group" role="presentation">
            <span className="template-select__group-label">Default templates</span>
            <ul className="template-select__group-list" role="none">
              {domainGroups.length > 0 ? (
                domainGroups.map(({ domain, templates: domainTemplates }) => {
                  const isOpen = openDomainId === domain.id;
                  const containsSelected = domainTemplates.some((t) => t.id === selectedId);
                  return (
                    <li
                      key={domain.id}
                      className={`template-select__domain${isOpen ? " template-select__domain--open" : ""}`}
                      role="none"
                    >
                      <button
                        type="button"
                        className={[
                          "template-select__domain-btn",
                          isOpen ? "template-select__domain-btn--open" : "",
                          containsSelected ? "template-select__domain-btn--active" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        role="menuitem"
                        aria-haspopup="menu"
                        aria-expanded={isOpen}
                        onClick={() =>
                          setOpenDomainId((prev) => (prev === domain.id ? null : domain.id))
                        }
                      >
                        <span>{domain.label}</span>
                        <span className="template-select__domain-meta" aria-hidden>
                          {domainTemplates.length}
                          <span className="template-select__domain-chevron">{isOpen ? "▾" : "▸"}</span>
                        </span>
                      </button>
                      {isOpen ? (
                        <ul
                          className="template-select__submenu"
                          role="menu"
                          aria-label={domain.label}
                        >
                          {domainTemplates.map(renderBundledOption)}
                        </ul>
                      ) : null}
                    </li>
                  );
                })
              ) : (
                <li className="template-select__empty">No default templates</li>
              )}
            </ul>
          </li>
          <li className="template-select__group" role="presentation">
            <span className="template-select__group-label">Your templates</span>
            <ul className="template-select__group-list" role="none">
              {userTemplates.length > 0 ? (
                userTemplates.map(renderUserOption)
              ) : (
                <li className="template-select__empty">Use Settings → Save to Your templates</li>
              )}
            </ul>
          </li>
        </ul>
      ) : null}
    </div>
  );
}
