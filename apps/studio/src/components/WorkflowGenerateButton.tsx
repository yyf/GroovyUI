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

type GeneratePath = "llm" | "templates";

type Props = {
  onApply: (workflow: Workflow) => void;
  onTaskStart?: () => void;
  /** Bump to open the panel (e.g. Cmd/Ctrl+G). */
  openNonce?: number;
};

function isEnterKey(event: { key: string; code?: string }): boolean {
  return event.key === "Enter" || event.code === "Enter" || event.code === "NumpadEnter";
}

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
  const [resultMode, setResultMode] = useState<"llm" | "templates" | null>(null);
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const [claudeAvailable, setClaudeAvailable] = useState(false);
  /** Explicit user choice — never inferred from key alone at submit time. */
  const [generatePath, setGeneratePath] = useState<GeneratePath>("templates");
  const [pathInitialized, setPathInitialized] = useState(false);
  const [llmModel, setLlmModel] = useState<PlanLlmModelId>(PLAN_LLM_OPTIONS[0].id);
  const [results, setResults] = useState<Suggestion[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const promptRef = useRef(prompt);
  const loadingRef = useRef(loading);
  const lastOpenNonce = useRef(openNonce);
  promptRef.current = prompt;
  loadingRef.current = loading;

  const useLlm = generatePath === "llm";
  const selected = useMemo(
    () => results.find((item) => item.template_id === selectedId) ?? results[0] ?? null,
    [results, selectedId],
  );
  const selectedUnknown = selected?.unknown_node_types ?? [];
  const applyLocked = resultMode === "llm" && selectedUnknown.length > 0;
  const hasDraft = results.length > 0 && !loading;
  const llmBlocked = useLlm && !claudeAvailable;

  const resetDraft = () => {
    setResults([]);
    setSelectedId(null);
    setError(null);
    setNotes(null);
    setResultMode(null);
    setFallbackReason(null);
  };

  const close = () => {
    setOpen(false);
  };

  const choosePath = (path: GeneratePath) => {
    if (path === generatePath) return;
    setGeneratePath(path);
    resetDraft();
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
    void fetchStudioSettings()
      .then((settings) => {
        const keyed = Boolean(settings.anthropic_api_key_set);
        setClaudeAvailable(keyed);
        if (!pathInitialized) {
          setGeneratePath(keyed ? "llm" : "templates");
          setPathInitialized(true);
        }
      })
      .catch(() => {
        setClaudeAvailable(false);
        if (!pathInitialized) {
          setGeneratePath("templates");
          setPathInitialized(true);
        }
      });
  }, [pathInitialized]);

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
    if (useLlm && !claudeAvailable) {
      setError(
        "LLM path needs a Claude key — set ANTHROPIC_API_KEY or Settings → Plan / Claude, or switch to Templates.",
      );
      return;
    }
    onTaskStart?.();
    setLoading(true);
    setError(null);
    setNotes(null);
    setResultMode(null);
    setFallbackReason(null);
    setResults([]);
    try {
      const data = await suggestWorkflows(text, {
        prefer_llm: useLlm,
        llm_model: useLlm ? llmModel : undefined,
      });
      const mode = data.mode === "llm" || data.source === "llm" ? "llm" : "templates";
      setResultMode(mode);
      setFallbackReason(data.fallback_reason ?? null);
      if (data.notes) setNotes(data.notes);
      const nextResults = data.results ?? [];
      setResults(nextResults);
      if (nextResults.length === 0) {
        setError(
          useLlm
            ? "Claude returned no graph drafts — try another prompt."
            : "No matching templates — try describing your audio task.",
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

  const submitLabel = loading
    ? useLlm
      ? "Drafting…"
      : "Matching…"
    : useLlm
      ? "Draft with LLM"
      : "Match templates";

  const stage = open
    ? createPortal(
        <div className="generate-stage" role="dialog" aria-modal="true" aria-label="Generate workflow">
          <button type="button" className="generate-stage__scrim" aria-label="Close generate" onClick={close} />
          <div className={`generate-stage__sheet${hasDraft || loading ? " generate-stage__sheet--expanded" : ""}`}>
            <header className="generate-stage__header">
              <div className="generate-stage__brand">
                <span className="generate-stage__eyebrow">Generate</span>
                <strong className="generate-stage__title">
                  {useLlm ? "Draft a patch blueprint" : "Match a bundled template"}
                </strong>
              </div>
              <button type="button" className="generate-stage__close" onClick={close} aria-label="Close">
                Esc
              </button>
            </header>

            <div className="generate-stage__path" role="radiogroup" aria-label="Generate path">
              <button
                type="button"
                role="radio"
                aria-checked={useLlm}
                className={`generate-stage__path-btn${useLlm ? " generate-stage__path-btn--active" : ""}`}
                disabled={loading}
                onClick={() => choosePath("llm")}
              >
                <strong>With LLM</strong>
                <span>Claude drafts a new blueprint (BYOK)</span>
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={!useLlm}
                className={`generate-stage__path-btn${!useLlm ? " generate-stage__path-btn--active" : ""}`}
                disabled={loading}
                onClick={() => choosePath("templates")}
              >
                <strong>Without LLM</strong>
                <span>Deterministic match of bundled templates</span>
              </button>
            </div>

            <div className="generate-stage__composer">
              {useLlm ? (
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
              ) : null}
              {llmBlocked ? (
                <p className="generate-stage__key-hint">
                  No Claude key detected. Add <code>ANTHROPIC_API_KEY</code> or Settings → Plan / Claude, or choose{" "}
                  <strong>Without LLM</strong>.
                </p>
              ) : null}
              <textarea
                ref={inputRef}
                className="generate-stage__input"
                rows={2}
                placeholder={
                  useLlm
                    ? "Describe the patch outcome — e.g. modular drone with granular texture"
                    : "Describe your audio task — e.g. denoise podcast then normalize"
                }
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
                  <kbd>Enter</kbd> {useLlm ? "draft" : "match"} · <kbd>⇧Enter</kbd> newline
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
                    {submitLabel}
                  </button>
                </div>
              </div>
            </div>

            {error ? <p className="generate-stage__error">{error}</p> : null}
            {notes && !error && hasDraft ? <p className="generate-stage__notes">{notes}</p> : null}

            {loading ? (
              <div className="generate-stage__waiting">
                <p>
                  {useLlm ? "Waiting for Claude…" : "Matching templates…"}
                  <span>{prompt.trim()}</span>
                </p>
              </div>
            ) : null}

            {!loading && resultMode === "llm" && selected?.workflow ? (
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

            {!loading && resultMode === "templates" && results.length > 0 ? (
              <ul className="generate-stage__templates">
                {fallbackReason && useLlm ? (
                  <li className="generate-stage__templates-note">
                    Claude returned no drafts ({fallbackReason}) — showing template matches. Switch to{" "}
                    <strong>Without LLM</strong> for intentional template search.
                  </li>
                ) : null}
                {results.map((item) => (
                  <li key={item.template_id}>
                    <button
                      type="button"
                      className="generate-stage__template"
                      onClick={() => {
                        onApply(item.workflow);
                        setPrompt("");
                        resetDraft();
                        close();
                      }}
                    >
                      <strong>{item.title}</strong>
                      <span>{item.rationale}</span>
                      <em>Apply &amp; review compliance →</em>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            {!loading && !hasDraft && !error ? (
              <div className="generate-stage__empty">
                <p>
                  {useLlm
                    ? "LLM drafts stay off-canvas until you Apply. Unavailable nodes stay visible for snapshot export — no silent template swap when Claude returns a graph."
                    : "Without LLM matches bundled templates only — same prompt always yields the same ranking."}
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
        title="Generate a workflow — choose LLM or templates (⌘G / Ctrl+G)"
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
