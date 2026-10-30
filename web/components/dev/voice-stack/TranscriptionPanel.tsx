"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch } from "@/lib/auth-client";
import { responseError } from "@/components/dev/voice-stack/profileModel";

/** When and how caller speech is transcribed on PSTN calls (platform-wide). */
export function TranscriptionPanel() {
  const [transcriptionMode, setTranscriptionMode] = useState<"off" | "live" | "post_call">("off");
  const [transcriptionLiveModel, setTranscriptionLiveModel] = useState("gpt-4o-mini-transcribe");
  const [saasPhoneRaw, setSaasPhoneRaw] = useState<Record<string, unknown> | null>(null);
  const [transcriptionSaving, setTranscriptionSaving] = useState(false);
  const [transcriptionStatus, setTranscriptionStatus] = useState("");
  const [transcriptionError, setTranscriptionError] = useState("");

  const loadTranscription = useCallback(async () => {
    try {
      const res = await portalFetch("dev", "/api/dev/stack/saas-phone");
      if (!res.ok) return;
      const data = await res.json();
      const saved = (data.saved?.stack_override || data.resolved) as Record<string, unknown> | undefined;
      if (saved) {
        setSaasPhoneRaw(saved);
        if (typeof saved.transcription_mode === "string") {
          setTranscriptionMode(saved.transcription_mode as "off" | "live" | "post_call");
        }
        if (typeof saved.transcription_live_model === "string") {
          setTranscriptionLiveModel(saved.transcription_live_model);
        }
      }
    } catch {
      // Non-blocking transcription fetch
    }
  }, []);

  useEffect(() => {
    void loadTranscription();
  }, [loadTranscription]);

  async function handleSaveTranscription() {
    if (transcriptionSaving) return;
    setTranscriptionSaving(true);
    setTranscriptionStatus("");
    setTranscriptionError("");
    try {
      const currentOverride: Record<string, unknown> = saasPhoneRaw ? { ...saasPhoneRaw } : { pipeline: "realtime_voice", language: "te-IN" };
      currentOverride.transcription_mode = transcriptionMode;
      currentOverride.transcription_live_model = transcriptionLiveModel;

      const res = await portalFetch("dev", "/api/dev/stack/saas-phone", {
        method: "PUT",
        body: JSON.stringify({
          language: String(currentOverride.language || "te-IN"),
          stack_override: currentOverride,
        }),
      });
      if (!res.ok) throw new Error(await responseError(res));
      setTranscriptionStatus("Transcription configuration saved and applied globally.");
      await loadTranscription();
    } catch (err) {
      setTranscriptionError(err instanceof Error ? err.message : "Failed to save transcription.");
    } finally {
      setTranscriptionSaving(false);
    }
  }

  return (
    <DevCard
      title="Transcription Mode & Caller Transcripts"
      description="Choose when and how caller speech is transcribed into text records during PSTN telephone conversations."
    >
      {transcriptionError && (
        <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
          {transcriptionError}
        </div>
      )}
      {transcriptionStatus && (
        <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
          {transcriptionStatus}
        </div>
      )}

      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            {
              id: "off" as const,
              title: "Off",
              detail: "No caller transcripts recorded. Reduces processing overhead for high-throughput calls.",
            },
            {
              id: "live" as const,
              title: "Live transcription",
              detail: "Caller speech transcribed in real time during the call using the selected recognizer below.",
            },
            {
              id: "post_call" as const,
              title: "Post-call — Gemini 3.5 Transcribe",
              detail: "~$0.005/min batch processed from recording after call hangs up.",
            },
          ].map((opt) => (
            <label
              key={opt.id}
              className={`flex flex-col rounded-xl border p-4 cursor-pointer transition-all ${
                transcriptionMode === opt.id
                  ? "border-accent-primary bg-accent-dim shadow-sm"
                  : "border-surface-border bg-surface-card hover:bg-surface-raised/40"
              }`}
            >
              <div className="flex items-center gap-2">
                <input
                  type="radio"
                  name="workbenchTranscriptionMode"
                  checked={transcriptionMode === opt.id}
                  onChange={() => setTranscriptionMode(opt.id)}
                  className="accent-accent-primary"
                />
                <span className="font-semibold text-xs text-text">{opt.title}</span>
              </div>
              <p className="mt-2 text-xs text-text-muted leading-relaxed">{opt.detail}</p>
            </label>
          ))}
        </div>

        {transcriptionMode === "live" && (
          <div className="mt-4 rounded-xl border border-surface-border bg-surface-raised/40 p-4 space-y-2">
            <label className="block text-xs font-semibold text-text">
              Live Transcription Recognizer Model
            </label>
            <select
              value={transcriptionLiveModel}
              onChange={(e) => setTranscriptionLiveModel(e.target.value)}
              className="w-full sm:max-w-md rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-xs text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
            >
              <option value="gpt-4o-mini-transcribe">GPT-4o Mini Transcribe · ~$0.003/min</option>
              <option value="gpt-transcribe">GPT-Transcribe · ~$0.0045/min</option>
              <option value="saaras:v3-realtime">Sarvam Saaras Realtime · ~₹0.50/min</option>
              <option value="gemini-native">Gemini Native · In-session tokens</option>
            </select>
            <p className="text-[11px] text-text-subtle">
              The recognizer receives the inbound caller audio stream and writes live speech transcripts to the database.
            </p>
          </div>
        )}

        <div className="mt-6 pt-4 border-t border-border flex items-center justify-between">
          <span className="text-xs text-text-subtle">
            Applies globally to new inbound and outbound PSTN calls.
          </span>
          <Button
            type="button"
            disabled={transcriptionSaving}
            onClick={() => void handleSaveTranscription()}
            className="px-5 py-2.5"
          >
            {transcriptionSaving ? "Saving…" : "Save Transcription Settings"}
          </Button>
        </div>
      </div>
    </DevCard>
  );
}
