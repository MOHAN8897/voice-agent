"use client";

import { cn } from "@/lib/cn";

export type TranscriptLine = {
  role: "user" | "assistant";
  text: string;
  interrupted?: boolean;
  ts?: number;
};

export function LiveTranscriptConsole({
  lines,
  partial,
  speaking,
}: {
  lines: TranscriptLine[];
  partial?: string;
  speaking?: boolean;
}) {
  return (
    <section
      className="skeuo-inset min-h-[220px] max-h-80 overflow-y-auto rounded-skeuo-md border border-surface-border-subtle p-3"
      aria-label="Live transcript monitor"
      role="region"
    >
      <header className="mb-3 flex items-center justify-between border-b border-surface-border-subtle pb-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">Live monitor</p>
        {speaking && (
          <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-status-info">
            <span className="skeuo-led skeuo-led-info animate-pulse-soft" aria-hidden />
            TTS playing
          </span>
        )}
      </header>

      {lines.length === 0 && !partial ? (
        <p className="text-sm text-text-muted">Press the voice control — transcript lines appear with timing metadata.</p>
      ) : (
        <div className="space-y-3">
          {lines.map((line, i) => (
            <article
              key={`${line.role}-${i}-${line.ts ?? i}`}
              className={cn(
                "rounded-skeuo-sm border px-3 py-2",
                line.role === "user"
                  ? "border-surface-border-subtle bg-surface-panel/60"
                  : "border-accent-primary/15 bg-accent-primary/5",
                line.interrupted && "opacity-60"
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">
                  {line.role === "user" ? "USER" : "AGENT"}
                </span>
                {line.ts && (
                  <span className="font-mono text-[10px] text-text-subtle">
                    {new Date(line.ts).toLocaleTimeString()}
                  </span>
                )}
              </div>
              <p
                className={cn(
                  "mt-1 text-sm leading-relaxed text-text",
                  line.interrupted && "line-through decoration-status-warning/60"
                )}
              >
                {line.text}
              </p>
              {line.interrupted && (
                <p className="mt-1 font-mono text-[9px] uppercase tracking-wider text-status-warning">Interrupted</p>
              )}
            </article>
          ))}
          {partial && (
            <article className="rounded-skeuo-sm border border-dashed border-accent-primary/25 px-3 py-2">
              <span className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">USER · partial</span>
              <p className="mt-1 text-sm text-text-muted">{partial}</p>
            </article>
          )}
        </div>
      )}
    </section>
  );
}
