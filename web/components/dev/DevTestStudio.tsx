"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ensureArray } from "@/lib/ensure-array";
import { AgentTestStudio } from "@/components/test-studio/AgentTestStudio";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { refreshPortalSession } from "@/lib/auth-client";

export function DevTestStudio() {
  const searchParams = useSearchParams();
  const agentFromQuery = searchParams.get("agent") || "";
  const [agents, setAgents] = useState<{ agent_id: string; name: string }[]>([]);
  const [agentId, setAgentId] = useState(agentFromQuery);

  useEffect(() => {
    if (agentFromQuery) setAgentId(agentFromQuery);
  }, [agentFromQuery]);

  useEffect(() => {
    refreshPortalSession("dev").then(() =>
      fetch("/api/agents", { credentials: "include" })
        .then((r) => r.json())
        .then((j) => {
          const list = ensureArray<{ agent_id: string; name: string }>(j.agents);
          setAgents(list);
          if (agentFromQuery && list.some((a) => a.agent_id === agentFromQuery)) {
            setAgentId(agentFromQuery);
          } else if (list[0]) {
            setAgentId((current) => current || list[0].agent_id);
          }
        })
    );
  }, [agentFromQuery]);

  return (
    <div className="space-y-6">
      <SkeuoPanel
        title="Agent under test"
        description="Agents tab is for editing brain, voice, and tools. Test Studio is the live voice lab — pick an agent and stack here."
        padding="md"
      >
        <label className="block text-sm">
          <span className="text-text-muted">Agent</span>
          <select
            className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2.5 text-sm"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
          >
          {agents.length === 0 ? (
            <option value="">No agents — create one in Agents</option>
          ) : (
            agents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>
                {a.name}
              </option>
            ))
          )}
          </select>
        </label>
      </SkeuoPanel>

      {agentId && <AgentTestStudio agentId={agentId} portal="dev" />}
    </div>
  );
}
