/** Bird's-eye floor — below React Flow's default 0.5 so Fit all can show the whole graph. */
export const CANVAS_MIN_ZOOM = 0.15;
export const CANVAS_MAX_ZOOM = 2;

/** Fit-all / template load: overview zoom, avoid blowing up tiny graphs. */
export const FIT_ALL_OPTIONS = {
  padding: 0.18,
  duration: 200,
  minZoom: CANVAS_MIN_ZOOM,
  maxZoom: 1.25,
} as const;
