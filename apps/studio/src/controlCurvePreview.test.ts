import { describe, expect, it } from "vitest";
import {
  controlCurveFromWidgets,
  parsePoints,
  pointsPatch,
  serializePoints,
  syncPointsFromStartEnd,
} from "./components/ControlCurvePreview";

describe("controlCurveFromWidgets", () => {
  it("reads linear ramp params with defaults", () => {
    const curve = controlCurveFromWidgets({});
    expect(curve.points).toEqual([
      { t: 0, v: 0 },
      { t: 1, v: 1 },
    ]);
    expect(curve.durationSec).toBe(1);
  });

  it("parses points JSON", () => {
    const curve = controlCurveFromWidgets({
      points: JSON.stringify([
        { t: 0, v: 0 },
        { t: 0.5, v: 1 },
        { t: 1, v: 0.2 },
      ]),
    });
    expect(curve.points).toHaveLength(3);
    expect(curve.points[1]).toMatchObject({ t: 0.5, v: 1 });
  });
});

describe("pointsPatch", () => {
  it("serializes and syncs start/end", () => {
    const patch = pointsPatch([
      { t: 0, v: 0.1 },
      { t: 0.4, v: 0.9 },
      { t: 1, v: 0.3 },
    ]);
    expect(patch.start_value).toBe(0.1);
    expect(patch.end_value).toBe(0.3);
    expect(parsePoints(patch.points)).toHaveLength(3);
  });
});

describe("syncPointsFromStartEnd", () => {
  it("updates first point when start_value changes", () => {
    const widgets = {
      points: serializePoints([
        { t: 0, v: 0 },
        { t: 0.5, v: 1 },
        { t: 1, v: 1 },
      ]),
      start_value: 0,
      end_value: 1,
    };
    const patch = syncPointsFromStartEnd(widgets, "start_value", 0.25);
    expect(patch?.start_value).toBe(0.25);
    expect(parsePoints(patch?.points)[0]?.v).toBe(0.25);
  });
});
