/** Client-side helpers for offline PCM sample integrity (A/B + inspector). */

export type SampleMetaSummary = {
  content_hash?: unknown;
  sample_rate?: unknown;
  frame_count?: unknown;
  channels?: unknown;
  channel_layout?: unknown;
  source_node_type?: unknown;
};

export type SamplePairCheck = {
  label: string;
  summary: string;
  same_content_hash: boolean;
  same_sample_rate: boolean;
  same_frame_count: boolean;
  same_channel_layout: boolean;
};

export function samplePairCheck(metaA: SampleMetaSummary, metaB: SampleMetaSummary): SamplePairCheck {
  const hashA = typeof metaA.content_hash === "string" ? metaA.content_hash : "";
  const hashB = typeof metaB.content_hash === "string" ? metaB.content_hash : "";
  const sameHash = Boolean(hashA) && hashA === hashB;
  const sameSr = Number(metaA.sample_rate || 0) === Number(metaB.sample_rate || 0);
  const sameFrames = Number(metaA.frame_count || 0) === Number(metaB.frame_count || 0);
  const sameLayout = String(metaA.channel_layout || "") === String(metaB.channel_layout || "");

  if (sameHash && sameSr && sameFrames && sameLayout) {
    return {
      label: "identical",
      summary: "A and B share the same content hash, sample rate, frame count, and layout.",
      same_content_hash: true,
      same_sample_rate: true,
      same_frame_count: true,
      same_channel_layout: true,
    };
  }
  if (sameSr && sameLayout && !sameHash) {
    return {
      label: "same_clock_different_pcm",
      summary: "Same sample rate and layout, different PCM content hash.",
      same_content_hash: false,
      same_sample_rate: true,
      same_frame_count: sameFrames,
      same_channel_layout: true,
    };
  }
  if (!sameSr || !sameLayout) {
    return {
      label: "format_mismatch",
      summary: "Sample rate and/or channel layout differ between A and B.",
      same_content_hash: sameHash,
      same_sample_rate: sameSr,
      same_frame_count: sameFrames,
      same_channel_layout: sameLayout,
    };
  }
  return {
    label: "different",
    summary: "Buffers differ (hash and/or frame count).",
    same_content_hash: sameHash,
    same_sample_rate: sameSr,
    same_frame_count: sameFrames,
    same_channel_layout: sameLayout,
  };
}
