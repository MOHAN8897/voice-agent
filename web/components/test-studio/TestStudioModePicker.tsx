"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { cn } from "@/lib/cn";

export type TestStudioMode = "agent" | "pstn";

const MODES: { id: TestStudioMode; label: string; hint: string }[] = [
  {
    id: "agent",
    label: "Agent only",
    hint: "Browser mic · STT → brain → TTS · no Exotel",
  },
  {
    id: "pstn",
    label: "Full PSTN flow",
    hint: "Exotel handshake · outbound · telephony stream",
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
    <div data-testid="test-studio-mode-picker">
    <SkeuoPanel
      title="Test mode"
      description="Agent-only uses your mic. Full PSTN uses Exotel virtual number + stream."
      padding="sm"
    >
      <div className="flex flex-col gap-2 sm:flex-row">
        {options.map((m) => (
          <button
            key={m.id}
            type="button"
            data-testid={`test-mode-${m.id}`}
            disabled={locked}
            onClick={() => onModeChange(m.id)}
            className={cn(
              "flex-1 rounded-skeuo-sm border px-3 py-2.5 text-left transition-all disabled:opacity-50",
              mode === m.id
                ? "skeuo-btn-primary border-transparent text-white"
                : "skeuo-btn-secondary border-surface-border-subtle"
            )}
          >
            <span className="block text-xs font-semibold uppercase tracking-wide">{m.label}</span>
            <span
              className={cn(
                "mt-0.5 block text-[10px] leading-snug",
                mode === m.id ? "text-white/80" : "text-text-muted"
              )}
            >
              {m.hint}
            </span>
          </button>
        ))}
      </div>
    </SkeuoPanel>
    </div>
  );
}
