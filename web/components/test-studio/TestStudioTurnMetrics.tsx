"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";

export type TurnMetricRow = {
  turn: number;
  userText: string;
  assistantText: string;
  at: number;
  inputTokens?: number;
  outputTokens?: number;
  cachedTokens?: number;
  cacheWriteTokens?: number;
  memoryOps?: number;
  cacheHit?: boolean;
};

export function TestStudioTurnMetrics({
  rows,
  sessionTotal,
}: {
  rows: TurnMetricRow[];
  sessionTotal: {
    input: number;
    output: number;
    cached: number;
  };
}) {
  return (
    <SkeuoPanel title="Token usage" description="Per-turn LLM tokens · cache breakpoint savings" padding="md">
      <div className="mb-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-skeuo-sm skeuo-inset px-2 py-2">
          <p className="font-mono text-[9px] uppercase text-text-subtle">Input</p>
          <p className="font-mono text-sm font-semibold text-text">{sessionTotal.input}</p>
        </div>
        <div className="rounded-skeuo-sm skeuo-inset px-2 py-2">
          <p className="font-mono text-[9px] uppercase text-text-subtle">Cached</p>
          <p className="font-mono text-sm font-semibold text-status-success">{sessionTotal.cached}</p>
        </div>
        <div className="rounded-skeuo-sm skeuo-inset px-2 py-2">
          <p className="font-mono text-[9px] uppercase text-text-subtle">Output</p>
          <p className="font-mono text-sm font-semibold text-text">{sessionTotal.output}</p>
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="text-xs text-text-muted">Complete a spoken turn to see token breakdown per turn.</p>
      ) : (
        <div className="max-h-48 overflow-y-auto space-y-2">
          {rows.map((r) => (
            <div
              key={`${r.turn}-${r.at}`}
              className="rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 text-xs"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-[10px] uppercase text-text-subtle">Turn {r.turn}</span>
                <span className="font-mono text-[10px] text-text-muted">
                  in {r.inputTokens ?? 0} · out {r.outputTokens ?? 0}
                  {(r.cachedTokens ?? 0) > 0 && (
                    <span className="text-status-success"> · cached {r.cachedTokens}</span>
                  )}
                </span>
              </div>
              <p className="mt-1 truncate text-text-muted">You: {r.userText.slice(0, 60)}</p>
              <div className="mt-1 flex flex-wrap gap-2">
                {r.cacheHit && (
                  <span className="rounded bg-status-success/15 px-1.5 py-0.5 font-mono text-[9px] text-status-success">
                    prompt cache hit
                  </span>
                )}
                {(r.memoryOps ?? 0) > 0 && (
                  <span className="rounded bg-accent-primary/10 px-1.5 py-0.5 font-mono text-[9px] text-accent-primary">
                    memory +{r.memoryOps} ops
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </SkeuoPanel>
  );
}
