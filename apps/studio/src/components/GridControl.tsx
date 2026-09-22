import { ControlButton } from "@xyflow/react";

type Props = {
  enabled: boolean;
  onToggle: () => void;
};

/** Canvas control: show/hide zoom-synced grid + snap (also `g`). */
export default function GridControl({ enabled, onToggle }: Props) {
  return (
    <ControlButton
      onClick={onToggle}
      title={enabled ? "Hide grid + snap (g)" : "Show grid + snap (g)"}
      aria-label={enabled ? "Hide canvas grid" : "Show canvas grid"}
      aria-pressed={enabled}
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" aria-hidden="true">
        <path
          d="M6 6h4v4H6V6zm8 0h4v4h-4V6zm8 0h4v4h-4V6zM6 14h4v4H6v-4zm8 0h4v4h-4v-4zm8 0h4v4h-4v-4zM6 22h4v4H6v-4zm8 0h4v4h-4v-4zm8 0h4v4h-4v-4z"
          fill="currentColor"
          opacity={enabled ? 1 : 0.45}
        />
      </svg>
    </ControlButton>
  );
}
