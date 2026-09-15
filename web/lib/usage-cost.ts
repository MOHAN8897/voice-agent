/**
 * Voice-turn cost estimates from official provider docs (2026-09-03).
 *
 * Sarvam STT  — ₹30 / hour of audio (realtime + streaming). Telugu chars are not billed.
 * Sarvam TTS  — ₹3.00 / 1,000 Unicode characters (Telugu code points count).
 * OpenAI Luna — $0.20/M uncached input, $0.02/M cached input, $0.25/M cache write, $1.20/M output.
 * OpenAI 5.5  — $5.00/M in, $0.50/M cached, $6.25/M write, $30/M out.
 * Cartesia TTS — Pro plan ~$50 / 1M characters (1 credit/char).
 * Cartesia STT — ink-whisper 1 credit/sec; ink-2 3 credits/sec (Pro $5/100K credits).
 */

export const DEFAULT_FX_INR = 95.64;

export const PRICING = {
  updatedAt: "2026-09-03",
  sarvamSttInrPerHour: 30,
  sarvamTtsInrPer1kChars: 3,
  cartesiaProUsdPerCredit: 5 / 100_000,
  cartesiaTtsUsdPerMChars: 50,
    openaiUsdPerM: {
        "gpt-realtime-2.1-mini": { input: 0.6, cachedInput: 0.06, cacheWrite: 0.6, output: 2.4 },
        "gpt-realtime-2.1": { input: 4.0, cachedInput: 0.4, cacheWrite: 4.0, output: 24.0 },
        "gpt-realtime-2": { input: 4.0, cachedInput: 0.4, cacheWrite: 4.0, output: 24.0 },
        "gpt-5.6-luna": { input: 0.2, cachedInput: 0.02, cacheWrite: 0.25, output: 1.2 },
        "gpt-5.5": { input: 5.0, cachedInput: 0.5, cacheWrite: 6.25, output: 30.0 },
        "gpt-5.4": { input: 2.5, cachedInput: 0.25, cacheWrite: 3.125, output: 15.0 },
        "gpt-5": { input: 5.0, cachedInput: 0.5, cacheWrite: 6.25, output: 30.0 },
    },
    openaiAudioUsdPerM: {
        "gpt-realtime-2.1-mini": { input: 10, cachedInput: 0.3, output: 20 },
        "gpt-realtime-2.1": { input: 32, cachedInput: 0.4, output: 64 },
        "gpt-realtime-2": { input: 32, cachedInput: 0.4, output: 64 },
    },
    telnyxOutboundUsdPerMin: 0.012,
    telnyxInboundUsdPerMin: 0.005,
} as const;

export type CacheEvent = "cache_hit" | "cache_write" | "partial_hit" | "cache_miss";

export type PricingMeta = {
  fx_rate_inr?: number;
  "sarvam:saaras:v3"?: { inr_per_hour?: number; usd_per_unit?: number };
  "sarvam:bulbul:v3"?: { inr_per_1k_chars?: number; usd_per_unit?: number };
  "openai:gpt-realtime-2.1-mini"?: LlmRateMeta;
  "openai:gpt-realtime-2.1"?: LlmRateMeta;
  "openai:gpt-realtime-2"?: LlmRateMeta;
  "openai:gpt-5.6-luna"?: LlmRateMeta;
  "openai:gpt-5.5"?: LlmRateMeta;
  "openai:gpt-5.4"?: LlmRateMeta;
  "cartesia:sonic-3.5"?: { usd_per_unit?: number };
  "cartesia:ink-whisper"?: { credits_per_sec?: number; usd_per_hour?: number };
  "cartesia:ink-2"?: { credits_per_sec?: number; usd_per_hour?: number };
  "telnyx:outbound"?: { usd_per_unit?: number };
  "telnyx:inbound"?: { usd_per_unit?: number };
};

type LlmRateMeta = {
  usd_input_per_m?: number;
  usd_cached_input_per_m?: number;
  usd_cache_write_per_m?: number;
  usd_output_per_m?: number;
  usd_audio_input_per_m?: number;
  usd_audio_cached_input_per_m?: number;
  usd_audio_output_per_m?: number;
};

export function resolveTtsProvider(provider: string, model = ""): "sarvam" | "cartesia" {
  const p = (provider || "sarvam").toLowerCase();
  const m = (model || "").toLowerCase();
  if (p === "cartesia" || m.startsWith("sonic")) return "cartesia";
  return "sarvam";
}

export function resolveSttProvider(provider: string, model = ""): "sarvam" | "cartesia" {
  const p = (provider || "sarvam").toLowerCase();
  const m = (model || "").toLowerCase();
  if (p === "cartesia" || m.startsWith("ink")) return "cartesia";
  return "sarvam";
}

export function openaiAudioRatesForModel(model: string | undefined, meta?: PricingMeta | null) {
  const m = (model || "gpt-realtime-2.1-mini").toLowerCase();
  const key = `openai:${m}` as keyof PricingMeta;
  const fromMeta = meta?.[key] as LlmRateMeta | undefined;
  const fallback =
    PRICING.openaiAudioUsdPerM[m as keyof typeof PRICING.openaiAudioUsdPerM] ||
    Object.entries(PRICING.openaiAudioUsdPerM).find(([k]) => m.startsWith(k))?.[1] ||
    PRICING.openaiAudioUsdPerM["gpt-realtime-2.1-mini"];
  return {
    input: Number(fromMeta?.usd_audio_input_per_m) || fallback.input,
    cachedInput: Number(fromMeta?.usd_audio_cached_input_per_m) || fallback.cachedInput,
    output: Number(fromMeta?.usd_audio_output_per_m) || fallback.output,
  };
}

export function openaiRatesForModel(model: string | undefined, meta?: PricingMeta | null) {
  const m = (model || "gpt-realtime-2.1-mini").toLowerCase();
  const key = `openai:${m}` as keyof PricingMeta;
  const fromMeta = meta?.[key] as LlmRateMeta | undefined;
  const fallback =
    PRICING.openaiUsdPerM[m as keyof typeof PRICING.openaiUsdPerM] ||
    Object.entries(PRICING.openaiUsdPerM).find(([k]) => m.startsWith(k))?.[1] ||
    PRICING.openaiUsdPerM["gpt-5.6-luna"];
  return {
    input: Number(fromMeta?.usd_input_per_m) || fallback.input,
    cachedInput: Number(fromMeta?.usd_cached_input_per_m) || fallback.cachedInput,
    cacheWrite: Number(fromMeta?.usd_cache_write_per_m) || fallback.cacheWrite,
    output: Number(fromMeta?.usd_output_per_m) || fallback.output,
  };
}

function cartesiaSttCreditsPerSec(model = "", realtime = true): number {
  const m = (model || "ink-whisper").toLowerCase();
  if (m.includes("ink-2")) return realtime ? 3 : 1.5;
  return realtime ? 1 : 0.5;
}

export function classifyCacheEvent(input: number, cached: number, written: number): CacheEvent {
  const c = Math.max(0, cached || 0);
  const w = Math.max(0, written || 0);
  if (c > 0 && w > 0) return "partial_hit";
  if (c > 0) return "cache_hit";
  if (w > 0) return "cache_write";
  return "cache_miss";
}

export function splitLlmTokens(input: number, cached: number, written: number) {
  const inp = Math.max(0, Math.floor(input || 0));
  const cachedBilled = Math.min(inp, Math.max(0, Math.floor(cached || 0)));
  const writtenBilled = Math.min(Math.max(0, Math.floor(written || 0)), Math.max(0, inp - cachedBilled));
  const uncached = Math.max(0, inp - cachedBilled - writtenBilled);
  return { input: inp, cached: cachedBilled, written: writtenBilled, uncached };
}

function fxOf(meta?: PricingMeta | null): number {
  const fx = Number(meta?.fx_rate_inr);
  return fx > 0 ? fx : DEFAULT_FX_INR;
}

export function costSttUsd(
  audioSec: number,
  meta?: PricingMeta | null,
  opts?: { sttProvider?: string; sttModel?: string }
): number {
  const sec = Math.max(0, audioSec || 0);
  if (resolveSttProvider(opts?.sttProvider || "sarvam", opts?.sttModel || "") === "cartesia") {
    const credits = cartesiaSttCreditsPerSec(opts?.sttModel || "ink-whisper") * sec;
    return credits * PRICING.cartesiaProUsdPerCredit;
  }
  const hours = sec / 3600;
  const inrHour = Number(meta?.["sarvam:saaras:v3"]?.inr_per_hour) || PRICING.sarvamSttInrPerHour;
  return (hours * inrHour) / fxOf(meta);
}

export function costTtsUsd(
  chars: number,
  provider: string,
  model: string,
  meta?: PricingMeta | null
): number {
  const n = Math.max(0, chars || 0);
  if (resolveTtsProvider(provider, model) === "cartesia") {
    const perM = Number(meta?.["cartesia:sonic-3.5"]?.usd_per_unit) || PRICING.cartesiaTtsUsdPerMChars;
    return (n * perM) / 1_000_000;
  }
  const inr1k = Number(meta?.["sarvam:bulbul:v3"]?.inr_per_1k_chars) || PRICING.sarvamTtsInrPer1kChars;
  return ((n / 1000) * inr1k) / fxOf(meta);
}

export function costLlmUsd(opts: {
  inputTokens: number;
  outputTokens: number;
  cachedTokens?: number;
  cacheWriteTokens?: number;
  llmModel?: string;
  meta?: PricingMeta | null;
  inputAudioTokens?: number;
  outputAudioTokens?: number;
  cachedAudioTokens?: number;
}) {
  const audioInTok = Math.max(0, opts.inputAudioTokens || 0);
  const audioOutTok = Math.max(0, opts.outputAudioTokens || 0);
  const textIn = Math.max(0, (opts.inputTokens || 0) - audioInTok);
  const textOut = Math.max(0, (opts.outputTokens || 0) - audioOutTok);
  let audioCached = Math.min(audioInTok, Math.max(0, opts.cachedAudioTokens || 0));
  if (audioCached === 0 && (opts.cachedTokens || 0) > 0) {
    audioCached = Math.min(audioInTok, Math.max(0, (opts.cachedTokens || 0) - textIn));
  }
  const textCached = Math.max(0, (opts.cachedTokens || 0) - audioCached);
  const parts = splitLlmTokens(textIn, textCached, opts.cacheWriteTokens || 0);
  const rates = openaiRatesForModel(opts.llmModel, opts.meta);
  const audioRates = openaiAudioRatesForModel(opts.llmModel, opts.meta);
  const uncachedUsd = (parts.uncached * rates.input) / 1_000_000;
  const cachedUsd = (parts.cached * rates.cachedInput) / 1_000_000;
  const writeUsd = (parts.written * rates.cacheWrite) / 1_000_000;
  const outputUsd = (textOut * rates.output) / 1_000_000;
  const audioInUsd =
    ((audioInTok - audioCached) * audioRates.input + audioCached * audioRates.cachedInput) / 1_000_000;
  const audioOutUsd = (audioOutTok * audioRates.output) / 1_000_000;
  return {
    uncachedUsd,
    cachedUsd,
    cacheWriteUsd: writeUsd,
    outputUsd,
    audioInputUsd: audioInUsd,
    audioOutputUsd: audioOutUsd,
    totalUsd: uncachedUsd + cachedUsd + writeUsd + outputUsd + audioInUsd + audioOutUsd,
    parts,
  };
}

export type TurnCost = {
  sttUsd: number;
  ttsUsd: number;
  llmUsd: number;
  totalUsd: number;
  sttInr: number;
  ttsInr: number;
  llmInr: number;
  totalInr: number;
  cacheEvent: CacheEvent;
  fx: number;
};

export function costTelnyxUsd(
  durationSec: number,
  direction: "inbound" | "outbound" = "outbound",
  meta?: PricingMeta | null
): number {
  const minutes = Math.max(0, durationSec) / 60;
  if (minutes <= 0) return 0;
  const key = direction === "inbound" ? "telnyx:inbound" : "telnyx:outbound";
  const fromMeta = meta?.[key]?.usd_per_unit;
  const fallback =
    direction === "inbound" ? PRICING.telnyxInboundUsdPerMin : PRICING.telnyxOutboundUsdPerMin;
  return minutes * (typeof fromMeta === "number" ? fromMeta : fallback);
}

export function estimateTurnCost(opts: {
  sttAudioSec: number;
  ttsChars: number;
  ttsProvider: string;
  ttsModel?: string;
  sttProvider?: string;
  sttModel?: string;
  llmModel?: string;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  cacheWriteTokens: number;
  inputAudioTokens?: number;
  outputAudioTokens?: number;
  cachedAudioTokens?: number;
  meta?: PricingMeta | null;
}): TurnCost {
  const fx = fxOf(opts.meta);
  const sttUsd = costSttUsd(opts.sttAudioSec, opts.meta, {
    sttProvider: opts.sttProvider,
    sttModel: opts.sttModel,
  });
  const ttsUsd = costTtsUsd(
    opts.ttsChars,
    opts.ttsProvider,
    opts.ttsModel || "",
    opts.meta
  );
  const llm = costLlmUsd({
    inputTokens: opts.inputTokens,
    outputTokens: opts.outputTokens,
    cachedTokens: opts.cachedTokens,
    cacheWriteTokens: opts.cacheWriteTokens,
    llmModel: opts.llmModel,
    meta: opts.meta,
    inputAudioTokens: opts.inputAudioTokens,
    outputAudioTokens: opts.outputAudioTokens,
    cachedAudioTokens: opts.cachedAudioTokens,
  });
  const totalUsd = sttUsd + ttsUsd + llm.totalUsd;
  return {
    sttUsd,
    ttsUsd,
    llmUsd: llm.totalUsd,
    totalUsd,
    sttInr: sttUsd * fx,
    ttsInr: ttsUsd * fx,
    llmInr: llm.totalUsd * fx,
    totalInr: totalUsd * fx,
    cacheEvent: classifyCacheEvent(opts.inputTokens, opts.cachedTokens, opts.cacheWriteTokens),
    fx,
  };
}

export function perMinute(totalUsd: number, durationSec: number, fx: number) {
  const minutes = Math.max(durationSec, 0) / 60;
  if (minutes <= 0) return { usd: 0, inr: 0 };
  return { usd: totalUsd / minutes, inr: (totalUsd * fx) / minutes };
}

export function formatUsd(n: number): string {
  if (!Number.isFinite(n)) return "$0";
  if (n === 0) return "$0";
  if (n < 0.0001) return `$${n.toExponential(1)}`;
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(3)}`;
}

export function formatInr(n: number): string {
  if (!Number.isFinite(n)) return "₹0";
  if (n === 0) return "₹0";
  if (n < 0.01) return `₹${n.toFixed(4)}`;
  if (n < 1) return `₹${n.toFixed(3)}`;
  return `₹${n.toFixed(2)}`;
}

export function cacheEventLabel(event: CacheEvent): string {
  switch (event) {
    case "cache_hit":
      return "cache hit";
    case "cache_write":
      return "cache write (miss)";
    case "partial_hit":
      return "partial hit + write";
    default:
      return "cache miss";
  }
}
