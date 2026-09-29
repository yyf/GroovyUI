export type LedTone = "off" | "ok" | "busy" | "warn" | "fault";

export type StatusLedSpec = {
  id: string;
  label: string;
  tone: LedTone;
  title: string;
  /** Full report opened in a new window when the LED is warn/fault. */
  report?: string;
  /** Extra action (e.g. select the failed canvas node). */
  onInspect?: () => void;
};

type Props = {
  leds: StatusLedSpec[];
};

export function ledIsInspectable(tone: LedTone, hasInspectHandler = false): boolean {
  return tone === "fault" || tone === "warn" || hasInspectHandler;
}

export function escapeReportHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function buildStatusReportHtml(label: string, body: string): string {
  const safeLabel = escapeReportHtml(label);
  const safeBody = escapeReportHtml(body).replace(/\n/g, "<br />");
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>GroovyUI ${safeLabel}</title>
  <style>
    body { margin: 0; background: #0b0d12; color: #e8eefc; font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
    header { padding: 14px 18px; border-bottom: 1px solid #ff002b; letter-spacing: 0.16em; text-transform: uppercase; color: #ff6b7f; }
    main { padding: 18px; white-space: normal; word-break: break-word; }
  </style>
</head>
<body>
  <header>${safeLabel} fault</header>
  <main>${safeBody}</main>
</body>
</html>`;
}

export function openStatusReportWindow(label: string, body: string): Window | null {
  if (typeof window === "undefined") return null;
  const html = buildStatusReportHtml(label, body);
  // Empty URL + document.write stays in the click gesture; blob: URLs are often blocked.
  const win = window.open(
    "",
    `groovy-${label.toLowerCase()}`,
    "width=560,height=480,menubar=no,toolbar=no,location=no",
  );
  if (!win) return null;
  win.document.open();
  win.document.write(html);
  win.document.close();
  return win;
}

/** Mission-control micro LEDs for render / canvas / API state. */
export default function StatusLeds({ leds }: Props) {
  return (
    <ul className="status-leds" aria-label="Studio status">
      {leds.map((led) => {
        const inspectable = ledIsInspectable(led.tone, Boolean(led.onInspect));
        const openReport = () => {
          led.onInspect?.();
          // Inspector handlers (e.g. API status) skip the popup when no report body.
          if (led.report != null) {
            openStatusReportWindow(led.label, led.report);
          } else if (!led.onInspect) {
            openStatusReportWindow(led.label, led.title);
          }
        };
        const lamp = (
          <>
            <span className={`status-leds__lamp status-leds__lamp--${led.tone}`} aria-hidden />
            <span className="status-leds__label">{led.label}</span>
            <span className="visually-hidden">
              {led.label}: {led.title}
              {inspectable ? " — click for details" : ""}
            </span>
          </>
        );
        return (
          <li key={led.id} className="status-leds__item" title={inspectable ? `${led.title} (click for details)` : led.title}>
            {inspectable ? (
              <button type="button" className="status-leds__hit" onClick={openReport}>
                {lamp}
              </button>
            ) : (
              lamp
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function renderLedTone(args: {
  running: boolean;
  statusMessage?: string;
}): LedTone {
  const msg = (args.statusMessage ?? "").toLowerCase();
  if (args.running) return "busy";
  if (msg.includes("fail") || msg.startsWith("error") || msg.includes("crash") || msg.includes("unknown node")) {
    return "fault";
  }
  if (msg.includes("cancel")) return "warn";
  if (msg.includes("complete") || msg.includes("ready") || msg.includes("audition")) return "ok";
  return "off";
}

export function canvasLedTone(args: {
  issueCount: number;
  crashed?: boolean;
}): LedTone {
  if (args.crashed) return "fault";
  if (args.issueCount > 0) return "warn";
  return "ok";
}

export function apiLedTone(online: boolean | null): LedTone {
  if (online === null) return "off";
  return online ? "ok" : "fault";
}
