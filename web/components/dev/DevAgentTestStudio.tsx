"use client";

import { useState } from "react";
import { LiveVoiceSession, type SessionTraceEvent } from "@/components/live/LiveVoiceSession";
import { DevCard } from "@/components/dev/DevCard";
import { SessionTracePanel } from "@/components/dev/SessionTracePanel";

export function DevAgentTestStudio({ agentId }: { agentId: string }) {
  const [events, setEvents] = useState<SessionTraceEvent[]>([]);
  const [memoryJson, setMemoryJson] = useState<string>("");

  function onTrace(event: SessionTraceEvent) {
    setEvents((prev) => [...prev, event]);
    if (event.kind === "call" && event.detail.startsWith("started ")) {
      const callId = event.detail.replace("started ", "");
      fetch(`/api/call/${callId}/memory/projection`, { credentials: "include" })
        .then((r) => (r.ok ? r.json() : null))
        .then((j) => setMemoryJson(JSON.stringify(j?.projection || j, null, 2)))
        .catch(() => setMemoryJson(""));
    }
  }

  return (
    <div className="space-y-6">
      <DevCard title="Live session">
        <LiveVoiceSession agentId={agentId} onTrace={onTrace} />
      </DevCard>
      <SessionTracePanel events={events} />
      <div className="grid gap-4 lg:grid-cols-2">
        <DevCard title="Memory projection inspector">
          <pre className="max-h-48 overflow-auto font-mono text-[11px] text-text-muted">
            {memoryJson || "Start a call to inspect server-owned memory projection."}
          </pre>
        </DevCard>
        <DevCard title="PSTN / Plivo test">
          <p className="text-sm text-text-muted">
            Outbound and inbound PSTN share the same call ledger. Configure Plivo credentials in Environment, assign
            numbers under Business Integrations, then dial from a campaign or inbound webhook.
          </p>
        </DevCard>
      </div>
    </div>
  );
}
