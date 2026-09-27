import {
  DEFAULT_REALTIME_NOISE_REDUCTION,
  DEFAULT_REALTIME_SILENCE_MS,
  DEFAULT_REALTIME_SPEED,
  DEFAULT_REALTIME_TURN_DETECTION,
  DEFAULT_REALTIME_VAD_EAGERNESS,
  DEFAULT_REALTIME_VOICE,
  isGeminiLiveVoiceModel,
  normalizeRealtimeNoiseReduction,
  normalizeRealtimeSilenceMs,
  normalizeRealtimeSpeed,
  normalizeRealtimeTurnDetection,
  normalizeRealtimeVadEagerness,
  normalizeRealtimeVoice,
} from "@/lib/realtime-voice";
import {
  buildPstnRealtimeStackOverride,
  defaultStackForm,
  type StackForm,
} from "@/lib/test-studio-stack";

/** PSTN Gemini Live maps OpenAI Realtime voice slugs → Gemini prebuilt names (server parity). */
export const OPENAI_TO_GEMINI_VOICE_MAP: Record<string, string> = {
  ash: "Aoede",
  marin: "Puck",
  cedar: "Charon",
  alloy: "Kore",
  echo: "Fenrir",
  shimmer: "Leda",
  sage: "Orus",
  ballad: "Zephyr",
  coral: "Aoede",
  verse: "Puck",
};

export function geminiMappedVoice(openAiSlug: string | undefined): string {
  const slug = normalizeRealtimeVoice(openAiSlug);
  return OPENAI_TO_GEMINI_VOICE_MAP[slug] || "Puck";
}

export const SAAS_PHONE_LANGUAGES: { id: string; label: string }[] = [
  { id: "te-IN", label: "Telugu (India)" },
  { id: "en-IN", label: "English (India)" },
  { id: "hi-IN", label: "Hindi (India)" },
  { id: "en-US", label: "English (US)" },
];

export function saasPhoneStackFromOverride(override: Record<string, unknown> | null | undefined): StackForm {
  const base = defaultStackForm();
  if (!override || typeof override !== "object") return base;

  const llm =
    override.llm && typeof override.llm === "object" && !Array.isArray(override.llm)
      ? (override.llm as Record<string, unknown>)
      : {};
  const rv =
    override.realtime_voice &&
    typeof override.realtime_voice === "object" &&
    !Array.isArray(override.realtime_voice)
      ? (override.realtime_voice as Record<string, unknown>)
      : {};

  const model = String(llm.model || base.llmModel).trim();
  const providerRaw = String(llm.provider || "").trim().toLowerCase();
  const llmProvider =
    providerRaw === "gemini" || isGeminiLiveVoiceModel(model)
      ? "gemini"
      : providerRaw === "openai" || model.startsWith("gpt-realtime")
        ? "openai"
        : base.llmProvider;

  return {
    ...base,
    language: String(override.language || base.language).trim() || base.language,
    llmProvider,
    llmModel: model || base.llmModel,
    realtimeVoice: normalizeRealtimeVoice(String(rv.voice || base.realtimeVoice)),
    realtimeTurnDetection: normalizeRealtimeTurnDetection(
      String(rv.turn_detection || base.realtimeTurnDetection)
    ),
    realtimeVadEagerness: normalizeRealtimeVadEagerness(String(rv.vad_eagerness || base.realtimeVadEagerness)),
    realtimeNoiseReduction: normalizeRealtimeNoiseReduction(
      String(rv.noise_reduction || base.realtimeNoiseReduction)
    ),
    realtimeSpeed: normalizeRealtimeSpeed(rv.speed as number | string | undefined),
    realtimeSilenceMs: normalizeRealtimeSilenceMs(rv.silence_ms as number | string | undefined),
  };
}

export function saasPhoneStackToOverride(form: StackForm): Record<string, unknown> {
  const aligned: StackForm = {
    ...form,
    llmProvider: isGeminiLiveVoiceModel(form.llmModel) ? "gemini" : "openai",
    llmModel: form.llmModel,
  };
  return buildPstnRealtimeStackOverride(aligned);
}
