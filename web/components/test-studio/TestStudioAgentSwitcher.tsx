"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ensureArray } from "@/lib/ensure-array";
import { refreshPortalSession } from "@/lib/auth-client";
import { TEST_STUDIO_AGENTS_CHANGED } from "@/lib/agent-language";
import { testStudioAgentPath, testStudioHomePath } from "@/components/test-studio/TestStudioAgentSidebar";
import type { AgentRackItem } from "@/components/agents/AgentRackCard";

export function TestStudioAgentSwitcher({
  agentId,
  portal,
}: {
  agentId: string;
  portal: "app" | "dev";
}) {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentRackItem[]>([]);

  const loadAgents = useCallback(async () => {
    try {
      if (portal === "dev") await refreshPortalSession("dev");
      const r = await fetch("/api/agents", { credentials: "include" });
      if (!r.ok) return;
      const j = await r.json();
      setAgents(ensureArray<AgentRackItem>(j.agents));
    } catch {
      /* switcher is best-effort */
    }
  }, [portal]);

  useEffect(() => {
    void loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    const onChanged = () => void loadAgents();
    window.addEventListener(TEST_STUDIO_AGENTS_CHANGED, onChanged);
    return () => window.removeEventListener(TEST_STUDIO_AGENTS_CHANGED, onChanged);
  }, [loadAgents]);

  return (
    <div className="flex min-w-0 items-center gap-2" data-testid="test-studio-agent-switcher">
      <label className="sr-only" htmlFor="studio-agent-switcher">
        Switch agent lab
      </label>
      <select
        id="studio-agent-switcher"
        className="min-w-[10rem] max-w-[16rem] rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-sm"
        value={agentId}
        onChange={(e) => router.push(testStudioAgentPath(e.target.value, portal))}
      >
        {agents.length === 0 ? (
          <option value={agentId}>Current agent</option>
        ) : (
          agents.map((agent) => (
            <option key={agent.agent_id} value={agent.agent_id}>
              {agent.name || agent.agent_id}
            </option>
          ))
        )}
      </select>
      <a
        href={testStudioHomePath(portal)}
        className="shrink-0 text-xs font-medium text-text-muted hover:text-text"
      >
        All labs
      </a>
    </div>
  );
}
