"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { portalFetch } from "@/lib/auth-client";
import { persistTestStudioVoice } from "@/lib/persist-test-studio-voice";
import { useTestStudioSessionOptional } from "@/components/test-studio/TestStudioSessionContext";

type Voice = { id: string; providerVoiceId: string; category?: string; languages: string[] };

export function SarvamVoiceSelect({ value, onChange, disabled, className, model = "bulbul:v3", provider = "sarvam", language,
}: { value: string; onChange: (speaker: string) => void; disabled?: boolean; className?: string;
  model?: string; provider?: string; language?: string; speakersV3?: string[]; speakersV2?: string[];
}) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const session = useTestStudioSessionOptional();
  useEffect(() => {
    let current = true;
    setVoices([]); setLoading(true); setError("");
    void (async () => {
      try {
        const response = await portalFetch("dev", "/api/dev/stack/catalog");
        if (!response.ok) throw new Error("Could not load the model's voice catalog.");
        const data = await response.json();
        const rows = data.providers?.find((entry: { id: string }) => entry.id === provider)?.models?.tts?.find((entry: { id: string }) => entry.id === model)?.voices;
        if (!Array.isArray(rows)) throw new Error("No verified voices are available for this model.");
        if (current) setVoices(rows);
      } catch (caught) { if (current) setError(caught instanceof Error ? caught.message : "Could not load voices."); }
      finally { if (current) setLoading(false); }
    })();
    return () => { current = false; };
  }, [provider, model]);
  const available = voices.map((voice, index) => ({ ...voice, number: index + 1 })).filter((voice) => !language || voice.languages.includes(language));
  const known = available.some((voice) => voice.providerVoiceId === value);
  async function pick(id: string) {
    setSaving(true); setError("");
    try {
      const result = await persistTestStudioVoice({ ttsSpeaker: id, ttsModel: model, sessionId: session?.sessionId });
      if (!result.ok) throw new Error(result.error || "Could not save voice.");
      onChange(id);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not save voice."); }
    finally { setSaving(false); }
  }
  return <div className="space-y-2">
    <select aria-label="Speech model voice" disabled={disabled || loading || saving} value={known ? value : ""}
      className={cn("w-full rounded border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50", className)}
      onChange={(event) => void pick(event.target.value)}>
      <option value="" disabled>{loading ? "Loading voices…" : "Choose a voice"}</option>
      {available.map((voice) => <option key={voice.providerVoiceId} value={voice.providerVoiceId}>Voice {voice.number}{voice.category ? ` · ${voice.category}` : ""}</option>)}
    </select>
    <p className="text-xs text-text-muted">{available.length} model voices{saving ? " · saving…" : ""}</p>
    {value && !known && !loading && <p role="alert" className="text-xs text-status-warning">The saved voice is unavailable for this model and language. Choose a current voice.</p>}
    {error && <p role="alert" className="text-xs text-status-warning">{error}</p>}
  </div>;
}
