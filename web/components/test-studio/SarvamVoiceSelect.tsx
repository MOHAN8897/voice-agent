"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { persistTestStudioVoice } from "@/lib/persist-test-studio-voice";

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
  const list = model === "bulbul:v3" ? speakersV3 : speakersV2;
  const groups = groupSpeakers(list.length ? list : ["shubh", "priya", "kavya", "aditya"]);
  const resolved = value || list[0] || "shubh";

  async function pick(speaker: string) {
    onChange(speaker);
    setSaving(true);
    setSaveHint(null);
    const result = await persistTestStudioVoice({ ttsSpeaker: speaker, ttsModel: model });
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
        Sarvam Bulbul · {list.length || 0} voices
        {saving ? " · saving…" : saveHint ? ` · ${saveHint}` : ""}
      </p>
    </div>
  );
}
