import { useEffect } from "react";
import { useReactFlow } from "@xyflow/react";

type Props = {
  canvasSelector: string;
  onCenterReady: (getter: () => { x: number; y: number }) => void;
};

export default function FlowViewportBridge({ canvasSelector, onCenterReady }: Props) {
  const { screenToFlowPosition } = useReactFlow();

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

  return null;
}
