export type LedTone = "off" | "ok" | "busy" | "warn" | "fault";

export type StatusLedSpec = {
  id: string;
  label: string;
  tone: LedTone;
  title: string;
};

type Props = {
  leds: StatusLedSpec[];
};

/** Mission-control micro LEDs for render / canvas / API state. */
export default function StatusLeds({ leds }: Props) {
  return (
    <ul className="status-leds" aria-label="Studio status">
      {leds.map((led) => (
        <li key={led.id} className="status-leds__item" title={led.title}>
          <span
            className={`status-leds__lamp status-leds__lamp--${led.tone}`}
            aria-hidden
          />
          <span className="status-leds__label">{led.label}</span>
          <span className="visually-hidden">
            {led.label}: {led.title}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function renderLedTone(args: {
  running: boolean;
  statusMessage?: string;
}): LedTone {
  const msg = (args.statusMessage ?? "").toLowerCase();
  if (args.running) return "busy";
  if (msg.includes("fail") || msg.startsWith("error") || msg.includes("crash")) return "fault";
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
