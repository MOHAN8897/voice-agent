import { ensureTtsVoice } from "@/lib/voice/tts-config";
import { modelsFor, type ProviderEntry, type StackForm } from "@/lib/test-studio-stack";

/** STT models valid for live PSTN (16 kHz wire). */
export function sttModelsForPstn(
  providers: ProviderEntry[],
  providerId: string,
  language: string
): { id: string; label?: string }[] {
  const all = modelsFor(providers, providerId, "stt");
  if (providerId === "sarvam") {
    const realtime = all.find((m) => m.id === "saaras:v3-realtime");
    if (realtime) return [realtime];
    const legacy = all.find((m) => m.id === "saaras:v3");
    if (legacy) {
      return [{ id: "saaras:v3-realtime", label: "Saaras v3 Realtime (PSTN)" }];
    }
    return all.filter((m) => m.id.includes("realtime"));
  }
  if (providerId === "cartesia") {
    if (language.startsWith("en")) {
      return all.filter((m) => m.id === "ink-2" || m.id === "ink-whisper");
    }
    return all.filter((m) => m.id === "ink-whisper");
  }
  return all;
}

export function defaultPstnSttModel(providerId: string, language: string): string {
  if (providerId === "cartesia") {
    return language.startsWith("en") ? "ink-2" : "ink-whisper";
  }
  return "saaras:v3-realtime";
}

/** Apply PSTN-safe defaults when channel is PSTN (does not affect browser agent). */
export function applyPstnStackDefaults(form: StackForm, language: string): StackForm {
  let { sttProvider, sttModel, ttsProvider, ttsModel, ttsVoiceId } = form;
  if (sttProvider === "sarvam" && sttModel === "saaras:v3") {
    sttModel = "saaras:v3-realtime";
  }
  if (sttProvider === "cartesia") {
    const ok =
      (sttModel === "ink-2" && language.startsWith("en")) || sttModel === "ink-whisper";
    if (!ok) sttModel = defaultPstnSttModel("cartesia", language);
  }
  ttsVoiceId = ensureTtsVoice(ttsProvider, ttsVoiceId, ttsModel);
  return {
    ...form,
    sttModel,
    sttMode: "transcribe",
    sttStreamType: "fast",
    ttsVoiceId,
    language,
  };
}

export type PstnStackValidation = {
  ok: boolean;
  error?: string;
  validation_errors?: string[];
  adjustments?: string[];
};
