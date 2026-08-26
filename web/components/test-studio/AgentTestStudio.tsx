"use client";

import { useCallback, useEffect, useState } from "react";
import type { SessionTraceEvent } from "@/components/live/LiveVoiceSession";
import { CallDetailView } from "@/components/calls/CallDetailView";
import { PstnTestPanel } from "@/components/dev/test-studio/PstnTestPanel";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { refreshPortalSession, portalFetch } from "@/lib/auth-client";
import { TestStudioConfigRack } from "@/components/test-studio/TestStudioConfigRack";
import { TestStudioLivePanel } from "@/components/test-studio/TestStudioLivePanel";
import { TestStudioDiagnostics } from "@/components/test-studio/TestStudioDiagnostics";
import { LatencyWaterfallPanel } from "@/components/test-studio/LatencyWaterfallPanel";

type ChannelTab = "browser" | "pstn";

export function AgentTestStudio({
  agentId,
  portal = "app",
}: {
  agentId: string;
  portal?: "app" | "dev";
}) {
  const [channel, setChannel] = useState<ChannelTab>("browser");
  const [tier, setTier] = useState("medium");
  const [language, setLanguage] = useState("te-IN");
  const [events, setEvents] = useState<SessionTraceEvent[]>([]);
  const [callId, setCallId] = useState<string | null>(null);
  const [callEnded, setCallEnded] = useState(false);
  const [memoryJson, setMemoryJson] = useState("");
  const [sessionStatus, setSessionStatus] = useState("idle");
  const [locked, setLocked] = useState(false);

  const refreshMemory = useCallback(async (id: string) => {
    const r = await fetch(`/api/call/${id}/memory/projection`, { credentials: "include" });
    if (!r.ok) return;
    const j = await r.json();
    setMemoryJson(JSON.stringify(j?.projection || j, null, 2));
  }, []);

  useEffect(() => {
    if (portal === "dev") refreshPortalSession("dev");
    fetch(`/api/agents/${agentId}`, { credentials: "include" })
      .then((r) => r.json())
      .then((j) => {
        if (j.agent?.default_tier) setTier(j.agent.default_tier);
      });
  }, [agentId, portal]);

  useEffect(() => {
    if (!callId || callEnded) return;
    const t = setInterval(() => refreshMemory(callId), 4000);
    return () => clearInterval(t);
  }, [callId, callEnded, refreshMemory]);

  function onTrace(event: SessionTraceEvent) {
    setEvents((prev) => [...prev, event]);
  }

  function onCallStart(id: string) {
    setCallId(id);
    setCallEnded(false);
    setLocked(true);
    setEvents([]);
    refreshMemory(id);
  }

  function onCallEnd(id: string) {
    setCallEnded(true);
    setLocked(false);
    setSessionStatus("ended");
    refreshMemory(id);
    if (portal === "dev") {
      portalFetch("dev", `/api/call/${id}/memory/projection`).then(async (r) => {
        if (r.ok) {
          const j = await r.json();
          setMemoryJson(JSON.stringify(j?.projection || j, null, 2));
        }
      });
    }
  }

  const showPstn = portal === "dev";

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,260px)_minmax(0,1fr)_minmax(0,300px)]">
        <TestStudioConfigRack
          channel={channel}
          onChannelChange={setChannel}
          showPstn={showPstn}
          tier={tier}
          onTierChange={setTier}
          language={language}
          onLanguageChange={setLanguage}
          sessionStatus={sessionStatus}
          locked={locked}
        />

        <div className="min-w-0">
          {channel === "browser" ? (
            <TestStudioLivePanel
              agentId={agentId}
              tier={tier}
              languageCode={language}
              onTrace={onTrace}
              onCallStart={onCallStart}
              onCallEnd={onCallEnd}
              onStatusChange={setSessionStatus}
            />
          ) : (
            <SkeuoPanel
              title="PSTN · Plivo"
              description="Register numbers, assign agent, place test call"
              padding="md"
              className="console-page-enter"
            >
              <PstnTestPanel agentId={agentId} tier={tier} />
            </SkeuoPanel>
          )}
        </div>

        <TestStudioDiagnostics
          callId={callId}
          channel={channel}
          callEnded={callEnded}
          events={events}
          memoryJson={memoryJson}
        />
      </div>

      <LatencyWaterfallPanel events={events} />

      <div className="grid gap-4 lg:grid-cols-2">
        <SkeuoPanel title="Archive checklist" description="Post-call artifacts under data/calls/{call_id}/" padding="md">
          <ul className="space-y-1 text-xs text-text-muted">
            <li>meta.json · transcript.jsonl · mix.wav</li>
            <li>outcome.json · working_memory.json</li>
            <li>memory_events.jsonl · trace.json</li>
          </ul>
          {callId && <p className="mt-3 font-mono text-[10px] text-text-subtle break-all">{callId}</p>}
        </SkeuoPanel>
      </div>

      {callId && callEnded && (
        <SkeuoPanel title="Call review" description="Transcript, memory, outcome — same as Calls" padding="md">
          <CallDetailView callId={callId} />
        </SkeuoPanel>
      )}
    </div>
  );
}
