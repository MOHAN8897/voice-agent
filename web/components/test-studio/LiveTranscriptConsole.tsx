"use client";

import { useEffect, useRef } from "react";
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
  thinking,
  className,
}: {
  lines: TranscriptLine[];
  partial?: string;
  speaking?: boolean;
  thinking?: boolean;
  className?: string;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [lines, partial, speaking, thinking]);

  return (
    <section
      ref={scrollRef}
      className={cn(
        "skeuo-inset min-h-[280px] max-h-[min(52vh,420px)] overflow-y-auto rounded-skeuo-md border border-surface-border-subtle p-3",
        className
      )}
      aria-label="Conversation transcript"
      role="log"
      aria-live="polite"
    >
      <header className="mb-3 flex items-center justify-between border-b border-surface-border-subtle pb-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">Conversation</p>
        <div className="flex items-center gap-2">
          {thinking && (
            <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-status-warn">
              <span className="skeuo-led skeuo-led-warn animate-pulse-soft" aria-hidden />
              Agent thinking
            </span>
          )}
          {speaking && (
            <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-status-info">
              <span className="skeuo-led skeuo-led-info animate-pulse-soft" aria-hidden />
              Speaking
            </span>
          )}
        </div>
      </header>

      {lines.length === 0 && !partial ? (
        <p className="text-sm text-text-muted">
          Start the mic — your speech and the agent&apos;s replies appear here as a chat thread.
        </p>
      ) : (
        <div className="space-y-3">
          {lines.map((line, i) => (
            <article
              key={`${line.role}-${i}-${line.ts ?? i}`}
              className={cn(
                "max-w-[92%] rounded-skeuo-sm border px-3 py-2",
                line.role === "user"
                  ? "ml-auto border-surface-border-subtle bg-surface-panel/80"
                  : "mr-auto border-accent-primary/20 bg-accent-primary/8",
                line.interrupted && "opacity-60"
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">
                  {line.role === "user" ? "You" : "Agent"}
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
            <article className="ml-auto max-w-[92%] rounded-skeuo-sm border border-dashed border-accent-primary/30 bg-surface-panel/50 px-3 py-2">
              <span className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">You · speaking…</span>
              <p className="mt-1 text-sm text-text-muted">{partial}</p>
            </article>
          )}
        </div>
      )}
    </section>
  );
}
