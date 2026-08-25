"use client";

import { useEffect, useState } from "react";
import { LiveVoiceSession, type SessionTraceEvent } from "@/components/live/LiveVoiceSession";
import { DevCard } from "@/components/dev/DevCard";
import { DevMicOrb } from "@/components/dev/test-studio/DevMicOrb";

export function BrowserTestPanel({
  agentId,
  tier,
  onTrace,
  onCallStart,
  onCallEnd,
  onStatusChange,
}: {
  agentId: string;
  tier: string;
  onTrace: (e: SessionTraceEvent) => void;
  onCallStart: (callId: string) => void;
  onCallEnd: (callId: string) => void;
  onStatusChange: (status: string) => void;
}) {
  const [status, setStatus] = useState("idle");
  const [micLevel, setMicLevel] = useState(0);

  useEffect(() => {
    onStatusChange(status);
  }, [status, onStatusChange]);

  return (
    <DevCard title="Browser live test" description="Mic → STT → brain stream → TTS · config locks at call/start">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <DevMicOrb status={status} level={micLevel} active={status === "listening" || status === "connecting"} />
        <LiveVoiceSession
          agentId={agentId}
          tier={tier}
          variant="dev"
          onTrace={onTrace}
          onCallStart={onCallStart}
          onCallEnd={onCallEnd}
          onStatusChange={setStatus}
          onMicLevel={setMicLevel}
        />
      </div>
    </DevCard>
  );
}
