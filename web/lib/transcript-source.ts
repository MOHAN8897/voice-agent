/** Human labels for call transcript provenance (live vs post-call). */

export type TranscriptSourceInfo = {
  badge: string;
  detail: string;
  isPostCallGemini: boolean;
};

export function resolveTranscriptSource(meta?: {
  transcript_source?: string | null;
  usage?: { transcription_billing?: string; post_call_transcript_model?: string };
  post_call_transcript?: { status?: string; model?: string; source?: string };
} | null): TranscriptSourceInfo | null {
  if (!meta) return null;
  const source = String(
    meta.transcript_source ||
      meta.post_call_transcript?.source ||
      "",
  ).trim();
  const billing = String(meta.usage?.transcription_billing || "").trim();
  const postCall =
    billing === "post_call_gemini_transcribe" ||
    source.includes("gemini-3.5-transcribe") ||
    source.includes("telnyx+gemini");
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
