import { beforeEach, describe, expect, it, vi } from "vitest";
import { recordActivationDiagnostic } from "./api";
import {
  finishActivationSession,
  recordActivationMilestone,
  resetActivationSessionForTest,
  startActivationSession,
} from "./activationDiagnostics";

vi.mock("./api", () => ({
  recordActivationDiagnostic: vi.fn(async () => undefined),
}));

describe("activation diagnostics", () => {
  beforeEach(() => {
    resetActivationSessionForTest();
    vi.mocked(recordActivationDiagnostic).mockClear();
  });

  it("measures task start through actual playback without blocking the flow", async () => {
    const now = vi
      .spyOn(performance, "now")
      .mockReturnValueOnce(100)
      .mockReturnValueOnce(600)
      .mockReturnValueOnce(1600);

    startActivationSession({ source: "generate" });
    expect(recordActivationMilestone("render_started")).toBe(500);
    expect(
      finishActivationSession("playback_started", { preview_kind: "audio" }),
    ).toBe(1500);
    expect(recordActivationMilestone("render_completed")).toBeNull();

    await vi.waitFor(() =>
      expect(recordActivationDiagnostic).toHaveBeenCalledTimes(3),
    );
    expect(vi.mocked(recordActivationDiagnostic).mock.calls[0][0]).toMatchObject({
      event: "task_started",
      elapsed_ms: 0,
      context: { source: "generate" },
    });
    expect(vi.mocked(recordActivationDiagnostic).mock.calls[2][0]).toMatchObject({
      event: "playback_started",
      elapsed_ms: 1500,
    });
    now.mockRestore();
  });
});
