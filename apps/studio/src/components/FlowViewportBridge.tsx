import { useEffect } from "react";
import { useReactFlow, useUpdateNodeInternals } from "@xyflow/react";

type Props = {
  canvasSelector: string;
  onCenterReady: (getter: () => { x: number; y: number }) => void;
  /** Bumps when derived flow nodes change — forces handle remeasure for new edges. */
  nodeSyncKey?: string;
  /** Bumps after template load — fits all nodes in view. */
  fitViewKey?: number;
};

export default function FlowViewportBridge({
  canvasSelector,
  onCenterReady,
  nodeSyncKey,
  fitViewKey,
}: Props) {
  const { screenToFlowPosition, getNodes, fitView } = useReactFlow();
  const updateNodeInternals = useUpdateNodeInternals();

  useEffect(() => {
    onCenterReady(() => {
      const element = document.querySelector(canvasSelector);
      if (!element) return { x: 320, y: 200 };
      const rect = element.getBoundingClientRect();
      return screenToFlowPosition({
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
      });
    });
  }, [canvasSelector, onCenterReady, screenToFlowPosition]);

  useEffect(() => {
    if (!nodeSyncKey) return;
    const frame = requestAnimationFrame(() => {
      for (const node of getNodes()) {
        updateNodeInternals(node.id);
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [nodeSyncKey, updateNodeInternals, getNodes]);

  useEffect(() => {
    if (!fitViewKey || !nodeSyncKey) return;
    const frame = requestAnimationFrame(() => {
      if (getNodes().length === 0) return;
      void fitView({ padding: 0.2, duration: 0 });
    });
    return () => cancelAnimationFrame(frame);
  }, [fitViewKey, nodeSyncKey, fitView, getNodes]);

  return null;
}
