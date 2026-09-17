import { defaultTtsVoice, ensureTtsVoice, ttsProviderFromStack } from "@/lib/voice/tts-config";
import {
  DEFAULT_REALTIME_NOISE_REDUCTION,
  DEFAULT_REALTIME_SILENCE_MS,
  DEFAULT_REALTIME_SPEED,
  DEFAULT_REALTIME_TURN_DETECTION,
  DEFAULT_REALTIME_VAD_EAGERNESS,
  DEFAULT_REALTIME_VOICE,
  normalizeRealtimeNoiseReduction,
  normalizeRealtimeSilenceMs,
  normalizeRealtimeSpeed,
  normalizeRealtimeTurnDetection,
  normalizeRealtimeVadEagerness,
  normalizeRealtimeVoice,
} from "@/lib/realtime-voice";

export type StackForm = {
  sttProvider: string;
  sttModel: string;
  sttMode: string;
  sttStreamType: string;
  llmProvider: string;
  llmModel: string;
  ttsProvider: string;
  ttsModel: string;
  ttsVoiceId: string;
  language: string;
  realtimeVoice?: string;
  realtimeTurnDetection?: string;
  realtimeVadEagerness?: string;
  realtimeNoiseReduction?: string;
  realtimeSpeed?: number;
  realtimeSilenceMs?: number;
};

export type StackMode = "tier" | "custom";

export type ProviderEntry = {
  id: string;
  label?: string;
  enabled?: boolean;
  configured?: boolean;
  models?: { stt?: { id: string; label?: string }[]; llm?: { id: string; label?: string }[]; tts?: { id: string; label?: string }[] };
};

export type TierResolved = {
  stt?: { provider?: string; model?: string };
  llm?: { provider?: string; model?: string };
  tts?: { provider?: string; model?: string };
  language?: string;
};

export function defaultStackForm(row?: TierResolved): StackForm {
  const ttsProvider = row?.tts?.provider || "sarvam";
  const ttsModel = row?.tts?.model || "bulbul:v3";
  return {
    sttProvider: row?.stt?.provider || "sarvam",
    sttModel: row?.stt?.model || "saaras:v3",
    sttMode: "transcribe",
    sttStreamType: "fast",
    llmProvider: row?.llm?.provider || "openai",
    llmModel: row?.llm?.model || "gpt-realtime-2.1-mini",
    ttsProvider,
    ttsModel,
    ttsVoiceId: defaultTtsVoice(ttsProviderFromStack(ttsProvider, ttsModel)),
    language: row?.language || "te-IN",
    realtimeVoice: DEFAULT_REALTIME_VOICE,
    realtimeTurnDetection: DEFAULT_REALTIME_TURN_DETECTION,
    realtimeVadEagerness: DEFAULT_REALTIME_VAD_EAGERNESS,
    realtimeNoiseReduction: DEFAULT_REALTIME_NOISE_REDUCTION,
    realtimeSpeed: DEFAULT_REALTIME_SPEED,
    realtimeSilenceMs: DEFAULT_REALTIME_SILENCE_MS,
  };
}

export function modelsFor(providers: ProviderEntry[], providerId: string, stage: "stt" | "llm" | "tts") {
  const p = providers.find((x) => x.id === providerId);
  return p?.models?.[stage] || [];
}

export function buildStackOverride(form: StackForm): Record<string, unknown> {
  const speaker = ensureTtsVoice(form.ttsProvider, form.ttsVoiceId, form.ttsModel);
  const ttsConfig: Record<string, unknown> = { speaker };
  return {
    stt: {
      provider: form.sttProvider,
      model: form.sttModel,
      config: { mode: form.sttMode, stream_type: form.sttStreamType },
    },
    llm: { provider: form.llmProvider, model: form.llmModel },
    tts: {
      provider: form.ttsProvider,
      model: form.ttsModel,
      config: ttsConfig,
    },
  };
}

/** PSTN outbound stack — STT/TTS from form; live LLM comes from test-studio session + Realtime API. */
export function buildPstnStackOverride(form: StackForm, stackMode: StackMode): Record<string, unknown> {
  const speaker = ensureTtsVoice(form.ttsProvider, form.ttsVoiceId, form.ttsModel);
  const noiseReduction = normalizeRealtimeNoiseReduction(form.realtimeNoiseReduction);
  if (stackMode === "tier") {
    return {
      pipeline: "realtime_text",
      tts: { config: { speaker } },
      noise_reduction: noiseReduction,
    };
  }
  const full = buildStackOverride({ ...form, ttsVoiceId: speaker });
  const { llm: _omit, ...rest } = full as { llm?: unknown; stt?: unknown; tts?: unknown };
  return { ...rest, pipeline: "realtime_text", noise_reduction: noiseReduction };
}

/** Merge Place Call far-field toggle into the dial-time stack override. */
export function applyFarFieldNoiseReduction(
  override: Record<string, unknown> | undefined,
  enabled: boolean
): Record<string, unknown> {
  const noiseReduction = enabled ? "far_field" : "off";
  const base: Record<string, unknown> = { ...(override || {}) };
  const existing =
    base.realtime_voice && typeof base.realtime_voice === "object" && !Array.isArray(base.realtime_voice)
      ? { ...(base.realtime_voice as Record<string, unknown>) }
      : {};
  existing.noise_reduction = noiseReduction;
  base.noise_reduction = noiseReduction;
  base.realtime_voice = existing;
  return base;
}

export function effectivePstnLiveLlm(
  runtimeOpenAiModel?: string,
  stackLlmModel?: string
): { provider: string; model: string } {
  for (const slug of [stackLlmModel, runtimeOpenAiModel]) {
    const trimmed = String(slug || "").trim();
    if (trimmed.startsWith("gpt-realtime")) {
      return { provider: "openai", model: trimmed };
    }
  }
  return { provider: "openai", model: "gpt-realtime-2.1-mini" };
}

export function buildPstnRealtimeStackOverride(form: StackForm): Record<string, unknown> {
  const model = String(form.llmModel || "").startsWith("gpt-realtime")
    ? form.llmModel
    : "gpt-realtime-2.1-mini";
  return {
    pipeline: "realtime_voice",
    voice_flow: "realtime_e2e",
    llm: { provider: "openai", model },
    realtime_voice: {
      voice: normalizeRealtimeVoice(form.realtimeVoice),
      turn_detection: normalizeRealtimeTurnDetection(form.realtimeTurnDetection),
      vad_eagerness: normalizeRealtimeVadEagerness(form.realtimeVadEagerness),
      noise_reduction: normalizeRealtimeNoiseReduction(form.realtimeNoiseReduction),
      speed: normalizeRealtimeSpeed(form.realtimeSpeed),
      silence_ms: normalizeRealtimeSilenceMs(form.realtimeSilenceMs),
    },
  };
}

export function stackFormEqual(a: StackForm, b: StackForm): boolean {
  return (
    a.sttProvider === b.sttProvider &&
    a.sttModel === b.sttModel &&
    a.sttMode === b.sttMode &&
    a.sttStreamType === b.sttStreamType &&
    a.llmProvider === b.llmProvider &&
    a.llmModel === b.llmModel &&
    a.ttsProvider === b.ttsProvider &&
    a.ttsModel === b.ttsModel &&
    a.ttsVoiceId === b.ttsVoiceId &&
    a.language === b.language &&
    (a.realtimeVoice || DEFAULT_REALTIME_VOICE) === (b.realtimeVoice || DEFAULT_REALTIME_VOICE) &&
    (a.realtimeTurnDetection || DEFAULT_REALTIME_TURN_DETECTION) ===
      (b.realtimeTurnDetection || DEFAULT_REALTIME_TURN_DETECTION) &&
    (a.realtimeVadEagerness || DEFAULT_REALTIME_VAD_EAGERNESS) ===
      (b.realtimeVadEagerness || DEFAULT_REALTIME_VAD_EAGERNESS) &&
    (a.realtimeNoiseReduction || DEFAULT_REALTIME_NOISE_REDUCTION) ===
      (b.realtimeNoiseReduction || DEFAULT_REALTIME_NOISE_REDUCTION) &&
    normalizeRealtimeSpeed(a.realtimeSpeed) === normalizeRealtimeSpeed(b.realtimeSpeed) &&
    normalizeRealtimeSilenceMs(a.realtimeSilenceMs) === normalizeRealtimeSilenceMs(b.realtimeSilenceMs)
  );
}

/** Legacy global session — prefer testStudioSessionId(agentId) for isolated labs. */
export const TEST_STUDIO_SESSION_ID = "test-studio";

/** Per-agent Test Studio session — brief, stack, runtime, and UI prefs are isolated. */
export function testStudioSessionId(agentId: string): string {
  const id = String(agentId || "").trim();
  if (!id) return TEST_STUDIO_SESSION_ID;
  return `test-studio:${id}`;
}
