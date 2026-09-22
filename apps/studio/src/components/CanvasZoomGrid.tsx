import { useViewport } from "@xyflow/react";

/** Flow-space gap (px); visual dots and snapToGrid share this. */
export const CANVAS_GRID_GAP = 20;

/** Snap a flow-space point so it sits on a grid intersection (node top-left). */
export function snapFlowPosition(
  pos: { x: number; y: number },
  gap: number = CANVAS_GRID_GAP,
): { x: number; y: number } {
  return {
    x: Math.round(pos.x / gap) * gap,
    y: Math.round(pos.y / gap) * gap,
  };
}

/**
 * Dots that pan/zoom with the viewport (must render inside ReactFlow).
 * Gradient is anchored at the top-left of each cell so dots match snapToGrid
 * (node `position` = top-left corner).
 */
export default function CanvasZoomGrid() {
  const { x, y, zoom } = useViewport();
  const size = Math.max(4, CANVAS_GRID_GAP * zoom);
  return (
    <div
      className="canvas-zoom-grid"
      aria-hidden
      style={{
        backgroundSize: `${size}px ${size}px`,
        backgroundPosition: `${x}px ${y}px`,
      }}
    />
  );
}
