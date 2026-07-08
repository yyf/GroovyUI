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
    body {
      margin: 0;
      padding: 24px;
      font-family: "SF Pro Text", "Inter", system-ui, sans-serif;
      background: linear-gradient(165deg, #1a1a1a 0%, #050505 55%, #111 100%);
      color: #e8e8e8;
      min-height: 100vh;
    }
    h1 { margin: 0 0 4px; font-size: 18px; font-weight: 500; letter-spacing: 0.04em; }
    .sub { color: #9a9a9a; font-size: 12px; margin-bottom: 20px; line-height: 1.5; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    td { padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.08); vertical-align: top; }
    td:first-child { color: #8a8a8a; width: 42%; }
    .ok { color: #d4d4d4; }
    .bad { color: #a0a0a0; }
  </style>
</head>
<body>
${body}
</body>
</html>`;

  const popup = window.open("", `groovy-${title.toLowerCase().replace(/\s+/g, "-")}`, `width=440,height=${height},menubar=no,toolbar=no,location=no`);
  if (!popup) return;
  popup.document.open();
  popup.document.write(html);
  popup.document.close();
}

export function openAboutWindow(): void {
  const body = `
  <h1>GroovyUI Studio</h1>
  <p class="sub">Version ${STUDIO_VERSION}</p>
  <p class="sub">A node-graph studio purpose-built for AI audio — patch models and operators, render with sample accuracy, and stay in the graph while you explore, compare, and share.</p>
  <p class="sub">General-purpose graph tools spread audio across scattered custom nodes. GroovyUI fills that gap with an audio-native registry, typed signal flow, provenance, and modular-synth ergonomics in one workflow.</p>
  <table>
    <tr><td>Rendering</td><td>Sample-accurate offline · cached audition</td></tr>
    <tr><td>Signals</td><td>Audio, MIDI, stems, control, immersive layouts</td></tr>
    <tr><td>License</td><td>Apache 2.0 (core packages)</td></tr>
  </table>`;
  popupShell("GroovyUI — About", body, 400);
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
