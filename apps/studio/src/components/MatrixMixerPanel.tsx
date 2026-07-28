import { ParamPot } from "./ParamControls";

export const MATRIX_MIXER_SIZE = 4;

/** All crosspoint widget keys (gain_in_out). */
export const MATRIX_MIXER_GAIN_KEYS: string[] = Array.from({ length: MATRIX_MIXER_SIZE }, (_, i) =>
  Array.from({ length: MATRIX_MIXER_SIZE }, (__, j) => `gain_${i}_${j}`),
).flat();

type Props = {
  widgets: Record<string, unknown>;
  onChange: (name: string, value: number) => void;
  disabled?: boolean;
  min?: number;
  max?: number;
  step?: number;
  size?: number;
};

function readGain(widgets: Record<string, unknown>, inIdx: number, outIdx: number): number {
  const key = `gain_${inIdx}_${outIdx}`;
  const raw = widgets[key] ?? (outIdx === 0 ? widgets[`gain_${inIdx}`] : undefined);
  if (raw == null) return outIdx === 0 ? 1 : 0;
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) return outIdx === 0 ? 1 : 0;
  return n;
}

/** Classic N×M matrix plate — rows = inputs, columns = outputs, knobs only. */
export default function MatrixMixerPanel({
  widgets,
  onChange,
  disabled = false,
  min = 0,
  max = 4,
  step = 0.05,
  size = MATRIX_MIXER_SIZE,
}: Props) {
  const outs = Array.from({ length: size }, (_, j) => j);
  const ins = Array.from({ length: size }, (_, i) => i);

  return (
    <section className="matrix-mixer" aria-label="Matrix mixer gains">
      <div
        className="matrix-mixer__plate matrix-mixer__plate--grid"
        style={{ ["--matrix-size" as string]: String(size) }}
      >
        <div className="matrix-mixer__corner" aria-hidden />
        {outs.map((j) => (
          <div key={`out-${j}`} className="matrix-mixer__bus-head">
            <span className="matrix-mixer__bus-tag">OUT {j}</span>
          </div>
        ))}
        {ins.map((i) => (
          <div key={`row-${i}`} className="matrix-mixer__row">
            <span className="matrix-mixer__in-label">IN {i}</span>
            {outs.map((j) => {
              const key = `gain_${i}_${j}`;
              const value = readGain(widgets, i, j);
              return (
                <div key={key} className="matrix-mixer__cell">
                  <ParamPot
                    value={value}
                    min={min}
                    max={max}
                    step={step}
                    disabled={disabled}
                    showValue={false}
                    ariaLabel={`IN ${i} to OUT ${j}`}
                    onChange={(next) => onChange(key, next)}
                  />
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}
