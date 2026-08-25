"use client";

import { useCallback, useEffect, useState } from "react";
import type { SessionTraceEvent } from "@/components/live/LiveVoiceSession";
import { CallDetailView } from "@/components/calls/CallDetailView";
import { DevCard } from "@/components/dev/DevCard";
import { SessionTracePanel } from "@/components/dev/SessionTracePanel";
import { BrowserTestPanel } from "@/components/dev/test-studio/BrowserTestPanel";
import { CallLifecyclePanel } from "@/components/dev/test-studio/CallLifecyclePanel";
import { PstnTestPanel } from "@/components/dev/test-studio/PstnTestPanel";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type ChannelTab = "browser" | "pstn";

export function DevAgentTestStudio({ agentId }: { agentId: string }) {
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
    refreshPortalSession("dev");
    fetch(`/api/agents/${agentId}`, { credentials: "include" })
      .then((r) => r.json())
      .then((j) => {
        if (j.agent?.default_tier) setTier(j.agent.default_tier);
      });
  }, [agentId]);

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
    refreshMemory(id);
    portalFetch("dev", `/api/call/${id}/memory/projection`).then(async (r) => {
      if (r.ok) {
        const j = await r.json();
        setMemoryJson(JSON.stringify(j?.projection || j, null, 2));
      }
    });
  }

  return (
    <div className="space-y-6">
      <DevCard title="Test configuration" description="Locks at call/start — same lifecycle as production" delayMs={0}>
        <div className="flex flex-wrap gap-2">
          {(["browser", "pstn"] as ChannelTab[]).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setChannel(c)}
              className={`rounded-xl px-4 py-2 text-sm font-medium capitalize ${
                channel === c
                  ? "bg-accent text-white shadow-glow"
                  : "border border-surface-border bg-surface-card text-text-muted hover:border-accent/40"
              }`}
            >
              {c === "browser" ? "Browser mic" : "PSTN · Plivo"}
            </button>
          ))}
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <label className="block text-sm">
            <span className="text-text-muted">Tier</span>
            <select
              disabled={locked}
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm disabled:opacity-50"
              value={tier}
              onChange={(e) => setTier(e.target.value)}
            >
              <option value="low">LOW</option>
              <option value="medium">MEDIUM</option>
              <option value="premium">PREMIUM</option>
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-text-muted">Language</span>
            <select
              disabled={locked}
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm disabled:opacity-50"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="te-IN">te-IN — Telugu</option>
              <option value="en-IN">en-IN — English</option>
              <option value="hi-IN">hi-IN — Hindi</option>
            </select>
          </label>
          <div className="rounded-xl border border-surface-border-subtle bg-surface-raised px-3 py-2 text-sm">
            <p className="text-text-muted">Session</p>
            <p className="mt-1 font-mono text-xs text-text">{sessionStatus}</p>
            {locked && <p className="mt-1 text-xs text-warning">Config locked during call</p>}
          </div>
        </div>
      </DevCard>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          {channel === "browser" ? (
            <BrowserTestPanel
              agentId={agentId}
              tier={tier}
              onTrace={onTrace}
              onCallStart={onCallStart}
              onCallEnd={onCallEnd}
              onStatusChange={setSessionStatus}
            />
          ) : (
            <PstnTestPanel agentId={agentId} tier={tier} />
          )}
        </div>
        <CallLifecyclePanel callId={callId} channel={channel} ended={callEnded} />
      </div>

      <SessionTracePanel events={events} />

      <div className="grid gap-4 lg:grid-cols-2">
        <DevCard title="Memory projection (live)" description="Layer C — what the LLM sees each turn">
          <pre className="max-h-56 overflow-auto font-mono text-[11px] text-text-muted">
            {memoryJson || "Start a call to inspect server-owned memory projection."}
          </pre>
        </DevCard>
        <DevCard title="Archive checklist" description="Post-call artifacts under data/calls/{call_id}/">
          <ul className="space-y-1 text-xs text-text-muted">
            <li>meta.json · transcript.jsonl · mix.wav</li>
            <li>outcome.json · working_memory.json</li>
            <li>memory_events.jsonl · trace.json</li>
          </ul>
          {callId && (
            <p className="mt-3 font-mono text-[10px] text-text-subtle break-all">{callId}</p>
          )}
        </DevCard>
      </div>

      {callId && callEnded && (
        <DevCard title="Call review" description="Transcript, memory, outcome — same as Business Console">
          <CallDetailView callId={callId} />
        </DevCard>
      )}
    </div>
  );
}
