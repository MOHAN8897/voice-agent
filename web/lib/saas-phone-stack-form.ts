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

const GEMINI_INDIC_VOICE_IDS = new Set([
  "hi-in-csagent-1", "hi-in-csagent-2", "ta-in-csagent-2", "ta-in-csagent-3",
  "te-in-csagent-1", "te-in-csagent-4", "te-in-csagent-5", "te-in-csagent-7",
  "te-in-concierge-2", "te-in-concierge-7", "te-in-techagent-1",
  "en-in-csagent-1", "en-in-csagent-3",
]);
const GEMINI_PREBUILT_VOICES = new Set([
  "zephyr", "kore", "orus", "autonoe", "umbriel", "erinome", "laomedeia", "schedar",
  "achird", "sadachbia", "puck", "fenrir", "aoede", "enceladus", "algieba", "algenib",
  "achernar", "gacrux", "zubenelgenubi", "sadaltager", "charon", "leda", "callirrhoe",
  "iapetus", "despina", "rasalgethi", "alnilam", "pulcherrima", "vindemiatrix", "sulafat",
]);

export function defaultGeminiLiveVoice(language: string | undefined): string {
  const locale = String(language || "").replaceAll("_", "-").toLowerCase();
  if (locale.startsWith("te")) return "te-in-csagent-5";
  if (locale.startsWith("hi")) return "hi-in-csagent-1";
  if (locale.startsWith("ta")) return "ta-in-csagent-3";
  if (locale === "en-in") return "en-in-csagent-3";
  return "Puck";
}

function normalizeGeminiVoice(value: string | undefined, language: string): string {
  const raw = String(value || "").trim();
  if (GEMINI_INDIC_VOICE_IDS.has(raw.toLowerCase())) return raw.toLowerCase();
  if (GEMINI_PREBUILT_VOICES.has(raw.toLowerCase())) {
    return raw[0].toUpperCase() + raw.slice(1).toLowerCase();
  }
  if (Object.prototype.hasOwnProperty.call(OPENAI_TO_GEMINI_VOICE_MAP, raw.toLowerCase())) {
    return defaultGeminiLiveVoice(language);
  }
  return defaultGeminiLiveVoice(language);
}

export function geminiMappedVoice(openAiSlug: string | undefined): string {
  const raw = String(openAiSlug || "").trim();
  if (GEMINI_INDIC_VOICE_IDS.has(raw.toLowerCase()) || GEMINI_PREBUILT_VOICES.has(raw.toLowerCase())) {
    return raw;
  }
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

  const tx =
    override.transcription &&
    typeof override.transcription === "object" &&
    !Array.isArray(override.transcription)
      ? (override.transcription as Record<string, unknown>)
      : {};

  return {
    ...base,
    language: String(override.language || base.language).trim() || base.language,
    llmProvider,
    llmModel: model || base.llmModel,
    realtimeVoice:
      llmProvider === "gemini"
        ? normalizeGeminiVoice(String(rv.voice || ""), String(override.language || base.language))
        : normalizeRealtimeVoice(String(rv.voice || base.realtimeVoice)),
    realtimeTurnDetection: normalizeRealtimeTurnDetection(
      String(rv.turn_detection || base.realtimeTurnDetection)
    ),
    realtimeVadEagerness: normalizeRealtimeVadEagerness(String(rv.vad_eagerness || base.realtimeVadEagerness)),
    realtimeNoiseReduction: normalizeRealtimeNoiseReduction(
      String(rv.noise_reduction || base.realtimeNoiseReduction)
    ),
    realtimeSpeed: normalizeRealtimeSpeed(rv.speed as number | string | undefined),
    realtimeSilenceMs: normalizeRealtimeSilenceMs(rv.silence_ms as number | string | undefined),
    transcriptionMode: tx.live_enabled
      ? "live"
      : tx.post_call_enabled !== undefined
        ? tx.post_call_enabled
          ? "post_call"
          : "off"
        : "post_call",
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
