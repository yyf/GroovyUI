export type AudioMetaRow = {
  label: string;
  value: string;
};

function asString(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

function formatChannelMap(map: unknown): string | null {
  if (!Array.isArray(map) || map.length === 0) return null;
  return map.join(" · ");
}

export function formatAudioMeta(meta: Record<string, unknown>): AudioMetaRow[] {
  const spatial = (meta.spatial_meta as Record<string, unknown> | undefined) ?? {};
  const rows: AudioMetaRow[] = [];

  const push = (label: string, value: unknown) => {
    const text = asString(value);
    if (text) rows.push({ label, value: text });
  };

  push("Channels", meta.channels);
  push("Layout", meta.channel_layout);
  push("Encoding", meta.encoding_scheme);
  push("Channel map", formatChannelMap(meta.channel_map));

  const order = meta.layout_order ?? spatial.layout_order;
  if (order !== null && order !== undefined) {
    push("Ambisonics order", order === 1 ? "1 (FOA)" : String(order));
  }

  push("Channel ordering", spatial.channel_ordering);
  push("Normalization", spatial.normalization);
  push("Container", spatial.container);
  push("ADM version", spatial.adm_version);
  push("Downmixed from", spatial.downmixed_from);
  push("Export format", spatial.export_format);

  const codec = [meta.file_format, meta.file_subtype].filter(Boolean).join(" / ");
  push("File codec", codec || null);
  push("Sample rate", meta.sample_rate ? `${meta.sample_rate} Hz` : null);
  push("Samples", meta.frame_count != null ? String(meta.frame_count) : null);

  if (meta.content_hash) {
    const hash = String(meta.content_hash).replace(/^sha256:/, "");
    push("Content hash", hash.length > 20 ? `${hash.slice(0, 12)}…` : hash);
  }

  if (meta.duration_seconds) {
    const seconds = Number(meta.duration_seconds);
    if (!Number.isNaN(seconds)) {
      push("Duration", `${seconds.toFixed(2)} s`);
    }
  } else if (meta.frame_count && meta.sample_rate) {
    const seconds = Number(meta.frame_count) / Number(meta.sample_rate);
    push("Duration", `${seconds.toFixed(2)} s`);
  }

  return rows;
}

export function hasAudioFormatMeta(meta: Record<string, unknown> | null): boolean {
  if (!meta) return false;
  return formatAudioMeta(meta).length > 0;
}
