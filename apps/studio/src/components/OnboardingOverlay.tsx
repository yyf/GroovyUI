import type { Workflow } from "../types";

const STORAGE_KEY = "groovy_onboarding_v1";

type Props = {
  open: boolean;
  onClose: () => void;
  onStartHello: () => void;
};

export function isOnboardingComplete(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "done";
  } catch {
    return false;
  }
}

export function markOnboardingComplete(): void {
  try {
    localStorage.setItem(STORAGE_KEY, "done");
  } catch {
    // ignore storage failures
  }
}

export default function OnboardingOverlay({ open, onClose, onStartHello }: Props) {
  if (!open) return null;

  return (
    <div className="onboarding-backdrop">
      <div className="onboarding">
        <h2>Welcome to GroovyUI</h2>
        <p>Patch AI audio like a modular synth. Render sample-accurate previews without leaving the graph.</p>
        <ol className="onboarding__steps">
          <li>
            <strong>Start simple</strong> — try the Hello Groovy template (Load → Normalize → Preview).
          </li>
          <li>
            <strong>Press Play</strong> — Audition the selected node after you render it.
          </li>
          <li>
            <strong>Cmd+K</strong> — search models, get recommendations, or suggest a workflow.
          </li>
        </ol>
        <div className="onboarding__actions">
          <button
            type="button"
            className="onboarding__primary"
            onClick={() => {
              markOnboardingComplete();
              onStartHello();
              onClose();
            }}
          >
            Start with Hello Groovy
          </button>
          <button
            type="button"
            onClick={() => {
              markOnboardingComplete();
              onClose();
            }}
          >
            Skip — I know the ropes
          </button>
        </div>
      </div>
    </div>
  );
}

export function shouldShowOnboarding(_workflow: Workflow | null): boolean {
  return !isOnboardingComplete();
}
