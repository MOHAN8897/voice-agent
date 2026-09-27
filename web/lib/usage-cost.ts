import { isGeminiLiveVoiceModel } from "@/lib/realtime-voice";

/**
 * Voice-turn cost estimates from official provider docs (2026-09-23).
 *
 * Sarvam STT  — ₹30 / hour of audio (realtime + streaming). Telugu chars are not billed.
 * Sarvam TTS  — ₹3.00 / 1,000 Unicode characters (Telugu code points count).
 * OpenAI Luna — $0.20/M uncached input, $0.02/M cached input, $0.25/M cache write, $1.20/M output.
 * OpenAI 5.5  — $5.00/M in, $0.50/M cached, $6.25/M write, $30/M out.
 * Cartesia TTS — Pro plan ~$50 / 1M characters (1 credit/char).
 * Cartesia STT — ink-whisper 1 credit/sec; ink-2 3 credits/sec (Pro $5/100K credits).
 * Telnyx PSTN (wall-clock, component sum): Voice API $0.002/min + SIP (dest-specific, IN default
 *   $0.009/min) + media WebSocket $0.0035/min + optional recording $0.002/min.
 * Gemini 3.8 Live — billed on actual text/audio/image tokens; session usage_metadata is cumulative
 *   (context re-billed per turn). List $0.005/$0.018 audio-min is reference only, not × call duration.
 * Per-call total after hangup: model_cost_usd (tokens) + telnyx_usd (components).
 */

export const DEFAULT_FX_INR = 95.64;

export const PRICING = {
  updatedAt: "2026-09-23",
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
    telnyxVoiceApiUsdPerMin: 0.002,
    telnyxSipOutboundUsdPerMin: 0.005,
    telnyxSipOutboundIndiaUsdPerMin: 0.009,
    telnyxSipInboundUsdPerMin: 0.0032,
    telnyxMediaStreamUsdPerMin: 0.0035,
    telnyxCallRecordingUsdPerMin: 0.002,
    telnyxOutboundUsdPerMin: 0.002 + 0.005 + 0.0035,
    telnyxInboundUsdPerMin: 0.002 + 0.0032 + 0.0035,
    geminiLiveUsdPerM: {
        "gemini-3.8-live": { input: 0.75, cachedInput: 0, cacheWrite: 0, output: 4.5 },
        "gemini-2.5-flash-native-audio-latest": { input: 0.5, cachedInput: 0, cacheWrite: 0, output: 2.0 },
    },
    geminiLiveAudioUsdPerM: {
        "gemini-3.8-live": { input: 3.0, cachedInput: 0, output: 12.0 },
        "gemini-2.5-flash-native-audio-latest": { input: 3.0, cachedInput: 0, output: 12.0 },
    },
    geminiLiveImageUsdPerM: {
        "gemini-3.8-live": 1.0,
        "gemini-2.5-flash-native-audio-latest": 3.0,
    },
    geminiLiveAudioInputUsdPerMin: 0.005,
    geminiLiveAudioOutputUsdPerMin: 0.018,
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
  "telnyx:voice_api"?: { usd_per_unit?: number };
  "telnyx:sip_outbound"?: { usd_per_unit?: number };
  "telnyx:sip_outbound_india"?: { usd_per_unit?: number };
  "telnyx:sip_inbound"?: { usd_per_unit?: number };
  "telnyx:media_stream"?: { usd_per_unit?: number };
  "telnyx:call_recording"?: { usd_per_unit?: number };
  "telnyx:outbound"?: { usd_per_unit?: number };
  "telnyx:inbound"?: { usd_per_unit?: number };
  "gemini:gemini-3.8-live"?: LlmRateMeta;
  "gemini:gemini-2.5-flash-native-audio-latest"?: LlmRateMeta;
};

type LlmRateMeta = {
  usd_input_per_m?: number;
  usd_cached_input_per_m?: number;
  usd_cache_write_per_m?: number;
  usd_output_per_m?: number;
  usd_audio_input_per_m?: number;
  usd_audio_cached_input_per_m?: number;
  usd_audio_output_per_m?: number;
  usd_image_input_per_m?: number;
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

export function geminiAudioRatesForModel(model: string | undefined, meta?: PricingMeta | null) {
  const m = (model || "gemini-3.8-live").toLowerCase();
  const key = `gemini:${m}` as keyof PricingMeta;
  const fromMeta = meta?.[key] as LlmRateMeta | undefined;
  const fallback =
    PRICING.geminiLiveAudioUsdPerM[m as keyof typeof PRICING.geminiLiveAudioUsdPerM] ||
    PRICING.geminiLiveAudioUsdPerM["gemini-3.8-live"];
  return {
    input: Number(fromMeta?.usd_audio_input_per_m) || fallback.input,
    cachedInput: Number(fromMeta?.usd_audio_cached_input_per_m) || fallback.cachedInput,
    output: Number(fromMeta?.usd_audio_output_per_m) || fallback.output,
  };
}

export function geminiRatesForModel(model: string | undefined, meta?: PricingMeta | null) {
  const m = (model || "gemini-3.8-live").toLowerCase();
  const key = `gemini:${m}` as keyof PricingMeta;
  const fromMeta = meta?.[key] as LlmRateMeta | undefined;
  const fallback =
    PRICING.geminiLiveUsdPerM[m as keyof typeof PRICING.geminiLiveUsdPerM] ||
    PRICING.geminiLiveUsdPerM["gemini-3.8-live"];
  return {
    input: Number(fromMeta?.usd_input_per_m) || fallback.input,
    cachedInput: Number(fromMeta?.usd_cached_input_per_m) || fallback.cachedInput,
    cacheWrite: Number(fromMeta?.usd_cache_write_per_m) || fallback.cacheWrite,
    output: Number(fromMeta?.usd_output_per_m) || fallback.output,
  };
}

export function geminiImageRateForModel(model: string | undefined, meta?: PricingMeta | null) {
  const m = (model || "gemini-3.8-live").toLowerCase();
  const key = `gemini:${m}` as keyof PricingMeta;
  const fromMeta = meta?.[key] as LlmRateMeta | undefined;
  const fallback =
    PRICING.geminiLiveImageUsdPerM[m as keyof typeof PRICING.geminiLiveImageUsdPerM] ||
    PRICING.geminiLiveImageUsdPerM["gemini-3.8-live"];
  return Number(fromMeta?.usd_image_input_per_m) || fallback;
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
  inputImageTokens?: number;
}) {
  const audioInTok = Math.max(0, opts.inputAudioTokens || 0);
  const audioOutTok = Math.max(0, opts.outputAudioTokens || 0);
  const imageInTok = Math.max(0, opts.inputImageTokens || 0);
  const textIn = Math.max(0, (opts.inputTokens || 0) - audioInTok - imageInTok);
  const textOut = Math.max(0, (opts.outputTokens || 0) - audioOutTok);
  let audioCached = Math.min(audioInTok, Math.max(0, opts.cachedAudioTokens || 0));
  if (audioCached === 0 && (opts.cachedTokens || 0) > 0) {
    audioCached = Math.min(audioInTok, Math.max(0, (opts.cachedTokens || 0) - textIn));
  }
  const textCached = Math.max(0, (opts.cachedTokens || 0) - audioCached);
  const parts = splitLlmTokens(textIn, textCached, opts.cacheWriteTokens || 0);
  const gemini = isGeminiLiveVoiceModel(opts.llmModel);
  const rates = gemini ? geminiRatesForModel(opts.llmModel, opts.meta) : openaiRatesForModel(opts.llmModel, opts.meta);
  const audioRates = gemini
    ? geminiAudioRatesForModel(opts.llmModel, opts.meta)
    : openaiAudioRatesForModel(opts.llmModel, opts.meta);
  const uncachedUsd = (parts.uncached * rates.input) / 1_000_000;
  const cachedUsd = (parts.cached * rates.cachedInput) / 1_000_000;
  const writeUsd = (parts.written * rates.cacheWrite) / 1_000_000;
  const outputUsd = (textOut * rates.output) / 1_000_000;
  const audioInUsd =
    ((audioInTok - audioCached) * audioRates.input + audioCached * audioRates.cachedInput) / 1_000_000;
  const audioOutUsd = (audioOutTok * audioRates.output) / 1_000_000;
  const imageInUsd = gemini ? (imageInTok * geminiImageRateForModel(opts.llmModel, opts.meta)) / 1_000_000 : 0;
  return {
    uncachedUsd,
    cachedUsd,
    cacheWriteUsd: writeUsd,
    outputUsd,
    audioInputUsd: audioInUsd,
    audioOutputUsd: audioOutUsd,
    imageInputUsd: imageInUsd,
    totalUsd: uncachedUsd + cachedUsd + writeUsd + outputUsd + audioInUsd + audioOutUsd + imageInUsd,
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

export function telnyxDestinationCountryFromE164(e164: string | null | undefined): string | null {
  const digits = String(e164 || "").replace(/\D/g, "");
  if (!digits) return null;
  if (digits.startsWith("91") && digits.length >= 12) return "IN";
  if (digits.startsWith("1") && digits.length >= 11) return "US";
  return null;
}

export type TelnyxCostOptions = {
  mediaStreaming?: boolean;
  callRecording?: boolean;
  destinationCountry?: string | null;
};

function telnyxRate(meta: PricingMeta | null | undefined, key: keyof PricingMeta, fallback: number): number {
  const fromMeta = meta?.[key]?.usd_per_unit;
  return typeof fromMeta === "number" ? fromMeta : fallback;
}

export function costTelnyxBreakdown(
  durationSec: number,
  direction: "inbound" | "outbound" = "outbound",
  meta?: PricingMeta | null,
  opts?: TelnyxCostOptions
): {
  totalUsd: number;
  voiceApiUsd: number;
  sipUsd: number;
  mediaStreamUsd: number;
  callRecordingUsd: number;
  sipUsdPerMin: number;
  destinationCountry: string | null;
} {
  const minutes = Math.max(0, durationSec) / 60;
  const dest = opts?.destinationCountry ?? null;
  const voiceRate = telnyxRate(meta, "telnyx:voice_api", PRICING.telnyxVoiceApiUsdPerMin);
  const sipRate =
    direction === "inbound"
      ? telnyxRate(meta, "telnyx:sip_inbound", PRICING.telnyxSipInboundUsdPerMin)
      : dest === "IN"
        ? telnyxRate(meta, "telnyx:sip_outbound_india", PRICING.telnyxSipOutboundIndiaUsdPerMin)
        : telnyxRate(meta, "telnyx:sip_outbound", PRICING.telnyxSipOutboundUsdPerMin);
  const mediaRate = opts?.mediaStreaming
    ? telnyxRate(meta, "telnyx:media_stream", PRICING.telnyxMediaStreamUsdPerMin)
    : 0;
  const recordingRate = opts?.callRecording
    ? telnyxRate(meta, "telnyx:call_recording", PRICING.telnyxCallRecordingUsdPerMin)
    : 0;
  if (minutes <= 0) {
    return {
      totalUsd: 0,
      voiceApiUsd: 0,
      sipUsd: 0,
      mediaStreamUsd: 0,
      callRecordingUsd: 0,
      sipUsdPerMin: sipRate,
      destinationCountry: dest,
    };
  }
  const voiceApiUsd = minutes * voiceRate;
  const sipUsd = minutes * sipRate;
  const mediaStreamUsd = minutes * mediaRate;
  const callRecordingUsd = minutes * recordingRate;
  return {
    totalUsd: voiceApiUsd + sipUsd + mediaStreamUsd + callRecordingUsd,
    voiceApiUsd,
    sipUsd,
    mediaStreamUsd,
    callRecordingUsd,
    sipUsdPerMin: sipRate,
    destinationCountry: dest,
  };
}

export function costTelnyxUsd(
  durationSec: number,
  direction: "inbound" | "outbound" = "outbound",
  meta?: PricingMeta | null,
  opts?: TelnyxCostOptions
): number {
  return costTelnyxBreakdown(durationSec, direction, meta, opts).totalUsd;
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
  inputImageTokens?: number;
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
    inputImageTokens: opts.inputImageTokens,
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

export function cacheEventLabel(
  event: CacheEvent,
  opts?: { llmModel?: string; geminiLiveNoCache?: boolean }
): string {
  if (
    opts?.geminiLiveNoCache ||
    (opts?.llmModel && /gemini-3\.8-live/i.test(opts.llmModel))
  ) {
    return "Gemini Live (no prompt cache)";
  }
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
