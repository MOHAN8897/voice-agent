"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";
import type { TranscriptLine } from "@/lib/call-detail-types";
import { elapsedFromStart } from "@/lib/call-timeline-utils";

export function CallTranscriptTimeline({ lines }: { lines: TranscriptLine[] }) {
  const startTs = lines[0]?.ts;

  return (
    <SkeuoPanel
      title="Transcript"
      description="Speaker, timestamp, interruption metadata, and per-component latencies"
      padding="md"
    >
      {lines.length === 0 ? (
        <p className="text-sm text-text-muted">No transcript lines yet.</p>
      ) : (
        <ul className="space-y-2 max-h-[min(50vh,480px)] overflow-y-auto">
          {lines.map((line) => {
            const role = line.role || "unknown";
            const isUser = role === "user";
            return (
              <li
                key={`${line.seq}-${line.ts}-${role}`}
                className={cn(
                  "rounded-skeuo-sm border px-3 py-2",
                  isUser ? "skeuo-inset border-surface-border-subtle" : "border-accent-primary/15 bg-accent-primary/5",
                  line.partial && "opacity-60"
                )}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">
                      {elapsedFromStart(line.ts, startTs)}
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-wider text-text">
                      {isUser ? "USER" : "AGENT"}
                    </span>
                    {line.partial && (
                      <span className="font-mono text-[9px] uppercase text-status-warning">partial</span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2 font-mono text-[10px] text-text-subtle">
                    {line.stt_latency_ms != null && <span>STT {line.stt_latency_ms}ms</span>}
                    {line.brain_latency_ms != null && <span>LLM {line.brain_latency_ms}ms</span>}
                    {line.tts_first_byte_ms != null && <span>TTS {line.tts_first_byte_ms}ms</span>}
                  </div>
                </div>
                <p className={cn("mt-1 text-sm leading-relaxed text-text", line.partial && "line-through")}>
                  {line.text}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </SkeuoPanel>
  );
}
