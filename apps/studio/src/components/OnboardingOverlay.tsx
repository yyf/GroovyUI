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
        <p>Patch AI audio like a modular synth. Render sample-accurate previews, then save files from the graph.</p>
        <ol className="onboarding__steps">
          <li>
            <strong>Search &amp; install</strong> — Cmd+K → Model Browser → install hero models.
          </li>
          <li>
            <strong>Patch &amp; render</strong> — open a featured template, wire the chain, press Render.
          </li>
          <li>
            <strong>Audition</strong> — Play previews cached from your last render (not live inference).
          </li>
          <li>
            <strong>Compliance</strong> — review license, provenance, and authenticity.
          </li>
          <li>
            <strong>Share JSON</strong> — Share opens a Save dialog defaulted to{" "}
            <code>workspace/share</code>.
          </li>
          <li>
            <strong>Save/export audio</strong> — render the SaveAudio node; files land under <code>exports/</code>.
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
            Start with Podcast Denoise
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
