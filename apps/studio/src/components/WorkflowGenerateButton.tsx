import { useEffect, useRef, useState } from "react";
import { suggestWorkflows } from "../api";
import type { Workflow } from "../types";

type Suggestion = {
  template_id: string;
  title: string;
  description: string;
  rationale: string;
  score: number;
  workflow: Workflow;
};

type Props = {
  onApply: (workflow: Workflow) => void;
};

export default function WorkflowGenerateButton({ onApply }: Props) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Suggestion[]>([]);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
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

  const handleGenerate = async () => {
    const text = prompt.trim();
    if (!text) return;
    setLoading(true);
    setError(null);
    setResults([]);
    try {
      const data = await suggestWorkflows(text);
      setResults(data.results);
      if (data.results.length === 0) {
        setError("No matching templates — try describing your audio task.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  };

  const applySuggestion = (suggestion: Suggestion) => {
    onApply(suggestion.workflow);
    setOpen(false);
    setPrompt("");
    setResults([]);
    setError(null);
  };

  return (
    <div className="workflow-generate" ref={rootRef}>
      <button
        type="button"
        className={`workflow-generate__trigger${open ? " workflow-generate__trigger--open" : ""}`}
        onClick={() => setOpen((prev) => !prev)}
        title="Describe a task to generate a workflow template"
      >
        Generate
      </button>
      {open ? (
        <div className="workflow-generate__panel">
          <p className="workflow-generate__hint">Describe your audio task — GroovyUI will suggest a starter workflow.</p>
          <textarea
            ref={inputRef}
            className="workflow-generate__input"
            rows={3}
            placeholder="e.g. denoise podcast dialogue and normalize to −16 LUFS"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                void handleGenerate();
              }
            }}
          />
          <div className="workflow-generate__actions">
            <button type="button" className="workflow-generate__submit" disabled={loading || !prompt.trim()} onClick={() => void handleGenerate()}>
              {loading ? "Generating…" : "Suggest workflow"}
            </button>
          </div>
          {error ? <p className="workflow-generate__error">{error}</p> : null}
          {results.length > 0 ? (
            <ul className="workflow-generate__results">
              {results.map((item) => (
                <li key={item.template_id}>
                  <button type="button" className="workflow-generate__result" onClick={() => applySuggestion(item)}>
                    <span className="workflow-generate__result-title">{item.title}</span>
                    <span className="workflow-generate__result-rationale">{item.rationale}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
