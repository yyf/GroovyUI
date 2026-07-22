import { recordActivationDiagnostic } from "./api";
import type { ActivationDiagnosticEvent } from "./types";

type DiagnosticContext = Record<string, string | number | boolean>;

type ActiveSession = {
  id: string;
  startedAt: number;
};

let activeSession: ActiveSession | null = null;
let persistQueue: Promise<void> = Promise.resolve();

function sessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID().replaceAll("-", "");
  }
  return `session_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function persist(
  session: ActiveSession,
  event: ActivationDiagnosticEvent,
  elapsedMs: number,
  context: DiagnosticContext,
): void {
  persistQueue = persistQueue
    .then(() =>
      recordActivationDiagnostic({
        session_id: session.id,
        event,
        elapsed_ms: elapsedMs,
        context,
      }),
    )
    .catch(() => {
      // Diagnostics must never interrupt the creative path.
    });
}

export function startActivationSession(context: DiagnosticContext): string {
  activeSession = {
    id: sessionId(),
    startedAt: performance.now(),
  };
  persist(activeSession, "task_started", 0, context);
  return activeSession.id;
}

export function hasActiveActivationSession(): boolean {
  return activeSession != null;
}

export function recordActivationMilestone(
  event: ActivationDiagnosticEvent,
  context: DiagnosticContext = {},
): number | null {
  if (!activeSession) return null;
  const elapsedMs = Math.max(0, Math.round(performance.now() - activeSession.startedAt));
  persist(activeSession, event, elapsedMs, context);
  return elapsedMs;
}

export function finishActivationSession(
  event: "playback_started" | "cancelled" | "failed",
  context: DiagnosticContext = {},
): number | null {
  const elapsedMs = recordActivationMilestone(event, context);
  activeSession = null;
  return elapsedMs;
}

export function resetActivationSessionForTest(): void {
  activeSession = null;
  persistQueue = Promise.resolve();
}
