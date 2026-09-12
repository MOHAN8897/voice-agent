"use client";

import { StudioTabRail } from "@/components/test-studio/StudioTabRail";

export type TestStudioMode = "agent" | "pstn" | "pstn_realtime";

const MODES: { id: TestStudioMode; label: string; hint: string }[] = [
  {
    id: "agent",
    label: "Agent only",
    hint: "Browser mic · STT → brain → TTS · no PSTN",
  },
  {
    id: "pstn",
    label: "Full PSTN flow",
    hint: "Telnyx · STT → Realtime text → TTS",
  },
  {
    id: "pstn_realtime",
    label: "Realtime PSTN",
    hint: "Telnyx · OpenAI Realtime mini · audio in/out",
  },
];

export function TestStudioModePicker({
  mode,
  onModeChange,
  locked,
  showPstn = true,
}: {
  mode: TestStudioMode;
  onModeChange: (m: TestStudioMode) => void;
  locked?: boolean;
  showPstn?: boolean;
}) {
  const options = showPstn ? MODES : MODES.filter((m) => m.id === "agent");

  return (
    <StudioTabRail
      tone="parent"
      ariaLabel="Test mode"
      testId="test-studio-mode-picker"
      items={options.map((m) => ({
        id: m.id,
        label: m.label,
        hint: m.hint,
        testId: `test-mode-${m.id}`,
      }))}
      value={mode}
      onChange={onModeChange}
      locked={locked}
    />
  );
}
