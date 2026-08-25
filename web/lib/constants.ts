export const PRIMARY_NAV = [
  { href: "/app", label: "Overview" },
  { href: "/app/agents", label: "Agents" },
  { href: "/app/test-studio", label: "Test Studio" },
  { href: "/app/calls", label: "Calls" },
  { href: "/app/analytics", label: "Analytics" },
  { href: "/app/integrations", label: "Integrations" },
  { href: "/app/settings", label: "Settings" },
] as const;

export const AGENT_WORKSPACE_TABS = [
  { slug: "summary", label: "Summary" },
  { slug: "brain", label: "Business Brain" },
  { slug: "voice", label: "Voice & Models" },
  { slug: "memory-schema", label: "Memory Schema" },
  { slug: "tools", label: "Tools & Actions" },
  { slug: "channels", label: "Channels" },
  { slug: "versions", label: "Versions & Deployment" },
] as const;

/** PRD §3 eight-section business brain taxonomy */
export const BRAIN_SECTION_LABELS: Record<string, string> = {
  identity_purpose: "Identity & Purpose",
  facts: "Facts",
  actions_limits: "Actions & Limits",
  flow_qualification: "Flow: qualify buyer",
  flow_callback: "Flow: arrange callback",
  scope_redirects: "Scope & Redirects",
  guardrails: "Guardrails",
  faq: "FAQ",
};

export const BRAIN_SECTION_ORDER = [
  "identity_purpose",
  "facts",
  "actions_limits",
  "flow_qualification",
  "flow_callback",
  "scope_redirects",
  "guardrails",
  "faq",
] as const;
