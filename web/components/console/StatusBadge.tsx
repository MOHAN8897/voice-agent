const TONES: Record<string, string> = {
  success: "bg-accent-dim text-success",
  warning: "bg-warning/10 text-warning",
  info: "bg-surface-raised text-accent-secondary",
  muted: "bg-surface-raised text-text-muted",
  accent: "bg-accent-dim text-accent",
};

export function StatusBadge({
  children,
  tone = "muted",
}: {
  children: React.ReactNode;
  tone?: keyof typeof TONES;
}) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function dispositionTone(value?: string): keyof typeof TONES {
  const v = (value || "").toLowerCase();
  if (["can_convert", "qualified", "booked", "completed"].some((k) => v.includes(k))) return "success";
  if (["failed", "no_answer", "busy", "error"].some((k) => v.includes(k))) return "warning";
  if (!v) return "muted";
  return "info";
}
