"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";
import type { UnifiedTimelineEvent } from "@/lib/call-detail-types";

const LANE_META: Record<
  UnifiedTimelineEvent["lane"],
  { label: string; tone: string }
> = {
  audio: { label: "USER AUDIO", tone: "bg-surface-panel-raised text-text-muted" },
  stt: { label: "STT", tone: "bg-status-info/15 text-status-info" },
  llm: { label: "LLM", tone: "bg-accent-primary/15 text-accent-primary" },
  tts: { label: "TTS", tone: "bg-status-success/15 text-status-success" },
  memory: { label: "MEMORY", tone: "bg-accent-secondary/15 text-accent-secondary" },
  error: { label: "ERROR", tone: "bg-status-error/15 text-status-error" },
};

export function CallUnifiedTimeline({ events }: { events: UnifiedTimelineEvent[] }) {
  return (
    <SkeuoPanel
      title="Pipeline timeline"
      description="Correlated USER AUDIO · STT · LLM · TTS · MEMORY · ERRORS"
      padding="md"
    >
      {events.length === 0 ? (
        <p className="text-sm text-text-muted">Timeline populates after turns complete and trace is sealed.</p>
      ) : (
        <ol className="space-y-2 max-h-[min(50vh,420px)] overflow-y-auto">
          {events.map((ev) => {
            const meta = LANE_META[ev.lane];
            return (
              <li
                key={ev.id}
                className="flex gap-3 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset px-3 py-2"
              >
                <span
                  className={cn(
                    "shrink-0 rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider",
                    meta.tone
                  )}
                >
                  {meta.label}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {ev.turn != null && (
                      <span className="font-mono text-[10px] text-text-subtle">Turn {ev.turn}</span>
                    )}
                    <span className="text-sm font-medium text-text">{ev.label}</span>
                    {ev.ms != null && (
                      <span className="font-mono text-[10px] text-text-subtle">{ev.ms}ms</span>
                    )}
                  </div>
                  {ev.detail && (
                    <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-text-muted">{ev.detail}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </SkeuoPanel>
  );
}
