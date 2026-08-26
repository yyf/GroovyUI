import { describe, expect, it } from "vitest";
import { samplePairCheck } from "./sampleIntegrity";

describe("samplePairCheck", () => {
  it("detects identical buffers", () => {
    const meta = {
      content_hash: "sha256:abc",
      sample_rate: 48000,
      frame_count: 100,
      channel_layout: "mono",
    };
    const result = samplePairCheck(meta, { ...meta });
    expect(result.label).toBe("identical");
    expect(result.same_content_hash).toBe(true);
  });

  it("detects same clock different pcm", () => {
    const result = samplePairCheck(
      { content_hash: "sha256:a", sample_rate: 48000, frame_count: 100, channel_layout: "mono" },
      { content_hash: "sha256:b", sample_rate: 48000, frame_count: 100, channel_layout: "mono" },
    );
    expect(result.label).toBe("same_clock_different_pcm");
  });
});
