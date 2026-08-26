import { cn } from "@/lib/cn";

const TONES: Record<string, string> = {
  success: "text-status-success border-status-success/30 bg-status-success/10",
  warning: "text-status-warning border-status-warning/30 bg-status-warning/10",
  error: "text-status-error border-status-error/30 bg-status-error/10",
  info: "text-status-info border-status-info/30 bg-status-info/10",
  muted: "text-text-muted border-surface-border-subtle bg-surface-panel-inset",
  accent: "text-accent-primary border-accent-primary/30 bg-accent-primary/10",
  live: "text-status-live border-status-live/30 bg-status-live/10",
};

export function SkeuoBadge({
  children,
  tone = "muted",
  className,
}: {
  children: React.ReactNode;
  tone?: keyof typeof TONES;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-skeuo-sm border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider skeuo-inset",
        TONES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

export function dispositionTone(value?: string): "success" | "warning" | "info" | "muted" {
  const v = (value || "").toLowerCase();
  if (["can_convert", "qualified", "booked", "completed"].some((k) => v.includes(k))) return "success";
  if (["failed", "no_answer", "busy", "error"].some((k) => v.includes(k))) return "warning";
  if (!v) return "muted";
  return "info";
}
