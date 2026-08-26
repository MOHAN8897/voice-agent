"use client";

import { useRef, useState } from "react";
import {
  LiveVoiceSession,
  type Bubble,
  type LiveVoiceSessionHandle,
  type SessionTraceEvent,
} from "@/components/live/LiveVoiceSession";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { VoiceControlOrb } from "@/components/test-studio/VoiceControlOrb";
import { LiveTranscriptConsole, type TranscriptLine } from "@/components/test-studio/LiveTranscriptConsole";

export function TestStudioLivePanel({
  agentId,
  tier,
  languageCode,
  onTrace,
  onCallStart,
  onCallEnd,
  onStatusChange,
}: {
  agentId: string;
  tier: string;
  languageCode: string;
  onTrace: (e: SessionTraceEvent) => void;
  onCallStart: (callId: string) => void;
  onCallEnd: (callId: string) => void;
  onStatusChange: (status: string) => void;
}) {
  const sessionRef = useRef<LiveVoiceSessionHandle>(null);
  const [status, setStatus] = useState("idle");
  const [micLevel, setMicLevel] = useState(0);
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [partial, setPartial] = useState("");

  const listening = status === "listening" || status === "connecting";
  const orbActive = listening || status === "speaking" || status === "thinking";

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
      description="Mic → STT → brain stream → TTS · monitoring console"
      padding="md"
      className="console-page-enter"
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,200px)_minmax(0,1fr)]">
        <div className="flex flex-col items-center gap-3">
          <VoiceControlOrb
            status={status}
            level={micLevel}
            active={orbActive}
            listening={listening}
            onStart={() => sessionRef.current?.startListening()}
            onStop={() => sessionRef.current?.stopListening()}
          />
          <div className="flex flex-wrap justify-center gap-2">
            <SkeuoButton variant="ghost" size="sm" onClick={() => sessionRef.current?.endCall()}>
              End call
            </SkeuoButton>
          </div>
        </div>

        <LiveTranscriptConsole lines={lines} partial={partial} speaking={status === "speaking"} />
      </div>

      <div className="mt-4 border-t border-surface-border-subtle pt-4">
        <LiveVoiceSession
          ref={sessionRef}
          agentId={agentId}
          tier={tier}
          languageCode={languageCode}
          variant="lab"
          onTrace={onTrace}
          onCallStart={onCallStart}
          onCallEnd={onCallEnd}
          onStatusChange={handleStatus}
          onMicLevel={setMicLevel}
          onTranscriptChange={handleTranscript}
        />
      </div>
    </SkeuoPanel>
  );
}
