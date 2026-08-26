"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import type { SessionTraceEvent } from "@/components/live/LiveVoiceSession";
import { TestStudioLifecycle } from "@/components/test-studio/TestStudioLifecycle";
import { TestStudioEventStream } from "@/components/test-studio/TestStudioEventStream";

export function TestStudioDiagnostics({
  callId,
  channel,
  callEnded,
  events,
  memoryJson,
}: {
  callId: string | null;
  channel: "browser" | "pstn";
  callEnded: boolean;
  events: SessionTraceEvent[];
  memoryJson: string;
}) {
  return (
    <div className="space-y-4 console-page-enter">
      <TestStudioLifecycle callId={callId} channel={channel} ended={callEnded} />
      <TestStudioEventStream events={events} />
      <SkeuoPanel title="Memory projection" description="Layer C — LLM context each turn" padding="md">
        <pre className="max-h-40 overflow-auto font-mono text-[11px] text-text-muted skeuo-inset rounded-skeuo-sm p-3">
          {memoryJson || "Start a call to inspect server-owned memory projection."}
        </pre>
      </SkeuoPanel>
    </div>
  );
}
