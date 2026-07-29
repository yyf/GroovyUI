import { ControlButton, useReactFlow } from "@xyflow/react";
import { FIT_ALL_OPTIONS } from "../canvasViewport";

/** Canvas control: zoom to show the whole graph (bird's-eye when needed). */
export default function FitAllControl() {
  const { fitView, getNodes } = useReactFlow();

  return (
    <ControlButton
      onClick={() => {
        if (getNodes().length === 0) return;
        void fitView({ ...FIT_ALL_OPTIONS });
      }}
      title="Fit all (⌘0)"
      aria-label="Fit all nodes in view"
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" aria-hidden="true">
        <path d="M4 4h8v2H6v6H4V4zm16 0h8v8h-2V6h-6V4zM4 20h2v6h6v2H4v-8zm18 6v-6h2v8h-8v-2h6z" />
        <path d="M10 10h12v12H10z" opacity="0.35" />
      </svg>
    </ControlButton>
  );
}
