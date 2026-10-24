"use client";

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { persistTestStudioVoice } from "@/lib/persist-test-studio-voice";
import { useTestStudioSessionOptional } from "@/components/test-studio/TestStudioSessionContext";

export type CartesiaVoice = { id: string; name: string; gender?: string; languages?: string[]; category?: string };

export function CartesiaVoiceSelect({ value, onChange, disabled, className, showMeta = true,
  ttsModel = "sonic-3.5", autoSave = true, initialVoices, language,
}: { value: string; onChange: (voiceId: string) => void; disabled?: boolean; className?: string;
  showMeta?: boolean; ttsModel?: string; autoSave?: boolean; defaultVoiceId?: string;
  initialVoices?: CartesiaVoice[]; language?: string;
}) {
  const [voices, setVoices] = useState<CartesiaVoice[]>(initialVoices || []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const session = useTestStudioSessionOptional();
  const load = useCallback(async (refresh = false) => {
    setLoading(true); setError("");
    try {
      const query = new URLSearchParams({ model: ttsModel, refresh: String(refresh) });
      const response = await fetch(`/api/settings/cartesia-voices?${query}`, { credentials: "include" });
      if (!response.ok) throw new Error("Could not load the model's voice catalog.");
      const data = await response.json();
      if (!Array.isArray(data.voices)) throw new Error("Incomplete voice catalog.");
      setVoices(data.voices);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not load voices."); }
    finally { setLoading(false); }
  }, [ttsModel]);
  useEffect(() => { setVoices([]); void load(); }, [load]);
  const numbered = voices.map((voice, index) => ({ ...voice, number: index + 1 }));
  const available = numbered.filter((voice) => !language || voice.languages?.includes(language));
  const selected = available.some((voice) => voice.id === value);
  async function choose(id: string) {
    setError("");
    if (autoSave) {
      setLoading(true);
      const result = await persistTestStudioVoice({ ttsSpeaker: id, ttsModel, sessionId: session?.sessionId });
      setLoading(false);
      if (!result.ok) { setError(result.error || "Could not save voice."); return; }
    }
    onChange(id);
  }
  return <div className="space-y-2">
    <div className="flex gap-2">
      <select aria-label="Model voice" disabled={disabled || loading} value={selected ? value : ""}
        className={cn("min-w-0 flex-1 rounded border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm", className)}
        onChange={(event) => void choose(event.target.value)}>
        <option value="" disabled>{loading ? "Loading voices…" : "Choose a voice"}</option>
        {available.map((voice) => <option key={voice.id} value={voice.id}>
          Voice {voice.number} · {voice.languages?.join(", ")}{voice.category ? ` · ${voice.category}` : ""}
        </option>)}
      </select>
      <button type="button" disabled={disabled || loading} onClick={() => void load(true)} className="rounded border px-3 text-xs">Refresh</button>
    </div>
    {value && !selected && !loading && <p role="alert" className="text-xs text-status-warning">The saved voice is unavailable for this model and language. Choose a current voice.</p>}
    {showMeta && <p className="text-xs text-text-muted">{available.length} Indian language voices</p>}
    {error && <p role="alert" className="text-xs text-status-warning">{error}</p>}
  </div>;
}
