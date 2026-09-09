import { defaultTtsVoice, ensureTtsVoice, ttsProviderFromStack } from "@/lib/voice/tts-config";

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
  if (stackMode === "tier") {
    return {
      pipeline: "realtime_text",
      tts: { config: { speaker } },
    };
  }
  const full = buildStackOverride({ ...form, ttsVoiceId: speaker });
  const { llm: _omit, ...rest } = full as { llm?: unknown; stt?: unknown; tts?: unknown };
  return { ...rest, pipeline: "realtime_text" };
}

export function effectivePstnLiveLlm(runtimeOpenAiModel?: string): { provider: string; model: string } {
  const slug = String(runtimeOpenAiModel || "").trim();
  if (slug.startsWith("gpt-realtime")) {
    return { provider: "openai", model: slug };
  }
  return { provider: "openai", model: "gpt-realtime-2.1-mini" };
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
    a.language === b.language
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
