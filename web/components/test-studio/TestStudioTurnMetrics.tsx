"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";
import {
  cacheEventLabel,
  costTelnyxBreakdown,
  costGeminiPostCallTranscribeUsd,
  costLlmUsd,
  telnyxDestinationCountryFromE164,
  estimateTurnCost,
  formatInr,
  formatUsd,
  perMinute,
  PRICING,
  splitLlmTokens,
  type CacheEvent,
  type PricingMeta,
} from "@/lib/usage-cost";
import { isGeminiLiveVoiceModel } from "@/lib/realtime-voice";
import { CallTranscriptSourceBadge } from "@/components/calls/detail/CallTranscriptSourceBadge";
import type { CallMeta } from "@/lib/call-detail-types";

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
  inputImageTokens?: number;
  cachedAudioTokens?: number;
  inputAudioTokens?: number;
  outputAudioTokens?: number;
  memoryOps?: number;
  cacheHit?: boolean;
  cacheEvent?: CacheEvent;
  /** Server-billed delta for this trace turn (PSTN realtime). */
  costUsd?: number;
  costInr?: number;
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
  costBreakdownUsd?: Record<string, number>;
  fxRateInr?: number;
  fxSource?: string;
  fxAsOf?: string;
  llmModel?: string;
  cachedTokens?: number;
  durationSec?: number;
  modelCostUsd?: number;
  modelCostInr?: number;
  telnyxUsd?: number;
  telnyxInr?: number;
  telnyxDestinationCountry?: string;
  totalUsd?: number;
  totalInr?: number;
  /** Live ledger cumulative tokens (Gemini session snapshot). */
  inputTokens?: number;
  outputTokens?: number;
  inputImageTokens?: number;
  cachedAudioTokens?: number;
  inputAudioTokens?: number;
  outputAudioTokens?: number;
  postCallTranscriptUsd?: number;
  postCallTranscriptInr?: number;
  transcriptionBilling?: string;
  transcriptSource?: string;
  postCallTranscriptStatus?: string;
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
      <p className="font-mono text-[11px] uppercase text-text-subtle">{label}</p>
      <p className={cn("font-mono text-sm font-semibold", accent ? "text-status-success" : "text-text")}>
        {value}
      </p>
      {sub ? <p className="mt-0.5 font-mono text-[11px] text-text-muted">{sub}</p> : null}
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
  telnyxDestinationE164,
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
  /** PSTN callee E.164 — used for India vs US SIP estimate. */
  telnyxDestinationE164?: string;
  stampedUsage?: StampedSessionUsage | null;
  sessionEnded?: boolean;
}) {
  llmModel = stampedUsage?.llmModel || llmModel;
  pricing = stampedUsage?.fxRateInr ? {
    ...pricing, fx_rate_inr: stampedUsage.fxRateInr,
    fx_source: stampedUsage.fxSource, fx_as_of: stampedUsage.fxAsOf,
  } : pricing;
  const e2e = mode === "pstn_realtime";
  const pstn = mode === "pstn" || mode === "pstn_realtime";
  const ledgerTokens =
    stampedUsage?.inputTokens != null
      ? {
          inputTokens: stampedUsage.inputTokens ?? 0,
          outputTokens: stampedUsage.outputTokens ?? 0,
          inputAudioTokens: stampedUsage.inputAudioTokens ?? 0,
          outputAudioTokens: stampedUsage.outputAudioTokens ?? 0,
        }
      : null;
  const sessionCost = estimateTurnCost({
    sttAudioSec: e2e ? 0 : sessionTotal.sttAudioSec,
    ttsChars: e2e ? 0 : sessionTotal.ttsChars,
    ttsProvider,
    ttsModel,
    sttProvider,
    sttModel,
    llmModel,
    inputTokens: ledgerTokens?.inputTokens ?? sessionTotal.llmInput,
    outputTokens: ledgerTokens?.outputTokens ?? sessionTotal.llmOutput,
    cachedTokens: stampedUsage?.cachedTokens ?? sessionTotal.llmCached,
    cacheWriteTokens: sessionTotal.llmCacheWrite,
    inputAudioTokens: e2e ? ledgerTokens?.inputAudioTokens ?? sessionTotal.llmAudioInput : 0,
    outputAudioTokens: e2e ? ledgerTokens?.outputAudioTokens ?? sessionTotal.llmAudioOutput : 0,
    cachedAudioTokens: stampedUsage?.cachedAudioTokens ?? 0,
    inputImageTokens: stampedUsage?.inputImageTokens ?? 0,
    meta: pricing,
  });
  const connectedSec = sessionDurationMs / 1000;
  const wallSec =
    sessionEnded && stampedUsage?.durationSec != null && stampedUsage.durationSec > 0
      ? stampedUsage.durationSec
      : connectedSec > 0
        ? connectedSec
        : Math.max(stampedUsage?.durationSec ?? 0, e2e ? 0 : sessionTotal.sttAudioSec, 0);
  const telnyxDestCountry =
    stampedUsage?.telnyxDestinationCountry ??
    telnyxDestinationCountryFromE164(telnyxDestinationE164);
  const telnyxLiveEstimate = pstn
    ? costTelnyxBreakdown(wallSec, callDirection, pricing, {
        mediaStreaming: true,
        callRecording: true,
        destinationCountry: telnyxDestCountry,
      })
    : null;
  const estimatedTelnyxUsd = telnyxLiveEstimate?.totalUsd ?? 0;
  const modelUsd = stampedUsage?.modelCostUsd ?? sessionCost.totalUsd;
  const modelInr = stampedUsage?.modelCostInr ?? sessionCost.totalInr;
  const telnyxUsd = stampedUsage?.telnyxUsd ?? estimatedTelnyxUsd;
  const telnyxInr = stampedUsage?.telnyxInr ?? telnyxUsd * sessionCost.fx;
  const gemini = isGeminiLiveVoiceModel(llmModel);
  const transcriptUsdStamped = stampedUsage?.postCallTranscriptUsd ?? 0;
  const postCallTranscript =
    stampedUsage?.transcriptionBilling === "post_call_gemini_transcribe" ||
    transcriptUsdStamped > 0 ||
    (mode === "pstn_realtime" && gemini);
  const postCallEstimateUsd =
    postCallTranscript && transcriptUsdStamped <= 0 && wallSec > 0
      ? costGeminiPostCallTranscribeUsd(wallSec)
      : 0;
  const transcriptUsd = transcriptUsdStamped > 0 ? transcriptUsdStamped : postCallEstimateUsd;
  const transcriptInr =
    stampedUsage?.postCallTranscriptInr ?? (transcriptUsd > 0 ? transcriptUsd * sessionCost.fx : 0);
  const usageMetaForTx: CallMeta | null =
    stampedUsage?.transcriptSource || stampedUsage?.transcriptionBilling
      ? {
          transcript_source: stampedUsage.transcriptSource,
          usage: {
            transcription_billing: stampedUsage.transcriptionBilling,
            post_call_transcript_model: "gemini-3.5-transcribe",
          },
          post_call_transcript: stampedUsage.postCallTranscriptStatus
            ? { status: stampedUsage.postCallTranscriptStatus }
            : undefined,
        }
      : postCallTranscript
        ? { usage: { transcription_billing: "post_call_gemini_transcribe" } }
        : null;
  const transcriptForTotal =
    sessionEnded && stampedUsage?.totalUsd != null
      ? transcriptUsdStamped
      : sessionEnded
        ? transcriptUsdStamped
        : transcriptUsd;
  const totalUsd = stampedUsage?.totalUsd ?? modelUsd + telnyxUsd + transcriptForTotal;
  const totalInr = stampedUsage?.totalInr ?? modelInr + telnyxInr + transcriptForTotal * sessionCost.fx;
  const perMinWall = perMinute(totalUsd, wallSec, sessionCost.fx);
  const perMinStt = perMinute(sessionCost.totalUsd, sessionTotal.sttAudioSec, sessionCost.fx);
  const audioIn = ledgerTokens?.inputAudioTokens ?? sessionTotal.llmAudioInput;
  const audioOut = ledgerTokens?.outputAudioTokens ?? sessionTotal.llmAudioOutput;
  const modelParts = costLlmUsd({
    inputTokens: ledgerTokens?.inputTokens ?? sessionTotal.llmInput,
    outputTokens: ledgerTokens?.outputTokens ?? sessionTotal.llmOutput,
    inputAudioTokens: audioIn, outputAudioTokens: audioOut,
    inputImageTokens: stampedUsage?.inputImageTokens ?? 0,
    cachedTokens: stampedUsage?.cachedTokens ?? sessionTotal.llmCached,
    cachedAudioTokens: stampedUsage?.cachedAudioTokens ?? 0,
    llmModel, meta: pricing,
  });
  const billedParts = stampedUsage?.costBreakdownUsd;
  const breakdownAudioIn = billedParts?.audio_input_usd ?? modelParts.audioInputUsd;
  const breakdownAudioOut = billedParts?.audio_output_usd ?? modelParts.audioOutputUsd;
  const breakdownContext = billedParts ? (billedParts.uncached_usd || 0) + (billedParts.cached_usd || 0) + (billedParts.cache_write_usd || 0) : modelParts.uncachedUsd + modelParts.cachedUsd + modelParts.cacheWriteUsd;
  const breakdownTextOut = billedParts?.output_usd ?? modelParts.outputUsd;
  const breakdownImage = billedParts?.image_input_usd ?? modelParts.imageInputUsd;
  const cachePct =
    sessionTotal.llmInput > 0 ? Math.round((sessionTotal.llmCached / sessionTotal.llmInput) * 100) : 0;

  return (
    <div data-testid="test-studio-usage-panel">
      <SkeuoPanel
        title="Usage per turn"
        description={
          mode === "pstn_realtime"
            ? "Session clock · Live speech model audio tokens (OpenAI or Gemini) · Telnyx · total ₹"
            : mode === "agent"
            ? "STT chars (user transcript) · TTS chars (LLM reply → speech) · LLM tokens (cache hit vs write)"
            : "Session clock · Sarvam STT/TTS · OpenAI tokens · Telnyx call minutes · total ₹"
        }
        padding="md"
      >
        {e2e ? (
          <div className="mb-5 flex flex-col gap-4">
            {usageMetaForTx ? <CallTranscriptSourceBadge meta={usageMetaForTx} /> : null}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <StatCell label="Estimated total" value={formatInr(totalInr)} sub={formatUsd(totalUsd)} accent />
              <StatCell
                label="Session duration"
                value={formatClock(wallSec * 1000)}
                sub={
                  wallSec > 0
                    ? `${(wallSec / 60).toFixed(2)} min · ${sessionEnded ? "ledger (answered→hangup)" : "live after answer"}`
                    : "Timer starts when the callee answers"
                }
                accent
              />
              <StatCell label="Average per connected minute" value={wallSec > 0 ? formatInr(perMinWall.inr) : "?"}
                sub={wallSec > 0 ? `${formatUsd(perMinWall.usd)}/min all-in` : "—"} accent />
            </div>
            <div className="rounded-skeuo-sm border border-surface-border-subtle p-3">
              <p className="mb-3 text-xs font-semibold text-text">Cost breakdown{!billedParts && " (current-model estimate)"}</p>
              <dl className="flex flex-col gap-2 text-xs text-text-muted">
                {[
                  ["Audio received", breakdownAudioIn],
                  ["Audio spoken", breakdownAudioOut],
                  ["Prompt and conversation context", breakdownContext],
                  [
                    postCallTranscript ? "Text output (voice session)" : "Text output / native transcripts",
                    breakdownTextOut,
                  ],
                  ...(breakdownImage > 0 ? [["Image input", breakdownImage]] : []),
                  ...(postCallTranscript && transcriptUsd > 0
                    ? [
                        [
                          transcriptUsdStamped > 0
                            ? "Post-call transcript (Gemini 3.5)"
                            : "Post-call transcript (Gemini 3.5, est.)",
                          transcriptUsd,
                        ],
                      ]
                    : []),
                ].map(([label, usd]) => (
                  <div key={String(label)} className="flex justify-between gap-3">
                    <dt>{label}</dt><dd className="shrink-0 font-mono text-text">{formatInr(Number(usd) * sessionCost.fx)}</dd>
                  </div>
                ))}
                <div className="flex justify-between gap-3 border-t border-surface-border-subtle pt-2 font-semibold text-text">
                  <dt>AI model total</dt><dd className="font-mono">{formatInr(modelInr)}</dd>
                </div>
                <div className="flex justify-between gap-3"><dt>Telnyx phone charges</dt><dd className="font-mono text-text">{formatInr(telnyxInr)}</dd></div>
              </dl>
              <p className="mt-3 text-xs leading-relaxed text-text-muted">
                {gemini && (postCallTranscript || mode === "pstn_realtime")
                  ? "Live call is voice-only (Gemini 3.8 Live). After hangup, Telnyx recording is transcribed with Gemini 3.5 Transcribe; that post-call line is shown above and is not part of live audio token rows."
                  : gemini
                    ? "Transcription uses Gemini Live. Its text output charge is included above; no separate OpenAI transcription call is made."
                    : "Transcription uses gpt-4o-mini-transcribe (about $0.003 per audio minute). This separate provider charge is not included unless metered."}
                {e2e && !stampedUsage?.totalUsd && sessionEnded
                  ? " Session totals finalize from the call ledger after hangup; per-turn rows are usage deltas."
                  : null}
              </p>
            </div>
            <details className="text-xs text-text-muted">
              <summary className="cursor-pointer py-2 font-medium text-text focus-visible:outline focus-visible:outline-2">Rates and billing details</summary>
              <div className="mt-2 flex flex-col gap-2 leading-relaxed">
                <p>{llmModel} ? {audioIn.toLocaleString()} audio input tokens ? {audioOut.toLocaleString()} audio output tokens.</p>
                <p>Costs use provider token counts. Prompt/history text and native transcripts have separate text rates; they are not charged again as audio. History may be billed again each turn. Average ?/min is total cost divided by connected minutes, not a fixed tariff.</p>
                {telnyxLiveEstimate && <p>Telnyx estimate: API {formatInr(telnyxLiveEstimate.voiceApiUsd * sessionCost.fx)}, SIP {formatInr(telnyxLiveEstimate.sipUsd * sessionCost.fx)}, streaming {formatInr(telnyxLiveEstimate.mediaStreamUsd * sessionCost.fx)}, recording {formatInr(telnyxLiveEstimate.callRecordingUsd * sessionCost.fx)}. Destination {telnyxDestCountry || "unknown"}; SIP uses a configured estimate, subject to your account rate deck.</p>}
                <p>USD ? INR: ?{sessionCost.fx.toFixed(2)} per dollar ? {pricing?.fx_source || "fallback estimate"}{pricing?.fx_as_of ? ` ? ${pricing.fx_as_of}` : " ? no live quote date available"}. Taxes, currency conversion fees and number rental excluded.</p>
                <p className="flex flex-wrap gap-3">
                  <a className="underline" href="https://ai.google.dev/gemini-api/docs/pricing" target="_blank" rel="noreferrer">Gemini rates</a>
                  <a className="underline" href="https://developers.openai.com/api/docs/pricing" target="_blank" rel="noreferrer">OpenAI rates</a>
                  <a className="underline" href="https://telnyx.com/pricing/voice-api" target="_blank" rel="noreferrer">Telnyx rates</a>
                </p>
              </div>
            </details>
          </div>
        ) : (
        <div className="mb-4 space-y-3">
          <p className="font-mono text-xs uppercase tracking-wider text-text-subtle">Session totals</p>
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
                sub={
                  telnyxLiveEstimate
                    ? `${(wallSec / 60).toFixed(2)} min · API+SIP${telnyxDestCountry ? ` ${telnyxDestCountry}` : ""}+media${
                        telnyxLiveEstimate.callRecordingUsd > 0 ? "+rec" : ""
                      }`
                    : `${(wallSec / 60).toFixed(2)} min · ${callDirection}`
                }
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
            <p className="font-mono text-[11px] text-text-subtle">
              Blended ₹/min on STT audio only: {formatInr(perMinStt.inr)} ({formatUsd(perMinStt.usd)})
            </p>
          ) : null}
          <p className="font-mono text-[11px] text-text-subtle">
            FX ₹{sessionCost.fx.toFixed(2)}/$
            {pricing?.fx_source
              ? ` (${pricing.fx_source}${pricing.fx_as_of ? ` · ${pricing.fx_as_of}` : ""})`
              : ""}{" "}
            ·{" "}
            {e2e
              ? `Speech-to-speech E2E · ${llmModel}`
              : `STT ${sttProvider}/${sttModel || "default"} · TTS ${ttsProvider}/${ttsModel || "default"} · LLM ${llmModel}`}
            {pstn
              ? " · Telnyx = Voice API + SIP (dest) + WebSocket media (+ recording est.) on connected seconds"
              : ""}
          </p>
          {e2e && isGeminiLiveVoiceModel(llmModel) ? (
            <p className="font-mono text-[11px] text-text-subtle">
              Gemini model cost uses billed tokens (session-cumulative; context can re-bill). Text{" "}
              {Math.max(0, sessionTotal.llmInput - sessionTotal.llmAudioInput)} tok · audio{" "}
              {sessionTotal.llmAudioInput} in / {sessionTotal.llmAudioOutput} out — not call duration ×
              list audio ₹/min (ref continuous speech ≈ ₹
              {(
                (PRICING.geminiLiveAudioInputUsdPerMin + PRICING.geminiLiveAudioOutputUsdPerMin) *
                sessionCost.fx
              ).toFixed(2)}
              /min if speaking both ways the whole time).
            </p>
          ) : null}
        </div>
        )}

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
            <div className="grid grid-cols-3 gap-1 px-1 font-mono text-[11px] uppercase tracking-wide text-text-subtle">
              <span>{e2e ? "Audio in" : "STT chars"}</span>
              <span>{e2e ? "Audio out" : "LLM in"}</span>
              <span>{e2e ? "AI cost only" : "TTS chars"}</span>
            </div>
            {rows.map((r) => {
              const estimated = estimateTurnCost({
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
                inputImageTokens: r.inputImageTokens ?? 0,
                cachedAudioTokens: r.cachedAudioTokens ?? 0,
                meta: pricing,
              });
              const cost =
                e2e && r.costUsd != null
                  ? {
                      ...estimated,
                      totalUsd: r.costUsd,
                      totalInr: r.costInr ?? r.costUsd * estimated.fx,
                      llmUsd: r.costUsd,
                      llmInr: r.costInr ?? r.costUsd * estimated.fx,
                    }
                  : estimated;
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
                    <span className="font-mono text-xs uppercase text-text-subtle">
                      {e2e ? "Usage update" : "Turn"} {r.turn}
                      {r.sttAudioSec != null && (
                        <span className="ml-2 text-text-muted">· STT {r.sttAudioSec.toFixed(1)}s</span>
                      )}
                    </span>
                    <span className="font-mono text-[11px] font-semibold text-text">
                      {formatInr(cost.totalInr)}{" "}
                      <span className="font-normal text-text-muted">{formatUsd(cost.totalUsd)}</span>
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-1 font-mono text-[11px] text-text-muted">
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
                      <span className="text-text-subtle">AI cost only</span>
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
                  {e2e && <p className="mt-2 text-xs leading-relaxed text-text-muted">
                    Text: {Math.max(0, (r.inputTokens ?? 0) - (r.inputAudioTokens ?? 0) - (r.inputImageTokens ?? 0))} input / {Math.max(0, (r.outputTokens ?? 0) - (r.outputAudioTokens ?? 0))} output tokens. Phone charges are included in the session total above.
                  </p>}
                  {!e2e && turnSec > 0 ? (
                    <p className="mt-1 font-mono text-[11px] text-text-subtle">
                      This turn ₹/min {formatInr(turnPerMin.inr)} ({formatUsd(turnPerMin.usd)})
                    </p>
                  ) : null}
                  <p className="mt-1.5 truncate text-text-muted">You: {r.userText.slice(0, 50)}</p>
                  <div className="mt-1 flex flex-wrap gap-2">
                    <span className={cn("rounded px-1.5 py-0.5 font-mono text-[11px]", cacheTone(event))}>
                      {cacheEventLabel(event, { llmModel })}
                    </span>
                    {(r.memoryOps ?? 0) > 0 && (
                      <span className="rounded bg-accent-primary/10 px-1.5 py-0.5 font-mono text-[11px] text-accent-primary">
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
