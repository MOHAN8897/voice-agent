"use client";

import {
  DEFAULT_REALTIME_VOICE,
  isGeminiLiveVoiceModel,
  REALTIME_VOICE_OPTIONS,
  realtimeVoiceOptionLabel,
} from "@/lib/realtime-voice";

const inputCls =
  "w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50";

type Props = {
  value: string | undefined;
  onChange: (voiceId: string) => void;
  disabled?: boolean;
  llmModel?: string;
  className?: string;
};

export function RealtimeVoiceSelect({ value, onChange, disabled, llmModel, className }: Props) {
  const gemini = isGeminiLiveVoiceModel(llmModel);
  const current = value || DEFAULT_REALTIME_VOICE;

  return (
    <div className={className}>
      <select
        disabled={disabled}
        className={inputCls}
        value={current}
        onChange={(e) => onChange(e.target.value)}
      >
        {REALTIME_VOICE_OPTIONS.map((v) => (
          <option key={v.id} value={v.id}>
            {realtimeVoiceOptionLabel(v.id, { geminiLive: gemini })}
          </option>
        ))}
      </select>
      {gemini ? (
        <p className="mt-1 text-[11px] text-text-subtle">
          PSTN uses Gemini voice{" "}
          <span className="font-mono">
            {REALTIME_VOICE_OPTIONS.find((v) => v.id === current)?.geminiVoice || "Puck"}
          </span>
          {" "}
          (
          {REALTIME_VOICE_OPTIONS.find((v) => v.id === current)?.geminiGender || "—"})
        </p>
      ) : null}
    </div>
  );
}
