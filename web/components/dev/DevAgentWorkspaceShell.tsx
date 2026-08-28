"use client";

import { useEffect, useState } from "react";
import { SetupProgressStrip, SkeuoWorkspaceNav } from "@/components/agents/SkeuoWorkspaceNav";
import { ConsolePage } from "@/components/console/ConsolePage";
import { StatusBadge } from "@/components/console/StatusBadge";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";

export function DevAgentWorkspaceShell({
  agentId,
  children,
}: {
  agentId: string;
  children: React.ReactNode;
}) {
  const [agent, setAgent] = useState<{
    name?: string;
    status?: string;
    default_tier?: string;
    languages?: string[];
    environment?: string;
    active_compiled_brain_version?: string | null;
  }>({});

  useEffect(() => {
    fetch(`/api/agents/${agentId}`, { credentials: "include" })
      .then((r) => r.json())
      .then((j) => setAgent(j.agent || {}));
  }, [agentId]);

  const agentName = agent.name || agentId;
  const status = agent.status || "";
  const env = agent.environment || "development";
  const tier = agent.default_tier || "medium";
  const langs = (agent.languages || ["te-IN"]).join(", ");
  const version = agent.active_compiled_brain_version || "—";

  return (
    <ConsolePage>
      <div className="skeuo-panel rounded-skeuo-lg border border-surface-border-subtle p-5 md:p-6">
        <p className="label-caps text-text-subtle">Agent workspace</p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight text-text md:text-3xl">{agentName}</h1>
          {status && (
            <StatusBadge tone={status === "active" ? "success" : "muted"}>{status.toUpperCase()}</StatusBadge>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <SkeuoBadge tone="muted">Env {env}</SkeuoBadge>
          <SkeuoBadge tone="accent">Tier {tier}</SkeuoBadge>
          <SkeuoBadge tone="info">{langs}</SkeuoBadge>
          <SkeuoBadge tone="muted">v{version}</SkeuoBadge>
        </div>
        <p className="mt-2 font-mono text-[10px] text-text-subtle">{agentId}</p>
        <SetupProgressStrip agentId={agentId} portal="dev" />
      </div>

      <div className="sticky top-0 z-30 mt-6 border-b border-surface-border-subtle bg-surface/95 py-2 backdrop-blur supports-[backdrop-filter]:bg-surface/90">
        <SkeuoWorkspaceNav agentId={agentId} portal="dev" />
      </div>
      {children}
    </ConsolePage>
  );
}
