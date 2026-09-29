import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { fetchStudioSettings, suggestWorkflows } from "../api";
import { PLAN_LLM_OPTIONS, type PlanLlmModelId } from "../planLlmOptions";
import type { Workflow } from "../types";
import WorkflowBlueprintPreview from "./WorkflowBlueprintPreview";

type Suggestion = {
  template_id: string;
  title: string;
  description: string;
  rationale: string;
  score: number;
  workflow: Workflow;
  source?: string;
  unknown_node_types?: string[];
};

type Props = {
  onApply: (workflow: Workflow) => void;
  onTaskStart?: () => void;
  /** Bump to open the panel (e.g. Cmd/Ctrl+G). */
  openNonce?: number;
};

function isEnterKey(event: { key: string; code?: string }): boolean {
  return event.key === "Enter" || event.code === "Enter" || event.code === "NumpadEnter";
}

/** ⌘G — LLM graph drafts only. Template match lives in Model Browser → Suggest workflow. */
export default function WorkflowGenerateButton({
  onApply,
  onTaskStart,
  openNonce = 0,
}: Props) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [claudeAvailable, setClaudeAvailable] = useState(false);
  const [llmModel, setLlmModel] = useState<PlanLlmModelId>(PLAN_LLM_OPTIONS[0].id);
  const [results, setResults] = useState<Suggestion[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const promptRef = useRef(prompt);
  const loadingRef = useRef(loading);
  const lastOpenNonce = useRef(openNonce);
  promptRef.current = prompt;
  loadingRef.current = loading;

  const selected = useMemo(
    () => results.find((item) => item.template_id === selectedId) ?? results[0] ?? null,
    [results, selectedId],
  );
  const selectedUnknown = selected?.unknown_node_types ?? [];
  const applyLocked = selectedUnknown.length > 0;
  const hasDraft = results.length > 0 && !loading;
  const llmBlocked = !claudeAvailable;

  const resetDraft = () => {
    setResults([]);
    setSelectedId(null);
    setError(null);
    setNotes(null);
  };

  const close = () => {
    setOpen(false);
  };

  useEffect(() => {
    if (openNonce === lastOpenNonce.current) return;
    lastOpenNonce.current = openNonce;
    if (openNonce > 0) {
      setOpen(true);
      queueMicrotask(() => inputRef.current?.focus());
    }
  }, [openNonce]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    void fetchStudioSettings()
      .then((settings) => setClaudeAvailable(Boolean(settings.anthropic_api_key_set)))
      .catch(() => setClaudeAvailable(false));
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (!results.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !results.some((item) => item.template_id === selectedId)) {
      setSelectedId(results[0].template_id);
    }
  }, [results, selectedId]);

  const handleGenerate = async (rawText?: string) => {
    const text = (rawText ?? promptRef.current).trim();
    if (!text || loadingRef.current) return;
    if (!claudeAvailable) {
      setError(
        "Generate needs a Claude key — set ANTHROPIC_API_KEY or Settings → Plan / Claude. For bundled templates, use Model Browser → Suggest workflow.",
      );
      return;
    }
    onTaskStart?.();
    setLoading(true);
    setError(null);
    setNotes(null);
    setResults([]);
    try {
      const data = await suggestWorkflows(text, {
        prefer_llm: true,
        llm_model: llmModel,
      });
      if (data.notes) setNotes(data.notes);
      // Template fallback belongs in Model Browser → Suggest workflow — never show it here.
      const fromLlm =
        data.mode === "llm" || data.source === "llm"
          ? (data.results ?? [])
          : (data.results ?? []).filter((item) => item.source === "llm");
      setResults(fromLlm);
      if (fromLlm.length === 0) {
        const fallback = data.fallback_reason ? ` (${data.fallback_reason})` : "";
        setError(
          `Claude returned no graph drafts${fallback}. Try another prompt, or use Model Browser → Suggest workflow for bundled templates.`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  };

  const applySelected = () => {
    if (!selected?.workflow || applyLocked) return;
    onApply(selected.workflow);
    setPrompt("");
    resetDraft();
    close();
  };

  const stage = open
    ? createPortal(
        <div className="generate-stage" role="dialog" aria-modal="true" aria-label="Generate workflow">
          <button type="button" className="generate-stage__scrim" aria-label="Close generate" onClick={close} />
          <div className={`generate-stage__sheet${hasDraft || loading ? " generate-stage__sheet--expanded" : ""}`}>
            <header className="generate-stage__header">
              <div className="generate-stage__brand">
                <span className="generate-stage__eyebrow">Generate</span>
                <strong className="generate-stage__title">Draft a patch blueprint with LLM</strong>
              </div>
              <button type="button" className="generate-stage__close" onClick={close} aria-label="Close">
                Esc
              </button>
            </header>

            <div className="generate-stage__composer">
              <div className="generate-stage__models" role="radiogroup" aria-label="Claude model">
                {PLAN_LLM_OPTIONS.map((option) => {
                  const active = llmModel === option.id;
                  return (
                    <button
                      key={option.id}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      className={`generate-stage__model${active ? " generate-stage__model--active" : ""}`}
                      title={option.description}
                      disabled={loading || !claudeAvailable}
                      onClick={() => setLlmModel(option.id)}
                    >
                      {option.label.replace(/^Claude\s+/, "")}
                    </button>
                  );
                })}
              </div>
              {llmBlocked ? (
                <p className="generate-stage__key-hint">
                  No Claude key detected. Add <code>ANTHROPIC_API_KEY</code> or Settings → Plan / Claude.
                  For bundled templates, open Model Browser → <strong>Suggest workflow</strong>.
                </p>
              ) : null}
              <textarea
                ref={inputRef}
                className="generate-stage__input"
                rows={2}
                placeholder="Describe the patch outcome — e.g. modular drone with granular texture"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                onKeyDown={(event) => {
                  if (!isEnterKey(event)) return;
                  if (event.shiftKey || event.nativeEvent.isComposing || event.repeat) return;
                  event.preventDefault();
                  event.stopPropagation();
                  void handleGenerate(event.currentTarget.value);
                }}
              />
              <div className="generate-stage__composer-actions">
                <span className="generate-stage__hint">
                  <kbd>Enter</kbd> draft · <kbd>⇧Enter</kbd> newline
                </span>
                <div className="generate-stage__composer-buttons">
                  {hasDraft ? (
                    <button type="button" className="generate-stage__secondary" onClick={resetDraft} disabled={loading}>
                      Clear draft
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="generate-stage__primary"
                    disabled={loading || !prompt.trim() || llmBlocked}
                    onClick={() => void handleGenerate()}
                  >
                    {loading ? "Drafting…" : "Draft with LLM"}
                  </button>
                </div>
              </div>
            </div>

            {error ? <p className="generate-stage__error">{error}</p> : null}
            {notes && !error && hasDraft ? <p className="generate-stage__notes">{notes}</p> : null}

            {loading ? (
              <div className="generate-stage__waiting">
                <p>
                  Waiting for Claude…
                  <span>{prompt.trim()}</span>
                </p>
              </div>
            ) : null}

            {!loading && selected?.workflow ? (
              <div className="generate-stage__review">
                {results.length > 1 ? (
                  <aside className="generate-stage__rail" aria-label="Blueprint options">
                    {results.map((item, index) => {
                      const active = selected.template_id === item.template_id;
                      const unknownCount = item.unknown_node_types?.length ?? 0;
                      return (
                        <button
                          key={item.template_id}
                          type="button"
                          className={`generate-stage__rail-item${active ? " generate-stage__rail-item--active" : ""}`}
                          onClick={() => setSelectedId(item.template_id)}
                        >
                          <span className="generate-stage__rail-index">{index + 1}</span>
                          <span className="generate-stage__rail-copy">
                            <strong>{item.title}</strong>
                            <em>{unknownCount > 0 ? `${unknownCount} unavailable` : "ready to apply"}</em>
                          </span>
                        </button>
                      );
                    })}
                  </aside>
                ) : null}
                <div className="generate-stage__blueprint">
                  <WorkflowBlueprintPreview
                    workflow={selected.workflow}
                    title={selected.title}
                    subtitle={selected.rationale || selected.description}
                    unknownNodeTypes={selected.unknown_node_types}
                    showSnapshotExport={selectedUnknown.length > 0}
                  />
                </div>
                <footer className="generate-stage__footer">
                  <p className={`generate-stage__footer-hint${applyLocked ? " generate-stage__footer-hint--warn" : ""}`}>
                    {applyLocked
                      ? "Brainstorming snapshot — Apply locked. Save JSON or image from the blueprint chrome."
                      : "All nodes available — Apply replaces the canvas with this blueprint."}
                  </p>
                  <button
                    type="button"
                    className="generate-stage__primary"
                    disabled={applyLocked}
                    onClick={applySelected}
                  >
                    Apply to canvas
                  </button>
                </footer>
              </div>
            ) : null}

            {!loading && !hasDraft && !error ? (
              <div className="generate-stage__empty">
                <p>
                  LLM drafts stay off-canvas until you Apply. For bundled template match, use Model Browser →
                  Suggest workflow.
                </p>
              </div>
            ) : null}
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <div className="workflow-generate">
      <button
        type="button"
        className={`workflow-generate__trigger${open ? " workflow-generate__trigger--open" : ""}`}
        onMouseDown={(event) => {
          if (!open) event.preventDefault();
        }}
        onClick={() => setOpen((prev) => !prev)}
        title="Generate a workflow with LLM (⌘G / Ctrl+G). Templates: Model Browser → Suggest workflow."
        aria-keyshortcuts="Meta+G Control+G"
        aria-expanded={open}
      >
        Generate
        <kbd className="workflow-generate__kbd">⌘G</kbd>
      </button>
      {stage}
    </div>
  );
}
