import { formatAudioMeta, hasAudioFormatMeta } from "../multichannelMeta";

type Props = {
  meta: Record<string, unknown> | null;
  title?: string;
};

export default function AudioFormatPanel({ meta, title = "Audio format" }: Props) {
  if (!meta || !hasAudioFormatMeta(meta)) {
    return null;
  }

  const rows = formatAudioMeta(meta);

  return (
    <section className="node-helper__format-panel">
      <h3 className="node-helper__format-title">{title}</h3>
      <dl className="node-helper__meta-grid">
        {rows.map((row) => (
          <div key={row.label} className="node-helper__meta-row">
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
