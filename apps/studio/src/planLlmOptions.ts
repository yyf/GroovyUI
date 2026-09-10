/** Shared Claude model picks for Plan and Generate-by-LLM. */
export const PLAN_LLM_OPTIONS = [
  {
    id: "claude-sonnet-5",
    label: "Claude Sonnet",
    description: "Stronger multi-step graph drafts. Best default.",
  },
  {
    id: "claude-fable-5",
    label: "Claude Fable",
    description: "Highest-capability drafting for complex multi-hop graphs. Slower and costlier.",
  },
  {
    id: "claude-haiku-4-5",
    label: "Claude Haiku",
    description: "Faster and cheaper. Better for short, single-goal drafts.",
  },
] as const;

export type PlanLlmModelId = (typeof PLAN_LLM_OPTIONS)[number]["id"];
