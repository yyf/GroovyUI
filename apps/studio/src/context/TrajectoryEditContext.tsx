import { createContext, useContext } from "react";

export type TrajectoryEditApi = {
  /** Patch TrajectoryAuthor widgets (XYZ / drawn points). Not live audio — re-render to hear. */
  patchAuthor: (authorNodeId: string, patch: Record<string, number | string>) => void;
};

export const TrajectoryEditContext = createContext<TrajectoryEditApi>({
  patchAuthor: () => {},
});

export function useTrajectoryEdit(): TrajectoryEditApi {
  return useContext(TrajectoryEditContext);
}
