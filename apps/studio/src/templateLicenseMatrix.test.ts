import { describe, expect, it } from "vitest";
import { STANDARD_BUNDLED_TEMPLATE_IDS } from "./templateUi";
import {
  TEMPLATE_LICENSE_MATRIX,
  isCommerciallyCleared,
  templateLicenseSummary,
} from "./templateLicenseMatrix";

describe("templateLicenseMatrix", () => {
  it("covers only public standard bundled templates without duplicate ids", () => {
    const ids = TEMPLATE_LICENSE_MATRIX.map((row) => row.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.sort()).toEqual([...STANDARD_BUNDLED_TEMPLATE_IDS].sort());
  });

  it("marks public MIT/Apache heroes as commercially cleared", () => {
    expect(isCommerciallyCleared("empty-canvas")).toBe(true);
    expect(isCommerciallyCleared("hello-groovy")).toBe(true);
    expect(isCommerciallyCleared("podcast-denoise")).toBe(true);
    expect(isCommerciallyCleared("isolate-vocals-to-transcribe")).toBe(true);
    expect(isCommerciallyCleared("prompt-modular-synth")).toBe(true);
  });

  it("does not claim clearance for non-public / internal-only templates", () => {
    expect(isCommerciallyCleared("text-to-music")).toBe(false);
    expect(isCommerciallyCleared("stem-separation")).toBe(false);
    expect(isCommerciallyCleared("ace-step-1.5")).toBe(false);
  });

  it("summarizes clearance counts for the public set", () => {
    const summary = templateLicenseSummary();
    expect(summary.total).toBe(STANDARD_BUNDLED_TEMPLATE_IDS.length);
    expect(summary.commercialSafe + summary.conferenceOnly + summary.caution).toBe(
      summary.total,
    );
    expect(summary.commercialSafe).toBe(5);
    expect(summary.conferenceOnly).toBe(0);
    expect(summary.caution).toBe(0);
  });
});
