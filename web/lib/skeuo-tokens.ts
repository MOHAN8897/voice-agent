/**
 * Skeuomorphic design tokens — VOICE_AGENT_PRESETS.md §50
 * Central reference for JS/TS usage; CSS variables live in globals.css.
 */
export const skeuoTokens = {
  surface: {
    chassis: "var(--surface-chassis)",
    panel: "var(--surface-panel)",
    panelRaised: "var(--surface-panel-raised)",
    panelInset: "var(--surface-panel-inset)",
    glass: "var(--surface-glass)",
  },
  border: {
    subtle: "var(--border-subtle)",
    highlight: "var(--border-highlight)",
    inset: "var(--border-inset)",
  },
  shadow: {
    raised: "var(--shadow-raised)",
    inset: "var(--shadow-inset)",
    floating: "var(--shadow-floating)",
  },
  status: {
    success: "var(--status-success)",
    warning: "var(--status-warning)",
    error: "var(--status-error)",
    info: "var(--status-info)",
    live: "var(--status-live)",
  },
  radius: {
    sm: "var(--radius-sm)",
    md: "var(--radius-md)",
    lg: "var(--radius-lg)",
  },
} as const;
