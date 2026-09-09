"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { persistTestStudioVoice } from "@/lib/persist-test-studio-voice";
import { useTestStudioSessionOptional } from "@/components/test-studio/TestStudioSessionContext";
import { DEFAULT_SARVAM_SPEAKER, isCartesiaVoiceId } from "@/lib/voice/tts-config";

const FEMALE = new Set([
  "ritu", "priya", "neha", "pooja", "simran", "kavya", "ishita", "shreya", "roopa", "tanya",
  "shruti", "suhani", "kavitha", "rupali", "anushka", "manisha", "vidya",
]);
const MALE = new Set([
  "shubh", "aditya", "rahul", "rohan", "amit", "dev", "ratan", "varun", "manan", "sumit",
  "kabir", "aayan", "ashutosh", "advait", "anand", "tarun", "sunny", "mani", "gokul", "vijay",
  "mohit", "rehan", "soham", "arya", "abhilash", "karun", "hitesh",
]);

function groupSpeakers(speakers: string[]) {
  const female: string[] = [];
  const male: string[] = [];
  const other: string[] = [];
  for (const s of speakers) {
    const id = s.toLowerCase();
    if (FEMALE.has(id)) female.push(id);
    else if (MALE.has(id)) male.push(id);
    else other.push(id);
  }
  return { female, male, other };
}

export function SarvamVoiceSelect({
  value,
  onChange,
  disabled,
  className,
  model = "bulbul:v3",
  speakersV3 = [],
  speakersV2 = [],
}: {
  value: string;
  onChange: (speaker: string) => void;
  disabled?: boolean;
  className?: string;
  model?: string;
  speakersV3?: string[];
  speakersV2?: string[];
}) {
  const [saving, setSaving] = useState(false);
  const [saveHint, setSaveHint] = useState<string | null>(null);
  const autoAppliedRef = useRef("");
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const studioSession = useTestStudioSessionOptional();

  const list = model === "bulbul:v3" ? speakersV3 : speakersV2;
  const options = (list.length ? list : ["shubh", "priya", "kavya", "aditya"]).map((s) => s.toLowerCase());
  const known = new Set(options);
  const groups = groupSpeakers(options);
  const fallback = known.has(DEFAULT_SARVAM_SPEAKER) ? DEFAULT_SARVAM_SPEAKER : options[0] || DEFAULT_SARVAM_SPEAKER;
  const normalized = (value || "").trim().toLowerCase();
  const resolved =
    normalized && known.has(normalized) && !isCartesiaVoiceId(normalized) ? normalized : fallback;

  useEffect(() => {
    if (normalized && known.has(normalized) && !isCartesiaVoiceId(normalized)) return;
    if (autoAppliedRef.current === fallback) return;
    autoAppliedRef.current = fallback;
    onChangeRef.current(fallback);
    void persistTestStudioVoice({ ttsSpeaker: fallback, ttsModel: model, sessionId: studioSession?.sessionId }).then((result) => {
      setSaveHint(result.ok ? "Default Sarvam voice applied" : result.error || "Save failed");
    });
  }, [normalized, fallback, model]);

  async function pick(speaker: string) {
    autoAppliedRef.current = speaker;
    onChange(speaker);
    setSaving(true);
    setSaveHint(null);
    const result = await persistTestStudioVoice({ ttsSpeaker: speaker, ttsModel: model, sessionId: studioSession?.sessionId });
    setSaving(false);
    setSaveHint(result.ok ? "Voice saved — applies on next spoken turn" : result.error || "Save failed");
  }

  return (
    <div className="space-y-2">
      <select
        disabled={disabled || saving}
        className={cn(
          "w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50",
          className
        )}
        value={resolved}
        onChange={(e) => void pick(e.target.value)}
      >
        {groups.female.length > 0 && (
          <optgroup label={`Female (${groups.female.length})`}>
            {groups.female.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </optgroup>
        )}
        {groups.male.length > 0 && (
          <optgroup label={`Male (${groups.male.length})`}>
            {groups.male.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </optgroup>
        )}
        {groups.other.length > 0 && (
          <optgroup label="Other">
            {groups.other.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </optgroup>
        )}
      </select>
      <p className="text-[10px] text-text-subtle">
        Sarvam Bulbul · {options.length || 0} voices
        {saving ? " · saving…" : saveHint ? ` · ${saveHint}` : ""}
      </p>
    </div>
  );
}
