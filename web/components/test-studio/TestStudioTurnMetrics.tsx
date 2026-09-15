"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";
import {
  cacheEventLabel,
  costTelnyxUsd,
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
  inputAudioTokens?: number;
  outputAudioTokens?: number;
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
  llmAudioInput: number;
  llmAudioOutput: number;
  turns: number;
};

export type StampedSessionUsage = {
  durationSec?: number;
  modelCostUsd?: number;
  modelCostInr?: number;
  telnyxUsd?: number;
  telnyxInr?: number;
  totalUsd?: number;
  totalInr?: number;
};

function formatClock(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

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
    llmAudioInput: 0,
    llmAudioOutput: 0,
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
  callDirection = "outbound",
  stampedUsage,
  sessionEnded = false,
}: {
  rows: TurnMetricRow[];
  sessionTotal: SessionUsageTotals;
  mode?: "agent" | "pstn" | "pstn_realtime";
  ttsProvider?: string;
  ttsModel?: string;
  sttProvider?: string;
  sttModel?: string;
  llmModel?: string;
  pricing?: PricingMeta | null;
  sessionDurationMs?: number;
  callDirection?: "inbound" | "outbound";
  stampedUsage?: StampedSessionUsage | null;
  sessionEnded?: boolean;
}) {
  const e2e = mode === "pstn_realtime";
  const pstn = mode === "pstn" || mode === "pstn_realtime";
  const sessionCost = estimateTurnCost({
    sttAudioSec: e2e ? 0 : sessionTotal.sttAudioSec,
    ttsChars: e2e ? 0 : sessionTotal.ttsChars,
    ttsProvider,
    ttsModel,
    sttProvider,
    sttModel,
    llmModel,
    inputTokens: sessionTotal.llmInput,
    outputTokens: sessionTotal.llmOutput,
    cachedTokens: sessionTotal.llmCached,
    cacheWriteTokens: sessionTotal.llmCacheWrite,
    inputAudioTokens: e2e ? sessionTotal.llmAudioInput : 0,
    outputAudioTokens: e2e ? sessionTotal.llmAudioOutput : 0,
    meta: pricing,
  });
  const wallSec = Math.max(
    stampedUsage?.durationSec ?? 0,
    sessionDurationMs / 1000,
    sessionTotal.sttAudioSec,
    0
  );
  const estimatedTelnyxUsd = pstn ? costTelnyxUsd(wallSec, callDirection, pricing) : 0;
  const modelUsd = stampedUsage?.modelCostUsd ?? sessionCost.totalUsd;
  const modelInr = stampedUsage?.modelCostInr ?? sessionCost.totalInr;
  const telnyxUsd = stampedUsage?.telnyxUsd ?? estimatedTelnyxUsd;
  const telnyxInr = stampedUsage?.telnyxInr ?? telnyxUsd * sessionCost.fx;
  const totalUsd = stampedUsage?.totalUsd ?? modelUsd + telnyxUsd;
  const totalInr = stampedUsage?.totalInr ?? modelInr + telnyxInr;
  const perMinWall = perMinute(totalUsd, wallSec, sessionCost.fx);
  const perMinStt = perMinute(sessionCost.totalUsd, sessionTotal.sttAudioSec, sessionCost.fx);
  const cachePct =
    sessionTotal.llmInput > 0 ? Math.round((sessionTotal.llmCached / sessionTotal.llmInput) * 100) : 0;

  return (
    <div data-testid="test-studio-usage-panel">
      <SkeuoPanel
        title="Usage per turn"
        description={
          mode === "pstn_realtime"
            ? "Session clock · OpenAI audio in/out tokens · Telnyx call minutes · total ₹"
            : mode === "agent"
            ? "STT chars (user transcript) · TTS chars (LLM reply → speech) · LLM tokens (cache hit vs write)"
            : "Session clock · Sarvam STT/TTS · OpenAI tokens · Telnyx call minutes · total ₹"
        }
        padding="md"
      >
        <div className="mb-4 space-y-3">
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Session totals</p>
          <div className="grid grid-cols-2 gap-2">
            <StatCell
              label="Call session"
              value={formatClock(wallSec * 1000)}
              sub={
                wallSec > 0
                  ? sessionEnded
                    ? `${wallSec.toFixed(0)}s ended`
                    : `${wallSec.toFixed(0)}s connected`
                  : "starts when the call connects"
              }
              accent
            />
            <StatCell
              label="Total cost"
              value={formatInr(totalInr)}
              sub={formatUsd(totalUsd)}
              accent
            />
          </div>
          {pstn ? (
            <div className="grid grid-cols-3 gap-2">
              <StatCell
                label="Model"
                value={formatInr(modelInr)}
                sub={
                  e2e
                    ? `${sessionTotal.llmAudioInput || sessionTotal.llmInput} in / ${sessionTotal.llmAudioOutput || sessionTotal.llmOutput} out`
                    : formatUsd(modelUsd)
                }
              />
              <StatCell
                label="Telnyx"
                value={formatInr(telnyxInr)}
                sub={`${(wallSec / 60).toFixed(2)} min · ${callDirection}`}
              />
              <StatCell
                label="Per minute"
                value={formatInr(perMinWall.inr)}
                sub={formatUsd(perMinWall.usd)}
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <StatCell
                label="Per minute"
                value={formatInr(perMinWall.inr)}
                sub={`${formatUsd(perMinWall.usd)} · mic on→off`}
              />
              <StatCell label="Turns" value={String(sessionTotal.turns)} sub={`${cachePct}% cached`} />
            </div>
          )}
          <div className="grid grid-cols-3 gap-2">
            {e2e ? (
              <>
                <StatCell
                  label="Audio in"
                  value={String(sessionTotal.llmAudioInput || sessionTotal.llmInput)}
                  sub="Realtime audio input tokens"
                />
                <StatCell
                  label="Audio out"
                  value={String(sessionTotal.llmAudioOutput || sessionTotal.llmOutput)}
                  sub="Realtime audio output tokens"
                />
                <StatCell label="Turns" value={String(sessionTotal.turns)} />
              </>
            ) : (
              <>
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
              </>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2">
            <StatCell
              label="LLM"
              value={formatInr(sessionCost.llmInr)}
              sub={`${cachePct}% cached · ${formatUsd(sessionCost.llmUsd)}`}
            />
            {!e2e && <StatCell label="Turns" value={String(sessionTotal.turns)} />}
            <StatCell label="LLM out" value={String(sessionTotal.llmOutput)} sub={`in ${sessionTotal.llmInput} · ${sessionTotal.llmCached} hit`} />
            {e2e && (
              <StatCell
                label="No STT/TTS"
                value="₹0"
                sub="OpenAI audio E2E"
              />
            )}
          </div>
          {!e2e && (
          <div className="grid grid-cols-3 gap-2">
            <StatCell label="LLM in" value={String(sessionTotal.llmInput)} sub={`${sessionTotal.llmCached} cached · ${sessionTotal.llmCacheWrite} write`} />
            <StatCell
              label="TTS"
              value={formatInr(sessionCost.ttsInr)}
              sub={`${formatUsd(sessionCost.ttsUsd)} · ₹3/1k chars`}
            />
            <StatCell label="TTS audio" value={formatBytes(sessionTotal.ttsAudioBytes)} />
          </div>
          )}
          {sessionTotal.sttAudioSec > 0 && Math.abs(perMinStt.inr - perMinWall.inr) > 0.01 ? (
            <p className="font-mono text-[9px] text-text-subtle">
              Blended ₹/min on STT audio only: {formatInr(perMinStt.inr)} ({formatUsd(perMinStt.usd)})
            </p>
          ) : null}
          <p className="font-mono text-[9px] text-text-subtle">
            FX ₹{sessionCost.fx.toFixed(2)}/$ · {e2e ? "OpenAI Realtime audio E2E" : `STT ${sttProvider}/${sttModel || "default"} · TTS ${ttsProvider}/${ttsModel || "default"}`} · LLM {llmModel}
            {pstn ? " · Telnyx per connected minute" : ""}
          </p>
        </div>

        {rows.length === 0 ? (
          <p className="text-xs text-text-muted" data-testid="usage-empty-hint">
            {mode === "agent"
              ? "Turn the mic on, speak, and turn it off — each completed turn shows STT, LLM, and TTS cost here."
              : mode === "pstn_realtime"
                ? "Place a Telnyx call — session clock, audio-token cost, and Telnyx minutes show here."
                : "Place a Telnyx call — session clock, STT/TTS/LLM, and Telnyx minutes show here."}
          </p>
        ) : (
          <div className="max-h-72 overflow-y-auto space-y-2" data-testid="usage-turn-list">
            <div className="grid grid-cols-3 gap-1 px-1 font-mono text-[9px] uppercase tracking-wide text-text-subtle">
              <span>{e2e ? "Audio in" : "STT chars"}</span>
              <span>{e2e ? "Audio out" : "LLM in"}</span>
              <span>{e2e ? "Turn cost" : "TTS chars"}</span>
            </div>
            {rows.map((r) => {
              const cost = estimateTurnCost({
                sttAudioSec: e2e ? 0 : r.sttAudioSec ?? 0,
                ttsChars: e2e ? 0 : r.ttsChars ?? 0,
                ttsProvider,
                ttsModel,
                sttProvider,
                sttModel,
                llmModel,
                inputTokens: r.inputTokens ?? 0,
                outputTokens: r.outputTokens ?? 0,
                cachedTokens: r.cachedTokens ?? 0,
                cacheWriteTokens: r.cacheWriteTokens ?? 0,
                inputAudioTokens: r.inputAudioTokens ?? 0,
                outputAudioTokens: r.outputAudioTokens ?? 0,
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
                    {e2e ? (
                      <>
                    <div>
                      <span className="text-text-subtle">Audio in</span>
                      <br />
                      <span className="text-sm font-semibold text-text">{r.inputAudioTokens ?? 0}</span>
                    </div>
                    <div>
                      <span className="text-text-subtle">Audio out</span>
                      <br />
                      <span className="text-sm font-semibold text-text">{r.outputAudioTokens ?? 0}</span>
                    </div>
                    <div>
                      <span className="text-text-subtle">LLM</span>
                      <br />
                      {formatInr(cost.llmInr)}
                    </div>
                      </>
                    ) : (
                      <>
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
                      </>
                    )}
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
