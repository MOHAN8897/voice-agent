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
}: {
  callId: string | null;
  channel: "agent" | "pstn";
  callEnded: boolean;
  events: SessionTraceEvent[];
}) {
  return (
    <div className="space-y-4 console-page-enter">
      <TestStudioLifecycle callId={callId} channel={channel} ended={callEnded} />
      <TestStudioEventStream events={events} />
    </div>
  );
}
