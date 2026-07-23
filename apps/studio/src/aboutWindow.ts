import { API } from "./api";

const STUDIO_VERSION = "0.18.0";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function popupShell(title: string, body: string, height = 360): void {
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
      overflow: hidden;
    }
    h1 { margin: 0 0 2px; font-size: 17px; font-weight: 500; letter-spacing: 0.04em; }
    .sub { color: #9a9a9a; font-size: 12px; margin: 0 0 10px; line-height: 1.45; }
    .sub:last-of-type { margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    td { padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.08); vertical-align: top; }
    td:first-child { color: #8a8a8a; width: 36%; padding-right: 10px; }
    .ok { color: #d4d4d4; }
    .bad { color: #a0a0a0; }
  </style>
</head>
<body>
${body}
</body>
</html>`;

  const width = 440;
  const popup = window.open(
    "",
    `groovy-${title.toLowerCase().replace(/\s+/g, "-")}`,
    `width=${width},height=${height},menubar=no,toolbar=no,location=no`,
  );
  if (!popup) return;
  popup.document.open();
  popup.document.write(html);
  popup.document.close();

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

export function openAboutWindow(): void {
  const body = `
  <h1>GroovyUI Studio</h1>
  <p class="sub">Patch-bay for AI audio. Version ${STUDIO_VERSION}</p>
  <p class="sub">A node-graph studio purpose-built for AI audio — patch models and operators, render with sample accuracy, and stay in the graph while you explore, compare, and share.</p>
  <p class="sub">General-purpose graph tools spread audio across scattered custom nodes. GroovyUI fills that gap with an audio-native registry, typed signal flow, provenance, and modular-synth ergonomics in one workflow.</p>
  <table>
    <tr><td>Rendering</td><td>Sample-accurate offline · cached audition</td></tr>
    <tr><td>Signals</td><td>Audio, MIDI, stems, and control</td></tr>
    <tr><td>License</td><td>Apache 2.0 (core packages)</td></tr>
  </table>`;
  popupShell("GroovyUI — About", body, 520);
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
