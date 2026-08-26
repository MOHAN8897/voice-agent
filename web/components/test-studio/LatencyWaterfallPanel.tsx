"use client";

import { useMemo } from "react";
import type { SessionTraceEvent } from "@/components/live/LiveVoiceSession";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";

type TurnLatency = {
  turn: number;
  sttMs: number;
  llmMs: number;
  ttsMs: number;
  e2eMs: number;
};

function buildTurns(events: SessionTraceEvent[]): TurnLatency[] {
  const turns: TurnLatency[] = [];
  let turnStart = 0;
  let sttAt = 0;
  let brainStart = 0;
  let brainEnd = 0;
  let ttsAt = 0;
  let turn = 0;

  for (const e of events) {
    if (e.kind === "stt" && e.detail.startsWith("final")) {
      turn += 1;
      turnStart = e.at;
      sttAt = e.at;
      brainStart = 0;
      brainEnd = 0;
      ttsAt = 0;
    } else if (e.kind === "brain" && e.detail.includes("stream start")) {
      brainStart = e.at;
    } else if (e.kind === "brain" && e.detail.includes("stream done")) {
      brainEnd = e.at;
    } else if (e.kind === "tts" && e.detail.includes("request")) {
      ttsAt = e.at;
      if (turnStart && brainEnd) {
        const sttMs = brainStart ? brainStart - turnStart : 0;
        const llmMs = brainEnd - (brainStart || turnStart);
        const ttsMs = ttsAt - brainEnd;
        const e2eMs = ttsAt - turnStart;
        turns.push({ turn, sttMs, llmMs, ttsMs, e2eMs });
      }
    }
  }
  return turns;
}

function Bar({ label, ms, maxMs, tone }: { label: string; ms: number; maxMs: number; tone: string }) {
  const width = maxMs > 0 ? Math.min(100, Math.round((ms / maxMs) * 100)) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between font-mono text-[10px] uppercase tracking-wider text-text-subtle">
        <span>{label}</span>
        <span>{ms > 0 ? `${ms}ms` : "—"}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full skeuo-inset">
        <div className={cn("h-full rounded-full transition-all duration-300", tone)} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export function LatencyWaterfallPanel({ events }: { events: SessionTraceEvent[] }) {
  const turns = useMemo(() => buildTurns(events), [events]);
  const maxMs = useMemo(
    () => Math.max(1, ...turns.flatMap((t) => [t.sttMs, t.llmMs, t.ttsMs, t.e2eMs])),
    [turns]
  );

  return (
    <SkeuoPanel
      title="Latency waterfall"
      description="STT → LLM TTFT → TTS first audio — instrument trace per turn"
      padding="md"
      className="console-page-enter"
    >
      {turns.length === 0 ? (
        <p className="text-sm text-text-muted">
          Complete at least one spoken turn to see STT, LLM, and TTS segments.
        </p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {turns.map((t) => (
            <div key={t.turn} className="skeuo-inset rounded-skeuo-md p-4 space-y-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-accent-primary">Turn {t.turn}</p>
              <Bar label="STT final" ms={t.sttMs} maxMs={maxMs} tone="bg-status-info/70" />
              <Bar label="LLM stream" ms={t.llmMs} maxMs={maxMs} tone="bg-accent-primary/70" />
              <Bar label="TTS request" ms={t.ttsMs} maxMs={maxMs} tone="bg-status-success/70" />
              <div className="border-t border-surface-border-subtle pt-2 font-mono text-xs text-text-muted">
                E2E <span className="text-text">{t.e2eMs}ms</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </SkeuoPanel>
  );
}
