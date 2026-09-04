"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";
import {
  cacheEventLabel,
  estimateTurnCost,
  formatInr,
  formatUsd,
  perMinute,
  splitLlmTokens,
  type CacheEvent,
  type PricingMeta,
} from "@/lib/usage-cost";

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
  cacheEvent?: CacheEvent;
};

export type SessionUsageTotals = {
  sttChars: number;
  sttAudioSec: number;
  llmInput: number;
  llmOutput: number;
  llmCached: number;
  llmCacheWrite: number;
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
    llmCacheWrite: 0,
    ttsChars: 0,
    ttsAudioBytes: 0,
    turns: 0,
  };
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  return `${(n / 1024).toFixed(1)} KB`;
}

function StatCell({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-skeuo-sm skeuo-inset px-2 py-2 text-center">
      <p className="font-mono text-[9px] uppercase text-text-subtle">{label}</p>
      <p className={cn("font-mono text-sm font-semibold", accent ? "text-status-success" : "text-text")}>
        {value}
      </p>
      {sub ? <p className="mt-0.5 font-mono text-[9px] text-text-muted">{sub}</p> : null}
    </div>
  );
}

function cacheTone(event: CacheEvent): string {
  if (event === "cache_hit") return "bg-status-success/15 text-status-success";
  if (event === "cache_write") return "bg-status-warning/15 text-status-warning";
  if (event === "partial_hit") return "bg-accent-primary/10 text-accent-primary";
  return "bg-surface-raised text-text-muted";
}

export function TestStudioTurnMetrics({
  rows,
  sessionTotal,
  mode = "agent",
  ttsProvider = "sarvam",
  ttsModel = "",
  sttProvider = "sarvam",
  sttModel = "",
  llmModel = "gpt-5.6-luna",
  pricing,
  sessionDurationMs = 0,
}: {
  rows: TurnMetricRow[];
  sessionTotal: SessionUsageTotals;
  mode?: "agent" | "pstn";
  ttsProvider?: string;
  ttsModel?: string;
  sttProvider?: string;
  sttModel?: string;
  llmModel?: string;
  pricing?: PricingMeta | null;
  sessionDurationMs?: number;
}) {
  const sessionCost = estimateTurnCost({
    sttAudioSec: sessionTotal.sttAudioSec,
    ttsChars: sessionTotal.ttsChars,
    ttsProvider,
    ttsModel,
    sttProvider,
    sttModel,
    llmModel,
    inputTokens: sessionTotal.llmInput,
    outputTokens: sessionTotal.llmOutput,
    cachedTokens: sessionTotal.llmCached,
    cacheWriteTokens: sessionTotal.llmCacheWrite,
    meta: pricing,
  });
  const wallSec = Math.max(sessionDurationMs / 1000, sessionTotal.sttAudioSec, 0);
  const perMinWall = perMinute(sessionCost.totalUsd, wallSec, sessionCost.fx);
  const perMinStt = perMinute(sessionCost.totalUsd, sessionTotal.sttAudioSec, sessionCost.fx);
  const cachePct =
    sessionTotal.llmInput > 0 ? Math.round((sessionTotal.llmCached / sessionTotal.llmInput) * 100) : 0;

  return (
    <div data-testid="test-studio-usage-panel">
      <SkeuoPanel
        title="Usage per turn"
        description={
          mode === "agent"
            ? "STT chars (user transcript) · TTS chars (LLM reply → speech) · LLM tokens (cache hit vs write)"
            : "Agent usage appears in Agent only mode · PSTN calls tracked in Exotel panel"
        }
        padding="md"
      >
        <div className="mb-4 space-y-3">
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Session totals</p>
          <div className="grid grid-cols-2 gap-2">
            <StatCell
              label="Session cost"
              value={formatInr(sessionCost.totalInr)}
              sub={formatUsd(sessionCost.totalUsd)}
              accent
            />
            <StatCell
              label="Per minute"
              value={formatInr(perMinWall.inr)}
              sub={`${formatUsd(perMinWall.usd)} · mic on→off`}
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <StatCell
              label="STT"
              value={formatInr(sessionCost.sttInr)}
              sub={`${sessionTotal.sttAudioSec.toFixed(1)}s · ₹30/hr`}
            />
            <StatCell
              label="STT chars"
              value={String(sessionTotal.sttChars)}
              sub="user transcript processed"
            />
            <StatCell
              label="TTS chars"
              value={String(sessionTotal.ttsChars)}
              sub="LLM reply → speech"
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <StatCell
              label="LLM"
              value={formatInr(sessionCost.llmInr)}
              sub={`${cachePct}% cached · ${formatUsd(sessionCost.llmUsd)}`}
            />
            <StatCell label="Turns" value={String(sessionTotal.turns)} />
            <StatCell label="LLM out" value={String(sessionTotal.llmOutput)} sub={`in ${sessionTotal.llmInput} · ${sessionTotal.llmCached} hit`} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <StatCell label="LLM in" value={String(sessionTotal.llmInput)} sub={`${sessionTotal.llmCached} cached · ${sessionTotal.llmCacheWrite} write`} />
            <StatCell
              label="TTS"
              value={formatInr(sessionCost.ttsInr)}
              sub={`${formatUsd(sessionCost.ttsUsd)} · ₹3/1k chars`}
            />
            <StatCell label="TTS audio" value={formatBytes(sessionTotal.ttsAudioBytes)} />
          </div>
          {sessionTotal.sttAudioSec > 0 && Math.abs(perMinStt.inr - perMinWall.inr) > 0.01 ? (
            <p className="font-mono text-[9px] text-text-subtle">
              Blended ₹/min on STT audio only: {formatInr(perMinStt.inr)} ({formatUsd(perMinStt.usd)})
            </p>
          ) : null}
          <p className="font-mono text-[9px] text-text-subtle">
            FX ₹{sessionCost.fx.toFixed(2)}/$ · STT {sttProvider}/{sttModel || "default"} · TTS {ttsProvider}/
            {ttsModel || "default"} · LLM {llmModel}
          </p>
        </div>

        {rows.length === 0 ? (
          <p className="text-xs text-text-muted" data-testid="usage-empty-hint">
            {mode === "agent"
              ? "Turn the mic on, speak, and turn it off — each completed turn shows STT, LLM, and TTS cost here."
              : "Switch to Agent only mode to measure per-turn STT / LLM / TTS usage with the browser mic."}
          </p>
        ) : (
          <div className="max-h-72 overflow-y-auto space-y-2" data-testid="usage-turn-list">
            <div className="grid grid-cols-3 gap-1 px-1 font-mono text-[9px] uppercase tracking-wide text-text-subtle">
              <span>STT chars</span>
              <span>LLM in</span>
              <span>TTS chars</span>
            </div>
            {rows.map((r) => {
              const cost = estimateTurnCost({
                sttAudioSec: r.sttAudioSec ?? 0,
                ttsChars: r.ttsChars ?? 0,
                ttsProvider,
                ttsModel,
                sttProvider,
                sttModel,
                llmModel,
                inputTokens: r.inputTokens ?? 0,
                outputTokens: r.outputTokens ?? 0,
                cachedTokens: r.cachedTokens ?? 0,
                cacheWriteTokens: r.cacheWriteTokens ?? 0,
                meta: pricing,
              });
              const event = r.cacheEvent || cost.cacheEvent;
              const turnSec = (r.micDurationMs ?? 0) / 1000 || r.sttAudioSec || 0;
              const turnPerMin = perMinute(cost.totalUsd, turnSec, cost.fx);
              const llmParts = splitLlmTokens(
                r.inputTokens ?? 0,
                r.cachedTokens ?? 0,
                r.cacheWriteTokens ?? 0
              );
              return (
                <div
                  key={`${r.turn}-${r.at}`}
                  data-testid={`usage-turn-${r.turn}`}
                  className="rounded-skeuo-sm border border-surface-border-subtle px-3 py-2 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono text-[10px] uppercase text-text-subtle">
                      Turn {r.turn}
                      {r.sttAudioSec != null && (
                        <span className="ml-2 text-text-muted">· STT {r.sttAudioSec.toFixed(1)}s</span>
                      )}
                    </span>
                    <span className="font-mono text-[11px] font-semibold text-text">
                      {formatInr(cost.totalInr)}{" "}
                      <span className="font-normal text-text-muted">{formatUsd(cost.totalUsd)}</span>
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-1 font-mono text-[9px] text-text-muted">
                    <div>
                      <span className="text-text-subtle">STT chars</span>
                      <br />
                      <span className="text-sm font-semibold text-text">{r.sttChars ?? 0}</span>
                      <br />
                      {formatInr(cost.sttInr)} · {(r.sttAudioSec ?? 0).toFixed(1)}s
                    </div>
                    <div>
                      <span className="text-text-subtle">LLM in</span>
                      <br />
                      {formatInr(cost.llmInr)}
                      <br />
                      miss {llmParts.uncached} · hit {llmParts.cached} · write {llmParts.written} · out{" "}
                      {r.outputTokens ?? 0}
                    </div>
                    <div>
                      <span className="text-text-subtle">TTS chars</span>
                      <br />
                      <span className="text-sm font-semibold text-text">{r.ttsChars ?? 0}</span>
                      <br />
                      {formatInr(cost.ttsInr)} · {formatBytes(r.ttsAudioBytes ?? 0)}
                    </div>
                  </div>
                  {turnSec > 0 ? (
                    <p className="mt-1 font-mono text-[9px] text-text-subtle">
                      This turn ₹/min {formatInr(turnPerMin.inr)} ({formatUsd(turnPerMin.usd)})
                    </p>
                  ) : null}
                  <p className="mt-1.5 truncate text-text-muted">You: {r.userText.slice(0, 50)}</p>
                  <div className="mt-1 flex flex-wrap gap-2">
                    <span className={cn("rounded px-1.5 py-0.5 font-mono text-[9px]", cacheTone(event))}>
                      {cacheEventLabel(event)}
                    </span>
                    {(r.memoryOps ?? 0) > 0 && (
                      <span className="rounded bg-accent-primary/10 px-1.5 py-0.5 font-mono text-[9px] text-accent-primary">
                        memory +{r.memoryOps}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SkeuoPanel>
    </div>
  );
}
