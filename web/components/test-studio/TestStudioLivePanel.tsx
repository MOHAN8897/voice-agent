"use client";

import { useRef, useState } from "react";
import {
  LiveVoiceSession,
  type Bubble,
  type LiveVoiceSessionHandle,
  type SessionTraceEvent,
  type TurnCompleteEvent,
} from "@/components/live/LiveVoiceSession";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { VoiceControlOrb } from "@/components/test-studio/VoiceControlOrb";
import { LiveTranscriptConsole, type TranscriptLine } from "@/components/test-studio/LiveTranscriptConsole";

export function TestStudioLivePanel({
  agentId,
  tier,
  languageCode,
  stackOverride,
  sessionId,
  onTrace,
  onCallStart,
  onCallEnd,
  onStatusChange,
  onTurnComplete,
}: {
  agentId: string;
  tier: string;
  languageCode: string;
  stackOverride?: Record<string, unknown>;
  sessionId?: string;
  onTrace: (e: SessionTraceEvent) => void;
  onCallStart: (callId: string) => void;
  onCallEnd: (callId: string) => void;
  onStatusChange: (status: string) => void;
  onTurnComplete?: (event: TurnCompleteEvent) => void;
}) {
  const sessionRef = useRef<LiveVoiceSessionHandle>(null);
  const [status, setStatus] = useState("idle");
  const [micLevel, setMicLevel] = useState(0);
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [partial, setPartial] = useState("");

  const listening =
    status === "listening" ||
    status === "connecting" ||
    status === "thinking" ||
    status === "speaking";
  const callActive = status !== "idle" && status !== "ended" && status !== "paused";
  const orbActive = listening;

  function handleStatus(next: string) {
    setStatus(next);
    onStatusChange(next);
  }

  function handleTranscript(bubbles: Bubble[], partialText: string) {
    setPartial(partialText);
    setLines(
      bubbles.map((b) => ({
        role: b.role,
        text: b.text,
        interrupted: b.interrupted,
        ts: b.ts,
      }))
    );
  }

  return (
    <SkeuoPanel
      title="Live conversation"
      description="Mic → STT → brain stream → TTS · chat transcript below"
      padding="md"
      className="console-page-enter"
    >
      <div className="mb-5 flex flex-col items-center gap-3 border-b border-surface-border-subtle pb-5 lg:flex-row lg:items-start lg:justify-between">
        <VoiceControlOrb
          status={status}
          level={micLevel}
          active={orbActive}
          listening={listening}
          callActive={callActive}
          onStart={() => sessionRef.current?.startListening()}
          onStop={() => sessionRef.current?.pauseListening()}
        />
        <div className="flex flex-col items-center gap-2 lg:items-end">
          <SkeuoButton variant="ghost" size="sm" onClick={() => sessionRef.current?.endCall()}>
            End call
          </SkeuoButton>
          <p className="max-w-xs text-center text-[11px] text-text-muted lg:text-right">
            {listening
              ? "Listening — your words appear in the chat below"
              : callActive
                ? "Mic off — flip the switch to speak again"
                : "Turn on the mic to start a voice session"}
          </p>
        </div>
      </div>

      <LiveTranscriptConsole
        lines={lines}
        partial={partial}
        speaking={status === "speaking"}
        thinking={status === "thinking"}
        className="max-h-[min(42vh,22rem)]"
      />

      <div className="sr-only">
        <LiveVoiceSession
          ref={sessionRef}
          agentId={agentId}
          tier={tier}
          languageCode={languageCode}
          stackOverride={stackOverride}
          sessionId={sessionId}
          variant="lab"
          onTrace={onTrace}
          onCallStart={onCallStart}
          onCallEnd={onCallEnd}
          onStatusChange={handleStatus}
          onMicLevel={setMicLevel}
          onTranscriptChange={handleTranscript}
          onTurnComplete={onTurnComplete}
        />
      </div>
    </SkeuoPanel>
  );
}
