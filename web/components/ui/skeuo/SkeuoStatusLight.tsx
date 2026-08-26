import { cn } from "@/lib/cn";

type Status = "ok" | "warn" | "error" | "info" | "idle" | "live";

const toneClass: Record<Status, string> = {
  ok: "skeuo-led-ok",
  warn: "skeuo-led-warn",
  error: "skeuo-led-error",
  info: "skeuo-led-info",
  idle: "skeuo-led-idle",
  live: "skeuo-led-live",
};

export function SkeuoStatusLight({
  status = "idle",
  label,
  pulse = false,
  className,
}: {
  status?: Status;
  label?: string;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span
        className={cn(
          "skeuo-led",
          toneClass[status],
          pulse && status !== "idle" && "animate-pulse-soft"
        )}
        aria-hidden
      />
      {label && <span className="font-mono text-[10px] uppercase tracking-wider text-text-muted">{label}</span>}
    </span>
  );
}
