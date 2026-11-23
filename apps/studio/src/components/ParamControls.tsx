import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { formatControlValue, snapToStep } from "../widgetControls";

type BaseProps = {
  disabled?: boolean;
  label?: string;
};

type NumericProps = BaseProps & {
  value: number;
  min: number;
  max: number;
  step: number;
  isInt?: boolean;
  onChange: (value: number) => void;
  /** When false, hide the numeric text field (knob-only chrome). */
  showValue?: boolean;
  /** Accessible name for the dial (defaults to formatted value). */
  ariaLabel?: string;
  /** Plain-language meaning of the lower bound (Inspector faders). */
  minHint?: string;
  /** Plain-language meaning of the upper bound (Inspector faders). */
  maxHint?: string;
};

function useDragValue({
  value,
  min,
  max,
  step,
  disabled,
  onChange,
  sensitivity,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (value: number) => void;
  /** Pixels of drag per full travel (larger = finer). */
  sensitivity: number;
}) {
  const drag = useRef<{ startY: number; startValue: number } | null>(null);

  const onPointerDown = useCallback(
    (e: ReactPointerEvent) => {
      if (disabled) return;
      e.preventDefault();
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      drag.current = { startY: e.clientY, startValue: value };
    },
    [disabled, value],
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent) => {
      if (!drag.current) return;
      const span = Math.max(1e-9, max - min);
      const delta = (drag.current.startY - e.clientY) / sensitivity;
      const next = snapToStep(drag.current.startValue + delta * span, min, max, step);
      if (next !== value) onChange(next);
    },
    [min, max, step, sensitivity, onChange, value],
  );

  const onPointerUp = useCallback((e: ReactPointerEvent) => {
    drag.current = null;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  }, []);

  return { onPointerDown, onPointerMove, onPointerUp };
}

/** Shared readout under pot/fader — drag the control or type into the same label. */
function ParamValueField({
  value,
  min,
  max,
  step,
  isInt = false,
  onChange,
  disabled,
  className,
}: NumericProps & { className: string }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => formatControlValue(value, step, isInt));

  useEffect(() => {
    if (!editing) setDraft(formatControlValue(value, step, isInt));
  }, [value, step, isInt, editing]);

  const commit = useCallback(() => {
    setEditing(false);
    const raw = draft.trim().replace(/,/g, "");
    if (!raw) {
      setDraft(formatControlValue(value, step, isInt));
      return;
    }
    const parsed = isInt ? Number.parseInt(raw, 10) : Number.parseFloat(raw);
    if (!Number.isFinite(parsed)) {
      setDraft(formatControlValue(value, step, isInt));
      return;
    }
    onChange(snapToStep(parsed, min, max, step));
  }, [draft, value, step, isInt, min, max, onChange]);

  return (
    <input
      type="text"
      inputMode={isInt ? "numeric" : "decimal"}
      className={className}
      value={editing ? draft : formatControlValue(value, step, isInt)}
      disabled={disabled}
      aria-label="Value"
      spellCheck={false}
      onFocus={() => {
        setEditing(true);
        setDraft(formatControlValue(value, step, isInt));
      }}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          (e.currentTarget as HTMLInputElement).blur();
        } else if (e.key === "Escape") {
          e.preventDefault();
          setEditing(false);
          setDraft(formatControlValue(value, step, isInt));
          (e.currentTarget as HTMLInputElement).blur();
        }
      }}
      onPointerDown={(e) => e.stopPropagation()}
    />
  );
}

/** Vertical toggle switch — industrial square. */
export function ParamSwitch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className={`param-switch${checked ? " param-switch--on" : ""}${disabled ? " param-switch--disabled" : ""}`}
      disabled={disabled}
      aria-pressed={checked}
      onClick={() => onChange(!checked)}
    >
      <span className="param-switch__track">
        <span className="param-switch__thumb" />
      </span>
      <span className="param-switch__state">{checked ? "ON" : "OFF"}</span>
    </button>
  );
}

/** Rotary potentiometer — drag vertically to adjust, or type the value below. */
export function ParamPot({
  value,
  min,
  max,
  step,
  isInt = false,
  onChange,
  disabled,
  showValue = true,
  ariaLabel,
}: NumericProps) {
  const span = Math.max(1e-9, max - min);
  const t = Math.min(1, Math.max(0, (value - min) / span));
  // Travel ~270° from 7:30 to 4:30
  const angle = -135 + t * 270;
  const { onPointerDown, onPointerMove, onPointerUp } = useDragValue({
    value,
    min,
    max,
    step,
    disabled,
    onChange,
    sensitivity: 120,
  });

  return (
    <div className={`param-pot${disabled ? " param-pot--disabled" : ""}${showValue ? "" : " param-pot--knob-only"}`}>
      <button
        type="button"
        className="param-pot__dial"
        disabled={disabled}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-label={ariaLabel ?? `Value ${value}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <span className="param-pot__ticks" aria-hidden />
        <span className="param-pot__knob" style={{ ["--pot-angle" as string]: `${angle}deg` }}>
          <span className="param-pot__pointer" />
        </span>
      </button>
      {showValue ? (
        <ParamValueField
          className="param-pot__value"
          value={value}
          min={min}
          max={max}
          step={step}
          isInt={isInt}
          onChange={onChange}
          disabled={disabled}
        />
      ) : null}
    </div>
  );
}

/** Horizontal slider — label-friendly overview in the Inspector. */
export function ParamFader({
  value,
  min,
  max,
  step,
  isInt = false,
  onChange,
  disabled,
  minHint = "lower",
  maxHint = "higher",
}: NumericProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const span = Math.max(1e-9, max - min);
  const t = Math.min(1, Math.max(0, (value - min) / span));

  const setFromClientX = useCallback(
    (clientX: number) => {
      const el = trackRef.current;
      if (!el || disabled) return;
      const rect = el.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / Math.max(1, rect.width)));
      onChange(snapToStep(min + ratio * span, min, max, step));
    },
    [disabled, min, max, step, span, onChange],
  );

  const onPointerDown = useCallback(
    (e: ReactPointerEvent) => {
      if (disabled) return;
      e.preventDefault();
      e.stopPropagation();
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      setFromClientX(e.clientX);
    },
    [disabled, setFromClientX],
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent) => {
      if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
      setFromClientX(e.clientX);
    },
    [setFromClientX],
  );

  const minLabel = formatControlValue(min, step, isInt);
  const maxLabel = formatControlValue(max, step, isInt);

  return (
    <div className={`param-fader${disabled ? " param-fader--disabled" : ""}`}>
      <div
        className="param-fader__bound param-fader__bound--min"
        title={`Minimum ${minLabel}: ${minHint}`}
      >
        <span className="param-fader__bound-tag">Min</span>
        <span className="param-fader__bound-value">{minLabel}</span>
        <span className="param-fader__bound-hint">{minHint}</span>
      </div>
      <div
        ref={trackRef}
        className="param-fader__track"
        role="slider"
        tabIndex={disabled ? -1 : 0}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-label={`Value between ${minLabel} (${minHint}) and ${maxLabel} (${maxHint})`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={(e) => {
          try {
            (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
          } catch {
            /* ignore */
          }
        }}
        onKeyDown={(e) => {
          if (disabled) return;
          if (e.key === "ArrowUp" || e.key === "ArrowRight") {
            e.preventDefault();
            onChange(snapToStep(value + step, min, max, step));
          } else if (e.key === "ArrowDown" || e.key === "ArrowLeft") {
            e.preventDefault();
            onChange(snapToStep(value - step, min, max, step));
          }
        }}
      >
        <span className="param-fader__fill" style={{ width: `${t * 100}%` }} />
        <span className="param-fader__cap" style={{ left: `calc(${t * 100}% - 5px)` }} />
      </div>
      <div
        className="param-fader__bound param-fader__bound--max"
        title={`Maximum ${maxLabel}: ${maxHint}`}
      >
        <span className="param-fader__bound-tag">Max</span>
        <span className="param-fader__bound-value">{maxLabel}</span>
        <span className="param-fader__bound-hint">{maxHint}</span>
      </div>
      <ParamValueField
        className="param-fader__value"
        value={value}
        min={min}
        max={max}
        step={step}
        isInt={isInt}
        onChange={onChange}
        disabled={disabled}
      />
    </div>
  );
}

/** Multi-position switch / select for discrete options (no rotary knobs). */
export function ParamStepped({
  value,
  options,
  onChange,
  disabled,
}: {
  value: string;
  options: string[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const safeValue = options.includes(value) ? value : (options[0] ?? value);
  const groupId = useId();

  // Compact: horizontal segmented switch when ≤5 options; otherwise a select.
  if (options.length <= 5) {
    return (
      <div className={`param-seg${disabled ? " param-seg--disabled" : ""}`} role="radiogroup" aria-labelledby={groupId}>
        {options.map((opt) => {
          const active = opt === safeValue;
          return (
            <button
              key={opt}
              type="button"
              role="radio"
              aria-checked={active}
              className={`param-seg__btn${active ? " param-seg__btn--active" : ""}`}
              disabled={disabled}
              onClick={() => onChange(opt)}
            >
              {opt}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className={`param-stepped${disabled ? " param-stepped--disabled" : ""}`}>
      <select
        className="param-stepped__select"
        value={safeValue}
        disabled={disabled}
        aria-label="Option"
        onChange={(e) => onChange(e.target.value)}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}
