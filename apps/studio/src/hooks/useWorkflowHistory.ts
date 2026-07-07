import { useCallback, useRef, useState } from "react";
import type { Workflow } from "../types";

const MAX_HISTORY = 50;

function cloneWorkflow(workflow: Workflow): Workflow {
  return structuredClone(workflow);
}

export function useWorkflowHistory(initial: Workflow | null = null) {
  const [workflow, setWorkflowState] = useState<Workflow | null>(initial);
  const pastRef = useRef<Workflow[]>([]);
  const futureRef = useRef<Workflow[]>([]);

  const resetHistory = useCallback((next: Workflow | null) => {
    pastRef.current = [];
    futureRef.current = [];
    setWorkflowState(next);
  }, []);

  const setWorkflow = useCallback(
    (updater: Workflow | ((prev: Workflow | null) => Workflow | null), options?: { record?: boolean }) => {
      const record = options?.record ?? true;
      setWorkflowState((prev) => {
        const next = typeof updater === "function" ? updater(prev) : updater;
        if (record && prev && next && prev !== next) {
          pastRef.current.push(cloneWorkflow(prev));
          if (pastRef.current.length > MAX_HISTORY) {
            pastRef.current.shift();
          }
          futureRef.current = [];
        }
        return next;
      });
    },
    [],
  );

  const undo = useCallback(() => {
    setWorkflowState((current) => {
      const previous = pastRef.current.pop();
      if (!previous || !current) return current;
      futureRef.current.push(cloneWorkflow(current));
      return cloneWorkflow(previous);
    });
  }, []);

  const redo = useCallback(() => {
    setWorkflowState((current) => {
      const next = futureRef.current.pop();
      if (!next || !current) return current;
      pastRef.current.push(cloneWorkflow(current));
      return cloneWorkflow(next);
    });
  }, []);

  return {
    workflow,
    setWorkflow,
    resetHistory,
    undo,
    redo,
  };
}
