type Props = {
  peaksA: number[];
  peaksB: number[];
  labelA: string;
  labelB: string;
  titleA?: string;
  titleB?: string;
};

function resamplePeaks(peaks: number[], width: number): number[] {
  if (peaks.length === 0) return Array(width).fill(0);
  if (peaks.length === width) return peaks;
  const out: number[] = [];
  for (let i = 0; i < width; i++) {
    const idx = Math.floor((i / width) * peaks.length);
    out.push(peaks[idx] ?? 0);
  }
  return out;
}

export default function WaveformCompare({ peaksA, peaksB, labelA, labelB, titleA, titleB }: Props) {
  const width = 256;
  const height = 48;
  const mid = height / 2;
  const alignedA = resamplePeaks(peaksA, width);
  const alignedB = resamplePeaks(peaksB, width);
  const max = Math.max(...alignedA, ...alignedB, 0.001);

  if (!peaksA.length && !peaksB.length) {
    return <div className="waveform-compare waveform-compare--empty" />;
  }

  return (
    <div className="waveform-compare">
      <div className="waveform-compare__legend">
        <span className="waveform-compare__swatch waveform-compare__swatch--a" />
        <span className="waveform-compare__label" title={titleA ?? labelA}>
          {labelA}
        </span>
        <span className="waveform-compare__swatch waveform-compare__swatch--b" />
        <span className="waveform-compare__label" title={titleB ?? labelB}>
          {labelB}
        </span>
      </div>
      <svg className="waveform-compare__svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden>
        {alignedA.map((peak, index) => {
          const amp = (peak / max) * (mid - 1);
          return (
            <line
              key={`a-${index}`}
              className="waveform-compare__line waveform-compare__line--a"
              x1={index + 0.5}
              x2={index + 0.5}
              y1={mid - amp}
              y2={mid + amp}
            />
          );
        })}
        {alignedB.map((peak, index) => {
          const amp = (peak / max) * (mid - 1);
          return (
            <line
              key={`b-${index}`}
              className="waveform-compare__line waveform-compare__line--b"
              x1={index + 0.5}
              x2={index + 0.5}
              y1={mid - amp}
              y2={mid + amp}
            />
          );
        })}
      </svg>
    </div>
  );
}
