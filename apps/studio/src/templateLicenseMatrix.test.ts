import { describe, expect, it } from "vitest";
import {
  TEMPLATE_LICENSE_MATRIX,
  isCommerciallyCleared,
  templateLicenseSummary,
} from "./templateLicenseMatrix";

describe("templateLicenseMatrix", () => {
  it("covers all curated bundled templates without duplicate ids", () => {
    const ids = TEMPLATE_LICENSE_MATRIX.map((row) => row.id);
    expect(ids.length).toBe(37);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("marks MusicGen / F5 / Stable Audio / RAVE paths as not commercial", () => {
    expect(isCommerciallyCleared("text-to-music")).toBe(false);
    expect(isCommerciallyCleared("voice-cloning")).toBe(false);
    expect(isCommerciallyCleared("stable-audio")).toBe(false);
    expect(isCommerciallyCleared("rave-timbre-transfer")).toBe(false);
    expect(isCommerciallyCleared("song-cover-remix")).toBe(false);
  });

  it("marks MIT/Apache heroes as commercially cleared", () => {
    expect(isCommerciallyCleared("hello-groovy")).toBe(true);
    expect(isCommerciallyCleared("podcast-denoise")).toBe(true);
    expect(isCommerciallyCleared("ace-step-1.5")).toBe(true);
    expect(isCommerciallyCleared("stem-separation")).toBe(true);
  });

  it("summarizes clearance counts", () => {
    const summary = templateLicenseSummary();
    expect(summary.total).toBe(37);
    expect(summary.commercialSafe + summary.conferenceOnly + summary.caution).toBe(37);
    expect(summary.commercialSafe).toBeGreaterThan(20);
  });
});
