"use client";

import { useEffect, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import { LiveVoiceSession, type SessionTraceEvent } from "@/components/live/LiveVoiceSession";
import { DevCard } from "@/components/dev/DevCard";
import { SessionTracePanel } from "@/components/dev/SessionTracePanel";
import { refreshPortalSession } from "@/lib/auth-client";

export function DevTestStudio() {
  const [agents, setAgents] = useState<{ agent_id: string; name: string }[]>([]);
  const [agentId, setAgentId] = useState("");
  const [tier, setTier] = useState("medium");
  const [events, setEvents] = useState<SessionTraceEvent[]>([]);

  useEffect(() => {
    refreshPortalSession("dev").then(() =>
      fetch("/api/agents", { credentials: "include" })
        .then((r) => r.json())
        .then((j) => {
          const list = ensureArray<{ agent_id: string; name: string }>(j.agents);
          setAgents(list);
          if (list[0]) setAgentId(list[0].agent_id);
        })
    );
  }, []);

  return (
    <div className="space-y-6">
      <DevCard title="Test configuration" delayMs={0}>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-text-muted">Agent</span>
            <select
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
            >
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>{a.name}</option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-text-muted">Tier</span>
            <select
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
              value={tier}
              onChange={(e) => setTier(e.target.value)}
            >
              <option value="low">LOW</option>
              <option value="medium">MEDIUM</option>
              <option value="premium">PREMIUM</option>
            </select>
          </label>
        </div>
      </DevCard>

      <DevCard title="Live session" delayMs={80}>
        <LiveVoiceSession
          agentId={agentId}
          tier={tier}
          onTrace={(e) => setEvents((prev) => [...prev, e])}
        />
      </DevCard>

      <SessionTracePanel events={events} />
    </div>
  );
}
