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
  return {
    sttProvider: row?.stt?.provider || "sarvam",
    sttModel: row?.stt?.model || "saaras:v3",
    sttMode: "transcribe",
    sttStreamType: "fast",
    llmProvider: row?.llm?.provider || "openai",
    llmModel: row?.llm?.model || "gpt-5.6-luna",
    ttsProvider: row?.tts?.provider || "sarvam",
    ttsModel: row?.tts?.model || "bulbul:v3",
    ttsVoiceId: "",
    language: row?.language || "te-IN",
  };
}

export function modelsFor(providers: ProviderEntry[], providerId: string, stage: "stt" | "llm" | "tts") {
  const p = providers.find((x) => x.id === providerId);
  return p?.models?.[stage] || [];
}

export function buildStackOverride(form: StackForm): Record<string, unknown> {
  const ttsConfig: Record<string, unknown> = {};
  if (form.ttsProvider === "cartesia" && form.ttsVoiceId) {
    ttsConfig.speaker = form.ttsVoiceId;
  } else if (form.ttsProvider === "sarvam" && form.ttsVoiceId) {
    ttsConfig.speaker = form.ttsVoiceId;
  }
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

/** PSTN outbound custom stack — same shape as buildStackOverride. */
export function buildPstnStackOverride(form: StackForm): Record<string, unknown> {
  return buildStackOverride(form);
}

export const TEST_STUDIO_SESSION_ID = "test-studio";
