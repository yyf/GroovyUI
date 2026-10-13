import { useEffect, useState } from "react";
import {
  estimateCreativePlanMs,
  formatCreativePlanTiming,
  type CreativeTabSession,
} from "../creativeTabSession";

type Props = {
  session: CreativeTabSession;
  onDismiss: () => void;
};

/** Thin canvas HUD for Tab Creative Agent — mission-control, not a Generate sheet. */
export default function CreativeTabHud({ session, onDismiss }: Props) {
  const step =
    !session.planning && session.cursor < session.steps.length
      ? session.steps[session.cursor]
      : null;
  const progress =
    session.steps.length > 0
      ? `${Math.min(session.cursor + 1, session.steps.length)}/${session.steps.length}`
      : null;

  const [elapsedMs, setElapsedMs] = useState(0);
  const estimateMs = estimateCreativePlanMs();

  useEffect(() => {
    if (!session.planning || session.planningStartedAt == null) {
      setElapsedMs(0);
      return;
    }
    const started = session.planningStartedAt;
    const tick = () => setElapsedMs(Math.max(0, performance.now() - started));
    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [session.planning, session.planningStartedAt]);

  return (
    <div
      className={`creative-tab-hud mod-frame${session.notice ? " creative-tab-hud--flash" : ""}${session.planning ? " creative-tab-hud--planning" : ""}`}
      role="status"
      aria-live="polite"
    >
      <div className="creative-tab-hud__main">
        <div className="creative-tab-hud__eyebrow-row">
          <span className="creative-tab-hud__eyebrow">Creative</span>
          {session.planning ? (
            <span className="creative-tab-hud__agent-pill" title="Anthropic Claude via BYOK">
              AI agent
            </span>
          ) : null}
        </div>
        {session.planning ? (
          <>
            <strong className="creative-tab-hud__title">Planning with AI agent…</strong>
            <span className="creative-tab-hud__rationale">
              {formatCreativePlanTiming(elapsedMs, estimateMs)}
            </span>
          </>
        ) : step ? (
          <>
            <strong className="creative-tab-hud__title">
              {progress ? `${progress} · ` : ""}
              {step.title}
            </strong>
            {session.notice ? (
              <span className="creative-tab-hud__notice">{session.notice}</span>
            ) : step.rationale ? (
              <span className="creative-tab-hud__rationale">{step.rationale}</span>
            ) : null}
            {step.remapped_from && step.action.type === "add_node" ? (
              <span className="creative-tab-hud__notice">
                Remapped “{step.remapped_from}” → {step.action.node.type}
              </span>
            ) : null}
            {step.remapped_from && step.action.type === "propose_note" ? (
              <span className="creative-tab-hud__notice">
                “{step.remapped_from}” isn’t in this build — Tab accepts as a note
              </span>
            ) : null}
            {step.apply_locked ? (
              <span className="creative-tab-hud__notice">
                Locked — unavailable node type. Shift+Tab to skip.
              </span>
            ) : null}
          </>
        ) : session.steps.length > 0 && session.cursor >= session.steps.length ? (
          <>
            <strong className="creative-tab-hud__title">Plan complete</strong>
            {session.notice ? (
              <span className="creative-tab-hud__notice">{session.notice}</span>
            ) : (
              <span className="creative-tab-hud__rationale">Esc clears ghosts</span>
            )}
          </>
        ) : (
          <strong className="creative-tab-hud__title">{session.goal || "No steps"}</strong>
        )}
      </div>
      <div className="creative-tab-hud__keys">
        {session.planning ? (
          <span className="creative-tab-hud__wait">Waiting on Claude</span>
        ) : step ? (
          <>
            <span>
              <kbd>Tab</kbd> approve
            </span>
            <span>
              <kbd>⇧Tab</kbd> skip
            </span>
          </>
        ) : null}
        <button type="button" className="creative-tab-hud__dismiss" onClick={onDismiss} title="Dismiss">
          <kbd>Esc</kbd>
        </button>
      </div>
    </div>
  );
}
