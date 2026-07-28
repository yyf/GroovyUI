import { describe, expect, it } from "vitest";
import { apiLedTone, canvasLedTone, renderLedTone } from "./StatusLeds";

describe("status LED tones", () => {
  it("maps render states", () => {
    expect(renderLedTone({ running: true })).toBe("busy");
    expect(renderLedTone({ running: false, statusMessage: "Failed: boom" })).toBe("fault");
    expect(renderLedTone({ running: false, statusMessage: "Error: x" })).toBe("fault");
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
});
