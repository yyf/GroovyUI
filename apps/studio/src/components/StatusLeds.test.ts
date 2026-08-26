import { describe, expect, it } from "vitest";
import {
  apiLedTone,
  buildStatusReportHtml,
  canvasLedTone,
  escapeReportHtml,
  ledIsInspectable,
  renderLedTone,
} from "./StatusLeds";

describe("status LED tones", () => {
  it("maps render states", () => {
    expect(renderLedTone({ running: true })).toBe("busy");
    expect(renderLedTone({ running: false, statusMessage: "Failed: boom" })).toBe("fault");
    expect(renderLedTone({ running: false, statusMessage: "Unknown node type: BeatTrack" })).toBe("fault");
    expect(renderLedTone({ running: false, statusMessage: "Cancelled" })).toBe("warn");
    expect(renderLedTone({ running: false, statusMessage: "Render complete" })).toBe("ok");
    expect(renderLedTone({ running: false, statusMessage: "Ready" })).toBe("ok");
  });

  it("maps canvas states", () => {
    expect(canvasLedTone({ issueCount: 0 })).toBe("ok");
    expect(canvasLedTone({ issueCount: 2 })).toBe("warn");
    expect(canvasLedTone({ issueCount: 0, crashed: true })).toBe("fault");
  });

  it("maps api states", () => {
    expect(apiLedTone(null)).toBe("off");
    expect(apiLedTone(true)).toBe("ok");
    expect(apiLedTone(false)).toBe("fault");
  });

  it("only warn/fault LEDs are inspectable", () => {
    expect(ledIsInspectable("fault")).toBe(true);
    expect(ledIsInspectable("warn")).toBe(true);
    expect(ledIsInspectable("ok")).toBe(false);
    expect(ledIsInspectable("busy")).toBe(false);
  });

  it("escapes report HTML", () => {
    expect(escapeReportHtml('<img src=x onerror="alert(1)">')).toContain("&lt;img");
    const html = buildStatusReportHtml("RND", "Failed: boom\nnode n23");
    expect(html).toContain("RND fault");
    expect(html).toContain("Failed: boom");
    expect(html).toContain("<br />");
  });
});
