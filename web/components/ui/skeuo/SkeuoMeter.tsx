import { cn } from "@/lib/cn";

/** Instrument-style readout — VOICE_AGENT_PRESETS §11 latency/cost modules */
export function SkeuoMeter({
  label,
  value,
  unit,
  hint,
  tone = "default",
  className,
}: {
  label: string;
  value: string;
  unit?: string;
  hint?: string;
  tone?: "default" | "ok" | "warn" | "accent";
  className?: string;
}) {
  const valueTone =
    tone === "ok"
      ? "text-status-success"
      : tone === "warn"
        ? "text-status-warning"
        : tone === "accent"
          ? "text-accent-primary"
          : "text-text";

  return (
    <div className={cn("skeuo-inset rounded-skeuo-md p-4", className)}>
      <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-text-subtle">{label}</p>
      <div className="mt-2 flex items-baseline gap-1">
        <span className={cn("font-mono text-2xl font-medium tabular-nums tracking-tight", valueTone)}>{value}</span>
        {unit && <span className="font-mono text-xs text-text-muted">{unit}</span>}
      </div>
      {hint && <p className="mt-1.5 text-xs leading-relaxed text-text-muted">{hint}</p>}
    </div>
  );
}
