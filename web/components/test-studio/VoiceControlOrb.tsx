"use client";

import { cn } from "@/lib/cn";

const STATUS_LABELS: Record<string, string> = {
  idle: "READY",
  ready: "READY",
  connecting: "CONNECTING",
  listening: "LISTENING",
  thinking: "THINKING",
  speaking: "SPEAKING",
  ended: "ENDED",
};

const STATUS_LED: Record<string, string> = {
  idle: "skeuo-led-idle",
  ready: "skeuo-led-ok",
  connecting: "skeuo-led-info",
  listening: "skeuo-led-live",
  thinking: "skeuo-led-warn",
  speaking: "skeuo-led-info",
  ended: "skeuo-led-idle",
};

export function VoiceControlOrb({
  status,
  level,
  active,
  onStart,
  onStop,
  listening,
}: {
  status: string;
  level: number;
  active: boolean;
  listening?: boolean;
  onStart?: () => void;
  onStop?: () => void;
}) {
  const normalized = status === "idle" ? "ready" : status;
  const scale = 1 + Math.min(0.28, level * 0.45);
  const label = STATUS_LABELS[normalized] || status.toUpperCase();

  return (
    <div className="flex flex-col items-center gap-5 py-4">
      <button
        type="button"
        onClick={listening ? onStop : onStart}
        disabled={!onStart && !onStop}
        className={cn(
          "relative flex h-32 w-32 items-center justify-center rounded-full border-2 transition-all duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
          active
            ? "border-status-live/50 bg-status-live/10 shadow-[0_0_32px_-8px_rgba(225,29,72,0.55)]"
            : "border-surface-border-subtle skeuo-panel hover:border-accent-primary/25"
        )}
        style={{ transform: `scale(${active ? scale : 1})` }}
        aria-label={listening ? "Stop listening" : "Start listening"}
      >
        {active && (
          <span
            className="absolute inset-0 rounded-full bg-status-live/15 animate-pulse-soft"
            style={{ transform: `scale(${scale * 1.12})` }}
            aria-hidden
          />
        )}
        <svg viewBox="0 0 24 24" className="relative h-10 w-10 text-text" fill="currentColor" aria-hidden>
          <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-1.08A7 7 0 0 0 19 11h-2z" />
        </svg>
        <span
          className={cn("absolute -bottom-1 right-2 h-3 w-3 rounded-full skeuo-led", STATUS_LED[normalized] || "skeuo-led-idle")}
          aria-hidden
        />
      </button>

      <div className="text-center">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">Voice control</p>
        <p className="mt-1 font-mono text-sm font-semibold tracking-wider text-text">{label}</p>
      </div>

      <div className="skeuo-inset flex h-3 w-full max-w-xs gap-0.5 rounded-full p-0.5">
        {Array.from({ length: 32 }).map((_, i) => (
          <div
            key={i}
            className={cn(
              "flex-1 rounded-full transition-all duration-75",
              active && level * 32 > i ? "bg-accent-primary/80" : "bg-surface-panel-raised"
            )}
          />
        ))}
      </div>
    </div>
  );
}
