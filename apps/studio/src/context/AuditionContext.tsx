import { createContext, useContext } from "react";

type AuditionHandler = (nodeId: string) => void;

export const AuditionContext = createContext<AuditionHandler>(() => {});

export function useAudition(): AuditionHandler {
  return useContext(AuditionContext);
}
