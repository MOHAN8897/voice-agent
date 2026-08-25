"use client";

const STATUS_LABELS: Record<string, string> = {
  idle: "Idle",
  connecting: "Connecting",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

export function DevMicOrb({
  status,
  level,
  active,
}: {
  status: string;
  level: number;
  active: boolean;
}) {
  const scale = 1 + Math.min(0.35, level * 0.5);
  const label = STATUS_LABELS[status] || status;

  return (
    <div className="flex flex-col items-center gap-4 py-6">
      <div className="relative flex h-28 w-28 items-center justify-center">
        {active && (
          <span
            className="absolute inset-0 rounded-full bg-accent/20 animate-pulse"
            style={{ transform: `scale(${scale * 1.15})` }}
          />
        )}
        <span
          className={`relative flex h-20 w-20 items-center justify-center rounded-full border-2 transition-transform duration-75 ${
            active
              ? "border-accent bg-accent/15 shadow-glow"
              : "border-surface-border bg-surface-raised"
          }`}
          style={{ transform: `scale(${active ? scale : 1})` }}
        >
          <svg viewBox="0 0 24 24" className="h-8 w-8 text-text" fill="currentColor" aria-hidden>
            <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-1.08A7 7 0 0 0 19 11h-2z" />
          </svg>
        </span>
      </div>
      <div className="text-center">
        <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Session state</p>
        <p className="mt-1 text-sm font-medium text-text">{label}</p>
      </div>
      <div className="flex h-2 w-48 gap-0.5 rounded-full bg-surface-raised p-0.5">
        {Array.from({ length: 24 }).map((_, i) => (
          <div
            key={i}
            className={`flex-1 rounded-full transition-all duration-75 ${
              active && level * 24 > i ? "bg-accent" : "bg-surface-border/60"
            }`}
          />
        ))}
      </div>
    </div>
  );
}
