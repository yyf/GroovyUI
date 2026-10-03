import { createContext, useContext } from "react";

export type PreviewVideoSizeApi = {
  /** Aspect-locked size patch for PreviewVideo canvas chrome (does not dirty render). */
  patchSize: (nodeId: string, width: number, height: number) => void;
};

export const PreviewVideoSizeContext = createContext<PreviewVideoSizeApi>({
  patchSize: () => {},
});

export function usePreviewVideoSize(): PreviewVideoSizeApi {
  return useContext(PreviewVideoSizeContext);
}
