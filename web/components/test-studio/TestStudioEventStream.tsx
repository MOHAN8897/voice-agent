"use client";

import { useState } from "react";
import type { SessionTraceEvent } from "@/components/live/LiveVoiceSession";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { cn } from "@/lib/cn";

const KIND_COLORS: Record<string, string> = {
  call: "text-accent-primary bg-accent-primary/15",
  stt: "text-status-info bg-status-info/15",
  vad: "text-status-warning bg-status-warning/15",
  brain: "text-accent-secondary bg-accent-secondary/15",
  tts: "text-status-success bg-status-success/15",
};

export function TestStudioEventStream({ events }: { events: SessionTraceEvent[] }) {
  const [open, setOpen] = useState(true);

  return (
    <SkeuoPanel title="Event stream" description="Conversation trace · provider signals" padding="md">
      <SkeuoButton variant="ghost" size="sm" onClick={() => setOpen((v) => !v)} className="mb-3">
        {open ? "Collapse" : "Expand"} trace
      </SkeuoButton>
      {open && (
        <ul className="max-h-48 space-y-1 overflow-y-auto font-mono text-[11px] skeuo-inset rounded-skeuo-sm p-2">
          {events.length === 0 ? (
            <li className="text-text-muted">Start a session to see events.</li>
          ) : (
            events.map((e, i) => (
              <li key={`${e.at}-${i}`} className="flex gap-2 text-text-muted">
                <span className={cn("rounded px-1 shrink-0", KIND_COLORS[e.kind] || "bg-surface-panel-raised")}>
                  {e.kind}
                </span>
                <span className="truncate">{e.detail}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </SkeuoPanel>
  );
}
