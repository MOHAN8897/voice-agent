import { apiOrigin } from "@/lib/api";
import type { TtsConfig } from "@/lib/voice/types";

let cached: { key: string; cfg: TtsConfig; at: number } | null = null;
const CACHE_MS = 120_000;

const SARVAM_DEFAULTS: TtsConfig = {
  provider: "sarvam",
  model: "bulbul:v3",
  speaker: "shubh",
  pace: 1.0,
  language_code: "te-IN",
  min_buffer_size: 30,
  max_chunk_length: 80,
  output_audio_codec: "linear16",
  output_audio_bitrate: "128k",
  sample_rate: 24000,
};

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isCartesiaModel(model: string): boolean {
  return model.startsWith("sonic");
}

export function isCartesiaVoiceId(value: string): boolean {
  return UUID_RE.test(value.trim());
}

/** Cartesia "Skylar" — same as server constants.CARTESIA_DEFAULT_VOICE_ID */
export const DEFAULT_CARTESIA_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4";
export const DEFAULT_SARVAM_SPEAKER = "shubh";

export function defaultTtsVoice(provider: string): string {
  return provider === "cartesia" ? DEFAULT_CARTESIA_VOICE_ID : DEFAULT_SARVAM_SPEAKER;
}

export function ttsProviderFromStack(provider: string, model = ""): "cartesia" | "sarvam" {
  if (provider === "cartesia" || isCartesiaModel(model)) return "cartesia";
  return "sarvam";
}

export function voiceMatchesTtsProvider(provider: string, voiceId: string): boolean {
  const id = (voiceId || "").trim();
  if (!id) return false;
  if (provider === "cartesia") return isCartesiaVoiceId(id);
  return !isCartesiaVoiceId(id);
}

/** If the voice is empty or belongs to the other TTS, return that provider's default. */
export function ensureTtsVoice(provider: string, voiceId: string, model = ""): string {
  const p = ttsProviderFromStack(provider, model);
  const id = (voiceId || "").trim();
  if (voiceMatchesTtsProvider(p, id)) return id;
  return defaultTtsVoice(p);
}

async function fetchStackTtsFallback(sessionId: string, languageCode: string): Promise<TtsConfig | null> {
  try {
    const [stackRes, runtimeRes] = await Promise.all([
      fetch(`${apiOrigin()}/api/settings/stack/preview?sessionId=${encodeURIComponent(sessionId)}`, {
        credentials: "include",
        cache: "no-store",
      }),
      fetch(`${apiOrigin()}/api/settings/runtime?sessionId=${encodeURIComponent(sessionId)}`, {
        credentials: "include",
        cache: "no-store",
      }),
    ]);
    if (!stackRes.ok) return null;
    const j = (await stackRes.json()) as {
      stack?: {
        tts?: {
          provider?: string;
          model?: string;
          config?: { speaker?: string };
        };
      };
    };
    const runtime =
      runtimeRes.ok
        ? ((await runtimeRes.json()) as { values?: { ttsSpeaker?: string; ttsModel?: string } })
        : null;
    const tts = j.stack?.tts;
    if (!tts) return null;
    const model = runtime?.values?.ttsModel || tts.model || "sonic-3.5";
    const speaker = runtime?.values?.ttsSpeaker || tts.config?.speaker || "";
    const isCartesia =
      tts.provider === "cartesia" || isCartesiaModel(model) || isCartesiaVoiceId(speaker);
    if (!isCartesia) return null;
    return {
      provider: "cartesia",
      model,
      speaker,
      pace: 1.0,
      language_code: languageCode,
      min_buffer_size: 30,
      max_chunk_length: 80,
      output_audio_codec: "linear16",
      output_audio_bitrate: "128k",
      sample_rate: 24000,
    };
  } catch {
    return null;
  }
}

export async function fetchTtsConfig(
  sessionId: string,
  languageCode: string,
  callId?: string | null
): Promise<TtsConfig> {
  const key = `${sessionId}:${languageCode}:${callId || ""}`;
  const now = Date.now();
  if (cached && cached.key === key && now - cached.at < CACHE_MS) {
    return cached.cfg;
  }
  try {
    const qs = new URLSearchParams({
      sessionId,
      language_code: languageCode,
    });
    if (callId) qs.set("callId", callId);
    const r = await fetch(`${apiOrigin()}/api/settings/tts-config?${qs}`, {
      credentials: "include",
      cache: "no-store",
    });
    if (r.ok) {
      const j = (await r.json()) as { ttsConfig?: TtsConfig };
      const cfg = { ...SARVAM_DEFAULTS, ...j.ttsConfig, language_code: languageCode };
      cached = { key, cfg, at: now };
      console.info("[tts-config] resolved", {
        provider: cfg.provider,
        model: cfg.model,
        speaker: cfg.speaker?.slice(0, 8),
      });
      return cfg;
    }
    const errBody = await r.text().catch(() => "");
    console.warn(`[tts-config] GET /tts-config failed ${r.status}`, errBody.slice(0, 200));
  } catch (e) {
    console.warn("[tts-config] fetch error", e);
  }

  const fallback = await fetchStackTtsFallback(sessionId, languageCode);
  if (fallback) {
    cached = { key, cfg: fallback, at: now };
    console.info("[tts-config] stack preview fallback", {
      model: fallback.model,
      speaker: fallback.speaker?.slice(0, 8),
    });
    return fallback;
  }

  console.warn("[tts-config] using Sarvam defaults — voice may be wrong for Cartesia sessions");
  return { ...SARVAM_DEFAULTS, language_code: languageCode };
}

export function invalidateTtsConfigCache() {
  cached = null;
}

export function buildWsTtsConfig(cfg: TtsConfig): Record<string, unknown> {
  const model = cfg.model || "bulbul:v3";
  const minBuf = Math.max(30, Math.min(200, cfg.min_buffer_size ?? 30));
  const maxChunk = Math.max(50, Math.min(500, cfg.max_chunk_length ?? 80));
  const out: Record<string, unknown> = {
    language_code: cfg.language_code,
    pace: cfg.pace ?? 1.0,
    min_buffer_size: minBuf,
    max_chunk_length: maxChunk,
    output_audio_codec: "linear16",
    output_audio_bitrate: cfg.output_audio_bitrate || "128k",
    sample_rate: cfg.sample_rate || 24000,
    model,
  };
  if (cfg.speaker) {
    out.speaker = cfg.speaker;
  }
  if (cfg.temperature != null && model === "bulbul:v3") {
    out.temperature = cfg.temperature;
  }
  return out;
}
