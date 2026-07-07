type Props = {
  peaks: number[];
};

export default function WaveformMini({ peaks }: Props) {
  if (!peaks.length) {
    return <div className="waveform-mini waveform-mini--empty" />;
  }
  const max = Math.max(...peaks, 0.001);
  const width = peaks.length;
  const height = 32;
  const mid = height / 2;

  return (
    <svg className="waveform-mini" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden>
      {peaks.map((peak, index) => {
        const amp = (peak / max) * (mid - 1);
        return (
          <line
            key={index}
            x1={index + 0.5}
            x2={index + 0.5}
            y1={mid - amp}
            y2={mid + amp}
          />
        );
      })}
    </svg>
  );
}
