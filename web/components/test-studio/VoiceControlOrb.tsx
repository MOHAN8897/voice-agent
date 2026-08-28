"use client";

import { cn } from "@/lib/cn";

const STATUS_LABELS: Record<string, string> = {
  idle: "READY",
  ready: "READY",
  paused: "MIC OFF",
  connecting: "CONNECTING",
  listening: "LISTENING",
  thinking: "THINKING",
  speaking: "SPEAKING",
  ended: "ENDED",
};

const STATUS_LED: Record<string, string> = {
  idle: "skeuo-led-idle",
  ready: "skeuo-led-ok",
  paused: "skeuo-led-warn",
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
  callActive,
}: {
  status: string;
  level: number;
  active: boolean;
  listening?: boolean;
  callActive?: boolean;
  onStart?: () => void;
  onStop?: () => void;
}) {
  const micOn = Boolean(listening);
  const normalized = status === "idle" ? "ready" : status;
  const scale = 1 + Math.min(0.32, level * 0.5);
  const label = STATUS_LABELS[normalized] || status.toUpperCase();

  return (
    <div className="flex flex-col items-center gap-4 py-2">
      <div className="relative">
        <div
          className={cn(
            "absolute inset-0 rounded-full blur-2xl transition-opacity duration-300",
            micOn ? "bg-status-live/25 opacity-100" : "bg-accent-primary/10 opacity-60"
          )}
          style={{ transform: `scale(${micOn ? scale * 1.15 : 1})` }}
          aria-hidden
        />
        <button
          type="button"
          onClick={micOn ? onStop : onStart}
          disabled={!onStart && !onStop}
          className={cn(
            "relative flex h-36 w-36 items-center justify-center rounded-full border-[3px] transition-all duration-200",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/50",
            micOn
              ? "border-status-live bg-gradient-to-b from-status-live/20 to-status-live/5 shadow-[0_0_40px_-6px_rgba(225,29,72,0.6)]"
              : "border-surface-border skeuo-panel hover:border-accent-primary/30"
          )}
          style={{ transform: `scale(${micOn ? scale : 1})` }}
          aria-label={micOn ? "Turn microphone off" : "Turn microphone on"}
          aria-pressed={micOn}
        >
          {micOn && (
            <>
              <span
                className="absolute inset-2 rounded-full border border-status-live/30 animate-pulse-soft"
                aria-hidden
              />
              <span
                className="absolute inset-0 rounded-full border-2 border-status-live/20"
                style={{ transform: `scale(${scale * 1.08})` }}
                aria-hidden
              />
            </>
          )}
          <svg
            viewBox="0 0 24 24"
            className={cn("relative h-11 w-11 transition-colors", micOn ? "text-status-live" : "text-text")}
            fill="currentColor"
            aria-hidden
          >
            {micOn ? (
              <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-1.08A7 7 0 0 0 19 11h-2z" />
            ) : (
              <>
                <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3z" opacity="0.45" />
                <path d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-14 0H3c0 1.19.34 2.3.9 3.28l1.23-1.23c-.27-.62-.43-1.31-.43-2.05zM14.3 4.71l1.04-1.04A9.96 9.96 0 0 0 12 2C8.14 2 5 5.14 5 9H7c0-2.76 2.24-5 5-5 .96 0 1.85.27 2.62.71zM4.27 3 3 4.27 7.73 9H3v2h4l5 5v-3.28l4.73 4.73 1.27-1.27L4.27 3z" />
              </>
            )}
          </svg>
          <span
            className={cn(
              "absolute -bottom-0.5 right-3 h-3.5 w-3.5 rounded-full skeuo-led ring-2 ring-surface-panel",
              STATUS_LED[normalized] || "skeuo-led-idle"
            )}
            aria-hidden
          />
        </button>
      </div>

      <div className="flex flex-col items-center gap-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-subtle">Live mic</p>
        <p className="font-mono text-sm font-semibold tracking-wider text-text">{label}</p>
        {callActive && !micOn && (
          <p className="text-[10px] text-status-warning">Call active — mic muted</p>
        )}
      </div>

      <button
        type="button"
        role="switch"
        aria-checked={micOn}
        disabled={!onStart && !onStop}
        onClick={micOn ? onStop : onStart}
        className={cn(
          "relative flex h-9 w-[4.5rem] items-center rounded-full border border-surface-border-subtle p-1 transition-colors",
          micOn ? "bg-status-live/20" : "skeuo-inset bg-surface-panel-inset"
        )}
      >
        <span
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-full shadow-skeuo-sm transition-transform duration-200",
            micOn ? "translate-x-[2.15rem] bg-status-live text-white" : "translate-x-0 bg-surface-raised text-text-muted"
          )}
        >
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="currentColor" aria-hidden>
            {micOn ? (
              <path d="M8 9.5a1.5 1.5 0 0 0 1.5-1.5V4.5a1.5 1.5 0 1 0-3 0V8A1.5 1.5 0 0 0 8 9.5zm3-1.5a3 3 0 0 1-6 0H3.5a6.5 6.5 0 0 0 5.5 6.42V14h1.5v-.58A6.5 6.5 0 0 0 16 8h-2.5z" />
            ) : (
              <path d="M3.27 2 2 3.27 5.27 6.5H2.5v1h3.5l2 2v-1.1l2.73 2.73 1.27-1.27L3.27 2zM8 9.5a1.5 1.5 0 0 0 1.5-1.5V6.27L6.77 4.04A1.5 1.5 0 0 1 8 4.5V8c0 .17-.03.33-.08.48L9.02 9.58c.16-.35.25-.73.25-1.13V8a3 3 0 0 0-2.12-2.87L8 9.5zm5 0H11c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28H13z" />
            )}
          </svg>
        </span>
        <span className="sr-only">{micOn ? "Microphone on" : "Microphone off"}</span>
      </button>

      <div className="skeuo-inset flex h-3 w-full max-w-[13rem] gap-0.5 rounded-full p-0.5">
        {Array.from({ length: 28 }).map((_, i) => (
          <div
            key={i}
            className={cn(
              "flex-1 rounded-full transition-all duration-75",
              micOn && level * 28 > i ? "bg-status-live/85" : "bg-surface-panel-raised"
            )}
          />
        ))}
      </div>
    </div>
  );
}
