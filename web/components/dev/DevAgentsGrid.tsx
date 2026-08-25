"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import { AGENT_WORKSPACE_TABS } from "@/lib/constants";

type Agent = { agent_id: string; name: string; status?: string; default_tier?: string };

export function DevAgentsGrid() {
  const [agents, setAgents] = useState<Agent[]>([]);

  useEffect(() => {
    fetch("/api/agents", { credentials: "include" })
      .then((r) => r.json())
      .then((j) => setAgents(j.agents || []));
  }, []);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {agents.map((agent, i) => (
        <DevCard key={agent.agent_id} delayMs={i * 50}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-text">{agent.name}</h3>
              <p className="mt-1 font-mono text-xs text-text-subtle">{agent.agent_id}</p>
            </div>
            <span className="rounded-full border border-surface-border px-2 py-0.5 text-[10px] uppercase tracking-wider text-text-muted">
              {agent.default_tier || "medium"}
            </span>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {AGENT_WORKSPACE_TABS.map((tab) => (
              <Link
                key={tab.slug}
                href={`/dev/agents/${agent.agent_id}/${tab.slug}`}
                className="rounded-lg border border-surface-border-subtle px-2.5 py-1 text-xs text-text-muted hover:border-accent/40 hover:text-accent"
              >
                {tab.label}
              </Link>
            ))}
            <Link
              href={`/dev/agents/${agent.agent_id}/test`}
              className="rounded-lg bg-accent-dim px-2.5 py-1 text-xs font-medium text-accent"
            >
              Test Studio
            </Link>
            <Link
              href={`/dev/agents/${agent.agent_id}/summary`}
              className="rounded-lg border border-accent/30 px-2.5 py-1 text-xs font-medium text-accent"
            >
              Open studio
            </Link>
          </div>
        </DevCard>
      ))}
    </div>
  );
}
