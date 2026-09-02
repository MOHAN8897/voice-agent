"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";

export type TurnMetricRow = {
  turn: number;
  userText: string;
  assistantText: string;
  at: number;
  micDurationMs?: number;
  /** LLM */
  inputTokens?: number;
  outputTokens?: number;
  cachedTokens?: number;
  cacheWriteTokens?: number;
  /** STT */
  sttChars?: number;
  sttAudioSec?: number;
  /** TTS */
  ttsChars?: number;
  ttsAudioBytes?: number;
  memoryOps?: number;
  cacheHit?: boolean;
};

export type SessionUsageTotals = {
  sttChars: number;
  sttAudioSec: number;
  llmInput: number;
  llmOutput: number;
  llmCached: number;
  ttsChars: number;
  ttsAudioBytes: number;
  turns: number;
};

export function emptySessionTotals(): SessionUsageTotals {
  return {
    sttChars: 0,
    sttAudioSec: 0,
    llmInput: 0,
    llmOutput: 0,
    llmCached: 0,
    ttsChars: 0,
    ttsAudioBytes: 0,
    turns: 0,
  };
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  return `${(n / 1024).toFixed(1)} KB`;
}

function StatCell({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-skeuo-sm skeuo-inset px-2 py-2 text-center">
      <p className="font-mono text-[9px] uppercase text-text-subtle">{label}</p>
      <p className={cn("font-mono text-sm font-semibold", accent ? "text-status-success" : "text-text")}>
        {value}
      </p>
    </div>
  );
}

export function TestStudioTurnMetrics({
  rows,
  sessionTotal,
  mode = "agent",
}: {
  rows: TurnMetricRow[];
  sessionTotal: SessionUsageTotals;
  mode?: "agent" | "pstn";
}) {
  return (
    <div data-testid="test-studio-usage-panel">
    <SkeuoPanel
      title="Usage per turn"
      description={
        mode === "agent"
          ? "STT chars · LLM tokens · TTS chars/audio — each mic-on → mic-off turn"
          : "Agent usage appears in Agent only mode · PSTN calls tracked in Exotel panel"
      }
      padding="md"
    >
      <div className="mb-4 space-y-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Session totals</p>
        <div className="grid grid-cols-3 gap-2">
          <StatCell label="STT chars" value={String(sessionTotal.sttChars)} />
          <StatCell label="STT audio" value={`${sessionTotal.sttAudioSec.toFixed(1)}s`} />
          <StatCell label="Turns" value={String(sessionTotal.turns)} />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <StatCell label="LLM in" value={String(sessionTotal.llmInput)} />
          <StatCell label="LLM cached" value={String(sessionTotal.llmCached)} accent />
          <StatCell label="LLM out" value={String(sessionTotal.llmOutput)} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <StatCell label="TTS chars" value={String(sessionTotal.ttsChars)} />
          <StatCell label="TTS audio" value={formatBytes(sessionTotal.ttsAudioBytes)} />
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="text-xs text-text-muted" data-testid="usage-empty-hint">
          {mode === "agent"
            ? "Turn the mic on, speak, and turn it off — each completed turn shows STT, LLM, and TTS usage here."
            : "Switch to Agent only mode to measure per-turn STT / LLM / TTS usage with the browser mic."}
        </p>
      ) : (
        <div className="max-h-56 overflow-y-auto space-y-2" data-testid="usage-turn-list">
          {rows.map((r) => (
            <div
              key={`${r.turn}-${r.at}`}
              data-testid={`usage-turn-${r.turn}`}
              className="rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 text-xs"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-[10px] uppercase text-text-subtle">
                  Turn {r.turn}
                  {r.micDurationMs != null && (
                    <span className="ml-2 text-text-muted">· mic {Math.round(r.micDurationMs / 1000)}s</span>
                  )}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-1 font-mono text-[9px] text-text-muted">
                <div>
                  <span className="text-text-subtle">STT</span>
                  <br />
                  {r.sttChars ?? 0}c · {(r.sttAudioSec ?? 0).toFixed(1)}s
                </div>
                <div>
                  <span className="text-text-subtle">LLM</span>
                  <br />
                  in {r.inputTokens ?? 0} · out {r.outputTokens ?? 0}
                  {(r.cachedTokens ?? 0) > 0 && (
                    <span className="text-status-success"> · {r.cachedTokens}c</span>
                  )}
                </div>
                <div>
                  <span className="text-text-subtle">TTS</span>
                  <br />
                  {r.ttsChars ?? 0}c · {formatBytes(r.ttsAudioBytes ?? 0)}
                </div>
              </div>
              <p className="mt-1.5 truncate text-text-muted">You: {r.userText.slice(0, 50)}</p>
              <div className="mt-1 flex flex-wrap gap-2">
                {r.cacheHit && (
                  <span className="rounded bg-status-success/15 px-1.5 py-0.5 font-mono text-[9px] text-status-success">
                    prompt cache hit
                  </span>
                )}
                {(r.memoryOps ?? 0) > 0 && (
                  <span className="rounded bg-accent-primary/10 px-1.5 py-0.5 font-mono text-[9px] text-accent-primary">
                    memory +{r.memoryOps}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </SkeuoPanel>
    </div>
  );
}
