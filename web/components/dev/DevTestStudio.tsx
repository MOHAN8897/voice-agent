"use client";

import { useEffect, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import { AgentTestStudio } from "@/components/test-studio/AgentTestStudio";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { refreshPortalSession } from "@/lib/auth-client";

export function DevTestStudio() {
  const [agents, setAgents] = useState<{ agent_id: string; name: string }[]>([]);
  const [agentId, setAgentId] = useState("");

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
      <SkeuoPanel title="Agent selector" description="Pick agent for global Test Studio" padding="md">
        <label className="block text-sm">
          <span className="text-text-muted">Agent</span>
          <select
            className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2.5 text-sm"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
          >
            {agents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>{a.name}</option>
            ))}
          </select>
        </label>
      </SkeuoPanel>

      {agentId && <AgentTestStudio agentId={agentId} portal="dev" />}
    </div>
  );
}
