/**
 * Claude / Anthropic-powered studio UX (Patch Generation, Model Plan, Tab Creative Agent, Settings key).
 * Hidden for now — intended as a future paid unlock when clients need it.
 */
export const CLAUDE_UX_ENABLED = false;

/**
 * Tab expands the selected node with its deterministic Help/minimal patch
 * (local recipes only — no Claude). Creative-agent Tab loop stays behind CLAUDE_UX_ENABLED.
 */
export const TAB_GROW_UX_ENABLED = true;
