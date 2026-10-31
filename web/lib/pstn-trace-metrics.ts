/** Map PSTN call trace + transcript lines into Test Studio turn metric rows. */
import { billingCharCount } from "@/lib/billing-chars";
import { classifyCacheEvent, type CacheEvent } from "@/lib/usage-cost";
import type { TurnMetricRow } from "@/components/test-studio/TestStudioTurnMetrics";

type LedgerLine = {
  seq?: number;
  role?: string;
  text?: string;
  ts?: string;
  stt_latency_ms?: number;
  brain_latency_ms?: number;
  tts_first_byte_ms?: number;
};

type TraceTurn = {
  kind?: string;
  turn?: number;
  user_text?: string;
  assistant_text?: string;
  post_call_transcript_usd?: number;
  post_call_transcript_inr?: number;
  post_call_transcript_model?: string;
  transcript_lines?: number;
  input_tokens?: number;
  output_tokens?: number;
  cached_tokens?: number;
  cache_write_tokens?: number;
  input_image_tokens?: number;
  cached_audio_tokens?: number;
  input_audio_tokens?: number;
  output_audio_tokens?: number;
  stt_final_ms?: number;
  e2e_ms?: number;
  cost_usd?: number;
  cost_inr?: number;
  token_scope?: string;
};

function pairLines(lines: LedgerLine[]): { userText: string; assistantText: string; sttMs: number; at: number; turnMs: number }[] {
  const pairs: { userText: string; assistantText: string; sttMs: number; at: number; turnMs: number }[] = [];
  let pendingUser: LedgerLine | null = null;
  for (const line of lines) {
    if (line.role === "user") {
      pendingUser = line;
      continue;
    }
    if (line.role === "assistant") {
      const userTs = pendingUser?.ts ? Date.parse(pendingUser.ts) : NaN;
      const asstTs = line.ts ? Date.parse(line.ts) : NaN;
      const turnMs =
        Number.isFinite(userTs) && Number.isFinite(asstTs) && asstTs > userTs ? asstTs - userTs : 0;
      pairs.push({
        userText: pendingUser?.text || "",
        assistantText: line.text || "",
        sttMs: Number(pendingUser?.stt_latency_ms || 0),
        at: Number.isFinite(userTs) ? userTs : 0,
        turnMs,
      });
      pendingUser = null;
    }
  }
  return pairs;
}

export function mapPstnTraceToTurnRows(
  turns: TraceTurn[],
  lines: LedgerLine[],
  e2e: boolean
): TurnMetricRow[] {
  const pairs = pairLines(lines);
  let dialogIndex = 0;
  return turns.map((turn, index) => {
    if (turn.kind === "post_call_transcript") {
      const usd = Number(turn.post_call_transcript_usd || 0);
      const inr = Number(turn.post_call_transcript_inr || usd);
      const model = turn.post_call_transcript_model || "gemini-3.5-transcribe";
      const lineCount = Number(turn.transcript_lines || 0);
      return {
        turn: Number(turn.turn ?? index + 1),
        userText: "",
        assistantText: `Post-call transcript (${model}${lineCount > 0 ? `, ${lineCount} lines` : ""})`,
        at: index + 1,
        inputTokens: 0,
        outputTokens: 0,
        cachedTokens: 0,
        cacheWriteTokens: 0,
        sttChars: 0,
        sttAudioSec: 0,
        ttsChars: 0,
        ttsAudioBytes: 0,
        cacheHit: false,
        costUsd: usd > 0 ? usd : undefined,
        costInr: inr > 0 ? inr : undefined,
      };
    }
    const pair = pairs[dialogIndex];
    dialogIndex += 1;
    const userText = String(turn.user_text || pair?.userText || "");
    const assistantText = String(turn.assistant_text || pair?.assistantText || "");
    const input = Number(turn.input_tokens || 0);
    const cached = Number(turn.cached_tokens || 0);
    const cacheWrite = Number(turn.cache_write_tokens || 0);
    const sttMs = Number(turn.stt_final_ms || pair?.sttMs || 0);
    const cacheEvent: CacheEvent = classifyCacheEvent(input, cached, cacheWrite);
    const turnMs = Number(turn.e2e_ms || 0) || pair?.turnMs || 0;
    return {
      turn: Number(turn.turn ?? index + 1),
      userText,
      assistantText,
      at: pair?.at || index + 1,
      micDurationMs: turnMs > 0 ? turnMs : undefined,
      inputTokens: input,
      outputTokens: Number(turn.output_tokens || 0),
      cachedTokens: cached,
      cacheWriteTokens: cacheWrite,
      inputImageTokens: Number(turn.input_image_tokens || 0),
      cachedAudioTokens: Number(turn.cached_audio_tokens || 0),
      inputAudioTokens: Number(turn.input_audio_tokens || 0),
      outputAudioTokens: Number(turn.output_audio_tokens || 0),
      sttChars: e2e ? 0 : billingCharCount(userText),
      sttAudioSec: e2e ? 0 : sttMs > 0 ? sttMs / 1000 : 0,
      ttsChars: e2e ? 0 : billingCharCount(assistantText),
      ttsAudioBytes: 0,
      cacheEvent,
      cacheHit: cached > 0,
      costUsd: turn.cost_usd != null ? Number(turn.cost_usd) : undefined,
      costInr: turn.cost_inr != null ? Number(turn.cost_inr) : undefined,
    };
  });
}

export function callAudioUrl(
  callId: string,
  kind: "mix" | "user" | "agent" | "mix_clear" | "user_clear" | "agent_clear",
  download = false
) {
  const params = new URLSearchParams();
  if (download) params.set("download", "1");
  const q = params.toString();
  return `/api/call/${encodeURIComponent(callId)}/audio/${kind}${q ? `?${q}` : ""}`;
}
