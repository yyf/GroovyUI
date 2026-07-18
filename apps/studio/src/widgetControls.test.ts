import { describe, expect, it } from "vitest";
import { resolveWidgetControl, snapToStep } from "./widgetControls";

describe("resolveWidgetControl", () => {
  it("maps booleans to switches", () => {
    expect(resolveWidgetControl({ name: "split", type: "BOOLEAN" }).kind).toBe("switch");
  });

  it("keeps free text as text", () => {
    expect(resolveWidgetControl({ name: "prompt", type: "STRING" }).kind).toBe("text");
    expect(resolveWidgetControl({ name: "path", type: "STRING" }).kind).toBe("text");
    expect(resolveWidgetControl({ name: "seed", type: "INT", default: -1, min: -1 }).kind).toBe("text");
  });

  it("maps known string enums to stepped switches", () => {
    const mode = resolveWidgetControl({ name: "mode", type: "STRING", default: "lufs" });
    expect(mode.kind).toBe("stepped");
    expect(mode.options).toEqual(["lufs", "peak"]);
  });

  it("maps gains to faders and most floats to pots", () => {
    expect(resolveWidgetControl({ name: "gain_a", type: "FLOAT", default: 1 }).kind).toBe("fader");
    expect(resolveWidgetControl({ name: "target_lufs", type: "FLOAT", default: -16 }).kind).toBe("pot");
  });

  it("maps sample rate to stepped options", () => {
    const sr = resolveWidgetControl({ name: "target_sample_rate", type: "INT", default: 48000 });
    expect(sr.kind).toBe("stepped");
    expect(sr.options?.includes("48000")).toBe(true);
  });
});

describe("snapToStep", () => {
  it("snaps and clamps", () => {
    expect(snapToStep(0.53, 0, 1, 0.1)).toBeCloseTo(0.5);
    expect(snapToStep(-1, 0, 1, 0.1)).toBe(0);
  });
});
