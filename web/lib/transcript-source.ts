/** Human labels for call transcript provenance (live vs post-call). */

export type TranscriptSourceInfo = {
  badge: string;
  detail: string;
  isPostCallGemini: boolean;
};

type TranscriptSourceMeta = {
  transcript_source?: string | null;
  usage?: { transcription_billing?: string; post_call_transcript_model?: string };
  post_call_transcript?: { status?: string; model?: string; source?: string };
  internal_fields_hidden?: boolean;
} | null;

/**
 * Provenance, in the words the viewer is allowed to have.
 *
 * Naming the transcription vendors and the exact model told a tenant which suppliers
 * sit behind their call and what each of them charges — the same class of leak as the
 * wholesale rates on the metadata panel. A tenant gets "how this call was
 * transcribed"; the platform team still gets the model names for debugging.
 */
export function resolveTranscriptSource(
  meta?: TranscriptSourceMeta,
  audience: "tenant" | "internal" = "internal"
): TranscriptSourceInfo | null {
  if (!meta) return null;
  const internal = audience === "internal" && !meta.internal_fields_hidden;
  const source = String(
    meta.transcript_source ||
      meta.post_call_transcript?.source ||
      "",
  ).trim();
  const billing = String(meta.usage?.transcription_billing || "").trim();
  const liveOpenai =
    billing.includes("live_openai_transcribe") || source.includes("gpt-4o-mini-transcribe") || source.startsWith("live:");
  const postCall =
    billing.includes("post_call_gemini_transcribe") ||
    source.includes("gemini-3.5-transcribe") ||
    source.includes("telnyx+gemini") ||
    Boolean(meta.post_call_transcript?.status);

  if (!internal) {
    if (postCall) {
      return {
        badge: "Transcript: recorded and transcribed",
        detail:
          "The call was recorded and transcribed after the conversation finished, so the transcript is available in full.",
        isPostCallGemini: true,
      };
    }
    if (liveOpenai || source || billing) {
      return {
        badge: "Transcript: live",
        detail: "Speech was transcribed during the call.",
        isPostCallGemini: false,
      };
    }
    return null;
  }

  if (liveOpenai && !postCall) {
    return {
      badge: "Transcript: gpt-4o-mini-transcribe (live)",
      detail: "Caller audio transcribed during the call with OpenAI gpt-4o-mini-transcribe.",
      isPostCallGemini: false,
    };
  }
  if (postCall) {
    const model =
      meta.post_call_transcript?.model ||
      meta.usage?.post_call_transcript_model ||
      "gemini-3.5-transcribe";
    return {
      badge: "Transcript: Telnyx + Gemini 3.5 (post-call)",
      detail: `Recorded on Telnyx, transcribed after hangup with ${model}. Live Gemini 3.8 session is voice-only (no native transcript billing).`,
      isPostCallGemini: true,
    };
  }
  if (source) {
    return {
      badge: `Transcript: ${source}`,
      detail: "Transcript source from call ledger metadata.",
      isPostCallGemini: false,
    };
  }
  if (billing) {
    return {
      badge: `Transcription billing: ${billing}`,
      detail: "",
      isPostCallGemini: billing === "post_call_gemini_transcribe",
    };
  }
  return null;
}