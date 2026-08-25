export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "ok" | "warn" | "accent";
}) {
  const valueClass =
    tone === "ok"
      ? "text-success"
      : tone === "warn"
        ? "text-warning"
        : tone === "accent"
          ? "text-accent"
          : "text-text";

  return (
    <div className="rounded-2xl border border-surface-border-subtle bg-surface-card p-4">
      <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">{label}</p>
      <p className={`mt-2 text-2xl font-medium tracking-tight ${valueClass}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-text-muted">{hint}</p>}
    </div>
  );
}
