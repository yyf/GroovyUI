import { API } from "./api";
import {
  TEMPLATE_LICENSE_MATRIX,
  templateLicenseSummary,
  type TemplateLicenseTone,
} from "./templateLicenseMatrix";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

type PopupShellOptions = {
  height?: number;
  width?: number;
  /** When true, body scrolls instead of auto-fitting height to content. */
  scrollable?: boolean;
  extraCss?: string;
};

function popupShell(title: string, body: string, options: PopupShellOptions | number = 360): void {
  const opts: PopupShellOptions =
    typeof options === "number" ? { height: options } : options;
  const width = opts.width ?? 440;
  const height = opts.height ?? 360;
  const overflow = opts.scrollable ? "auto" : "hidden";
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; }
    body {
      padding: 18px 20px 16px;
      font-family: "SF Pro Text", "Inter", system-ui, sans-serif;
      background: linear-gradient(165deg, #1a1a1a 0%, #050505 55%, #111 100%);
      color: #e8e8e8;
      overflow: ${overflow};
    }
    h1 { margin: 0 0 2px; font-size: 17px; font-weight: 500; letter-spacing: 0.04em; }
    .sub { color: #9a9a9a; font-size: 12px; margin: 0 0 10px; line-height: 1.45; }
    .sub:last-of-type { margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    td { padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.08); vertical-align: top; }
    td:first-child { color: #8a8a8a; width: 36%; padding-right: 10px; }
    .ok { color: #d4d4d4; }
    .bad { color: #a0a0a0; }
    ${opts.extraCss ?? ""}
  </style>
</head>
<body>
${body}
</body>
</html>`;

  const popup = window.open(
    "",
    `groovy-${title.toLowerCase().replace(/\s+/g, "-")}`,
    `width=${width},height=${height},menubar=no,toolbar=no,location=no`,
  );
  if (!popup) return;
  popup.document.open();
  popup.document.write(html);
  popup.document.close();

  if (opts.scrollable) return;

  // Fit chrome + content so the About copy is fully visible without scrolling.
  const fit = () => {
    try {
      const doc = popup.document;
      const contentHeight = Math.ceil(
        Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight),
      );
      const chrome = popup.outerHeight - popup.innerHeight;
      const nextHeight = Math.min(
        Math.max(contentHeight + chrome + 8, 280),
        Math.floor(window.screen.availHeight * 0.9),
      );
      popup.resizeTo(width, nextHeight);
    } catch {
      /* popup may be blocked from resize in some browsers */
    }
  };
  popup.requestAnimationFrame(() => fit());
  setTimeout(fit, 50);
}

export async function openApiStatusWindow(): Promise<void> {
  let health: Record<string, unknown> = { status: "offline" };
  try {
    const res = await fetch(`${API}/api/health`);
    if (res.ok) health = await res.json();
  } catch {
    /* offline */
  }

  const status = escapeHtml(String(health.status ?? "offline"));
  const version = escapeHtml(String(health.groovy_version ?? "unknown"));
  const api = escapeHtml(API);
  const features = Object.entries(health)
    .filter(([key]) => !["status", "groovy_version"].includes(key))
    .map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(String(value))}</td></tr>`)
    .join("");

  const body = `
  <h1>API status</h1>
  <p class="sub">Live connection to the GroovyUI backend.</p>
  <table>
    <tr><td>Endpoint</td><td>${api}</td></tr>
    <tr><td>Status</td><td class="${status === "ok" ? "ok" : "bad"}">${status}</td></tr>
    <tr><td>Version</td><td>${version}</td></tr>
    ${features}
  </table>`;
  popupShell("GroovyUI — API status", body, 380);
}

function toneClass(tone: TemplateLicenseTone): string {
  if (tone === "safe") return "tone-safe";
  if (tone === "nc") return "tone-nc";
  return "tone-caution";
}

/** Settings → Template licenses (⌘⇧D / studio dev mode) — commercial clearance overview. */
export function openTemplateLicenseWindow(): void {
  const summary = templateLicenseSummary();
  const rows = TEMPLATE_LICENSE_MATRIX.map(
    (row) => `
    <tr class="${toneClass(row.tone)}">
      <td>
        <div class="t-title">${escapeHtml(row.title)}</div>
        <div class="t-id">${escapeHtml(row.id)}</div>
      </td>
      <td>${escapeHtml(row.models)}</td>
      <td>${escapeHtml(row.licenses)}</td>
      <td class="t-decision">${escapeHtml(row.final)}</td>
    </tr>`,
  ).join("");

  const body = `
  <h1>Template licenses</h1>
  <p class="sub">Quick overview of which bundled templates are commercially cleared for demos and posts. Based on model-registry seed licenses — not legal advice; re-check upstream before campaigns.</p>
  <p class="sub counts"><span class="pill pill-safe">${summary.commercialSafe} commercial safe</span><span class="pill pill-nc">${summary.conferenceOnly} conference / NC</span><span class="pill pill-caution">${summary.caution} caution</span></p>
  <table class="matrix">
    <thead>
      <tr>
        <th>Template</th>
        <th>Model(s)</th>
        <th>Model license</th>
        <th>Final decision</th>
      </tr>
    </thead>
    <tbody>
      ${rows}
    </tbody>
  </table>
  <p class="sub foot">Commercial Safe = MIT / Apache-2.0 (or DSP-only). NC / Community templates are OK for academic talks with attribution, not for marketing audio.</p>`;

  popupShell("GroovyUI — Template licenses", body, {
    width: 920,
    height: 640,
    scrollable: true,
    extraCss: `
      body { padding: 16px 18px 20px; }
      .counts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
      .pill {
        display: inline-block;
        font-size: 11px;
        letter-spacing: 0.02em;
        padding: 3px 8px;
        border: 1px solid rgba(255,255,255,0.14);
        color: #c8c8c8;
      }
      .pill-safe { border-color: rgba(120, 180, 120, 0.45); color: #c8e0c8; }
      .pill-nc { border-color: rgba(200, 160, 80, 0.45); color: #e0d0a8; }
      .pill-caution { border-color: rgba(200, 100, 100, 0.45); color: #e0b0b0; }
      table.matrix { font-size: 11px; }
      table.matrix th {
        text-align: left;
        font-weight: 500;
        color: #9a9a9a;
        padding: 6px 8px 8px 0;
        border-bottom: 1px solid rgba(255,255,255,0.16);
        position: sticky;
        top: 0;
        background: #121212;
      }
      table.matrix td {
        padding: 8px 10px 8px 0;
        border-bottom: 1px solid rgba(255,255,255,0.07);
        color: #d8d8d8;
        width: auto;
      }
      table.matrix td:first-child { width: 22%; color: #e8e8e8; }
      .t-title { font-weight: 500; }
      .t-id { color: #7a7a7a; font-size: 10px; margin-top: 2px; }
      .t-decision { font-weight: 500; }
      tr.tone-safe .t-decision { color: #c8e0c8; }
      tr.tone-nc .t-decision { color: #e0d0a8; }
      tr.tone-caution .t-decision { color: #e0b0b0; }
      .foot { margin-top: 14px; margin-bottom: 0; }
    `,
  });
}
